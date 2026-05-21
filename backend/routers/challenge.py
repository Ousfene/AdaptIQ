"""
routers/challenge.py — FastAPI router for the Challenge Room.

Covers:
    - GET  /api/challenge/user/{user_id}/rank
    - POST /api/challenge/start-session
    - GET  /api/challenge/session/{session_id}
    - POST /api/challenge/change-level
    - POST /api/challenge/generate-question
    - POST /api/challenge/submit-answer
    - POST /api/challenge/end-session

Internal helper groups:
    - Access/session guards and issued-question tracking
    - Level-aware LLM generation and prompt controls
    - Dependency loaders for app-level services (LLM, RAG, HTTP)
    - Server-side answer verification and ranking/session orchestration
"""



import json
import random
import logging
import uuid
from typing import Optional, Annotated
import asyncio

from fastapi import APIRouter, HTTPException, Depends, Request, Body
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from schemas.challenge import (
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
from database.models import QuestionBank

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
from services.classic_service import ClassicService
from dependencies import limiter
from routers.auth import get_current_user, get_db

logger = logging.getLogger(__name__)
challenge_router = APIRouter(prefix="/api/challenge", tags=["Challenge Room"])
CHALLENGE_SESSION_QUESTION_TTL_SECONDS = 6 * 60 * 60


# Ensure users can only operate on their own challenge resources.
def _ensure_user_match(target_user_id: str, current_user_id: str) -> None:
    try:
        target_uuid = uuid.UUID(str(target_user_id))
    except ValueError:
        raise HTTPException(422, "user_id must be a valid UUID")
    if str(target_uuid) != current_user_id:
        raise HTTPException(403, "You are not allowed to access this user data")


# Build the cache key used for issued-question tracking per session.
def _challenge_session_question_key(session_id: str) -> str:
    return f"challenge_session_questions:{session_id}"


# Remember a generated question as issued to this session (redis/in-memory).
async def _remember_issued_question(request: Request, session_id: str, question_id: str) -> bool:
    key = _challenge_session_question_key(session_id)
    qid = str(question_id)
    redis_client = getattr(request.app.state, "redis", None)

    if redis_client is not None:
        try:
            await redis_client.sadd(key, qid)
            await redis_client.expire(key, CHALLENGE_SESSION_QUESTION_TTL_SECONDS)
            return True
        except Exception as exc:
            logger.warning("challenge issued-question redis write failed: %s", exc)

    fallback = getattr(request.app.state, "challenge_session_questions", None)
    if fallback is None:
        fallback = {}
        request.app.state.challenge_session_questions = fallback

    values = set(fallback.get(key, []))
    values.add(qid)
    fallback[key] = list(values)
    try:
        logger.debug("Remembered issued challenge question: session=%s question=%s", session_id[:8], qid[:8])
    except Exception:
        pass
    return True


# Verify whether a question was already issued in this session.
async def _session_has_issued_question(request: Request, session_id: str, question_id: str) -> bool:
    key = _challenge_session_question_key(session_id)
    qid = str(question_id)
    redis_client = getattr(request.app.state, "redis", None)

    if redis_client is not None:
        try:
            return bool(await redis_client.sismember(key, qid))
        except Exception as exc:
            logger.warning("challenge issued-question redis read failed: %s", exc)

    fallback = getattr(request.app.state, "challenge_session_questions", None)
    if fallback is None:
        return False
    return qid in set(fallback.get(key, []))


async def _get_user_seen_challenge_signatures(
    db: AsyncSession,
    user_id: uuid.UUID,
    topic: str,
) -> set[str]:
    # Use topic='mix' to gather seen questions across all topics (global dedupe)
    seen_ids = await ClassicService.get_user_seen_question_ids(
        db=db,
        user_id=user_id,
        topic="mix",
    )
    if not seen_ids:
        return set()

    result = await db.execute(
        select(QuestionBank.question_text).where(QuestionBank.id.in_(list(seen_ids)))
    )
    try:
        logger.debug("Challenge seen signatures fetched: user=%s count=%d", str(user_id)[:8], len(seen_ids))
    except Exception:
        pass
    return {
        _challenge_signature(str(text))
        for text in result.scalars().all()
        if str(text).strip()
    }


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
- QUESTION QUALITY: The question MUST be a properly formatted interrogative sentence (starting with Who, What, Where, When, Why, How, or Which).
- DO NOT generate statement-like questions with a question mark at the end.
- NEVER include the correct answer in the question text.
- Follow the options_rule exactly for this level
- Question text must be concise: one sentence, maximum 22 words
- The explanation must be genuinely interesting — a fun fact, historical context, or surprising detail
- Return ONLY the JSON, nothing else"""


# Trim generated question text to a concise single-question sentence.
def _shorten_question_text(text: str, max_words: int = 22) -> str:
    cleaned = " ".join((text or "").strip().split())
    if not cleaned:
        return ""
    first_sentence = cleaned.split(".")[0].strip()
    words = first_sentence.split()
    if len(words) <= max_words:
        return first_sentence if first_sentence.endswith("?") else f"{first_sentence}?"
    shortened = " ".join(words[:max_words]).rstrip(" ,;:")
    if not shortened.endswith("?"):
        shortened += "?"
    return shortened


# Compute a normalized text signature for duplicate-detection checks.
def _challenge_signature(text: str) -> str:
    normalized = " ".join((text or "").strip().lower().split())
    return normalized


# Generate one level-aware challenge question payload using the LLM.
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
            "text":         _shorten_question_text(str(parsed["text"])),
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
# Note: get_db is imported from routers.auth (line 52) and used by most endpoints.
# The helpers below are for LLM/RAG/HTTP dependencies only.
# ─────────────────────────────────────────────────────────────────────────

# Return app.state so helper dependencies can read shared services.
def _get_app_state(request: Request):
    """Get the FastAPI app.state object (contains llm_client, rag_pipeline, etc.)."""
    return request.app.state


# Provide the configured LLM client dependency.
async def get_llm(request: Request):
    """Get LLM client from app state. Raises 503 if unavailable."""
    app_st = _get_app_state(request)
    llm = getattr(app_st, "llm_client", None)
    if llm is None:
        raise HTTPException(503, "LLM service not available")
    return llm


# Provide the optional RAG pipeline dependency.
async def get_rag(request: Request):
    """Get RAG pipeline from app state. Returns None if unavailable (optional)."""
    app_st = _get_app_state(request)
    return getattr(app_st, "rag_pipeline", None)


# Provide the optional shared HTTP client dependency.
async def get_http(request: Request):
    """Get shared HTTP client from app state. Returns None if unavailable (optional)."""
    app_st = _get_app_state(request)
    return getattr(app_st, "http_client", None)


# ─────────────────────────────────────────────────────────────────────────
# ANSWER VERIFICATION
# ─────────────────────────────────────────────────────────────────────────

# Compare submitted answer with persisted answer key in question_bank.
async def _verify_answer(db: AsyncSession, question_id: str, selected: str) -> bool:
    """
    For MCQ levels (1-4): exact match against stored correct_answer.
    For free-text level 5: case-insensitive, strip whitespace.
    Both use the same comparison — level 5 is just more forgiving because
    the user typed it themselves.
    """
    from database.models import QuestionBank

    try:
        question_uuid = uuid.UUID(question_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid question_id format")

    try:
        stmt = select(QuestionBank.correct_answer).where(
            QuestionBank.id == question_uuid
        )
        result = await db.execute(stmt)
        row = result.scalar_one_or_none()
    except SQLAlchemyError as exc:
        logger.error("Challenge answer verification query failed: %s", exc)
        raise HTTPException(status_code=503, detail="Answer verification temporarily unavailable")

    if row is None:
        raise HTTPException(status_code=404, detail="Question not found")

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


# ═════════════════════════════════════════════════════════════════════════
# ENDPOINT 1 — GET /api/challenge/user/{user_id}/rank
# ═════════════════════════════════════════════════════════════════════════

@challenge_router.get("/user/{user_id}/rank", response_model=UserRankOut)
# Return current challenge rank, points, and unlocked levels for a user.
async def get_user_rank(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current=Depends(get_current_user),
):
    user, _ = current
    _ensure_user_match(user_id, str(user.id))
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
# Start a new challenge session at a rank-allowed initial level.
async def start_session(
    body: Annotated[StartSessionRequest, Body()],
    db: AsyncSession = Depends(get_db),
    current=Depends(get_current_user),
):
    user, _ = current
    _ensure_user_match(body.user_id, str(user.id))
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
# Return full challenge session state for the owning user.
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current=Depends(get_current_user),
):
    user, _ = current
    session = await get_challenge_session(db, session_id)
    if session is None:
        raise HTTPException(404, f"Session {session_id} not found")
    if str(session.user_id) != str(user.id):
        raise HTTPException(403, "You are not allowed to access this session")

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
# Move session level up/down within rank bounds.
async def change_level(
    session_id: str,
    body: Annotated[ChangeLevelRequest, Body()],
    db: AsyncSession = Depends(get_db),
    current=Depends(get_current_user),
):
    user, _ = current
    session = await get_challenge_session(db, session_id)
    if session is None:
        raise HTTPException(404, f"Session {session_id} not found")
    if str(session.user_id) != str(user.id):
        raise HTTPException(403, "You are not allowed to modify this session")
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
@limiter.limit("40/minute")
# Generate and persist one new challenge question for the active session.
async def generate_challenge_question(
    request: Request,
    body: Annotated[GenerateChallengeQuestionRequest, Body()],
    db          : AsyncSession = Depends(get_db),
    llm                        = Depends(get_llm),
    rag                        = Depends(get_rag),
    http_client                = Depends(get_http),
    current=Depends(get_current_user),
):
    user, _ = current
    _ensure_user_match(body.user_id, str(user.id))
    session = await get_challenge_session(db, body.session_id)
    if session is None:
        raise HTTPException(404, f"Session {body.session_id} not found")
    if str(session.user_id) != str(user.id):
        raise HTTPException(403, "You are not allowed to use this session")
    if session.is_completed:
        raise HTTPException(400, "Session is already completed")

    # SECURITY: Use session's current level, not client-provided level
    # This prevents users from skipping levels by modifying the request
    effective_level = session.current_level
    if body.level != effective_level:
        logger.warning(
            f"Level mismatch: client sent level={body.level} but session is at level={effective_level}. "
            f"Using session level. user={body.user_id[:8]}"
        )

    question_dict = None
    gov_decision = None
    context       = ""

    recent_question_texts = (
        await db.execute(
            select(QuestionBank.question_text)
            .join(ChallengeAnswer, ChallengeAnswer.question_id == QuestionBank.id)
            .where(ChallengeAnswer.session_id == session.id)
            .order_by(ChallengeAnswer.created_at.desc())
            .limit(40)
        )
    ).scalars().all()
    recent_signatures = {
        _challenge_signature(str(text))
        for text in recent_question_texts
        if str(text).strip()
    }

    recent_signatures.update(
        await _get_user_seen_challenge_signatures(
            db,
            user.id,
            body.topic,
        )
    )

    # ── Try RAG for context (levels 3-5 benefit most from real context) ──
    # RAG is optional — falls back to LLM-only if pipeline not available
    if effective_level >= 3 and rag is not None and http_client is not None:
        try:
            rag_result = await rag.run(
                topic         = body.topic,
                difficulty    = effective_level,
                user_accuracy = 0.5,
                llm_client    = llm,
                http_client   = http_client,
            )
            if rag_result:
                context = rag_result.get("text", "")
                logger.info(f"RAG provided context for level {effective_level}")
        except Exception as e:
            logger.warning(f"RAG context fetch failed (falling back to LLM): {e}")
    elif effective_level >= 3:
        logger.info(f"RAG pipeline not available, using LLM-only for level {effective_level}")

    # ── Generate with level-specific prompt and reject repeats ───────────
    for _ in range(4):
        candidate = await _generate_challenge_question_llm(
            llm=llm,
            topic=body.topic,
            level=effective_level,
            context=context,
        )

        if not candidate:
            if getattr(llm, "last_status_code", None) == 429:
                raise HTTPException(
                    status_code=429,
                    detail="LLM rate limit reached. Please retry in a few seconds.",
                    headers={"Retry-After": "3"},
                )
            continue

        signature = _challenge_signature(candidate.get("text", ""))
        if signature and signature in recent_signatures:
            logger.warning("Rejected repeated challenge prompt signature session=%s", str(session.id)[:8])
            continue

        # Additional DB-level duplicate safeguards: reject if any existing bank
        # row has identical or closely matching text/correct answer (case-insensitive).
        try:
            cand_text_norm = str(candidate.get("text", "")).strip().lower()
            cand_correct_norm = str(candidate.get("correctAnswer", "")).strip().lower()
            dup_stmt = (
                select(QuestionBank.id)
                .where(
                    or_(
                        func.lower(QuestionBank.question_text) == cand_text_norm,
                        func.lower(QuestionBank.correct_answer) == cand_correct_norm,
                        func.lower(QuestionBank.question_text).like(f"%{cand_text_norm}%"),
                    )
                )
                .limit(1)
            )
            dup_result = await db.execute(dup_stmt)
            if dup_result.scalar_one_or_none():
                logger.warning("Rejected candidate because DB contains similar question (dedupe)")
                continue
        except Exception:
            # If dedupe check fails for any reason, don't block generation.
            pass

        # Governance: reject blocked/low-quality candidates before persisting.
        try:
            from services.governance_service import GovernanceService

            decision = await GovernanceService.evaluate_candidate(
                db,
                question_id=candidate.get("id"),
                room="challenge",
                action="persist",
                topic=body.topic,
                question_text=str(candidate.get("text", "")),
                correct_answer=str(candidate.get("correctAnswer", "")),
                explanation=str(candidate.get("explanation", "")),
                options=list(candidate.get("options") or []),
            )
            if decision is not None and not decision.approved:
                logger.warning(
                    "Challenge governance rejected candidate",
                    session=str(session.id)[:8],
                    reasons=list(decision.reasons or []),
                )
                continue
        except Exception as exc:
            # Governance must never break challenge generation.
            logger.warning("Challenge governance evaluation failed: %s", exc)
            decision = None

        question_dict = candidate
        gov_decision = decision
        if signature:
            recent_signatures.add(signature)
        break

    if not question_dict:
        # Fallback: try to serve an existing bank question the user hasn't seen.
        try:
            seen_ids = await ClassicService.get_user_seen_question_ids(db=db, user_id=user.id, topic="mix")
            stmt = select(QuestionBank).where(QuestionBank.source != "challenge_llm")
            if seen_ids:
                stmt = stmt.where(QuestionBank.id.notin_(list(seen_ids)))
            stmt = stmt.order_by(func.random()).limit(1)
            row = (await db.execute(stmt)).scalars().first()
            if row:
                question_dict = {
                    "id": str(row.id),
                    "text": row.question_text,
                    "options": json.loads(row.options_json or "[]"),
                    "correctAnswer": row.correct_answer,
                    "explanation": row.explanation or "",
                    "is_free_text": False,
                }
                gov_decision = None
        except Exception:
            question_dict = None

    if not question_dict:
        raise HTTPException(503, "Could not generate a fresh challenge question. Please retry.")

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
            difficulty     = effective_level,
            source         = "challenge_llm",
        )

        # Persist governance signals onto the bank row (best-effort).
        if gov_decision is not None:
            try:
                from services.governance_service import GovernanceService

                stored_row = await db.get(QuestionBank, uuid.UUID(str(question_dict["id"])))
                if stored_row is not None:
                    await GovernanceService.apply_decision_to_persisted_row(
                        db,
                        row=stored_row,
                        decision=gov_decision,
                    )
                    await db.commit()
            except Exception as exc:
                await db.rollback()
                logger.warning("Challenge governance persistence hook failed: %s", exc)
    except Exception as e:
        # Log full traceback for diagnostics and enqueue a background retry to persist.
        logger.exception("CRITICAL: Could not store challenge question; scheduling background retry")
        try:
            import asyncio

            async def _retry_store(qdict, attempts=3):
                for i in range(attempts):
                    try:
                        async with db.begin():
                            await classic_crud.store_question(
                                db,
                                question_id    = qdict["id"],
                                question_text  = qdict["text"],
                                correct_answer = qdict["correctAnswer"],
                                options        = qdict["options"],
                                explanation    = qdict.get("explanation", ""),
                                topic          = body.topic,
                                difficulty     = effective_level,
                                source         = "challenge_llm",
                            )
                        logger.info("Background persist succeeded for challenge question=%s", qdict.get("id"))
                        return
                    except Exception:
                        logger.exception("Background persist attempt failed for question=%s", qdict.get("id"))
                        await asyncio.sleep(2 * (i + 1))

            # Fire-and-forget background retry
            asyncio.create_task(_retry_store(question_dict, attempts=3))
        except Exception:
            logger.exception("Failed to schedule background retry for question persist")

    if not await _remember_issued_question(request, body.session_id, question_dict["id"]):
        logger.error(
            "Failed to track issued challenge question: session=%s question=%s",
            str(body.session_id)[:8],
            str(question_dict.get("id", ""))[:8],
        )
        raise HTTPException(500, "Failed to track issued challenge question")

    correct_pts, _ = CHALLENGE_POINTS_TABLE[effective_level]

    # SECURITY: Do NOT return correctAnswer — answer is verified server-side
    return ChallengeQuestionOut(
        id            = question_dict["id"],
        text          = question_dict["text"],
        options       = question_dict["options"],
        # Anti-cheat: explanation is revealed only after answer submission.
        explanation   = "",
        level         = effective_level,
        points_value  = correct_pts,
        is_free_text  = question_dict.get("is_free_text", False),
    )


# ═════════════════════════════════════════════════════════════════════════
# ENDPOINT 6 — POST /api/challenge/submit-answer
# ═════════════════════════════════════════════════════════════════════════

@challenge_router.post("/submit-answer", response_model=SubmitChallengeAnswerOut)
@limiter.limit("80/minute")
# Verify one answer submission and apply points/streak/level updates.
async def submit_challenge_answer(
    request: Request,
    body: Annotated[SubmitChallengeAnswerRequest, Body()],
    db: AsyncSession = Depends(get_db),
    current=Depends(get_current_user),
):
    user, _ = current
    _ensure_user_match(body.user_id, str(user.id))
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
    if str(session.user_id) != str(user.id):
        raise HTTPException(403, "You are not allowed to submit for this session")
    if session.is_completed:
        raise HTTPException(400, "Session already completed")

    if not await _session_has_issued_question(request, body.session_id, body.question_id):
        # If the issued-question tracker missed this ID (dev fallback), allow submit
        # when the question exists in the DB and then remember it for the session.
        try:
            q_uuid = uuid.UUID(str(body.question_id))
            q_row = await db.get(QuestionBank, q_uuid)
            if q_row is not None:
                logger.info(
                    "Issued-question tracker miss recovered from DB: session=%s question=%s",
                    str(body.session_id)[:8],
                    str(body.question_id)[:8],
                )
                await _remember_issued_question(request, body.session_id, body.question_id)
            else:
                logger.warning(
                    "Rejected challenge answer for unissued question: user=%s session=%s question=%s",
                    str(body.user_id)[:8],
                    str(body.session_id)[:8],
                    str(body.question_id)[:8],
                )
                raise HTTPException(409, "Question was not issued for this session")
        except Exception as exc:
            logger.warning(
                "Rejected challenge answer for unissued question (lookup failed): %s",
                exc,
            )
            raise HTTPException(409, "Question was not issued for this session")

    # Verify question exists in database
    from database.models import QuestionBank
    try:
        question_uuid = uuid.UUID(body.question_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid question_id format")

    question_check = await db.execute(
        select(QuestionBank).where(QuestionBank.id == question_uuid)
    )
    question_row = question_check.scalar_one_or_none()
    if question_row is None:
        raise HTTPException(
            status_code=400,
            detail="Question not found in database. Was it properly generated?"
        )

    # Cache question fields as plain values.
    # IMPORTANT: IntegrityError handling triggers db.rollback(), which expires ORM
    # attributes. Accessing expired ORM attributes in async context can raise
    # MissingGreenlet. Use cached scalar values in all return paths.
    question_correct_answer = str(question_row.correct_answer)
    question_explanation = (
        question_row.explanation
        or "Use elimination and topic context to identify the strongest answer."
    )

    # Anti-abuse: replay duplicate submits idempotently instead of returning 409.
    if await has_answered_question(db, body.session_id, body.question_id):
        logger.warning(
            "Duplicate challenge answer replayed idempotently: user=%s session=%s question=%s",
            str(body.user_id)[:8],
            str(body.session_id)[:8],
            str(body.question_id)[:8],
        )
        existing_answer = await db.execute(
            select(ChallengeAnswer).where(
                ChallengeAnswer.session_id == uuid.UUID(str(body.session_id)),
                ChallengeAnswer.question_id == uuid.UUID(str(body.question_id)),
            )
        )
        answer_row = existing_answer.scalar_one_or_none()
        if answer_row is not None:
            return SubmitChallengeAnswerOut(
                id                 = str(answer_row.id),
                is_correct         = answer_row.is_correct,
                correct_answer     = question_correct_answer,
                explanation        = question_explanation,
                points_change      = answer_row.points_change,
                new_rank_points    = session.rank_points,
                new_level          = session.current_level,
                streak_correct     = session.streak_correct,
                streak_wrong       = session.streak_wrong,
                force_level_change = None,
            )

    # Verify answer server-side
    is_correct    = await _verify_answer(db, body.question_id, body.answer)
    logger.info(
        f"ANSWER VERIFICATION: user={body.user_id[:8]} question={body.question_id[:8]} "
        f"submitted='{body.answer}' correct_stored='{question_correct_answer}' "
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
    # Cache session snapshot for safe use after rollback in race-handling.
    session_rank_points = session.rank_points
    session_current_level = session.current_level
    session_streak_correct = session.streak_correct
    session_streak_wrong = session.streak_wrong

    stored_answer = None
    try:
        stored_answer = await record_challenge_answer(
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
        logger.warning(
            "IntegrityError on challenge answer insert; replaying stored answer if available session=%s question=%s",
            str(body.session_id)[:8],
            str(body.question_id)[:8],
        )

        # Prefer fresh session state from DB (the concurrent request may have
        # already updated the session aggregates).
        fresh_rank_points = session_rank_points
        fresh_level = session_current_level
        fresh_streak_correct = session_streak_correct
        fresh_streak_wrong = session_streak_wrong
        try:
            sid_uuid = uuid.UUID(str(body.session_id))
            sess_state = await db.execute(
                select(
                    ChallengeSession.rank_points,
                    ChallengeSession.current_level,
                    ChallengeSession.streak_correct,
                    ChallengeSession.streak_wrong,
                ).where(ChallengeSession.id == sid_uuid)
            )
            row = sess_state.first()
            if row is not None:
                fresh_rank_points, fresh_level, fresh_streak_correct, fresh_streak_wrong = row
        except Exception:
            pass

        existing_answer = await db.execute(
            select(ChallengeAnswer).where(
                ChallengeAnswer.session_id == uuid.UUID(str(body.session_id)),
                ChallengeAnswer.question_id == uuid.UUID(str(body.question_id)),
            )
        )
        answer_row = existing_answer.scalar_one_or_none()
        if answer_row is not None:
            return SubmitChallengeAnswerOut(
                id                 = str(answer_row.id),
                is_correct         = answer_row.is_correct,
                correct_answer     = question_correct_answer,
                explanation        = question_explanation,
                points_change      = answer_row.points_change,
                new_rank_points    = int(fresh_rank_points or 0),
                new_level          = int(fresh_level or session_current_level),
                streak_correct     = int(fresh_streak_correct or 0),
                streak_wrong       = int(fresh_streak_wrong or 0),
                force_level_change = None,
            )
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
        id                 = str(stored_answer.id) if stored_answer is not None else None,
        is_correct         = is_correct,
        correct_answer     = question_correct_answer,
        explanation        = question_explanation,
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
# Finalize a session and update global ranking progression.
async def end_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current=Depends(get_current_user),
):
    user, _ = current
    session = await get_challenge_session(db, session_id)
    if session is None:
        raise HTTPException(404, f"Session {session_id} not found")
    if str(session.user_id) != str(user.id):
        raise HTTPException(403, "You are not allowed to end this session")

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