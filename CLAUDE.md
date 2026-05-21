# CLAUDE.md

## Runtime Scope (Strict)

Use only active project sources in this repository:

- backend/
- frontend/
- docs/
- admin_dashboard.html
- admin_server.py

Treat these as archive/reference only (not runtime authority):

- REFRENCE/
- oldstate/

## Project Summary

AdaptIQ is an adaptive learning platform with four room types:

- Classic: adaptive training flow with server-side session/question state.
- Challenge: level/streak/rank progression with 5 difficulty tiers.
- Custom: topic-focused learning with concept tracking and strict session binding.
- PvP: 1v1 matchmaking with Elo rating and progressive question reveal.

Core stack:

- Backend: FastAPI, SQLAlchemy async, PostgreSQL, Redis, Pydantic v2.
- Frontend: React 19, TypeScript, Vite.
- LLM/RAG: Groq LLM client + optional agentic RAG pipeline.
- Governance: Keyword-based content blocking + audit logging (feature-flagged via ENABLE_TRUSTWORTHY_GENERATION).

## Active Structure

- backend/main.py: app lifespan, middleware, router registration, health route.
- backend/config.py: env-driven settings + startup security validation.
- backend/routers/: auth, classic_room, challenge, custom, onboarding, admin, governance, pvp.
- backend/services/: room logic, session management, monitoring, LLM helpers, governance.
- backend/database/: SQLAlchemy models + IRT helpers.
- backend/schemas/: Pydantic request/response models (classic.py, challenge.py, custom.py, pvp.py).
- backend/scripts/: operational scripts (seeding/history/population utilities).
- backend/tests/: pytest tests + live/standalone integration scripts.
- frontend/src/App.tsx: route map.
- frontend/src/context/AuthContext.tsx: auth bootstrap/login/logout storage behavior.
- frontend/src/services/: per-room API clients (apiService, adminService, challengeService, customService, pvpService).

## Local Ports

- Frontend dev server: http://localhost:3000
- Backend API: http://localhost:8000
- Backend docs: http://localhost:8000/docs
- Admin static dashboard server: http://localhost:9000
- Docker PostgreSQL host port: 5433
- Docker Redis host port: 6379

## Runbook

From repo root:

1. Infrastructure (optional via Docker):

```powershell
Set-Location backend
docker compose -f docker-compose.yml up -d
```

2. Backend:

```powershell
Set-Location backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

3. Frontend:

```powershell
Set-Location frontend
npm install
npm run dev
```

4. Admin dashboard (optional):

```powershell
Set-Location ..
python admin_server.py
```

## API Prefix Map (Current Source)

All API routes use `/api/` prefix (no version segment):

- Auth: /api/auth
- Classic: /api/rooms/classic
- Challenge: /api/challenge
- Custom: /api/custom
- Onboarding: /api/onboarding
- PvP: /api/pvp
- Admin: /api/admin
- Governance: /api/admin/governance
- Health: /health

## Endpoint Snapshot

Auth (/api/auth):

- POST /signup
- POST /login
- GET /me
- GET /profile
- GET /stats
- GET /stats/daily-trend
- POST /forgot-password
- POST /reset-password
- POST /bootstrap-admin

Classic (/api/rooms/classic):

- POST /questions
- POST /hints
- POST /answers

Challenge (/api/challenge):

- GET /user/{user_id}/rank
- POST /start-session
- GET /session/{session_id}
- PATCH /session/{session_id}/change-level
- POST /generate-question
- POST /submit-answer
- POST /session/{session_id}/end

Custom (/api/custom):

- GET /topics
- GET /concepts/{topic}
- GET /user/{user_id}/concept-mastery
- POST /start-session
- POST /generate-question
- POST /generate-hint
- POST /submit-answer
- POST /session/{session_id}/end

Onboarding (/api/onboarding):

- GET /status
- POST /survey
- POST /skip
- POST /mark-tour-seen

PvP (/api/pvp):

- POST /join-queue
- DELETE /leave-queue
- GET /queue-status
- GET /match/{match_id}
- POST /match/{match_id}/answer
- POST /match/{match_id}/end
- GET /user/{user_id}/rating
- GET /leaderboard

Admin (/api/admin):

- GET /overview
- GET /top-concepts
- GET /concepts
- GET /concepts/{concept_id}
- GET /users
- GET /users/{user_id}
- PATCH /users/{user_id}
- GET /questions
- GET /sessions
- GET /db/schema
- GET /db/table/{table_name}
- GET /monitoring

Governance (/api/admin/governance):

- GET /blocked-rules
- POST /blocked-rules
- PATCH /blocked-rules/{rule_id}
- DELETE /blocked-rules/{rule_id}
- GET /audits

## Security And Integrity Rules (Current Behavior)

- JWT auth is required across protected routes via get_current_user.
- User-scoped endpoints enforce ownership checks (403 on mismatch).
- Classic uses server-side current-question state for answer verification.
- Challenge tracks issued question IDs per session and rejects unissued submissions.
- Challenge uses session.current_level (not client-provided level) for question generation.
- Custom submit-answer rejects question IDs not issued for that session (409).
- PvP get-match returns only one unanswered question at a time (progressive reveal).
- PvP submit-answer validates question_id against server match payload index.
- PvP end-match validates caller is a match participant and is idempotent on replay.
- Admin endpoints require is_admin=True; localhost GET bypass allowed in dev only.
- Governance endpoints require admin privileges for all CRUD operations.
- Admin bootstrap is disabled in production (ENVIRONMENT=production blocks it).
- Global exception handler returns generic error detail in production.
- All datetime usage is timezone-aware: datetime.now(timezone.utc) (no deprecated utcnow).
- Password hashing uses bcrypt with 12 rounds (no passlib dependency).
- OTP reset codes are rate-limited (5/min) with 3-attempt lockout.

## Known Limitations

- **SMTP not implemented**: Password reset OTP is generated and stored in Redis but never emailed. In dev mode the code is logged to console. See comment in routers/auth.py forgot-password endpoint.
- **No Alembic migrations**: Schema changes use AUTO_CREATE_TABLES=true (dev only). Production must use proper migrations.

## Frontend Contracts

- API base: frontend/src/config.ts -> VITE_API_URL fallback http://localhost:8000.
- Route guards: ProtectedRoute and AdminRoute in frontend/src/components/RouteGuards.tsx.
- Canonical localStorage user key: adaptiq_user_id.
- Legacy user_id is migrated/cleared in active auth/service flows.
- Auth token key: adaptiq_token.

## Test And Verification Commands

Backend pytest baseline:

```powershell
Set-Location backend
python -m pytest -q tests
```

Comprehensive API script (requires running backend):

```powershell
Set-Location backend
python tests/e2e_test.py
```

Focused regressions:

```powershell
Set-Location backend
python -m pytest -q tests/test_pvp_admin_regressions.py tests/test_security_regressions.py
```

Frontend type/lint/build checks:

```powershell
Set-Location frontend
npm run lint
npm run build
```

## Test User Workflow (Non-Destructive)

Seed deterministic profiles:

```powershell
Set-Location backend
python scripts/setup_test_users.py
```

Important:

- Default behavior is profile-only seeding.
- Synthetic sample history is opt-in with --with-sample-history.

Generate real API-backed history for all seeded users:

```powershell
Set-Location backend
python scripts/generate_real_test_user_history.py
```

Safety guarantees for real-history script:

- No table truncation.
- No Redis flush/reset.
- Appends normal gameplay history only through live APIs.

Generated outputs:

- backend/generated/test_users.json
- backend/generated/test_users.csv
- backend/generated/real_test_user_history_report.json

## Environment Variables (.env)

Key variables (see backend/.env for full list):

- DATABASE_URL: PostgreSQL async connection string
- REDIS_URL: Redis connection string
- JWT_SECRET_KEY: Must be ≥32 chars, unique per environment
- ADMIN_BOOTSTRAP_KEY: Secret key for /api/auth/bootstrap-admin (dev only)
- GROQ_API_KEY / GEMINI_API_KEY: LLM provider keys
- ENABLE_TRUSTWORTHY_GENERATION: Toggle governance layer (true/false)
- ENABLE_CONCEPT_TRACKING: Toggle concept-level IRT tracking
- CUSTOM_ROOM_SIMPLE_MODE: Simplified custom room mode
- ENVIRONMENT: "development" or "production"
- DEV_BYPASS_AUTH: Must be false in production

## Practical Notes

- backend/dependencies.py exports only the rate limiter; active routers use dependency providers from backend/routers/auth.py and per-router helpers.
- Ensure .env values align with your runtime (especially DATABASE_URL vs Docker port mapping).
- If backend fails to start with exit code 1, check for port collisions on 8000 before deeper debugging.
- The REFRENCE/ directory contains the original project skeleton and is NOT used at runtime.
