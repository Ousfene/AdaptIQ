from datetime import date, datetime
import logging
from typing import Dict

import redis
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.core.dependencies import get_current_user
from auth.services import auth_service
from database import crud
from database.models import User, UserResponse, UserConceptTheta, Concept
from database.concept_irt import ConceptIRT
from config import ENABLE_CONCEPT_DISPLAY
from dependencies import get_db, get_redis
from schemas import (
    AuthResponse,
    ConceptMasteryItemOut,
    ConceptMasteryOut,
    DailyTrendOut,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    OTPResponse,
    RedisOpsOut,
    RegisterRequest,
    ResetPasswordRequest,
    TopicBreakdownOut,
    UserResponse as UserResponseSchema,
    UserStatsOut,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = logging.getLogger(__name__)


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",", 1)[0].strip() or "unknown"
    xri = request.headers.get("x-real-ip", "")
    if xri:
        return xri.strip()
    return request.client.host if request.client else "unknown"


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    request: Request,
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    ip = _client_ip(request)
    allowed, retry_after = await auth_service.check_rate_limit(
        redis=redis,
        scope="register",
        key_value=f"{ip}:{body.email.strip().lower()}",
        limit=5,
        window_seconds=300,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many registration attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    try:
        return await auth_service.register_user(body, db)
    except ValueError as exc:
        logger.error("register_user_error", extra={"error": str(exc)})
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Registration failed. Please try again.") from exc


@router.post("/login", response_model=AuthResponse)
async def login_user(
    request: Request,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    client_ip = _client_ip(request)
    email = body.email.strip().lower()

    allowed, retry_after = await auth_service.check_login_rate_limit(redis, client_ip, email)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many login attempts. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )

    try:
        response = await auth_service.login_user(body, db)
    except ValueError as exc:
        logger.error("login_user_error", extra={"error": str(exc)})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password") from exc

    await auth_service.clear_login_rate_limit(redis, client_ip, email)
    return response


@router.get("/me", response_model=UserResponseSchema)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserResponseSchema(
        id=str(current_user.id),
        email=str(current_user.email),
        username=str(current_user.username),
    )


@router.get("/stats", response_model=UserStatsOut)
async def get_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return aggregated quiz statistics for the authenticated user."""
    from sqlalchemy import Integer, cast, select as sa_select

    today_start = datetime.combine(date.today(), datetime.min.time())

    # All-time totals
    total_result = await db.execute(
        sa_select(
            func.count(UserResponse.id).label("total"),
            func.coalesce(func.sum(cast(UserResponse.answered_correct, Integer)), 0).label("correct"),
            func.coalesce(func.sum(UserResponse.time_taken), 0).label("total_time"),
        ).where(UserResponse.user_id == current_user.id)
    )
    total_row = total_result.one()

    # Today's stats
    daily_result = await db.execute(
        sa_select(
            func.count(UserResponse.id).label("daily"),
            func.coalesce(func.sum(cast(UserResponse.answered_correct, Integer)), 0).label("daily_correct"),
        ).where(
            and_(
                UserResponse.user_id == current_user.id,
                UserResponse.created_at >= today_start,
            )
        )
    )
    daily_row = daily_result.one()

    total_q = total_row.total or 0
    correct_q = int(total_row.correct or 0)
    daily_q = daily_row.daily or 0
    daily_correct = int(daily_row.daily_correct or 0)

    # Safely convert points (handle unexpected types)
    try:
        points_val = int(current_user.points) if isinstance(current_user.points, (int, str)) else 0
    except (ValueError, TypeError):
        logger.warning(f"Invalid points value for user {current_user.id}: {current_user.points}, defaulting to 0")
        points_val = 0

    return UserStatsOut(
        id=str(current_user.id),
        points=points_val,
        level=str(current_user.level or "Novice"),
        total_questions=total_q,
        correct_questions=correct_q,
        global_accuracy=round(correct_q / total_q * 100, 1) if total_q > 0 else 0.0,
        daily_questions=daily_q,
        daily_correct=daily_correct,
        daily_accuracy=round(daily_correct / daily_q * 100, 1) if daily_q > 0 else 0.0,
        learning_time_minutes=int((total_row.total_time or 0) // 60),
    )


@router.get("/stats/topic-breakdown", response_model=TopicBreakdownOut)
async def get_stats_topic_breakdown(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await crud.get_user_topic_breakdown(db, str(current_user.id))
    return TopicBreakdownOut(topics=rows)


@router.get("/stats/daily-trend", response_model=DailyTrendOut)
async def get_stats_daily_trend(
    days: int = Query(default=7, ge=1, le=90),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    points = await crud.get_user_daily_trend(db, str(current_user.id), days)
    return DailyTrendOut(days=days, points=points)


@router.get("/stats/redis-ops", response_model=RedisOpsOut)
async def get_stats_redis_ops(
    current_user: User = Depends(get_current_user),
    redis=Depends(get_redis),
):
    _ = current_user
    if redis is None:
        return RedisOpsOut(
            status="in-memory-fallback",
            active_sessions=0,
            session_ttl_buckets={"lt_5m": 0, "5m_to_30m": 0, "gt_30m": 0, "unknown": 0},
            otp_keys=0,
            rate_limit_keys=0,
            revoked_token_keys=0,
        )

    active_sessions = 0
    otp_keys = 0
    rate_limit_keys = 0
    revoked_token_keys = 0
    ttl_buckets = {"lt_5m": 0, "5m_to_30m": 0, "gt_30m": 0, "unknown": 0}

    try:
        async for key in redis.scan_iter(match="session:*"):
            active_sessions += 1
            ttl = await redis.ttl(key)
            if ttl is None or ttl < 0:
                ttl_buckets["unknown"] += 1
            elif ttl < 300:
                ttl_buckets["lt_5m"] += 1
            elif ttl <= 1800:
                ttl_buckets["5m_to_30m"] += 1
            else:
                ttl_buckets["gt_30m"] += 1

        async for _ in redis.scan_iter(match="otp:*"):
            otp_keys += 1
        async for _ in redis.scan_iter(match="ratelimit:*"):
            rate_limit_keys += 1
        async for _ in redis.scan_iter(match="auth:revoked_after:*"):
            revoked_token_keys += 1
    except (redis.ConnectionError, redis.TimeoutError) as exc:
        logger.error("redis_connection_error", extra={"error": str(exc)})
        raise HTTPException(status_code=503, detail="Cache service unavailable") from exc
    except Exception as exc:
        logger.error("redis_metrics_error", extra={"error": str(exc), "error_type": type(exc).__name__})
        raise HTTPException(status_code=500, detail="Metrics retrieval failed") from exc

    return RedisOpsOut(
        status="ok",
        active_sessions=active_sessions,
        session_ttl_buckets=ttl_buckets,
        otp_keys=otp_keys,
        rate_limit_keys=rate_limit_keys,
        revoked_token_keys=revoked_token_keys,
    )


@router.post("/forgot-password", response_model=OTPResponse)
async def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    ip = _client_ip(request)
    email = body.email.strip().lower()
    allowed, retry_after = await auth_service.check_rate_limit(
        redis=redis,
        scope="forgot-password",
        key_value=f"{ip}:{email}",
        limit=5,
        window_seconds=300,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many password reset requests. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )
    return await auth_service.forgot_password(body, db, redis)


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    request: Request,
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    ip = _client_ip(request)
    email = body.email.strip().lower()
    allowed, retry_after = await auth_service.check_rate_limit(
        redis=redis,
        scope="reset-password",
        key_value=f"{ip}:{email}",
        limit=8,
        window_seconds=600,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many reset attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    try:
        return await auth_service.reset_password(body, db, redis)
    except ValueError as exc:
        logger.error("reset_password_error", extra={"error": str(exc)})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    redis=Depends(get_redis),
):
    """
    Logout and revoke all tokens for the current user.
    
    After calling this endpoint, all existing tokens for this user will be
    invalidated. The user will need to log in again to get a new token.
    """
    from auth.core.security import mark_tokens_revoked
    
    if redis is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Logout service temporarily unavailable",
        )
    
    await mark_tokens_revoked(redis, str(current_user.id))
    logger.info("user_logged_out", extra={"user_id": str(current_user.id)})
    return MessageResponse(message="Logged out successfully")


@router.get("/stats/concept-mastery", response_model=ConceptMasteryOut)
async def get_concept_mastery(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Return per-concept mastery breakdown for dashboard visualization.
    Requires ENABLE_CONCEPT_DISPLAY flag (feature disabled by default during concept rollout).
    """
    if not ENABLE_CONCEPT_DISPLAY:
        # Feature not yet enabled; return empty response
        return ConceptMasteryOut(concepts={})

    try:
        # Fetch all concept thetas for this user
        stmt = select(UserConceptTheta).where(UserConceptTheta.user_id == current_user.id)
        result = await db.execute(stmt)
        theta_records = result.scalars().all()

        if not theta_records:
            return ConceptMasteryOut(concepts={})

        # Group by topic
        by_topic: Dict[str, list[ConceptMasteryItemOut]] = {}

        # Batch fetch all concepts (avoid N+1 query)
        concept_ids = [record.concept_id for record in theta_records]
        if concept_ids:
            concepts_stmt = select(Concept).where(Concept.id.in_(concept_ids))
            concepts_result = await db.execute(concepts_stmt)
            concept_rows = concepts_result.scalars().all()
            concepts_by_id = {c.id: c for c in concept_rows}
        else:
            concepts_by_id = {}

        skipped_concept_count = 0
        for record in theta_records:
            # Look up concept from batch-fetched dictionary (no extra query)
            concept = concepts_by_id.get(record.concept_id)

            if not concept:
                logger.warning(f"Concept {record.concept_id} not found for user {current_user.id}")
                skipped_concept_count += 1
                continue

            if concept.topic not in by_topic:
                by_topic[concept.topic] = []

            # Map theta to mastery level
            if record.theta < -1.0:
                level = "Beginner"
            elif record.theta < 1.0:
                level = "Intermediate"
            else:
                level = "Advanced"

            by_topic[concept.topic].append(
                ConceptMasteryItemOut(
                    concept=concept.name,
                    theta=round(record.theta, 2),
                    level=level,
                    responses=record.response_count,
                    lastUpdated=record.last_updated.isoformat() if record.last_updated else None,
                )
            )

        if skipped_concept_count > 0:
            logger.info(f"Skipped {skipped_concept_count} concept records for user {current_user.id}")

        return ConceptMasteryOut(concepts=by_topic)

    except Exception as e:
        logger.error("concept_mastery_retrieval_failed", extra={"error": str(e), "user_id": str(current_user.id)})
        raise HTTPException(status_code=500, detail="Failed to retrieve concept mastery data")