"""
pydantic_visual.py
Request / Response schemas for the VisualRoom router.

Designed to match exactly what the frontend TypeScript interfaces expect.
The frontend files show these types are needed:
  - VisualQuestion (returned by fetchNextVisualQuestion)
  - Submit response (returned by submitVisualAnswer)
"""

from __future__ import annotations
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


# ─── Outbound: question served to frontend ────────────────────────────────────

class VisualQuestionOut(BaseModel):
    """
    Matches the frontend VisualQuestion type.
    NOTE: correctAnswer is intentionally NOT included.
    The frontend must NOT know the correct answer before submission.
    Hints are fetched via a separate endpoint using question_id only.
    """
    id:           str
    image_url:    str
    text:         str           # the question string
    options:      List[str]     # empty list for Level 5 (text input)
    topic:        str
    level:        int
    question_type:str           # "M" or "T"
    options_count:int
    shape_svg:    Optional[str] = None   # SVG silhouette, None for history rows
    show_flag:    bool = True            # True → frontend shows flag image
    show_shape:   bool = False
    model_config = {"populate_by_name": True}


# ─── Inbound: start session ───────────────────────────────────────────────────

class StartVisualSessionRequest(BaseModel):
    user_id: str
    topic:   Literal["History", "Geography", "Mixed"]
    level:   int = Field(ge=1, le=5)


class StartVisualSessionResponse(BaseModel):
    session_id:      str
    topic:           str
    level:           int
    total_questions: int


# ─── Inbound: submit answer ───────────────────────────────────────────────────

class SubmitVisualAnswerRequest(BaseModel):
    session_id:    str
    question_id:   str
    user_id:       str
    chosen_answer: str
    user_time_ms:  Optional[int] = None


class SubmitVisualAnswerResponse(BaseModel):
    is_correct:     bool
    correct_answer: str
    explanation:    str
    # next_question is null when the session is complete
    next_question:  Optional[VisualQuestionOut] = None


# ─── Hint ─────────────────────────────────────────────────────────────────────

class VisualHintResponse(BaseModel):
    hint: str


# ─── Explanation (standalone fetch) ──────────────────────────────────────────

class VisualExplanationResponse(BaseModel):
    question_id: str
    explanation: str


# Rebuild all
VisualQuestionOut.model_rebuild()
StartVisualSessionRequest.model_rebuild()
StartVisualSessionResponse.model_rebuild()
SubmitVisualAnswerRequest.model_rebuild()
SubmitVisualAnswerResponse.model_rebuild()
VisualHintResponse.model_rebuild()
VisualExplanationResponse.model_rebuild()
