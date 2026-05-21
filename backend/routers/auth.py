"""
routers/auth.py — Unified authentication router for AdaptIQ.

Covers:
  - POST /api/auth/signup          → Register a new user
  - POST /api/auth/login           → Login with email+password
  - GET  /api/auth/me              → Get current user profile (token-protected)
  - GET  /api/auth/profile         → Alias for /me (returns user fields directly)
  - POST /api/auth/forgot-password → Request OTP for password reset
  - POST /api/auth/reset-password  → Reset password with OTP verification
  - POST /api/auth/bootstrap-admin → Promote user to admin (dev only)

Dependencies exported for other routers:
  - get_db(request)        → yields AsyncSession from app.state
  - get_current_user(...)  → returns (User, issued_at) tuple

Internal helper groups in this module:
    - Password helpers: _hash_password, _verify_password
    - JWT helpers: _create_access_token, _build_user_out
    - OTP helpers: _save_otp, _read_otp, _bump_otp_attempts, _delete_otp
"""

import json
import logging
import os
import uuid
import hmac
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Optional, Tuple

import bcrypt
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import Integer, cast, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.email_service import send_otp_email
from config import (
    JWT_SECRET_KEY,
    JWT_ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ENVIRONMENT,
    POINTS_BASE_AWARD,
    POINTS_TIME_BONUS_DIVISOR,
    POINTS_HINT_PENALTY,
    POINTS_WRONG_PENALTY,
)
from dependencies import limiter
from database.challenge_models import ChallengeSession
from database.concept_models import ClassicSession
from database.custom_models import CustomSession
from database.models import User
from database.models import UserResponse

logger = logging.getLogger(__name__)

# Admin bootstrap key from env — empty disables the endpoint
ADMIN_BOOTSTRAP_KEY: str = os.getenv("ADMIN_BOOTSTRAP_KEY", "")

# In-memory OTP fallback when Redis is unavailable (dev only)
_otp_store: dict[str, dict] = {}


def _db_utc_now() -> datetime:
    """Return UTC time as naive datetime for TIMESTAMP WITHOUT TIME ZONE columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ═══════════════════════════════════════════════════════════════════════════
# PYDANTIC REQUEST / RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════════════════


class SignupRequest(BaseModel):
    """Registration payload — email must be unique, password ≥ 8 chars."""
    email: EmailStr
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8, max_length=72)


class LoginRequest(BaseModel):
    """Login payload — email + plaintext password."""
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    """Forgot-password payload — email to send OTP to."""
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Reset-password payload — email + OTP code + new password."""
    email: EmailStr
    code: str = Field(min_length=4, max_length=8)
    new_password: str = Field(min_length=8, max_length=128)


class BootstrapAdminRequest(BaseModel):
    """Promote a user to admin using a secret key (dev/setup only)."""
    email: EmailStr
    bootstrap_key: str = Field(min_length=8, max_length=256)


class AuthUserOut(BaseModel):
    """User fields returned in auth responses."""
    id: str
    email: str
    username: str
    points: int = 0
    level: str = "Novice"
    is_active: bool = True
    is_admin: bool = False
    created_at: datetime


class AuthResponse(BaseModel):
    """Signup/login success response — includes JWT + user profile."""
    access_token: str
    token_type: str = "bearer"
    user: AuthUserOut


class MeOut(BaseModel):
    """GET /me response — user profile + token issued_at timestamp."""
    user: AuthUserOut
    issued_at: datetime


class MessageOut(BaseModel):
    """Generic success message response."""
    message: str


class RoomProgressOut(BaseModel):
    """Per-room progress percentages for the dashboard."""
    classic: int = 0
    challenge: int = 0
    pvp: int = 0
    custom: int = 0
    visual: int = 0


class RoomLocksOut(BaseModel):
    """Per-room lock state for the dashboard."""
    classic: bool = False
    challenge: bool = False
    pvp: bool = False
    custom: bool = False
    visual: bool = False


class UserStatsOut(BaseModel):
    """Dashboard stats payload for the authenticated user."""
    id: str
    points: int
    level: str
    total_questions: int
    global_accuracy: float
    daily_questions: int
    daily_accuracy: float
    learning_time_minutes: int
    daily_points: int
    streak_days: int
    room_progress: RoomProgressOut
    room_locks: RoomLocksOut


class DailyTrendPointOut(BaseModel):
    """One day in the daily activity trend series."""
    date: str
    day: str
    count: int
    correct: int
    points: int


class DailyTrendOut(BaseModel):
    """Daily activity trend payload."""
    days: int
    points: list[DailyTrendPointOut]


# ═══════════════════════════════════════════════════════════════════════════
# PASSWORD HASHING (bcrypt — no passlib dependency)
# ═══════════════════════════════════════════════════════════════════════════


# Hash a plaintext password using bcrypt with a fixed cost factor.
def _hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt (12 rounds).
    Example: _hash_password("mySecret123") → "$2b$12$..."
    """
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


# Verify a plaintext password against a persisted bcrypt hash.
def _verify_password(password: str, password_hash: str) -> bool:
    """Compare plaintext password against bcrypt hash.
    Example: _verify_password("mySecret123", stored_hash) → True/False
    """
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except Exception as exc:
        logger.warning("Password verification error: %s", exc)
        return False


# ═══════════════════════════════════════════════════════════════════════════
# JWT TOKEN HELPERS
# ═══════════════════════════════════════════════════════════════════════════


# Build a short-lived signed access token for API authentication.
def _create_access_token(user_id: str) -> str:
    """Create a signed JWT with sub=user_id, exp=30 min, jti=random.
    Example: _create_access_token("550e8400-...") → "eyJhbGci..."
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


# Convert a database user row into the auth response shape.
def _build_user_out(user: User) -> AuthUserOut:
    """Map SQLAlchemy User row to AuthUserOut pydantic model."""
    return AuthUserOut(
        id=str(user.id),
        email=user.email,
        username=user.username,
        points=user.points or 0,
        level=user.level or "Novice",
        is_active=bool(user.is_active),
        is_admin=bool(getattr(user, "is_admin", False)),
        created_at=user.created_at,
    )


# ═══════════════════════════════════════════════════════════════════════════
# SHARED DEPENDENCIES (imported by other routers)
# ═══════════════════════════════════════════════════════════════════════════


# Provide a request-scoped async DB session from app state.
async def get_db(request: Request):
    """Yield an AsyncSession from app.state.db_session_factory.
    Used as a FastAPI dependency: db: AsyncSession = Depends(get_db)
    """
    factory = getattr(request.app.state, "db_session_factory", None)
    if not factory:
        raise HTTPException(status_code=503, detail="Database unavailable")
    async with factory() as session:
        yield session


# Return the configured Redis client when available.
async def get_redis(request: Request):
    """Return the Redis client from app state, or None if unavailable."""
    return getattr(request.app.state, "redis", None)


# Authenticate the bearer token and load the corresponding active user.
async def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Tuple[User, datetime]:
    """Extract and validate current user from Bearer token.

    Returns a (User, issued_at) tuple for compatibility with all routers.
    Raises 401 on missing/invalid token or inactive user.

    Example header: Authorization: Bearer eyJhbGci...
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        issued_at = datetime.fromtimestamp(
            int(payload.get("iat", 0)), tz=timezone.utc
        )
    except (JWTError, ValueError) as exc:
        logger.warning("Token decode failed: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid token")

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    try:
        user_uuid = uuid.UUID(str(user_id))
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = await db.get(User, user_uuid)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    logger.debug("Authenticated user=%s email=%s", str(user.id)[:8], user.email)
    return user, issued_at


# ═══════════════════════════════════════════════════════════════════════════
# OTP HELPERS (Redis with in-memory fallback)
# ═══════════════════════════════════════════════════════════════════════════


# Compute a consecutive-day activity streak ending today.
def _compute_streak_days(day_counts: dict[date, int], today: date) -> int:
    streak = 0
    cursor = today
    while day_counts.get(cursor, 0) > 0:
        streak += 1
        cursor = cursor - timedelta(days=1)
    return streak


def _response_points_delta(*, answered_correct: bool, time_taken: int, used_hint: bool) -> int:
    """Compute dashboard points for one response using Classic Room scoring rules."""
    if answered_correct:
        remaining_seconds = max(0, 30 - int(time_taken or 0))
        delta = int(POINTS_BASE_AWARD) + int(remaining_seconds // int(POINTS_TIME_BONUS_DIVISOR))
    else:
        delta = -int(POINTS_WRONG_PENALTY)

    if used_hint:
        delta -= int(POINTS_HINT_PENALTY)

    return int(delta)


# Compute progress shares from per-room activity counts.
def _compute_room_progress(
    classic_count: int,
    challenge_count: int,
    custom_count: int,
    pvp_count: int,
) -> RoomProgressOut:
    total = classic_count + challenge_count + custom_count + pvp_count
    if total <= 0:
        return RoomProgressOut()

    return RoomProgressOut(
        classic=int(round((classic_count / total) * 100)),
        challenge=int(round((challenge_count / total) * 100)),
        custom=int(round((custom_count / total) * 100)),
        pvp=int(round((pvp_count / total) * 100)),
        visual=0,
    )


# Persist a reset OTP code with a short expiration window.
async def _save_otp(redis_client, email: str, code: str) -> None:
    """Store a 6-digit OTP for password reset (TTL 5 min)."""
    key = f"otp:reset:{email}"
    payload = {"code": code, "attempts": 0}
    if redis_client is not None:
        await redis_client.set(key, json.dumps(payload), ex=300)
    else:
        _otp_store[key] = {
            "code": code,
            "attempts": 0,
            "expires_at": datetime.now(timezone.utc) + timedelta(seconds=300),
        }
    logger.info("OTP stored for email=%s", email)


# Load the current OTP payload for an email if still valid.
async def _read_otp(redis_client, email: str) -> Optional[dict]:
    """Read stored OTP, return None if expired or missing."""
    key = f"otp:reset:{email}"
    if redis_client is not None:
        data = await redis_client.get(key)
        return json.loads(data) if data else None

    cached = _otp_store.get(key)
    if not cached:
        return None
    if datetime.now(timezone.utc) > cached["expires_at"]:
        _otp_store.pop(key, None)
        return None
    return {"code": cached["code"], "attempts": cached["attempts"]}


# Increment the failed-attempt counter for a reset OTP.
async def _bump_otp_attempts(redis_client, email: str, current: dict) -> None:
    """Increment OTP attempt counter (locks out after 3 failed tries)."""
    key = f"otp:reset:{email}"
    next_payload = {
        "code": current["code"],
        "attempts": int(current.get("attempts", 0)) + 1,
    }
    if redis_client is not None:
        await redis_client.set(key, json.dumps(next_payload), ex=300)
    else:
        cached = _otp_store.get(key)
        if cached:
            cached["attempts"] = next_payload["attempts"]


# Delete an OTP after success or lockout.
async def _delete_otp(redis_client, email: str) -> None:
    """Remove OTP after successful use or max attempts."""
    key = f"otp:reset:{email}"
    if redis_client is not None:
        await redis_client.delete(key)
    _otp_store.pop(key, None)


# ═══════════════════════════════════════════════════════════════════════════
# ROUTER
# ═══════════════════════════════════════════════════════════════════════════

auth_router = APIRouter(prefix="/api/auth", tags=["Auth"])


@auth_router.post("/signup", response_model=AuthResponse)
@limiter.limit("20/minute")
# Register a brand-new user and return an access token.
async def signup(
    request: Request,
    payload: SignupRequest,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user account.

    1. Checks email/username uniqueness
    2. Hashes the password with bcrypt
    3. Creates the user row
    4. Returns JWT + user profile
    """
    logger.info("Signup attempt: email=%s username=%s", payload.email, payload.username)

    # Check email uniqueness
    existing_email = await db.scalar(
        select(User).where(User.email == payload.email.lower().strip())
    )
    if existing_email:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Check username uniqueness
    existing_username = await db.scalar(
        select(User).where(User.username == payload.username.strip())
    )
    if existing_username:
        raise HTTPException(status_code=400, detail="Username already taken")

    # Create user
    user = User(
        email=payload.email.lower().strip(),
        username=payload.username.strip(),
        password_hash=_hash_password(payload.password),
        points=0,
        level="Novice",
        created_at=_db_utc_now(),
        is_active=True,
        is_admin=False,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        details = str(getattr(exc, "orig", exc)).lower()
        if "email" in details:
            raise HTTPException(status_code=400, detail="Email already registered")
        if "username" in details:
            raise HTTPException(status_code=400, detail="Username already taken")
        raise HTTPException(status_code=409, detail="User registration failed due to duplicate data")
    await db.refresh(user)

    token = _create_access_token(str(user.id))
    logger.info("User registered: id=%s email=%s", str(user.id)[:8], user.email)

    return AuthResponse(access_token=token, user=_build_user_out(user))


@auth_router.post("/login", response_model=AuthResponse)
@limiter.limit("10/minute")
# Authenticate existing credentials and return an access token.
async def login(
    request: Request,
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate user with email + password.

    Returns JWT + user profile on success, 401 on failure.
    Updates last_login timestamp.
    """
    logger.info("Login attempt: email=%s", payload.email)

    user = await db.scalar(
        select(User).where(User.email == payload.email.lower().strip())
    )
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not _verify_password(payload.password, user.password_hash):
        logger.warning("Failed login for email=%s", payload.email)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is disabled")

    user.last_login = _db_utc_now()
    await db.commit()

    token = _create_access_token(str(user.id))
    logger.info("User logged in: id=%s email=%s", str(user.id)[:8], user.email)

    return AuthResponse(access_token=token, user=_build_user_out(user))


@auth_router.get("/me", response_model=MeOut)
# Return the authenticated user profile plus token issue time.
async def me(current=Depends(get_current_user)):
    """Get current authenticated user profile + token issued_at.

    Requires: Authorization: Bearer <token>
    Returns: {user: {...}, issued_at: "2026-..."}
    """
    user, issued_at = current
    logger.debug("Profile requested: user=%s", str(user.id)[:8])
    return MeOut(user=_build_user_out(user), issued_at=issued_at)


@auth_router.get("/profile")
# Return the authenticated user profile without wrapper metadata.
async def profile(current=Depends(get_current_user)):
    """Alias for /me — returns user fields directly (no wrapper).

    Requires: Authorization: Bearer <token>
    Returns: {id, email, username, points, level, ...}
    """
    user, _ = current
    return _build_user_out(user)


@auth_router.get("/stats", response_model=UserStatsOut)
@limiter.limit("120/minute")
# Return dynamic dashboard stats for the authenticated user.
async def stats(
    request: Request,
    current=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user, _issued_at = current
    user_id = user.id

    now = _db_utc_now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    total_questions = await db.scalar(
        select(func.count())
        .select_from(UserResponse)
        .where(UserResponse.user_id == user_id)
    ) or 0
    correct_questions = await db.scalar(
        select(func.count())
        .select_from(UserResponse)
        .where(
            UserResponse.user_id == user_id,
            UserResponse.answered_correct == True,
        )
    ) or 0

    daily_questions = await db.scalar(
        select(func.count())
        .select_from(UserResponse)
        .where(
            UserResponse.user_id == user_id,
            UserResponse.created_at >= today_start,
        )
    ) or 0
    daily_correct = await db.scalar(
        select(func.count())
        .select_from(UserResponse)
        .where(
            UserResponse.user_id == user_id,
            UserResponse.created_at >= today_start,
            UserResponse.answered_correct == True,
        )
    ) or 0
    total_seconds_today = await db.scalar(
        select(func.coalesce(func.sum(UserResponse.time_taken), 0))
        .where(
            UserResponse.user_id == user_id,
            UserResponse.created_at >= today_start,
        )
    ) or 0

    global_accuracy = (
        round((int(correct_questions) / int(total_questions)) * 100, 1)
        if int(total_questions) > 0
        else 0.0
    )
    daily_accuracy = (
        round((int(daily_correct) / int(daily_questions)) * 100, 1)
        if int(daily_questions) > 0
        else 0.0
    )
    learning_time_minutes = int(round(float(total_seconds_today) / 60.0))
    daily_point_rows = await db.execute(
        select(
            UserResponse.answered_correct,
            UserResponse.time_taken,
            UserResponse.used_hint,
        )
        .where(
            UserResponse.user_id == user_id,
            UserResponse.created_at >= today_start,
        )
    )
    daily_points = 0
    for answered_correct, time_taken, used_hint in daily_point_rows.all():
        daily_points += _response_points_delta(
            answered_correct=bool(answered_correct),
            time_taken=int(time_taken or 0),
            used_hint=bool(used_hint),
        )

    streak_window_start = today_start - timedelta(days=365)
    streak_rows = await db.execute(
        select(
            func.date(UserResponse.created_at).label("day"),
            func.count(UserResponse.id).label("count"),
        )
        .where(
            UserResponse.user_id == user_id,
            UserResponse.created_at >= streak_window_start,
        )
        .group_by(func.date(UserResponse.created_at))
    )
    day_counts: dict[date, int] = {}
    for day_value, count in streak_rows.all():
        if day_value is None:
            continue
        if isinstance(day_value, datetime):
            key = day_value.date()
        else:
            key = day_value
        day_counts[key] = int(count or 0)
    streak_days = _compute_streak_days(day_counts, today_start.date())

    classic_sessions = await db.scalar(
        select(func.count())
        .select_from(ClassicSession)
        .where(ClassicSession.user_id == user_id)
    ) or 0
    challenge_sessions = await db.scalar(
        select(func.count())
        .select_from(ChallengeSession)
        .where(ChallengeSession.user_id == user_id)
    ) or 0
    custom_sessions = await db.scalar(
        select(func.count())
        .select_from(CustomSession)
        .where(CustomSession.user_id == user_id)
    ) or 0

    pvp_matches = 0
    try:
        from database.pvp_models import PvPMatch

        pvp_matches = await db.scalar(
            select(func.count())
            .select_from(PvPMatch)
            .where(
                or_(
                    PvPMatch.user1_id == user_id,
                    PvPMatch.user2_id == user_id,
                )
            )
        ) or 0
    except Exception as exc:
        logger.warning("PvP stats unavailable in /api/auth/stats: %s", exc)

    room_progress = _compute_room_progress(
        int(classic_sessions),
        int(challenge_sessions),
        int(custom_sessions),
        int(pvp_matches),
    )
    room_locks = RoomLocksOut(
        classic=False,
        challenge=int(classic_sessions) < 1,
        custom=int(classic_sessions) < 1,
        pvp=int(challenge_sessions) < 1,
        visual=False,
    )

    return UserStatsOut(
        id=str(user.id),
        points=int(user.points or 0),
        level=str(user.level or "Novice"),
        total_questions=int(total_questions),
        global_accuracy=global_accuracy,
        daily_questions=int(daily_questions),
        daily_accuracy=daily_accuracy,
        learning_time_minutes=learning_time_minutes,
        daily_points=daily_points,
        streak_days=streak_days,
        room_progress=room_progress,
        room_locks=room_locks,
    )


@auth_router.get("/stats/daily-trend", response_model=DailyTrendOut)
@limiter.limit("120/minute")
# Return a day-by-day activity series for chart rendering.
async def stats_daily_trend(
    request: Request,
    days: int = Query(default=7, ge=1, le=90),
    current=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user, _issued_at = current

    safe_days = int(max(1, min(days, 90)))
    now = _db_utc_now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    range_start = today_start - timedelta(days=safe_days - 1)

    rows = await db.execute(
        select(
            func.date(UserResponse.created_at).label("day"),
            func.count(UserResponse.id).label("count"),
            func.coalesce(func.sum(cast(UserResponse.answered_correct, Integer)), 0).label("correct"),
        )
        .where(
            UserResponse.user_id == user.id,
            UserResponse.created_at >= range_start,
        )
        .group_by(func.date(UserResponse.created_at))
    )

    day_map: dict[date, tuple[int, int]] = {}
    for day_value, count, correct in rows.all():
        if day_value is None:
            continue
        if isinstance(day_value, datetime):
            key = day_value.date()
        else:
            key = day_value
        day_map[key] = (int(count or 0), int(correct or 0))

    points: list[DailyTrendPointOut] = []
    for offset in range(safe_days):
        current_day = (range_start + timedelta(days=offset)).date()
        count, correct = day_map.get(current_day, (0, 0))
        points.append(
            DailyTrendPointOut(
                date=current_day.isoformat(),
                day=current_day.strftime("%a"),
                count=count,
                correct=correct,
                points=correct * 10,
            )
        )

    return DailyTrendOut(days=safe_days, points=points)


@auth_router.post("/forgot-password", response_model=MessageOut)
@limiter.limit("5/minute")
# Start password reset flow by generating an OTP for known users.
async def forgot_password(
    request: Request,
    payload: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
    redis_client=Depends(get_redis),
):
    """Request a password reset OTP.

    Always returns success (prevents email enumeration).
    In dev mode, OTP code is printed to console.
    """
    logger.info("Forgot-password request: email=%s", payload.email)

    user = await db.scalar(
        select(User).where(User.email == payload.email.lower().strip())
    )
    if user:
        code = f"{secrets.randbelow(1_000_000):06d}"
        await _save_otp(redis_client, user.email, code)
        # Send OTP via email (falls back to console when SMTP is not configured)
        await send_otp_email(recipient=user.email, otp_code=code)

    return MessageOut(message="If the account exists, a reset code has been sent")


@auth_router.post("/reset-password", response_model=MessageOut)
@limiter.limit("10/minute")
# Verify OTP and replace the stored password hash.
async def reset_password(
    request: Request,
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    redis_client=Depends(get_redis),
):
    """Reset password using OTP code.

    Validates OTP, checks max attempts (3), then updates password hash.
    """
    email = payload.email.lower().strip()
    logger.info("Reset-password attempt: email=%s", email)

    otp_payload = await _read_otp(redis_client, email)
    if not otp_payload:
        raise HTTPException(status_code=400, detail="OTP expired or not found")

    attempts = int(otp_payload.get("attempts", 0))
    if attempts >= 3:
        await _delete_otp(redis_client, email)
        raise HTTPException(status_code=400, detail="OTP max attempts exceeded")

    if otp_payload.get("code") != payload.code.strip():
        await _bump_otp_attempts(redis_client, email, otp_payload)
        raise HTTPException(status_code=400, detail="Invalid OTP code")

    user = await db.scalar(select(User).where(User.email == email))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.password_hash = _hash_password(payload.new_password)
    await db.commit()
    await _delete_otp(redis_client, email)

    logger.info("Password reset successful: email=%s", email)
    return MessageOut(message="Password reset successful")


@auth_router.post("/bootstrap-admin", response_model=MessageOut)
@limiter.limit("3/minute")
# Promote an existing user to admin using the bootstrap secret.
async def bootstrap_admin(
    request: Request,
    payload: BootstrapAdminRequest,
    db: AsyncSession = Depends(get_db),
):
    """Promote a user to admin using a secret bootstrap key.

    Only works if ADMIN_BOOTSTRAP_KEY env var is set.
    Used during initial setup — disable in production.
    """
    if ENVIRONMENT.lower() == "production":
        raise HTTPException(status_code=403, detail="Admin bootstrap is disabled in production")

    if not ADMIN_BOOTSTRAP_KEY:
        raise HTTPException(status_code=403, detail="Admin bootstrap is disabled")

    if not hmac.compare_digest(payload.bootstrap_key, ADMIN_BOOTSTRAP_KEY):
        logger.warning("Invalid bootstrap key attempt for email=%s", payload.email)
        raise HTTPException(status_code=403, detail="Invalid bootstrap key")

    user = await db.scalar(
        select(User).where(User.email == payload.email.lower().strip())
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_admin = True
    await db.commit()

    logger.info("User promoted to admin: email=%s", user.email)
    return MessageOut(message=f"User {user.email} promoted to admin")
