"""
pydantic_types.py — Pydantic models matching the React TypeScript interfaces exactly.

NOTE: Do NOT add 'from __future__ import annotations' here.
      Pydantic 2.11 + Python 3.13 needs real types, not ForwardRefs.
"""

from typing import Literal, List, Dict
from pydantic import BaseModel, Field


# ── TopicType matches TS: 'History' | 'Geography' | 'Mixed' ──────────────
TopicType = Literal["History", "Geography", "Mixed"]


# ── Matches TS interface Question ────────────────────────────────────────
class QuestionOut(BaseModel):
    id: str
    text: str
    options: List[str]
    correctAnswer: str
    explanation: str

    model_config = {"populate_by_name": True}


# ── POST /api/classic/generate-question ──────────────────────────────────
class GenerateQuestionRequest(BaseModel):
    topic: Literal["History", "Geography", "Mixed"]
    difficulty: int = Field(default=2, ge=1, le=5)
    user_id: str
    session_id: str


# ── POST /api/classic/generate-hint ──────────────────────────────────────
class GenerateHintRequest(BaseModel):
    questionText: str
    correctAnswer: str


class HintOut(BaseModel):
    hint: str


# ── POST /api/classic/submit-answer ──────────────────────────────────────
class SubmitAnswerRequest(BaseModel):
    user_id: str
    session_id: str
    question_id: str
    selected_answer: str
    time_taken: int
    used_hint: bool


class SubmitAnswerOut(BaseModel):
    success: bool = True
    updated_difficulty: int


# ── Internal session model ────────────────────────────────────────────────
class QuizSessionState(BaseModel):
    topic: Literal["History", "Geography", "Mixed"]
    questions: List[QuestionOut] = []
    currentIndex: int = 0
    score: int = 0
    pointsEarned: int = 0
    hintsUsed: int = 0
    startTime: int = 0
    isFinished: bool = False
    current_difficulty: int = 2


# ── Health check ─────────────────────────────────────────────────────────
class HealthOut(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
    services: Dict[str, str] = {}


# Force Pydantic to fully resolve all models now (not lazily)
QuestionOut.model_rebuild()
GenerateQuestionRequest.model_rebuild()
GenerateHintRequest.model_rebuild()
HintOut.model_rebuild()
SubmitAnswerRequest.model_rebuild()
SubmitAnswerOut.model_rebuild()
QuizSessionState.model_rebuild()
HealthOut.model_rebuild()