"""
database/challenge_models.py — SQLAlchemy ORM models for Challenge Room.
"""

import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from database.models import Base


class ChallengeSession(Base):
    __tablename__ = "challenge_sessions"

    id              = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id         = Column(PG_UUID(as_uuid=True), nullable=False)
    topic           = Column(String(30), nullable=False)
    starting_level  = Column(Integer, nullable=False)
    current_level   = Column(Integer, nullable=False)
    rank_points     = Column(Integer, default=0)
    streak_correct  = Column(Integer, default=0)
    streak_wrong    = Column(Integer, default=0)
    total_questions = Column(Integer, default=0)
    correct_answers = Column(Integer, default=0)
    started_at      = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at        = Column(DateTime, nullable=True)
    is_completed    = Column(Boolean, default=False)


class ChallengeAnswer(Base):
    __tablename__ = "challenge_answers"

    id              = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id      = Column(PG_UUID(as_uuid=True), nullable=False)
    question_id     = Column(PG_UUID(as_uuid=True), nullable=False)
    chosen_answer   = Column(Text, nullable=False)
    is_correct      = Column(Boolean, nullable=False)
    points_change   = Column(Integer, nullable=False)
    level_at_answer = Column(Integer, nullable=False)
    time_taken      = Column(Float, nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow, nullable=False)


class ChallengeRanking(Base):
    __tablename__ = "challenge_ranking"

    user_id         = Column(PG_UUID(as_uuid=True), primary_key=True)
    current_rank    = Column(String(1), nullable=False, default="E")
    rank_points     = Column(Integer, nullable=False, default=0)
    total_sessions  = Column(Integer, default=0)
    total_questions = Column(Integer, default=0)
    highest_streak  = Column(Integer, default=0)
    updated_at      = Column(DateTime, default=datetime.utcnow, nullable=False)