"""config.py — Single source of truth for all app settings, loaded from .env."""
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load the backend/.env file relative to this config module so the app
# works when started from the repo root or other working directories.
env_path = Path(__file__).resolve().parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    # Fall back to normal lookup (cwd, parent, etc.) for flexibility
    load_dotenv()
logger = logging.getLogger(__name__)


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
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://adaptiq:adaptiq@localhost:5432/adaptiq_db",
)

# ── Redis ─────────────────────────────────────────────────────────────────
REDIS_URL: str = os.getenv(
    "REDIS_URL",
    "redis://localhost:6379/0",
)

# ── LLM ───────────────────────────────────────────────────────────────────
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

# ── App ───────────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
LOG_DIR: str = os.getenv("LOG_DIR", "logs")
AUTO_CREATE_TABLES: bool = _parse_bool(os.getenv("AUTO_CREATE_TABLES"), default=True)

# ── CORS ──────────────────────────────────────────────────────────────────
_cors_origins_env = os.getenv("CORS_ORIGINS", "")
CORS_ORIGINS: list[str] = (
    [origin.strip() for origin in _cors_origins_env.split(",") if origin.strip()]
    if _cors_origins_env
    else [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://localhost:9000",
        "http://127.0.0.1:9000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3001",
        "http://localhost:3001",
    ]
)

# ── Auth / JWT ────────────────────────────────────────────────────────────
JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "change-this-dev-secret-change-this-dev-secret")
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
CSRF_SECRET_KEY: str = os.getenv("CSRF_SECRET_KEY", "")

# ── Feature Flags ──────────────────────────────────────────────────────────
ENABLE_IDEMPOTENCY: bool = _parse_bool(os.getenv("ENABLE_IDEMPOTENCY"), default=True)
ENABLE_CONCEPT_TRACKING: bool = _parse_bool(os.getenv("ENABLE_CONCEPT_TRACKING"), default=True)
ENABLE_CONCEPT_DISPLAY: bool = _parse_bool(os.getenv("ENABLE_CONCEPT_DISPLAY"), default=True)
ENABLE_TRUSTWORTHY_GENERATION: bool = _parse_bool(os.getenv("ENABLE_TRUSTWORTHY_GENERATION"), default=False)
DEV_BYPASS_AUTH: bool = _parse_bool(os.getenv("DEV_BYPASS_AUTH"), default=False)

# ── Quiz / Game Rules ─────────────────────────────────────────────────────
QUIZ_TIME_LIMIT_SECONDS: int = int(os.getenv("QUIZ_TIME_LIMIT_SECONDS", "30"))
QUIZ_QUESTIONS_PER_SESSION: int = int(os.getenv("QUIZ_QUESTIONS_PER_SESSION", "10"))

POINTS_BASE_AWARD: int = int(os.getenv("POINTS_BASE_AWARD", "10"))
POINTS_TIME_BONUS_DIVISOR: int = int(os.getenv("POINTS_TIME_BONUS_DIVISOR", "3"))
POINTS_HINT_PENALTY: int = int(os.getenv("POINTS_HINT_PENALTY", "3"))
POINTS_WRONG_PENALTY: int = int(os.getenv("POINTS_WRONG_PENALTY", "5"))

# ── Inactivity Decay ──────────────────────────────────────────────────────
INACTIVITY_DECAY_DAYS: int = int(os.getenv("INACTIVITY_DECAY_DAYS", "14"))
INACTIVITY_DECAY_FACTOR: float = float(os.getenv("INACTIVITY_DECAY_FACTOR", "0.1"))

# ── Session / Cache TTLs ──────────────────────────────────────────────────
SESSION_TTL_SECONDS: int = int(os.getenv("SESSION_TTL_SECONDS", "3600"))
IDEMPOTENCY_TTL_SECONDS: int = int(os.getenv("IDEMPOTENCY_TTL_SECONDS", "3600"))
QUESTION_CACHE_TTL_SECONDS: int = int(os.getenv("QUESTION_CACHE_TTL_SECONDS", "3600"))
SESSION_LOCK_TTL_SECONDS: int = int(os.getenv("SESSION_LOCK_TTL_SECONDS", "60"))
SESSION_LOCK_TIMEOUT_SECONDS: int = int(os.getenv("SESSION_LOCK_TIMEOUT_SECONDS", "30"))

# ── Custom Room Configuration ─────────────────────────────────────────────
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
CUSTOM_ROOM_SESSION_TTL: int = int(os.getenv("CUSTOM_ROOM_SESSION_TTL", "3600"))
CUSTOM_ROOM_SIMPLE_MODE: bool = _parse_bool(os.getenv("CUSTOM_ROOM_SIMPLE_MODE"), default=False)

# Level thresholds for user progression
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
    normalized_secret = (JWT_SECRET_KEY or "").strip()

    if not normalized_secret:
        raise RuntimeError(
            "CRITICAL: JWT_SECRET_KEY is empty. Set a strong secret via JWT_SECRET_KEY."
        )

    if len(normalized_secret) < JWT_MIN_SECRET_LENGTH:
        raise RuntimeError(
            f"CRITICAL: JWT_SECRET_KEY is too short ({len(normalized_secret)} chars). "
            f"Minimum {JWT_MIN_SECRET_LENGTH} required."
        )

    if ENVIRONMENT.lower() == "production" and normalized_secret == "change-this-dev-secret-change-this-dev-secret":
        raise RuntimeError(
            "CRITICAL: JWT_SECRET_KEY is using the default insecure placeholder in production."
        )

    if ENVIRONMENT.lower() != "production" and normalized_secret == "change-this-dev-secret-change-this-dev-secret":
        logger.warning(
            "JWT_SECRET_KEY is using the default development placeholder. "
            "Set JWT_SECRET_KEY in .env to avoid insecure local tokens."
        )

    if ENVIRONMENT.lower() == "production" and AUTO_CREATE_TABLES:
        raise RuntimeError(
            "CRITICAL: AUTO_CREATE_TABLES is enabled in production! "
            "This is dangerous. Use Alembic migrations instead. Set AUTO_CREATE_TABLES=false."
        )

    if DEV_BYPASS_AUTH and ENVIRONMENT.lower() == "production":
        raise RuntimeError(
            "CRITICAL: DEV_BYPASS_AUTH is enabled in production! "
            "This allows anyone to impersonate any user. Set DEV_BYPASS_AUTH=false immediately."
        )

    if POINTS_TIME_BONUS_DIVISOR <= 0:
        raise RuntimeError(
            "POINTS_TIME_BONUS_DIVISOR must be > 0 to avoid division by zero"
        )
