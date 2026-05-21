## 🧠 WHAT YOU ARE BUILDING

**AdaptIQ** is an adaptive quiz platform (university final project — PFE).

Users register, pick a room, and answer MCQs. The system tracks per-concept knowledge using IRT (Item Response Theory) and adapts difficulty automatically so the quiz never feels too easy or too hard.

Two rooms:
- **Classic Room** — Learning mode. 4 options, hints, explanations, visible ELO, no pressure.
- **Challenge Room** — Competitive mode. Ranks, timers, no hints, hidden ELO, skip mechanics.

**Tech Stack (do not change):**
- Backend: FastAPI + SQLAlchemy async + PostgreSQL 16 + Redis 7 + Pydantic 2
- Frontend: React 19 + TypeScript + Vite + Tailwind CSS 4 + React Router 7
- LLM: Groq API (llama-3.1-8b-instant) for MCQ generation + hints
- Auth: JWT (access + refresh tokens)
- Migrations: Alembic

---

## 📂 CURRENT PROJECT LAYOUT

```
pfe_auth/
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── dependencies.py
│   ├── schemas.py
│   ├── pydantic_types.py
│   ├── auth/
│   │   ├── core/security.py
│   │   ├── core/dependencies.py
│   │   └── services/auth_service.py, otp_service.py, email_service.py
│   ├── database/
│   │   ├── models.py        ← SQLAlchemy models (needs full rebuild)
│   │   ├── crud.py
│   │   └── irt.py
│   ├── routers/
│   │   ├── auth.py
│   │   ├── classic_room.py  ← incomplete / no JWT enforcement
│   │   └── system.py
│   ├── services/
│   │   ├── llm.py           ← Groq client
│   │   └── session.py       ← Redis session (with in-memory fallback)
│   └── rag/
│       ├── agentic.py
│       ├── wikipedia.py
│       ├── wikidata.py
│       └── hf_dataset.py
├── frontend/
│   └── src/
│       ├── App.tsx
│       ├── types.ts
│       ├── context/AuthContext.tsx
│       ├── pages/  (Home, Login, Signup, Dashboard, ClassicRoom)
│       ├── services/apiService.ts
│       └── components/InternalLayout.tsx
├── alembic/
├── docker-compose.yml
└── CLAUDE.md
```

---

## ⚙️ ENVIRONMENT (ALREADY SET — DO NOT CHANGE)

**backend/.env:**
- DB: `postgresql+asyncpg://pfe:...@localhost:5433/adaptive_learning`
- Redis: `redis://:...@localhost:6379/0`
- `GROQ_API_KEY` set
- `DEV_BYPASS_AUTH=true`
- JWT secret set

**frontend/.env.local:**
- `VITE_API_URL=http://localhost:8000`

**Ports:**
| Service | Port |
|---------|------|
| FastAPI | 8000 |
| Vite | 5173 |
| PostgreSQL | 5433 |
| Redis | 6379 |

---

## 🚨 AGENT RULES (READ BEFORE EVERY PHASE)

1. **Read before writing.** Read every relevant file before modifying anything.
2. **Log issues, then fix.** Create `AUDIT.md` in phase 0. Reference it in every phase.
3. **Never break auth.** Any route that reads/writes user data MUST use `get_current_user` dependency.
4. **Dev bypass stays.** `DEV_BYPASS_AUTH=true` in `.env` must allow testing without a real token.
5. **No deployment work.** Focus is local dev only. No Docker production configs, no CI/CD.
6. **One concern per file.** Don't dump everything into `main.py` or `schemas.py`.
7. **After every phase:** restart backend, run `pytest`, test one user flow manually.
8. **Commit-ready code only.** No commented-out dead code, no `TODO: fix later` in critical paths.

---

---

# PHASE 0 — AUDIT (DO THIS FIRST, DO NOT SKIP)

**Goal:** Understand the full state of the codebase before touching anything.

## Steps

1. Read every file in `backend/` and `frontend/src/` systematically.
2. Start the services:
   ```bash
   docker-compose up -d postgres redis
   cd backend && python main.py
   cd frontend && npm run dev
   ```
3. Run these checks and record every error:
   ```bash
   cd backend
   pytest --collect-only
   alembic current
   alembic history
   ```
4. Test auth manually:
   ```bash
   # Register
   curl -X POST http://localhost:8000/api/auth/register \
     -H "Content-Type: application/json" \
     -d '{"email":"audit@test.com","username":"auditor","password":"Test1234!"}'

   # Login
   curl -X POST http://localhost:8000/api/auth/login \
     -H "Content-Type: application/json" \
     -d '{"email":"audit@test.com","password":"Test1234!"}'

   # Health check (with token from above)
   curl -H "Authorization: Bearer <token>" http://localhost:8000/api/system/health
   ```
5. Test the classic room:
   ```bash
   curl -X POST http://localhost:8000/api/rooms/classic/questions \
     -H "Content-Type: application/json" \
     -d '{"topic":"history","user_id":"test","session_id":"s1"}'
   ```

## Create `AUDIT.md` at project root

```
# AdaptIQ Code Audit — [DATE]

## 🔴 CRITICAL (fix in Phase 1)
- [ ] ...

## 🟡 MAJOR (fix in Phase 2–4)
- [ ] ...

## 🟢 MINOR (fix in Phase 5–6)
- [ ] ...

## Auth Status
- Register: [WORKS / BROKEN — reason]
- Login: [WORKS / BROKEN — reason]
- JWT protected route: [WORKS / BROKEN — reason]

## DB Status
- alembic current: [output]
- Tables present: [list]
- Missing tables: [list]

## Classic Room Status
- /questions: [WORKS / BROKEN — reason]
- /hints: [WORKS / BROKEN — reason]
- /answers: [WORKS / BROKEN — reason]

## Frontend Status
- Build: [PASSES / FAILS — errors]
- Login page: [WORKS / BROKEN]
- ClassicRoom: option spam bug: [PRESENT / FIXED]
```

**✅ Phase 0 complete when:** AUDIT.md exists and covers every section above.

---

---

# PHASE 1 — DATABASE SCHEMA REBUILD

**Goal:** Replace the existing models with a schema that supports all AdaptIQ features.

## 1.1 — New SQLAlchemy Models (`backend/database/models.py`)

Replace the file entirely with these models:

```python
# Core tables needed:

# users
# id (UUID PK), email, username, hashed_password,
# elo_global (float, default 0.0), created_at, last_login

# concepts
# id (UUID PK), name, subject (enum: geography/history),
# parent_concept_id (self-FK nullable),
# difficulty_profile_avg (float -3..3, default 0.0)
# Example rows: "Egyptian Empire", "Roman Empire", "Amazon River Basin"

# question_bank
# id (UUID PK), text, options (JSON array of 4 strings),
# correct_index (int 0-3), explanation (text), hint (text),
# beta_irt (float -3..3), subject (enum), created_at, times_seen (int)

# question_concept  (many-to-many join)
# question_id (FK), concept_id (FK), confidence (float 0..1)
# PK = (question_id, concept_id)

# user_concept_theta  (CORE ADAPTIVITY TABLE)
# user_id (FK), concept_id (FK),
# theta (float -3..3, default 0.0),
# n_responses (int, default 0),
# last_practiced_at (datetime)
# UNIQUE (user_id, concept_id)

# user_concept_repeat_queue
# id, user_id (FK), concept_id (FK),
# question_id (FK), repeat_probability (float),
# due_after_session (int), created_at

# classic_sessions
# id (UUID PK), user_id (FK),
# topic (enum: geography/history/mix),
# questions_answered (int), correct_count (int),
# created_at, ended_at (nullable)

# challenge_ranks
# id (int PK), name (str), min_elo (float),
# n_options (int), has_timer (bool), timer_seconds (int nullable)

# user_challenge_rank
# user_id (FK PK), current_rank_id (FK),
# wins (int), losses (int),
# skip_attempts_remaining (int default 3),
# last_skip_at (datetime nullable)

# challenge_matches
# id (UUID PK), user_id (FK), rank_id (FK),
# questions_answered (int), score (float),
# time_taken (int seconds), created_at,
# result (enum: win/loss/draw/incomplete)
```

## 1.2 — Alembic Migration

```bash
cd backend
alembic revision --autogenerate -m "full_schema_rebuild"
# Review the generated file — check for missing columns, wrong types
alembic upgrade head
```

After upgrade, verify in psql or pgAdmin:
- All tables exist
- Foreign keys are correct
- Indexes on `user_id`, `concept_id` columns

## 1.3 — Seed Data Script (`backend/scripts/seed.py`)

Create this as a standalone script (not a migration). It must be idempotent (safe to run twice).

**Seed the following:**

**Concepts (minimum 15):**
```
Geography: "Amazon River Basin", "Sahara Desert", "Himalayan Range",
           "Mediterranean Sea", "Great Barrier Reef", "Arctic Circle",
           "Nile River Delta", "Siberian Tundra"

History:   "Egyptian Empire", "Roman Empire", "Mongol Empire",
           "Ottoman Empire", "Byzantine Empire", "Greek City-States",
           "Persian Empire"
```

**Questions (minimum 30 — 15 geography, 15 history):**
- Each question must have: text, 4 options, correct_index, explanation, hint, beta_irt
- Vary beta_irt across -2.0 to 2.0 (easy to hard)
- Tag each question to 1-2 concepts via `question_concept`

**Test Users (5 — password for all: `TestPass123!`):**

| email | username | elo_global | profile |
|-------|----------|------------|---------|
| geo_expert@test.com | geo_expert | 1.8 | theta=2.0 on geography concepts, -1.0 on history |
| hist_expert@test.com | hist_expert | 1.6 | theta=2.0 on history concepts, -1.0 on geography |
| balanced@test.com | balanced | 0.1 | theta≈0.0 on all concepts |
| beginner@test.com | beginner | -0.5 | no theta records (cold start) |
| challenger@test.com | challenger | 0.9 | in challenge rank 2, 8 wins 3 losses |

Each test user (except beginner) should have 10-20 rows in `user_concept_theta` and 20+ rows in `user_responses` (simulated history).

Run seed:
```bash
cd backend
python scripts/seed.py
```

**✅ Phase 1 complete when:** `alembic upgrade head` passes, seed script runs without errors, all 5 test users exist in DB, pgAdmin shows all tables.

---

---

# PHASE 2 — CLASSIC ROOM ADAPTIVITY ENGINE

**Goal:** Build a working adaptive quiz loop for the Classic Room.

## 2.1 — IRT Engine (`backend/database/irt.py`)

Ensure these functions exist and are correct:

```python
# Probability of correct answer (1PL IRT)
def p_correct(theta: float, beta: float) -> float:
    return 1 / (1 + exp(-(theta - beta)))

# Update theta after a response (gradient step)
def update_theta(theta: float, beta: float, correct: bool,
                 learning_rate: float = 0.3) -> float:
    p = p_correct(theta, beta)
    delta = learning_rate * (int(correct) - p)
    return max(-3.0, min(3.0, theta + delta))

# Given current theta, return target beta range (ZPD = 60-75% correct)
def target_beta_range(theta: float) -> tuple[float, float]:
    # P(correct) ∈ [0.60, 0.75] → solve for beta
    # beta_low = theta - ln(1/0.75 - 1) ≈ theta - 1.10
    # beta_high = theta - ln(1/0.60 - 1) ≈ theta - 0.41
    return (theta - 1.10, theta - 0.41)
```

## 2.2 — Concept Selection Algorithm

In `backend/services/classic_service.py` (create this file):

```python
async def select_concepts_for_session(
    user_id: str,
    topic: str,  # "geography" | "history" | "mix"
    n_concepts: int = 5,
    db: AsyncSession
) -> list[Concept]:
    """
    Strategy:
    1. Load all concepts matching topic.
    2. For each concept, load user_concept_theta (or default theta=0).
    3. If user has n_responses < 5 for a concept → 'cold start' mode
       Cold start: pick concepts whose difficulty_profile_avg is near 0
       (not too hard or easy for a new user)
    4. If user has n_responses >= 5:
       score = 0.4 * mastery_gap    # how much room to grow
             + 0.3 * recency_bonus  # hasn't practiced recently
             + 0.2 * repeat_due     # flagged for repetition
             + 0.1 * zpd_fit        # currently in ZPD range
       Pick top n_concepts by score.
    5. Always mix difficulties — avoid all-easy or all-hard.
    """
```

## 2.3 — Classic Room Router (`backend/routers/classic_room.py`)

Rebuild this file with proper JWT auth. Required endpoints:

### `POST /api/rooms/classic/start`
```
Auth: Bearer token required
Body: { "topic": "geography" | "history" | "mix" }
Response: {
  "session_id": "uuid",
  "first_question": QuestionOut,
  "session_stats": { "questions_answered": 0, "correct_count": 0 }
}
Logic:
  1. Create classic_session row
  2. Run select_concepts_for_session
  3. Select first question via IRT (ZPD range)
  4. Store session state in Redis (session:{session_id})
  5. Return question — options must be shuffled, correct_index updated accordingly
```

### `POST /api/rooms/classic/answer/{session_id}`
```
Auth: Bearer token required
Body: {
  "question_id": "uuid",
  "selected_index": 0-3,
  "time_taken_seconds": int
}
Response: {
  "correct": bool,
  "correct_index": int,
  "explanation": str,
  "theta_change": float,   # how much user's theta moved
  "next_question": QuestionOut | null,  # null if session ends
  "session_stats": { "questions_answered": int, "correct_count": int }
}
Logic:
  1. Verify session belongs to current user
  2. Evaluate answer
  3. Update user_concept_theta for all concepts tagged to this question
  4. Repeat logic:
     - Wrong: 25% chance → insert into user_concept_repeat_queue
     - Correct: 1% chance → insert into user_concept_repeat_queue
  5. Select next question (different concept if possible)
  6. Update Redis session state
  7. If 10 questions answered → mark session ended, return next_question=null
```

### `POST /api/rooms/classic/hint/{session_id}`
```
Auth: Bearer token required
Body: { "question_id": "uuid" }
Response: { "hint": str }
Logic:
  1. Check if question has stored hint in DB → return it (fast path)
  2. If not → call Groq LLM to generate hint
  3. CRITICAL: Hint must NOT reveal the answer or any option text
  4. Store generated hint back to question_bank
```

### `GET /api/rooms/classic/metrics/{session_id}`
```
Auth: Bearer token required
Response: {
  "accuracy": float,
  "theta_progress": [{ "concept": str, "theta_start": float, "theta_now": float }],
  "adaptivity_score": float  # % of questions that were in ZPD (target: 60-75%)
}
```

## 2.4 — Repeat Scheduling

After any answer, check `user_concept_repeat_queue`:
- If `due_after_session <= current_session_count` → prioritize this concept next
- After showing repeated question → delete from queue

## 2.5 — Decay Logic (scheduled, not real-time)

Create `backend/scripts/decay_theta.py`:
```python
"""
Run daily via cron or manually.
For users inactive > 14 days:
  theta = theta * 0.95  (slight regression toward mean)
  n_responses = max(0, n_responses - 1)  (reduce confidence)
Log every user affected.
"""
```

**✅ Phase 2 complete when:**
- `geo_expert` gets easy geography questions + hard history questions
- `beginner` gets medium-difficulty questions (cold start)
- Hint endpoint never reveals the answer
- Session ends cleanly after 10 questions

---

---

# PHASE 3 — CHALLENGE ROOM

**Goal:** Build the competitive ranking system.

## 3.1 — Rank Definitions (seed in Phase 1)

| Rank | Name | N Options | Timer | Question Style |
|------|------|-----------|-------|----------------|
| 1 | Bronze | 2 | None | Easy questions, 2 plausible options |
| 2 | Silver | 4 | None | 4 options, 2 obviously wrong |
| 3 | Gold | 4 | 45s | 4 options, all plausible |
| 4 | Platinum | 4 | 30s | Hard + trap options |
| 5 | Diamond | type-in | 25s | Skip for now (return placeholder) |

Bronze requires 0 ELO (anyone can enter after playing Classic ≥ 5 questions).
Each higher rank requires +0.5 ELO.

## 3.2 — Challenge Router (`backend/routers/challenge.py`)

### `GET /api/rooms/challenge/status`
```
Auth: Bearer token required
Response: {
  "current_rank": { "id": int, "name": str },
  "can_skip_up": bool,
  "skip_attempts_remaining": int,
  "wins": int, "losses": int,
  "classic_games_played": int  # must be >= 5 to unlock challenge
}
```

### `POST /api/rooms/challenge/start`
```
Auth: Bearer token required
Body: { "rank_id": int, "is_skip_attempt": bool }
Validation:
  - User must have played Classic >= 5 questions total
  - If rank_id > current_rank → forbidden (unless is_skip_attempt=true)
  - If is_skip_attempt=true:
      - rank_id must be exactly current_rank + 1
      - skip_attempts_remaining > 0
      - No active skip attempt cooldown (24h)
  - Cannot play rank < current_rank (anti-farming)
Response: {
  "match_id": "uuid",
  "rank": { "id": int, "name": str, "n_options": int, "timer_seconds": int | null },
  "first_question": QuestionOut
}
```

### `POST /api/rooms/challenge/answer/{match_id}`
```
Auth: Bearer token required
Body: { "question_id": "uuid", "selected_index": int, "time_taken_seconds": int }
Validation:
  - If rank has timer AND time_taken_seconds > timer_seconds → count as wrong
  - No hints available
  - No explanation returned during match
Response: {
  "correct": bool,
  "score_so_far": float,
  "questions_remaining": int,
  "next_question": QuestionOut | null
}
```

### `POST /api/rooms/challenge/end/{match_id}`
```
Auto-triggered after 10 questions OR called explicitly.
Response: {
  "result": "win" | "loss",
  "score": float,
  "rank_changed": bool,
  "new_rank": { "id": int, "name": str } | null,
  "skip_result": "promoted" | "failed" | null
}
Win condition: score >= 0.70 (70% correct)
If win on skip attempt → promote rank, reset skip_attempts
If loss on skip attempt → skip cooldown 24h, decrement skip_attempts_remaining
If win on current rank → no rank change (rank-up requires skip)
```

## 3.3 — Anti-Farming

Users can only play their current rank or one above (skip attempt).
Playing current rank gives no rank change, only stat tracking.
Log a warning if user tries to play below current rank — return 403.

**✅ Phase 3 complete when:**
- `challenger` (rank 2) can see their status
- Cannot play rank 1 (anti-farming)
- Skip attempt to rank 3 works if attempts remaining > 0
- Match ends with correct result after 10 questions

---

---

# PHASE 4 — FRONTEND

**Goal:** Fix all existing bugs and add missing screens.

## 4.1 — Critical Bugs to Fix First

### Option Spam Bug (MUST FIX)
In `ClassicRoom.tsx`:
```typescript
// Add a state: isQuestionLoaded = false
// Set to false when fetching next question
// Set to true ONLY after question data is received AND rendered
// Disable all option buttons while isQuestionLoaded === false
// Never show the green "correct" highlight until the user has clicked AND
// the answer has been verified by the backend
```

### Auth Enforcement
All pages except `/`, `/login`, `/signup` must redirect to `/login` if no valid token.
Use `AuthContext` — check token expiry on every protected page mount.

## 4.2 — Required Pages & Components

### `/login` and `/signup`
- Already exist — verify they call the correct endpoints and store `adaptiq_token` in localStorage
- Add form validation (email format, password min 8 chars)
- Show proper error messages from backend (not just "error")

### `/dashboard`
```
Show:
  - User greeting + global ELO
  - "Classic Room" button → /rooms/classic
  - "Challenge Room" button → /rooms/challenge (show lock if < 5 classic games)
  - Recent sessions list (last 5)
  - Dev mode indicator if ?dev=true
```

### `/rooms/classic`
```
Flow:
1. Topic selector: Geography | History | Mix
   → POST /api/rooms/classic/start
2. Question display:
   - Question text
   - 4 option buttons (LOCKED during load)
   - Hint button → GET hint endpoint → show hint below question
   - Timer indicator (visual only, not enforced in classic)
3. After answer (user clicks option):
   - Lock all buttons immediately
   - POST answer to backend
   - Show: ✅ Correct / ❌ Wrong + explanation modal
   - "Next Question" button → fetch next question
4. Session end (10 questions):
   - Show session summary: score, accuracy, ELO change
   - "Play Again" + "Go to Dashboard"
```

### `/rooms/challenge`
```
Flow:
1. Show current rank + skip option (if available)
2. Rank selector (can only pick current or +1 for skip)
   → POST /api/rooms/challenge/start
3. Question display:
   - N options per rank (2 for bronze, 4 for others)
   - Timer countdown if rank >= 3
   - NO hint button
   - NO explanation after answer — just correct/wrong flash
4. Match end:
   - Win/loss screen with rank change animation if promoted
```

### `/profile`
```
Show:
  - Per-concept theta as a simple bar chart or radar chart
    (use recharts or plain SVG — no extra dependencies)
  - Session history table
  - Challenge rank badge
```

## 4.3 — Dev Bypass Mode

When `?dev=true` is in the URL:
- Show a floating panel with test user selector
- Clicking a test user auto-logs in (calls login endpoint with known credentials)
- Panel must be visible on every page while `?dev=true` is active

## 4.4 — Loading States

Every async operation must show a loading state:
- Spinner or skeleton on question load
- Disabled submit button during answer POST
- Loading screen between sessions

## 4.5 — Option Locking (State Machine)

```
LOADING → question fetch in progress, all buttons disabled
READY   → question loaded, buttons enabled
ANSWERED → user clicked, buttons locked, waiting for backend response
RESULT  → backend responded, show result, "Next" button enabled
```
Never skip states. Never allow clicking during LOADING or ANSWERED.

**✅ Phase 4 complete when:**
- Cannot spam options (spam test: click 10 times on load — only first click registers)
- Dev mode shows test user switcher
- Classic room full flow works (start → 10 questions → summary)
- Challenge room shows rank correctly

---

---

# PHASE 5 — AUTH, CACHING, LOGGING, DECAY

**Goal:** Harden the infrastructure.

## 5.1 — JWT Auth

Verify `backend/auth/core/security.py`:
```python
# Must have:
# - create_access_token(user_id, expires_delta=30min)
# - create_refresh_token(user_id, expires_delta=7days)
# - verify_token(token) → user_id or raise HTTPException 401

# Dev bypass: if DEV_BYPASS_AUTH=true in settings,
# accept token "dev-bypass-{user_id}" without signature check
```

All classic room and challenge room endpoints must use:
```python
current_user: User = Depends(get_current_user)
```

Remove `user_id` from request bodies — always read from `current_user.id`.

## 5.2 — Redis Caching

Ensure `backend/services/session.py`:
```python
# session:{session_id}  TTL=1h
#   stores: topic, questions_asked, current_concepts, theta_snapshot

# zpd_cache:{concept_id}:{theta_bucket}  TTL=5min
#   stores: list of question_ids in ZPD range for this concept+theta
#   theta_bucket = round(theta * 2) / 2  (quantize to 0.5 steps)

# challenge_skip_cooldown:{user_id}  TTL=24h
#   stores: 1 if user is in cooldown

# rate_limit:login:{ip}:{email}  TTL=1min
#   counter, max 5 attempts
```

Fallback: if Redis is unreachable, session state falls back to in-memory dict. Log a WARNING when fallback is used.

## 5.3 — Structured Logging

In `backend/main.py` lifespan setup, configure:
```python
import logging, json

class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "ts": self.formatTime(record),
            "level": record.levelname,
            "module": record.module,
            "msg": record.getMessage(),
            **getattr(record, "extra", {})
        })

# Log EVERY adaptivity decision:
logger.info("concept_selected", extra={
    "extra": {"user_id": ..., "concept_id": ..., "score": ..., "reason": ...}
})

# Log EVERY IRT update:
logger.info("theta_updated", extra={
    "extra": {"user_id": ..., "concept_id": ...,
              "theta_before": ..., "theta_after": ..., "correct": ...}
})

# Log EVERY challenge rank change:
logger.info("rank_change", extra={
    "extra": {"user_id": ..., "from_rank": ..., "to_rank": ..., "result": ...}
})
```

## 5.4 — Inactive User Decay (Daily Script)

`backend/scripts/decay_theta.py`:
```python
"""
For users whose last_practiced_at < 14 days ago:
  theta = theta * 0.95
  n_responses = max(0, n_responses - 1)
  log each affected user

Run manually: python scripts/decay_theta.py
"""
```

**✅ Phase 5 complete when:**
- All routes return 401 if no token (except /auth/* and /system/health)
- Dev bypass works: `Authorization: Bearer dev-bypass-{user_id}` accepted when DEV_BYPASS_AUTH=true
- Redis session survives backend restart (not lost on restart)
- decay_theta.py runs without errors

---

---

# PHASE 6 — TESTS

**Goal:** Confidence that nothing breaks silently.

## 6.1 — Backend Unit Tests (`backend/tests/`)

### `test_irt.py`
```python
# test p_correct returns 0.5 when theta == beta
# test update_theta increases theta on correct answer
# test update_theta decreases theta on wrong answer
# test theta is clamped to [-3, 3]
# test target_beta_range returns values where P(correct) ∈ [0.60, 0.75]
```

### `test_classic.py`
```python
# Use geo_expert test user
# Start classic session with topic=history
# Verify questions selected are harder than baseline
# Answer all wrong → verify repeat queue populated
# Answer all correct → verify repeat queue is nearly empty
# Verify session ends after 10 questions
```

### `test_challenge.py`
```python
# challenger user (rank 2) cannot start rank 1 match
# challenger user can start rank 2 match
# skip attempt to rank 3: success path
# skip attempt to rank 3: failure path (loss) → cooldown set
# skip attempt when skip_attempts_remaining=0 → 403
# time violation: answer arrives after timer → counted as wrong
```

### `test_auth.py`
```python
# Register → login → get /auth/me → returns user info
# Invalid token → 401 on protected route
# Dev bypass token accepted when DEV_BYPASS_AUTH=true
# Rate limit: 6th login attempt in 1min → 429
```

### `test_hints.py`
```python
# Hint for a question with stored hint → returns immediately (no LLM call)
# Hint response never contains the correct answer text
# Hint response never contains any option text verbatim
```

## 6.2 — E2E Tests (Playwright, `frontend/e2e/`)

```typescript
// classic_flow.spec.ts
// 1. Login as geo_expert
// 2. Start classic session (topic=history)
// 3. Play 10 questions clicking first option each time
// 4. Verify session summary screen appears
// 5. Verify option buttons are disabled during load (spam test)

// challenge_flow.spec.ts
// 1. Login as challenger
// 2. View challenge status → rank 2
// 3. Start rank 2 match
// 4. Play 10 questions
// 5. View result screen

// auth_flow.spec.ts
// 1. Visit /dashboard without token → redirect to /login
// 2. Login → redirect to /dashboard
// 3. Logout → token removed → redirect to /login

// dev_bypass.spec.ts
// 1. Visit /?dev=true → dev panel visible
// 2. Click "geo_expert" → auto-login
// 3. Navigate to /rooms/classic → works without manual login
```

Install Playwright:
```bash
cd frontend
npm install -D @playwright/test
npx playwright install chromium
```

Run all tests:
```bash
# Backend
cd backend && pytest -v

# E2E
cd frontend && npx playwright test
```

**✅ Phase 6 complete when:**
- `pytest` passes 100%
- E2E tests pass (at minimum classic_flow and auth_flow)
- No test modifies production data (use test DB or rollback fixtures)

---

---

# PHASE 7 — QUALITY GATES & WRAP-UP

**Goal:** Verify everything works together before calling it done.

## 7.1 — Manual Test Matrix

Run through each of these with the named test users:

| User | Scenario | Expected |
|------|----------|----------|
| geo_expert | Classic, topic=history | Gets hard history Qs (beta > 1.0) |
| geo_expert | Classic, topic=geography | Gets easy geography Qs (beta < 0) |
| hist_expert | Classic, topic=history | Gets easy history Qs |
| beginner | Classic, any topic | Gets medium Qs (cold start) |
| challenger | Challenge status | Sees rank 2, skip option |
| challenger | Try to start rank 1 | Gets 403 |
| challenger | Skip to rank 3 | Match starts, 4 options, 45s timer |
| any user | No token | 401 on all protected routes |
| any user | ?dev=true | Dev panel visible, test user login works |

## 7.2 — Alembic Check

```bash
alembic current     # should show latest revision
alembic check       # should say "up to date"
```

If not up to date — run `alembic upgrade head` and re-verify.

## 7.3 — API Docs Check

Open `http://localhost:8000/docs` — verify:
- All routes listed
- Auth routes show 🔒 lock icon
- Example request/response schemas look correct

## 7.4 — Create `STATUS.md` at project root

```markdown
# AdaptIQ Status — [DATE]

## ✅ Done
- [ ] Phase 0: Audit (AUDIT.md complete)
- [ ] Phase 1: Schema rebuilt, seed data loaded
- [ ] Phase 2: Classic room adaptivity working
- [ ] Phase 3: Challenge room ranks + skip logic
- [ ] Phase 4: Frontend — spam bug fixed, dev mode, all screens
- [ ] Phase 5: Auth JWT enforced, Redis caching, logging, decay
- [ ] Phase 6: Tests passing (unit + E2E)
- [ ] Phase 7: Manual matrix checked

## Known Remaining Issues
- [ ] ...

## Test User Credentials (password: TestPass123!)
- geo_expert@test.com
- hist_expert@test.com
- balanced@test.com
- beginner@test.com
- challenger@test.com
```

---

---

# APPENDIX A — QUESTION QUALITY GUIDELINES

When generating questions via LLM or writing seed questions, enforce:

**Good question criteria:**
- Tests a specific, verifiable fact (not opinion)
- Clear and unambiguous wording
- Exactly 4 options (or 2 for Bronze rank)
- One definitively correct answer
- Three plausible distractors (not obviously wrong)
- Explanation: 2-3 sentences, teaches why the correct answer is right
- Hint: one sentence, narrows down without revealing the answer

**Bad question patterns (reject these):**
- "Which of these is NOT true?" — confusing negation
- Options like "All of the above" or "None of the above"
- Trick questions based on phrasing rather than knowledge
- Explanation that says "The correct answer is X" without explaining why
- Hint that contains the answer or option text

**Hint validation (in `backend/services/llm.py`):**
```python
def validate_hint(hint: str, correct_answer: str, all_options: list[str]) -> bool:
    hint_lower = hint.lower()
    if correct_answer.lower() in hint_lower:
        return False
    for option in all_options:
        if option.lower() in hint_lower:
            return False
    return True
```

---

# APPENDIX B — IRT MATH REFERENCE

```
θ (theta) = user ability on a concept. Range: -3 to 3.
β (beta)  = question difficulty. Range: -3 to 3.
           β = -2 → very easy, β = 0 → average, β = 2 → very hard.

P(correct) = 1 / (1 + e^(-(θ - β)))

ZPD (Zone of Proximal Development):
  P(correct) ∈ [0.60, 0.75] → question feels challenging but achievable.
  Solve for β given θ:
    β_low  = θ - ln(1/0.75 - 1) ≈ θ - 1.10
    β_high = θ - ln(1/0.60 - 1) ≈ θ - 0.41

IRT update (gradient ascent):
  Δθ = learning_rate * (actual - P)
  learning_rate = 0.3 initially, reduce to 0.1 after 20+ responses
  Clamp: θ ∈ [-3, 3]

Cold start (n_responses < 5):
  Use concept.difficulty_profile_avg as the seed beta.
  Don't update theta until 3+ responses to avoid noise.
```

---

# APPENDIX C — REDIS KEY REFERENCE

| Key Pattern | TTL | Contents |
|-------------|-----|----------|
| `session:{session_id}` | 1h | Current session state JSON |
| `zpd_cache:{concept_id}:{theta_bucket}` | 5min | List of question_ids |
| `challenge_skip_cooldown:{user_id}` | 24h | `"1"` |
| `rate_limit:login:{ip}:{email}` | 1min | Count integer |
| `otp:{email}` | 10min | OTP code |

---

# APPENDIX D — DEV BYPASS SPEC

When `DEV_BYPASS_AUTH=true` in `.env`:
- Backend accepts `Authorization: Bearer dev-bypass-{user_id}` on any protected route
- `get_current_user` dependency looks up the user by ID directly from DB
- No signature verification, no expiry check
- Log a DEBUG message every time dev bypass is used: `"DEV BYPASS USED: {user_id}"`

Frontend `?dev=true`:
- Persisted in sessionStorage as `devMode=true`
- Floating bottom-right panel shows 5 test users
- Clicking one user POSTs to `/api/auth/login` with their test credentials
- On success, stores token normally — rest of app works identically to real users
- Panel is hidden in production (when `import.meta.env.PROD === true`)

---

*End of AdaptIQ Agent Prompt — Version 1.0*