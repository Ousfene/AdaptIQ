# CLAUDE.md — AdaptIQ Project Context

## What This Is
Adaptive learning quiz platform (PFE project). Users register, enter rooms to answer MCQs that adapt difficulty via IRT at the **concept level** (not just topic).

## Game Modes

### Classic Room (Training Mode)
- User selects topic: Geography, History, or Mix
- 4 options per question
- Hints available (never reveal answer)
- Post-answer explanations for learning
- **Concept-level adaptation**: e.g., "Egyptian Empire" vs "Roman Empire" tracked separately
- Wrong answers: 25% chance to repeat in next 7 sessions
- Correct answers: 1% chance to repeat
- ELO currently visible (will be hidden later - training, not competing)
- **Inactivity decay**: Theta decays toward 0 after 14 days of inactivity (10% per period)

### Challenge Room (Competitive Mode)
- Ranked competition with visible ELO
- 5 ranks with increasing difficulty:
  - **Bronze**: Levels 1-2, easy entry
  - **Silver**: Levels 1-3, no timer
  - **Gold**: Levels 2-4, 45s timer
  - **Platinum**: Levels 3-5, 30s timer
  - **Diamond**: Levels 4-5, 25s timer (future: typed answers)
- **Dynamic Level System** (V2):
  - Streak of 4 correct → level up
  - Streak of 2 wrong → level down
  - Points vary by level: Level 1 (+3/-1) to Level 5 (+11/-9)
- Rank progression based on cumulative points: Bronze(0)→Silver(1000)→Gold(3000)→Platinum(7000)→Diamond(15000)
- Skip rank: Can attempt 1 rank above (3 attempts, 24h cooldown)
- Anti-farming: Cannot play lower ranks
- Unlocks after 5 Classic Room games

## Tech Stack
- **Backend**: FastAPI (Python 3.13+), SQLAlchemy async, PostgreSQL 16, Redis 7, Pydantic 2
- **Frontend**: React 19, TypeScript, Vite, Tailwind CSS 4, React Router 7
- **LLM**: Groq API (Llama 3.1-8B-instant) for MCQ generation + hints
- **IRT**: 1-Parameter Logistic model (θ=user ability per concept, β=question difficulty)
- **RAG**: 3-agent pipeline (Router→Retriever→Validator) using Wikipedia, Wikidata, HuggingFace datasets

## Project Structure
```
pfe_auth/
├── backend/
│   ├── main.py              # App bootstrap: lifespan, middleware, router registration, auto-seed
│   ├── config.py            # Environment-backed settings + validate_security_config()
│   ├── dependencies.py      # Shared FastAPI dependencies for DB, Redis, HTTP client
│   ├── schemas.py           # Canonical request/response models (auth, rooms, challenge, system)
│   ├── pydantic_types.py    # Compatibility re-exports for older imports
│   ├── auth/                # Auth internals
│   │   ├── routers.py       # Legacy router re-export (compatibility only)
│   │   ├── schemas.py       # Legacy schema re-exports (compatibility only)
│   │   ├── core/
│   │   │   ├── security.py  # JWT + bcrypt + token revocation helpers
│   │   │   └── dependencies.py  # get_current_user, require_admin
│   │   └── services/
│   │       ├── auth_service.py  # register, login, forgot/reset password + rate limiting
│   │       ├── otp_service.py   # Redis-backed OTP create/verify
│   │       └── email_service.py # SMTP (placeholder — logs OTP to console)
│   ├── database/
│   │   ├── models.py        # All SQLAlchemy models (User, Question, Concept, Challenge, etc.)
│   │   ├── crud.py          # Async CRUD + IRT recalibration
│   │   ├── irt.py           # IRT math (update_theta, update_beta, next_difficulty, ZPD)
│   │   ├── concept_irt.py   # Per-concept IRT theta tracking with confidence
│   │   └── __init__.py
│   ├── routers/
│   │   ├── auth.py          # /api/auth routes (login, register, stats, concept-mastery)
│   │   ├── classic_room.py  # /api/rooms/classic routes
│   │   ├── challenge.py     # /api/rooms/challenge routes (V1 + V2 endpoints)
│   │   └── system.py        # /api/system routes (health, monitoring)
│   ├── services/
│   │   ├── llm.py           # Groq LLMClient (generate_mcq, generate_hint, simple_completion)
│   │   ├── session.py       # Redis session service (fallback: in-memory dict)
│   │   ├── classic_service.py    # Classic Room business logic (sessions, concepts, IRT)
│   │   ├── challenge_service.py  # Challenge Room business logic (streaks, levels, points)
│   │   ├── challenge_llm.py      # Challenge question generation with fallback
│   │   ├── concept_service.py    # Dynamic concept discovery with fuzzy matching
│   │   ├── concept_extractor.py  # LLM-based concept extraction from questions
│   │   ├── concept_cache_service.py  # Concept caching layer
│   │   ├── decay_service.py      # Inactivity decay for user theta (IMPLEMENTED)
│   │   ├── monitoring.py         # In-memory monitoring for rate limits and API errors
│   │   ├── log_aggregator.py     # Log aggregation service
│   │   └── question_cache_service.py  # Question caching
│   ├── rag/
│   │   ├── agentic.py       # 3-agent RAG orchestrator
│   │   ├── wikipedia.py     # Wikipedia context fetcher
│   │   ├── wikidata.py      # Wikidata SPARQL facts
│   │   └── hf_dataset.py    # HuggingFace dataset loader
│   ├── tests/               # Pytest test suite
│   │   ├── conftest.py      # Test fixtures
│   │   ├── test_adaptive_behavior.py
│   │   ├── test_auth_api.py
│   │   ├── test_challenge.py
│   │   ├── test_challenge_ranks.py
│   │   ├── test_classic_room_api.py
│   │   ├── test_concept_awareness.py
│   │   ├── test_hints.py
│   │   ├── test_irt.py
│   │   └── test_system_health.py
│   ├── scripts/             # Utility scripts
│   │   ├── decay_theta.py   # Manual theta decay script
│   │   └── cleanup_test_data.py
│   ├── seeds/
│   │   ├── seed.py          # Idempotent seed with schema migrations
│   │   ├── cleanup_questions.py
│   │   └── test_fixture.py
│   ├── alembic/             # Database migrations
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env                 # EXISTS and is configured (see Env section)
├── frontend/
│   ├── src/
│   │   ├── App.tsx          # Routes with ProtectedRoute/PublicRoute wrappers
│   │   ├── main.tsx
│   │   ├── config.ts        # API_BASE configuration
│   │   ├── types.ts         # TopicType, Question, QuizSessionState, MasteryLevel, etc.
│   │   ├── context/
│   │   │   ├── AuthContext.tsx   # JWT auth provider
│   │   │   └── DevModeContext.tsx  # Dev mode with difficulty/accuracy overrides
│   │   ├── pages/
│   │   │   ├── Home.tsx
│   │   │   ├── Login.tsx
│   │   │   ├── Signup.tsx
│   │   │   ├── ForgotPassword.tsx
│   │   │   ├── ResetPassword.tsx
│   │   │   ├── Dashboard.tsx
│   │   │   ├── Profile.tsx
│   │   │   ├── ClassicRoom.tsx
│   │   │   └── ChallengeRoom.tsx
│   │   ├── services/
│   │   │   ├── apiService.ts       # API calls for classic room and system
│   │   │   ├── challengeService.ts # API calls for Challenge Room V2
│   │   │   ├── errorTracking.ts    # Error tracking service
│   │   │   ├── logAggregator.ts    # Log aggregation
│   │   │   └── validation.ts       # Input validation
│   │   ├── components/
│   │   │   ├── InternalLayout.tsx
│   │   │   ├── ConceptMastery.tsx  # Concept mastery visualization
│   │   │   └── DevPanel.tsx        # Dev mode panel (dev only)
│   │   ├── types/
│   │   │   └── challenge.ts   # Challenge room types (Rank, ChallengeLevel, etc.)
│   │   └── styles/
│   ├── e2e/                 # Playwright E2E tests
│   ├── package.json
│   ├── vite.config.ts
│   ├── vitest.config.ts
│   ├── playwright.config.ts
│   ├── .env.local           # VITE_API_URL=http://localhost:8000
│   └── Dockerfile
├── docker-compose.yml       # postgres:5433, redis:6379, pgadmin:5050, redis-commander:8081
└── CLAUDE.md
```

## Backend Layout
`main.py` is now a thin entrypoint with:
- Auto-seed on startup (if database is empty)
- Request/response logging middleware
- Rate limiting with slowapi
- Global exception handler
- Structlog for structured logging

Routes are split into `backend/routers/`:
- `auth.py` — authentication + user stats + concept mastery
- `classic_room.py` — training mode gameplay
- `challenge.py` — competitive mode (V1 + V2 endpoints)
- `system.py` — health checks + monitoring

## API Endpoints

### System
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/api/system/health` | No | Health check (db + redis status) |
| GET | `/api/system/health/detailed` | No | Detailed health with latency, memory |
| GET | `/api/system/test-question` | No | Hardcoded test question |
| GET | `/api/system/monitoring/stats` | No | API statistics and error rates |
| GET | `/api/system/monitoring/rate-limits` | No | Recent rate limit hits |
| GET | `/api/system/monitoring/errors` | No | Recent API errors |

### Auth
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/auth/register` | No | Create account → JWT (rate-limited) |
| POST | `/api/auth/login` | No | Login → JWT (rate-limited 5/min per IP+email) |
| GET | `/api/auth/me` | Bearer | Current user info |
| POST | `/api/auth/logout` | Bearer | Revoke all user tokens |
| GET | `/api/auth/stats` | Bearer | User quiz statistics |
| GET | `/api/auth/stats/topic-breakdown` | Bearer | Per-topic stats |
| GET | `/api/auth/stats/daily-trend` | Bearer | Daily performance trend |
| GET | `/api/auth/stats/redis-ops` | Bearer | Redis session metrics |
| GET | `/api/auth/stats/concept-mastery` | Bearer | Per-concept theta breakdown |
| POST | `/api/auth/forgot-password` | No | Send OTP via Redis |
| POST | `/api/auth/reset-password` | No | Verify OTP + reset |

### Classic Room
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/rooms/classic/questions` | Bearer | RAG pipeline → MCQ |
| POST | `/api/rooms/classic/hints` | Bearer | LLM hint (no answer reveal) |
| POST | `/api/rooms/classic/answers` | Bearer | Submit answer, update theta |

### Challenge Room V1
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/api/rooms/challenge/status` | Bearer | User's current rank and stats |
| POST | `/api/rooms/challenge/start` | Bearer | Start a challenge match |
| POST | `/api/rooms/challenge/match/{id}/answer` | Bearer | Submit answer |

### Challenge Room V2 (Dynamic Levels + Streaks)
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/api/rooms/challenge/v2/status` | Bearer | Enhanced status with points/streaks |
| POST | `/api/rooms/challenge/v2/start` | Bearer | Start session with level selection |
| POST | `/api/rooms/challenge/v2/generate-question` | Bearer | Generate question at current level |
| POST | `/api/rooms/challenge/v2/submit-answer` | Bearer | Submit answer, get streak/level changes |
| GET | `/api/rooms/challenge/v2/session/{id}` | Bearer | Get session state |
| POST | `/api/rooms/challenge/v2/session/{id}/end` | Bearer | End session, get results |

## Environment (.env files already configured)
### backend/.env (EXISTS)
- DB: `postgresql+asyncpg://pfe:...@localhost:5433/adaptive_learning`
- Redis: `redis://:...@localhost:6379/0`
- JWT_SECRET_KEY: set (minimum 32 characters required)
- JWT_ALGORITHM: HS256
- ACCESS_TOKEN_EXPIRE_MINUTES: 30
- GROQ_API_KEY: set (gsk_...)
- GEMINI_API_KEY: set
- GOOGLE_CLIENT_ID: set
- DEV_BYPASS_AUTH: true (MUST be false in production)
- ENVIRONMENT: development
- LOG_LEVEL: INFO
- SMTP: not configured (OTPs logged to console)

### Feature Flags (backend/.env)
```bash
ENABLE_IDEMPOTENCY=true       # Spam prevention with submission state machine
ENABLE_CONCEPT_TRACKING=true  # Per-concept IRT theta tracking
ENABLE_CONCEPT_DISPLAY=true   # Show concept mastery in dashboard UI
DEV_BYPASS_AUTH=true          # Dev bypass tokens (NEVER in production)
```

### frontend/.env.local (EXISTS)
- VITE_API_URL=http://localhost:8000

## How to Run

### 1. Docker services (Postgres + Redis)
```bash
docker-compose up -d postgres redis
# Optional admin UIs:
docker-compose up -d pgadmin redis-commander
```

### 2. Backend
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate       # Windows
pip install -r requirements.txt
python main.py
# Runs on http://localhost:8000
# Auto-seeds database on first run if empty
```

### 3. Frontend
```bash
cd frontend
npm install
npm run dev
# Runs on http://localhost:5173
# Add ?dev=true to URL for dev panel (development only)
```

### 4. Run Tests
```bash
cd backend
pytest                        # All tests
pytest tests/test_irt.py -v   # Specific test file
pytest -k "adaptive" -v       # Tests matching keyword
```

## DB Tables (auto-created by SQLAlchemy on startup)

### Core Tables
- `users` — id(uuid), email, username, password_hash, points, level, elo_global, created_at, last_login, is_active, is_admin
- `user_responses` — tracks every answer (user_id, session_id, question_id, topic, difficulty_sent, answered_correct, time_taken, used_hint, created_at)
- `question_bank` — cached LLM-generated questions (question_text, correct_answer, options_json, explanation, hint, topic, difficulty_irt, discrimination, usage_count, times_seen, source, primary_concept_id)

### Concept Tracking Tables
- `concepts` — id, name, topic, description (e.g., "Egyptian Empire" under "history")
- `question_concepts` — N-to-M: links questions to concepts (question_id, concept_id, is_primary)
- `user_concept_theta` — per-user, per-concept ability tracking (user_id, concept_id, theta, theta_variance, response_count, last_updated, first_seen_at, exposure_count, mastery_level, concept_state)
- `user_concept_repeat_queue` — spaced repetition queue (user_id, concept_id, question_id, repeat_probability, due_after_session)

### Challenge Tables
- `challenge_ranks` — rank definitions (id, name, min_elo, n_options, has_timer, timer_seconds, levels_allowed, points_to_advance)
- `user_challenge_rank` — user's rank state (user_id, current_rank_id, wins, losses, skip_attempts_remaining, last_skip_at, rank_points, highest_streak, total_sessions)
- `challenge_matches` — match records (user_id, rank_id, questions_answered, score, time_taken, result, is_skip_attempt)
- `challenge_sessions` — V2 session tracking (user_id, match_id, topic, starting_level, current_level, rank_points, streak_correct, streak_wrong, highest_streak, total_questions, correct_answers, is_completed)
- `challenge_answers` — per-answer records (session_id, question_id, chosen_answer, is_correct, points_change, level_at_answer, time_taken)

### Session Tables
- `classic_sessions` — session tracking (user_id, topic, questions_answered, correct_count, created_at, ended_at)

## Critical Constants (config.py)
```python
# Quiz Settings
QUIZ_TIME_LIMIT_SECONDS = 30
QUIZ_QUESTIONS_PER_SESSION = 10

# Points System
POINTS_BASE_AWARD = 10
POINTS_TIME_BONUS_DIVISOR = 3    # bonus = seconds_remaining / 3
POINTS_HINT_PENALTY = 3
POINTS_WRONG_PENALTY = 5

# Inactivity Decay (IMPLEMENTED)
INACTIVITY_DECAY_DAYS = 14       # Start decay after 2 weeks
INACTIVITY_DECAY_FACTOR = 0.1    # 10% decay per period

# Session/Cache TTLs
SESSION_TTL_SECONDS = 3600       # 1 hour
IDEMPOTENCY_TTL_SECONDS = 3600
QUESTION_CACHE_TTL_SECONDS = 3600
SESSION_LOCK_TTL_SECONDS = 60

# Level Thresholds (points → level name)
# 5000+ = Master, 1500+ = Expert, 500+ = Scholar, 100+ = Apprentice, 0+ = Novice
```

### IRT Constants (database/irt.py + concept_irt.py)
```python
THETA_INIT = 0.0                 # Starting ability estimate
LEARN_RATE = 0.3                 # Gradient step size
THETA_RANGE = (-3.0, 3.0)        # Ability bounds
BETA_RANGE = (-3.0, 3.0)         # Difficulty bounds
VARIANCE_DECAY_FACTOR = 0.95     # Uncertainty decreases per response
MIN_RESPONSES_FOR_CONFIDENCE = 5 # Warm-up before trusting theta

# Zone of Proximal Development
ZPD_P_LOW = 0.60                 # Target P(correct) lower bound
ZPD_P_HIGH = 0.75                # Target P(correct) upper bound
```

### Challenge Constants (services/challenge_service.py)
```python
# Points by level: (correct_points, wrong_points)
CHALLENGE_POINTS_TABLE = {
    1: (3,  -1),   # Easy
    2: (5,  -2),   # Medium
    3: (7,  -4),   # Hard
    4: (9,  -6),   # Expert
    5: (11, -9),   # Master
}

# Streak thresholds
STREAK_UP_THRESHOLD = 4    # 4 correct → level up
STREAK_DOWN_THRESHOLD = 2  # 2 wrong → level down

# Rank level access
RANK_LEVEL_ACCESS = {
    "Bronze":   [1, 2],
    "Silver":   [1, 2, 3],
    "Gold":     [2, 3, 4],
    "Platinum": [3, 4, 5],
    "Diamond":  [4, 5],
}

# Rank point thresholds (cumulative)
RANK_THRESHOLDS = [
    (0,     "Bronze"),
    (1000,  "Silver"),
    (3000,  "Gold"),
    (7000,  "Platinum"),
    (15000, "Diamond"),
]
```

### Spaced Repetition (services/classic_service.py)
```python
WRONG_ANSWER_REPEAT_PROBABILITY = 0.25  # 25% queue after wrong
CORRECT_ANSWER_REPEAT_PROBABILITY = 0.01  # 1% queue after correct
REPEAT_DUE_SESSIONS = 7  # Show repeat after N sessions
```

## Key Design Decisions
1. **Concept-Level IRT** — Not just "History" but "Egyptian Empire" vs "Roman Empire"
2. **Session state in Redis** — keyed by `session:{session_id}`, 1hr TTL, falls back to in-memory dict
3. **IRT difficulty 1-5** maps to IRT β via breakpoints: [-1.5, -0.5, 0.5, 1.5]
4. **MCQ options are shuffled** — correct answer position is randomized
5. **Hints never reveal the answer** — LLM prompt strictly forbids it
6. **Spaced Repetition** — Wrong answers queued for repeat, correct rarely repeat
7. **Anti-Spam** — Idempotency keys + session locks + server-side timing
8. **Dev Bypass** — `Authorization: Bearer dev-bypass-{user_id}` for testing
9. **Inactivity Decay** — Theta decays toward 0 after 14 days of inactivity
10. **Dynamic Challenge Levels** — Streaks trigger automatic level changes
11. **Auto-Seed** — Database auto-populates on first startup if empty
12. **Security Validation** — `validate_security_config()` fails fast on insecure settings

## Testing

### Dev Auth Bypass
```bash
# Enable in backend/.env
DEV_BYPASS_AUTH=true

# Use in requests
curl -H "Authorization: Bearer dev-bypass-550e8400-e29b-41d4-a716-446655440000" \
  http://localhost:8000/api/auth/me
```

### Dev Mode (Frontend)
```
http://localhost:5173?dev=true
```
Opens a dev panel with:
- Difficulty override (1-5)
- Accuracy override (0-100%)
- Skip timer option

### Test Users (created via seed.py)
- User A: Geography expert, History novice
- User B: History expert, Geography novice
- User C: New user, no history
- User D: Diamond rank challenger
- User E: Inactive user (for decay testing)

### Running Tests
```bash
cd backend
pytest                              # All tests
pytest tests/test_irt.py -v         # IRT tests
pytest tests/test_challenge.py -v   # Challenge tests
pytest -k "concept" -v              # Concept-related tests
```

## Architecture Decisions
- **Structlog** for structured JSON logging in production
- **Rotating file handlers** for logs (5MB max, 5 backups)
- **Monitoring service** tracks rate limits and errors in-memory
- **Request ID** in response headers for debugging
- **CORS** configured for development origins (configure for production)
- **Alembic** for database migrations (manual for schema changes)

## Ports
| Service | Port |
|---------|------|
| Backend (FastAPI) | 8000 |
| Frontend (Vite) | 5173 |
| PostgreSQL | 5433 (host) → 5432 (container) |
| Redis | 6379 |
| pgAdmin | 5050 |
| Redis Commander | 8081 |

## Known Issues / TODO
- [ ] **E2E Tests**: Playwright setup exists but incomplete
- [ ] **Rank 5 Typed Answers**: Diamond rank should require typing, not MC
- [ ] **SMTP Configuration**: Currently logs OTPs to console instead of sending email
- [ ] **Production CORS**: Currently allows localhost origins only
