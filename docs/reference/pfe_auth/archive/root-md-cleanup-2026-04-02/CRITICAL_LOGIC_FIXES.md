# Critical Logic Issues & Improvement Plan

**Date**: April 2, 2026
**Status**: 8 Issues Identified, Fixes Prioritized
**Blocking Issues**: 5 (MUST fix before production)

---

## 🔴 CRITICAL BLOCKING ISSUES

### ISSUE 1.1: Silent OTP Failure When Redis Offline
**Severity**: CRITICAL
**File**: `backend/auth/services/auth_service.py:92-107`
**Problem**: Returns success message even when OTP not created (Redis down)
**Impact**: Users can't reset passwords when Redis unavailable

**Current Code**:
```python
if redis is not None and user is not None and bool(user.password_hash):
    code = await create_otp(redis, email, OTP_PURPOSE_PASSWORD_RESET)
    await send_email(email, "AdaptIQ — Password Reset Code", html)

return {"message": "If an account exists with this email, a reset code has been sent."}
```

**Fix** (ADD ERROR CHECK):
```python
if user is None:
    return {"message": "If an account exists with this email, a reset code has been sent."}

if not bool(user.password_hash):
    return {"message": "Account has no password set."}

if redis is None:  # ← ADD CRITICAL CHECK
    raise HTTPException(
        status_code=503,
        detail="Password reset temporarily unavailable - Redis service down"
    )

code = await create_otp(redis, email, OTP_PURPOSE_PASSWORD_RESET)
await send_email(email, "AdaptIQ — Password Reset Code", html)
return {"message": "Reset code sent to email."}
```

---

### ISSUE 2.1: V1/V2 Difficulty Algorithm Mismatch
**Severity**: HIGH
**Files**:
- V1 (broken): `backend/routers/classic_room.py:389-392`
- V2 (correct): `backend/routers/classic_room.py:248-260`
**Problem**: Two incompatible difficulty selection algorithms
**Impact**: Users get wrong difficulty progression depending on endpoint

**Fix**: REMOVE V1 endpoints, enforce V2-only
V1 endpoints to DELETE:
- Line 65: `POST /questions` (legacy question generation)
- Line 303: `POST /hints` (legacy hints)
- Line 334: `POST /answers` (legacy answer submission)

Or rewrite V1 to use V2 logic:
```python
# Use V2 logic from classic_service.py:248-260
next_difficulty = await ConsultIRT.compute_next_difficulty_for_topic(
    db=db,
    user_id=user_id,
    topic=topic,
    answered_correct=body.answered_correct,
)
```

---

### ISSUE 4.1: Missing last_updated on Concept Theta
**Severity**: MEDIUM → HIGH (blocking recency tracking)
**File**: `backend/database/concept_irt.py:89-102`
**Problem**: Never updates last_updated timestamp when theta changes
**Impact**: Concept recency bonus broken, wrong concepts selected

**Current Code**:
```python
stmt = (
    sqlalchemy_update(UserConceptTheta)
    .where((UserConceptTheta.user_id == user_id) & ...)
    .values(
        theta=new_theta,
        theta_variance=new_variance,
        response_count=UserConceptTheta.response_count + 1,
        # ← MISSING last_updated
    )
)
```

**Fix** (ADD ONE LINE):
```python
from datetime import datetime, timezone

def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

stmt = (
    sqlalchemy_update(UserConceptTheta)
    .where((UserConceptTheta.user_id == user_id) & ...)
    .values(
        theta=new_theta,
        theta_variance=new_variance,
        response_count=UserConceptTheta.response_count + 1,
        last_updated=utc_now(),  # ← ADD THIS
    )
)
```

---

### ISSUE 4.2: Idempotency Cache Doesn't Include Session ID
**Severity**: MEDIUM → HIGH (data corruption)
**File**: `backend/routers/classic_room.py:347-363`
**Problem**: Same answer in different sessions returns old session's result
**Impact**: Session statistics corrupted, wrong difficulty progression

**Current Code**:
```python
answer_hash = hashlib.sha256(
    f"{str(body.user_id)}{str(body.question_id)}{body.selected_answer}".encode()
).hexdigest()
# ← NO session_id in hash!
```

**Fix**:
```python
answer_hash = hashlib.sha256(
    f"{str(body.user_id)}{str(body.session_id)}{str(body.question_id)}{body.selected_answer}".encode()
).hexdigest()
# ← ADD session_id to prevent cross-session collisions
```

Also update is_submission_duplicate call:
```python
cached_result = await session_service.is_submission_duplicate(
    str(body.user_id), str(body.session_id), str(body.question_id), answer_hash
)
```

---

### ISSUE 8.1: V1 /answers Endpoint Missing Session Ownership Check
**Severity**: HIGH (data corruption)
**File**: `backend/routers/classic_room.py:370-380`
**Problem**: No validation that session belongs to user
**Impact**: User A can submit answers to User B's session

**Current Code**:
```python
if body.user_id != current_user.id:
    raise HTTPException(status_code=403, detail="user_id does not match authenticated user")

# ← No check that session_id belongs to this user!
```

**Fix** (ADD SESSION OWNERSHIP CHECK):
```python
if body.user_id != current_user.id:
    raise HTTPException(status_code=403, detail="user_id does not match authenticated user")

# NEW: Verify session ownership
session_data = await session_service.get_session(body.session_id)
if not session_data:
    raise HTTPException(status_code=404, detail="Session not found")
if session_data.get("user_id") != str(current_user.id):
    raise HTTPException(status_code=403, detail="Session does not belong to you")
```

---

## 🟡 HIGH PRIORITY IMPROVEMENTS

### ISSUE 1.2: DEV_BYPASS_AUTH Production Safety
**Severity**: HIGH (security)
**File**: `backend/config.py:123-149`
**Problem**: No check to prevent DEV_BYPASS_AUTH in production
**Fix**:
```python
def validate_security_config() -> None:
    # ... existing checks ...

    # ADD: Check DEV_BYPASS_AUTH only in development
    if DEV_BYPASS_AUTH and ENVIRONMENT == "production":
        raise ValueError(
            "DEV_BYPASS_AUTH cannot be enabled in production! "
            "This completely bypasses authentication."
        )
```

---

### ISSUE 2.2: Question Beta Calibration Precision Loss
**Severity**: MEDIUM (long-term)
**File**: `backend/database/crud.py:189-214`
**Problem**: Converts continuous IRT beta to integer difficulty, loses precision
**Fix**: Store both difficulty level (1-5) AND beta (float) separately
```python
# Schema change needed:
# ALTER TABLE question_bank
#   ADD COLUMN difficulty_beta FLOAT DEFAULT 0.0;

# Then in update:
new_beta = update_beta(beta_irt, theta, answered_correct)
await db.execute(
    update(QuestionBank)
    .where(QuestionBank.id == uuid.UUID(question_id))
    .values(
        difficulty_irt=new_beta,              # Store continuous value
        difficulty_beta=new_beta,              # Also store for calculations
    )
)
```

---

### ISSUE 3.1: Session Lock Timeout Deadlock Risk
**Severity**: MEDIUM (concurrent)
**File**: `backend/services/session.py:276-314`
**Problem**: Lock TTL (60s) > timeout (30s) = potential deadlock
**Fix**:
```python
LOCK_TIMEOUT = 30      # seconds to wait
LOCK_TTL = 10          # ← REDUCE from 60s to 10s (should never hold lock >5s)

# Better: Use Lua script for atomic lock + operation
# Or: Replace lock_key polling with Redis WATCH transaction
```

---

### ISSUE 3.2: In-Memory Session Fallback Memory Leak
**Severity**: MEDIUM (ops)
**File**: `backend/services/session.py:24`
**Problem**: Global dict accumulates sessions indefinitely, no TTL
**Fix**: Add TTL tracking to in-memory store
```python
import time

_memory_store: dict[str, tuple[str, float]] = {}  # {key: (data_json, expires_at)}

async def get_session(self, session_id: str) -> Optional[dict]:
    key = f"session:{session_id}"
    try:
        if self._redis:
            raw = await self._redis.get(key)
        else:
            if key in _memory_store:
                data_json, expires_at = _memory_store[key]
                if time.time() > expires_at:
                    del _memory_store[key]  # ← Purge expired
                    return None
                return json.loads(data_json)
            return None
        return json.loads(raw) if raw else None
    except Exception as e:
        logger.warning(f"Session get failed: {e}")
        return None

async def set_session(self, session_id: str, data: dict) -> bool:
    key = f"session:{session_id}"
    try:
        serialized = json.dumps(data)
        if self._redis:
            await self._redis.setex(key, self._ttl, serialized)
        else:
            expires_at = time.time() + self._ttl
            _memory_store[key] = (serialized, expires_at)
        return True
    except Exception as e:
        logger.warning(f"Session set failed: {e}")
        return False
```

---

### ISSUE 5.1: Unlimited Skip Reset Problem
**Severity**: MEDIUM (balance)
**File**: `backend/routers/challenge.py:507-534`
**Problem**: Skip attempts reset to 3 on every win, allowing infinite skips
**Fix**:
```python
# Track skip usage with 24-hour cooldown
if match.result == "win":
    if match.is_skip_attempt:
        # Don't just reset to 3!
        # Check if 24 hours have passed since last reset
        last_reset = user_rank.last_skip_reset  # ← Add field to schema
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        if last_reset is None or (now - last_reset).days >= 1:
            user_rank.skip_attempts_remaining = 3
            user_rank.last_skip_reset = now
        # else: don't reset, keep count
else:
    if match.is_skip_attempt:
        user_rank.skip_attempts_remaining = max(0, user_rank.skip_attempts_remaining - 1)
```

---

### ISSUE 5.2: Non-Atomic Match Finalization
**Severity**: MEDIUM (race condition)
**File**: `backend/routers/challenge.py:413-428`
**Problem**: Match can be finalized twice if /answer finishes match then /end called
**Fix**:
```python
# Mark match as "incomplete" initially
# Only finalize when explicitly requested

# In /answer endpoint:
if questions_remaining <= 0:
    match.is_complete = True  # ← Add flag
    match.result = "win" if score_so_far >= WIN_THRESHOLD else "loss"
    # Don't recalculate rank, let /end handle it

    await db.commit()

    return ChallengeAnswerResponse(
        message="Match complete",
        next_question=None,
        session_ended=True,
        is_match_complete=True,  # ← Signal to frontend
    )

# In /end endpoint:
if not match.is_complete:
    raise HTTPException(status_code=400, detail="Match not yet complete")

# Now safely recalculate rank/ELO
```

---

### ISSUE 6.1: Token Revocation with Redis Failure
**Severity**: LOW (security)
**File**: `backend/auth/core/security.py:74-99`
**Problem**: Revocations ignored when Redis down
**Fix**: Add configuration option
```python
# In config.py:
TOKEN_REVOCATION_POLICY = os.getenv(
    "TOKEN_REVOCATION_POLICY",
    "graceful"  # "graceful" (allow) or "strict" (deny)
)

# In security.py:
async def is_token_revoked(redis, user_id: str, token_iat: int | None) -> bool:
    if redis is None:
        if TOKEN_REVOCATION_POLICY == "strict":
            logger.error("redis_unavailable_denying_all_tokens")
            return True  # ← Deny when strict + Redis down
        else:
            logger.warning("redis_unavailable_allowing_tokens")
            return False  # ← Allow when graceful (default for learning platform)

    # ...rest of logic
```

---

## 📊 IMPACT ASSESSMENT

| Issue | Impact | Users Affected | Data Loss | Blocking |
|-------|--------|---|---|---|
| 1.1 | Can't reset password | 100% when Redis down | Account locked | YES |
| 2.1 | Wrong difficulty | 100% V1 users | Learning progress | YES |
| 4.1 | Wrong concept selection | 100% | Concept tracking | YES |
| 4.2 | Session corruption | Multi-session users | Stats corrupted | YES |
| 8.1 | Cross-user access | Multi-user systems | Data cross-contamination | YES|
| 1.2 | Auth bypass | 0% (dev-only) | All data | INFO |
| 2.2 | Calibration drift | All users (long-term) | Question relevance | LOW |
| 3.1 | Deadlock | <1% (concurrent) | Session timeout | MEDIUM |
| 3.2 | Memory leak | 100% (without Redis) | None | MEDIUM |
| 5.1 | Game abuse | <5% (skilled) | System balance | MEDIUM |
| 5.2 | Rank change twice | <1% (network retry) | Rank inflation | MEDIUM |
| 6.1 | Revocation bypass | <0.1% | Session security | LOW |
| 7.1 | Poor debugging | Ops team | None | LOW |

---

## 🚀 IMPLEMENTATION ROADMAP

### MUST FIX BEFORE TESTING (Today):
1. ✅ Issue 1.1 - Redis check in OTP
2. ✅ Issue 4.1 - Add last_updated to theta updates
3. ✅ Issue 4.2 - Add session_id to idempotency hash
4. ✅ Issue 8.1 - Add session ownership check to V1

### SHOULD FIX BEFORE PRODUCTION (This week):
5. Issue 2.1 - Remove V1 endpoints
6. Issue 1.2 - Add DEV_BYPASS_AUTH production check
7. Issue 2.2 - Split difficulty/beta columns
8. Issue 3.1 - Reduce lock TTL
9. Issue 3.2 - Add TTL to in-memory store
10. Issue 5.1 - Implement skip cooldown
11. Issue 5.2 - Atomic match finalization

### NICE TO HAVE (After launch):
12. Issue 6.1 - Add TOKEN_REVOCATION_POLICY config
13. Issue 7.1 - Better error logging in question selection

---

## ✅ TESTING IMPACT

These issues will cause:
- Multi-user tests to fail (data corruption)
- Session tests to have false positives
- Difficulty progression tests to show inconsistency
- Challenge room tests to show rank duplication

**RECOMMENDATION**: Fix critical issues (1.1, 4.1, 4.2, 8.1) BEFORE comprehensive testing.

---

**Priority**: 🔴 **FIX NOW** | 🟡 **FIX THIS WEEK** | 🟢 **FIX LATER**
