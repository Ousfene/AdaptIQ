"""
routers/onboarding.py
Onboarding endpoints — same pattern as routers/custom.py and routers/challenge.py.

Covers:
    - GET  /api/onboarding/status            → Current onboarding flags
    - POST /api/onboarding/survey            → Save onboarding answers
    - POST /api/onboarding/skip              → Skip onboarding flow
    - POST /api/onboarding/mark-tour-seen    → Mark guided tour as completed

Internal helpers:
    - _ensure_user_match: prevents cross-user access
    - _get_db: local DB dependency adapter
    - _parse_uuid: strict user_id validation
"""


import uuid
import logging

from fastapi import APIRouter, HTTPException, Request, Depends
from sqlalchemy import select

from dependencies import limiter

from database.onboarding_models import UserOnboardingFlags
from schemas.onboarding import (
    OnboardingStatusRequest,
    OnboardingStatusResponse,
    SurveyRequest,
    SurveyResponse,
    SkipRequest,
    SkipResponse,
    MarkTourSeenRequest,
    MarkTourSeenResponse,
)
from services.onboarding_service import (
    get_onboarding_status,
    submit_survey,
    skip_onboarding,
    mark_tour_seen,
)
from routers.auth import get_current_user, get_db

logger = logging.getLogger(__name__)

onboarding_router = APIRouter(prefix="/api/onboarding", tags=["Onboarding"])


# Ensure callers can only access onboarding data for themselves.
def _ensure_user_match(target_user_id: str, current_user_id: str) -> None:
    if str(target_user_id) != str(current_user_id):
        raise HTTPException(403, "You are not allowed to access this user data")


# ─── DB dependency ────────────────────────────────────────────────────────────

# Yield a request-scoped DB session from app state.
async def _get_db(request: Request):
    factory = getattr(request.app.state, "db_session_factory", None)
    if factory is None:
        raise HTTPException(503, "Database not available")
    async with factory() as db:
        yield db


# Parse a raw identifier into UUID and raise a clean 422 on failure.
def _parse_uuid(raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(raw))
    except (ValueError, AttributeError):
        raise HTTPException(422, f"user_id must be a valid UUID, got: {raw!r}")


# ─── GET /api/onboarding/status ───────────────────────────────────────────────

@onboarding_router.get("/status", response_model=OnboardingStatusResponse)
@limiter.limit("30/minute")
# Return current onboarding status flags for the authenticated user.
async def onboarding_status(user_id: str, request: Request, current=Depends(get_current_user)):
    """
    Returns onboarding flags for the user.
    Creates the flags row (with defaults) if it doesn't exist yet —
    so calling this on first login is sufficient to initialise onboarding.
    """
    user, _ = current
    _ensure_user_match(user_id, str(user.id))
    uid = _parse_uuid(user_id)
    async for db in _get_db(request):
        status = await get_onboarding_status(db, uid)
        return OnboardingStatusResponse(**status)


# ─── POST /api/onboarding/survey ──────────────────────────────────────────────

@onboarding_router.post("/survey", response_model=SurveyResponse)
@limiter.limit("10/minute")
# Persist onboarding survey selections and complete onboarding.
async def submit_onboarding_survey(body: SurveyRequest, request: Request, current=Depends(get_current_user)):
    """
    Saves topic self-assessments and marks onboarding as completed.
    Returns 409 if onboarding was already completed.
    """
    user, _ = current
    _ensure_user_match(body.user_id, str(user.id))
    uid = _parse_uuid(body.user_id)
    async for db in _get_db(request):
        success = await submit_survey(
            db,
            user_id              = uid,
            topics_confident     = body.topics_confident,
            topics_want_to_learn = body.topics_want_to_learn,
        )
        if not success:
            raise HTTPException(409, "Onboarding already completed")
        return SurveyResponse(success=True, redirect_to_dashboard=True)


# ─── POST /api/onboarding/skip ────────────────────────────────────────────────

@onboarding_router.post("/skip", response_model=SkipResponse)
@limiter.limit("10/minute")
# Mark onboarding complete without storing survey answers.
async def skip_onboarding_route(body: SkipRequest, request: Request, current=Depends(get_current_user)):
    """
    Marks onboarding as completed without saving topic data.
    The guided tour will still show afterward.
    """
    user, _ = current
    _ensure_user_match(body.user_id, str(user.id))
    uid = _parse_uuid(body.user_id)
    async for db in _get_db(request):
        await skip_onboarding(db, uid)
        return SkipResponse(success=True)


# ─── POST /api/onboarding/mark-tour-seen ─────────────────────────────────────

@onboarding_router.post("/mark-tour-seen", response_model=MarkTourSeenResponse)
@limiter.limit("10/minute")
# Mark the guided product tour as seen.
async def mark_tour_seen_route(body: MarkTourSeenRequest, request: Request, current=Depends(get_current_user)):
    """
    Sets tour_seen = True.
    Called when user clicks "Got it" on the last tour step, or skips the tour.
    """
    user, _ = current
    _ensure_user_match(body.user_id, str(user.id))
    uid = _parse_uuid(body.user_id)
    async for db in _get_db(request):
        await mark_tour_seen(db, uid)
        return MarkTourSeenResponse(success=True)
