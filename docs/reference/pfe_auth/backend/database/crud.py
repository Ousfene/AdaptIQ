"""
database/crud.py — Async CRUD operations using SQLAlchemy 2.0 async API.

All functions accept an AsyncSession and return domain objects.
"""

from __future__ import annotations
import json
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from database.models import UserResponse, QuestionBank
from database.irt import update_beta, difficulty_to_beta, beta_to_difficulty
from schemas import QuestionOut

logger = logging.getLogger(__name__)


def utc_now_naive() -> datetime:
    """Return current UTC time as naive datetime (for PostgreSQL TIMESTAMP)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


TOPICS = ("history", "geography", "mix")


# ── user_responses ────────────────────────────────────────────────────────

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
    # TODO: Optimize by batching commits for high-frequency inserts
    await db.commit()
    await db.refresh(row)
    return row


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
        # Increment usage count and update last_served_at timestamp
        await db.execute(
            update(QuestionBank)
            .where(QuestionBank.id == row.id)
            .values(
                usage_count=QuestionBank.usage_count + 1,
                last_served_at=utc_now_naive()
            )
        )
        await db.commit()
        try:
            options = json.loads(row.options_json)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse options for question {row.id}: {e}")
            continue

        return QuestionOut(
            id            = str(row.id),
            text          = row.question_text,
            options       = options,
            correctAnswer = row.correct_answer,
            explanation   = row.explanation,
        )
    return None


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


async def get_user_topic_breakdown(db: AsyncSession, user_id: str) -> list[dict]:
    from sqlalchemy import Integer, cast

    stmt = (
        select(
            UserResponse.topic.label("topic"),
            func.count(UserResponse.id).label("total_questions"),
            func.coalesce(func.sum(cast(UserResponse.answered_correct, Integer)), 0).label("correct_questions"),
            func.coalesce(func.sum(cast(UserResponse.used_hint, Integer)), 0).label("hints_used"),
            func.coalesce(func.avg(UserResponse.time_taken), 0).label("avg_time_seconds"),
        )
        .where(UserResponse.user_id == uuid.UUID(user_id))
        .group_by(UserResponse.topic)
    )
    result = await db.execute(stmt)
    rows = {
        row.topic: {
            "topic": row.topic,
            "total_questions": int(row.total_questions or 0),
            "correct_questions": int(row.correct_questions or 0),
            "hints_used": int(row.hints_used or 0),
            "avg_time_seconds": round(float(row.avg_time_seconds or 0), 1),
        }
        for row in result
    }

    out: list[dict] = []
    for topic in TOPICS:
        entry = rows.get(
            topic,
            {
                "topic": topic,
                "total_questions": 0,
                "correct_questions": 0,
                "hints_used": 0,
                "avg_time_seconds": 0.0,
            },
        )
        total = entry["total_questions"]
        correct = entry["correct_questions"]
        entry["accuracy"] = round((correct / total) * 100, 1) if total > 0 else 0.0
        out.append(entry)
    return out


async def get_user_daily_trend(db: AsyncSession, user_id: str, days: int = 7) -> list[dict]:
    from sqlalchemy import Integer, cast

    window_days = max(1, min(days, 90))
    start_day = date.today() - timedelta(days=window_days - 1)

    stmt = (
        select(
            func.date(UserResponse.created_at).label("day"),
            func.count(UserResponse.id).label("total_questions"),
            func.coalesce(func.sum(cast(UserResponse.answered_correct, Integer)), 0).label("correct_questions"),
            func.coalesce(func.avg(UserResponse.time_taken), 0).label("avg_time_seconds"),
        )
        .where(
            UserResponse.user_id == uuid.UUID(user_id),
            UserResponse.created_at >= start_day,
        )
        .group_by(func.date(UserResponse.created_at))
    )
    result = await db.execute(stmt)

    by_day = {
        row.day: {
            "date": str(row.day),
            "total_questions": int(row.total_questions or 0),
            "correct_questions": int(row.correct_questions or 0),
            "avg_time_seconds": round(float(row.avg_time_seconds or 0), 1),
        }
        for row in result
    }

    points: list[dict] = []
    for i in range(window_days):
        day = start_day + timedelta(days=i)
        point = by_day.get(
            day,
            {
                "date": str(day),
                "total_questions": 0,
                "correct_questions": 0,
                "avg_time_seconds": 0.0,
            },
        )
        total = point["total_questions"]
        correct = point["correct_questions"]
        point["accuracy"] = round((correct / total) * 100, 1) if total > 0 else 0.0
        points.append(point)
    return points
