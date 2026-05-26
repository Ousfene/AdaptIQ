"""
main.py — FastAPI application for AdaptIQ backend.

Features:
  - Auto-seed on startup if database is empty
  - Request/response logging middleware
  - Rate limiting with slowapi
  - Global exception handler
  - Structlog for structured logging
  - Modular router-based architecture
"""

import logging
import time
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path
from contextlib import asynccontextmanager
from typing import cast, Any

import httpx
import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
import redis.asyncio as aioredis

from config import (
    DATABASE_URL,
    REDIS_URL,
    ENVIRONMENT,
    LOG_LEVEL,
    LOG_DIR,
    CORS_ORIGINS,
    AUTO_CREATE_TABLES,
    validate_security_config,
    GROQ_API_KEY,
)
from dependencies import limiter
from database.models import Base
import database.challenge_models
import database.custom_models
import database.onboarding_models
import database.concept_models
import database.pvp_models
import database.governance_models
import database.visual_models as _visual_models  # registers VisualQuestion/VisualSession
from services.llm import LLMClient
from services.session import SessionService
from services.monitoring import get_monitoring
from rag.agentic import AgenticRAGPipeline
from rag.hf_dataset import load_hf_dataset

# ═══════════════════════════════════════════════════════════════════════════
# LOGGING CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════


def _configure_logging() -> None:
    """Configure logging with rotating file handlers."""
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
        structlog.dev.ConsoleRenderer() if ENVIRONMENT == "development"
        else structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)
logger = structlog.get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# LIFESPAN
# ═══════════════════════════════════════════════════════════════════════════


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    logger.info("AdaptIQ backend starting up")

    validate_security_config()
    logger.info(
        "startup_configuration",
        environment=ENVIRONMENT,
        auto_create_tables=AUTO_CREATE_TABLES,
        log_level=LOG_LEVEL,
        cors_origins_count=len(CORS_ORIGINS),
        llm_enabled=bool(GROQ_API_KEY),
    )

    app.state.db_engine = None
    app.state.db_session_factory = None
    app.state.redis = None
    app.state.http_client = None
    app.state.llm_client = None
    app.state.rag_pipeline = None
    app.state.session_service = None

    _engine = None
    _factory = None
    redis_client = None
    http_client = None

    # ── DATABASE CONNECTION ────────────────────────────────────────────────
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

        if AUTO_CREATE_TABLES:
            async with _engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("PostgreSQL connected and tables ready (create_all enabled)")
        else:
            logger.info("PostgreSQL connected (use Alembic migrations)")

        app.state.db_engine = _engine
        app.state.db_session_factory = _factory

        # ── AUTO-SEED: Populate if empty ───────────────────────────────────
        try:
            from database.concept_models import Concept
            from database.models import QuestionBank
            async with _factory() as db:
                concept_count = (await db.execute(select(func.count(Concept.id)))).scalar() or 0
                question_count = (await db.execute(select(func.count(QuestionBank.id)))).scalar() or 0
                if concept_count == 0 or question_count == 0:
                    logger.warning(
                        "Seed baseline missing (concepts=%s, questions=%s) — running auto-seed...",
                        concept_count,
                        question_count,
                    )
                    try:
                        from seeds.seed import seed_all
                        await seed_all(_factory)
                        logger.info("Auto-seed completed")
                    except Exception as seed_exc:
                        logger.warning(f"Auto-seed failed (non-critical): {seed_exc}")
        except Exception as check_exc:
            logger.warning(f"Auto-seed check skipped: {check_exc}")

    except Exception as exc:
        logger.error(f"PostgreSQL unavailable: {exc}")
        if _engine:
            await _engine.dispose()
        _engine = None
        _factory = None

    # ── REDIS CONNECTION ───────────────────────────────────────────────────
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
        logger.warning(f"Redis unavailable: {exc} — using in-memory session store")
        redis_client = None

    # ── HTTP CLIENT ────────────────────────────────────────────────────────
    try:
        http_client = httpx.AsyncClient(
            timeout=15.0,
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
            headers={"User-Agent": "AdaptIQ/1.0 (educational-platform)"},
        )
        app.state.http_client = http_client
    except Exception as exc:
        logger.error(f"HTTP client init failed: {exc}")
        http_client = None

    # ── LLM CLIENT ─────────────────────────────────────────────────────────
    if GROQ_API_KEY:
        app.state.llm_client = LLMClient(api_key=GROQ_API_KEY)
        logger.info("Groq LLM client ready")
    else:
        logger.warning("GROQ_API_KEY not set — LLM generation disabled")

    # ── RAG DATA + PIPELINE ────────────────────────────────────────────────
    hf_dataset_ready = False
    try:
        hf_dataset_ready = await load_hf_dataset()
    except Exception as exc:
        logger.warning(f"HF dataset loading failed (non-critical): {exc}")

    if hf_dataset_ready:
        logger.info("HuggingFace dataset loaded for RAG")
    else:
        logger.warning("HuggingFace dataset unavailable; RAG will run without dataset-backed retrieval")

    try:
        app.state.rag_pipeline = AgenticRAGPipeline()
        logger.info("Agentic RAG pipeline initialized")
    except Exception as exc:
        app.state.rag_pipeline = None
        logger.warning(f"RAG pipeline initialization failed: {exc}")

    # ── SESSION SERVICE ────────────────────────────────────────────────────
    app.state.session_service = SessionService(redis=redis_client)
    logger.info("Session service initialized")

    logger.info("AdaptIQ backend ready ✓")

    yield

    logger.info("Shutting down")
    if app.state.http_client:
        await app.state.http_client.aclose()
    if app.state.llm_client:
        await app.state.llm_client.close()
    if app.state.db_engine:
        await app.state.db_engine.dispose()
    if app.state.redis:
        await app.state.redis.aclose()
    logger.info("Shutdown complete")


# ═══════════════════════════════════════════════════════════════════════════
# APPLICATION
# ═══════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title="AdaptIQ API",
    version="1.1.0",
    description="Adaptive MCQ backend with concept-level IRT and modular architecture",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


# ═══════════════════════════════════════════════════════════════════════════
# MIDDLEWARE
# ═══════════════════════════════════════════════════════════════════════════

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["content-type", "authorization"],
    max_age=3600,
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log HTTP requests and responses."""
    request_id = str(uuid.uuid4())
    start_time = time.time()
    monitoring = get_monitoring()

    logger.info(
        "request_started",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "client_ip": get_remote_address(request),
        }
    )

    try:
        response = await call_next(request)
        duration_ms = (time.time() - start_time) * 1000

        if response.status_code < 400:
            monitoring.record_request(request.url.path)
        elif response.status_code >= 500:
            monitoring.record_error(
                request.url.path, request.method, response.status_code,
                "ServerError", "Server error", duration_ms
            )
        elif response.status_code >= 400 and response.status_code != 429:
            monitoring.record_error(
                request.url.path, request.method, response.status_code,
                f"ClientError{response.status_code}", "Client error", duration_ms
            )

        logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "path": request.url.path,
                "method": request.method,
                "status": response.status_code,
                "duration_ms": round(duration_ms, 2),
            }
        )

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
            }
        )
        monitoring.record_error(
            request.url.path, request.method, 500, type(e).__name__, str(e), duration_ms
        )
        raise


# ═══════════════════════════════════════════════════════════════════════════
# EXCEPTION HANDLERS
# ═══════════════════════════════════════════════════════════════════════════

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Handle rate limit exceeded."""
    client_ip = get_remote_address(request)
    get_monitoring().record_rate_limit(client_ip, request.url.path, request.method)

    logger.warning(
        "rate_limit_exceeded",
        extra={
            "client_ip": client_ip,
            "path": request.url.path,
            "method": request.method,
        }
    )
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please try again later."},
        headers={"Retry-After": "60"},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch all unhandled exceptions."""
    logger.error(
        "UNHANDLED_EXCEPTION",
        extra={
            "exception_type": type(exc).__name__,
            "path": request.url.path,
            "method": request.method,
        },
        exc_info=exc,
    )
    detail = (
        f"{type(exc).__name__}: {str(exc)[:100]}"
        if ENVIRONMENT.lower() == "development"
        else "Internal server error"
    )
    return JSONResponse(status_code=500, content={"detail": detail})


# ═══════════════════════════════════════════════════════════════════════════
# ROUTES (to be imported and included from routers/)
# ═══════════════════════════════════════════════════════════════════════════

# Import routers
try:
    from routers.auth import auth_router
    from routers.classic_room import classic_router
    from routers.challenge import challenge_router
    from routers.custom import custom_router
    from routers.onboarding import onboarding_router
    from routers.admin import admin_router
    from routers.governance import governance_router
    from routers.pvp import pvp_router
    from routers.visual_room import visual_router
    from routers.chat_router import chat_router

    app.include_router(auth_router)
    app.include_router(classic_router)
    app.include_router(challenge_router)
    app.include_router(custom_router)
    app.include_router(onboarding_router)
    app.include_router(admin_router)
    app.include_router(governance_router)
    app.include_router(pvp_router)
    app.include_router(visual_router)
    app.include_router(chat_router)
    logger.info("All routers loaded successfully (including Visual Room and Scholar Chat)")
except ImportError as e:
    logger.warning(f"Some routers failed to load: {e}")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    services = {
        "database": "ok" if app.state.db_engine else "unavailable",
        "redis": "ok" if app.state.redis else "unavailable",
        "llm": "ok" if app.state.llm_client else "disabled",
    }
    return {
        "status": "ok",
        "version": "1.1.0",
        "services": services
    }


if __name__ == "__main__":
    import os as _os
    import uvicorn
    run_port = int(_os.getenv("PORT", "8000"))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=run_port,
        reload=False,
        log_level=LOG_LEVEL.lower(),
    )
