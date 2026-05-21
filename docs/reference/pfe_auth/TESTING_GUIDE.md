# AdaptIQ Comprehensive Testing & Evaluation Guide

**Date**: April 2, 2026
**Status**: Phase 2 Complete - Test Users Created
**Next**: Phase 3 - Comprehensive Page Testing

---

## Overview

This document guides you through the comprehensive testing and evaluation of the AdaptIQ platform. The testing validates:

- User registration and authentication flows
- Classic room adaptive difficulty (IRT) system
- Challenge room rank progression
- Database state changes (theta, ELO, mastery levels)
- Cache behavior and hit rates
- Logging infrastructure for audit trails

---

## Phase 2: Test Users Created ✅

**5 test profiles have been successfully created** with different knowledge levels and subjects:

### Profile 1: Novice_Reader
- **Username**: `novice_reader_1775089851`
- **Email**: `novice_reader_test@example.com`
- **Password**: `TestPass123!@#`
- **Knowledge Level**: Beginner in all topics (θ = -2.0)
- **Topics**: Geography, History
- **Purpose**: Observe rapid learning curve as user answers questions
- **Expected Behavior**: Low accuracy (30-50%), theta increases quickly

### Profile 2: Geography_Expert
- **Username**: `geo_expert_1775089851`
- **Email**: `geo_expert_test@example.com`
- **Password**: `TestPass123!@#`
- **Knowledge Level**: Expert in geography (θ = 2.0), Novice in history (θ = -2.0)
- **Topics**: Geography, History
- **Purpose**: Verify asymmetric knowledge representation
- **Expected Behavior**: High accuracy on geography (70%+), low on history (30-40%)

### Profile 3: History_Expert
- **Username**: `hist_expert_1775089851`
- **Email**: `hist_expert_test@example.com`
- **Password**: `TestPass123!@#`
- **Knowledge Level**: Expert in history (θ = 2.0), Novice in geography (θ = -2.0)
- **Topics**: History, Geography
- **Purpose**: Verify opposite asymmetry to geo_expert
- **Expected Behavior**: High accuracy on history (70%+), low on geography (30-40%)

### Profile 4: Balanced_Learner
- **Username**: `balanced_1775089851`
- **Email**: `balanced_test@example.com`
- **Password**: `TestPass123!@#`
- **Knowledge Level**: Intermediate in both (θ = 0.0)
- **Topics**: Geography, History
- **Purpose**: Verify optimal ZPD learning (60-75% accuracy)
- **Expected Behavior**: Consistent 60-75% accuracy, stable theta

### Profile 5: Challenger
- **Username**: `challenger_1775089851`
- **Email**: `challenger_test@example.com`
- **Password**: `TestPass123!@#`
- **Knowledge Level**: Intermediate (θ = 1.0)
- **Topics**: Mixed
- **Purpose**: Focus on challenge room rank progression
- **Expected Behavior**: Rank progression from Bronze → higher ranks

---

## Phase 3: Comprehensive Page Testing

### Setup

1. **Start Backend**
   ```bash
   cd backend
   python main.py
   ```

2. **Start Frontend** (in another terminal)
   ```bash
   cd frontend
   npm run dev
   ```

3. **Access Application**
   - Open browser to `http://localhost:5173`

### Testing Procedure

For **each test profile**, follow this workflow:

#### Step 1: Login
1. Navigate to `/login`
2. Enter credentials (email + password from profile above)
3. Expected: Redirect to `/dashboard`, JWT token stored

#### Step 2: View Dashboard
1. Navigate to `/dashboard`
2. Verify displays:
   - User level
   - ELO rating (0.0 for new users)
   - Recent sessions (will be empty)
   - Achievement badges
3. **Log File**: Check `backend/logs/` for session events

#### Step 3: View Profile
1. Navigate to `/profile`
2. Verify displays:
   - Concept list (Geography, History concepts)
   - Theta progression bars (will show neutral 0.0 for new users)
   - Mastery levels (should be "Beginner" initially)
   - Concept state (should be "Exploring")
3. **Check**: Concepts match database records

#### Step 4: Classic Room (Main Test)
1. Navigate to `/rooms/classic`
2. **Start Session**
   - Select topic: "geography", "history", or "mix"
   - Click "Start Quiz"
   - Session ID created and stored
3. **For 10 questions, repeat:**
   - **View Question**
     - Note question ID, difficulty indicator
     - Check: Are options shuffled?
     - Log: Question shown event
   - **Submit Answer**
     - Click on one of 4 options
     - Wait for response (1-2 seconds)
     - Expected: "Correct!" or "Wrong" message
     - Log: Answer submitted, was_correct, time_taken
   - **Check Answer Feedback**
     - Verify theta update displayed (if shown)
     - Verify difficulty adjusted for next question (should vary ±1)
4. **Session Complete**
   - After 10 questions, session ends automatically
   - Verify statistics shown:
     - Questions answered: 10
     - Correct: [count]
     - Accuracy: [percentage]
   - Expected theta changes:
     - Novice_Reader: θ -2.0 → -1.5 to -0.5 (improvement)
     - Geo_Expert (Geography): θ 2.0 → 2.1-2.3 (stays high)
     - Geo_Expert (History): θ -2.0 → -1.5 to -1.0 (improves from low)
     - Balanced: θ 0.0 → slight ±0.3 change (stable)

#### Step 5: Challenge Room (For Challenger Profile)
1. Navigate to `/rooms/challenge`
2. **Start Match**
   - Current rank shown (Bronze)
   - Difficulty range displayed
   - Click "Start Match"
3. **Answer 3-5 Questions**
   - Verify 2 options (Bronze level)
   - Log each answer
4. **Attempt Rank Up**
   - Should show "Skip Attack" button (if 3 attempts available)
   - Click "Skip Attack" or answer final questions
5. **Monitor Progression**
   - Expected: Rank change to Silver (4 options)
   - ELO rating should increase with wins

---

## Monitoring & Logging

### Real-Time Log File Monitoring

```bash
# Monitor backend logs in real-time
tail -f backend/logs/test_session_*.json

# Or: Check all logs
ls -lah backend/logs/

# Or: Export and analyze
cat backend/logs/test_*.json | jq '.' | grep -A5 "theta_update"
```

### Log Entry Examples

**Session Start**:
```json
{
  "timestamp": "2026-04-02T00:45:30.123Z",
  "event_type": "session_start",
  "category": "session",
  "user_id": "dfead852-5c1c-4396-8536-ba6ebcfc312d",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "data": {
    "topic": "geography",
    "initial_theta": -2.0
  }
}
```

**Question Shown**:
```json
{
  "timestamp": "2026-04-02T00:45:45.456Z",
  "event_type": "question_shown",
  "category": "session",
  "data": {
    "question_id": "q123...",
    "user_theta": -1.95,
    "question_beta": -0.5,
    "expected_p_correct": 0.62
  }
}
```

**Theta Update**:
```json
{
  "timestamp": "2026-04-02T00:46:00.789Z",
  "event_type": "theta_update",
  "category": "irt",
  "data": {
    "old_theta": -1.95,
    "new_theta": -1.65,
    "theta_change": 0.30,
    "p_correct": 0.65,
    "learning_rate": 0.3
  }
}
```

---

## Database Verification

### Check User Concept Theta Changes

```sql
-- View all concepts for a test user
SELECT c.name, uc.theta, uc.response_count, uc.mastery_level
FROM user_concept_theta uc
JOIN concepts c ON uc.concept_id = c.id
JOIN users u ON uc.user_id = u.id
WHERE u.username = 'novice_reader_1775089851'
ORDER BY uc.last_updated DESC;
```

### Check All User Responses

```sql
-- View all responses for a test user
SELECT question_id, topic, difficulty_sent, answered_correct, time_taken
FROM user_responses
WHERE user_id = (SELECT id FROM users WHERE username = 'novice_reader_1775089851')
ORDER BY created_at DESC
LIMIT 20;
```

### Check ELO Changes (Challenge Room)

```sql
-- View user ELO for challenge tracking
SELECT username, elo_global, last_login
FROM users
WHERE username IN (
  'novice_reader_1775089851',
  'geo_expert_1775089851',
  'hist_expert_1775089851',
  'balanced_1775089851',
  'challenger_1775089851'
);
```

---

## Expected Outcomes

### Classic Room Behavior

| Profile | Expected Accuracy | Theta Trend | Learning Pattern |
|---------|------------------|-------------|------------------|
| Novice_Reader | 30-50% | ↑ Rapid increase | Fast learner (α=0.3) |
| Geo_Expert (Geo) | 70%+ | ↑ Slight increase | Skilled performer |
| Geo_Expert (Hist) | 30-40% | ↑ Increase | Learning new domain |
| Balanced | 60-75% | → Stable | Optimal ZPD |
| Challenger | 60-75% | → Stable | Rank progression |

### IRT System Validation

- ✅ Questions in ZPD range selected (60-75% success)
- ✅ Difficulty adjusts after each answer (±1)
- ✅ Theta updates by ~0.3 per answer
- ✅ Learning rate applied correctly (LEARN_RATE = 0.3)
- ✅ Theta clamped to [-3, 3] range

### Cache System Validation

- ✅ Session cache created with 1-hour TTL
- ✅ Cache hit rate increases over time (expected 30-50%)
- ✅ Difficulty computations fast (<50ms)
- ✅ No cache corruption detected

---

## Data Collection Summary

After completing all profiles through classical room testing:

**Expected Logs Generated**:
- 50+ session events (10 questions × 5 profiles)
- 50+ theta updates
- 50+ difficulty selections
- 5 session completion events

**Expected Database Changes**:
- 50+ entries in `user_responses`
- 10-15 entries in `user_concept_theta` (updated with new theta, response_count)
- Mastery levels may change for some concepts
- Timestamp updates on all interactions

---

## Testing Checklist

- [ ] All 5 test profiles created successfully
- [ ] Backend logs directory created
- [ ] Can login with each profile
- [ ] Dashboard displays correctly
- [ ] Profile page shows concept data
- [ ] Can start classic room session
- [ ] Questions load and display correctly
- [ ] Can submit answers
- [ ] Theta changes logged
- [ ] Session completes after 10 questions
- [ ] Difficulty adjusts per question
- [ ] Challenge room starts for Challenger profile
- [ ] Rank progression working
- [ ] Logs exported to JSON files
- [ ] Database queries verify state changes
- [ ] Test summary report generated

---

## Quick Start Commands

```bash
# 1. Create test users
python backend/scripts/test_user_profiles.py

# 2. Start backend
python backend/main.py

# 3. Start frontend (new terminal)
npm run dev

# 4. Run comprehensive test
# - Open http://localhost:5173
# - Login with test credentials
# - Follow Phase 3 testing procedure above

# 5. Monitor logs
tail -f backend/logs/test_session_*.json

# 6. Export and analyze logs
python -c "
import json
with open('backend/logs/test_profiles_created_20260402_003052.json') as f:
    logs = json.load(f)
    print(f'Total events: {len(logs)}')
    for log in logs:
        print(f' - {log[\"event_type\"]}: {log[\"data\"].get(\"profile\")}')"
```

---

## Performance Baselines (Reference)

- Page load time: <2 seconds
- API response time: <500ms
- Question creation (LLM): 1-2 seconds
- Database query: <100ms
- Cache hit retrieval: <50ms

---

## Next Steps After Testing

1. **Export and Analyze Logs**
   - All logs in `backend/logs/` directory
   - Analyze with Python/JSON tools

2. **Generate Test Report**
   - Compile findings into `TEST_RESULTS.md`
   - Include: Pass/fail rates, performance metrics, issues found

3. **Production Readiness Decision**
   - If all tests pass: Ready for deployment
   - If issues found: Document and prioritize fixes

---

**Status**: Logging infrastructure ready for testing
**Test Users**: 5 profiles created
**Next Action**: Start comprehensive page testing (Phase 3)

Good luck with testing! 🚀
