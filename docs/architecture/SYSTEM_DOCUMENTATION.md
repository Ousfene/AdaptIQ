# AdaptIQ — System Documentation

## 1. Architecture Overview

AdaptIQ is an adaptive quiz platform built for a final year project (Bachelor's degree). It uses Item Response Theory (IRT) to personalize question difficulty per user and per concept.

### Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Backend | FastAPI (Python 3.11+) | REST API server |
| Database | PostgreSQL 16 | Persistent storage |
| Cache | Redis 7 | Session management, OTP storage, question cache |
| LLM | Groq (Llama 3.1-8B) | Question and hint generation |
| Frontend | React 19 + Vite + TypeScript | User interface |
| ORM | SQLAlchemy 2.0 (async) | Database access |
| Migrations | Alembic | Schema versioning |
| Auth | JWT (HS256) + bcrypt | Authentication |

### System Diagram

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  React/Vite │────▶│  FastAPI      │────▶│ PostgreSQL  │
│  Port 3000  │     │  Port 8000    │     │ Port 5432   │
└─────────────┘     └──────┬───────┘     └─────────────┘
                           │
                    ┌──────▼───────┐     ┌─────────────┐
                    │    Redis     │     │  Groq API   │
                    │  Port 6379   │     │  (LLM)      │
                    └──────────────┘     └─────────────┘
```

## 2. Room Types

### Classic Room (`/api/rooms/classic`)
- **Purpose**: Core adaptive learning environment
- **Difficulty**: IRT-based (theta tracks per-concept ability)
- **Features**: Concept tracking, repeat queue, hints
- **Session Flow**: Start → Question → Answer → IRT Update → Next Question

### Challenge Room (`/api/challenge`)
- **Purpose**: Competitive difficulty with streaks
- **Difficulty**: 5 levels (1-5), streak-based advancement
- **Rules**: 4 correct → level up, 2 wrong → level down
- **Ranking**: E → D → C → B → A (point thresholds)

### Custom Room (`/api/custom`)
- **Purpose**: Topic-focused mastery
- **Difficulty**: Concept-oriented with fact-based progress
- **Features**: Topic catalogue, concept mastery tracking

### PvP Room (`/api/pvp`)
- **Purpose**: 1v1 competitive matches
- **Matchmaking**: Elo-based with concept affinity
- **Flow**: Join queue → Match → Same quiz for both → Score → Elo update
- **Rating**: Standard Elo (K=32 new, K=16 experienced)

## 3. Database Schema

### Core Tables
- `users` — Registered users with auth and progression data
- `user_responses` — Every answer submitted (drives IRT recalibration)
- `question_bank` — Cached questions with IRT difficulty parameters

### Concept Tables
- `concepts` — Named concepts (e.g. "Ancient Egypt")
- `question_concepts` — Many-to-many link between questions and concepts
- `user_concept_theta` — Per-user, per-concept ability estimate
- `user_concept_repeat_queue` — Questions queued for re-testing

### Challenge Tables
- `challenge_sessions` — Active/completed challenge sessions
- `challenge_answers` — Per-question answers in challenge sessions
- `challenge_rankings` — Global ranking per user

### Custom Room Tables
- `custom_sessions` — Custom room sessions
- `custom_answers` — Per-question answers
- `custom_topic_mastery` — Per-user topic mastery percentages
- `custom_fact_progress` — Individual fact learning progress

### PvP Tables
- `pvp_matchmaking_queue` — Players waiting for opponents
- `pvp_matches` — Active/completed 1v1 matches
- `pvp_match_answers` — Per-player answers per match
- `pvp_ratings` — Elo ratings and match stats

### Onboarding Tables
- `user_onboarding_flags` — First login, tour seen, onboarding completed
- `user_onboarding_topics` — Survey responses (confident/want-to-learn)

## 4. API Endpoints

### Auth (`/api/auth`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /signup | Register new user |
| POST | /login | Login, returns JWT |
| GET | /me | Current user profile |
| GET | /profile | Profile (alias for /me) |
| POST | /forgot-password | Request reset OTP |
| POST | /reset-password | Reset with OTP |
| POST | /bootstrap-admin | Promote to admin |

### Classic Room (`/api/rooms/classic`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /questions | Generate adaptive question |
| POST | /hints | Get study hint |
| POST | /answers | Submit answer |

### Challenge Room (`/api/challenge`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /rank | Get user rank |
| POST | /sessions | Start session |
| GET | /sessions/{id} | Get session details |
| POST | /questions | Generate question |
| POST | /answers | Submit answer |
| POST | /sessions/{id}/end | End session |

### PvP Room (`/api/pvp`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /join-queue | Join matchmaking |
| DELETE | /leave-queue | Leave queue |
| GET | /queue-status | Poll for match |
| GET | /match/{id} | Match details |
| POST | /match/{id}/answer | Submit answer |
| POST | /match/{id}/end | End match |
| GET | /user/{id}/rating | PvP rating |
| GET | /leaderboard | Top players |

### Admin (`/api/admin`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /overview | System stats |
| GET | /top-concepts | Most-tracked concepts |
| GET | /users | Paginated user list |
| GET | /users/{id} | User detail + mastery |
| PATCH | /users/{id} | Toggle active/admin |
| GET | /questions | Question list |
| GET | /sessions | Session list |
| GET | /monitoring | System monitoring |

## 5. IRT (Item Response Theory)

The system uses the **1-Parameter Logistic (1PL)** model:

```
P(correct | θ, β) = 1 / (1 + exp(-(θ - β)))
```

- **θ (theta)**: User ability estimate (per concept)
- **β (beta)**: Question difficulty parameter

After each answer:
1. θ is updated based on correctness and current β
2. β is recalibrated via MLE approximation
3. θ change is larger when θ and β are close (maximum information)

### ZPD Targeting
Questions are selected from the **Zone of Proximal Development**:
- Target β is within ±1 standard deviation of θ
- This ensures 50-70% expected accuracy (optimal learning zone)

## 6. Configuration

All settings are in `.env` (loaded by `config.py`):

| Variable | Description | Default |
|----------|-------------|---------|
| DATABASE_URL | PostgreSQL connection | localhost:5432 |
| REDIS_URL | Redis connection | localhost:6379 |
| GROQ_API_KEY | LLM API key | (required) |
| JWT_SECRET_KEY | JWT signing secret | (change this) |
| DEV_BYPASS_AUTH | Skip auth (dev only) | false |
| ENABLE_CONCEPT_TRACKING | Track per-concept theta | true |
| AUTO_CREATE_TABLES | Auto-create on startup | true |

## 7. Running Locally

```bash
# 1. Start infrastructure (PostgreSQL + Redis)
docker-compose up -d postgres redis

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Run migrations
alembic upgrade head

# 4. Start backend
python main.py
# or: uvicorn main:app --reload --port 8000

# 5. Start frontend (separate terminal)
cd ../frontend
npm install
npm run dev
```

# 6. Seed test users and sample room state (separate terminal from `backend/`)
```bash
python create_test_user.py
```

## 8. Postman Collection

Import `AdaptIQ_Complete_Postman.json` into Postman.

**Setup:**
1. Set `base_url` variable to `http://localhost:8000`
2. Run Auth → Signup, then Auth → Login (auto-sets `auth_token`)
3. Run folders in order: Auth → Onboarding → Classic → Challenge → Custom → PvP → Admin

## 9. File Structure

```
backend/
├── main.py                    # FastAPI app, lifespan, middleware
├── config.py                  # Environment config
├── bcrypt_utils.py            # Password hashing
├── dependencies.py            # Rate limiter, shared deps
├── schemas.py                 # Classic Room Pydantic models
├── pydantic_*.py              # Per-room Pydantic models
├── database/
│   ├── models.py              # User, UserResponse, QuestionBank
│   ├── concept_models.py      # Concept, QuestionConcept, UserConceptTheta
│   ├── challenge_models.py    # ChallengeSession, ChallengeAnswer, Ranking
│   ├── custom_models.py       # CustomSession, CustomAnswer, Mastery
│   ├── onboarding_models.py   # Onboarding flags, topics
│   ├── pvp_models.py          # PvP matches, ratings, queue
│   ├── irt.py                 # IRT math functions
│   └── crud.py                # CRUD operations
├── routers/
│   ├── auth.py                # Auth (signup, login, password reset)
│   ├── classic_room.py        # Classic Room endpoints
│   ├── challenge.py           # Challenge Room endpoints
│   ├── custom.py              # Custom Room endpoints
│   ├── pvp.py                 # PvP Room endpoints
│   ├── onboarding.py          # Onboarding endpoints
│   └── admin.py               # Admin dashboard endpoints
├── services/
│   ├── llm.py                 # Groq LLM client
│   ├── session.py             # Redis session management
│   ├── classic_service.py     # Classic Room business logic
│   ├── challenge_service.py   # Challenge Room business logic
│   ├── custom_service.py      # Custom Room business logic
│   ├── pvp_service.py         # PvP matchmaking + Elo
│   ├── concept_service.py     # Concept discovery
│   ├── concept_irt.py         # Per-concept IRT
│   ├── question_cache_service.py # Question difficulty cache
│   ├── onboarding_service.py  # Onboarding logic
│   └── monitoring.py          # API metrics
├── rag/
│   ├── agentic.py             # 3-agent RAG pipeline
│   ├── wikipedia.py           # Wikipedia retriever
│   ├── wikidata.py            # Wikidata retriever
│   └── hf_dataset.py          # HuggingFace dataset retriever
├── seeds/
│   └── seed.py                # Database seeding
├── alembic/
│   ├── env.py                 # Alembic config
│   └── versions/              # Migration files
└── docker-compose.yml         # Infrastructure services

frontend/
├── src/
│   ├── App.tsx                # Routes
│   ├── config.ts              # API base URL
│   ├── main.tsx               # Entry point
│   ├── vite-env.d.ts          # Vite type declarations
│   ├── pages/                 # Page components
│   ├── components/            # Shared components
│   ├── services/              # API client functions
│   ├── context/               # Auth context
│   ├── styles/                # CSS files
│   └── types/                 # TypeScript type definitions
└── package.json
```

## 10. Admin Dashboard

Local development monitoring dashboard for system statistics, user activity, and data inspection. Requires no authentication (local-only access).

### Quick Start

**Option 1: Python Server (Recommended)**
```bash
python admin_server.py
# Auto-opens http://localhost:9000
```

**Option 2: Direct HTML**
Open `admin_dashboard.html` in browser (no server needed, but auto-refresh may be limited)

### Features

| Section | Description |
|---------|-------------|
| **Overview Cards** | Total users, questions, active sessions, unique concepts, PvP matches, hourly activity |
| **Top Concepts** | Top 10 concepts by tracked users, sorted by engagement (theta values) |
| **Recent Users** | Last 20 users with email, username, points, level, admin/active flags, signup/last_active timestamps |
| **Question Bank** | Last 15 questions with text, difficulty, times_seen, usage_count, source, last_served |
| **System Health** | Status checks for database connection, Redis connection, core tables |
| **Raw Data Inspector** | View raw JSON response from any endpoint (debug mode) |
| **Auto-Refresh** | Updates every 30 seconds; configurable API base URL |

### API Endpoints

Dashboard calls these read-only admin endpoints (defined in `routers/admin.py`):

```
GET /api/admin/overview        → System statistics
GET /api/admin/top-concepts    → Top 10 concepts by engagement
GET /api/admin/users           → User list paginated
GET /api/admin/questions       → Question bank paginated
```

### Configuration

- **API Base URL**: Configure at top of dashboard (defaults to `http://localhost:8000`)
- **Auto-Refresh Interval**: Hardcoded to 30 seconds (edit HTML line containing `setInterval(fetchData, 30000)`)
- **Port**: Admin server runs on `9000` (separate from backend `8000`, frontend `3000`)
- **Test users**: See [TEST_USERS.md](TEST_USERS.md) for seeded accounts and credentials

### Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| **No data loading** | Backend down or wrong API URL | Check backend is running; verify API URL input at top |
| **CORS errors** | Browser security policy | Use Python server option; direct HTML file may have restrictions |
| **Outdated data** | Auto-refresh timer | Manual refresh button in UI; or set auto-refresh to shorter interval |
| **Connection timeout** | Backend unreachable | Check `config.py` DATABASE_URL and REDIS_URL settings |
| **Empty tables** | No data in database | Run seeding: `python scripts/populate_questions.py` |

### Files

- `admin_dashboard.html` – Complete UI (HTML/CSS/JavaScript, single file, ~450 lines)
- `admin_server.py` – HTTP server wrapper on port 9000 (~40 lines)
- `ADMIN_DASHBOARD_README.md` – Detailed setup and feature guide

## 11. Code-Audited Current State (2026-04-14)

This section is derived from source code inspection and local test execution, not from historical docs.

### Verified endpoint map (source-of-truth)

- Auth router prefix: `/api/auth`
- Classic router prefix: `/api/rooms/classic`
- Challenge router prefix: `/api/challenge`
- Custom router prefix: `/api/custom`
- PvP router prefix: `/api/pvp`
- Onboarding router prefix: `/api/onboarding`
- Admin router prefix: `/api/admin`

Challenge endpoints currently implemented:

- `GET /api/challenge/user/{user_id}/rank`
- `POST /api/challenge/start-session`
- `GET /api/challenge/session/{session_id}`
- `PATCH /api/challenge/session/{session_id}/change-level`
- `POST /api/challenge/generate-question`
- `POST /api/challenge/submit-answer`
- `POST /api/challenge/session/{session_id}/end`

### Test reality snapshot

- `python -m py_compile` across backend project files: clean
- `python -m pytest -q --ignore tests/e2e_test.py --ignore tests/test_live_room_harvest.py --ignore tests/test_live_room_harvest_direct.py --ignore tests/test_live_room_harvest_randomized.py`: 27 passed, 9 skipped
- `tests/e2e_test.py` requires a running backend on localhost:8000 and fails in collection when server is not running
- New targeted regression coverage added in `backend/tests/test_pvp_admin_regressions.py` for PvP payload integrity, Elo fairness replay math, and admin guard/session validation.

### Confirmed code issues and minimal fixes

1. Critical: PvP end-match authorization gap
       - File: `backend/services/pvp_service.py`
       - Issue: `end_match()` does not verify requester belongs to match participants.
       - Impact: Any authenticated user can finalize someone else's match.
       - Fix: Validate `user_id in {match.user1_id, match.user2_id}` and return 403/ValueError otherwise.

2. Critical: PvP Elo can be applied multiple times
       - File: `backend/services/pvp_service.py`
       - Issue: `end_match()` recomputes and reapplies Elo even when match is already completed.
       - Impact: Duplicate rating drift when endpoint is called repeatedly.
       - Fix: Make rating settlement idempotent (e.g., if `match.status == "completed"` and ratings already applied, return existing result only).

3. High: Classic session max-question cap can be bypassed
       - Files: `backend/services/classic_service.py`, `backend/routers/classic_room.py`
       - Issue: final answered question is not persisted to `questions_asked` before completion path, and `/questions` does not enforce finished state.
       - Impact: session can continue beyond intended max questions.
       - Fix: persist final session state and enforce an explicit `is_finished` guard before generating more questions.

4. High: Classic answer index bounds not validated
       - Files: `backend/schemas.py`, `backend/routers/classic_room.py`, `backend/services/classic_service.py`
       - Issue: `selected_index` has no bounds checks; negative/non-range values can cause wrong indexing or 500.
       - Fix: constrain schema and re-check against option list length server-side.

5. High: Challenge submit-answer lacks session-issued question binding
       - File: `backend/routers/challenge.py`
       - Issue: submit path verifies existence of question and duplicate answer, but not that question was issued to that challenge session.
       - Impact: progression integrity risk if arbitrary known question IDs are submitted.
       - Fix: track issued question IDs per challenge session and reject submissions not in issued set.

6. High: JWT secret security checks incomplete
       - File: `backend/config.py`
       - Issue: `validate_security_config()` does not enforce non-default/non-weak `JWT_SECRET_KEY`.
       - Impact: production misconfiguration can enable token forgery.
       - Fix: fail startup when secret is default, empty, or below configured minimum length.

7. Medium: Exception responses leak internal error class names
       - File: `backend/main.py`
       - Issue: global exception handler returns `{ExceptionType}: {message}` in response detail.
       - Fix: return generic message in production and keep detailed type only in logs.

8. Medium: Admin debug endpoint bypasses admin auth
       - File: `backend/routers/admin.py`
       - Issue: `/api/admin/test-endpoint` has no auth/admin guard.
       - Fix: remove endpoint or protect with `_require_admin(current)` dependency.

9. Medium: Admin sessions endpoint behavior mismatch
       - File: `backend/routers/admin.py`
       - Issue: no PvP branch, independent pagination per source, then global slice.
       - Fix: add PvP session branch and apply pagination after merging/sorting all requested session types.

10. Medium: PvP answer payload integrity gap
        - File: `backend/services/pvp_service.py`
        - Issue: answer correctness is derived from `question_index` while persisted `question_id` is client supplied and not cross-checked.
        - Fix: verify `question_id == questions[question_index]["id"]` before storing.

11. Medium: PvP Elo K-factor depends only on user1
        - File: `backend/services/pvp_service.py`
        - Issue: Elo delta magnitude is computed once using `rating1.total_matches` and mirrored to user2.
        - Fix: compute each player's delta using that player's own K-factor.

12. Low: Custom generation feature flag logic is contradictory
        - File: `backend/routers/custom.py`
        - Issue: both `if not CUSTOM_REQUIRE_RAG_GENERATION` and post-RAG hard raise keep non-RAG fallback paths unreachable.
        - Fix: align flag branches so disabling strict RAG actually enables static fallback path.

### Remediation status update (2026-04-14)

Implemented in code:

- Issue 1 fixed: PvP end-match requester is now validated as a match participant.
- Issue 2 fixed: PvP end-match settlement is idempotent for already-completed matches.
- Issue 3 fixed: Classic sessions now persist finished state and `/questions` blocks continued generation.
- Issue 4 fixed: Classic selected index has schema + service-level bounds validation.
- Issue 5 fixed: Challenge submit-answer now rejects question IDs not issued for that session.
- Issue 6 fixed: startup fails on empty/short/default JWT secret in production; warns on default secret in non-production.
- Issue 7 fixed: global exception responses are generic outside development.
- Phase 2 anti-cheat completed: Challenge and Custom `generate-question` now return blank `explanation` until submit; `submit-answer` remains the reveal point.
- Issue 8 fixed: admin debug endpoint now enforces admin auth.
- Issue 9 fixed: admin sessions endpoint now supports challenge/custom/pvp with merged global sort and pagination.
- Issue 10 fixed: PvP submit-answer now verifies `question_id` matches the server-issued `question_index` payload.
- Issue 11 fixed: PvP Elo settlement now computes per-player delta using each player's own K-factor.
- Issue 12 fixed: Custom generation flag flow now allows fallback path when strict RAG mode is disabled.

Still pending from the list above:

- None.
