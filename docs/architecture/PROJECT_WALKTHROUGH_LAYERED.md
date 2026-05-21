# AdaptIQ Layered Project Walkthrough

## Purpose
This document walks through the whole project from a quick summary to deep technical behavior.

It is structured in layers so you can stop at the depth you need:
- Layer 0: 30-second summary
- Layer 1: architecture and runtime map
- Layer 2: user journeys (UI to API to DB)
- Layer 3: backend request lifecycle
- Layer 4: data model and persistence
- Layer 5: adaptive algorithms (IRT, Challenge scoring, Elo)
- Layer 6: security, anti-cheat, and integrity guards
- Layer 7: endpoint catalog
- Layer 8: operations, testing, and current caveats

## Scope And Canonical Sources
Canonical runtime sources are:
- Frontend: `frontend/src/*`
- Backend: `backend/*`

Reference snapshots (`REFRENCE/*`, `oldstate/*`) are not the active runtime.

---

## Layer 0: Quick Summary
AdaptIQ is an adaptive learning platform with 4 learning/game modes:
- Classic Room: concept-aware adaptive training
- Challenge Room: rank and streak based progression
- Custom Room: topic-focused learning with concept mastery
- PvP Room: real-time 1v1 with Elo ratings

High-level stack:
- Frontend: React + Vite + TypeScript
- Backend: FastAPI + SQLAlchemy async
- Storage: PostgreSQL + Redis (with in-memory fallback paths)
- AI: Groq LLM + optional agentic RAG retrieval

Core platform guarantees:
- JWT-protected APIs for authenticated flows
- Session binding guards (prevents cross-session answer replay)
- Anti-leak behavior (correct answers hidden before submission)
- Admin analytics and monitoring endpoints

---

## Layer 1: Architecture Map

### 1.1 Frontend Runtime
Entry and routing:
- `frontend/src/main.tsx`: mounts `AuthProvider`, `BrowserRouter`, `App`
- `frontend/src/App.tsx`: route table and route protection
- `frontend/src/components/RouteGuards.tsx`: `ProtectedRoute` and `AdminRoute`

Routes:
- Public: `/`, `/login`, `/signup`, `/forgot-password`, `/reset-password`
- Auth-only: `/dashboard`, `/rooms/classic`, `/rooms/challenge`, `/rooms/custom`, `/rooms/pvp`, `/profile`
- Admin-only: `/admin`

API base and auth headers:
- `frontend/src/config.ts`: `API_BASE = VITE_API_URL ?? http://localhost:8000`
- `frontend/src/services/http.ts`: injects `Authorization: Bearer <token>` from localStorage

### 1.2 Backend Runtime
Startup and lifecycle:
- `backend/main.py`:
  - validates security config at startup
  - initializes DB engine/session factory
  - initializes Redis, HTTP client, LLM client, RAG pipeline, SessionService
  - installs middleware and exception handlers
  - includes all routers

Routers included:
- Auth: `/api/auth`
- Classic: `/api/rooms/classic`
- Challenge: `/api/challenge`
- Custom: `/api/custom`
- Onboarding: `/api/onboarding`
- Admin: `/api/admin`
- PvP: `/api/pvp`
- Health: `/health`

### 1.3 Data And Service Boundaries
Primary services and responsibilities:
- `services/session.py`: Redis/in-memory session state for quiz flow
- `services/classic_service.py`: classic concept selection, question selection, answer processing
- `services/challenge_service.py`: challenge scoring, streaks, rank updates
- `services/pvp_service.py`: queue, match state, answer validation, Elo
- `services/onboarding_service.py`: onboarding status and survey persistence
- `services/llm.py`: MCQ generation and hint generation
- `rag/agentic.py`: Router/Retriever/Validator RAG orchestration
- `services/monitoring.py`: request/error/rate-limit counters

---

## Layer 2: User Journeys (End To End)

## 2.1 Visitor Journey (No Login Yet)

### A) Landing
1. User enters `/`.
2. `Home.tsx` renders the marketing + CTA experience.
3. CTA navigates to `/signup` or `/login`.

### B) Signup
1. `Signup.tsx` validates fields.
2. Frontend calls `POST /api/auth/signup`.
3. Backend checks uniqueness, hashes password, creates user, returns JWT + user.
4. Frontend stores:
   - `adaptiq_token`
   - `adaptiq_user_id`
   - `adaptiq_user`
5. User is redirected to `/dashboard`.

### C) Login
1. `Login.tsx` calls `POST /api/auth/login`.
2. Backend validates credentials and updates `last_login`.
3. Frontend stores token/user and redirects to `/dashboard`.

### D) Forgot/Reset Password
1. `ForgotPassword.tsx` calls `POST /api/auth/forgot-password`.
2. OTP is stored in Redis (or in-memory fallback) with TTL.
3. `ResetPassword.tsx` calls `POST /api/auth/reset-password` with email + code + new password.
4. Backend verifies OTP and updates password hash.

## 2.2 Auth Bootstrap On App Reload
1. `AuthProvider` loads cached user from localStorage.
2. `refreshUser()` calls `GET /api/auth/me` using token.
3. If token invalid/expired: logout and clear local/session storage.
4. If valid: user state is refreshed and route guards allow protected screens.

## 2.3 Dashboard + Onboarding
1. User reaches `/dashboard`.
2. Dashboard calls onboarding APIs:
   - `GET /api/onboarding/status?user_id=...`
   - `POST /api/onboarding/survey` on completion
   - `POST /api/onboarding/skip` on skip
   - `POST /api/onboarding/mark-tour-seen` after tour
3. Backend creates onboarding flags row if missing and updates flags/topics.

Important current behavior note:
- `AuthContext` stores user id under `adaptiq_user_id`, while `Dashboard.tsx` currently reads `user_id` on mount for onboarding status. This key mismatch can block onboarding fetch unless `user_id` is present from another path.

## 2.4 Classic Room Journey
Frontend API client:
- `frontend/src/services/apiService.ts`

Flow:
1. User opens `/rooms/classic`.
2. Frontend calls `POST /api/rooms/classic/questions`.
3. If no session id, backend starts a new classic session.
4. Backend selects concepts and target question (IRT-aware), then stores server-side current question payload.
5. Response hides `correctAnswer` (anti-cheat).
6. User may call `POST /api/rooms/classic/hints`.
7. User submits via `POST /api/rooms/classic/answers`.
8. Backend verifies against server-stored shuffled options (not client trust), updates concept theta, maybe queues repeats, and may return next question.

Classic anti-cheat and integrity:
- Answer grading uses server session state + stored shuffled options.
- Session ownership check prevents cross-user session usage.
- No correct answer exposed before submit.

## 2.5 Challenge Room Journey
Frontend API client:
- `frontend/src/services/challengeService.ts`

Flow:
1. On room entry, frontend calls `GET /api/challenge/user/{user_id}/rank`.
2. User selects allowed start level and starts session with `POST /api/challenge/start-session`.
3. Question generation via `POST /api/challenge/generate-question`.
4. Backend tracks issued question IDs per session (`challenge_session_questions:{session_id}`) and keeps explanation hidden pre-answer.
5. Submission via `POST /api/challenge/submit-answer`.
6. Backend validates submission, computes points and streak effects, may force level up/down.
7. Session closes via `POST /api/challenge/session/{session_id}/end`, updating global rank state.

Challenge anti-cheat and integrity:
- Session must belong to authenticated user.
- Duplicate question submissions are blocked.
- Answer details are revealed only after submit.

## 2.6 Custom Room Journey
Frontend API client:
- `frontend/src/services/customService.ts`

Flow:
1. User chooses History/Geography theme and starts with `POST /api/custom/start-session`.
2. Frontend requests questions via `POST /api/custom/generate-question`.
3. Backend strategy can involve:
   - existing DB bank selection (topic/concept/recent filters)
   - repeat queue reuse
   - LLM generation
   - RAG generation path (if enabled)
   - offline/template fallback in some geography cases
4. Backend stores issued question tracking for session integrity.
5. Hint request uses `POST /api/custom/generate-hint` and requires `question_id`.
6. Answer submission uses `POST /api/custom/submit-answer`.
7. Backend verifies question was issued for this session, updates topic mastery, and updates concept theta/queues when concept tracking is enabled.
8. End session via `POST /api/custom/session/{session_id}/end`.

Custom anti-cheat and integrity:
- `submit-answer` rejects non-issued question IDs (`409`).
- Correct answers are not exposed by `generate-question`.
- Explanation is intentionally empty before submit.

## 2.7 PvP Room Journey
Frontend API client:
- `frontend/src/services/pvpService.ts`

Flow:
1. Player joins queue with `POST /api/pvp/join-queue`.
2. Frontend polls `GET /api/pvp/queue-status` until matched.
3. Match details pulled from `GET /api/pvp/match/{match_id}`.
4. Each answer submitted via `POST /api/pvp/match/{match_id}/answer`.
5. Backend verifies:
   - user belongs to match
   - question index is valid
   - submitted `question_id` matches server question payload
   - duplicate submissions are rejected safely
6. Match completion via `POST /api/pvp/match/{match_id}/end`.
7. Elo changes are persisted and endpoint is idempotent for re-calls.

PvP rating policy (current product behavior):
- Any authenticated user can fetch any other user rating via `GET /api/pvp/user/{user_id}/rating`.
- Unknown valid UUID returns `404 User not found` (not 500).

## 2.8 Profile Journey
1. `/profile` calls `GET /api/auth/me`.
2. Then fetches concept mastery via `GET /api/custom/user/{user_id}/concept-mastery`.
3. User sees account + concept mastery snapshot.

## 2.9 Admin Journey
1. `AdminRoute` ensures `user.is_admin` before `/admin`.
2. Admin dashboard calls multiple endpoints:
   - overview
   - top concepts
   - users (and PATCH toggles)
   - questions
   - sessions (challenge/custom/pvp merged)
   - monitoring stats
3. Backend enforces admin role in every admin handler.

---

## Layer 3: Backend Request Lifecycle
Generic lifecycle for most protected endpoints:

1. Browser event triggers frontend service call.
2. `fetch()` sends request to `API_BASE + route` with JSON + Bearer token.
3. FastAPI app receives request.
4. Middleware chain runs:
   - CORS
   - SlowAPI middleware
   - request logging middleware with request id
5. Router dependency resolves DB session (`get_db`) and user (`get_current_user`) as needed.
6. Pydantic request model validates payload.
7. Router invokes service-layer function.
8. Service performs DB/Redis/LLM/RAG operations.
9. Commit/rollback is applied.
10. Response model serialization runs.
11. Request logs and monitoring counters are updated.
12. Response returns to frontend; UI state updates.

Error paths:
- 401: missing/invalid bearer token
- 403: authenticated user mismatch or role mismatch
- 404: missing entity (session, question, user, match)
- 409: conflict guards (already answered, onboarding already done, etc.)
- 422: validation/parsing errors
- 429: rate limit exceeded
- 500: unhandled server errors

---

## Layer 4: Data Model Deep Dive

Core entities:
- `users`: identity, credentials, progression fields, admin flag
- `question_bank`: canonical stored questions (topic, options, answer, difficulty_irt, source)
- `user_responses`: historical answer stream feeding adaptation

Concept adaptation entities:
- `concepts`: concept vocabulary
- `question_concepts`: links questions to concept IDs
- `user_concept_theta`: per-user per-concept ability state
- `user_concept_repeat_queue`: deferred repeats for weak spots

Mode-specific entities:
- Challenge:
  - `challenge_sessions`
  - `challenge_answers`
  - `challenge_ranking`
- Custom:
  - `custom_topics`
  - `custom_facts`
  - `custom_sessions`
  - `user_topic_mastery`
  - `user_fact_progress`
- Onboarding:
  - `user_onboarding_flags`
  - `user_onboarding_topics`
- PvP:
  - `pvp_matchmaking_queue`
  - `pvp_matches`
  - `pvp_match_answers`
  - `pvp_ratings`

State stores outside SQL:
- Redis (or in-memory fallback): session data, current question payloads, OTP, challenge issued question set, custom recency/signature caches.

---

## Layer 5: Adaptive And Competitive Algorithms

## 5.1 IRT (Classic + Concept Tracking)
1PL model (from `database/irt.py`):

$$
P(correct \mid \theta, \beta) = \frac{1}{1 + e^{-(\theta - \beta)}}
$$

Online theta update:

$$
\theta_{new} = \theta + \alpha (y - P(correct))
$$

Where:
- $\theta$: user ability
- $\beta$: question difficulty
- $y \in \{0,1\}$: observed correctness
- $\alpha$: learning rate

ZPD targeting:
- Question selection attempts a beta range where expected correctness is around 60-75%.
- Cold-start users get wider ranges.

Concept theta specifics (`services/concept_irt.py`):
- independent theta per concept
- confidence threshold after minimum response count
- mastery labels from theta bands

## 5.2 Challenge Scoring And Rank
Points table (`challenge_service.py`):
- L1: +3 / -1
- L2: +5 / -2
- L3: +7 / -4
- L4: +9 / -6
- L5: +11 / -9

Streak triggers:
- 4 consecutive correct: level up
- 2 consecutive wrong: level down

Rank thresholds:
- E: 0+
- D: 1000+
- C: 3000+
- B: 7000+
- A: 15000+

Level access is rank-clamped.

## 5.3 PvP Elo
Expected score and delta:

$$
E_a = \frac{1}{1 + 10^{(R_b - R_a)/400}}
$$

$$
\Delta R_a = K(S_a - E_a)
$$

Where:
- $S_a$: 1 win, 0 loss, 0.5 draw
- $K=32$ for new players (<30 matches), else $K=16$

Other PvP mechanics:
- matchmaking by topic compatibility + Elo window + concept overlap
- shared question payload for both players
- idempotent end-match responses (no double Elo application)

---

## Layer 6: Security, Integrity, And Anti-Cheat

Authentication and authorization:
- JWT bearer parsing in `routers/auth.py:get_current_user`
- User ownership checks in room APIs (body/query user id must match auth user where required)
- Admin role checks in `routers/admin.py`

Data integrity and anti-cheat examples:
- Classic:
  - server stores shuffled options and correct answer in session state
  - submit uses server-side source of truth
- Challenge:
  - issued question tracking per session
  - no pre-answer explanation leak
- Custom:
  - `submit-answer` validates question was issued for that session
  - no pre-answer correct answer leak
- PvP:
  - question id must match server question at submitted index
  - duplicate answer race protected by early flush + integrity handling
  - end-match idempotency

Security fail-fast at startup (`config.validate_security_config`):
- empty/short/default JWT secrets are rejected in unsafe contexts
- dangerous production config combos fail startup

---

## Layer 7: Endpoint Catalog (Current Runtime)

## 7.1 Auth (`/api/auth`)
- POST `/signup`
- POST `/login`
- GET `/me`
- GET `/profile`
- POST `/forgot-password`
- POST `/reset-password`
- POST `/bootstrap-admin`

## 7.2 Onboarding (`/api/onboarding`)
- GET `/status`
- POST `/survey`
- POST `/skip`
- POST `/mark-tour-seen`

## 7.3 Classic (`/api/rooms/classic`)
- POST `/questions`
- POST `/hints`
- POST `/answers`

## 7.4 Challenge (`/api/challenge`)
- GET `/user/{user_id}/rank`
- POST `/start-session`
- GET `/session/{session_id}`
- PATCH `/session/{session_id}/change-level`
- POST `/generate-question`
- POST `/submit-answer`
- POST `/session/{session_id}/end`

## 7.5 Custom (`/api/custom`)
- GET `/topics`
- GET `/concepts/{topic}`
- GET `/user/{user_id}/concept-mastery`
- POST `/start-session`
- POST `/generate-question`
- POST `/generate-hint`
- POST `/submit-answer`
- POST `/session/{session_id}/end`

## 7.6 PvP (`/api/pvp`)
- POST `/join-queue`
- DELETE `/leave-queue`
- GET `/queue-status`
- GET `/match/{match_id}`
- POST `/match/{match_id}/answer`
- POST `/match/{match_id}/end`
- GET `/user/{user_id}/rating`
- GET `/leaderboard`

## 7.7 Admin (`/api/admin`)
- GET `/overview`
- GET `/top-concepts`
- GET `/concepts`
- GET `/concepts/{concept_id}`
- GET `/users`
- GET `/users/{user_id}`
- PATCH `/users/{user_id}`
- GET `/questions`
- GET `/sessions`
- GET `/monitoring`

## 7.8 System
- GET `/health`

---

## Layer 8: Operations, Rate Limits, Testing, And Caveats

## 8.1 Rate Limits (Active Decorators)
Configured endpoint limits include:
- Auth:
  - signup: 20/minute
  - login: 10/minute
  - forgot-password: 5/minute
  - reset-password: 10/minute
  - bootstrap-admin: 3/minute
- Classic:
  - questions: 40/minute
  - answers: 80/minute
- Challenge:
  - generate-question: 40/minute
  - submit-answer: 80/minute
- Custom:
  - generate-question: 40/minute
  - submit-answer: 80/minute

Rate-limit middleware and 429 handling are in `main.py`.

## 8.2 Observability
- Request-id header: `X-Request-ID`
- Structured request logs at start/end
- In-memory monitoring counters for:
  - total requests
  - total errors
  - total rate-limit events
  - per-endpoint counts

## 8.3 Regression And Collection Status (Latest Verified In This Workstream)
- Backend tests: passing (`31 passed, 10 skipped`)
- Frontend type/lint check: passing
- Postman/Newman collection: `65 requests, 81 assertions, 0 failures`
- PvP rating behavior verified:
  - cross-user rating reads allowed for authenticated users
  - unknown valid UUID returns 404

## 8.4 Known Caveats To Keep In Mind
1. Dashboard onboarding currently reads `localStorage.user_id`, while auth context stores `adaptiq_user_id`. This mismatch can suppress onboarding status fetch on some clients.
2. `challengeService` and `apiService` can create a UUID if user id key is missing, which can lead to auth/user mismatch errors if storage is corrupted.
3. Some docs in repository are historical snapshots and may not match current runtime endpoints. Prefer router files as the source of truth.

---

## Appendix: Fast Mental Model
If you need one compact model of how AdaptIQ works:
- Auth establishes identity via JWT.
- Each room has its own progression mechanics.
- Redis-backed session state preserves server-trusted question context.
- SQL stores durable user performance and ranking/mastery data.
- LLM/RAG extends content generation when bank selection is insufficient.
- Guards prevent answer leaks and cross-session/cross-user cheating.
- Admin APIs expose observability and platform control.
