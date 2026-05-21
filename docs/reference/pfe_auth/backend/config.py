"""config.py — Single source of truth for all app settings, loaded from .env."""
import os
from dotenv import load_dotenv

load_dotenv()


def _parse_bool(value: str | None, default: bool = False) -> bool:
    """
    Parse a boolean from an environment variable string.
    
    Accepts: "true", "1", "yes", "on" (case-insensitive) as True
    Accepts: "false", "0", "no", "off" (case-insensitive) as False
    Returns default for None or empty string.
    """
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in ("true", "1", "yes", "on")

# ── Database ──────────────────────────────────────────────────────────────
# docker-compose overrides DATABASE_URL with container-internal hostname.
# Local dev default uses host-mapped port 5433.
# IMPORTANT: Do not change the default value. It will fail with validation error
# if DATABASE_URL is not configured via environment variable.
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://pfe:CHANGEME@localhost:5433/adaptive_learning",
)

# ── Redis ─────────────────────────────────────────────────────────────────
REDIS_URL: str = os.getenv(
    "REDIS_URL",
    "redis://:CHANGEME@localhost:6379/0",
)

# ── LLM ───────────────────────────────────────────────────────────────────
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

# ── App ───────────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
LOG_DIR: str = os.getenv("LOG_DIR", "logs")

# ── CORS ──────────────────────────────────────────────────────────────────
# Comma-separated list of allowed origins. In production, set to your actual domains.
# Example: CORS_ORIGINS=https://adaptiq.example.com,https://www.adaptiq.example.com
_cors_origins_env = os.getenv("CORS_ORIGINS", "")
CORS_ORIGINS: list[str] = (
    [origin.strip() for origin in _cors_origins_env.split(",") if origin.strip()]
    if _cors_origins_env
    else [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
)

# ── Auth / JWT ────────────────────────────────────────────────────────────
JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "")
JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
JWT_MIN_SECRET_LENGTH: int = int(os.getenv("JWT_MIN_SECRET_LENGTH", "32"))

# ── SMTP ──────────────────────────────────────────────────────────────────
SMTP_HOST: str = os.getenv("SMTP_HOST", "")
SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", "")
SMTP_FROM_NAME: str = os.getenv("SMTP_FROM_NAME", "AdaptIQ")
SMTP_USE_TLS: bool = _parse_bool(os.getenv("SMTP_USE_TLS"), default=True)

# ── OTP ───────────────────────────────────────────────────────────────────
OTP_LENGTH: int = int(os.getenv("OTP_LENGTH", "6"))
OTP_EXPIRE_SECONDS: int = int(os.getenv("OTP_EXPIRE_SECONDS", "300"))
OTP_MAX_ATTEMPTS: int = int(os.getenv("OTP_MAX_ATTEMPTS", "3"))

# ── CSRF ──────────────────────────────────────────────────────────────────
CSRF_SECRET_KEY: str = os.getenv("CSRF_SECRET_KEY", "")  # Must be set in production

# ── Feature Flags ──────────────────────────────────────────────────────────
# Spam Prevention: Idempotent answer submission with submission state machine
ENABLE_IDEMPOTENCY: bool = _parse_bool(os.getenv("ENABLE_IDEMPOTENCY"), default=True)
# Concept Tracking: Per-concept IRT theta tracking (backend processing)
ENABLE_CONCEPT_TRACKING: bool = _parse_bool(os.getenv("ENABLE_CONCEPT_TRACKING"), default=True)
# Concept Display: Show concept mastery in dashboard UI
ENABLE_CONCEPT_DISPLAY: bool = _parse_bool(os.getenv("ENABLE_CONCEPT_DISPLAY"), default=True)
# Dev Bypass Auth: Allow "dev-bypass-{user_id}" tokens for testing (NEVER enable in production)
DEV_BYPASS_AUTH: bool = _parse_bool(os.getenv("DEV_BYPASS_AUTH"), default=False)

# ── Quiz / Game Rules ─────────────────────────────────────────────────────
# All quiz/scoring constants live here so they are easy to find and tune
# without touching game logic. Override any via environment variable.

# Seconds allowed per question (must match frontend QUIZ_TIME_LIMIT)
QUIZ_TIME_LIMIT_SECONDS: int = int(os.getenv("QUIZ_TIME_LIMIT_SECONDS", "30"))
# Number of questions per quiz session
QUIZ_QUESTIONS_PER_SESSION: int = int(os.getenv("QUIZ_QUESTIONS_PER_SESSION", "10"))
# Base points for a correct answer
POINTS_BASE_AWARD: int = int(os.getenv("POINTS_BASE_AWARD", "10"))
# Time bonus = floor(seconds_remaining / POINTS_TIME_BONUS_DIVISOR)
# e.g. 24s left / 3 = +8 bonus → total 18 pts  (matches frontend formula)
POINTS_TIME_BONUS_DIVISOR: int = int(os.getenv("POINTS_TIME_BONUS_DIVISOR", "3"))
# Points deducted when a hint is used
POINTS_HINT_PENALTY: int = int(os.getenv("POINTS_HINT_PENALTY", "3"))
# Points deducted for a wrong answer (user total cannot go below 0)
POINTS_WRONG_PENALTY: int = int(os.getenv("POINTS_WRONG_PENALTY", "5"))

# ── Inactivity Decay ──────────────────────────────────────────────────────
# Users who haven't played for a while should have their theta estimates
# decay toward 0 (neutral) to account for knowledge decay over time.
INACTIVITY_DECAY_DAYS: int = int(os.getenv("INACTIVITY_DECAY_DAYS", "14"))  # Start decay after 2 weeks
INACTIVITY_DECAY_FACTOR: float = float(os.getenv("INACTIVITY_DECAY_FACTOR", "0.1"))  # 10% decay per period

# ── Session / Cache TTLs ──────────────────────────────────────────────────
# ═══════ REDIS-1 FIX: Move TTLs to config ═══════
SESSION_TTL_SECONDS: int = int(os.getenv("SESSION_TTL_SECONDS", "3600"))  # 1 hour
IDEMPOTENCY_TTL_SECONDS: int = int(os.getenv("IDEMPOTENCY_TTL_SECONDS", "3600"))  # 1 hour
QUESTION_CACHE_TTL_SECONDS: int = int(os.getenv("QUESTION_CACHE_TTL_SECONDS", "3600"))  # 1 hour
SESSION_LOCK_TTL_SECONDS: int = int(os.getenv("SESSION_LOCK_TTL_SECONDS", "60"))  # 60 seconds
SESSION_LOCK_TIMEOUT_SECONDS: int = int(os.getenv("SESSION_LOCK_TIMEOUT_SECONDS", "30"))  # Wait timeout

# ── Custom Room Configuration ─────────────────────────────────────────────────
# Topic registry: maps theme/country names to descriptions
CUSTOM_ROOM_TOPICS: dict[str, dict[str, str]] = {
    "History": {
        "World War II": "1939-1945 global conflict",
        "Cold War": "1947-1991 superpower standoff",
        "Ancient Rome": "27 BC - 476 AD empire",
        "Medieval Europe": "5th-15th centuries",
        "Renaissance": "14th-17th century revival",
    },
    "Geography": {
        "France": "Western European nation",
        "Japan": "East Asian island nation",
        "Brazil": "South American giant",
        "Egypt": "North African nation",
        "Australia": "Oceanian continent-nation",
    }
}

CUSTOM_ROOM_FACTS_PER_TOPIC: int = int(os.getenv("CUSTOM_ROOM_FACTS_PER_TOPIC", "1000"))
CUSTOM_ROOM_SESSION_TTL: int = int(os.getenv("CUSTOM_ROOM_SESSION_TTL", "3600"))  # 1 hour

# Level thresholds: (minimum_points_required, level_name)
# Ordered highest → lowest so compute_level() short-circuits early
_LEVEL_THRESHOLDS: list[tuple[int, str]] = [
    (5000, "Master"),
    (1500, "Expert"),
    (500,  "Scholar"),
    (100,  "Apprentice"),
    (0,    "Novice"),
]


def compute_level(points: int) -> str:
    """Return the level name matching the current points total."""
    for threshold, label in _LEVEL_THRESHOLDS:
        if points >= threshold:
            return label
    return "Novice"


def validate_security_config() -> None:
    """Fail fast for insecure auth settings."""
    # ── Validate credentials are configured ────────────────────────────────
    if "CHANGEME" in DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not configured. Set the DATABASE_URL environment variable "
            "with proper credentials. The default placeholder CHANGEME prevents accidental "
            "connection with incomplete configuration."
        )
    if "CHANGEME" in REDIS_URL:
        raise RuntimeError(
            "REDIS_URL is not configured. Set the REDIS_URL environment variable "
            "with proper credentials. The default placeholder CHANGEME prevents accidental "
            "connection with incomplete configuration."
        )

    # ── Validate JWT settings ──────────────────────────────────────────────
    if not JWT_SECRET_KEY:
        raise RuntimeError("JWT_SECRET_KEY is required and must not be empty")
    if JWT_SECRET_KEY == "change-this-dev-secret-change-this-dev-secret":
        raise RuntimeError("JWT_SECRET_KEY default placeholder is not allowed")
    if len(JWT_SECRET_KEY) < JWT_MIN_SECRET_LENGTH:
        raise RuntimeError(
            f"JWT_SECRET_KEY must be at least {JWT_MIN_SECRET_LENGTH} characters"
        )
    if ACCESS_TOKEN_EXPIRE_MINUTES < 5 or ACCESS_TOKEN_EXPIRE_MINUTES > 120:
        raise RuntimeError("ACCESS_TOKEN_EXPIRE_MINUTES must be between 5 and 120")
    
    # ── Validate JWT algorithm ─────────────────────────────────────────────
    valid_algorithms = {"HS256", "HS384", "HS512", "RS256", "RS384", "RS512"}
    if JWT_ALGORITHM not in valid_algorithms:
        raise RuntimeError(
            f"Invalid JWT_ALGORITHM: {JWT_ALGORITHM}. "
            f"Must be one of: {', '.join(sorted(valid_algorithms))}"
        )
    
    # ── Validate dev bypass is disabled in production ──────────────────────
    if DEV_BYPASS_AUTH and ENVIRONMENT.lower() == "production":
        raise RuntimeError(
            "CRITICAL: DEV_BYPASS_AUTH is enabled in production! "
            "This allows anyone to impersonate any user. "
            "Set DEV_BYPASS_AUTH=false immediately."
        )
    
    # ── Validate points config ─────────────────────────────────────────────
    if POINTS_TIME_BONUS_DIVISOR <= 0:
        raise RuntimeError(
            "POINTS_TIME_BONUS_DIVISOR must be > 0 to avoid division by zero"
        )
