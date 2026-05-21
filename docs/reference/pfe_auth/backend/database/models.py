"""
database/models.py — SQLAlchemy ORM models.
Added: users table so login/signup works with the backend.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text, Index, ForeignKey
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, ARRAY
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def utc_now_naive() -> datetime:
    # Keep UTC semantics without relying on deprecated datetime.utcnow().
    return datetime.now(timezone.utc).replace(tzinfo=None)


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
    elo_global   = Column(Float, default=0.0, nullable=False)  # Challenge room ELO rating
    created_at   = Column(DateTime, default=utc_now_naive, nullable=False)
    last_login   = Column(DateTime, nullable=True)
    is_active    = Column(Boolean, default=True)
    is_admin     = Column(Boolean, default=False)


class UserResponse(Base):
    """One row per answer submitted. Drives IRT recalibration."""
    __tablename__ = "user_responses"

    id               = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id          = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id       = Column(PG_UUID(as_uuid=True), nullable=False, index=True)
    question_id      = Column(PG_UUID(as_uuid=True), ForeignKey("question_bank.id", ondelete="CASCADE"), nullable=False, index=True)
    topic            = Column(String(20), nullable=False)
    difficulty_sent  = Column(Integer, nullable=False)
    answered_correct = Column(Boolean, nullable=False)
    time_taken       = Column(Integer, nullable=False)
    used_hint        = Column(Boolean, default=False)
    created_at       = Column(DateTime, default=utc_now_naive, nullable=False, index=True)

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
    hint           = Column(Text, nullable=True)  # Cached hint (avoid LLM re-generation)
    topic          = Column(String(20), nullable=False, index=True)
    difficulty_irt = Column(Float, default=2.5)
    discrimination = Column(Float, default=1.0)
    usage_count    = Column(Integer, default=0)
    times_seen     = Column(Integer, default=0)  # How many times served across all users
    created_at     = Column(DateTime, default=utc_now_naive)
    last_served_at = Column(DateTime, nullable=True, index=True)
    source         = Column(String(30), default="llm")
    primary_concept_id = Column(PG_UUID(as_uuid=True), ForeignKey("concepts.id", ondelete="SET NULL"), nullable=True, index=True)

    __table_args__ = (
        Index("ix_question_bank_topic_diff", "topic", "difficulty_irt"),
    )


class Concept(Base):
    """Knowledge domain concepts (e.g., Egyptian Empire, Roman History)."""
    __tablename__ = "concepts"

    id           = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name         = Column(String(255), unique=True, nullable=False, index=True)
    topic        = Column(String(50), nullable=False, index=True)
    description  = Column(Text, nullable=True)
    created_at   = Column(DateTime, default=utc_now_naive, nullable=False)


class QuestionConcept(Base):
    """Many-to-many: links questions to the concepts they test."""
    __tablename__ = "question_concepts"

    id           = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_id  = Column(PG_UUID(as_uuid=True), ForeignKey("question_bank.id", ondelete="CASCADE"), nullable=False, index=True)
    concept_id   = Column(PG_UUID(as_uuid=True), ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False, index=True)
    is_primary   = Column(Boolean, default=False, nullable=False)
    created_at   = Column(DateTime, default=utc_now_naive, nullable=False)

    __table_args__ = (
        Index("ix_question_concepts_question", "question_id"),
        Index("ix_question_concepts_concept", "concept_id"),
    )


class UserConceptTheta(Base):
    """Per-user, per-concept IRT ability tracking."""
    __tablename__ = "user_concept_theta"

    id             = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id        = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    concept_id     = Column(PG_UUID(as_uuid=True), ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False, index=True)
    theta          = Column(Float, default=0.0, nullable=False)  # [-3, 3] ability
    theta_variance = Column(Float, default=1.0, nullable=False)  # Uncertainty
    response_count = Column(Integer, default=0, nullable=False)  # How many answers calibrated this
    last_updated   = Column(DateTime, default=utc_now_naive, nullable=False)
    created_at     = Column(DateTime, default=utc_now_naive, nullable=False)
    first_seen_at  = Column(DateTime, nullable=True)  # When user first encountered this concept
    exposure_count = Column(Integer, default=0, nullable=False)  # How many times concept was shown
    # Additional columns to match actual database schema
    mastery_level  = Column(String(20), nullable=False, default="BEGINNER")  # BEGINNER, LEARNING, PROFICIENT, ADVANCED
    last_played_at = Column(DateTime, nullable=False, default=utc_now_naive)  # When concept was last practiced
    updated_at     = Column(DateTime, nullable=False, default=utc_now_naive)  # Last schema update time
    concept_state  = Column(String(20), nullable=False, default="EXPLORING")  # EXPLORING, LEARNING, MASTERED

    __table_args__ = (
        Index("ix_user_concept_theta_user", "user_id"),
        Index("ix_user_concept_theta_concept", "concept_id"),
        Index("ix_user_concept_theta_updated", "last_updated"),
    )


class UserConceptRepeatQueue(Base):
    """Queue for spaced repetition — concepts user got wrong need revisiting."""
    __tablename__ = "user_concept_repeat_queue"

    id                = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id           = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    concept_id        = Column(PG_UUID(as_uuid=True), ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id       = Column(PG_UUID(as_uuid=True), ForeignKey("question_bank.id", ondelete="CASCADE"), nullable=False, index=True)
    repeat_probability= Column(Float, default=0.5, nullable=False)  # Priority weight
    due_after_session = Column(Integer, default=0, nullable=False)  # Session count when this should be shown
    created_at        = Column(DateTime, default=utc_now_naive, nullable=False)

    __table_args__ = (
        Index("ix_repeat_queue_user_due", "user_id", "due_after_session"),
    )


class ClassicSession(Base):
    """Tracks a classic room quiz session."""
    __tablename__ = "classic_sessions"

    id                = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id           = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    topic             = Column(String(20), nullable=False)  # geography, history, mix
    questions_answered= Column(Integer, default=0, nullable=False)
    correct_count     = Column(Integer, default=0, nullable=False)
    created_at        = Column(DateTime, default=utc_now_naive, nullable=False)
    ended_at          = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_classic_sessions_user", "user_id"),
    )


class ChallengeRank(Base):
    """Rank definitions for Challenge Room (Bronze → Diamond)."""
    __tablename__ = "challenge_ranks"

    id            = Column(Integer, primary_key=True)  # 1=Bronze, 2=Silver, etc.
    name          = Column(String(50), unique=True, nullable=False)
    min_elo       = Column(Float, default=0.0, nullable=False)
    n_options     = Column(Integer, default=4, nullable=False)  # 2 for Bronze, 4 for others
    has_timer     = Column(Boolean, default=False, nullable=False)
    timer_seconds = Column(Integer, nullable=True)  # null if no timer
    # New fields from MHD merge
    levels_allowed= Column(ARRAY(Integer), default=[1, 2, 3, 4, 5], nullable=False)  # Which levels can be played at this rank
    points_to_advance = Column(Integer, default=1000, nullable=False)  # Points needed to rank up


class UserChallengeRank(Base):
    """User's current rank and challenge stats in Challenge Room."""
    __tablename__ = "user_challenge_rank"

    user_id                = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    current_rank_id        = Column(Integer, ForeignKey("challenge_ranks.id"), nullable=False, default=1)
    wins                   = Column(Integer, default=0, nullable=False)
    losses                 = Column(Integer, default=0, nullable=False)
    skip_attempts_remaining= Column(Integer, default=3, nullable=False)
    last_skip_at           = Column(DateTime, nullable=True)
    # New fields from MHD merge
    rank_points            = Column(Integer, default=0, nullable=False)  # Points toward next rank
    highest_streak         = Column(Integer, default=0, nullable=False)  # Longest correct streak ever
    total_sessions         = Column(Integer, default=0, nullable=False)  # Total challenge sessions played


class ChallengeMatch(Base):
    """Records each challenge match attempt."""
    __tablename__ = "challenge_matches"

    id                = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id           = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    rank_id           = Column(Integer, ForeignKey("challenge_ranks.id"), nullable=False)
    questions_answered= Column(Integer, default=0, nullable=False)
    score             = Column(Float, default=0.0, nullable=False)  # Percentage correct
    time_taken        = Column(Integer, default=0, nullable=False)  # Total seconds
    created_at        = Column(DateTime, default=utc_now_naive, nullable=False)
    result            = Column(String(20), default="incomplete", nullable=False)  # win, loss, draw, incomplete
    is_skip_attempt   = Column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index("ix_challenge_matches_user", "user_id"),
        Index("ix_challenge_matches_result", "result"),
    )


class ChallengeSession(Base):
    """
    Tracks a challenge room session with dynamic level changes (MHD merge).
    
    Unlike ChallengeMatch which tracks overall results, this tracks
    session state including streaks, level changes, and per-question points.
    """
    __tablename__ = "challenge_sessions"

    id              = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id         = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    match_id        = Column(PG_UUID(as_uuid=True), ForeignKey("challenge_matches.id", ondelete="CASCADE"), nullable=True, index=True)
    topic           = Column(String(30), nullable=False)
    starting_level  = Column(Integer, nullable=False, default=1)  # Level when session started
    current_level   = Column(Integer, nullable=False, default=1)  # Current dynamic level (1-5)
    rank_points     = Column(Integer, default=0, nullable=False)  # Points earned this session
    streak_correct  = Column(Integer, default=0, nullable=False)  # Current consecutive correct
    streak_wrong    = Column(Integer, default=0, nullable=False)  # Current consecutive wrong
    highest_streak  = Column(Integer, default=0, nullable=False)  # Best streak this session
    total_questions = Column(Integer, default=0, nullable=False)
    correct_answers = Column(Integer, default=0, nullable=False)
    started_at      = Column(DateTime, default=utc_now_naive, nullable=False)
    ended_at        = Column(DateTime, nullable=True)
    is_completed    = Column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index("ix_challenge_sessions_user", "user_id"),
        Index("ix_challenge_sessions_match", "match_id"),
    )


class ChallengeAnswer(Base):
    """
    Tracks each answer in a challenge session (MHD merge).
    
    Records level at time of answer, points change, and timing for
    detailed session analytics and streak tracking.
    """
    __tablename__ = "challenge_answers"

    id              = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id      = Column(PG_UUID(as_uuid=True), ForeignKey("challenge_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id     = Column(PG_UUID(as_uuid=True), ForeignKey("question_bank.id", ondelete="SET NULL"), nullable=True, index=True)
    chosen_answer   = Column(Text, nullable=False)
    is_correct      = Column(Boolean, nullable=False)
    points_change   = Column(Integer, nullable=False)  # Can be negative
    level_at_answer = Column(Integer, nullable=False)  # Level when this question was answered
    time_taken      = Column(Float, nullable=True)  # Seconds to answer
    created_at      = Column(DateTime, default=utc_now_naive, nullable=False)

    __table_args__ = (
        Index("ix_challenge_answers_session", "session_id"),
    )


class Fact(Base):
    """
    Core fact pool for Custom Room topics.

    Each fact represents a small piece of knowledge (e.g., a battle, a leader, a capital).
    Facts are used to dynamically generate MCQs at runtime, avoiding need for 1000 fixed questions.

    Example facts:
    - History - WW2: "Battle of Stalingrad occurred 1942-1943"
    - Geography - France: "Capital is Paris"
    """
    __tablename__ = "facts"

    id                       = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic                    = Column(String(255), nullable=False, index=True)  # e.g., "History - World War II"
    content                  = Column(Text, nullable=False)  # The raw fact (e.g., "Battle of Stalingrad 1942-1943")
    difficulty_hint          = Column(String(20), nullable=True)  # "easy", "medium", "hard" (optional)
    total_questions_generated= Column(Integer, default=0)  # Analytics: how many questions generated from this fact
    created_at               = Column(DateTime, default=utc_now_naive, nullable=False)

    __table_args__ = (
        Index("ix_facts_topic", "topic"),
        Index("ix_facts_topic_difficulty", "topic", "difficulty_hint"),
    )


class UserTopicMastery(Base):
    """
    Tracks user progress toward mastery of each Custom Room topic.

    Mastery = percentage of facts user has answered correctly at least once.
    Progress percentage = (mastered_facts_count / total_facts_count) * 100

    Each user can track independent progress for multiple topics.
    """
    __tablename__ = "user_topic_mastery"

    user_id                = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    topic                  = Column(String(255), primary_key=True)  # e.g., "History - World War II"
    mastered_facts_count   = Column(Integer, default=0)  # Facts user has answered correctly
    total_facts_count      = Column(Integer, default=0)  # Total facts available in this topic
    completion_percentage  = Column(Float, default=0.0)  # (mastered / total) * 100
    last_session_at        = Column(DateTime, nullable=True)
    created_at             = Column(DateTime, default=utc_now_naive, nullable=False)

    __table_args__ = (
        Index("ix_user_topic_mastery_user", "user_id"),
        Index("ix_user_topic_mastery_completion", "completion_percentage"),
    )


class CustomSession(Base):
    """
    Tracks Custom Room session metadata for history and analytics.

    Records when a user studied a particular topic, how many questions they answered,
    and their final progress percentage for that session.
    """
    __tablename__ = "custom_sessions"

    id                          = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id                     = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    topic                       = Column(String(255), nullable=False)  # e.g., "History - World War II"
    started_at                  = Column(DateTime, default=utc_now_naive, nullable=False)
    ended_at                    = Column(DateTime, nullable=True)
    total_questions             = Column(Integer, default=0)
    correct_count               = Column(Integer, default=0)
    completion_percentage_after = Column(Float, nullable=True)  # Final % after this session

    __table_args__ = (
        Index("ix_custom_sessions_user_topic", "user_id", "topic"),
        Index("ix_custom_sessions_started", "started_at"),
    )


class QuestionFact(Base):
    """
    Links generated questions to their underlying facts.

    Allows tracing back which fact was used to generate a question,
    enabling analytics on fact reuse and difficulty calibration.
    """
    __tablename__ = "question_facts"

    id          = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_id = Column(PG_UUID(as_uuid=True), ForeignKey("question_bank.id", ondelete="CASCADE"), nullable=False)
    fact_id     = Column(PG_UUID(as_uuid=True), ForeignKey("facts.id", ondelete="CASCADE"), nullable=False, index=True)

    __table_args__ = (
        Index("ix_question_facts_question", "question_id"),
        Index("ix_question_facts_fact", "fact_id"),
    )