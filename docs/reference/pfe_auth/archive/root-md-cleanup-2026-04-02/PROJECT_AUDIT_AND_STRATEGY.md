# AdaptIQ Project Audit & Strategic Recommendations
## Project Lead Review & Agent Prompt Engineering

**Date**: 2026-04-02
**Status**: COMPREHENSIVE AUDIT IN PROGRESS
**Current Phase**: Production-Ready Core (100% test pass rate, but gaps remain)

---

## EXECUTIVE SUMMARY

### Current State: 7/10 Production Readiness

**✅ WORKING (100% verified)**
- Authentication: JWT + bcrypt ✅
- Classic Room: Question generation, adaptive difficulty ✅
- Hints: LLM-powered, answer-non-revelation enforced ✅
- Session Management: Redis-backed with TTL ✅
- Database: PostgreSQL with proper migrations ✅
- Server-side time calculation: Anti-tampering ✅

**⚠️ NEEDS ATTENTION (Critical)**
1. Challenge Room: Incomplete implementation (403 errors, rank not fully integrated)
2. Frontend: Incomplete (no challenge room UI, missing form validation locking)
3. Concept-based adaptivity: Needs per-concept theta tracking (partially done)
4. Question quality: RAG pipeline works but needs quality gates
5. Test user profiles: Missing varied concept knowledge distributions

**❌ MISSING (Must implement)**
1. Frontend challenges UI (entire module)
2. Concept-aware question filtering (ranked by user's concept theta)
3. Question repetition logic (7-quiz threshold tracking)
4. ELO decay system (when user inactive >30 days)
5. E2E testing suite
6. Production logging infrastructure
7. Admin dashboard skeleton

---

## PART A: AS-IS CODE REVIEW

### 1. BACKEND ARCHITECTURE

#### ✅ **main.py** (Strong)
- Lifespan management with proper cleanup ✅
- Structured logging with structlog ✅
- CORS configured for localhost development ✅
- Global exception handler captures all errors ✅
- Rate limiting middleware in place ✅
- Request logging with request_id tracking ✅

**Issues Found**:
- [ ] CORS origins hardcoded (should use config)
- [ ] No HTTPS redirect in production mode
- [ ] No request body size limits

#### ✅ **schemas.py** (Good)
- SubmitAnswerRequest: Has optional time_taken ✅
- ClassicAnswerRequest: Has optional time_taken_seconds ✅
- ChallengeAnswerRequest: Has optional time_taken_seconds ✅
- All have proper validation ✅

**Issues Found**:
- [ ] No pagination schemas (for future dashboard)
- [ ] No stats aggregation schemas
- [ ] Challenge rank response missing from schema exports

#### ⚠️ **database/models.py** (Incomplete)
**Models Present**:
- User (id, email, username, password_hash, last_login, is_admin)
- UserResponse (tracks answers: user_id, question_id, correct, time_taken, used_hint)
- QuestionBank (cached questions with difficulty_irt, discrimination)
- Concept (new: concept names like "Egyptian Empire", "Roman History")
- UserConceptTheta (new: per-user-concept ability tracking)

**Missing Models** ❌:
- [ ] ChallengeRank (rank definitions: Bronze, Silver, Gold, Platinum, Diamond)
- [ ] UserChallengeRank (user's current rank + ELO)
- [ ] ChallengeMatch (history: user_id, rank, questions, score, elo_change)
- [ ] QuestionRepetition (tracks: question_id, user_id, last_shown, times_wrong)
- [ ] UserActivityLog (timestamps of quiz activity for decay calculation)
- [ ] ConceptMastery (mastered_at, concept_id, user_id for milestone tracking)

#### ⚠️ **database/irt.py** (Partial)
**Present**:
- IRT calculation: update_theta() ✅
- Beta (difficulty) estimation ✅
- Zone of Proximal Development targeting (60-75% success) ✅

**Missing** ❌:
- [ ] Concept-specific theta updates (currently global only)
- [ ] Question repetition scoring (age penalty for repeated Qs)
- [ ] Concept mastery thresholds
- [ ] Theta decay for inactive users

#### ✅ **routers/auth.py** (Strong)
- Registration with password validation ✅
- Login with rate limiting (5 per minute per IP+email) ✅
- JWT token generation ✅
- Forgot/Reset password with OTP ✅
- User stats endpoint ✅

**Issues Found**:
- [ ] No password strength requirements in validation (lacks special char enforcement)
- [ ] OTP expires in 5 min (OK but should be configurable)
- [ ] No email verification (logs to console)

#### ⚠️ **routers/classic_room.py** (Working with gaps)
**Present**:
- Session start ✅
- Question generation via RAG ✅
- Answer submission with adaptive difficulty ✅
- Hint generation ✅
- Server-side time calculation ✅

**Missing** ❌:
- [ ] Concept-aware question filtering (should rank by user's concept knowledge)
- [ ] Question repetition logic (should pull recently-wrong questions)
- [ ] Confidence scoring (system doesn't track how confident user was)
- [ ] Learning path tracking (which concepts to focus on)
- [ ] Session stats (avg accuracy per concept)

#### ❌ **routers/challenge.py** (Incomplete)
**Status Implementation**:
- GET /status: Returns rank data but incomplete schema ✅

**Missing** ❌ (entire feature):
- [ ] POST /start (begin match at specific rank)
- [ ] GET /question (get next question for current match)
- [ ] POST /answer (submit answer, check timer)
- [ ] GET /leaderboard (rank progression)
- [ ] POST /skip (skip to higher rank with attempt limit)

#### ⚠️ **routers/system.py** (Basic)
- Health check ✅
- Test question ✅
- Monitoring stats ✅

**Missing**:
- [ ] Admin endpoints (user management)
- [ ] Analytics endpoints (learning curves)

#### ✅ **services/llm.py** (Good)
- Groq integration for question generation ✅
- Hint generation with answer non-revelation ✅
- Proper error handling ✅

**Issues Found**:
- [ ] No prompt versioning (if prompts change, old questions are invalid)
- [ ] No quality scoring for generated questions
- [ ] No fallback when Groq API is down

#### ⚠️ **rag/agentic.py** (Functional but basic)
- 3-agent pipeline (Router→Retriever→Validator) ✅
- Wikipedia + Wikidata + HF dataset sourcing ✅

**Issues Found**:
- [ ] No source attribution in responses (users don't know where facts come from)
- [ ] No fact verification against multiple sources
- [ ] No concept extraction (questions don't auto-label concepts)
- [ ] Validator sometimes lets ambiguous facts through

#### ⚠️ **services/session.py** (Basic Redis)
- Session storage with 1hr TTL ✅
- Fallback to in-memory dict ✅

**Missing**:
- [ ] Distributed locking (prevents race conditions)
- [ ] Session expiry callbacks
- [ ] Cross-device session sync

---

### 2. FRONTEND STATUS

#### ✅ **pages/Home.tsx** - Present
#### ✅ **pages/Login.tsx** - Present
#### ✅ **pages/Signup.tsx** - Present
#### ✅ **pages/Dashboard.tsx** - Present
#### ⚠️ **pages/ClassicRoom.tsx** - Partially complete
- Session creation ✅
- Question display ✅
- Answer submission ❌ (form locking issue: can click options before question loads)
- Hints ✅

#### ❌ **pages/ChallengeRoom.tsx** - MISSING (entire feature)
**Needs**:
- [ ] Rank display
- [ ] Question view (limited options)
- [ ] Timer UI (countdown)
- [ ] Skip button with attempt counter
- [ ] Match history/results
- [ ] Leaderboard

#### ⚠️ **components/** - Incomplete
- **Missing**: Form validation locking, option disable during loading, timer component

#### ⚠️ **context/AuthContext.tsx** - Basic
- JWT storage ✅
- Login/logout ✅
- Dev bypass ✅

**Missing**:
- [ ] Token refresh logic (JWT should refresh before expiry)
- [ ] Session state persistence after page reload
- [ ] Error recovery (what if token invalid)

---

### 3. DATABASE SCHEMA GAPS

**Currently Missing Tables** ❌:

```sql
-- Challenge Room System
CREATE TABLE challenge_ranks (
  id SERIAL PRIMARY KEY,
  rank_name VARCHAR(50),           -- Bronze, Silver, Gold, Platinum, Diamond
  difficulty_level INT,             -- 1-5
  min_options INT,                  -- 2, 4, 4, 4, 0 (open-ended)
  time_limit_seconds INT,            -- 45, 40, 35, 30, 25
  elo_threshold INT,                -- min ELO to access

  created_at TIMESTAMP
);

CREATE TABLE user_challenge_ranks (
  id UUID PRIMARY KEY,
  user_id UUID REFERENCES users,
  current_rank_id INT REFERENCES challenge_ranks,
  elo INT DEFAULT 1200,
  matches_played INT DEFAULT 0,
  matches_won INT DEFAULT 0,
  skip_attempts_remaining INT DEFAULT 1,
  skip_cooldown_until TIMESTAMP,

  created_at TIMESTAMP,
  updated_at TIMESTAMP
);

CREATE TABLE challenge_matches (
  id UUID PRIMARY KEY,
  user_id UUID REFERENCES users,
  rank_id INT REFERENCES challenge_ranks,
  questions_count INT DEFAULT 5,
  score INT DEFAULT 0,
  elo_before INT,
  elo_after INT,
  elo_change INT,
  status VARCHAR(20),               -- in_progress, completed, abandoned
  total_time INT,                   -- seconds
  started_at TIMESTAMP,
  ended_at TIMESTAMP
);

-- Question Repetition Tracking
CREATE TABLE question_repetitions (
  id UUID PRIMARY KEY,
  question_id UUID REFERENCES question_bank,
  user_id UUID REFERENCES users,
  times_shown INT DEFAULT 1,
  times_wrong INT DEFAULT 0,
  times_correct INT DEFAULT 0,
  last_shown TIMESTAMP,
  next_show_after TIMESTAMP,        -- for spaced repetition

  created_at TIMESTAMP,
  updated_at TIMESTAMP
);

-- User Activity Tracking (for ELO decay)
CREATE TABLE user_activity_log (
  id UUID PRIMARY KEY,
  user_id UUID REFERENCES users,
  activity_type VARCHAR(50),        -- quiz_completed, challenge_match, login
  metadata JSONB,                   -- context about activity
  activity_at TIMESTAMP,

  INDEX user_activity_idx (user_id, activity_at DESC)
);

-- Concept Mastery
CREATE TABLE concept_mastery (
  id UUID PRIMARY KEY,
  user_id UUID REFERENCES users,
  concept_id UUID REFERENCES concepts,
  mastered_at TIMESTAMP,            -- NULL until theta > 0.8
  confidently_mastered_at TIMESTAMP, -- NULL until theta > 1.5

  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  UNIQUE(user_id, concept_id)
);
```

---

## PART B: CRITICAL ISSUES IDENTIFIED

### 🔴 BLOCKING (Must fix before release)

1. **Challenge Room Completely Missing**
   - No endpoints implemented (except /status stub)
   - No frontend UI
   - No rank progression logic
   - No ELO calculation
   - **Impact**: Core feature unusable
   - **Effort**: 40+ hours

2. **Frontend Form Locking Missing**
   - Users can click options while question is loading
   - Can cause "answer submitted for wrong question"
   - **Impact**: Data integrity + user frustration
   - **Effort**: 2 hours

3. **Concept-Aware Filtering Missing**
   - Questions don't consider user's per-concept theta
   - Defeats the whole adaptive learning concept
   - **Impact**: System not actually adaptive
   - **Effort**: 8 hours

4. **Question Repetition Logic Missing**
   - No tracking of "asked 7 times already"
   - No spaced repetition scheduling
   - **Impact**: Learning effectiveness
   - **Effort**: 6 hours

### 🟡 HIGH PRIORITY

5. **Alembic Migrations Manual**
   - Missing migrations for new tables
   - Database schema not versioned
   - **Fix**: Run alembic revision --autogenerate
   - **Effort**: 1 hour

6. **Password Strength Validation**
   - Currently missing special char check
   - Allows weak passwords
   - **Effort**: 1 hour

7. **No E2E Tests**
   - Only unit tests exist
   - User workflows not tested end-to-end
   - **Impact**: Can't catch integration bugs
   - **Effort**: 20 hours

8. **Test User Profiles Missing**
   - No varied concept knowledge
   - All test users have same theta
   - **Effort**: 2 hours

### 🟠 MEDIUM PRIORITY

9. **ELO Decay System**
   - Users inactive >30 days don't lose ELO
   - Leaderboards become stale
   - **Effort**: 4 hours

10. **Question Quality Gates**
    - No filtering of bad generated questions
    - Some questions factually incorrect
    - **Effort**: 8 hours

11. **Production Logging**
    - Only basic structlog
    - No log aggregation
    - No distributed tracing
    - **Effort**: 16 hours (with ELK/DataDog)

---

## PART C: DESIGN & UX ASSESSMENT

### UI/UX Strengths ✅
- Clean dashboard layout
- Clear button hierarchy
- Responsive design (mobile working)
- Loading states present
- Hints button prominent

### UI/UX Issues ⚠️

1. **Form Interaction Feedback**
   - [ ] No visual feedback when selecting answer (should highlight)
   - [ ] No loading spinner on submit
   - [ ] Disabled state not clear enough
   - **Fix**: Add spinner, highlight, button disable during submission

2. **Timer UI Missing**
   - [ ] Challenge room has no countdown timer visible
   - [ ] Users don't know time remaining
   - [ ] Can submit after time expires (no client-side check)
   - **Fix**: Add countdown timer component, client-side timeout

3. **Explanation Display**
   - [ ] Explanation text sometimes too long
   - [ ] Not scrollable on small screens
   - [ ] No formatting (bold, lists)
   - **Fix**: Limit 200 chars, make scrollable, format with markdown

4. **Hint UI**
   - [ ] Hint button doesn't disable after use
   - [ ] No visual indication hint was used
   - [ ] Hint text sometimes too long for popup
   - **Fix**: Disable button, show "Hint Used" badge, modal instead of popup

5. **Progress Tracking**
   - [ ] No progress bar (user doesn't know session length)
   - [ ] No score display during session
   - [ ] Post-session stats minimal
   - **Fix**: Add progress bar, session stats card, comparison to avg

### Design System Consistency
- **Tailwind**: Using well, good color scheme ✅
- **Components**: Reusable components lacking ⚠️
- **Typography**: Inconsistent sizes in some places ⚠️
- **Spacing**: Generally good ✅

---

## PART D: DATA MODEL ISSUES

### Per-Concept Adaptivity: Partial Implementation

**Current State**:
- `concepts` table exists
- `user_concept_theta` table exists
- IRT calculates theta updates

**Missing**:
- [ ] Concept extraction from generated questions
- [ ] Question filtering by concept (show questions in user's weak areas)
- [ ] Concept-specific difficulty selection

**Example Bug**:
```python
# Current: Returns ANY question from cache
question = await get_random_question(topic=topic)

# Needed: Filter by concept + user's theta that concept
weak_concepts = get_concepts_below_theta(user_id, threshold=0.5)
question = await get_question_by_concept(weak_concepts[0])
```

### ELO System

**For Challenge Room**:
- Starting ELO: 1200
- Win: +40 ELO
- Loss: -40 ELO
- Draw (timeout): -10 ELO

**Missing**:
- [ ] Netting K-factor based on rating (higher-rated users lose less)
- [ ] Decay system (inactive >30 days: -5 ELO/week)
- [ ] Cheating detection (too many 100% accuracy = flag)

---

## PART E: MISSING FEATURES ROADMAP

### Phase 1 (4 weeks - MVP Completion)
- [x] Classic room working
- [x] Basic hints
- [x] Authentication
- [ ] **Challenge room implementation** (2 weeks)
  - [ ] Rank definitions database
  - [ ] Match logic (timer, limited options, skip system)
  - [ ] ELO calculation
  - [ ] Frontend challenge UI (2 weeks)
    - [ ] Rank display
    - [ ] Question view (2-4 options based on rank)
    - [ ] Timer component
    - [ ] Results screen
    - [ ] Leaderboard

### Phase 2 (3 weeks - Adaptive Intelligence)
- [ ] Per-concept question filtering (1 week)
  - [ ] Auto-extract concepts from generated questions
  - [ ] Rank questions by user's concept theta
  - [ ] Prioritize weak concepts
- [ ] Question repetition logic (1 week)
  - [ ] Track question ID in user_responses
  - [ ] Schedule reappearance based on spaced repetition
  - [ ] Confidence scoring
- [ ] ELO decay system (3 days)
  - [ ] Activity tracking table
  - [ ] Daily decay calculation
  - [ ] Leaderboard recalculation

### Phase 3 (2 weeks - Polish & Quality)
- [ ] Question quality gates (1 week)
  - [ ] Fact-check against multiple sources
  - [ ] Remove ambiguous options
  - [ ] Validate explanations
- [ ] E2E testing (1 week)
  - [ ] Selenium for full user journeys
  - [ ] PDF report generation
  - [ ] CI/CD integration
- [ ] Production logging (3 days)
  - [ ] ELK stack setup
  - [ ] APM integration
  - [ ] Dashboard creation

### Phase 4 (1 week - Admin & Analytics)
- [ ] Admin dashboard
  - [ ] User management
  - [ ] Question editing
  - [ ] Statistical analysis
  - [ ] Cheating detection alerts
- [ ] Learning analytics
  - [ ] Progress charts
  - [ ] Concept mastery timeline
  - [ ] Recommended next questions

---

## PART F: VS CODE AGENT PROMPT

### For Use with VS Code Copilot or Claude Agent

```
## Your Role: AdaptIQ Development Agent

You are the technical lead for AdaptIQ, an adaptive learning quiz platform. You help with:
- Code reviews focused on IRT adaptivity logic
- Identifying database schema gaps
- Frontend/backend integration issues
- Performance bottlenecks in RAG pipeline
- Test coverage and edge cases

## Project Context

### What AdaptIQ Does
1. **Classic Room**: User answers MCQs, difficulty adapts based on their performance (IRT 1PL model)
2. **Challenge Room**: Competitive ranked mode with ELO, timer, and skill-based rank progression
3. **Adaptive Features**: Per-concept ability tracking, question repetition, learning path optimization

### Key Technologies
- Backend: FastAPI + SQLAlchemy + PostgreSQL + Redis
- Frontend: React 19 + TypeScript + Tailwind
- LLM: Groq API for question generation
- IRT: 1-Parameter Logistic model for adaptive difficulty

### Current State (April 2, 2026)
- ✅ Authentication working (JWT + bcrypt)
- ✅ Classic room question generation + answer submission
- ✅ Server-side time tracking (prevents client manipulation)
- ✅ Basic hints system
- ❌ Challenge room not implemented
- ❌ Per-concept question filtering missing
- ❌ Frontend form locking missing

## Your Task: Code Analysis & Implementation Guidance

When given a code file, you should:

1. **Identify Architectural Issues**
   - Is the IRT calculation correct for this code path?
   - Are database queries N+1 vulnerable?
   - Is async/await used properly?
   - Are there race conditions in session updates?

2. **Check Adaptive Logic**
   - Does the system consider user's per-concept theta?
   - Are questions ranked by user's weakness?
   - Is spaced repetition scheduled correctly?
   - Is ELO decay applied for inactive users?

3. **Validate Data Model**
   - Are foreign keys properly enforced?
   - Is there a migration for new tables?
   - Are indices on frequently-queried columns?
   - Is the schema normalized to 3NF?

4. **Frontend Integration**
   - Does frontend lock form during API calls?
   - Are timers client-side validated?
   - Is token refresh automatic?
   - Are error states shown to user?

5. **Provide Actionable Feedback**
   - State issue clearly with line numbers
   - Show before/after code examples
   - Estimate fix effort
   - Explain impact on users

## Critical Files to Know

Backend:
- backend/main.py (app bootstrap, middleware)
- backend/database/models.py (schema definition)
- backend/database/irt.py (adaptive difficulty math)
- backend/routers/classic_room.py (question → answer flow)
- backend/routers/challenge.py (NEEDS IMPLEMENTATION)
- backend/services/llm.py (Groq integration)
- backend/rag/agentic.py (RAG pipeline)

Frontend:
- frontend/src/pages/ClassicRoom.tsx (quiz UI)
- frontend/src/pages/ChallengeRoom.tsx (MISSING)
- frontend/src/context/AuthContext.tsx (auth state)
- frontend/src/services/apiService.ts (API calls)

Database:
- MISSING: challenge_ranks, user_challenge_ranks, challenge_matches
- MISSING: question_repetitions, user_activity_log, concept_mastery

## Code Quality Standards

- No N+1 queries (use relationships)
- All async functions properly awaited
- Proper error handling with logging
- Type hints on all function signatures
- Test coverage >80% for business logic
- No hardcoded values (use config)
- SQL injection prevention (parameterized queries)
- XSS prevention (never trust user input)

## When Reviewing Code, Ask

1. "Does this respect user's concept knowledge?" (adaptive check)
2. "Could this timeout or N+1 at scale?" (performance check)
3. "What if data is concurrent?" (concurrency check)
4. "Is this logged for debugging?" (observability check)
5. "What happens if Groq API is down?" (resilience check)

## Success Metrics

- All endpoints return <200ms p95 latency
- Zero unhandled exceptions (all logged)
- User can't manipulate difficulty or score
- Questions appropriately difficult (60-75% success rate target)
- Hints never reveal answers
- Challenge room accessible only after 10+ classic questions
```

---

## PART G: NEXT STEPS (PRIORITY ORDER)

### Week 1: Unblock Core Features
- [ ] **Challenge Room Backend (40 hours)**
  1. Create database migrations (challenge_ranks, user_challenge_ranks, challenge_matches)
  2. Implement POST /api/rooms/challenge/start
  3. Implement GET/POST for match gameplay
  4. Implement ELO calculation
  5. Test with API client

- [ ] **Challenge Room Frontend (40 hours)**
  1. Create Challenge pages structure
  2. Timer component
  3. Answer submission (2-4 options based on rank)
  4. Results screen
  5. Leaderboard view
  6. Integration testing

- [ ] **Form Locking on Frontend (2 hours)**
  1. Disable option buttons during API call
  2. Add spinner
  3. Show submission feedback

### Week 2: Adaptive Logic
- [ ] **Per-Concept Question Filtering (8 hours)**
  1. Auto-extract concepts from questions (in RAG)
  2. Get user's concept theta for each concept
  3. Prioritize weak concepts (theta < 0.0)
  4. Filter question pool accordingly

- [ ] **Question Repetition System (6 hours)**
  1. Track question IDs in user_responses
  2. Create question_repetitions table
  3. On wrong answer: schedule reappear in 3 quizzes
  4. On correct: schedule reappear in 30 quizzes

- [ ] **Test User Profiles (2 hours)**
  1. Create 5 users with varied concept knowledge
  2. Pre-load them with historical answers
  3. Set each with different theta values per concept

### Week 3: Quality & Testing
- [ ] **E2E Tests (20 hours)**
  1. Selenium + pytest framework
  2. Full user journey: register → classic room → challenge room
  3. Verify adaptivity (difficulty increases with success)
  4. Verify ELO changes
  5. CI/CD integration

- [ ] **Question Quality Gates (8 hours)**
  1. Fact-check generated questions
  2. Validate 3+ plausible options (not 2 obvious, 2 fake)
  3. Check explanation accuracy
  4. Fallback to cached questions if gen fails

---

## PART H: DEBUGGING TOOLKIT

### For Common Issues

**Issue: Questions too easy/hard**
```
→ Check database: SELECT user_id, concept_id, theta FROM user_concept_theta WHERE user_id = 'X'
→ Check last 5 questions: SELECT id, topic, difficulty_irt FROM question_bank ORDER BY created_at DESC LIMIT 5
→ Inspect IRT math: Run backend/database/irt.py with test theta values
```

**Issue: Answer not recording**
```
→ Check Redux: user_id in localStorage
→ Check session: REDIS > GET session:{session_id}
→ Check database: SELECT * FROM user_responses WHERE user_id = 'X' ORDER BY created_at DESC LIMIT 5
```

**Issue: Hints revealing answers**
```
→ Check llm.py: verify prompt says "DO NOT reveal the answer"
→ Test directly: Send hint request, grep response for option keywords
→ Manual review: Read 10 hints for answer keywords
```

**Issue: Challenge room 403**
```
→ Check user's classic question count: SELECT COUNT(*) FROM user_responses WHERE user_id = 'X'
→ Check minimum threshold in challenge.py
→ Check user's JWT scope (is_authenticated=true)
```

---

## Code Quality Checklist

Use when reviewing any PR:

- [ ] Types: All function args + returns typed
- [ ] Async: All async/await used correctly, no blocking calls
- [ ] Errors: All exceptions caught + logged
- [ ] Database: No N+1 queries, proper joins
- [ ] Security: No SQL injection, XSS, CSRF vulnerabilities
- [ ] Performance: <200ms endpoint latency, <50ms DB queries
- [ ] Tests: >80% coverage, edge cases covered
- [ ] Logging: All important decisions logged
- [ ] Config: No hardcoded values
- [ ] API: Proper status codes (201 for create, 422 for validation, etc)

---

## Conclusion

**Time to Production**: 3-4 weeks with 2 developers

**Critical Path**:
1. Challenge room & frontend (1 week)
2. Concept filtering (3 days)
3. Question repetition (2 days)
4. E2E tests (3 days)
5. Production deployment (1 day)

**Known Technical Debt**: ~60 hours of legacy code cleanup deferred to post-MVP

**Risks**:
- RAG pipeline unreliability (Groq API timeouts) → mitigation: cache + fallback
- Concept extraction accuracy → verify manually against 10% of generated questions
- ELO inflation in challenge room → add rating decay + cheating detection

---

**Next Meeting**: After implementing Challenge Room endpoints (est. 1 week)
