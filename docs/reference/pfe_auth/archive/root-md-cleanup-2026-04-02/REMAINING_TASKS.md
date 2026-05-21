# 📋 REMAINING TASKS - IMPLEMENTATION PLAN

## Overview
7 major tasks identified for AdaptIQ. This document outlines the implementation strategy and priority.

## Task Status

### 1. ✅ Switch Frontend to V2 Endpoints
**Status**: BLOCKED - SECURITY ISSUE FIRST
**Priority**: HIGH
**Impact**: Eliminates correctAnswer leak, uses index-based answers

**Issue Found**:
- V1 endpoints leak correctAnswer in response (security risk)
- V2 endpoints use index-based submission (safer)
- Frontend still calls V1 endpoints
- Backend already supports both

**Current State**:
- V1 endpoints: `/questions`, `/hints`, `/answers`
  - Generate question returns correctAnswer (✅ FIXED: now hidden)
  - Generate hint takes correctAnswer parameter (✅ FIXED: now gets from session)
  - Submit answer takes string answer (works but risky)

- V2 endpoints: `/start`, `/answer/{session_id}`, `/hint/{session_id}`
  - Start session returns first question (no correctAnswer)
  - Submit answer by index (safer)
  - Hint gets correctAnswer from session

**Migration Work**:
- Update apiService.ts to use V2 POST /start instead of POST /questions
- Change submitAnswer to use selected_index instead of selected_answer
- Update generateHint to not require correctAnswer parameter
- Update ClassicRoom component to store session_id
- Test full flow

**Estimated Effort**: 3-4 hours (moderate complexity)

---

### 2. ✅ Fix Response Count Double-Increment
**Status**: VERIFIED SAFE
**Priority**: LOW
**Finding**: Code already uses atomic SQL increment (line 98 in concept_irt.py)
- Uses `UserConceptTheta.response_count + 1` in SQL
- Comment explicitly warns against incrementing in memory
- No double-increment risk

**Effort**: 0 (Already fixed)

---

### 3. 🔄 Fix Timer Auto-Answer to Submit to Backend
**Status**: PARTIAL
**Priority**: MEDIUM
**Current Implementation**: Lines 57-71 in ClassicRoom.tsx

**What Works**:
- Timer counts down correctly
- When reaches 0, detects timeout
- Calls submitAnswer with empty string

**What Needs**:
- Ensure it awaits submission (currently fire-and-forget)
- Verify session is locked during timeout
- Test that next question doesn't load until timeout submits

**Estimated Effort**: 1-2 hours

---

### 4. 🔴 Normalize Topic Casing
**Status**: INCONSISTENT
**Priority**: MEDIUM
**Current Chaos**:
- Frontend types: Title case ('Geography', 'History', 'Mixed')
- Backend schemas: Title case ("History", "Geography", "Mixed")
- Seeds: Lowercase ("geography", "history")
- Classic service: Expects lowercase per comments
- RAG system: Title case

**Solution**: Standardize on TITLE CASE everywhere
- Update seed.py to use Title case
- Verify all backend endpoints accept Title case
- Add case-insensitive matching as fallback

**Files to Update**:
- `backend/seeds/seed.py`: ~60 lowercase references
- `backend/services/classic_service.py`: Add case normalization
- `backend/rag/*`: Verify Title case handling

**Estimated Effort**: 2-3 hours

---

### 5. 🏗 Build Challenge Room Frontend Page
**Status**: NOT STARTED
**Priority**: HIGH (Feature Complete)
**Scope**: Significant UI work

**TODO**:
1. Create frontend/src/pages/ChallengeRoom.tsx
   - Display current rank (Bronze/Silver/Gold/Platinum/Diamond)
   - Show rank requirements and stats
   - Button to "Start Match"
   - Option to "Skip to higher rank"

2. Implement match flow:
   - Display 10 questions with timer (if rank >= Silver)
   - Track win/loss condition (70% = win)
   - Show results and next rank

3. Add components:
   - RankBadge: Visual rank display
   - MatchStats: Score, accuracy, time
   - RankProgression: Visual progression bar

**Integration Points**:
- New API endpoints exist: `/api/rooms/challenge/start`, `/answer/{match_id}`, `/end/{match_id}`
- Backend already tracks rank, wins/losses
- Just need responsive UI

**Estimated Effort**: 6-8 hours (complex UI)

---

### 6. 🔧 Implement Dev Bypass UI
**Status**: NOT STARTED
**Priority**: MEDIUM (Developer QoL)
**Scope**: Quick UI toggle

**Features**:
1. Dev panel triggered by `?dev=true` URL parameter
2. Quick controls:
   - Set difficulty (1-5 slider)
   - Set accuracy (0-100%)
   - Skip timer
   - Generate test question
   - View current session state

3. Visual indicator:
   - Red banner "DEV MODE ACTIVE"
   - URL shows `?dev=true`
   - Panel appears bottom-right

**Implementation**:
- Add dev context/hook
- Parse URL params on mount
- Add dev panel component
- All controls optional (don't break non-dev flow)

**Estimated Effort**: 3-4 hours

---

### 7. 📊 Build Profile Page with Concept Theta Visualization
**Status**: NOT STARTED
**Priority**: MEDIUM (Analytics)
**Scope**: Data visualization page

**TODO**:
1. Create frontend/src/pages/Profile.tsx
   - Display user stats (points, level, global accuracy)
   - Show topic breakdowns
   - Concept mastery matrix

2. Add components:
   - StatsCard: Points, level, rank
   - ConceptHeatmap: Visualize all concepts with θ values
   - TopicProgress: Bar charts for History/Geography/Mixed
   - TheataTrendChart: θ progression over time

3. Backend integration:
   - GET /api/auth/stats → user overview
   - GET /api/auth/stats/concept-mastery → all concepts + θ values
   - GET /api/auth/stats/daily-trend → performance history

4. Visualizations:
   - Heatmap library (recharts or plotly.js)
   - Color coding: Red (weak) → Green (strong)
   - Interactive tooltips

**Estimated Effort**: 8-10 hours (very UI-heavy)

---

## Recommended Implementation Order

### Phase 1: Critical Fixes (4-6 hours)
1. **Normalize Topic Casing** (2-3 hours)
   - Fixes data consistency
   - Unblocks other work
   - Low risk

2. **Timer Auto-Answer** (1-2 hours)
   - Current functionality broken
   - User-facing bug
   - Medium complexity

### Phase 2: Security Enhacement (3-4 hours)
3. **V2 Endpoint Migration** (3-4 hours)
   - Eliminates correctAnswer leak
   - Uses safer index-based answers
   - Backend ready, frontend needs update

### Phase 3: New Features (16-22 hours)
4. **Dev Bypass UI** (3-4 hours) - Easiest new feature
5. **Challenge Room** (6-8 hours) - Core game feature
6. **Profile Page** (8-10 hours) - Analytics / showcase

---

## Risk Assessment

| Task | Risk | Mitigation |
|------|------|-----------|
| Topic Casing | LOW | Test with seed data |
| Timer Auto-Answer | LOW | Already mostly working |
| V2 Migration | MEDIUM | Test all answer flows |
| Dev UI | LOW | Feature toggle only |
| Challenge Room | MEDIUM | UI only, backend exists |
| Profile Page | MEDIUM | Third-party charts |

---

## Code Smells / Technical Debt

1. **Topic casing mess**: Results from mixed conventions
2. **Timer not awaiting**: Race condition risk
3. **V1/V2 endpoints**: Both maintained (redundant)
4. **Missing dev tools**: Hard to test adaptive difficulty
5. **No analytics UI**: Users can't see their progress

---

## Proposed Next Steps

1. **Run current tests** - Validate nothing broke from recent changes
2. **Implement Phase 1** - Topic casing + timer fix (quick wins)
3. **Implement Phase 2** - V2 migration (security)
4. **Plan Phase 3** - Could extend to full project

**Total Estimated Effort**: 24-32 hours for all tasks

---

**Generated**: April 1, 2026
**Status**: Ready for implementation
