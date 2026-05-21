"""
services/challenge_service.py — Business logic for the Challenge Room.
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database.challenge_models import ChallengeSession, ChallengeAnswer, ChallengeRanking

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═════════════════════════════════════════════════════════════════════════

CHALLENGE_POINTS_TABLE: dict[int, tuple[int, int]] = {
    1: (3,  -1),
    2: (5,  -2),
    3: (7,  -4),
    4: (9,  -6),
    5: (11, -9),
}

STREAK_UP_THRESHOLD   = 4   # 4 correct in a row → level up
STREAK_DOWN_THRESHOLD = 2   # 2 wrong  in a row → level down

RANK_THRESHOLDS: list[tuple[int, str]] = [
    (0,     "E"),
    (1000,  "D"),
    (3000,  "C"),
    (7000,  "B"),
    (15000, "A"),
]

# Which levels each rank can access — also defines the min/max level
# a user can reach during a session (level changes are clamped to this range)
RANK_LEVEL_ACCESS: dict[str, list[int]] = {
    "E": [1, 2],
    "D": [1, 2, 3],
    "C": [2, 3, 4],
    "B": [3, 4, 5],
    "A": [4, 5],
}

ALL_RANKS = ["E", "D", "C", "B", "A"]


# ═════════════════════════════════════════════════════════════════════════
# PURE LOGIC HELPERS
# ═════════════════════════════════════════════════════════════════════════

def get_available_levels(rank: str) -> list[int]:
    """Return level list available for this rank."""
    return RANK_LEVEL_ACCESS.get(rank, [1, 2])


def is_level_allowed(rank: str, level: int) -> bool:
    """Check if a starting level is valid for this rank."""
    return level in get_available_levels(rank)


def calculate_points(level: int, is_correct: bool) -> int:
    """Correct → positive points. Wrong → negative points."""
    correct_pts, wrong_pts = CHALLENGE_POINTS_TABLE.get(level, (3, -1))
    return correct_pts if is_correct else wrong_pts


def check_streak_trigger(
    streak_correct: int,
    streak_wrong: int,
) -> Optional[dict]:
    """
    Check if a streak threshold was hit.
    Returns direction + reason dict, or None.
    """
    if streak_correct >= STREAK_UP_THRESHOLD:
        return {
            "direction": "up",
            "reason": f"Outstanding! {streak_correct} correct in a row — advancing to next level.",
        }
    if streak_wrong >= STREAK_DOWN_THRESHOLD:
        return {
            "direction": "down",
            "reason": f"{streak_wrong} wrong answers — dropping to a more suitable level.",
        }
    return None


def apply_level_change(current_level: int, direction: str, rank: str) -> int:
    """
    Apply a forced level change, clamped to the user's rank boundaries.

    A rank C player (levels 2-4) can never go below 2 or above 4,
    even with a long streak. This keeps users in their skill zone.
    """
    available = get_available_levels(rank)
    min_level = min(available)
    max_level = max(available)

    if direction == "up":
        return min(max_level, current_level + 1)
    elif direction == "down":
        return max(min_level, current_level - 1)
    return current_level


def compute_rank_from_points(total_points: int) -> str:
    """Determine rank letter from cumulative rank_points."""
    rank = "E"
    for threshold, r in RANK_THRESHOLDS:
        if total_points >= threshold:
            rank = r
    return rank


def update_streaks_after_answer(
    streak_correct: int,
    streak_wrong: int,
    is_correct: bool,
) -> tuple[int, int]:
    """
    Correct → increment correct streak, reset wrong streak.
    Wrong   → increment wrong streak, reset correct streak.
    Returns (new_streak_correct, new_streak_wrong).
    """
    if is_correct:
        return (streak_correct + 1, 0)
    else:
        return (0, streak_wrong + 1)


# ═════════════════════════════════════════════════════════════════════════
# DB OPERATIONS
# ═════════════════════════════════════════════════════════════════════════

async def get_or_create_ranking(
    db: AsyncSession,
    user_id: str,
) -> ChallengeRanking:
    uid = uuid.UUID(user_id)
    result = await db.execute(
        select(ChallengeRanking).where(ChallengeRanking.user_id == uid)
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = ChallengeRanking(
            user_id      = uid,
            current_rank = "E",
            rank_points  = 0,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


async def create_challenge_session(
    db: AsyncSession,
    user_id: str,
    topic: str,
    starting_level: int,
) -> ChallengeSession:
    row = ChallengeSession(
        id             = uuid.uuid4(),
        user_id        = uuid.UUID(user_id),
        topic          = topic,
        starting_level = starting_level,
        current_level  = starting_level,
        rank_points    = 0,
        streak_correct = 0,
        streak_wrong   = 0,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def get_challenge_session(
    db: AsyncSession,
    session_id: str,
) -> Optional[ChallengeSession]:
    result = await db.execute(
        select(ChallengeSession).where(
            ChallengeSession.id == uuid.UUID(session_id)
        )
    )
    return result.scalar_one_or_none()


async def record_challenge_answer(
    db: AsyncSession,
    session_id: str,
    question_id: str,
    chosen_answer: str,
    is_correct: bool,
    points_change: int,
    level_at_answer: int,
    time_taken: Optional[float],
) -> ChallengeAnswer:
    row = ChallengeAnswer(
        id              = uuid.uuid4(),
        session_id      = uuid.UUID(session_id),
        question_id     = uuid.UUID(question_id),
        chosen_answer   = chosen_answer,
        is_correct      = is_correct,
        points_change   = points_change,
        level_at_answer = level_at_answer,
        time_taken      = time_taken,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def update_session_after_answer(
    db: AsyncSession,
    session: ChallengeSession,
    is_correct: bool,
    points_change: int,
    new_streak_correct: int,
    new_streak_wrong: int,
    new_level: int,
) -> ChallengeSession:
    session.rank_points    += points_change
    session.streak_correct  = new_streak_correct
    session.streak_wrong    = new_streak_wrong
    session.current_level   = new_level
    session.total_questions += 1
    if is_correct:
        session.correct_answers += 1
    await db.commit()
    await db.refresh(session)
    return session


async def finalize_session(
    db: AsyncSession,
    session: ChallengeSession,
) -> ChallengeSession:
    session.is_completed = True
    session.ended_at     = datetime.utcnow()
    await db.commit()
    await db.refresh(session)
    return session


async def update_global_ranking(
    db: AsyncSession,
    user_id: str,
    session_points: int,
    session_questions: int,
    session_streak: int,
) -> ChallengeRanking:
    ranking = await get_or_create_ranking(db, user_id)
    old_rank = ranking.current_rank

    ranking.rank_points     += session_points
    ranking.total_sessions  += 1
    ranking.total_questions += session_questions
    ranking.highest_streak   = max(ranking.highest_streak, session_streak)
    ranking.updated_at       = datetime.utcnow()
    ranking.current_rank     = compute_rank_from_points(ranking.rank_points)

    await db.commit()
    await db.refresh(ranking)

    if ranking.current_rank != old_rank:
        logger.info(
            f"User {user_id[:8]} promoted: {old_rank} → {ranking.current_rank} "
            f"({ranking.rank_points} pts)"
        )
    return ranking


async def has_answered_question(
    db: AsyncSession,
    session_id: str,
    question_id: str,
) -> bool:
    result = await db.execute(
        select(ChallengeAnswer).where(
            ChallengeAnswer.session_id  == uuid.UUID(session_id),
            ChallengeAnswer.question_id == uuid.UUID(question_id),
        )
    )
    return result.scalar_one_or_none() is not None