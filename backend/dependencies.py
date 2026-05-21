"""dependencies.py — Shared FastAPI dependencies for DB, Redis, HTTP client, auth."""
import httpx
from typing import AsyncGenerator
from fastapi import HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address

from config import ENVIRONMENT


# ───────────────────────────────────────────────────────────────────────────
# RATE LIMITER (singleton)
# ───────────────────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)


# ───────────────────────────────────────────────────────────────────────────
# NOTE: The real DB, Redis, and HTTP client dependencies are defined in
# routers/auth.py (get_db, get_redis) and injected at startup via
# app.state in main.py's lifespan handler.
#
# Do NOT use the stubs below — they exist only as interface documentation.
# Import from routers.auth instead:
#   from routers.auth import get_db, get_redis
# ───────────────────────────────────────────────────────────────────────────

