from datetime import datetime, timezone
from typing import Any, cast
import logging

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.core.security import create_access_token, hash_password_async, verify_password_async
from auth.core.security import mark_tokens_revoked
from auth.services.email_service import otp_email_template, send_email
from auth.services.otp_service import OTP_PURPOSE_PASSWORD_RESET, create_otp, verify_otp
from database.models import User


logger = logging.getLogger(__name__)


def utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def register_user(data, db: AsyncSession) -> dict[str, Any]:
    email = data.email.strip().lower()
    username = data.username.strip().lower()

    existing = await db.execute(
        select(User).where((User.email == email) | (User.username == username))
    )
    user = existing.scalar_one_or_none()
    if user is not None:
        logger.warning("auth.register.conflict")  # Don't log email/username
        if str(user.email) == email:
            raise ValueError("Email already registered")
        raise ValueError("Username already taken")

    user = User(
        email=email,
        username=username,
        password_hash=await hash_password_async(data.password),  # ← Use async
    )
    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
    except Exception:
        await db.rollback()
        raise

    user_record = cast(Any, user)
    token = create_access_token({"sub": str(user_record.id)})
    logger.info("auth.register.success", extra={"user_id": str(user_record.id)})  # Removed email
    return {
        "user": {
            "id": str(user_record.id),
            "email": str(user_record.email),
            "username": str(user_record.username),
        },
        "access_token": token,
        "token_type": "bearer",
    }


async def login_user(data, db: AsyncSession) -> dict[str, Any]:
    email = data.email.strip().lower()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    # Check if user exists and has a password_hash before verifying
    if user is None or user.password_hash is None:
        logger.warning("auth.login.invalid_credentials")  # Don't log email
        raise ValueError("Invalid email or password")

    if not await verify_password_async(data.password, user.password_hash):
        logger.warning("auth.login.invalid_credentials")  # Don't log email
        raise ValueError("Invalid email or password")

    user_record = cast(Any, user)
    user_record.last_login = utc_now_naive()
    try:
        await db.commit()
    except Exception:
        await db.rollback()

    token = create_access_token({"sub": str(user_record.id)})
    logger.info("auth.login.success", extra={"user_id": str(user_record.id)})  # Removed email
    return {
        "user": {
            "id": str(user_record.id),
            "email": str(user_record.email),
            "username": str(user_record.username),
        },
        "access_token": token,
        "token_type": "bearer",
    }


async def forgot_password(data, db: AsyncSession, redis) -> dict[str, str]:
    email = data.email.strip().lower()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    # Always act as if successful to avoid email enumeration
    if user is not None and bool(user.password_hash):
        if redis is None:
            # CRITICAL FIX 1.1: Fail explicitly when Redis is down
            raise HTTPException(
                status_code=503,
                detail="Password reset temporarily unavailable - Redis service required for OTP generation"
            )
        code = await create_otp(redis, email, OTP_PURPOSE_PASSWORD_RESET)
        html = otp_email_template(code, "Enter this code to reset your password")
        await send_email(email, "AdaptIQ — Password Reset Code", html)

    logger.info("auth.forgot_password.requested")  # Don't log email

    return {
        "message": "If an account exists with this email, a reset code has been sent.",
        "email": email,
        "purpose": "password_reset",
    }


async def reset_password(data, db: AsyncSession, redis) -> dict[str, str]:
    email = data.email.strip().lower()

    if redis is None:
        raise ValueError("Redis is offline")

    valid = await verify_otp(redis, email, OTP_PURPOSE_PASSWORD_RESET, data.code)
    if not valid:
        logger.warning("auth.reset_password.invalid_code")  # Don't log email
        raise ValueError("Invalid or expired reset code")

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError("No account found with this email")

    user_record = cast(Any, user)
    user_record.password_hash = await hash_password_async(data.new_password)  # ← Use async
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    await mark_tokens_revoked(redis, str(user_record.id))
    logger.info("auth.reset_password.success", extra={"user_id": str(user_record.id)})  # Removed email

    return {"message": "Password reset successfully. You can now log in."}


async def check_login_rate_limit(redis, ip: str, email: str, limit: int = 5, window_seconds: int = 60) -> tuple[bool, int]:
    if redis is None:
        return True, 0

    key = f"ratelimit:login:{ip or 'unknown'}:{email.lower()}"
    current = await redis.incr(key)
    ttl = await redis.ttl(key)
    if current == 1:
        await redis.expire(key, window_seconds)
        ttl = window_seconds
    if current > limit:
        retry_after = ttl if ttl and ttl > 0 else window_seconds
        return False, int(retry_after)
    return True, 0


async def clear_login_rate_limit(redis, ip: str, email: str) -> None:
    if redis is None:
        return
    await redis.delete(f"ratelimit:login:{ip or 'unknown'}:{email.lower()}")


async def check_rate_limit(
    redis,
    scope: str,
    key_value: str,
    limit: int,
    window_seconds: int,
) -> tuple[bool, int]:
    if redis is None:
        return True, 0

    key = f"ratelimit:{scope}:{key_value}"
    current = await redis.incr(key)
    ttl = await redis.ttl(key)
    if current == 1:
        await redis.expire(key, window_seconds)
        ttl = window_seconds
    if current > limit:
        retry_after = ttl if ttl and ttl > 0 else window_seconds
        return False, int(retry_after)
    return True, 0
