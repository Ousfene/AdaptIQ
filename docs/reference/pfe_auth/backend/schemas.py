from typing import Dict, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


TopicType = Literal["history", "geography", "mix"]


def _normalize_topic(value: str) -> str:
    topic = value.strip().lower()
    if topic not in {"history", "geography", "mix"}:
        raise ValueError("Topic must be one of: history, geography, mix")
    return topic


class UserResponse(BaseModel):
    id: UUID
    email: str
    username: str

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    user: UserResponse
    access_token: str
    token_type: str = "bearer"


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_.-]+$")
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        if not any(c.islower() for c in value):
            raise ValueError("Password must include at least one lowercase letter")
        if not any(c.isupper() for c in value):
            raise ValueError("Password must include at least one uppercase letter")
        if not any(c.isdigit() for c in value):
            raise ValueError("Password must include at least one digit")
        if not any(c in "!@#$%^&*()-_=+[]{};:,.?/" for c in value):
            raise ValueError("Password must include at least one special character")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=8, pattern=r"^\d+$")
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password_strength(cls, value: str) -> str:
        if not any(c.islower() for c in value):
            raise ValueError("Password must include at least one lowercase letter")
        if not any(c.isupper() for c in value):
            raise ValueError("Password must include at least one uppercase letter")
        if not any(c.isdigit() for c in value):
            raise ValueError("Password must include at least one digit")
        if not any(c in "!@#$%^&*()-_=+[]{};:,.?/" for c in value):
            raise ValueError("Password must include at least one special character")
        return value


class OTPResponse(BaseModel):
    message: str
    email: str
    purpose: str


class MessageResponse(BaseModel):
    message: str


class QuestionOut(BaseModel):
    """Legacy V1 question response."""
    id: UUID
    text: str
    options: list[str]
    correctAnswer: str | None = None
    explanation: str  # Shown after answer submission
    locked: bool = False  # NEW: False = UI can accept answers, True = UI locked

    model_config = {"populate_by_name": True, "from_attributes": True}


class GenerateQuestionRequest(BaseModel):
    topic: str
    difficulty: int = Field(default=2, ge=1, le=5)
    user_id: UUID
    session_id: UUID

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, value: str) -> str:
        return _normalize_topic(value)


class GenerateHintRequest(BaseModel):
    """Hint request. Supports secure session-based and legacy compatibility modes."""
    session_id: UUID | None = None
    questionText: str
    correctAnswer: str | None = None


class HintOut(BaseModel):
    hint: str


class SubmitAnswerRequest(BaseModel):
    user_id: UUID
    session_id: UUID
    question_id: UUID
    selected_answer: str = Field(..., max_length=1000)
    time_taken: Optional[int] = Field(None, ge=0, le=3600000)  # OPTIONAL: Server calculates if not provided
    used_hint: bool = False


class SubmitAnswerOut(BaseModel):
    success: bool = True
    updated_difficulty: int
    correct: bool | None = None
    correct_answer: str | None = None
    locked: bool = True  # NEW: True = UI locked until next question ready, False = can submit again


class QuizSessionState(BaseModel):
    topic: TopicType
    questions: list[QuestionOut] = Field(default_factory=list)
    currentIndex: int = 0
    score: int = 0
    pointsEarned: int = 0
    hintsUsed: int = 0
    startTime: int = 0
    isFinished: bool = False
    current_difficulty: int = 2


class HealthOut(BaseModel):
    status: str = "ok"
    version: str = "1.1.0"
    services: Dict[str, str] = Field(default_factory=dict)


class UserStatsOut(BaseModel):
    """Stats returned by GET /api/auth/stats for the Dashboard."""
    id: str
    points: int
    level: str
    total_questions: int
    correct_questions: int
    global_accuracy: float
    daily_questions: int
    daily_correct: int
    daily_accuracy: float
    learning_time_minutes: int


class TopicStatsOut(BaseModel):
    topic: TopicType
    total_questions: int
    correct_questions: int
    accuracy: float
    hints_used: int
    avg_time_seconds: float


class TopicBreakdownOut(BaseModel):
    topics: list[TopicStatsOut]


class DailyTrendPointOut(BaseModel):
    date: str
    total_questions: int
    correct_questions: int
    accuracy: float
    avg_time_seconds: float


class DailyTrendOut(BaseModel):
    days: int
    points: list[DailyTrendPointOut]


class RedisOpsOut(BaseModel):
    status: str
    active_sessions: int
    session_ttl_buckets: Dict[str, int]
    otp_keys: int
    rate_limit_keys: int
    revoked_token_keys: int


class ConceptMasteryItemOut(BaseModel):
    """Individual concept mastery record."""
    concept: str
    theta: float
    level: Literal["Beginner", "Intermediate", "Advanced"]
    responses: int
    lastUpdated: str | None


class ConceptMasteryOut(BaseModel):
    """Per-topic concept mastery breakdown."""
    concepts: Dict[str, list[ConceptMasteryItemOut]]


# ────────────────────────────────────────────────────────────────────────────
# Classic Room V2 (Session-based) Schemas
# ────────────────────────────────────────────────────────────────────────────

class ClassicStartRequest(BaseModel):
    """Request to start a new classic room session."""
    topic: str

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, value: str) -> str:
        return _normalize_topic(value)


class ClassicQuestionOut(BaseModel):
    """Question response for classic room (no correct answer sent to client)."""
    id: str
    text: str
    options: list[str]
    topic: str
    difficulty: int


class SessionStatsOut(BaseModel):
    """Session statistics."""
    questions_answered: int
    correct_count: int


class ClassicStartResponse(BaseModel):
    """Response from starting a classic session."""
    session_id: str
    first_question: ClassicQuestionOut | None
    session_stats: SessionStatsOut


class ClassicAnswerRequest(BaseModel):
    """Request to submit an answer in classic room."""
    question_id: str
    selected_index: int = Field(..., ge=-1, le=5)  # -1 = timeout, 0-1 for Bronze, 0-3 for others
    time_taken_seconds: Optional[int] = Field(None, ge=0, le=3600)  # OPTIONAL: Server calculates if not provided
    used_hint: bool = False


class ThetaChangeOut(BaseModel):
    """Theta change for a concept after an answer."""
    concept_id: str
    theta_before: float
    theta_after: float


class ClassicAnswerResponse(BaseModel):
    """Response after submitting an answer."""
    correct: bool
    correct_index: int
    explanation: str
    theta_change: float
    next_question: ClassicQuestionOut | None
    session_stats: SessionStatsOut
    session_ended: bool


class ClassicHintRequest(BaseModel):
    """Request for a hint."""
    question_id: str


class ClassicHintResponse(BaseModel):
    """Hint response."""
    hint: str


class ConceptThetaProgressOut(BaseModel):
    """Theta progress for a concept during a session."""
    concept: str
    theta_start: float
    theta_now: float


class ClassicMetricsResponse(BaseModel):
    """Session metrics response."""
    accuracy: float
    theta_progress: list[ConceptThetaProgressOut]
    adaptivity_score: float
    total_questions: int
    correct_count: int
    topic: str


# ────────────────────────────────────────────────────────────────────────────
# Challenge Room Schemas
# ────────────────────────────────────────────────────────────────────────────

class ChallengeRankOut(BaseModel):
    """Challenge rank info."""
    id: int
    name: str
    n_options: int
    has_timer: bool
    timer_seconds: int | None


class ChallengeStatusResponse(BaseModel):
    """User's challenge room status."""
    current_rank: ChallengeRankOut
    can_skip_up: bool
    skip_attempts_remaining: int
    wins: int
    losses: int
    classic_games_played: int


class ChallengeStartRequest(BaseModel):
    """Request to start a challenge match."""
    rank_id: int
    is_skip_attempt: bool = False


class ChallengeStartResponse(BaseModel):
    """Response from starting a challenge match."""
    match_id: str
    rank: ChallengeRankOut
    first_question: ClassicQuestionOut


class ChallengeAnswerRequest(BaseModel):
    """Request to submit an answer in challenge mode."""
    question_id: str
    selected_index: int = Field(..., ge=-1, le=5)  # -1 = timeout, 0-1 for Bronze, 0-3 for others
    time_taken_seconds: Optional[int] = Field(None, ge=0, le=3600)  # OPTIONAL: Server calculates if not provided


class ChallengeAnswerResponse(BaseModel):
    """Response after submitting a challenge answer."""
    correct: bool
    correct_index: int  # Reveal correct answer after submission for learning
    explanation: str    # Explanation for the answer
    score_so_far: float
    questions_remaining: int
    next_question: ClassicQuestionOut | None


class QuestionReviewItem(BaseModel):
    """Single question review for end-of-match summary."""
    question_text: str
    options: list[str]
    user_answer_index: int
    correct_answer_index: int
    was_correct: bool
    explanation: str


class ChallengeEndResponse(BaseModel):
    """Response when challenge match ends."""
    result: Literal["win", "loss"]
    score: float
    rank_changed: bool
    new_rank: ChallengeRankOut | None
    skip_result: Literal["promoted", "failed"] | None
    questions_review: list[QuestionReviewItem]  # All questions with answers for review


# ────────────────────────────────────────────────────────────────────────────
# Challenge Room V2 Schemas (MHD merge - dynamic levels & streaks)
# ────────────────────────────────────────────────────────────────────────────

class ChallengeStatusResponseV2(BaseModel):
    """Enhanced challenge status with points and streak info."""
    current_rank: ChallengeRankOut
    can_skip_up: bool
    skip_attempts_remaining: int
    wins: int
    losses: int
    classic_games_played: int
    # New V2 fields
    rank_points: int = 0  # Total points toward next rank
    highest_streak: int = 0  # Best ever correct streak
    total_sessions: int = 0  # Total challenge sessions played
    available_levels: list[int] = []  # Which levels this rank can access


class ChallengeStartRequestV2(BaseModel):
    """Request to start a challenge match with level selection."""
    topic: str = Field(..., pattern=r"^(History|Geography|Mixed)$")
    starting_level: int = Field(1, ge=1, le=5)  # Optional: defaults to rank's lowest


class ChallengeStartResponseV2(BaseModel):
    """Enhanced response from starting a challenge match."""
    match_id: str
    session_id: str  # New: tracks dynamic session state
    current_level: int
    rank_points: int  # Session points so far (starts at 0)
    available_levels: list[int]  # Levels this rank can access
    current_rank: ChallengeRankOut
    topic: str
    first_question: ClassicQuestionOut


class LevelChangeInfo(BaseModel):
    """Info about a streak-triggered level change."""
    direction: Literal["up", "down"]
    reason: str
    old_level: int
    new_level: int


class ChallengeAnswerResponseV2(BaseModel):
    """Enhanced response with dynamic level and streak info."""
    correct: bool
    correct_index: int
    explanation: str
    # V2 additions
    points_change: int  # Points gained/lost this question
    new_rank_points: int  # Total session points after this answer
    new_level: int  # Current level (may have changed)
    streak_correct: int  # Current consecutive correct
    streak_wrong: int  # Current consecutive wrong
    level_change: LevelChangeInfo | None  # If streak triggered a level change
    # Standard fields
    questions_remaining: int
    next_question: ClassicQuestionOut | None
    match_ended: bool = False


class ChallengeEndResponseV2(BaseModel):
    """Enhanced end-of-match response with detailed stats."""
    result: Literal["win", "loss"]
    score: float
    rank_changed: bool
    new_rank: ChallengeRankOut | None
    skip_result: Literal["promoted", "failed"] | None
    questions_review: list[QuestionReviewItem]
    # V2 additions
    session_points: int  # Points earned this session
    total_rank_points: int  # New total rank points
    highest_streak: int  # Best streak this session
    level_changes_count: int  # How many times level changed


# ────────────────────────────────────────────────────────────────────────────
# Challenge Room V2 Additional Schemas (MHD-style endpoints)
# ────────────────────────────────────────────────────────────────────────────

class ChallengeGenerateQuestionRequest(BaseModel):
    """Request to generate a challenge question (MHD-style separate endpoint)."""
    session_id: str
    topic: str = Field(..., pattern=r"^(History|Geography|Mixed)$")
    level: int = Field(..., ge=1, le=5)


class ChallengeQuestionOut(BaseModel):
    """Challenge question with level-specific info (MHD-style)."""
    id: str
    text: str
    options: list[str]
    correctAnswer: str  # Exposed for MHD flow (stored in Redis, verified server-side)
    explanation: str
    level: int
    points_value: int  # Points if answered correctly at this level
    is_free_text: bool = False


class ChallengeSubmitAnswerRequest(BaseModel):
    """Submit answer by string (MHD-style, not index)."""
    session_id: str
    question_id: str
    answer: str  # The actual answer string, not index
    time_taken: Optional[float] = None


class ForceLevelChange(BaseModel):
    """Level change triggered by streak."""
    direction: Literal["up", "down"]
    reason: str


class ChallengeSubmitAnswerResponse(BaseModel):
    """Response after submitting challenge answer (MHD-style)."""
    is_correct: bool
    points_change: int  # Signed value (+3 or -1, etc.)
    new_rank_points: int  # Session running total
    new_level: int
    streak_correct: int
    streak_wrong: int
    force_level_change: ForceLevelChange | None = None


class ChallengeSessionOut(BaseModel):
    """Current session state (MHD-style)."""
    session_id: str
    user_id: str
    topic: str
    starting_level: int
    current_level: int
    rank_points: int
    streak_correct: int
    streak_wrong: int
    total_questions: int
    correct_answers: int
    is_completed: bool


class ChallengeEndSessionResponse(BaseModel):
    """End session response (MHD-style)."""
    session_id: str
    total_questions: int
    correct_answers: int
    total_points_earned: int
    new_rank: str  # Bronze/Silver/Gold/Platinum/Diamond
    new_rank_points: int  # Global cumulative after this session
    rank_changed: bool


# ──────────────────────────────────────────────────────────────────────────────
# CUSTOM ROOM SCHEMAS
# ──────────────────────────────────────────────────────────────────────────────


class TopicOut(BaseModel):
    """Single topic (e.g., 'World War II')."""
    name: str
    slug: str
    description: str
    total_facts: int


class TopicsListResponse(BaseModel):
    """Response for GET /topics."""
    topics: Dict[str, list[TopicOut]]  # {"History": [...], "Geography": [...]}


class CustomStartSessionRequest(BaseModel):
    """Request to start a Custom Room session."""
    topic: str  # e.g., "History - World War II"


class CustomStartSessionResponse(BaseModel):
    """Response after starting a Custom Room session."""
    session_id: str
    topic: str
    progress_percentage: float
    total_facts: int


class GenerateCustomQuestionRequest(BaseModel):
    """Request to generate a Custom Room question."""
    session_id: str
    topic: str


class GenerateCustomQuestionResponse(BaseModel):
    """Generated MCQ for Custom Room (without correct answer)."""
    id: str
    text: str
    options: list[str]
    explanation: Optional[str] = None  # null until answer submitted


class SubmitCustomAnswerRequest(BaseModel):
    """Submit answer to a Custom Room question."""
    session_id: str
    question_id: str
    answer: str


class SubmitCustomAnswerResponse(BaseModel):
    """Response after submitting answer to Custom Room question."""
    is_correct: bool
    explanation: str
    new_progress_percentage: float


class CustomSessionEndRequest(BaseModel):
    """Request to end a Custom Room session (body can be empty)."""
    pass


class CustomSessionEndResponse(BaseModel):
    """Response after ending a Custom Room session."""
    session_id: str
    topic: str
    questions_answered: int
    correct_count: int
    completion_percentage: float
    duration_seconds: int