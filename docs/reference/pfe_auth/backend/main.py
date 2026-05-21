import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Any, cast
import uuid
import time

import httpx
import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from fastapi.responses import JSONResponse

from config import DATABASE_URL, REDIS_URL, ENVIRONMENT, LOG_LEVEL, LOG_DIR, CORS_ORIGINS, validate_security_config
from database.models import Base
from dependencies import limiter
from routers.auth import router as auth_router
from routers.classic_room import router as classic_room_router
from routers.challenge import router as challenge_router
from routers.custom import router as custom_router
from routers.system import router as system_router
from rag.hf_dataset import load_hf_dataset

from services.monitoring import get_monitoring


def _configure_logging() -> None:
    log_level = getattr(logging, LOG_LEVEL, logging.INFO)
    logs_path = Path(__file__).resolve().parent / LOG_DIR
    logs_path.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    app_file_handler = RotatingFileHandler(
        logs_path / "backend.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    app_file_handler.setFormatter(formatter)

    error_file_handler = RotatingFileHandler(
        logs_path / "backend-error.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    error_file_handler.setFormatter(formatter)
    error_file_handler.setLevel(logging.WARNING)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.addHandler(app_file_handler)
    root_logger.addHandler(error_file_handler)

    # Ensure uvicorn logs flow to the same handlers.
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
        uvicorn_logger.setLevel(log_level)


_configure_logging()

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.dev.ConsoleRenderer() if ENVIRONMENT == "development" else structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)
logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("AdaptIQ backend starting up")

    validate_security_config()


    app.state.db_engine = None
    app.state.db_session_factory = None
    app.state.redis = None
    app.state.http_client = None

    _engine = None
    _factory = None
    redis_client = None
    http_client = None

    try:
        _engine = create_async_engine(
            DATABASE_URL,
            echo=(ENVIRONMENT == "development"),
            pool_size=10,
            max_overflow=20,
        )
        _factory = async_sessionmaker(
            _engine,
            expire_on_commit=False,
        )
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        app.state.db_engine = _engine
        app.state.db_session_factory = _factory
        logger.info("PostgreSQL connected and tables ready")
        
        # ── AUTO-SEED: Populate database if empty ──────────────────────
        try:
            from sqlalchemy import select, func
            from database.models import Concept
            async with _factory() as db:
                result = await db.execute(select(func.count(Concept.id)))
                concept_count = result.scalar()
                if concept_count == 0:
                    logger.warning("Database empty - running auto-seed...")
                    try:
                        from seeds.seed import seed_all
                        await seed_all(_factory)
                        logger.info("Auto-seed completed successfully")
                    except Exception as seed_exc:
                        logger.error(f"Auto-seed failed: {seed_exc}")
                else:
                    logger.info(f"Database has {concept_count} concepts - skipping seed")
        except Exception as check_exc:
            logger.warning(f"Auto-seed check failed (non-critical): {check_exc}")
    except Exception as exc:
        logger.error(f"PostgreSQL unavailable: {exc}")
        if _engine:
            await _engine.dispose()
        _engine = None
        _factory = None

    try:
        redis_client = cast(
            Any,
            await aioredis.from_url(
                REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
            ),
        )
        await redis_client.ping()
        app.state.redis = redis_client
        logger.info("Redis connected")
    except Exception as exc:
        logger.error(f"Redis unavailable: {exc}")
        if redis_client:
            await redis_client.aclose()
        redis_client = None

    try:
        http_client = httpx.AsyncClient(
            timeout=15.0,
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
            headers={"User-Agent": "AdaptIQ/1.0 (educational-platform; contact@adaptiq.com)"},
        )
        app.state.http_client = http_client
    except Exception as exc:
        logger.error(f"HTTP client initialization failed: {exc}")
        http_client = None

    try:
        await load_hf_dataset()
        logger.info("HuggingFace dataset loaded asynchronously")
    except Exception as exc:
        logger.warning(f"HF dataset loading failed (non-critical): {exc}")

    logger.info("AdaptIQ backend ready")
    yield

    logger.info("Shutting down")
    if app.state.http_client:
        await app.state.http_client.aclose()
    if app.state.db_engine:
        await app.state.db_engine.dispose()
    if app.state.redis:
        await app.state.redis.aclose()
    logger.info("Shutdown complete")


app = FastAPI(
    title="AdaptIQ API",
    version="1.1.0",
    description="Adaptive MCQ backend with modular auth, room, and system routes.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],  # Explicit methods (no TRACE, CONNECT)
    allow_headers=["content-type", "authorization"],
    max_age=3600,  # Cache CORS preflight for 1 hour
)

# ── Setup request/response logging middleware ──────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    Log HTTP requests and responses for debugging.
    Tracks: request_id, path, method, status, duration, errors.
    """
    request_id = str(uuid.uuid4())
    start_time = time.time()
    monitoring = get_monitoring()

    # Log incoming request
    logger.info(
        "request_started",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "query": dict(request.query_params) if request.query_params else {},
            "client_ip": get_remote_address(request),
        }
    )

    try:
        response = await call_next(request)
        duration_ms = (time.time() - start_time) * 1000
        status_code = response.status_code

        # Track successful request
        if status_code < 400:
            monitoring.record_request(request.url.path)

        # Log response status
        log_level = "info"
        if status_code >= 500:
            log_level = "error"
            monitoring.record_error(
                request.url.path,
                request.method,
                status_code,
                "ServerError",
                "Server error response",
                duration_ms,
            )
        elif status_code >= 400:
            log_level = "warning"
            if status_code != 429:  # 429 handled separately
                monitoring.record_error(
                    request.url.path,
                    request.method,
                    status_code,
                    f"ClientError{status_code}",
                    "Client error response",
                    duration_ms,
                )

        getattr(logger, log_level)(
            "request_completed",
            extra={
                "request_id": request_id,
                "path": request.url.path,
                "method": request.method,
                "status": status_code,
                "duration_ms": round(duration_ms, 2),
                "client_ip": get_remote_address(request),
            }
        )

        # Add request_id to response headers for client debugging
        response.headers["X-Request-ID"] = request_id

        return response

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error(
            "request_failed",
            extra={
                "request_id": request_id,
                "path": request.url.path,
                "method": request.method,
                "duration_ms": round(duration_ms, 2),
                "error": str(e),
                "error_type": type(e).__name__,
                "client_ip": get_remote_address(request),
            }
        )
        monitoring.record_error(
            request.url.path,
            request.method,
            500,
            type(e).__name__,
            str(e),
            duration_ms,
        )
        raise

# ── Setup rate limiting (Fix 2.4) ──────────────────────────────────────
# limiter is now imported from dependencies.py (single shared instance)
app.state.limiter = limiter

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """
    Log rate limit hits for monitoring and debugging.
    Rate-limited endpoints return 429 with Retry-After header.
    """
    client_ip = get_remote_address(request)
    monitoring = get_monitoring()

    # Record rate limit hit
    monitoring.record_rate_limit(client_ip, request.url.path, request.method)

    logger.warning(
        "rate_limit_exceeded",
        extra={
            "client_ip": client_ip,
            "path": request.url.path,
            "method": request.method,
            "endpoint": f"{request.method} {request.url.path}",
            "query_params": dict(request.query_params),
            "total_rate_limits": monitoring.request_stats["total_rate_limits"],
        }
    )
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please try again later."},
        headers={"Retry-After": "60"},
    )

# ── Global exception handler for comprehensive error capture ────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Catches ALL unhandled exceptions and logs detailed information for debugging.
    """
    logger.error(
        "UNHANDLED_EXCEPTION",
        extra={
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "path": request.url.path,
            "method": request.method,
            "exception_traceback": True,  # structlog logs traceback with exc_info
        },
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": f"{type(exc).__name__}: {str(exc)[:100]}"},
    )

app.include_router(system_router)
app.include_router(auth_router)
app.include_router(classic_room_router)
app.include_router(challenge_router)
app.include_router(custom_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,  # Disabled to prevent constant reloads interfering with requests
        log_level=LOG_LEVEL.lower(),
    )