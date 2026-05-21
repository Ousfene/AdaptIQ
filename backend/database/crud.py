"""
database/crud.py — Async CRUD operations using SQLAlchemy 2.0 async API.

All functions accept an AsyncSession and return domain objects.

Covers:
    - user_responses inserts and history/accuracy queries
    - question_bank insert/cache fetch helpers
    - post-answer IRT recalibration persistence
"""

from __future__ import annotations
import json
import uuid
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from database.models import UserResponse, QuestionBank
from database.irt import update_beta, difficulty_to_beta, beta_to_difficulty
from schemas.types import QuestionOut


# ── user_responses ────────────────────────────────────────────────────────

# Insert one user response row and return the persisted record.
async def create_user_response(
    db: AsyncSession,
    *,
    user_id: str,
    session_id: str,
    question_id: str,
    topic: str,
    difficulty_sent: int,
    answered_correct: bool,
    time_taken: int,
    used_hint: bool,
) -> UserResponse:
    row = UserResponse(
        id               = uuid.uuid4(),
        user_id          = uuid.UUID(user_id),
        session_id       = uuid.UUID(session_id),
        question_id      = uuid.UUID(question_id),
        topic            = topic,
        difficulty_sent  = difficulty_sent,
        answered_correct = answered_correct,
        time_taken       = time_taken,
        used_hint        = used_hint,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


# Compute recent user accuracy for a topic using latest responses.
async def get_user_accuracy_by_topic(
    db: AsyncSession,
    user_id: str,
    topic: str,
    limit: int = 20,
) -> float:
    """Return fraction of correct answers for this user+topic (last N responses)."""
    stmt = (
        select(UserResponse.answered_correct)
        .where(
            UserResponse.user_id == uuid.UUID(user_id),
            UserResponse.topic == topic,
        )
        .order_by(UserResponse.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    if not rows:
        return 0.5   # neutral prior
    return sum(rows) / len(rows)


# Return recent response history needed by adaptive difficulty logic.
async def get_user_recent_responses(
    db: AsyncSession,
    user_id: str,
    limit: int = 10,
) -> list[dict]:
    stmt = (
        select(UserResponse)
        .where(UserResponse.user_id == uuid.UUID(user_id))
        .order_by(UserResponse.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        {"difficulty_sent": r.difficulty_sent, "answered_correct": r.answered_correct}
        for r in rows
    ]


# ── question_bank ─────────────────────────────────────────────────────────

# Persist one generated question into question_bank.
async def store_question(
    db: AsyncSession,
    *,
    question_id: str,
    question_text: str,
    correct_answer: str,
    options: list[str],
    explanation: str,
    topic: str,
    difficulty: int,
    source: str = "llm",
) -> QuestionBank:
    row = QuestionBank(
        id            = uuid.UUID(question_id),
        question_text = question_text,
        correct_answer= correct_answer,
        options_json  = json.dumps(options),
        explanation   = explanation,
        topic         = topic,
        difficulty_irt= float(difficulty),
        source        = source,
    )
    db.add(row)
    await db.commit()
    return row


# Retrieve one cached question near target difficulty, excluding seen ids.
async def get_cached_question(
    db: AsyncSession,
    topic: str,
    difficulty: int,
    seen_ids: set[str],
) -> Optional[QuestionOut]:
    """
    Fetch a question from the bank at the target difficulty (±0.5 window).
    Excludes questions already seen in this session.
    """
    low  = max(1.0, difficulty - 0.5)
    high = min(5.0, difficulty + 0.5)

    stmt = (
        select(QuestionBank)
        .where(
            QuestionBank.topic == topic,
            QuestionBank.difficulty_irt.between(low, high),
        )
        .order_by(func.random())
        .limit(20)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    for row in rows:
        if str(row.id) in seen_ids:
            continue
        # Increment usage count
        await db.execute(
            update(QuestionBank)
            .where(QuestionBank.id == row.id)
            .values(usage_count=QuestionBank.usage_count + 1)
        )
        await db.commit()
        return QuestionOut(
            id            = str(row.id),
            text          = row.question_text,
            options       = json.loads(row.options_json),
            correctAnswer = row.correct_answer,
            explanation   = row.explanation,
        )
    return None


# Recalculate and store question difficulty from one answer outcome.
async def recalibrate_question_irt(
    db: AsyncSession,
    question_id: str,
    theta: float,
    answered_correct: bool,
) -> None:
    """Update a question's IRT β parameter after an answer."""
    stmt = select(QuestionBank).where(QuestionBank.id == uuid.UUID(question_id))
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        return

    old_beta = row.difficulty_irt
    # Convert from 1-5 scale to IRT scale for computation
    from database.irt import difficulty_to_beta, update_beta, beta_to_difficulty
    beta_irt  = difficulty_to_beta(int(round(old_beta)))
    new_beta  = update_beta(beta_irt, theta, answered_correct)
    new_diff  = beta_to_difficulty(new_beta)

    await db.execute(
        update(QuestionBank)
        .where(QuestionBank.id == uuid.UUID(question_id))
        .values(difficulty_irt=float(new_diff))
    )
    await db.commit()
