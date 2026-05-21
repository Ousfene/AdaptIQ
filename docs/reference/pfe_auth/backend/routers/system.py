import uuid
import time
import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel

from schemas import HealthOut, QuestionOut
from services.monitoring import get_monitoring
from config import GROQ_API_KEY, ENVIRONMENT

logger = logging.getLogger(__name__)


# ── Response models for monitoring ────────────────────────────────────
class MonitoringEventOut(BaseModel):
    """Single monitoring event (rate limit or error)."""
    timestamp: str
    path: str
    method: str
    endpoint: str


class RateLimitEventOut(MonitoringEventOut):
    """Rate limit event."""
    client_ip: str


class ErrorEventOut(MonitoringEventOut):
    """API error event."""
    status_code: int
    error_type: str
    error_message: str
    duration_ms: float


class MonitoringStatsOut(BaseModel):
    """Overall monitoring statistics."""
    total_requests: int
    total_errors: int
    total_rate_limits: int
    error_rate: float
    rate_limit_count: int
    recent_errors: list[dict]
    recent_rate_limits: list[dict]


router = APIRouter(prefix="/api/system", tags=["system"])


class DetailedHealthOut(BaseModel):
    """Detailed health check response."""
    status: str
    environment: str
    version: str
    database: dict
    redis: dict
    llm: dict


@router.get("/health", response_model=HealthOut)
async def health_check(request: Request):
    services = {
        "database": "ok" if getattr(request.app.state, "db_engine", None) else "unavailable",
        "redis": "ok" if getattr(request.app.state, "redis", None) else "unavailable",
    }
    status = "ok" if all(v == "ok" for v in services.values()) else "degraded"
    return HealthOut(status=status, services=services)


@router.get("/health/detailed", response_model=DetailedHealthOut)
async def detailed_health_check(request: Request):
    """
    Detailed health check with latency measurements and configuration status.
    
    Returns:
    - status: Overall system status (healthy/degraded/unhealthy)
    - environment: Current environment (development/production)
    - version: Application version
    - database: Connection status and latency
    - redis: Connection status and memory usage
    - llm: LLM provider configuration status
    """
    from sqlalchemy import text
    
    # Check database with latency
    db_status = {"connected": False, "latency_ms": None, "error": None}
    db_engine = getattr(request.app.state, "db_engine", None)
    if db_engine:
        try:
            start = time.perf_counter()
            async with db_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            db_status["connected"] = True
            db_status["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
        except Exception as e:
            db_status["error"] = str(e)
            logger.warning("health_check_db_error", extra={"error": str(e)})
    
    # Check Redis with memory info
    redis_status = {"connected": False, "memory_mb": None, "error": None}
    redis_client = getattr(request.app.state, "redis", None)
    if redis_client:
        try:
            start = time.perf_counter()
            await redis_client.ping()
            redis_status["connected"] = True
            redis_status["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
            
            # Try to get memory info
            try:
                info = await redis_client.info("memory")
                redis_status["memory_mb"] = round(info.get("used_memory", 0) / (1024 * 1024), 2)
            except Exception:
                pass  # Memory info not critical
        except Exception as e:
            redis_status["error"] = str(e)
            logger.warning("health_check_redis_error", extra={"error": str(e)})
    
    # Check LLM configuration
    llm_status = {
        "groq_configured": bool(GROQ_API_KEY),
        "provider": "groq" if GROQ_API_KEY else "none",
    }
    
    # Determine overall status
    if db_status["connected"] and redis_status["connected"]:
        overall_status = "healthy"
    elif db_status["connected"]:
        overall_status = "degraded"  # Redis down but DB up
    else:
        overall_status = "unhealthy"
    
    logger.info("health_check_detailed", extra={
        "status": overall_status,
        "db_latency_ms": db_status.get("latency_ms"),
        "redis_latency_ms": redis_status.get("latency_ms"),
    })
    
    return DetailedHealthOut(
        status=overall_status,
        environment=ENVIRONMENT,
        version="1.0.0",
        database=db_status,
        redis=redis_status,
        llm=llm_status,
    )


@router.get("/test-question", response_model=QuestionOut)
async def test_question():
    return QuestionOut(
        id=uuid.uuid4(),
        text="What is the capital of France?",
        options=["London", "Berlin", "Paris", "Madrid"],
        explanation="Paris is the capital and largest city of France.",
    )


# ── Monitoring endpoints (for debugging and analytics) ──────────────────
@router.get("/monitoring/stats", response_model=MonitoringStatsOut)
async def get_monitoring_stats():
    """
    Get overall API statistics and health.

    Returns:
    - total_requests: Total successful requests tracked
    - total_errors: Total error responses
    - total_rate_limits: Total rate limit hits
    - error_rate: Proportion of requests that errored (0-1)
    - recent_errors: Last 5 errors for debugging
    - recent_rate_limits: Last 5 rate limits for debugging
    """
    monitoring = get_monitoring()
    return monitoring.get_stats()


@router.get("/monitoring/rate-limits", response_model=list[RateLimitEventOut])
async def get_recent_rate_limits(limit: int = 20):
    """
    Get recent rate limit hits for debugging abuse patterns.

    Args:
    - limit: Number of events to return (max 100)

    Returns list of recent rate limit events with client IPs and endpoints.
    """
    monitoring = get_monitoring()
    limit = min(limit, 100)
    events = monitoring.get_recent_rate_limits(limit)
    return [RateLimitEventOut(**e) for e in events]


@router.get("/monitoring/errors", response_model=list[ErrorEventOut])
async def get_recent_errors(limit: int = 20):
    """
    Get recent API errors for debugging.

    Args:
    - limit: Number of events to return (max 100)

    Returns list of recent error events with status codes and types.
    """
    monitoring = get_monitoring()
    limit = min(limit, 100)
    events = monitoring.get_recent_errors(limit)
    return [ErrorEventOut(**e) for e in events]