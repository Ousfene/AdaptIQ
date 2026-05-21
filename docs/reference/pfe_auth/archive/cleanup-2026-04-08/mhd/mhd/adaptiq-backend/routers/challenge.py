"""
routers/challenge.py — FastAPI router for the Challenge Room.
"""

from __future__ import annotations

import json
import random
import logging
import uuid
from typing import Optional, Annotated

from fastapi import APIRouter, HTTPException, Depends, Request, Body
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from pydantic_challenge import (
    UserRankOut,
    StartSessionRequest,
    StartSessionOut,
    ChallengeSessionOut,
    ChangeLevelRequest,
    ChangeLevelOut,
    GenerateChallengeQuestionRequest,
    ChallengeQuestionOut,
    SubmitChallengeAnswerRequest,
    SubmitChallengeAnswerOut,
    ForceLevelChange,
    EndSessionOut,
)

from database.challenge_models import ChallengeSession, ChallengeAnswer, ChallengeRanking

from services.challenge_service import (
    get_available_levels,
    is_level_allowed,
    calculate_points,
    check_streak_trigger,
    apply_level_change,
    update_streaks_after_answer,
    get_or_create_ranking,
    create_challenge_session,
    get_challenge_session,
    record_challenge_answer,
    update_session_after_answer,
    finalize_session,
    update_global_ranking,
    has_answered_question,
    CHALLENGE_POINTS_TABLE,
)

logger = logging.getLogger(__name__)
challenge_router = APIRouter(prefix="/api/challenge", tags=["Challenge Room"])


# ─────────────────────────────────────────────────────────────────────────
# LEVEL PROMPT CONFIG
# Describes exactly what the LLM must produce for each level.
# ─────────────────────────────────────────────────────────────────────────

LEVEL_PROMPTS = {
    1: {
        "description": "VERY EASY — well-known fact. Famous capitals, major battles, common dates.",
        "options_rule": "Return ONLY 2 options: 'correct' and 'wrong1'. Leave 'wrong2' and 'wrong3' as empty strings.",
        "options_count": 2,
        "is_free_text": False,
    },
    2: {
        "description": "EASY — straightforward fact. The 2 wrong answers must be obviously incorrect (different category, wrong continent, wrong century).",
        "options_rule": "Return 4 options. 'wrong1' and 'wrong2' must be obviously wrong. 'wrong3' should be slightly plausible.",
        "options_count": 4,
        "is_free_text": False,
    },
    3: {
        "description": "MEDIUM — requires connecting two facts. The question itself should be harder than level 2.",
        "options_rule": "Return 4 options. 2 of the wrong answers must be plausible (same category, same region, similar era). 1 wrong answer can be obvious.",
        "options_count": 4,
        "is_free_text": False,
    },
    4: {
        "description": "HARD — multi-hop reasoning, lesser-known facts. Expert level.",
        "options_rule": "Return 4 options. ALL 4 options must be plausible and from the same category. The user should genuinely be unsure.",
        "options_count": 4,
        "is_free_text": False,
    },
    5: {
        "description": "VERY HARD — obscure expert knowledge. Pre-medieval events, minor capitals, rare treaties.",
        "options_rule": "This is a FREE TEXT question. Do NOT generate options. Set 'wrong1', 'wrong2', 'wrong3' all to empty strings. The user will type their answer.",
        "options_count": 0,
        "is_free_text": True,
    },
}

# System prompt for the challenge LLM — stricter than ClassicRoom
CHALLENGE_SYSTEM_PROMPT = """You are an expert educational MCQ generator for a competitive quiz platform.
Return ONLY a valid JSON object — no markdown, no backticks, no extra text.

STRICT JSON structure:
{
  "text": "the question",
  "correct": "the single correct answer",
  "wrong1": "wrong answer or empty string",
  "wrong2": "wrong answer or empty string",
  "wrong3": "wrong answer or empty string",
  "explanation": "1-2 sentences with an interesting fact or context — NOT just restating the answer"
}

RULES:
- Follow the options_rule exactly for this level
- The explanation must be genuinely interesting — a fun fact, historical context, or surprising detail
- Return ONLY the JSON, nothing else"""


async def _generate_challenge_question_llm(
    llm,
    topic: str,
    level: int,
    context: str = "",
) -> Optional[dict]:
    """
    Call the LLM with a level-specific prompt.
    Returns a question dict or None on failure.
    """
    cfg = LEVEL_PROMPTS[level]

    user_prompt = f"""TOPIC: {topic}
LEVEL: {level}/5 — {cfg['description']}
OPTIONS RULE: {cfg['options_rule']}

{"CONTEXT (base your question on this):" + chr(10) + context[:600] if context else "Generate a unique question about " + topic + "."}

Generate ONE unique question following the level and options rule exactly.
Return ONLY the JSON."""

    try:
        response = await llm._chat_completion(
            system    = CHALLENGE_SYSTEM_PROMPT,
            user      = user_prompt,
            temperature = 0.92,
            max_tokens  = 400,
        )
        if not response:
            return None

        parsed = llm._parse_json_response(response)
        if not parsed:
            return None

        if not parsed.get("text") or not parsed.get("correct"):
            return None

        correct = str(parsed["correct"]).strip()

        # ── Build options based on level ──────────────────────────────────
        if cfg["is_free_text"]:
            # Level 5: no options, free text input
            options = []
        elif cfg["options_count"] == 2:
            # Level 1: only 2 options
            wrong1 = str(parsed.get("wrong1", "")).strip()
            if not wrong1:
                # LLM didn't follow instructions — generate a generic wrong
                wrong1 = "None of the above"
            options = [correct, wrong1]
            random.shuffle(options)
        else:
            # Levels 2, 3, 4: 4 options
            wrongs = [
                str(parsed.get("wrong1", "")).strip(),
                str(parsed.get("wrong2", "")).strip(),
                str(parsed.get("wrong3", "")).strip(),
            ]
            # Filter out empty strings
            wrongs = [w for w in wrongs if w]
            # Pad if LLM returned fewer than 3 wrongs
            pads = ["None of the above", "Cannot be determined", "All of the above"]
            while len(wrongs) < 3:
                wrongs.append(pads.pop(0))
            options = [correct] + wrongs[:3]
            # Remove duplicates
            seen = set()
            unique = []
            for o in options:
                if o.lower() not in seen:
                    seen.add(o.lower())
                    unique.append(o)
            while len(unique) < 4:
                unique.append(pads.pop(0) if pads else "Unknown")
            options = unique[:4]
            random.shuffle(options)

        return {
            "id":           str(uuid.uuid4()),
            "text":         str(parsed["text"]).strip(),
            "options":      options,
            "correctAnswer": correct,
            "explanation":  str(parsed.get("explanation", "")).strip(),
            "is_free_text": cfg["is_free_text"],
        }

    except Exception as e:
        logger.error(f"Challenge LLM generation failed at level {level}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────
# DEPENDENCY INJECTORS
# ─────────────────────────────────────────────────────────────────────────

def get_app_state(request: Request):
    return request.app.state


async def get_db(request: Request):
    app_st = get_app_state(request)
    factory = getattr(app_st, "db_session_factory", None)
    if factory is None:
        raise HTTPException(503, "Database not available")
    async with factory() as session:
        yield session


async def get_llm(request: Request):
    app_st = get_app_state(request)
    llm = getattr(app_st, "llm_client", None)
    if llm is None:
        raise HTTPException(503, "LLM service not available")
    return llm


async def get_rag(request: Request):
    app_st = get_app_state(request)
    rag = getattr(app_st, "rag_pipeline", None)
    if rag is None:
        raise HTTPException(503, "RAG pipeline not available")
    return rag


async def get_http(request: Request):
    app_st = get_app_state(request)
    client = getattr(app_st, "http_client", None)
    if client is None:
        raise HTTPException(503, "HTTP client not available")
    return client


# ─────────────────────────────────────────────────────────────────────────
# ANSWER VERIFICATION
# ─────────────────────────────────────────────────────────────────────────

async def _verify_answer(db: AsyncSession, question_id: str, selected: str) -> bool:
    """
    For MCQ levels (1-4): exact match against stored correct_answer.
    For free-text level 5: case-insensitive, strip whitespace.
    Both use the same comparison — level 5 is just more forgiving because
    the user typed it themselves.
    """
    from database.models import QuestionBank
    try:
        stmt = select(QuestionBank.correct_answer).where(
            QuestionBank.id == uuid.UUID(question_id)
        )
        result = await db.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            logger.error(f"VERIFICATION FAILED: Question {question_id} not found in database!")
            return False
        
        # Normalize both for comparison
        selected_clean = str(selected).strip().lower()
        correct_clean = str(row).strip().lower()
        
        is_match = selected_clean == correct_clean
        
        logger.debug(
            f"Verification: selected_raw='{selected}' correct_raw='{row}' "
            f"selected_clean='{selected_clean}' correct_clean='{correct_clean}' "
            f"match={is_match}"
        )
        
        return is_match
        
    except Exception as e:
        logger.error(f"CRITICAL: Exception during answer verification: {e}")
        return False


# ═════════════════════════════════════════════════════════════════════════
# ENDPOINT 1 — GET /api/challenge/user/{user_id}/rank
# ═════════════════════════════════════════════════════════════════════════

@challenge_router.get("/user/{user_id}/rank", response_model=UserRankOut)
async def get_user_rank(
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    ranking = await get_or_create_ranking(db, user_id)
    return UserRankOut(
        current_rank     = ranking.current_rank,
        rank_points      = ranking.rank_points,
        available_levels = get_available_levels(ranking.current_rank),
        total_sessions   = ranking.total_sessions,
        total_questions  = ranking.total_questions,
    )


# ═════════════════════════════════════════════════════════════════════════
# ENDPOINT 2 — POST /api/challenge/start-session
# ═════════════════════════════════════════════════════════════════════════

@challenge_router.post("/start-session", response_model=StartSessionOut)
async def start_session(
    body: Annotated[StartSessionRequest, Body()],
    db: AsyncSession = Depends(get_db),
):
    ranking   = await get_or_create_ranking(db, body.user_id)
    available = get_available_levels(ranking.current_rank)

    if body.starting_level not in available:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Level {body.starting_level} is not available for rank "
                f"{ranking.current_rank}. Available levels: {available}"
            ),
        )

    session = await create_challenge_session(
        db,
        user_id        = body.user_id,
        topic          = body.topic,
        starting_level = body.starting_level,
    )

    logger.info(
        f"Challenge session started: user={body.user_id[:8]} "
        f"rank={ranking.current_rank} level={body.starting_level} topic={body.topic}"
    )

    return StartSessionOut(
        session_id       = str(session.id),
        current_level    = session.current_level,
        rank_points      = 0,
        available_levels = available,
        current_rank     = ranking.current_rank,
        topic            = body.topic,
    )


# ═════════════════════════════════════════════════════════════════════════
# ENDPOINT 3 — GET /api/challenge/session/{session_id}
# ═════════════════════════════════════════════════════════════════════════

@challenge_router.get("/session/{session_id}", response_model=ChallengeSessionOut)
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    session = await get_challenge_session(db, session_id)
    if session is None:
        raise HTTPException(404, f"Session {session_id} not found")

    return ChallengeSessionOut(
        session_id      = str(session.id),
        user_id         = str(session.user_id),
        topic           = session.topic,
        starting_level  = session.starting_level,
        current_level   = session.current_level,
        rank_points     = session.rank_points,
        streak_correct  = session.streak_correct,
        streak_wrong    = session.streak_wrong,
        total_questions = session.total_questions,
        correct_answers = session.correct_answers,
        is_completed    = session.is_completed,
    )


# ═════════════════════════════════════════════════════════════════════════
# ENDPOINT 4 — PATCH /api/challenge/session/{session_id}/change-level
# ═════════════════════════════════════════════════════════════════════════

@challenge_router.patch("/session/{session_id}/change-level", response_model=ChangeLevelOut)
async def change_level(
    session_id: str,
    body: Annotated[ChangeLevelRequest, Body()],
    db: AsyncSession = Depends(get_db),
):
    session = await get_challenge_session(db, session_id)
    if session is None:
        raise HTTPException(404, f"Session {session_id} not found")
    if session.is_completed:
        raise HTTPException(400, "Cannot change level on a completed session")

    # Get user rank to enforce rank-bounded level change
    ranking   = await get_or_create_ranking(db, str(session.user_id))
    new_level = apply_level_change(session.current_level, body.direction, ranking.current_rank)

    session.current_level = new_level
    await db.commit()

    logger.info(
        f"Level change: session={session_id[:8]} "
        f"{body.direction} → level {new_level} ({body.reason})"
    )

    return ChangeLevelOut(
        session_id = session_id,
        new_level  = new_level,
        direction  = body.direction,
        reason     = body.reason,
    )


# ═════════════════════════════════════════════════════════════════════════
# ENDPOINT 5 — POST /api/challenge/generate-question
# ═════════════════════════════════════════════════════════════════════════

@challenge_router.post("/generate-question", response_model=ChallengeQuestionOut)
async def generate_challenge_question(
    request: Request,
    body: Annotated[GenerateChallengeQuestionRequest, Body()],
    db          : AsyncSession = Depends(get_db),
    llm                        = Depends(get_llm),
    rag                        = Depends(get_rag),
    http_client                = Depends(get_http),
):
    session = await get_challenge_session(db, body.session_id)
    if session is None:
        raise HTTPException(404, f"Session {body.session_id} not found")
    if session.is_completed:
        raise HTTPException(400, "Session is already completed")

    question_dict = None
    context       = ""

    # ── Try RAG for context (levels 3-5 benefit most from real context) ──
    # We use RAG to get context text, then pass it to our level-specific prompt
    if body.level >= 3:
        try:
            rag_result = await rag.run(
                topic         = body.topic,
                difficulty    = body.level,
                user_accuracy = 0.5,
                llm_client    = llm,
                http_client   = http_client,
            )
            if rag_result:
                # RAG returned a question — but we still regenerate with our
                # level-specific prompt using the RAG context as seed
                context = rag_result.get("text", "")
                logger.info(f"RAG provided context for level {body.level}")
        except Exception as e:
            logger.warning(f"RAG context fetch failed: {e}")

    # ── Generate with level-specific prompt ───────────────────────────────
    question_dict = await _generate_challenge_question_llm(
        llm     = llm,
        topic   = body.topic,
        level   = body.level,
        context = context,
    )

    if not question_dict:
        raise HTTPException(503, "Could not generate a question. Please try again.")

    # ── Store in question_bank ────────────────────────────────────────────
    from database import crud as classic_crud
    try:
        await classic_crud.store_question(
            db,
            question_id    = question_dict["id"],
            question_text  = question_dict["text"],
            correct_answer = question_dict["correctAnswer"],
            options        = question_dict["options"],
            explanation    = question_dict.get("explanation", ""),
            topic          = body.topic,
            difficulty     = body.level,
            source         = "challenge_llm",
        )
    except Exception as e:
        logger.error(f"CRITICAL: Could not store challenge question: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to persist question. Cannot proceed with this challenge."
        )

    correct_pts, _ = CHALLENGE_POINTS_TABLE[body.level]

    return ChallengeQuestionOut(
        id            = question_dict["id"],
        text          = question_dict["text"],
        options       = question_dict["options"],
        correctAnswer = question_dict["correctAnswer"],
        explanation   = question_dict.get("explanation", ""),
        level         = body.level,
        points_value  = correct_pts,
        is_free_text  = question_dict.get("is_free_text", False),
    )


# ═════════════════════════════════════════════════════════════════════════
# ENDPOINT 6 — POST /api/challenge/submit-answer
# ═════════════════════════════════════════════════════════════════════════

@challenge_router.post("/submit-answer", response_model=SubmitChallengeAnswerOut)
async def submit_challenge_answer(
    request: Request,
    body: Annotated[SubmitChallengeAnswerRequest, Body()],
    db: AsyncSession = Depends(get_db),
):
    # VALIDATION: Check answer is not empty
    if not body.answer or not str(body.answer).strip():
        logger.error(f"EMPTY ANSWER SUBMITTED: user={body.user_id} session={body.session_id} question={body.question_id}")
        raise HTTPException(
            status_code=400,
            detail="Answer cannot be empty. Please select an option or type your answer."
        )
    
    session = await get_challenge_session(db, body.session_id)
    if session is None:
        raise HTTPException(404, f"Session {body.session_id} not found")
    if session.is_completed:
        raise HTTPException(400, "Session already completed")

    # Anti-abuse: no duplicate answers
    if await has_answered_question(db, body.session_id, body.question_id):
        raise HTTPException(409, "This question has already been answered in this session")

    # Verify question exists in database
    from database.models import QuestionBank
    question_check = await db.execute(
        select(QuestionBank).where(QuestionBank.id == uuid.UUID(body.question_id))
    )
    question_row = question_check.scalar_one_or_none()
    if question_row is None:
        raise HTTPException(
            status_code=400,
            detail="Question not found in database. Was it properly generated?"
        )

    # Verify answer server-side
    is_correct    = await _verify_answer(db, body.question_id, body.answer)
    logger.info(
        f"ANSWER VERIFICATION: user={body.user_id[:8]} question={body.question_id[:8]} "
        f"submitted='{body.answer}' correct_stored='{question_row.correct_answer}' "
        f"match={is_correct}"
    )
    current_level = session.current_level
    points_change = calculate_points(current_level, is_correct)

    # Update streaks
    new_streak_correct, new_streak_wrong = update_streaks_after_answer(
        session.streak_correct, session.streak_wrong, is_correct
    )

    # Check streak trigger — use rank-bounded level change
    level_trigger = check_streak_trigger(new_streak_correct, new_streak_wrong)
    new_level     = current_level
    force_level_change_out: Optional[ForceLevelChange] = None

    if level_trigger:
        # Get user rank for boundary enforcement
        ranking   = await get_or_create_ranking(db, str(session.user_id))
        new_level = apply_level_change(
            current_level,
            level_trigger["direction"],
            ranking.current_rank,           # ← rank boundary enforced here
        )

        # Reset the streak that triggered the change
        if level_trigger["direction"] == "up":
            new_streak_correct = 0
        else:
            new_streak_wrong = 0

        force_level_change_out = ForceLevelChange(
            direction = level_trigger["direction"],
            reason    = level_trigger["reason"],
        )
        logger.info(
            f"Level change triggered: session={body.session_id[:8]} "
            f"{level_trigger['direction']} → level {new_level} "
            f"(rank boundary enforced)"
        )

    # Persist answer row
    try:
        await record_challenge_answer(
            db,
            session_id      = body.session_id,
            question_id     = body.question_id,
            chosen_answer   = body.answer,
            is_correct      = is_correct,
            points_change   = points_change,
            level_at_answer = current_level,
            time_taken      = body.time_taken,
        )
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Duplicate answer detected")

    # Update session state
    updated_session = await update_session_after_answer(
        db,
        session            = session,
        is_correct         = is_correct,
        points_change      = points_change,
        new_streak_correct = new_streak_correct,
        new_streak_wrong   = new_streak_wrong,
        new_level          = new_level,
    )

    logger.info(
        f"Challenge answer: correct={is_correct} pts={points_change:+d} "
        f"level={current_level}→{new_level} "
        f"session_pts={updated_session.rank_points}"
    )

    return SubmitChallengeAnswerOut(
        is_correct         = is_correct,
        points_change      = points_change,
        new_rank_points    = updated_session.rank_points,
        new_level          = new_level,
        streak_correct     = new_streak_correct,
        streak_wrong       = new_streak_wrong,
        force_level_change = force_level_change_out,
    )


# ═════════════════════════════════════════════════════════════════════════
# ENDPOINT 7 — POST /api/challenge/session/{session_id}/end
# ═════════════════════════════════════════════════════════════════════════

@challenge_router.post("/session/{session_id}/end", response_model=EndSessionOut)
async def end_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    session = await get_challenge_session(db, session_id)
    if session is None:
        raise HTTPException(404, f"Session {session_id} not found")

    if session.is_completed:
        ranking = await get_or_create_ranking(db, str(session.user_id))
        return EndSessionOut(
            session_id          = session_id,
            total_questions     = session.total_questions,
            correct_answers     = session.correct_answers,
            total_points_earned = session.rank_points,
            new_rank            = ranking.current_rank,
            new_rank_points     = ranking.rank_points,
            rank_changed        = False,
        )

    old_ranking = await get_or_create_ranking(db, str(session.user_id))
    old_rank    = old_ranking.current_rank

    await finalize_session(db, session)

    updated_ranking = await update_global_ranking(
        db,
        user_id           = str(session.user_id),
        session_points    = session.rank_points,
        session_questions = session.total_questions,
        session_streak    = max(session.streak_correct, session.streak_wrong),
    )

    rank_changed = updated_ranking.current_rank != old_rank

    logger.info(
        f"Session ended: session={session_id[:8]} "
        f"pts={session.rank_points} rank={old_rank}→{updated_ranking.current_rank}"
    )

    return EndSessionOut(
        session_id          = session_id,
        total_questions     = session.total_questions,
        correct_answers     = session.correct_answers,
        total_points_earned = session.rank_points,
        new_rank            = updated_ranking.current_rank,
        new_rank_points     = updated_ranking.rank_points,
        rank_changed        = rank_changed,
    )