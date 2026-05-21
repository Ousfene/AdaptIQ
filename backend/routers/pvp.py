"""
routers/pvp.py — PvP Room endpoints for 1v1 matchmaking and matches.

Endpoints:
  - POST   /api/pvp/join-queue        → Join the matchmaking queue
  - DELETE /api/pvp/leave-queue        → Leave the queue
  - GET    /api/pvp/queue-status       → Poll for match status
  - GET    /api/pvp/match/{match_id}   → Get match details + questions
  - POST   /api/pvp/match/{match_id}/answer → Submit an answer
  - POST   /api/pvp/match/{match_id}/end    → End match + get results
  - GET    /api/pvp/user/{user_id}/rating   → Get PvP rating
  - GET    /api/pvp/leaderboard             → Top players

Implementation summary:
    - Matchmaking endpoints delegate queue orchestration to services.pvp_service
    - Gameplay endpoints enforce participant checks before reading/updating match state
    - Rating endpoints expose per-user Elo and global leaderboard snapshots
"""

import json
import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import limiter
from routers.auth import get_current_user, get_db
from database.pvp_models import PvPMatchAnswer
from schemas.pvp import (
    JoinQueueRequest,
    JoinQueueResponse,
    LeaveQueueRequest,
    LeaveQueueResponse,
    QueueStatusResponse,
    PvPMatchOut,
    PvPQuestionOut,
    PvPSubmitAnswerRequest,
    PvPSubmitAnswerResponse,
    PvPEndMatchResponse,
    PvPRatingOut,
    LeaderboardResponse,
    LeaderboardEntry,
)
from services.pvp_service import (
    join_queue,
    leave_queue,
    get_queue_status,
    get_match,
    submit_answer,
    end_match,
    get_user_rating,
    get_leaderboard,
)

logger = logging.getLogger(__name__)
pvp_router = APIRouter(prefix="/api/pvp", tags=["PvP Room"])


# ═══════════════════════════════════════════════════════════════════════════
# MATCHMAKING
# ═══════════════════════════════════════════════════════════════════════════


@pvp_router.post("/join-queue", response_model=JoinQueueResponse)
@limiter.limit("10/minute")
# Add the current user to the PvP queue and try to match immediately.
async def join_queue_endpoint(
    request: Request,
    body: JoinQueueRequest,
    db: AsyncSession = Depends(get_db),
    current=Depends(get_current_user),
):
    """Join the PvP matchmaking queue.

    Finds an opponent with similar Elo and shared concept knowledge.
    Poll /queue-status to check if matched.
    """
    user, _ = current
    if str(user.id) != body.user_id:
        raise HTTPException(403, "User ID mismatch")

    logger.info("User %s joining PvP queue (topic=%s)", str(user.id)[:8], body.topic)
    entry = await join_queue(db, user.id, body.topic)

    return JoinQueueResponse(
        queue_id=str(entry.id),
        status=entry.status,
        message="Matched!" if entry.status == "matched" else "Searching for an opponent...",
    )


@pvp_router.delete("/leave-queue", response_model=LeaveQueueResponse)
@limiter.limit("20/minute")
# Remove the current user from matchmaking if queued.
async def leave_queue_endpoint(
    request: Request,
    body: LeaveQueueRequest,
    db: AsyncSession = Depends(get_db),
    current=Depends(get_current_user),
):
    """Leave the matchmaking queue."""
    user, _ = current
    if str(user.id) != body.user_id:
        raise HTTPException(403, "User ID mismatch")

    removed = await leave_queue(db, user.id)
    return LeaveQueueResponse(
        success=removed,
        message="Left the queue" if removed else "Not in queue",
    )


@pvp_router.get("/queue-status", response_model=QueueStatusResponse)
@limiter.limit("60/minute")
# Return current queue state and matched match_id when available.
async def queue_status_endpoint(
    request: Request,
    user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current=Depends(get_current_user),
):
    """Poll for matchmaking status.

    Returns "waiting" if still searching, "matched" if opponent found.
    Frontend should poll this every 2-3 seconds.
    """
    user, _ = current
    if str(user.id) != user_id:
        raise HTTPException(403, "User ID mismatch")

    status = await get_queue_status(db, user.id)
    return QueueStatusResponse(**status)


# ═══════════════════════════════════════════════════════════════════════════
# MATCH GAMEPLAY
# ═══════════════════════════════════════════════════════════════════════════


@pvp_router.get("/match/{match_id}", response_model=PvPMatchOut)
@limiter.limit("60/minute")
# Fetch match state and only the next unanswered question for a participant.
async def get_match_endpoint(
    request: Request,
    match_id: str,
    db: AsyncSession = Depends(get_db),
    current=Depends(get_current_user),
):
    """Get match details — returns only the current playable question and scores.

    The correct answer is NOT included — it's revealed after each answer submission.
    Future questions are intentionally hidden to prevent pre-reading.
    """
    user, _ = current
    try:
        mid = uuid.UUID(match_id)
    except ValueError:
        raise HTTPException(422, "Invalid match ID")

    match = await get_match(db, mid)
    if not match:
        raise HTTPException(404, "Match not found")

    if user.id not in (match.user1_id, match.user2_id):
        raise HTTPException(403, "You are not in this match")

    # Reveal only the next unanswered question for this user.
    raw_questions = json.loads(match.questions_json or "[]")
    answered_count = await db.scalar(
        select(func.count()).select_from(PvPMatchAnswer).where(
            PvPMatchAnswer.match_id == mid,
            PvPMatchAnswer.user_id == user.id,
        )
    )
    answered_count = int(answered_count or 0)

    questions: list[PvPQuestionOut] = []
    if answered_count < len(raw_questions):
        current_question = raw_questions[answered_count]
        current_options = current_question.get("options") if isinstance(current_question.get("options"), list) else []
        questions = [
            PvPQuestionOut(
                id=str(current_question.get("id", "")),
                text=str(current_question.get("text", "")),
                options=[str(opt) for opt in current_options],
                index=int(current_question.get("index", answered_count)),
            )
        ]

    return PvPMatchOut(
        match_id=str(match.id),
        user1_id=str(match.user1_id),
        user2_id=str(match.user2_id),
        topic=match.topic,
        status=match.status,
        total_questions=match.total_questions,
        questions=questions,
        user1_score=match.user1_score,
        user2_score=match.user2_score,
        user1_finished=match.user1_finished,
        user2_finished=match.user2_finished,
    )


@pvp_router.post("/match/{match_id}/answer", response_model=PvPSubmitAnswerResponse)
@limiter.limit("30/minute")
# Score one answer submission and update live match progress.
async def submit_answer_endpoint(
    request: Request,
    match_id: str,
    body: PvPSubmitAnswerRequest,
    db: AsyncSession = Depends(get_db),
    current=Depends(get_current_user),
):
    """Submit an answer for a question in an active PvP match.

    Validates the answer, updates scores, and checks if match is complete.
    """
    user, _ = current
    if str(user.id) != body.user_id:
        raise HTTPException(403, "User ID mismatch")

    try:
        mid = uuid.UUID(match_id)
    except ValueError:
        raise HTTPException(422, "Invalid match ID")

    try:
        result = await submit_answer(
            db,
            match_id=mid,
            user_id=user.id,
            question_id=body.question_id,
            question_index=body.question_index,
            answer=body.answer,
            time_taken=body.time_taken,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    return PvPSubmitAnswerResponse(**result)


@pvp_router.post("/match/{match_id}/end", response_model=PvPEndMatchResponse)
@limiter.limit("10/minute")
# Finalize a match for the caller and return Elo/ranking effects.
async def end_match_endpoint(
    request: Request,
    match_id: str,
    db: AsyncSession = Depends(get_db),
    current=Depends(get_current_user),
):
    """End a match and get final results with Elo changes.

    Can be called by either player. Match auto-ends when both finish.
    """
    user, _ = current
    try:
        mid = uuid.UUID(match_id)
    except ValueError:
        raise HTTPException(422, "Invalid match ID")

    try:
        result = await end_match(db, mid, user.id)
    except ValueError as e:
        message = str(e)
        if "not in this match" in message.lower():
            raise HTTPException(403, message)
        raise HTTPException(400, message)

    return PvPEndMatchResponse(**result)


# ═══════════════════════════════════════════════════════════════════════════
# RATING / LEADERBOARD
# ═══════════════════════════════════════════════════════════════════════════


@pvp_router.get("/user/{user_id}/rating", response_model=PvPRatingOut)
@limiter.limit("30/minute")
# Return PvP rating profile and aggregate match stats for one user.
async def get_rating_endpoint(
    request: Request,
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current=Depends(get_current_user),
):
    """Get a user's PvP Elo rating and match history stats."""
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(422, "Invalid user ID")

    try:
        result = await get_user_rating(db, uid)
    except ValueError as e:
        if str(e) == "User not found":
            raise HTTPException(404, "User not found")
        raise HTTPException(400, str(e))

    return PvPRatingOut(**result)


@pvp_router.get("/leaderboard", response_model=LeaderboardResponse)
@limiter.limit("20/minute")
# Return top players sorted by rating.
async def get_leaderboard_endpoint(
    request: Request,
    limit: int = Query(default=20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current=Depends(get_current_user),
):
    """Get the PvP leaderboard — top players ranked by Elo."""
    result = await get_leaderboard(db, limit)
    return LeaderboardResponse(
        entries=[LeaderboardEntry(**e) for e in result["entries"]],
        total_players=result["total_players"],
    )
