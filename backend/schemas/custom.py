"""
pydantic_custom.py
Request / Response schemas for the Custom Room router.

FIX: user_id is str (UUID string) — matches users.id UUID PK.
"""
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field


class StartSessionRequest(BaseModel):
    user_id: str   # UUID string, e.g. "550e8400-e29b-41d4-a716-446655440000"
    topic:   str   = Field(..., json_schema_extra={"example": "History - World War II"})
    concept_id: Optional[str] = None


class GenerateQuestionRequest(BaseModel):
    session_id: str
    topic:      str
    concept_id: Optional[str] = None


class SubmitAnswerRequest(BaseModel):
    session_id:    str
    question_id:   str
    answer:        str
    used_hint:     bool = False
    # Deprecated client fields (ignored by server for integrity).
    correct_answer: Optional[str] = None
    explanation:   Optional[str] = None


class TopicOut(BaseModel):
    type:        str
    slug:        str
    name:        str
    description: str
    total_facts: int


class TopicsResponse(BaseModel):
    topics: List[TopicOut]


class StartSessionResponse(BaseModel):
    session_id:               str
    topic:                    str
    concept_id:               Optional[str] = None
    progress_percentage:      float
    total_questions_estimate: int


class CustomQuestionResponse(BaseModel):
    id:             str
    text:           str
    options:        List[str]
    explanation:    str
    fact_id:        Optional[str] = None
    concept_id:     Optional[str] = None


class SubmitAnswerResponse(BaseModel):
    is_correct:                   bool
    correct_answer:               str
    explanation:                  str
    new_progress_percentage:      float
    total_questions_this_session: int


class EndSessionResponse(BaseModel):
    session_id:                   str
    topic:                        str
    questions_answered:           int
    correct_count:                int
    completion_percentage_after:  float


# ─── POST /api/custom/generate-hint ──────────────────────────────────────

class GenerateCustomHintRequest(BaseModel):
    question_id: str
    question_text: Optional[str] = None
    # Deprecated client field (ignored by server).
    correct_answer: Optional[str] = None


class HintOut(BaseModel):
    hint: str


class ConceptOut(BaseModel):
    id: str
    name: str
    topic: str
    description: Optional[str] = None


class ConceptsResponse(BaseModel):
    concepts: List[ConceptOut]


class ConceptMasteryItem(BaseModel):
    concept_id: str
    concept: str
    topic: str
    theta: float
    response_count: int
    mastery_level: str
    exposure_count: int


class ConceptMasteryResponse(BaseModel):
    user_id: str
    concepts: List[ConceptMasteryItem]