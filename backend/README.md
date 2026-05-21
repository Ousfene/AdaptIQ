# AdaptIQ Backend — Complete Setup Guide

This is a production-ready FastAPI backend for an adaptive learning platform with concept-level Item Response Theory (IRT), Alembic migrations, and comprehensive architecture.

## 📁 Directory Structure

```
backend/
├── config.py                      # Environment config with security validation
├── dependencies.py                # Shared FastAPI dependencies
├── schemas.py                     # Canonical Pydantic models
├── main.py                        # FastAPI app with lifespan and middleware
├── alembic/                       # Database migrations
│   ├── env.py                     # Alembic configuration
│   ├── script.py.mako             # Migration template
│   ├── versions/                  # Migration files
│   │   └── 20260411_01_concept_auth_schema.py
│   └── alembic.ini
├── database/
│   ├── models.py                  # Core models (User, QuestionBank, UserResponse)
│   ├── concept_models.py          # Concept-level models
│   ├── challenge_models.py        # Challenge room models
│   ├── custom_models.py           # Custom topic models
│   ├── onboarding_models.py       # Onboarding models
│   ├── crud.py                    # Database CRUD operations
│   ├── irt.py                     # IRT math
│   └── __init__.py
├── services/
│   ├── llm.py                     # Groq LLMClient
│   ├── session.py                 # Redis session management
│   ├── monitoring.py              # Monitoring service
│   ├── challenge_service.py       # Challenge room logic
│   ├── custom_service.py          # Custom room logic
│   ├── concept_service.py         # Concept discovery
│   ├── onboarding_service.py      # Onboarding logic
│   └── __init__.py
├── routers/
│   ├── auth.py                    # Auth endpoints
│   ├── challenge.py               # Challenge room endpoints
│   ├── custom.py                  # Custom room endpoints
│   ├── onboarding.py              # Onboarding endpoints
│   ├── admin.py                   # Admin endpoints
│   └── __pycache__/
├── rag/
│   ├── agentic.py                 # Agentic RAG pipeline
│   ├── wikipedia.py               # Wikipedia retriever
│   ├── wikidata.py                # Wikidata retriever
│   ├── hf_dataset.py              # HuggingFace dataset
│   └── __init__.py
├── seeds/
│   ├── seed.py                    # Database seeding
│   └── __init__.py
├── requirements.txt               # Python dependencies
├── Dockerfile                     # Container configuration
├── logs/                          # Log files (created at runtime)
└── README.md                      # This file
```

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.13+
- PostgreSQL 16+
- Redis 7+
- Docker & Docker Compose (optional)

### 2. Setup Environment

```bash
# Create .env file
cat > .env << 'EOF'
DATABASE_URL=postgresql+asyncpg://adaptiq:adaptiq@localhost:5432/adaptiq_db
REDIS_URL=redis://localhost:6379/0
GROQ_API_KEY=your-groq-api-key
JWT_SECRET_KEY=your-secret-key-at-least-32-characters-long
ENVIRONMENT=development
LOG_LEVEL=INFO
AUTO_CREATE_TABLES=true
ENABLE_CONCEPT_TRACKING=true
ENABLE_CONCEPT_DISPLAY=true
ENABLE_TRUSTWORTHY_GENERATION=false
DEV_BYPASS_AUTH=false
EOF
```

### 3. Docker Services

```bash
# Start PostgreSQL and Redis
docker-compose up -d postgres redis

# Run migrations (production)
# alembic upgrade head

# Or enable AUTO_CREATE_TABLES for development
# Already configured in .env above
```

### 4. Install Dependencies

```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### 5. Run Backend

```bash
python main.py
# Runs on http://localhost:8000
# Auto-seeds database on first startup if empty
# API docs: http://localhost:8000/docs
```

## Code-Audited Reality Check (2026-04-14)

The sections below contain legacy examples in some places. The following route prefixes are verified from current source code:

- Auth: `/api/auth`
- Classic: `/api/rooms/classic`
- Challenge: `/api/challenge`
- Custom: `/api/custom`
- PvP: `/api/pvp`
- Onboarding: `/api/onboarding`
- Admin: `/api/admin`

Current Challenge endpoints are:

- `GET /api/challenge/user/{user_id}/rank`
- `POST /api/challenge/start-session`
- `GET /api/challenge/session/{session_id}`
- `PATCH /api/challenge/session/{session_id}/change-level`
- `POST /api/challenge/generate-question`
- `POST /api/challenge/submit-answer`
- `POST /api/challenge/session/{session_id}/end`

Additional backend behavior verified in current code:

- `POST /api/pvp/match/{match_id}/answer` verifies `question_id` matches the server-issued question for the submitted `question_index`.
- `GET /api/admin/sessions` supports `challenge`, `custom`, and `pvp`, then sorts merged results and paginates globally.

Anti-cheat response contract (current behavior):

- `POST /api/challenge/generate-question` returns `explanation` as an empty string before submission.
- `POST /api/challenge/submit-answer` returns the question `explanation` after submission.
- `POST /api/custom/generate-question` returns `explanation` as an empty string before submission.
- `POST /api/custom/submit-answer` returns the question `explanation` after submission.

Testing note:

- `tests/e2e_test.py` expects a running backend at localhost:8000 during collection.

## 🗄️ Database & Migrations

### Schema Overview

**Core Tables:**
- `users` — User accounts with auth credentials
- `question_bank` — Cached questions from LLM
- `user_responses` — Quiz answer history
- `user_concept_theta` — Per-concept user ability (IRT θ)

**Concept Tables:**
- `concepts` — Concept definitions (e.g., "Egyptian Empire")
- `question_concepts` — N-to-M link between questions and concepts
- `user_concept_repeat_queue` — Spaced repetition queue

**Challenge Room:**
- `challenge_sessions` — Session tracking
- `challenge_answers` — Per-answer records
- `challenge_ranking` — Rank/point tracking

**Custom Room:**
- `custom_topics` — User-defined topics
-`custom_facts` — Facts within topics
- `user_topic_mastery` — Progress tracking

### Alembic Usage

```bash
# Initialize migrations (already done)
# alembic init alembic

# Create a migration from models
alembic revision --autogenerate -m "describe_change"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Stamp existing database (skip migrations)
alembic stamp head
```

## 🔑 Configuration (config.py)

All settings are environment-backed with sensible defaults:

```python
# Database
DATABASE_URL = "postgresql+asyncpg://user:pass@host:port/db"

# Redis
REDIS_URL = "redis://host:port/db"

# LLM
GROQ_API_KEY = "gsk_..."

# Auth
JWT_SECRET_KEY = "32+ chars required"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# App
ENVIRONMENT = "development" | "production"
LOG_LEVEL = "DEBUG" | "INFO" | "WARNING" | "ERROR"
AUTO_CREATE_TABLES = true | false

# Features
ENABLE_CONCEPT_TRACKING = true
ENABLE_CONCEPT_DISPLAY = true
ENABLE_IDEMPOTENCY = true
ENABLE_TRUSTWORTHY_GENERATION = true | false
DEV_BYPASS_AUTH = false  # NEVER true in production
```

Trustworthy generation governance (block rules + audits): see [GOVERNANCE_RUNBOOK.md](GOVERNANCE_RUNBOOK.md).

### Security Validation

`validate_security_config()` runs on startup and fails if:
- DEV_BYPASS_AUTH is true in production
- AUTO_CREATE_TABLES is true in production
- JWT_SECRET_KEY is too short or default
- Any required credentials are missing

## 📡 API Routes

### Health Check
```
GET /health
```

### Auth (from routers/auth.py)
```
POST   /api/auth/register
POST   /api/auth/login
GET    /api/auth/me
POST   /api/auth/logout
GET    /api/auth/stats
GET    /api/auth/stats/concept-mastery
POST   /api/auth/forgot-password
POST   /api/auth/reset-password
```

### Classic Room (Training Mode)
```
POST   /api/rooms/classic/questions    # Generate MCQ
POST   /api/rooms/classic/hints        # Get hint
POST   /api/rooms/classic/answers      # Submit answer
```

### Challenge Room (Competitive Mode)
```
GET    /api/rooms/challenge/status
POST   /api/rooms/challenge/start
POST   /api/rooms/challenge/v2/generate-question
POST   /api/rooms/challenge/v2/submit-answer
```

### System
```
GET    /api/system/health
GET    /api/system/monitoring/stats
```

## 🧠 IRT (Item Response Theory)

**Per-Concept Adaptation:**
- User ability: θ (theta) per concept, initialized at 0.0
- Question difficulty: β (beta) per question
- Maps difficulty 1-5 to β via breakpoints [-1.5, -0.5, 0.5, 1.5]

**Update Rule:**
- After each answer: θ' = θ + α(y - P), where:
  - y = 1 if correct, 0 if wrong
  - P = 1 / (1 + e^(-(θ - β))) [logistic function]
  - α = learning rate (0.3)

**Zone of Proximal Development (ZPD):**
- Target difficulty chosen so P(correct) ≈ 60-75%
- If accuracy too high: increase difficulty
- If accuracy too low: decrease difficulty

See `database/irt.py` for implementation.

## 🌱 Database Seeding

Auto-seeding happens on first startup if database is empty:

```python
from seeds.seed import seed_all
await seed_all(session_factory)
```

Seeds include:
- Concepts: "Egyptian Empire", "Roman History", "African Capitals", etc.
- Test users for development

## 🔐 Authentication

### JWT Tokens
- Algorithm: HS256 (configurable)
- Expiry: 30 minutes (configurable)
- Stored in Redis with revocation support

### Dev Bypass
Enable only in development for testing:
```bash
DEV_BYPASS_AUTH=true
```
Then use:
```bash
curl -H "Authorization: Bearer dev-bypass-550e8400-e29b-41d4-a716-446655440000" \
  http://localhost:8000/api/auth/me
```

## 📊 Logging

**Structured Logging (structlog):**
- JSON format in production
- Pretty console output in development
- Logs to files with rotation (5MB max, 5 backups)

**Log Files:**
- `logs/backend.log` — All logs
- `logs/backend-error.log` — Errors only

**Environment:**
```bash
LOG_LEVEL=DEBUG | INFO | WARNING | ERROR
LOG_DIR=logs
ENVIRONMENT=development | production
```

## 🛠️ Development

### Run Tests
```bash
pytest                # All tests
pytest -v tests/test_irt.py  # Specific file
pytest -k concept     # Keyword filter
```

### Code Structure

**Routers** (endpoint definitions)
- Split by feature: auth, classic_room, challenge, custom, onboarding, admin
- Use dependency injection for DB, Redis, LLM
- Validators at API boundary

**Services** (business logic)
- challenge_service.py — Level/streak/points logic
- concept_service.py — Concept discovery
- llm.py — LLM client for generation
- session.py — Redis session management

**Database** (persistence)
- models.py — Core ORM models
- concept_models.py — Concept-level tracking
- crud.py — Database operations
- irt.py — IRT calculations

## 🔗 Integration

### Frontend (React/TypeScript)
- Frontend runs on `http://localhost:5173`
- Calls backend API at `http://localhost:8000`
- CORS configured in main.py

### LLM (Groq)
- Question generation via LLM
- Temperature: 0.8 for creativity
- Fallback to static questions if LLM unavailable

### RAG Pipeline
- 3-agent orchestrator: Router → Retriever → Validator
- Retrieves Wikipedia, Wikidata, HuggingFace datasets
- Falls back to direct LLM if network blocked

## 📋 Monitoring & Debugging

### Health Check
```bash
curl http://localhost:8000/health
```

### Request Logging
All requests logged with:
- request_id (UUID)
- method, path, status
- duration_ms
- client IP

### Metrics
Monitoring service tracks:
- Total requests per endpoint
- Error rates (4xx, 5xx)
- Rate limit hits

Access via:
```bash
curl http://localhost:8000/api/system/monitoring/stats
```

## 🚨 Troubleshooting

### "Database unavailable"
- Check PostgreSQL is running: `docker ps | grep postgres`
- Check DATABASE_URL in .env
- Initialize database: `alembic upgrade head`

### "Redis unavailable"
- Backend falls back to in-memory session store
- Performance degrades; see console warning
- Check Redis running: `docker ps | grep redis`

### "GROQ_API_KEY not set"
- LLM generation disabled
- Questions fall back to static pool
- Set in .env and restart

### "DEV_BYPASS_AUTH in production"
- Security validation fails on startup
- Remove from .env immediately
- This is intentional — prevents accidental production exposure

## 📦 Production Deployment

### Before Deploy
1. ✅ Set `ENVIRONMENT=production`
2. ✅ Set `AUTO_CREATE_TABLES=false` (use Alembic instead)
3. ✅ Set `DEV_BYPASS_AUTH=false`
4. ✅ Rotate JWT_SECRET_KEY
5. ✅ Configure real CORS_ORIGINS
6. ✅ Enable SMTP for password resets
7. ✅ Set LOG_LEVEL=WARNING or ERROR

### Docker Deploy
```bash
docker build -t adaptiq-backend .
docker run -e DATABASE_URL="..." -e GROQ_API_KEY="..." adaptiq-backend
```

### Kubernetes / Systemd
See Dockerfile for container setup.

## 🤝 Contributing

1. Create feature branch: `git checkout -b feature/concept-xyz`
2. Follow existing patterns in services/routers
3. Add tests for new endpoints
4. Run full suite before push: `pytest`
5. Use Alembic for schema changes: `alembic revision --autogenerate`

## 📚 References

- **FastAPI:** https://fastapi.tiangolo.com
- **SQLAlchemy Async:** https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- **Alembic:** https://alembic.sqlalchemy.org
- **Pydantic:** https://docs.pydantic.dev
- **IRT Theory:** https://en.wikipedia.org/wiki/Item_response_theory

## 📄 License

AdaptIQ Backend © 2024. Educational Platform.
