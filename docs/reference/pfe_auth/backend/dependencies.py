from typing import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from slowapi import Limiter
from slowapi.util import get_remote_address

from config import DATABASE_URL


# Force slowapi to ignore backend/.env during import to avoid encoding-related crashes in tests.
limiter = Limiter(key_func=get_remote_address, config_filename="__slowapi_no_env__")


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    session_factory = getattr(request.app.state, "db_session_factory", None)
    if session_factory is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    async with session_factory() as session:
        yield session


def get_redis(request: Request):
    return getattr(request.app.state, "redis", None)


def get_http_client(request: Request) -> httpx.AsyncClient:
    http_client = getattr(request.app.state, "http_client", None)
    if http_client is None:
        raise HTTPException(status_code=503, detail="HTTP client unavailable")
    return http_client


@asynccontextmanager
async def get_async_session_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Standalone async session context for scripts (seed, decay, etc.).
    Creates its own engine and session, not tied to FastAPI app state.
    """
    engine = create_async_engine(DATABASE_URL, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()
    
    await engine.dispose()