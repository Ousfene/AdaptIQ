# AdaptIQ Comprehensive Code Audit — 2026-04-01

Full source-level audit of every file in the backend and frontend.

---

## 🔴 CRITICAL — Bugs, Logical Errors, Security

### 1. `correctAnswer` Leaked to Client (V1 Endpoints)
**Files:** [classic_room.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/routers/classic_room.py#L291-L298), [apiService.ts](file:///c:/Users/mns/Desktop/pfe_auth/frontend/src/services/apiService.ts#L109), [ClassicRoom.tsx](file:///c:/Users/mns/Desktop/pfe_auth/frontend/src/pages/ClassicRoom.tsx#L104-L105)

The V1 `/questions` endpoint returns `correctAnswer` in the response body. The frontend receives it and uses it for local answer checking ([normalizeAnswer(answer) === normalizeAnswer(currentQuestion.correctAnswer)](file:///c:/Users/mns/Desktop/pfe_auth/frontend/src/pages/ClassicRoom.tsx#28-29)). **Any user can inspect the network response to see the answer before clicking.** The V2 `/start` and `/answer/{session_id}` endpoints correctly omit the correct answer, but the **frontend still uses V1 endpoints**.

> [!CAUTION]
> This is a cheating vulnerability. The correct answer is visible in the browser DevTools Network tab.

### 2. `response_count` Double-Increment
**File:** [concept_irt.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/database/concept_irt.py#L83-L101)

In [update_concept_theta()](file:///c:/Users/mns/Desktop/pfe_auth/backend/database/concept_irt.py#40-105), the code first does `theta_record.response_count += 1` (ORM in-memory), then executes a SQL `UPDATE` with `response_count=UserConceptTheta.response_count + 1` (atomic DB increment). Both paths increment the counter, so **response_count grows by 2 for every answer** instead of 1.

### 3. Hardcoded CSRF Secret
**File:** [main.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/main.py#L153)

```python
app.state.csrf_secret = "your-secret-key-change-in-production"  # TODO still there
```
This is a hardcoded secret with a `TODO` that was never fixed.

### 4. Redis Unavailable → All Normal JWTs Rejected
**File:** [security.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/auth/core/security.py#L83-L85)

[is_token_revoked()](file:///c:/Users/mns/Desktop/pfe_auth/backend/auth/core/security.py#74-96) returns `True` when Redis is down. This means **if Redis goes down, all authenticated users are locked out** — even though the comment says "fail secure." In a dev environment where Redis might stop, this causes cascading auth failures that look like invalid tokens.

### 5. Timer Auto-Answer Never Submits to Backend
**File:** [ClassicRoom.tsx](file:///c:/Users/mns/Desktop/pfe_auth/frontend/src/pages/ClassicRoom.tsx#L56-L58)

When `timeLeft === 0`, the code sets `isAnswered = true` but **never calls [submitAnswer()](file:///c:/Users/mns/Desktop/pfe_auth/frontend/src/services/apiService.ts#161-200)**. This means: the user sees the result locally, but the backend never records the answer, the IRT theta is not updated, and the response is lost.

### 6. Frontend Uses V1 Endpoints, V2 Exists But Is Unused
**Files:** [apiService.ts](file:///c:/Users/mns/Desktop/pfe_auth/frontend/src/services/apiService.ts) vs [classic_room.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/routers/classic_room.py#L470-L641)

The frontend calls V1 endpoints (`/questions`, `/answers`, `/hints`) which have different schemas and behavior than the V2 endpoints (`/start`, `/answer/{session_id}`, `/hint/{session_id}`, `/metrics/{session_id}`). The V2 endpoints are fully built with proper session management, IRT concept selection, and no answer leak — but **no frontend code calls them**.

---

## 🟡 MAJOR — Mismatches, Logic Flaws, Design Issues

### 7. Topic Case Mismatch Between Frontend and Backend
- **Frontend** sends: `"Geography"`, `"History"`, `"Mixed"` (title-case in [types.ts](file:///c:/Users/mns/Desktop/pfe_auth/frontend/src/types.ts#L4))
- **V2 backend** expects: `"geography"`, `"history"`, `"mix"` (lowercase in [schemas.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/schemas.py#L210))
- **V1 backend** expects: `"History"`, `"Geography"`, `"Mixed"` (title-case in [schemas.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/schemas.py#L7))
- **Seed data** uses various: the `Concept.topic` field stores whatever was used during seeding
- **[crud.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/database/crud.py) TOPICS tuple**: [("History", "Geography", "Mixed")](file:///c:/Users/mns/Desktop/pfe_auth/frontend/src/App.tsx#44-51) — title-case

This mismatch means V2 concept selection queries `WHERE concept.topic = 'geography'` will **return 0 results** if seed data stored `"Geography"`.

### 8. V1 `/answers` Validates Answer by String Comparison
**File:** [classic_room.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/routers/classic_room.py#L362-L366)

Answer validation compares the submitted text against `session["correct_answer"]` using [_normalize_answer()](file:///c:/Users/mns/Desktop/pfe_auth/backend/routers/classic_room.py#51-54) (`.strip().casefold()`). This is fragile:
- LLM-generated options may have trailing punctuation or different unicode forms
- No index-based checking — the V2 approach (compare `selected_index` against `correct_index`) is much more robust

### 9. `user_id` Still in V1 Request Bodies (AGENT_PROMPT says remove)
**Files:** [schemas.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/schemas.py#L95-L96), [apiService.ts](file:///c:/Users/mns/Desktop/pfe_auth/frontend/src/services/apiService.ts#L87)

Both [GenerateQuestionRequest](file:///c:/Users/mns/Desktop/pfe_auth/backend/schemas.py#92-97) and [SubmitAnswerRequest](file:///c:/Users/mns/Desktop/pfe_auth/backend/schemas.py#108-115) include `user_id`. The AGENT_PROMPT explicitly says: *"Remove user_id from request bodies — always read from current_user.id."* The backend does verify `body.user_id != current_user.id`, but this is redundant — the user_id should come from the JWT only.

### 10. No Challenge Room Frontend
**File:** [App.tsx](file:///c:/Users/mns/Desktop/pfe_auth/frontend/src/App.tsx)

No route for `/rooms/challenge`. The backend Challenge Room API is fully implemented with 4 endpoints, but there is **zero frontend UI** for it. The dashboard mentions a "Challenge Room" button concept but no page exists.

### 11. No Profile Page
**File:** [App.tsx](file:///c:/Users/mns/Desktop/pfe_auth/frontend/src/App.tsx)

AGENT_PROMPT specifies a `/profile` page with per-concept theta charts, session history, and rank badge. No such page or route exists.

### 12. Hint Endpoint Doesn't Verify Session Ownership
**File:** [classic_room.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/routers/classic_room.py#L593-L594)

```python
_ = session_id  # Validates session ownership in future
_ = current_user  # Ensures user is authenticated
```
The V2 hint endpoint takes `session_id` but **never checks if the session belongs to the current user**. Any authenticated user could get hints for any session.

### 13. Adaptivity Score Uses Crude Approximation
**File:** [classic_service.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/services/classic_service.py#L633-L638)

```python
if 2 <= resp.difficulty_sent <= 4:
    in_zpd_count += 1
```
Instead of computing actual ZPD (θ ± β probability), it considers any difficulty 2-4 as "in ZPD." This makes the metric meaningless.

### 14. Metrics Endpoint Returns Empty `theta_progress`
**File:** [classic_room.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/routers/classic_room.py#L636)

```python
theta_progress=[],  # Would need session state tracking for full progress
```
The metrics endpoint always returns an empty list for theta progress, which is useless.

### 15. [generate_hint](file:///c:/Users/mns/Desktop/pfe_auth/backend/routers/classic_room.py#301-317) (V1) Sends `correctAnswer` from frontend
**File:** [apiService.ts](file:///c:/Users/mns/Desktop/pfe_auth/frontend/src/services/apiService.ts#L119-L127)

The hint request sends `correctAnswer` from the frontend to the backend as a parameter. Since the frontend already has the correct answer (bug #1), this is doubly insecure — the correct answer travels both directions.

### 16. [concept_extractor.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/services/concept_extractor.py) Uses [simple_completion](file:///c:/Users/mns/Desktop/pfe_auth/backend/services/llm.py#181-189) (10 token limit)
**File:** [concept_extractor.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/services/concept_extractor.py#L61), [llm.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/services/llm.py#L181-L188)

[simple_completion](file:///c:/Users/mns/Desktop/pfe_auth/backend/services/llm.py#181-189) has `max_tokens=10`. The concept extraction prompt asks for `PRIMARY: [name]\nSECONDARY: [name]` which requires ~20-30 tokens. The response will be truncated, causing frequent parsing failures and falling back to generic concepts.

---

## 🟠 MODERATE — Inconsistencies, Missing Features, Cleanup

### 17. Duplicate `Limiter` Instances
**Files:** [main.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/main.py#L156), [dependencies.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/dependencies.py#L14), [classic_room.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/routers/classic_room.py#L48), [challenge.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/routers/challenge.py#L47)

Four separate `Limiter(key_func=get_remote_address)` instances. Only the one on `app.state.limiter` has the exception handler. The router-level limiters create their own instances that may not share state properly with the global one.

### 18. [pydantic_types.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/pydantic_types.py) Is a Dead Compatibility Shim
**File:** [pydantic_types.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/pydantic_types.py)

Only re-exports from [schemas.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/schemas.py). It's imported by [crud.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/database/crud.py) and should be removed — all imports should use `schemas` directly.

### 19. [QuestionOut](file:///c:/Users/mns/Desktop/pfe_auth/backend/schemas.py#81-90) Schema Has Two Versions
- V1 [QuestionOut](file:///c:/Users/mns/Desktop/pfe_auth/backend/schemas.py#81-90) (line 81-89 of schemas.py): includes `correctAnswer`, `explanation`, `locked`
- V2 [ClassicQuestionOut](file:///c:/Users/mns/Desktop/pfe_auth/backend/schemas.py#213-220) (line 213-219): excludes `correctAnswer` (correct design)

Both coexist in schemas.py and serve different code paths.

### 20. [get_current_user](file:///c:/Users/mns/Desktop/pfe_auth/backend/auth/core/dependencies.py#18-114) Opens a Separate DB Session
**File:** [auth/core/dependencies.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/auth/core/dependencies.py#L57-L59)

The auth dependency creates its own DB session (from `db_factory`) separate from the [get_db](file:///c:/Users/mns/Desktop/pfe_auth/backend/dependencies.py#17-24) dependency. This means each request opens **two DB sessions** — one for auth, one for the route logic. This wastes connection pool resources.

### 21. No Refresh Token Implementation
**File:** [security.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/auth/core/security.py)

Only [create_access_token](file:///c:/Users/mns/Desktop/pfe_auth/backend/auth/core/security.py#40-54) exists. No `create_refresh_token` function despite the AGENT_PROMPT specifying refresh tokens with 7-day expiry. The frontend also doesn't implement token refresh.

### 22. [UserResponse](file:///c:/Users/mns/Desktop/pfe_auth/backend/database/models.py#43-61) Model Name Clashes with Schema Name
**Files:** [models.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/database/models.py#L43) vs [schemas.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/schemas.py#L10)

Both the SQLAlchemy model and Pydantic schema are named [UserResponse](file:///c:/Users/mns/Desktop/pfe_auth/backend/database/models.py#43-61), requiring awkward aliasing (`UserResponse as UserResponseSchema` in auth router).

### 23. Dev Bypass Mode (`?dev=true`) Not Implemented in Frontend
The AGENT_PROMPT specifies a floating panel with test user selector when `?dev=true` is in the URL. No such component exists in the frontend.

### 24. `Base.metadata.create_all` in Lifespan
**File:** [main.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/main.py#L77)

Using `create_all` alongside Alembic migrations is contradictory. Alembic should be the sole schema manager. `create_all` can create tables that Alembic doesn't know about, causing migration conflicts.

### 25. [classic_service.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/services/classic_service.py) Missing `import json` at Module Level
**File:** [classic_service.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/services/classic_service.py#L299)

[json](file:///c:/Users/mns/Desktop/pfe_auth/frontend/package.json) is imported inside the function body instead of at module top. Not a bug, but poor practice.

---

## 🟢 MINOR — Code Quality, Unnecessary Files, Polish

### 26. Unnecessary Root-Level Files
| File | Status |
|------|--------|
| [ersmnsDesktoppfe_auth](file:///c:/Users/mns/Desktop/pfe_auth/ersmnsDesktoppfe_auth) (556 bytes) | Junk file — looks like a corrupted path string |
| [create_dirs.py](file:///c:/Users/mns/Desktop/pfe_auth/create_dirs.py) (220 bytes) | One-time script, should be deleted |
| [commit.bat](file:///c:/Users/mns/Desktop/pfe_auth/commit.bat), [git_commands.bat](file:///c:/Users/mns/Desktop/pfe_auth/git_commands.bat), [git_commands.sh](file:///c:/Users/mns/Desktop/pfe_auth/git_commands.sh) | Git helper scripts — cluttering root |
| [run-full-validation.ps1](file:///c:/Users/mns/Desktop/pfe_auth/run-full-validation.ps1), `show_project_files.ps1/sh`, [start-backend.ps1](file:///c:/Users/mns/Desktop/pfe_auth/start-backend.ps1) | Dev utility scripts — consider moving to `scripts/` dir |
| [backend.env.example](file:///c:/Users/mns/Desktop/pfe_auth/backend.env.example) | Should be `backend/.env.example` |
| [CLAUDE.md](file:///c:/Users/mns/Desktop/pfe_auth/CLAUDE.md), [COMPREHENSIVE_AUDIT.md](file:///c:/Users/mns/Desktop/pfe_auth/COMPREHENSIVE_AUDIT.md), [AUDIT.md](file:///c:/Users/mns/Desktop/pfe_auth/AUDIT.md), [STATUS.md](file:///c:/Users/mns/Desktop/pfe_auth/STATUS.md), [CONCEPT_AWARE_SYSTEM.md](file:///c:/Users/mns/Desktop/pfe_auth/CONCEPT_AWARE_SYSTEM.md) | Multiple overlapping docs from previous agent runs |
| [backend/package-lock.json](file:///c:/Users/mns/Desktop/pfe_auth/backend/package-lock.json) (86 bytes) | Python project — no package.json |
| [frontend/metadata.json](file:///c:/Users/mns/Desktop/pfe_auth/frontend/metadata.json) | Purpose unclear |
| `.obsidian/` | Obsidian vault config — should be in [.gitignore](file:///c:/Users/mns/Desktop/pfe_auth/.gitignore) |

### 27. `__pycache__` Directories Committed
Multiple `__pycache__` directories exist at root, backend, and throughout modules. These should be in [.gitignore](file:///c:/Users/mns/Desktop/pfe_auth/.gitignore).

### 28. `frontend/dist/` Should Be Gitignored
The `dist/` build output directory is present. Should not be committed.

### 29. Multiple `services/csrf.py` Imported but CSRF Not Actually Used
**File:** [services/csrf.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/services/csrf.py) (755 bytes)

Imported in `main.py` but `generate_csrf_token` and `validate_csrf_token` are never called on any endpoint.

### 30. `require_admin` Does Nothing Special
**File:** [auth/core/dependencies.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/auth/core/dependencies.py#L116-L117)

```python
async def require_admin(user: User = Depends(get_current_user)) -> User:
    return user
```
No admin check — it just returns the user. If admin functionality isn't needed, remove it.

### 31. `concept_cache_service.py` and `question_cache_service.py` — Unused
**Files:** [concept_cache_service.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/services/concept_cache_service.py) (14.9KB), [question_cache_service.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/services/question_cache_service.py) (4.5KB)

These services exist but are never imported by any router or service file.

### 32. RAG Module (`rag/`) Has No Tests
The `rag/agentic.py`, `wikipedia.py`, `wikidata.py`, `hf_dataset.py` files are substantial (~27KB total) but have zero test coverage.

---

## Front-Back Link Summary

| Frontend Call | Backend Endpoint | Status |
|---|---|---|
| `generateQuestion()` → `POST /questions` | V1 endpoint — **returns correctAnswer** | ⚠️ Security issue |
| `submitAnswer()` → `POST /answers` | V1 endpoint — string-based answer check | ⚠️ Fragile |
| `generateHint()` → `POST /hints` | V1 endpoint — sends correctAnswer from client | ⚠️ Design flaw |
| `fetchUserStats()` → `GET /stats` | Works correctly | ✅ |
| `fetchUserTopicBreakdown()` → `GET /stats/topic-breakdown` | Works correctly | ✅ |
| `fetchUserDailyTrend()` → `GET /stats/daily-trend` | Works correctly | ✅ |
| `fetchRedisOpsStats()` → `GET /stats/redis-ops` | Works, exposed to all users | ⚠️ Should be admin-only |
| `fetchConceptMastery()` → `GET /stats/concept-mastery` | Works correctly | ✅ |
| (none) → `POST /start` | V2 — **no frontend caller** | ❌ Dead code |
| (none) → `POST /answer/{session_id}` | V2 — **no frontend caller** | ❌ Dead code |
| (none) → `POST /hint/{session_id}` | V2 — **no frontend caller** | ❌ Dead code |
| (none) → `GET /metrics/{session_id}` | V2 — **no frontend caller** | ❌ Dead code |
| (none) → Challenge Room endpoints | **No frontend page** | ❌ Missing feature |

---

## Quality Assessment

| Area | Method | Rating | Notes |
|---|---|---|---|
| **IRT Engine** | 1PL model in `irt.py` | ✅ Good | Math is correct, well-documented |
| **Concept IRT** | Per-concept theta in `concept_irt.py` | ⚠️ Has bugs | Double-increment bug (#2) |
| **Session Management** | Redis + in-memory fallback | ✅ Solid | Lock mechanism, TTL, fallback |
| **Auth/JWT** | bcrypt + jose JWT | ✅ Good | Async hashing, revocation support |
| **Password Validation** | Pydantic validators | ✅ Good | Complexity requirements enforced |
| **Rate Limiting** | slowapi | ⚠️ Fragmented | 4 separate instances (#17) |
| **Quiz Flow (V1)** | Frontend → Backend → LLM | ⚠️ Insecure | Answer visible client-side (#1) |
| **Quiz Flow (V2)** | Session-based, server-verified | ✅ Good design | But unused by frontend (#6) |
| **Challenge Room** | Backend complete | ⚠️ No frontend | Solid backend logic, skip/anti-farming |
| **Frontend State** | React state + epoch tracking | ✅ Good | Spam prevention via `questionEpoch` |

---

## Recommended Priority Order

1. **Switch frontend to V2 endpoints** — eliminates correctAnswer leak, uses index-based answers
2. **Fix `response_count` double-increment** in `concept_irt.py`
3. **Fix timer auto-answer** to submit to backend
4. **Normalize topic casing** — pick one convention and apply everywhere
5. **Build Challenge Room frontend page**
6. **Implement dev bypass UI** (`?dev=true` panel)
7. **Clean up dead files** (junk files, unused services, overlapping docs)
8. **Move CSRF secret** to environment variable or remove unused CSRF code
9. **Add refresh token** support
10. **Build Profile page** with concept theta visualization
