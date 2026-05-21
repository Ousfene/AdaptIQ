"""
routers/challenge.py — Challenge Room competitive quiz endpoints.

Provides ranked competitive play with:
- 5 ranks (Bronze → Diamond) with increasing difficulty
- Timer-based play at higher ranks
- Skip-ahead mechanics to challenge higher ranks
- Anti-farming (can only play current rank or +1 for skip)
"""
import uuid
import logging
import random
import json
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, update as sqlalchemy_update, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address

from auth.core.dependencies import get_current_user
from database.models import (
    User, ChallengeRank, UserChallengeRank, ChallengeMatch,
    QuestionBank, QuestionConcept, ClassicSession, UserResponse,
    ChallengeSession, ChallengeAnswer
)
from database.irt import target_beta_range, beta_to_difficulty
from database import crud as classic_crud
from dependencies import get_db, get_redis
from schemas import (
    # V1 endpoints
    ChallengeStatusResponse,
    ChallengeStartRequest,
    ChallengeStartResponse,
    ChallengeAnswerRequest,
    ChallengeAnswerResponse,
    ChallengeEndResponse,
    ChallengeRankOut,
    ClassicQuestionOut,
    QuestionReviewItem,
    # V2 endpoints
    ChallengeStatusResponseV2,
    ChallengeStartRequestV2,
    ChallengeStartResponseV2,
    ChallengeAnswerResponseV2,
    ChallengeEndResponseV2,
    LevelChangeInfo,
    # MHD-style endpoints
    ChallengeGenerateQuestionRequest,
    ChallengeQuestionOut,
    ChallengeSubmitAnswerRequest,
    ChallengeSubmitAnswerResponse,
    ChallengeSessionOut,
    ChallengeEndSessionResponse,
    ForceLevelChange,
)
from services.session import SessionService
from services.challenge_service import (
    get_or_create_user_challenge_rank,
    get_available_levels,
    get_starting_level,
    is_level_allowed,
    calculate_points,
    check_streak_trigger,
    apply_level_change,
    update_streaks_after_answer,
    get_rank_name_from_id,
    create_challenge_session,
    get_session_by_match_id,
    record_challenge_answer,
    update_session_after_answer,
    finalize_session,
    update_global_ranking,
    has_answered_question,
    get_session_answered_ids,
    CHALLENGE_POINTS_TABLE,
)
from services.challenge_llm import generate_challenge_question_with_fallback


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rooms/challenge", tags=["challenge-room"])

# Rate limiter for challenge endpoints
limiter = Limiter(key_func=get_remote_address, config_filename="__slowapi_no_env__")

# Constants
MIN_CLASSIC_GAMES_FOR_CHALLENGE = 5
QUESTIONS_PER_MATCH = 10
WIN_THRESHOLD = 0.70  # 70% correct to win
SKIP_COOLDOWN_HOURS = 24


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_session_service(redis=Depends(get_redis)) -> SessionService:
    return SessionService(redis=redis)


async def get_user_classic_games_count(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Count how many classic questions the user has answered."""
    stmt = select(func.count(UserResponse.id)).where(UserResponse.user_id == user_id)
    result = await db.execute(stmt)
    return result.scalar() or 0


# NOTE: get_or_create_user_challenge_rank imported from services.challenge_service
# V1 endpoints use it directly now (removed duplicate local function)


async def select_challenge_question(
    db: AsyncSession,
    rank: ChallengeRank,
    asked_question_ids: list[uuid.UUID],
    _recursion_depth: int = 0,
) -> dict | None:
    """Select a question appropriate for the challenge rank."""
    # Prevent infinite recursion
    MAX_RECURSION = 10
    if _recursion_depth >= MAX_RECURSION:
        logger.warning(f"Max recursion depth reached in select_challenge_question")
        return None
    
    # Determine target difficulty based on rank
    rank_beta_map = {
        1: (-2.0, -1.0),  # Bronze: easy
        2: (-1.0, 0.5),   # Silver: medium-easy
        3: (0.0, 1.0),    # Gold: medium
        4: (0.5, 1.5),    # Platinum: medium-hard
        5: (1.0, 2.5),    # Diamond: hard
    }
    beta_low, beta_high = rank_beta_map.get(rank.id, (0.0, 1.0))
    
    # Query questions in range
    filters = [
        QuestionBank.difficulty_irt >= beta_low,
        QuestionBank.difficulty_irt <= beta_high,
    ]
    if asked_question_ids:
        filters.append(QuestionBank.id.notin_(asked_question_ids))
    
    stmt = select(QuestionBank).where(and_(*filters)).order_by(func.random()).limit(1)
    
    result = await db.execute(stmt)
    question = result.scalar_one_or_none()
    
    # Fallback to any question if none in range
    if not question:
        fallback_filters = []
        if asked_question_ids:
            fallback_filters.append(QuestionBank.id.notin_(asked_question_ids))
        stmt = select(QuestionBank)
        if fallback_filters:
            stmt = stmt.where(and_(*fallback_filters))
        stmt = stmt.order_by(func.random()).limit(1)
        result = await db.execute(stmt)
        question = result.scalar_one_or_none()
    
    if not question:
        return None

    # Validate question quality before serving
    MIN_QUESTION_LENGTH = 10
    if not question.question_text or len(question.question_text.strip()) < MIN_QUESTION_LENGTH:
        logger.warning(f"Skipping garbage question {question.id}: text too short")
        # Recursively try another question (add this ID to excluded list)
        return await select_challenge_question(db, rank, asked_question_ids + [question.id], _recursion_depth + 1)

    # Parse options and shuffle
    try:
        options = json.loads(question.options_json)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to parse options for question {question.id} in challenge: {e}")
        return await select_challenge_question(db, rank, asked_question_ids + [question.id], _recursion_depth + 1)
    
    # Validate options
    if len(options) < 2:
        logger.warning(f"Skipping question {question.id}: insufficient options ({len(options)})")
        return await select_challenge_question(db, rank, asked_question_ids + [question.id], _recursion_depth + 1)

    correct_answer = question.correct_answer
    
    # For Bronze rank (n_options=2), reduce to 2 options
    if rank.n_options == 2:
        # Keep correct answer and one random wrong answer
        wrong_options = [o for o in options if o != correct_answer]
        if wrong_options:
            selected_wrong = random.choice(wrong_options)
            options = [correct_answer, selected_wrong]
            random.shuffle(options)
    else:
        random.shuffle(options)
    
    correct_index = options.index(correct_answer)
    
    # Update times_seen
    await db.execute(
        sqlalchemy_update(QuestionBank)
        .where(QuestionBank.id == question.id)
        .values(times_seen=QuestionBank.times_seen + 1, last_served_at=utc_now())
    )
    
    return {
        "id": str(question.id),
        "text": question.question_text,
        "options": options,
        "correct_index": correct_index,
        "topic": question.topic,
        "difficulty": beta_to_difficulty(question.difficulty_irt),
    }


@router.get("/status", response_model=ChallengeStatusResponse)
async def get_challenge_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get user's challenge room status.
    
    Returns current rank, skip availability, and stats.
    """
    user_rank = await get_or_create_user_challenge_rank(db, current_user.id)
    
    # Get rank details
    rank_stmt = select(ChallengeRank).where(ChallengeRank.id == user_rank.current_rank_id)
    rank_result = await db.execute(rank_stmt)
    rank = rank_result.scalar_one_or_none()
    
    if not rank:
        raise HTTPException(status_code=404, detail="Rank not found")
    
    # Check skip availability
    can_skip = user_rank.skip_attempts_remaining > 0
    if user_rank.last_skip_at:
        cooldown_end = user_rank.last_skip_at + timedelta(hours=SKIP_COOLDOWN_HOURS)
        if utc_now() < cooldown_end:
            can_skip = False
    
    # Get classic games count
    classic_games = await get_user_classic_games_count(db, current_user.id)
    
    await db.commit()
    
    return ChallengeStatusResponse(
        current_rank=ChallengeRankOut(
            id=rank.id,
            name=rank.name,
            n_options=rank.n_options,
            has_timer=rank.has_timer,
            timer_seconds=rank.timer_seconds,
        ),
        can_skip_up=can_skip and user_rank.current_rank_id < 5,  # Can't skip beyond Diamond
        skip_attempts_remaining=user_rank.skip_attempts_remaining,
        wins=user_rank.wins,
        losses=user_rank.losses,
        classic_games_played=classic_games,
    )


@limiter.limit("15/minute")
@router.post("/start", response_model=ChallengeStartResponse)
async def start_challenge_match(
    request: Request,
    body: ChallengeStartRequest,
    db: AsyncSession = Depends(get_db),
    session_service: SessionService = Depends(get_session_service),
    current_user: User = Depends(get_current_user),
):
    """
    Start a new challenge match.
    
    Validates rank eligibility and creates match record.
    """
    # Check classic games prerequisite
    classic_games = await get_user_classic_games_count(db, current_user.id)
    if classic_games < MIN_CLASSIC_GAMES_FOR_CHALLENGE:
        raise HTTPException(
            status_code=403,
            detail=f"Must complete at least {MIN_CLASSIC_GAMES_FOR_CHALLENGE} classic questions first"
        )
    
    user_rank = await get_or_create_user_challenge_rank(db, current_user.id)
    
    # Validate rank selection
    if body.rank_id < user_rank.current_rank_id:
        # Anti-farming: can't play below current rank
        logger.warning("anti_farming_blocked", extra={
            "user_id": str(current_user.id),
            "current_rank": user_rank.current_rank_id,
            "requested_rank": body.rank_id,
        })
        raise HTTPException(status_code=403, detail="Cannot play below your current rank")
    
    if body.rank_id > user_rank.current_rank_id + 1:
        raise HTTPException(status_code=403, detail="Can only play current rank or one above")
    
    if body.rank_id > user_rank.current_rank_id:
        # Skip attempt
        if not body.is_skip_attempt:
            raise HTTPException(status_code=400, detail="Must mark as skip attempt to play above current rank")
        
        if user_rank.skip_attempts_remaining <= 0:
            raise HTTPException(status_code=403, detail="No skip attempts remaining")
        
        # Check cooldown
        if user_rank.last_skip_at:
            cooldown_end = user_rank.last_skip_at + timedelta(hours=SKIP_COOLDOWN_HOURS)
            if utc_now() < cooldown_end:
                raise HTTPException(
                    status_code=403,
                    detail=f"Skip attempt on cooldown. Available after {cooldown_end.isoformat()}"
                )
    
    # Get rank details
    rank_stmt = select(ChallengeRank).where(ChallengeRank.id == body.rank_id)
    rank_result = await db.execute(rank_stmt)
    rank = rank_result.scalar_one_or_none()
    
    if not rank:
        raise HTTPException(status_code=404, detail="Rank not found")
    
    # Create match record
    match = ChallengeMatch(
        id=uuid.uuid4(),
        user_id=current_user.id,
        rank_id=body.rank_id,
        questions_answered=0,
        score=0.0,
        time_taken=0,
        created_at=utc_now(),
        result="incomplete",
        is_skip_attempt=body.is_skip_attempt,
    )
    db.add(match)
    await db.flush()
    
    # Select first question
    first_question = await select_challenge_question(db, rank, [])
    
    if not first_question:
        raise HTTPException(status_code=503, detail="No questions available")
    
    # Get explanation for first question (for review at end)
    first_q_stmt = select(QuestionBank).where(QuestionBank.id == uuid.UUID(first_question["id"]))
    first_q_result = await db.execute(first_q_stmt)
    first_q_db = first_q_result.scalar_one_or_none()

    if first_q_db is None:
        logger.warning(f"Question {first_question['id']} not found in database")
        first_explanation = "No explanation available"
    else:
        first_explanation = first_q_db.explanation or "No explanation available"
    
    # Store match state in Redis (including answered_questions for review)
    match_state = {
        "user_id": str(current_user.id),
        "rank_id": body.rank_id,
        "is_skip_attempt": body.is_skip_attempt,
        "questions_asked": [first_question["id"]],
        "current_question": first_question,
        "current_explanation": first_explanation,  # Store for answer response
        "correct_count": 0,
        "total_time": 0,
        "question_shown_at": utc_now().timestamp(),
        "answered_questions": [],  # NEW: Store all Q&A for end-of-match review
    }
    await session_service.store_session_state(f"challenge:{match.id}", match_state)
    
    logger.info("challenge_match_started", extra={
        "user_id": str(current_user.id),
        "match_id": str(match.id),
        "rank_id": body.rank_id,
        "is_skip": body.is_skip_attempt,
    })
    
    await db.commit()
    
    return ChallengeStartResponse(
        match_id=str(match.id),
        rank=ChallengeRankOut(
            id=rank.id,
            name=rank.name,
            n_options=rank.n_options,
            has_timer=rank.has_timer,
            timer_seconds=rank.timer_seconds,
        ),
        first_question=ClassicQuestionOut(
            id=first_question["id"],
            text=first_question["text"],
            options=first_question["options"],
            topic=first_question["topic"],
            difficulty=first_question["difficulty"],
        ),
    )


@limiter.limit("20/minute")
@router.post("/answer/{match_id}", response_model=ChallengeAnswerResponse)
async def answer_challenge_question(
    request: Request,
    match_id: str,
    body: ChallengeAnswerRequest,
    db: AsyncSession = Depends(get_db),
    session_service: SessionService = Depends(get_session_service),
    current_user: User = Depends(get_current_user),
):
    """
    Submit an answer to a challenge question.
    
    Checks timer violation and returns next question.
    """
    # Validate UUID format
    try:
        match_uuid = uuid.UUID(match_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid match ID format")
    
    # Get match from DB
    match_stmt = select(ChallengeMatch).where(ChallengeMatch.id == match_uuid)
    match_result = await db.execute(match_stmt)
    match = match_result.scalar_one_or_none()
    
    if not match or match.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Match not found")
    
    if match.result != "incomplete":
        raise HTTPException(status_code=400, detail="Match already ended")
    
    # Get match state from Redis
    match_state = await session_service.get_session_state(f"challenge:{match_id}")
    if not match_state:
        raise HTTPException(status_code=404, detail="Match state not found")
    
    # Get rank for timer check
    rank_stmt = select(ChallengeRank).where(ChallengeRank.id == match.rank_id)
    rank_result = await db.execute(rank_stmt)
    rank = rank_result.scalar_one_or_none()
    
    # Check timer violation
    current_question = match_state.get("current_question")
    if not current_question or current_question["id"] != body.question_id:
        raise HTTPException(status_code=400, detail="Question mismatch")

    # Get explanation for this question
    current_explanation = match_state.get("current_explanation", "")

    # ADDED: Calculate server-side time instead of trusting client
    question_shown_at = match_state.get("question_shown_at", utc_now().timestamp())
    now = utc_now().timestamp()
    time_taken_seconds = max(0, now - question_shown_at)

    # Timer violation = wrong answer
    time_violation = False
    if rank and rank.has_timer and rank.timer_seconds:
        if time_taken_seconds > rank.timer_seconds:  # SERVER-CALCULATED time (not client value)
            time_violation = True
    
    # Check answer
    correct = current_question["correct_index"] == body.selected_index
    if time_violation:
        correct = False
    
    # Store this Q&A for end-of-match review
    answered_questions = match_state.get("answered_questions", [])
    answered_questions.append({
        "question_text": current_question["text"],
        "options": current_question["options"],
        "user_answer_index": body.selected_index,
        "correct_answer_index": current_question["correct_index"],
        "was_correct": correct,
        "explanation": current_explanation,
    })
    match_state["answered_questions"] = answered_questions
    
    # Update state
    if correct:
        match_state["correct_count"] = match_state.get("correct_count", 0) + 1
    match_state["total_time"] = match_state.get("total_time", 0) + int(time_taken_seconds)
    # Update timestamp for next question
    match_state["question_shown_at"] = utc_now().timestamp()
    
    match.questions_answered += 1
    match.time_taken = match_state["total_time"]
    
    # Calculate score so far
    score_so_far = match_state["correct_count"] / match.questions_answered
    
    # Check if match should end
    questions_remaining = QUESTIONS_PER_MATCH - match.questions_answered
    
    if questions_remaining <= 0:
        # Match ends - keep state for end endpoint to retrieve review
        match.score = score_so_far
        match.result = "win" if score_so_far >= WIN_THRESHOLD else "loss"
        
        # DON'T delete state yet - end endpoint needs answered_questions
        await session_service.store_session_state(f"challenge:{match_id}", match_state)
        await db.commit()
        
        # Return with end signal (next_question=None)
        return ChallengeAnswerResponse(
            correct=correct,
            correct_index=current_question["correct_index"],
            explanation=current_explanation,
            score_so_far=score_so_far,
            questions_remaining=0,
            next_question=None,
        )
    
    # Select next question
    asked_ids = []
    for qid in match_state.get("questions_asked", []):
        if qid:
            try:
                asked_ids.append(uuid.UUID(qid))
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid UUID in questions_asked: {qid}, error: {e}")
                continue
    next_question = await select_challenge_question(db, rank, asked_ids)
    
    # Get explanation for next question
    next_explanation = ""
    if next_question:
        next_q_stmt = select(QuestionBank).where(QuestionBank.id == uuid.UUID(next_question["id"]))
        next_q_result = await db.execute(next_q_stmt)
        next_q_db = next_q_result.scalar_one_or_none()
        next_explanation = next_q_db.explanation if next_q_db else ""
        
        match_state["questions_asked"].append(next_question["id"])
        match_state["current_question"] = next_question
        match_state["current_explanation"] = next_explanation
    
    await session_service.store_session_state(f"challenge:{match_id}", match_state)
    await db.commit()
    
    return ChallengeAnswerResponse(
        correct=correct,
        correct_index=current_question["correct_index"],
        explanation=current_explanation,
        score_so_far=score_so_far,
        questions_remaining=questions_remaining,
        next_question=ClassicQuestionOut(
            id=next_question["id"],
            text=next_question["text"],
            options=next_question["options"],
            topic=next_question["topic"],
            difficulty=next_question["difficulty"],
        ) if next_question else None,
    )


@limiter.limit("15/minute")
@router.post("/end/{match_id}", response_model=ChallengeEndResponse)
async def end_challenge_match(
    request: Request,
    match_id: str,
    db: AsyncSession = Depends(get_db),
    session_service: SessionService = Depends(get_session_service),
    current_user: User = Depends(get_current_user),
):
    """
    End a challenge match (explicit or auto after 10 questions).
    
    Processes rank changes for skip attempts.
    """
    # Validate UUID format
    try:
        match_uuid = uuid.UUID(match_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid match ID format")
    
    # Get match from DB
    match_stmt = select(ChallengeMatch).where(ChallengeMatch.id == match_uuid)
    match_result = await db.execute(match_stmt)
    match = match_result.scalar_one_or_none()
    
    if not match or match.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Match not found")
    
    # Get match state
    match_state = await session_service.get_session_state(f"challenge:{match_id}")
    
    # Calculate final score if not already done
    if match.result == "incomplete":
        if match.questions_answered > 0:
            correct_count = match_state.get("correct_count", 0) if match_state else 0
            match.score = correct_count / match.questions_answered
        else:
            match.score = 0.0
        
        match.result = "win" if match.score >= WIN_THRESHOLD else "loss"
    
    # Get user rank record
    user_rank = await get_or_create_user_challenge_rank(db, current_user.id)
    
    # Process results
    rank_changed = False
    new_rank = None
    skip_result = None
    
    if match.result == "win":
        user_rank.wins += 1
        
        if match.is_skip_attempt:
            # Successful skip: promote to new rank
            user_rank.current_rank_id = match.rank_id
            user_rank.skip_attempts_remaining = 3  # Reset skip attempts
            rank_changed = True
            skip_result = "promoted"
            
            logger.info("rank_change", extra={
                "user_id": str(current_user.id),
                "from_rank": match.rank_id - 1,
                "to_rank": match.rank_id,
                "result": "skip_success",
            })
    else:
        user_rank.losses += 1
        
        if match.is_skip_attempt:
            # Failed skip: cooldown and decrement attempts
            user_rank.skip_attempts_remaining = max(0, user_rank.skip_attempts_remaining - 1)
            user_rank.last_skip_at = utc_now()
            skip_result = "failed"
            
            logger.info("skip_failed", extra={
                "user_id": str(current_user.id),
                "target_rank": match.rank_id,
                "attempts_remaining": user_rank.skip_attempts_remaining,
            })
    
    # Get new rank details if changed
    if rank_changed:
        new_rank_stmt = select(ChallengeRank).where(ChallengeRank.id == user_rank.current_rank_id)
        new_rank_result = await db.execute(new_rank_stmt)
        rank_obj = new_rank_result.scalar_one_or_none()
        if rank_obj:
            new_rank = ChallengeRankOut(
                id=rank_obj.id,
                name=rank_obj.name,
                n_options=rank_obj.n_options,
                has_timer=rank_obj.has_timer,
                timer_seconds=rank_obj.timer_seconds,
            )
    
    # Build questions review from match state
    questions_review = []
    answered_questions = match_state.get("answered_questions", []) if match_state else []
    for aq in answered_questions:
        questions_review.append(QuestionReviewItem(
            question_text=aq.get("question_text", ""),
            options=aq.get("options", []),
            user_answer_index=aq.get("user_answer_index", -1),
            correct_answer_index=aq.get("correct_answer_index", 0),
            was_correct=aq.get("was_correct", False),
            explanation=aq.get("explanation", ""),
        ))
    
    # Clean up Redis state
    await session_service.delete_session_state(f"challenge:{match_id}")
    
    await db.commit()
    
    return ChallengeEndResponse(
        result=match.result,
        score=match.score,
        rank_changed=rank_changed,
        new_rank=new_rank,
        skip_result=skip_result,
        questions_review=questions_review,
    )


# ════════════════════════════════════════════════════════════════════════════
# V2 ENDPOINTS — Dynamic Levels & Streaks (MHD merge)
# ════════════════════════════════════════════════════════════════════════════
# NOTE: Imports consolidated at top of file


@router.get("/v2/status", response_model=ChallengeStatusResponseV2)
async def get_challenge_status_v2(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get user's challenge room status (V2 with points & levels).
    
    Returns current rank, available levels, points progress, and stats.
    """
    user_rank = await get_or_create_user_challenge_rank(db, current_user.id)
    
    # Get rank details
    rank_stmt = select(ChallengeRank).where(ChallengeRank.id == user_rank.current_rank_id)
    rank_result = await db.execute(rank_stmt)
    rank = rank_result.scalar_one_or_none()
    
    if not rank:
        raise HTTPException(status_code=404, detail="Rank not found")
    
    # Get rank name for level access lookup
    rank_name = get_rank_name_from_id(user_rank.current_rank_id)
    
    # Check skip availability
    can_skip = user_rank.skip_attempts_remaining > 0
    if user_rank.last_skip_at:
        cooldown_end = user_rank.last_skip_at + timedelta(hours=SKIP_COOLDOWN_HOURS)
        if utc_now() < cooldown_end:
            can_skip = False
    
    # Get classic games count
    classic_games = await get_user_classic_games_count(db, current_user.id)
    
    await db.commit()
    
    return ChallengeStatusResponseV2(
        current_rank=ChallengeRankOut(
            id=rank.id,
            name=rank.name,
            n_options=rank.n_options,
            has_timer=rank.has_timer,
            timer_seconds=rank.timer_seconds,
        ),
        can_skip_up=can_skip and user_rank.current_rank_id < 5,
        skip_attempts_remaining=user_rank.skip_attempts_remaining,
        wins=user_rank.wins,
        losses=user_rank.losses,
        classic_games_played=classic_games,
        # V2 additions
        rank_points=user_rank.rank_points,
        highest_streak=user_rank.highest_streak,
        total_sessions=user_rank.total_sessions,
        available_levels=get_available_levels(rank_name),
    )


@limiter.limit("15/minute")
@router.post("/v2/start", response_model=ChallengeStartResponseV2)
async def start_challenge_match_v2(
    request: Request,
    body: ChallengeStartRequestV2,
    db: AsyncSession = Depends(get_db),
    session_service: SessionService = Depends(get_session_service),
    current_user: User = Depends(get_current_user),
):
    """
    Start a new challenge match (V2 with dynamic levels).
    
    Allows level selection within rank-allowed range.
    """
    # Check classic games prerequisite
    classic_games = await get_user_classic_games_count(db, current_user.id)
    if classic_games < MIN_CLASSIC_GAMES_FOR_CHALLENGE:
        raise HTTPException(
            status_code=403,
            detail=f"Must complete at least {MIN_CLASSIC_GAMES_FOR_CHALLENGE} classic questions first"
        )
    
    user_rank = await get_or_create_user_challenge_rank(db, current_user.id)
    rank_name = get_rank_name_from_id(user_rank.current_rank_id)
    
    # Validate starting level is allowed for this rank
    if not is_level_allowed(rank_name, body.starting_level):
        available = get_available_levels(rank_name)
        raise HTTPException(
            status_code=400,
            detail=f"Level {body.starting_level} not allowed at {rank_name} rank. Available: {available}"
        )
    
    # Get rank details
    rank_stmt = select(ChallengeRank).where(ChallengeRank.id == user_rank.current_rank_id)
    rank_result = await db.execute(rank_stmt)
    rank = rank_result.scalar_one_or_none()
    
    if not rank:
        raise HTTPException(status_code=404, detail="Rank not found")
    
    # Create match record (V1 compatible)
    match = ChallengeMatch(
        id=uuid.uuid4(),
        user_id=current_user.id,
        rank_id=user_rank.current_rank_id,
        questions_answered=0,
        score=0.0,
        time_taken=0,
        created_at=utc_now(),
        result="incomplete",
        is_skip_attempt=False,
    )
    db.add(match)
    await db.flush()
    
    # Create V2 session with streak tracking
    challenge_session = await create_challenge_session(
        db=db,
        user_id=current_user.id,
        match_id=match.id,
        topic=body.topic,
        starting_level=body.starting_level,
    )
    
    # Generate first question using level-specific LLM
    llm = getattr(request.app.state, "llm_client", None)
    first_question = None
    
    if llm:
        first_question = await generate_challenge_question_with_fallback(
            llm=llm,
            topic=body.topic,
            level=body.starting_level,
        )
    
    # Fallback to DB question if LLM fails
    if not first_question:
        first_question = await select_challenge_question(db, rank, [])
        if first_question:
            first_question["is_free_text"] = False
            first_question["level"] = body.starting_level
    
    if not first_question:
        raise HTTPException(status_code=503, detail="No questions available")
    
    # Get explanation
    first_explanation = first_question.get("explanation", "")
    if not first_explanation and "id" in first_question:
        try:
            first_q_stmt = select(QuestionBank).where(QuestionBank.id == uuid.UUID(first_question["id"]))
            first_q_result = await db.execute(first_q_stmt)
            first_q_db = first_q_result.scalar_one_or_none()
            first_explanation = first_q_db.explanation if first_q_db else ""
        except ValueError:
            pass
    
    # Store match state in Redis
    match_state = {
        "user_id": str(current_user.id),
        "session_id": str(challenge_session.id),
        "rank_id": user_rank.current_rank_id,
        "current_level": body.starting_level,
        "questions_asked": [first_question.get("id", str(uuid.uuid4()))],
        "current_question": first_question,
        "current_explanation": first_explanation,
        "correct_count": 0,
        "streak_correct": 0,
        "streak_wrong": 0,
        "rank_points": 0,
        "level_changes_count": 0,
        "total_time": 0,
        "question_shown_at": utc_now().timestamp(),
        "answered_questions": [],
    }
    await session_service.store_session_state(f"challenge:{match.id}", match_state)
    
    logger.info("challenge_v2_started", extra={
        "user_id": str(current_user.id),
        "match_id": str(match.id),
        "session_id": str(challenge_session.id),
        "rank": rank_name,
        "level": body.starting_level,
        "topic": body.topic,
    })
    
    await db.commit()
    
    return ChallengeStartResponseV2(
        match_id=str(match.id),
        session_id=str(challenge_session.id),
        current_level=body.starting_level,
        rank_points=0,
        available_levels=get_available_levels(rank_name),
        current_rank=ChallengeRankOut(
            id=rank.id,
            name=rank.name,
            n_options=rank.n_options,
            has_timer=rank.has_timer,
            timer_seconds=rank.timer_seconds,
        ),
        topic=body.topic,
        first_question=ClassicQuestionOut(
            id=first_question.get("id", str(uuid.uuid4())),
            text=first_question["text"],
            options=first_question.get("options", []),
            topic=body.topic,
            difficulty=first_question.get("level", body.starting_level),
        ),
    )


@limiter.limit("20/minute")
@router.post("/v2/answer/{match_id}", response_model=ChallengeAnswerResponseV2)
async def answer_challenge_question_v2(
    request: Request,
    match_id: str,
    body: ChallengeAnswerRequest,
    db: AsyncSession = Depends(get_db),
    session_service: SessionService = Depends(get_session_service),
    current_user: User = Depends(get_current_user),
):
    """
    Submit an answer (V2 with streaks and dynamic level changes).
    
    Processes streak triggers and adjusts level mid-session.
    """
    try:
        match_uuid = uuid.UUID(match_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid match ID format")
    
    # Get match from DB
    match_stmt = select(ChallengeMatch).where(ChallengeMatch.id == match_uuid)
    match_result = await db.execute(match_stmt)
    match = match_result.scalar_one_or_none()
    
    if not match or match.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Match not found")
    
    if match.result != "incomplete":
        raise HTTPException(status_code=400, detail="Match already ended")
    
    # Get match state from Redis
    match_state = await session_service.get_session_state(f"challenge:{match_id}")
    if not match_state:
        raise HTTPException(status_code=404, detail="Match state not found")
    
    # Get rank for timer check
    rank_stmt = select(ChallengeRank).where(ChallengeRank.id == match.rank_id)
    rank_result = await db.execute(rank_stmt)
    rank = rank_result.scalar_one_or_none()
    rank_name = get_rank_name_from_id(match.rank_id)
    
    current_question = match_state.get("current_question")
    if not current_question:
        raise HTTPException(status_code=400, detail="No current question")
    
    current_explanation = match_state.get("current_explanation", "")
    current_level = match_state.get("current_level", 1)
    
    # Server-side time calculation
    question_shown_at = match_state.get("question_shown_at", utc_now().timestamp())
    time_taken_seconds = max(0, utc_now().timestamp() - question_shown_at)
    
    # Timer violation check
    time_violation = False
    if rank and rank.has_timer and rank.timer_seconds:
        if time_taken_seconds > rank.timer_seconds:
            time_violation = True
    
    # Check answer correctness
    correct_index = current_question.get("correct_index")
    if correct_index is None:
        # If no correct_index, match by answer text
        correct_answer = current_question.get("correctAnswer", "")
        options = current_question.get("options", [])
        correct_index = options.index(correct_answer) if correct_answer in options else 0
    
    correct = body.selected_index == correct_index
    if time_violation:
        correct = False
    
    # Calculate points based on current level
    points_change = calculate_points(current_level, correct)
    
    # Update streaks
    old_streak_correct = match_state.get("streak_correct", 0)
    old_streak_wrong = match_state.get("streak_wrong", 0)
    new_streak_correct, new_streak_wrong = update_streaks_after_answer(
        old_streak_correct, old_streak_wrong, correct
    )
    
    # Check for streak-triggered level change
    level_change_info = None
    streak_trigger = check_streak_trigger(new_streak_correct, new_streak_wrong)
    new_level = current_level
    
    if streak_trigger:
        old_level = current_level
        new_level = apply_level_change(current_level, streak_trigger["direction"], rank_name)
        
        if new_level != old_level:
            match_state["level_changes_count"] = match_state.get("level_changes_count", 0) + 1
            level_change_info = LevelChangeInfo(
                direction=streak_trigger["direction"],
                reason=streak_trigger["reason"],
                old_level=old_level,
                new_level=new_level,
            )
            # MHD logic: Reset ONLY the streak that triggered the change
            if streak_trigger["direction"] == "up":
                new_streak_correct = 0
            else:
                new_streak_wrong = 0
            
            logger.info("level_changed", extra={
                "user_id": str(current_user.id),
                "match_id": match_id,
                "direction": streak_trigger["direction"],
                "old_level": old_level,
                "new_level": new_level,
            })
    
    # Update state
    match_state["current_level"] = new_level
    match_state["streak_correct"] = new_streak_correct
    match_state["streak_wrong"] = new_streak_wrong
    match_state["rank_points"] = match_state.get("rank_points", 0) + points_change
    match_state["total_time"] = match_state.get("total_time", 0) + int(time_taken_seconds)
    match_state["question_shown_at"] = utc_now().timestamp()
    
    if correct:
        match_state["correct_count"] = match_state.get("correct_count", 0) + 1
    
    # Track highest streak
    if new_streak_correct > match_state.get("highest_streak", 0):
        match_state["highest_streak"] = new_streak_correct
    
    # Record answer for review
    answered_questions = match_state.get("answered_questions", [])
    answered_questions.append({
        "question_text": current_question.get("text", ""),
        "options": current_question.get("options", []),
        "user_answer_index": body.selected_index,
        "correct_answer_index": correct_index,
        "was_correct": correct,
        "explanation": current_explanation,
        "level": current_level,
        "points": points_change,
    })
    match_state["answered_questions"] = answered_questions
    
    # Update DB records
    match.questions_answered += 1
    match.time_taken = match_state["total_time"]
    
    # Update challenge session in DB
    session_id = match_state.get("session_id")
    if session_id:
        session_stmt = select(ChallengeSession).where(ChallengeSession.id == uuid.UUID(session_id))
        session_result = await db.execute(session_stmt)
        challenge_session = session_result.scalar_one_or_none()
        
        if challenge_session:
            await update_session_after_answer(
                db=db,
                session=challenge_session,
                is_correct=correct,
                points_change=points_change,
                new_streak_correct=new_streak_correct,
                new_streak_wrong=new_streak_wrong,
                new_level=new_level,
            )
    
    # Check if match should end
    questions_remaining = QUESTIONS_PER_MATCH - match.questions_answered
    match_ended = questions_remaining <= 0

    next_question = None
    if match_ended:
        # Guard against division by zero if somehow no questions were answered
        if match.questions_answered > 0:
            match.score = match_state.get("correct_count", 0) / match.questions_answered
            match.result = "win" if match.score >= WIN_THRESHOLD else "loss"
        else:
            logger.warning(f"Match {match.id} ended with 0 questions answered")
            match.score = 0.0
            match.result = "loss"
    else:
        # Generate next question at new level
        llm = getattr(request.app.state, "llm_client", None)
        
        if llm:
            next_question = await generate_challenge_question_with_fallback(
                llm=llm,
                topic=match_state.get("topic", "Mixed"),
                level=new_level,
            )
        
        # Fallback to DB question
        if not next_question:
            asked_ids = []
            for qid in match_state.get("questions_asked", []):
                if qid:
                    try:
                        asked_ids.append(uuid.UUID(qid))
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Invalid UUID in questions_asked: {qid}, error: {e}")
                        continue
            next_question = await select_challenge_question(db, rank, asked_ids)
            if next_question:
                next_question["is_free_text"] = False
                next_question["level"] = new_level
        
        if next_question:
            next_explanation = next_question.get("explanation", "")
            if not next_explanation and "id" in next_question:
                try:
                    next_q_stmt = select(QuestionBank).where(QuestionBank.id == uuid.UUID(next_question["id"]))
                    next_q_result = await db.execute(next_q_stmt)
                    next_q_db = next_q_result.scalar_one_or_none()
                    next_explanation = next_q_db.explanation if next_q_db else ""
                except ValueError:
                    pass
            
            match_state["questions_asked"].append(next_question.get("id", str(uuid.uuid4())))
            match_state["current_question"] = next_question
            match_state["current_explanation"] = next_explanation
    
    await session_service.store_session_state(f"challenge:{match_id}", match_state)
    await db.commit()
    
    return ChallengeAnswerResponseV2(
        correct=correct,
        correct_index=correct_index,
        explanation=current_explanation,
        points_change=points_change,
        new_rank_points=match_state.get("rank_points", 0),
        new_level=new_level,
        streak_correct=new_streak_correct,
        streak_wrong=new_streak_wrong,
        level_change=level_change_info,
        questions_remaining=questions_remaining,
        match_ended=match_ended,
        next_question=ClassicQuestionOut(
            id=next_question.get("id", str(uuid.uuid4())),
            text=next_question.get("text", ""),
            options=next_question.get("options", []),
            topic=next_question.get("topic", "Mixed"),
            difficulty=next_question.get("level", new_level),
        ) if next_question else None,
    )


@limiter.limit("15/minute")
@router.post("/v2/end/{match_id}", response_model=ChallengeEndResponseV2)
async def end_challenge_match_v2(
    request: Request,
    match_id: str,
    db: AsyncSession = Depends(get_db),
    session_service: SessionService = Depends(get_session_service),
    current_user: User = Depends(get_current_user),
):
    """
    End a challenge match (V2 with detailed stats).
    
    Updates global ranking with session points and streak records.
    """
    try:
        match_uuid = uuid.UUID(match_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid match ID format")
    
    # Get match from DB
    match_stmt = select(ChallengeMatch).where(ChallengeMatch.id == match_uuid)
    match_result = await db.execute(match_stmt)
    match = match_result.scalar_one_or_none()
    
    if not match or match.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Match not found")
    
    # Get match state
    match_state = await session_service.get_session_state(f"challenge:{match_id}")
    
    # Calculate final score if not already done
    if match.result == "incomplete":
        if match.questions_answered > 0:
            correct_count = match_state.get("correct_count", 0) if match_state else 0
            match.score = correct_count / match.questions_answered
        else:
            match.score = 0.0
        match.result = "win" if match.score >= WIN_THRESHOLD else "loss"
    
    # Finalize challenge session
    session_id = match_state.get("session_id") if match_state else None
    session_points = match_state.get("rank_points", 0) if match_state else 0
    session_streak = match_state.get("highest_streak", 0) if match_state else 0
    level_changes = match_state.get("level_changes_count", 0) if match_state else 0
    
    if session_id:
        session_stmt = select(ChallengeSession).where(ChallengeSession.id == uuid.UUID(session_id))
        session_result = await db.execute(session_stmt)
        challenge_session = session_result.scalar_one_or_none()
        if challenge_session:
            await finalize_session(db, challenge_session)
    
    # Update global ranking
    won = match.result == "win"
    user_rank, rank_changed = await update_global_ranking(
        db=db,
        user_id=current_user.id,
        session_points=session_points,
        session_streak=session_streak,
        won=won,
    )
    
    # Get new rank details if changed
    new_rank = None
    skip_result = None
    
    if rank_changed:
        new_rank_stmt = select(ChallengeRank).where(ChallengeRank.id == user_rank.current_rank_id)
        new_rank_result = await db.execute(new_rank_stmt)
        rank_obj = new_rank_result.scalar_one_or_none()
        if rank_obj:
            new_rank = ChallengeRankOut(
                id=rank_obj.id,
                name=rank_obj.name,
                n_options=rank_obj.n_options,
                has_timer=rank_obj.has_timer,
                timer_seconds=rank_obj.timer_seconds,
            )
    
    # Handle skip attempt results (V1 compatibility)
    if match.is_skip_attempt:
        skip_result = "promoted" if won else "failed"
    
    # Build questions review
    questions_review = []
    answered_questions = match_state.get("answered_questions", []) if match_state else []
    for aq in answered_questions:
        questions_review.append(QuestionReviewItem(
            question_text=aq.get("question_text", ""),
            options=aq.get("options", []),
            user_answer_index=aq.get("user_answer_index", -1),
            correct_answer_index=aq.get("correct_answer_index", 0),
            was_correct=aq.get("was_correct", False),
            explanation=aq.get("explanation", ""),
        ))
    
    # Clean up Redis state
    await session_service.delete_session_state(f"challenge:{match_id}")
    
    logger.info("challenge_v2_ended", extra={
        "user_id": str(current_user.id),
        "match_id": match_id,
        "result": match.result,
        "score": match.score,
        "session_points": session_points,
        "total_rank_points": user_rank.rank_points,
        "highest_streak": session_streak,
        "level_changes": level_changes,
        "rank_changed": rank_changed,
    })
    
    await db.commit()
    
    return ChallengeEndResponseV2(
        result=match.result,
        score=match.score,
        rank_changed=rank_changed,
        new_rank=new_rank,
        skip_result=skip_result,
        questions_review=questions_review,
        session_points=session_points,
        total_rank_points=user_rank.rank_points,
        highest_streak=session_streak,
        level_changes_count=level_changes,
    )


# ════════════════════════════════════════════════════════════════════════════
# MHD-STYLE ENDPOINTS — Separate question generation + answer by string
# ════════════════════════════════════════════════════════════════════════════
# NOTE: Imports consolidated at top of file


async def _verify_answer_server_side(
    db: AsyncSession,
    question_id: str,
    selected_answer: str,
) -> bool:
    """
    Verify answer server-side by comparing with stored correct_answer.
    MHD-style: case-insensitive, strip whitespace.
    """
    try:
        stmt = select(QuestionBank.correct_answer).where(
            QuestionBank.id == uuid.UUID(question_id)
        )
        result = await db.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            logger.error(f"Question {question_id} not found in database!")
            return False
        
        # Normalize both for comparison
        selected_clean = str(selected_answer).strip().lower()
        correct_clean = str(row).strip().lower()
        
        is_match = selected_clean == correct_clean
        
        logger.debug(
            f"Answer verification: selected='{selected_answer}' correct='{row}' match={is_match}"
        )
        
        return is_match
    except Exception as e:
        logger.error(f"Exception during answer verification: {e}")
        return False


@router.get("/v2/session/{session_id}", response_model=ChallengeSessionOut)
async def get_challenge_session_state(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get current session state (MHD-style).
    """
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session ID format")
    
    session_stmt = select(ChallengeSession).where(ChallengeSession.id == session_uuid)
    session_result = await db.execute(session_stmt)
    session = session_result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your session")
    
    return ChallengeSessionOut(
        session_id=str(session.id),
        user_id=str(session.user_id),
        topic=session.topic,
        starting_level=session.starting_level,
        current_level=session.current_level,
        rank_points=session.rank_points,
        streak_correct=session.streak_correct,
        streak_wrong=session.streak_wrong,
        total_questions=session.total_questions,
        correct_answers=session.correct_answers,
        is_completed=session.is_completed,
    )


@limiter.limit("30/minute")
@router.post("/v2/generate-question", response_model=ChallengeQuestionOut)
async def generate_challenge_question_endpoint(
    request: Request,
    body: ChallengeGenerateQuestionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate a challenge question for the current level (MHD-style).
    
    Stores question in database and returns it with correctAnswer visible
    (frontend uses this for immediate feedback, but server still verifies).
    """
    try:
        session_uuid = uuid.UUID(body.session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session ID format")
    
    session_stmt = select(ChallengeSession).where(ChallengeSession.id == session_uuid)
    session_result = await db.execute(session_stmt)
    session = session_result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your session")
    
    if session.is_completed:
        raise HTTPException(status_code=400, detail="Session is already completed")
    
    # Generate question using level-specific LLM
    llm = getattr(request.app.state, "llm_client", None)
    question_dict = None
    
    if llm:
        # Try RAG for context at higher levels
        context = ""
        if body.level >= 3:
            rag = getattr(request.app.state, "rag_pipeline", None)
            http_client = getattr(request.app.state, "http_client", None)
            if rag and http_client:
                try:
                    rag_result = await rag.run(
                        topic=body.topic,
                        difficulty=body.level,
                        user_accuracy=0.5,
                        llm_client=llm,
                        http_client=http_client,
                    )
                    if rag_result:
                        context = rag_result.get("text", "")
                        logger.info(f"RAG context provided", extra={
                            "level": body.level,
                            "context_length": len(context),
                            "rag_metadata": rag_result.get("metadata", {})
                        })
                    else:
                        logger.warning(f"RAG returned empty result for level {body.level}")
                except Exception as e:
                    logger.warning(f"RAG context fetch failed", extra={
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "level": body.level,
                        "topic": body.topic
                    })
        
        question_dict = await generate_challenge_question_with_fallback(
            llm=llm,
            topic=body.topic,
            level=body.level,
            context=context,
        )
    
    if not question_dict:
        raise HTTPException(status_code=503, detail="Could not generate a question. Please try again.")
    
    # Store in question_bank
    try:
        await classic_crud.store_question(
            db,
            question_id=question_dict["id"],
            question_text=question_dict["text"],
            correct_answer=question_dict["correctAnswer"],
            options=question_dict["options"],
            explanation=question_dict.get("explanation", ""),
            topic=body.topic,
            difficulty=body.level,
            source="challenge_llm",
        )
    except Exception as e:
        logger.error(f"Could not store challenge question: {e}")
        raise HTTPException(status_code=500, detail="Failed to persist question")
    
    correct_pts, _ = CHALLENGE_POINTS_TABLE.get(body.level, (3, -1))
    
    return ChallengeQuestionOut(
        id=question_dict["id"],
        text=question_dict["text"],
        options=question_dict["options"],
        correctAnswer=question_dict["correctAnswer"],
        explanation=question_dict.get("explanation", ""),
        level=body.level,
        points_value=correct_pts,
        is_free_text=question_dict.get("is_free_text", False),
    )


@limiter.limit("30/minute")
@router.post("/v2/submit-answer", response_model=ChallengeSubmitAnswerResponse)
async def submit_challenge_answer_mhd_style(
    request: Request,
    body: ChallengeSubmitAnswerRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Submit answer by string (MHD-style).
    
    Uses server-side verification against stored correct_answer.
    """
    # Validate answer is not empty
    if not body.answer or not str(body.answer).strip():
        raise HTTPException(status_code=400, detail="Answer cannot be empty")
    
    try:
        session_uuid = uuid.UUID(body.session_id)
        question_uuid = uuid.UUID(body.question_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ID format")
    
    session_stmt = select(ChallengeSession).where(ChallengeSession.id == session_uuid)
    session_result = await db.execute(session_stmt)
    session = session_result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your session")
    
    if session.is_completed:
        raise HTTPException(status_code=400, detail="Session already completed")
    
    # Anti-abuse: no duplicate answers
    if await has_answered_question(db, session_uuid, question_uuid):
        raise HTTPException(status_code=409, detail="This question has already been answered")
    
    # Verify question exists
    question_stmt = select(QuestionBank).where(QuestionBank.id == question_uuid)
    question_result = await db.execute(question_stmt)
    question = question_result.scalar_one_or_none()
    
    if not question:
        raise HTTPException(status_code=400, detail="Question not found in database")
    
    # Server-side answer verification (MHD logic)
    is_correct = await _verify_answer_server_side(db, body.question_id, body.answer)
    
    logger.info(
        f"Answer verification: user={str(current_user.id)[:8]} "
        f"question={body.question_id[:8]} submitted='{body.answer}' "
        f"correct_stored='{question.correct_answer}' match={is_correct}"
    )
    
    current_level = session.current_level
    points_change = calculate_points(current_level, is_correct)
    
    # Update streaks (MHD logic)
    new_streak_correct, new_streak_wrong = update_streaks_after_answer(
        session.streak_correct, session.streak_wrong, is_correct
    )
    
    # Check streak trigger with rank-bounded level change
    level_trigger = check_streak_trigger(new_streak_correct, new_streak_wrong)
    new_level = current_level
    force_level_change_out = None
    
    if level_trigger:
        # Get user rank for boundary enforcement
        user_rank = await get_or_create_user_challenge_rank(db, current_user.id)
        rank_name = get_rank_name_from_id(user_rank.current_rank_id)
        
        new_level = apply_level_change(current_level, level_trigger["direction"], rank_name)
        
        # MHD logic: Reset ONLY the triggering streak
        if level_trigger["direction"] == "up":
            new_streak_correct = 0
        else:
            new_streak_wrong = 0
        
        force_level_change_out = ForceLevelChange(
            direction=level_trigger["direction"],
            reason=level_trigger["reason"],
        )
        
        logger.info(
            f"Level change triggered: session={body.session_id[:8]} "
            f"{level_trigger['direction']} → level {new_level}"
        )
    
    # Record answer in DB
    await record_challenge_answer(
        db=db,
        session_id=session_uuid,
        question_id=question_uuid,
        chosen_answer=body.answer,
        is_correct=is_correct,
        points_change=points_change,
        level_at_answer=current_level,
        time_taken=body.time_taken,
    )
    
    # Update session state
    updated_session = await update_session_after_answer(
        db=db,
        session=session,
        is_correct=is_correct,
        points_change=points_change,
        new_streak_correct=new_streak_correct,
        new_streak_wrong=new_streak_wrong,
        new_level=new_level,
    )
    
    logger.info(
        f"Challenge answer: correct={is_correct} pts={points_change:+d} "
        f"level={current_level}→{new_level} session_pts={updated_session.rank_points}"
    )
    
    return ChallengeSubmitAnswerResponse(
        is_correct=is_correct,
        points_change=points_change,
        new_rank_points=updated_session.rank_points,
        new_level=new_level,
        streak_correct=new_streak_correct,
        streak_wrong=new_streak_wrong,
        force_level_change=force_level_change_out,
    )


@limiter.limit("15/minute")
@router.post("/v2/session/{session_id}/end", response_model=ChallengeEndSessionResponse)
async def end_challenge_session_mhd_style(
    request: Request,
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    End a challenge session (MHD-style).
    
    Updates global ranking with session points.
    """
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session ID format")
    
    session_stmt = select(ChallengeSession).where(ChallengeSession.id == session_uuid)
    session_result = await db.execute(session_stmt)
    session = session_result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your session")
    
    # If already completed, just return current state
    if session.is_completed:
        user_rank = await get_or_create_user_challenge_rank(db, current_user.id)
        rank_name = get_rank_name_from_id(user_rank.current_rank_id)
        return ChallengeEndSessionResponse(
            session_id=session_id,
            total_questions=session.total_questions,
            correct_answers=session.correct_answers,
            total_points_earned=session.rank_points,
            new_rank=rank_name,
            new_rank_points=user_rank.rank_points,
            rank_changed=False,
        )
    
    # Get old rank before update
    old_user_rank = await get_or_create_user_challenge_rank(db, current_user.id)
    old_rank_id = old_user_rank.current_rank_id
    
    # Finalize session
    await finalize_session(db, session)
    
    # Update global ranking
    won = session.correct_answers >= (session.total_questions * WIN_THRESHOLD) if session.total_questions > 0 else False
    user_rank, rank_changed = await update_global_ranking(
        db=db,
        user_id=current_user.id,
        session_points=session.rank_points,
        session_streak=session.highest_streak,
        won=won,
    )
    
    rank_name = get_rank_name_from_id(user_rank.current_rank_id)
    
    logger.info(
        f"Session ended: session={session_id[:8]} "
        f"pts={session.rank_points} rank={get_rank_name_from_id(old_rank_id)}→{rank_name}"
    )
    
    return ChallengeEndSessionResponse(
        session_id=session_id,
        total_questions=session.total_questions,
        correct_answers=session.correct_answers,
        total_points_earned=session.rank_points,
        new_rank=rank_name,
        new_rank_points=user_rank.rank_points,
        rank_changed=rank_changed,
    )
