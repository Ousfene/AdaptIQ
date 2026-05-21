from datetime import datetime, timedelta, timezone
from uuid import uuid4
import asyncio
import logging

import bcrypt
from jose import jwt, JWTError
from config import ACCESS_TOKEN_EXPIRE_MINUTES, JWT_ALGORITHM, JWT_SECRET_KEY

logger = logging.getLogger(__name__)


# ── Password helpers ──

def hash_password(password: str) -> str:
    """Synchronous password hashing (use async version in async contexts)."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


async def hash_password_async(password: str) -> str:
    """Async-safe password hashing using thread pool to avoid blocking event loop."""
    return await asyncio.to_thread(hash_password, password)


def verify_password(plain: str, hashed: str) -> bool:
    """Synchronous password verification (use async version in async contexts)."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


async def verify_password_async(plain: str, hashed: str) -> bool:
    """Async-safe password verification using thread pool to avoid blocking event loop."""
    return await asyncio.to_thread(verify_password, plain, hashed)


# ── JWT helpers ──

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update(
        {
            "exp": expire,
            "iat": int(now.timestamp()),
            "jti": str(uuid4()),
        }
    )
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return dict(payload)
    except JWTError:
        return None


def _user_revoked_after_key(user_id: str) -> str:
    return f"auth:revoked_after:{user_id}"


async def mark_tokens_revoked(redis, user_id: str) -> None:
    if redis is None:
        return
    await redis.set(_user_revoked_after_key(user_id), int(datetime.now(timezone.utc).timestamp()))


async def is_token_revoked(redis, user_id: str, token_iat: int | None) -> bool:
    """
    Check if a token has been revoked for a user.

    GRACEFUL DEGRADATION: When Redis is unavailable, allow tokens through with
    warning log. For a learning platform, degraded service (possibly with
    temporarily unrevoked tokens) is better than complete authentication lockout.
    
    NOTE: If strict security is required, change `return False` to `return True`
    in the redis=None case below to fail secure.
    """
    if redis is None:
        logger.warning("redis_unavailable_allowing_tokens", extra={"user_id": user_id})
        return False  # ← GRACEFUL DEGRADATION: Allow tokens when Redis unavailable
    if token_iat is None:
        return True

    try:
        revoked_after = await redis.get(_user_revoked_after_key(user_id))
        if revoked_after is None:
            return False
        return int(token_iat) <= int(revoked_after)
    except Exception as e:
        # Redis connection error during request - allow through with warning
        logger.warning("redis_error_allowing_token", extra={"user_id": user_id, "error": str(e)})
        return False
