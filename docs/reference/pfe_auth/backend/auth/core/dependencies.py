from uuid import UUID
import logging

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.core.security import decode_access_token, is_token_revoked
from database.models import User
from config import DEV_BYPASS_AUTH

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> User:
    """
    Extract and validate a JWT Bearer token, then return the matching User row.

    Supports dev bypass mode: if DEV_BYPASS_AUTH=true and token is "dev-bypass-{user_id}",
    looks up user directly without JWT verification.

    The DB session is obtained from app_state (set via request.app.state) so
    this dependency does NOT need a get_db argument injected — that was the bug.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # ── Dev Bypass Mode ─────────────────────────────────────────────────────
    if DEV_BYPASS_AUTH and token.startswith("dev-bypass-"):
        user_id_str = token[len("dev-bypass-"):]
        logger.debug(f"DEV BYPASS USED: {user_id_str}")
        
        try:
            user_uuid = UUID(user_id_str)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid dev bypass token format",
            )
        
        db_factory = getattr(request.app.state, "db_session_factory", None)
        if db_factory is None:
            raise HTTPException(status_code=503, detail="Database unavailable")
        
        async with db_factory() as db:
            result = await db.execute(select(User).where(User.id == user_uuid))
            user = result.scalar_one_or_none()
        
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Dev bypass user not found",
            )
        return user

    # ── Standard JWT Flow ───────────────────────────────────────────────────
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id = payload.get("sub")
    token_iat = payload.get("iat")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    try:
        user_uuid = UUID(user_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    redis_client = getattr(request.app.state, "redis", None)
    if await is_token_revoked(redis_client, str(user_id), token_iat):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token revoked",
        )

    # Grab the session factory that main.py attaches to app.state at startup
    db_factory = getattr(request.app.state, "db_session_factory", None)
    if db_factory is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    async with db_factory() as db:
        result = await db.execute(select(User).where(User.id == user_uuid))
        user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """
    Dependency that requires admin privileges.
    Checks that the user has is_admin=True.
    """
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return user
