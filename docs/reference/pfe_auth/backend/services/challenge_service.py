"""
services/challenge_service.py — Business logic for the Challenge Room.

Ported from MHD version with adaptations for Main backend:
- Uses Main's ChallengeRank/UserChallengeRank models
- Maps Bronze/Silver/Gold/Platinum/Diamond to level access
- Integrates with existing JWT auth flow
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database.models import (
    ChallengeSession, ChallengeAnswer, UserChallengeRank, ChallengeRank
)

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    """Return current UTC time as naive datetime."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ═════════════════════════════════════════════════════════════════════════
# CONFIGURATION (ported from MHD)
# ═════════════════════════════════════════════════════════════════════════

# Points awarded/deducted per level
# Level 1 is easy (low risk/reward), Level 5 is hard (high risk/reward)
CHALLENGE_POINTS_TABLE: dict[int, tuple[int, int]] = {
    1: (3,  -1),   # Easy:   +3 correct, -1 wrong
    2: (5,  -2),   # Medium: +5 correct, -2 wrong
    3: (7,  -4),   # Hard:   +7 correct, -4 wrong
    4: (9,  -6),   # Expert: +9 correct, -6 wrong
    5: (11, -9),   # Master: +11 correct, -9 wrong (future: free-text)
}

# Streak thresholds for automatic level changes
STREAK_UP_THRESHOLD = 4    # 4 correct in a row → level up
STREAK_DOWN_THRESHOLD = 2  # 2 wrong in a row → level down

# Map Main backend rank names to level access
# Bronze = entry level (levels 1-2)
# Diamond = expert level (levels 4-5)
RANK_LEVEL_ACCESS: dict[str, list[int]] = {
    "Bronze":   [1, 2],
    "Silver":   [1, 2, 3],
    "Gold":     [2, 3, 4],
    "Platinum": [3, 4, 5],
    "Diamond":  [4, 5],
}

# Points thresholds for rank progression
# These are cumulative points, not per-session
RANK_THRESHOLDS: list[tuple[int, str]] = [
    (0,     "Bronze"),
    (1000,  "Silver"),
    (3000,  "Gold"),
    (7000,  "Platinum"),
    (15000, "Diamond"),
]

ALL_RANKS = ["Bronze", "Silver", "Gold", "Platinum", "Diamond"]


# ═════════════════════════════════════════════════════════════════════════
# PURE LOGIC HELPERS
# ═════════════════════════════════════════════════════════════════════════

def get_available_levels(rank_name: str) -> list[int]:
    """Return list of levels available for this rank."""
    return RANK_LEVEL_ACCESS.get(rank_name, [1, 2])


def is_level_allowed(rank_name: str, level: int) -> bool:
    """Check if a starting level is valid for this rank."""
    return level in get_available_levels(rank_name)


def get_starting_level(rank_name: str) -> int:
    """Get the default starting level for a rank (lowest available)."""
    levels = get_available_levels(rank_name)
    return min(levels) if levels else 1


def calculate_points(level: int, is_correct: bool) -> int:
    """
    Calculate points for an answer.
    
    Correct → positive points (higher levels = more points)
    Wrong → negative points (higher levels = more penalty)
    """
    correct_pts, wrong_pts = CHALLENGE_POINTS_TABLE.get(level, (3, -1))
    return correct_pts if is_correct else wrong_pts


def check_streak_trigger(
    streak_correct: int,
    streak_wrong: int,
) -> Optional[dict]:
    """
    Check if a streak threshold was hit.
    
    Returns dict with direction and reason, or None if no trigger.
    """
    if streak_correct >= STREAK_UP_THRESHOLD:
        return {
            "direction": "up",
            "reason": f"Outstanding! {streak_correct} correct in a row — advancing to next level!",
        }
    if streak_wrong >= STREAK_DOWN_THRESHOLD:
        return {
            "direction": "down",
            "reason": f"{streak_wrong} wrong answers — adjusting to a better-suited level.",
        }
    return None


def apply_level_change(current_level: int, direction: str, rank_name: str) -> int:
    """
    Apply a forced level change, clamped to the user's rank boundaries.
    
    A Gold player (levels 2-4) can never go below 2 or above 4,
    even with a long streak. This keeps users in their skill zone.
    """
    available = get_available_levels(rank_name)
    min_level = min(available)
    max_level = max(available)

    if direction == "up":
        return min(max_level, current_level + 1)
    elif direction == "down":
        return max(min_level, current_level - 1)
    return current_level


def compute_rank_from_points(total_points: int) -> str:
    """Determine rank name from cumulative rank_points."""
    rank = "Bronze"
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
    Update streak counters after an answer.
    
    Correct → increment correct streak, reset wrong streak.
    Wrong → increment wrong streak, reset correct streak.
    
    Returns (new_streak_correct, new_streak_wrong).
    """
    if is_correct:
        return (streak_correct + 1, 0)
    else:
        return (0, streak_wrong + 1)


def get_rank_id_from_name(rank_name: str) -> int:
    """Convert rank name to rank ID."""
    mapping = {"Bronze": 1, "Silver": 2, "Gold": 3, "Platinum": 4, "Diamond": 5}
    return mapping.get(rank_name, 1)


def get_rank_name_from_id(rank_id: int) -> str:
    """Convert rank ID to rank name."""
    mapping = {1: "Bronze", 2: "Silver", 3: "Gold", 4: "Platinum", 5: "Diamond"}
    return mapping.get(rank_id, "Bronze")


# ═════════════════════════════════════════════════════════════════════════
# DB OPERATIONS
# ═════════════════════════════════════════════════════════════════════════

async def get_or_create_user_challenge_rank(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> UserChallengeRank:
    """Get user's challenge rank, creating if needed."""
    result = await db.execute(
        select(UserChallengeRank).where(UserChallengeRank.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = UserChallengeRank(
            user_id=user_id,
            current_rank_id=1,  # Bronze
            wins=0,
            losses=0,
            skip_attempts_remaining=3,
            rank_points=0,
            highest_streak=0,
            total_sessions=0,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


async def get_challenge_rank(db: AsyncSession, rank_id: int) -> Optional[ChallengeRank]:
    """Get a challenge rank by ID."""
    result = await db.execute(
        select(ChallengeRank).where(ChallengeRank.id == rank_id)
    )
    return result.scalar_one_or_none()


async def create_challenge_session(
    db: AsyncSession,
    user_id: uuid.UUID,
    match_id: uuid.UUID,
    topic: str,
    starting_level: int,
) -> ChallengeSession:
    """Create a new challenge session with streaks tracking."""
    row = ChallengeSession(
        id=uuid.uuid4(),
        user_id=user_id,
        match_id=match_id,
        topic=topic,
        starting_level=starting_level,
        current_level=starting_level,
        rank_points=0,
        streak_correct=0,
        streak_wrong=0,
        highest_streak=0,
        total_questions=0,
        correct_answers=0,
        started_at=utc_now(),
        is_completed=False,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def get_challenge_session(
    db: AsyncSession,
    session_id: uuid.UUID,
) -> Optional[ChallengeSession]:
    """Get a challenge session by ID."""
    result = await db.execute(
        select(ChallengeSession).where(ChallengeSession.id == session_id)
    )
    return result.scalar_one_or_none()


async def get_session_by_match_id(
    db: AsyncSession,
    match_id: uuid.UUID,
) -> Optional[ChallengeSession]:
    """Get a challenge session by match ID."""
    result = await db.execute(
        select(ChallengeSession).where(ChallengeSession.match_id == match_id)
    )
    return result.scalar_one_or_none()


async def record_challenge_answer(
    db: AsyncSession,
    session_id: uuid.UUID,
    question_id: uuid.UUID,
    chosen_answer: str,
    is_correct: bool,
    points_change: int,
    level_at_answer: int,
    time_taken: Optional[float] = None,
) -> ChallengeAnswer:
    """Record a single answer in a challenge session."""
    row = ChallengeAnswer(
        id=uuid.uuid4(),
        session_id=session_id,
        question_id=question_id,
        chosen_answer=chosen_answer,
        is_correct=is_correct,
        points_change=points_change,
        level_at_answer=level_at_answer,
        time_taken=time_taken,
        created_at=utc_now(),
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
    """Update session state after an answer."""
    session.rank_points += points_change
    session.streak_correct = new_streak_correct
    session.streak_wrong = new_streak_wrong
    session.current_level = new_level
    session.total_questions += 1
    
    if is_correct:
        session.correct_answers += 1
    
    # Track highest streak
    if new_streak_correct > session.highest_streak:
        session.highest_streak = new_streak_correct
    
    await db.commit()
    await db.refresh(session)
    return session


async def finalize_session(
    db: AsyncSession,
    session: ChallengeSession,
) -> ChallengeSession:
    """Mark a session as completed."""
    session.is_completed = True
    session.ended_at = utc_now()
    await db.commit()
    await db.refresh(session)
    return session


async def update_global_ranking(
    db: AsyncSession,
    user_id: uuid.UUID,
    session_points: int,
    session_streak: int,
    won: bool,
) -> tuple[UserChallengeRank, bool]:
    """
    Update user's global challenge ranking after a session.
    
    Returns (updated_rank, rank_changed).
    """
    user_rank = await get_or_create_user_challenge_rank(db, user_id)
    old_rank_id = user_rank.current_rank_id
    
    # Update stats
    user_rank.rank_points += session_points
    user_rank.total_sessions += 1
    
    if won:
        user_rank.wins += 1
    else:
        user_rank.losses += 1
    
    if session_streak > user_rank.highest_streak:
        user_rank.highest_streak = session_streak
    
    # Compute new rank from points
    new_rank_name = compute_rank_from_points(user_rank.rank_points)
    new_rank_id = get_rank_id_from_name(new_rank_name)
    user_rank.current_rank_id = new_rank_id
    
    await db.commit()
    await db.refresh(user_rank)
    
    rank_changed = new_rank_id != old_rank_id
    if rank_changed:
        old_name = get_rank_name_from_id(old_rank_id)
        logger.info(
            f"User {str(user_id)[:8]} rank changed: {old_name} → {new_rank_name} "
            f"({user_rank.rank_points} pts)"
        )
    
    return user_rank, rank_changed


async def has_answered_question(
    db: AsyncSession,
    session_id: uuid.UUID,
    question_id: uuid.UUID,
) -> bool:
    """Check if a question was already answered in this session."""
    result = await db.execute(
        select(ChallengeAnswer).where(
            ChallengeAnswer.session_id == session_id,
            ChallengeAnswer.question_id == question_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def get_session_answered_ids(
    db: AsyncSession,
    session_id: uuid.UUID,
) -> set[uuid.UUID]:
    """Get all question IDs already answered in this session."""
    result = await db.execute(
        select(ChallengeAnswer.question_id).where(
            ChallengeAnswer.session_id == session_id
        )
    )
    return {row[0] for row in result.all()}
