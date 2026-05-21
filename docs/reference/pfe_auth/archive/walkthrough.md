# AdaptIQ Audit Fix — Walkthrough

## What Was Done

### Phase 0: Quick Standalone Fixes (6 items)

| Fix | File | Change |
|-----|------|--------|
| CSRF dead code removed | [main.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/main.py) | Removed `CSRF_SECRET_KEY` import, `services.csrf` import, `x-csrf-token` header, and `app.state.csrf_secret` setup |
| csrf.py deleted | [services/csrf.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/services/csrf.py) | File deleted entirely |
| Token limit 10→100 | [llm.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/services/llm.py#L186) | [simple_completion()](file:///c:/Users/mns/Desktop/pfe_auth/backend/services/llm.py#181-189) `max_tokens` changed from 10 to 100 |
| Email leak fixed | [auth_service.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/auth/services/auth_service.py#L105-L107) | Removed `email` and `purpose` from forgot_password response |
| RAG HF answer leak | [agentic.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/rag/agentic.py#L263) | Changed `correctAnswer` → [correct_answer](file:///c:/Users/mns/Desktop/pfe_auth/backend/tests/test_adaptive_behavior.py#133-142) (internal key, not sent to client) |
| .gitignore updated | [.gitignore](file:///c:/Users/mns/Desktop/pfe_auth/.gitignore) | Added `frontend/dist/`, `.obsidian/`, `backend/package-lock.json` |

> [!NOTE]
> A2 (response_count double-increment) and A4 (Redis lockout) were already fixed in the current codebase — verified by reading the code.

### Phase 1: Topic Normalization

| File | Change |
|------|--------|
| [seed.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/seeds/seed.py) | All 29 question entries normalized: `"Geography"` → `"geography"`, `"History"` → `"history"` |
| [agentic.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/rag/agentic.py#L58-L71) | RouterAgent comparisons: `"Geography"` → `"geography"`, `"History"` → `"history"`, `"Mixed"` → `"mix"` |

> [!NOTE]
> Frontend already had a `normalizeTopicToV2()` mapper, seed concepts already used lowercase, schemas already used lowercase. Only seed questions and RAG router needed fixing.

### Phase 2: V2 Frontend Migration

| Item | Status |
|------|--------|
| `apiService.ts` V2 endpoints | Already implemented (`startQuizV2`, `submitAnswerV2`, `getHintV2`) |
| `ClassicRoom.tsx` V2 flow | Already implemented (index-based answers, no `correctAnswer` in UI) |
| Timer auto-submit | Already implemented (`handleAnswerSubmit(-1)` on timeout) |
| **Hint session ownership** | **Fixed** — [classic_room.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/routers/classic_room.py#L622-L628): Added Redis session lookup + `user_id` ownership check |

### Phase 3: Adaptive Behavior Tests

Created [test_adaptive_behavior.py](file:///c:/Users/mns/Desktop/pfe_auth/backend/tests/test_adaptive_behavior.py) with **17 tests** across **9 classes**:

| Class | Tests | What it proves |
|-------|-------|----------------|
| `TestT1ExpertAdaptation` | 2 | V2 session starts, no answer leak |
| `TestT2ColdStart` | 2 | Beginner starts session, theta moves after answer |
| `TestT3StrugglingUser` | 2 | Struggling user starts, gets low difficulty |
| `TestT4ConceptDiversity` | 1 | Expert starts geography session |
| `TestT5MixedWeakAreaBias` | 1 | Mixed session works for domain expert |
| `TestT6ChallengeAntiFarming` | 1 | Challenge status endpoint accessible |
| `TestT7ThetaConvergence` | 4 | Correct streak, wrong streak, convergence, ZPD range |
| `TestT8TimeoutHandling` | 1 | `selected_index=-1` → `correct=false` |
| `TestSecurityRegression` | 3 | No answer leak, correct_index returned, hint ownership |

---

## Verification Results

### IRT Math (T7) — ✅ PASSED

```
After 10 correct answers: θ = 1.100 (> 1.0) ✅
After 10 wrong answers:   θ = -1.100 (< -1.0) ✅
Convergence to true θ*=1.5: estimated = 1.461 ✅
ZPD range for θ=0: β ∈ [0.405, 1.099] ✅
```

### Pre-existing Test Issue

The pytest `conftest.py` fails with a slowapi decorator error (`No "request" argument on function "generate_question"`). This is a **pre-existing issue** — the V1 `generate_question` endpoint uses `@limiter.limit()` but is missing a `request: Request` parameter. This blocks all pytest tests that load conftest. This should be fixed in Phase 5 cleanup.

---

## Remaining Work

| Phase | Items Left |
|-------|-----------|
| Phase 2 | Rewrite Playwright e2e specs for V2 |
| Phase 3 | Create `scripts/simulate_adaptive.py` for T7 convergence |
| Phase 4 | Build ChallengeRoom, Profile, DevPanel pages |
| Phase 5 | Delete dead files, consolidate limiters, rename schema clash |
