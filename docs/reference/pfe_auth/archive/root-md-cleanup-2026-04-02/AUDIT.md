# AdaptIQ Code Audit — 2026-03-31

## Implementation Progress

### ✅ Phase 0: Audit COMPLETE
- Read all backend/frontend files
- Created this AUDIT.md

### ✅ Phase 1: Database Schema COMPLETE
- Added `elo_global` to users table
- Added `hint`, `times_seen` to question_bank
- Added new tables: `user_concept_repeat_queue`, `classic_sessions`, `challenge_ranks`, `user_challenge_rank`, `challenge_matches`
- Created migration: `006_add_challenge_and_session_tables.py`
- Created seed script: `seeds/seed.py` with 15 concepts, 30 questions, 5 test users

### ✅ Phase 2: Classic Room Adaptivity COMPLETE
- Added `target_beta_range()` to `irt.py` for ZPD calculation
- Created `services/classic_service.py` with concept selection, question selection, answer processing
- Added V2 endpoints to `routers/classic_room.py`:
  - `POST /start` - Start session, returns first question
  - `POST /answer/{session_id}` - Submit answer, returns next question
  - `POST /hint/{session_id}` - Get hint for question
  - `GET /metrics/{session_id}` - Get session metrics
- Created `scripts/decay_theta.py` for inactive user theta decay

### ✅ Phase 3: Challenge Room COMPLETE
- Created `routers/challenge.py` with full challenge logic:
  - `GET /status` - User's challenge status
  - `POST /start` - Start challenge match
  - `POST /answer/{match_id}` - Submit answer
  - `POST /end/{match_id}` - End match
- Challenge ranks seeded in migration (Bronze → Diamond)
- Anti-farming: can't play below current rank
- Skip mechanics: can challenge +1 rank with limited attempts
- Timer enforcement at higher ranks

### ✅ Phase 5 (partial): Auth & Infrastructure
- Dev bypass mode implemented in `auth/core/dependencies.py`
- Added `DEV_BYPASS_AUTH` config flag
- Session state storage added to `services/session.py`

---

## 🔴 CRITICAL (fix in Phase 1)

- [ ] **Missing tables per AGENT_PROMPT.md spec:**
  - `user_concept_repeat_queue` — not in models.py (needed for repeat scheduling)
  - `classic_sessions` — not in models.py (needed for session tracking)
  - `challenge_ranks` — not in models.py (needed for Challenge Room)
  - `user_challenge_rank` — not in models.py (needed for Challenge Room)
  - `challenge_matches` — not in models.py (needed for Challenge Room)

- [ ] **Users table missing columns:**
  - `elo_global` column (spec requires, models.py has `points` + `level` instead)
  - Note: Current system uses points/level, may need migration strategy

- [ ] **Question bank missing columns:**
  - `hint` column (spec requires, currently hints are generated on-the-fly)
  - `times_seen` column (spec requires, currently `usage_count`)

## 🟡 MAJOR (fix in Phase 2–4)

- [ ] **Classic Room endpoints need redesign per spec:**
  - Current: `POST /questions`, `POST /hints`, `POST /answers`
  - Spec requires: `POST /start`, `POST /answer/{session_id}`, `POST /hint/{session_id}`, `GET /metrics/{session_id}`
  - Current endpoints still accept `user_id` and `session_id` in body (should come from JWT)

- [ ] **IRT functions missing `target_beta_range`:**
  - `irt.py` has `irt_probability`, `update_theta`, `update_beta`, `beta_to_difficulty`, `difficulty_to_beta`
  - Missing: `target_beta_range(theta)` returning `(beta_low, beta_high)` for ZPD

- [ ] **Missing `classic_service.py`:**
  - Spec requires `select_concepts_for_session` with scoring algorithm
  - Current: Question selection happens directly in router

- [ ] **Challenge Room not implemented:**
  - No `backend/routers/challenge.py` file exists
  - No challenge-related endpoints

- [ ] **Frontend option spam bug:**
  - ClassicRoom.tsx has `backendLocked` state but unclear if full state machine implemented
  - Spec requires: LOADING → READY → ANSWERED → RESULT state machine

- [ ] **Dev bypass panel not in frontend:**
  - Spec requires floating panel with 5 test users when `?dev=true`
  - Not present in current codebase

## 🟢 MINOR (fix in Phase 5–6)

- [ ] **Dev bypass token not implemented in backend:**
  - `auth/core/dependencies.py` does not accept `dev-bypass-{user_id}` format
  - Spec requires this for testing without real JWT

- [ ] **Structured JSON logging not fully implemented:**
  - `main.py` uses structlog but not the exact JSON format spec requires
  - Missing: `concept_selected`, `theta_updated`, `rank_change` log events

- [ ] **Decay script not implemented:**
  - No `backend/scripts/decay_theta.py` found
  - Spec requires: `theta *= 0.95` for users inactive > 14 days

- [ ] **Seed script missing:**
  - `backend/seeds/` directory exists but is empty
  - Spec requires idempotent script with 15+ concepts, 30+ questions, 5 test users

---

## Auth Status

- **Register:** ✅ WORKS — `POST /api/auth/register` creates user, returns JWT
- **Login:** ✅ WORKS — `POST /api/auth/login` validates credentials, returns JWT
- **JWT protected route:** ✅ WORKS — `/api/auth/me` requires valid Bearer token
- **Rate limiting:** ✅ WORKS — 5/min per IP+email for login
- **Password reset:** ✅ WORKS — OTP via Redis, revokes old tokens

---

## DB Status

- **alembic current:** 5 migrations present (001 through 005)
- **Tables present:**
  - `users` — ✅ with points, level, created_at, last_login
  - `user_responses` — ✅ tracks each answer
  - `question_bank` — ✅ with IRT params, primary_concept_id
  - `concepts` — ✅ with name, topic, description
  - `question_concepts` — ✅ M2M with is_primary flag
  - `user_concept_theta` — ✅ per-concept IRT tracking with exposure_count

- **Missing tables (per spec):**
  - `user_concept_repeat_queue`
  - `classic_sessions`
  - `challenge_ranks`
  - `user_challenge_rank`
  - `challenge_matches`

---

## Classic Room Status

- **/questions:** ✅ WORKS — RAG pipeline + LLM generates MCQs, caches in question_bank
- **/hints:** ✅ WORKS — LLM generates hint, validates no answer leak
- **/answers:** ✅ WORKS — Records response, updates concept theta, awards points
- **Concept tracking:** ✅ WORKS — Enabled via `ENABLE_CONCEPT_TRACKING=true`
- **Auto-discovery:** ✅ WORKS — 20% chance to inject unknown concept

**Issues:**
- Endpoints accept `user_id` in body (should use JWT's `current_user.id`)
- No `/start` endpoint to create session
- No `/metrics/{session_id}` endpoint
- No repeat queue logic

---

## Frontend Status

- **Build:** ✅ PASSES — Vite + TypeScript + Tailwind
- **Login page:** ✅ WORKS — Form validation present, stores token + user_id in localStorage
- **Signup page:** ✅ WORKS — Password strength validation
- **Dashboard:** ✅ WORKS — Shows stats, topic breakdown, daily trend, concept mastery
- **ClassicRoom:** ✅ WORKS — Topic selection, quiz flow, 10 questions

**Issues:**
- Option spam bug: Has `backendLocked` state but not full state machine
- No dev bypass panel (`?dev=true`)
- No Challenge Room page
- No Profile page

---

## Concept-Aware System Status

Per CONCEPT_AWARE_SYSTEM.md:
- ✅ `ConceptCacheService` exists (backend/services/concept_cache_service.py)
- ✅ `QuestionCacheService` exists (backend/services/question_cache_service.py)  
- ✅ `ConceptIRT` exists (backend/database/concept_irt.py)
- ✅ Auto-discovery with 80/20 known/unknown split
- ✅ Per-concept theta updates
- ✅ Exposure tracking

---

## Services Status

| Service | File | Status |
|---------|------|--------|
| LLMClient | services/llm.py | ✅ Groq API, MCQ + hint generation |
| SessionService | services/session.py | ✅ Redis + in-memory fallback |
| ConceptExtractor | services/concept_extractor.py | ✅ LLM-based concept extraction |
| ConceptCacheService | services/concept_cache_service.py | ✅ Concept selection + difficulty |
| QuestionCacheService | services/question_cache_service.py | ✅ Redis question caching |

---

## RAG Pipeline Status

| Component | File | Status |
|-----------|------|--------|
| AgenticRAGPipeline | rag/agentic.py | ✅ 3-agent orchestrator |
| Wikipedia fetcher | rag/wikipedia.py | ✅ Context retrieval |
| Wikidata SPARQL | rag/wikidata.py | ✅ Fact fetching |
| HuggingFace loader | rag/hf_dataset.py | ✅ Dataset integration |

---

## Test Status

- **Backend tests present:**
  - test_auth_api.py
  - test_classic_room_api.py
  - test_concept_awareness.py
  - test_system_health.py

- **E2E tests:** Not present (Playwright not set up)

---

## Summary

**What exists and works:**
1. Full auth flow (register/login/JWT/rate-limit/password-reset)
2. Classic Room quiz flow with RAG + LLM
3. Per-concept IRT theta tracking
4. Question caching in database
5. Dashboard with stats visualization

**What needs to be built (per AGENT_PROMPT.md):**
1. Challenge Room (ranks, timers, skip mechanics)
2. Missing database tables
3. Classic Room endpoint redesign (session-based)
4. Repeat queue logic
5. Dev bypass mode (backend + frontend)
6. Seed script with test users
7. Frontend state machine for option spam
8. E2E tests with Playwright
