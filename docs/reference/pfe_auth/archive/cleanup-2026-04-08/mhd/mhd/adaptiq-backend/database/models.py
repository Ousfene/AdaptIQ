"""
database/models.py — SQLAlchemy ORM models.
Added: users table so login/signup works with the backend.
"""

import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text, Index
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class User(Base):
    """
    Registered users — created on signup, looked up on login.
    Stores hashed password (never plaintext).
    """
    __tablename__ = "users"

    id           = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email        = Column(String(255), unique=True, nullable=False, index=True)
    username     = Column(String(100), unique=True, nullable=False)
    password_hash= Column(String(255), nullable=False)
    points       = Column(Integer, default=0)
    level        = Column(String(30), default="Novice")
    created_at   = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_login   = Column(DateTime, nullable=True)
    is_active    = Column(Boolean, default=True)


class UserResponse(Base):
    """One row per answer submitted. Drives IRT recalibration."""
    __tablename__ = "user_responses"

    id               = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id          = Column(PG_UUID(as_uuid=True), nullable=False, index=True)
    session_id       = Column(PG_UUID(as_uuid=True), nullable=False, index=True)
    question_id      = Column(PG_UUID(as_uuid=True), nullable=False)
    topic            = Column(String(20), nullable=False)
    difficulty_sent  = Column(Integer, nullable=False)
    answered_correct = Column(Boolean, nullable=False)
    time_taken       = Column(Integer, nullable=False)
    used_hint        = Column(Boolean, default=False)
    created_at       = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_user_responses_user_topic", "user_id", "topic"),
    )


class QuestionBank(Base):
    """Cached questions with IRT calibration params."""
    __tablename__ = "question_bank"

    id             = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_text  = Column(Text, nullable=False)
    correct_answer = Column(Text, nullable=False)
    options_json   = Column(Text, nullable=False)
    explanation    = Column(Text, nullable=False)
    topic          = Column(String(20), nullable=False, index=True)
    difficulty_irt = Column(Float, default=2.5)
    discrimination = Column(Float, default=1.0)
    usage_count    = Column(Integer, default=0)
    created_at     = Column(DateTime, default=datetime.utcnow)
    source         = Column(String(30), default="llm")

    __table_args__ = (
        Index("ix_question_bank_topic_diff", "topic", "difficulty_irt"),
    )