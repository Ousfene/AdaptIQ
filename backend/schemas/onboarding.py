"""
pydantic_onboarding.py
Request / Response schemas for the Onboarding router.
"""
from __future__ import annotations
from typing import List
from pydantic import BaseModel, Field


# ─── Requests ─────────────────────────────────────────────────────────────────

class OnboardingStatusRequest(BaseModel):
    user_id: str  # UUID string


class SurveyRequest(BaseModel):
    user_id:              str
    topics_confident:     List[str] = Field(default_factory=list, max_length=3)
    topics_want_to_learn: List[str] = Field(default_factory=list, max_length=3)


class SkipRequest(BaseModel):
    user_id: str


class MarkTourSeenRequest(BaseModel):
    user_id: str


# ─── Responses ────────────────────────────────────────────────────────────────

class OnboardingStatusResponse(BaseModel):
    first_login:           bool
    onboarding_needed:     bool   # True if first_login=True AND onboarding_completed=False
    onboarding_completed:  bool
    tour_needed:           bool   # True if onboarding_completed=True AND tour_seen=False


class SurveyResponse(BaseModel):
    success:               bool
    redirect_to_dashboard: bool


class SkipResponse(BaseModel):
    success: bool


class MarkTourSeenResponse(BaseModel):
    success: bool
