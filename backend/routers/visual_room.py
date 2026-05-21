"""
routers/visual_room.py
All VisualRoom API endpoints.

Endpoints:
  POST /api/visual/start-session         → session_id
  GET  /api/visual/next                  → VisualQuestionOut (no correct answer)
  POST /api/visual/submit                → is_correct + explanation + next_question
  GET  /api/visual/hint                  → hint text (no correct answer revealed)
  GET  /api/visual/explanation           → explanation for a question_id
  POST /api/visual/session/{id}/end      → session summary

Design notes:
  - correct_answer is NEVER sent to the frontend in the question payload.
    It is only revealed in the submit response AFTER the user answers.
  - Hints are generated from question_text + paragraph only — the correct
    answer is not passed to the hint generator.
  - Sessions track seen question IDs to avoid repeats within one session.
  - LLM generation happens on first use of a question, then the result is
    stored so subsequent calls are instant DB reads.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.visual_models import VisualQuestion, VisualSession
from pydantic_visual import (
    StartVisualSessionRequest,
    StartVisualSessionResponse,
    VisualQuestionOut,
    SubmitVisualAnswerRequest,
    SubmitVisualAnswerResponse,
    VisualHintResponse,
    VisualExplanationResponse,
)
from services.visual_room_service import (
    create_visual_session,
    get_visual_session,
    get_next_question,
    generate_and_store_question,
    visual_question_needs_generation,
    verify_mcq_answer,
    verify_text_answer,
    update_question_stats,
    generate_visual_hint,
    _add_seen_id,
    LEVEL_OPTIONS_COUNT,
)

logger = logging.getLogger(__name__)
visual_router = APIRouter(prefix="/api/visual", tags=["Visual Room"])


# ─── Dependencies ─────────────────────────────────────────────────────────────

async def _get_db(request: Request):
    factory = getattr(request.app.state, "db_session_factory", None)
    if factory is None:
        raise HTTPException(503, "Database not available")
    async with factory() as db:
        yield db


async def _get_llm(request: Request):
    llm = getattr(request.app.state, "llm_client", None)
    if llm is None:
        raise HTTPException(503, "LLM not available — set GROQ_API_KEY")
    return llm


def _question_to_out(q: VisualQuestion, level: int) -> VisualQuestionOut:
    import json as _json
    from services.visual_room_service import should_show_shape

    try:
        options = _json.loads(q.options_json or "[]")
    except Exception:
        options = []

    if level == 5:
        options = []
        question_type = "T"
        options_count = 0
    else:
        question_type = q.question_type or "M"
        options_count = LEVEL_OPTIONS_COUNT.get(level, 4)

    # L1 always flag only. L2+ use probability.
    if level == 1:
        show_flag  = True
        show_shape = False
    else:
        use_shape  = should_show_shape(level=level, topic=q.topic, has_shape=bool(q.shape_svg))
        show_flag  = not use_shape
        show_shape = use_shape

    return VisualQuestionOut(
        id            = str(q.id),
        image_url     = q.image_url,
        text          = q.question_text or "What does this image depict?",
        options       = options,
        topic         = q.topic,
        level         = level,
        question_type = question_type,
        options_count = options_count,
        shape_svg     = q.shape_svg if show_shape else None,
        show_flag     = show_flag,
        show_shape    = show_shape,
    )

# ═══════════════════════════════════════════════════════════════════════
# POST /api/visual/start-session
# ═══════════════════════════════════════════════════════════════════════

@visual_router.post("/start-session", response_model=StartVisualSessionResponse)
async def start_visual_session(body: StartVisualSessionRequest, request: Request):
    """
    Start a new VisualRoom session.
    Creates a VisualSession row that tracks seen questions and score.
    """
    try:
        uid = uuid.UUID(str(body.user_id))
    except ValueError:
        raise HTTPException(422, f"user_id must be a valid UUID, got: {body.user_id!r}")

    async for db in _get_db(request):
        # Auto-create user if needed (same pattern as CustomRoom)
        from database.models import User
        try:
            result = await db.execute(select(User).where(User.id == uid))
            if result.scalar_one_or_none() is None:
                db.add(User(
                    id=uid,
                    email=f"guest-{str(uid)[:8]}@visual-room.local",
                    username=f"user-{str(uid)[:8]}",
                    password_hash="",
                ))
                await db.flush()
        except Exception as e:
            logger.warning(f"Could not auto-create user: {e}")

        session = await create_visual_session(
            db,
            user_id         = str(uid),
            topic           = body.topic,
            level           = body.level,
            total_questions = 10,
        )
        return StartVisualSessionResponse(
            session_id      = str(session.id),
            topic           = body.topic,
            level           = body.level,
            total_questions = session.total_questions,
        )


# ═══════════════════════════════════════════════════════════════════════
# GET /api/visual/next
# ═══════════════════════════════════════════════════════════════════════

@visual_router.get("/next", response_model=VisualQuestionOut)
async def get_next_visual_question(
    request:    Request,
    session_id: str = Query(..., description="Active session ID"),
):
    """
    Fetch the next question for an active session.

    If the question has no LLM-generated content yet (question_text IS NULL),
    generates it now and stores it before returning — so the next request is
    a fast DB read.

    Correct answer is NOT included in the response.
    """
    async for db in _get_db(request):
        llm = getattr(request.app.state, "llm_client", None)

        # Load session
        session = await get_visual_session(db, session_id)
        if session is None:
            raise HTTPException(404, f"Session {session_id} not found")
        if session.is_completed:
            raise HTTPException(400, "Session is already completed")

        # Select question
        visual_q = await get_next_question(db, session.topic, session.level, session)
        if visual_q is None:
            raise HTTPException(
                503,
                f"No visual questions available for topic={session.topic} level={session.level}. "
                "Run the ingestion script first."
            )

        # Generate content on first use OR if placeholders are present.
        # If llm is unavailable, generate_and_store_question will fall back to
        # a deterministic (caption-based) MCQ instead of "Option A/B/C/D".
        if visual_question_needs_generation(visual_q, session.level):
            visual_q = await generate_and_store_question(db, visual_q, session.level, llm)

        # Mark as seen in this session
        await _add_seen_id(db, session, str(visual_q.id))

        return _question_to_out(visual_q, session.level)


# ═══════════════════════════════════════════════════════════════════════
# POST /api/visual/submit
# ═══════════════════════════════════════════════════════════════════════

@visual_router.post("/submit", response_model=SubmitVisualAnswerResponse)
async def submit_visual_answer(body: SubmitVisualAnswerRequest, request: Request):
    """
    Submit an answer.

    Verifies server-side (correct_answer stored in DB, never exposed to frontend).
    Updates n_attempts / n_correct / difficulty_actual.
    Returns the correct answer + explanation AFTER submission.
    Optionally returns the next question in the same response to save a round-trip.
    """
    async for db in _get_db(request):
        llm = getattr(request.app.state, "llm_client", None)

        # Load question
        result = await db.execute(
            select(VisualQuestion).where(VisualQuestion.id == uuid.UUID(body.question_id))
        )
        visual_q = result.scalar_one_or_none()
        if visual_q is None:
            raise HTTPException(404, f"Question {body.question_id} not found")
        if not visual_q.correct_answer:
            raise HTTPException(400, "Question has not been generated yet — call /next first")

        # Load session
        session = await get_visual_session(db, body.session_id)
        if session is None:
            raise HTTPException(404, f"Session {body.session_id} not found")
        
        # Security: verify user owns this session
        if str(session.user_id) != body.user_id:
            raise HTTPException(403, "Not authorized to submit for this session")

        # Verify answer
        if visual_q.question_type == 'T':
            is_correct = await verify_text_answer(
                body.chosen_answer,
                visual_q.correct_answer,
                llm,
            )
        else:
            is_correct = verify_mcq_answer(body.chosen_answer, visual_q.correct_answer)

        # Update DB stats
        await update_question_stats(db, visual_q, is_correct)

        # Update session score + index
        if is_correct:
            session.score += 1
        session.current_index += 1
        if session.current_index >= session.total_questions:
            session.is_completed = True
        await db.commit()

        # Fetch next question (optional — saves a round trip for the frontend)
        next_q_out: Optional[VisualQuestionOut] = None
        if not session.is_completed:
            next_visual = await get_next_question(db, session.topic, session.level, session)
            if next_visual:
                if not next_visual.question_text and llm:
                    next_visual = await generate_and_store_question(
                        db, next_visual, session.level, llm
                    )
                await _add_seen_id(db, session, str(next_visual.id))
                next_q_out = _question_to_out(next_visual, session.level)

        logger.info(
            f"[VisualRoom] submit: q={body.question_id[:8]} "
            f"correct={is_correct} session_score={session.score}"
        )

        return SubmitVisualAnswerResponse(
            is_correct     = is_correct,
            correct_answer = visual_q.correct_answer,
            explanation    = visual_q.explanation or "No explanation available.",
            next_question  = next_q_out,
        )


# ═══════════════════════════════════════════════════════════════════════
# GET /api/visual/hint
# ═══════════════════════════════════════════════════════════════════════

@visual_router.get("/hint", response_model=VisualHintResponse)
async def get_visual_hint(
    request:     Request,
    question_id: str = Query(..., description="Question UUID"),
):
    """
    Generate a hint for the current question.

    IMPORTANT: This endpoint takes only question_id — it does NOT receive
    or reveal the correct answer. Hint is generated from question_text +
    paragraph context only.
    """
    async for db in _get_db(request):
        llm = getattr(request.app.state, "llm_client", None)

        result = await db.execute(
            select(VisualQuestion).where(VisualQuestion.id == uuid.UUID(question_id))
        )
        visual_q = result.scalar_one_or_none()
        if visual_q is None:
            raise HTTPException(404, f"Question {question_id} not found")
        if not visual_q.question_text:
            raise HTTPException(400, "Question not yet generated — call /next first")

        hint = await generate_visual_hint(
            question_text = visual_q.question_text,
            paragraph     = visual_q.paragraph or "",
            llm_client    = llm,
        )

        return VisualHintResponse(hint=hint or "Think carefully about what you see.")


# ═══════════════════════════════════════════════════════════════════════
# GET /api/visual/explanation
# ═══════════════════════════════════════════════════════════════════════

@visual_router.get("/explanation", response_model=VisualExplanationResponse)
async def get_visual_explanation(
    request:     Request,
    question_id: str = Query(..., description="Question UUID"),
):
    """
    Fetch the stored explanation for a question.
    Only useful after the user has already submitted (explanation is revealed there too).
    """
    async for db in _get_db(request):
        result = await db.execute(
            select(VisualQuestion).where(VisualQuestion.id == uuid.UUID(question_id))
        )
        visual_q = result.scalar_one_or_none()
        if visual_q is None:
            raise HTTPException(404, f"Question {question_id} not found")

        return VisualExplanationResponse(
            question_id = str(visual_q.id),
            explanation = visual_q.explanation or "No explanation available for this question.",
        )


# ═══════════════════════════════════════════════════════════════════════
# POST /api/visual/session/{session_id}/end
# ═══════════════════════════════════════════════════════════════════════

@visual_router.post("/session/{session_id}/end")
async def end_visual_session(session_id: str, request: Request):
    """End a session early or finalize it. Returns final score."""
    async for db in _get_db(request):
        session = await get_visual_session(db, session_id)
        if session is None:
            raise HTTPException(404, f"Session {session_id} not found")

        if not session.is_completed:
            session.is_completed = True
            from datetime import datetime, timezone
            session.ended_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await db.commit()

        accuracy = round(session.score / max(session.current_index, 1) * 100, 1)
        return {
            "session_id":       str(session.id),
            "topic":            session.topic,
            "level":            session.level,
            "score":            session.score,
            "questions_seen":   session.current_index,
            "total_questions":  session.total_questions,
            "accuracy_percent": accuracy,
        }
