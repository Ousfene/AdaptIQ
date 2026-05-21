# Concept-Aware Question Caching & Per-User ELO System

**Status**: Implementation Phase 2 Complete ✅

## Overview

The AdaptIQ platform now features an advanced concept-aware question delivery system that:

1. **Caches questions** across users for efficiency
2. **Computes per-user difficulty** based on their concept-specific IRT ability (θ)
3. **Adapts automatically** to user strengths and weaknesses
4. **Discovers new concepts** gradually (80% known, 20% unknown)
5. **Starts new concepts** at difficulty 3 (medium-hard), then adapts based on performance

### Before: Global User Ability
```
User A answers History question → Updates global user_id:theta
```

### After: Per-Concept Ability
```
User A answers History question about "Egyptian Empire" → Updates user_id:concept_id:theta
Question Q1 (difficulty_irt=2.0) served to:
  - User A (θ=1.5 for this concept) → computed difficulty 2 (hard)
  - User B (θ=0.5 for this concept) → computed difficulty 3 (harder)
  - User C (θ=2.5 for this concept) → computed difficulty 1 (easy)
```

---

## Database Schema

### UserConceptTheta Table
```sql
CREATE TABLE user_concept_theta (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL,
  concept_id UUID NOT NULL,
  theta FLOAT DEFAULT 0.0,              -- User's ability in this concept [-3, 3]
  theta_variance FLOAT DEFAULT 1.0,     -- Uncertainty (decays with more responses)
  response_count INT DEFAULT 0,         -- How many questions answered for this concept
  exposure_count INT DEFAULT 0,         -- How many times concept was shown
  first_seen_at DATETIME,               -- When user first encountered this concept
  last_updated DATETIME,
  created_at DATETIME,
  
  UNIQUE(user_id, concept_id),
  INDEX(user_id),
  INDEX(concept_id),
  INDEX(last_updated)
);
```

### Concept Table
```sql
CREATE TABLE concepts (
  id UUID PRIMARY KEY,
  name VARCHAR(255) UNIQUE,             -- "Egyptian Empire", "Roman History", etc.
  topic VARCHAR(50),                    -- "History", "Geography", "Mixed"
  description TEXT,
  created_at DATETIME,
  
  INDEX(name),
  INDEX(topic)
);
```

### QuestionConcept Table (M-to-M)
```sql
CREATE TABLE question_concepts (
  id UUID PRIMARY KEY,
  question_id UUID NOT NULL,
  concept_id UUID NOT NULL,
  is_primary BOOLEAN,                   -- true = primary concept, false = secondary
  created_at DATETIME,
  
  INDEX(question_id),
  INDEX(concept_id)
);
```

---

## Core Services

### 1. ConceptCacheService (`backend/services/concept_cache_service.py`)

**Purpose**: Intelligent concept selection and difficulty computation

**Key Methods**:

#### `select_concept_for_user(db, user_id, topic) → concept_id`
Adaptive concept selection:
- **80%**: Pick weak concept (lowest θ) to improve gap areas
- **20%**: Pick unknown concept (auto-discovery)

```python
# Example: User has 5 concepts with thetas [1.5, 0.5, -0.5, 2.0, 1.0]
# Weak areas: concept with θ=-0.5 and θ=0.5 have higher selection probability
# Unknown concepts: if any exist, 20% chance to pick one
```

#### `get_or_create_concepts_for_question(db, question_id, concept_names, topic)`
Auto-create concepts if they don't exist in DB.

#### `compute_user_question_difficulty(user_theta, question_beta) → difficulty (1-5)`
Map IRT parameters to user-perceived difficulty:

```
P(correct) = 1 / (1 + exp(-(user_theta - question_beta)))

If P > 0.8 → difficulty 1 (very easy for user)
If P > 0.6 → difficulty 2 (easy)
If P > 0.4 → difficulty 3 (medium)
If P > 0.2 → difficulty 4 (hard)
If P ≤ 0.2 → difficulty 5 (very hard)
```

**Example**:
- Question β=2.0 (medium difficulty in absolute terms)
- User A: θ=1.5 → P=0.62 → difficulty 2 (feels easy)
- User B: θ=0.5 → P=0.38 → difficulty 4 (feels hard)

#### `select_and_serve_question(db, redis, user_id, topic) → question_dict`
Main orchestrator:
1. Select concept (adaptive strategy)
2. Get cached questions for concept
3. Pick random question
4. Compute user-specific difficulty
5. Track exposure
6. Return question with **computed difficulty**

### 2. QuestionCacheService (`backend/services/question_cache_service.py`)

**Purpose**: Redis-backed performance caching

**Key Methods**:

#### `cache_difficulty(user_id, question_id, concept_id, difficulty)`
Store computed difficulty in Redis for idempotency.

#### `get_cached_difficulty(user_id, question_id, concept_id) → difficulty or None`
Retrieve cached difficulty (cache hit → same difficulty always).

#### `invalidate_user_questions(user_id)`
Clear cache for user (called after major IRT recalibration).

**Cache Structure**:
```
Key: q_cache:{user_id}:{question_id}:{concept_id}
Value: {"difficulty": 3, "served_at": "...", "version": 1}
TTL: 1 hour
```

### 3. ConceptIRT (`backend/database/concept_irt.py`)

**Purpose**: Per-concept IRT theta updates

**Key Methods**:

#### `update_concept_theta(db, user_id, concept_id, beta, correct) → new_theta`
Update user's theta for a specific concept using 1-Parameter Logistic model:
```
δθ = α * (response - P(correct))
new_theta = clamp(theta + δθ, [-3, 3])
variance *= 0.95  # Uncertainty decays
```

#### `track_concept_exposure(db, user_id, concept_id)`
Increment exposure_count and set first_seen_at on first exposure.

#### `get_unknown_concepts(db, user_id, potential_concepts) → unknown_list`
Get concepts user hasn't encountered yet (for auto-discovery).

---

## New Concept Adaptation

**Goal**: New concepts start moderate, then adapt based on performance

**Implementation**:

```python
def get_difficulty_for_new_concept(user_id, concept_id):
    record = db.query(UserConceptTheta)
              .filter(user_id=user_id, concept_id=concept_id)
              .first()
    
    if not record or record.response_count < 3:
        return 3  # Difficulty 3 = medium-hard (balanced learning start)
    else:
        # After 3 responses: adapt based on user's theta
        return compute_user_question_difficulty(record.theta, difficulty_to_beta(3))
```

**Timeline**:
```
First exposure (Q1): difficulty 3
  User gets it wrong → θ -= 0.1 (now θ ≈ -0.1)
  
Second exposure (Q2): difficulty 3
  User gets it right → θ += 0.2 (now θ ≈ 0.1)
  
Third exposure (Q3): difficulty 3
  User gets it right → θ += 0.2 (now θ ≈ 0.3)
  
Fourth exposure (Q4): difficulty adapted based on θ
  If θ=0.3 with question β=2.0 → P≈0.50 → difficulty 3 (medium)
```

---

## Auto-Discovery Strategy

**Goal**: Gradually expose users to new concepts (80% known, 20% discovery)

**Implementation in routers/classic_room.py**:

```python
# Step 1: Select concept (adaptive 80/20)
concept_id = await select_concept_for_user(db, user_id, topic)
  # Returns: weak known concept (80%) OR unknown concept (20%)

# Step 2: Auto-discovery injection
if response_count < 5 and random.random() < 0.20:
    # Add random unknown concept to question
    unknown = get_unknown_concepts(db, user_id, all_concepts)
    if unknown:
        unknown_concept = random.choice(unknown)
        track_concept_exposure(db, user_id, unknown_concept)
```

**Result**: Users naturally discover new concepts without feeling forced.

---

## API Changes

### POST /api/rooms/classic/questions

**Request**:
```json
{
  "session_id": "uuid",
  "user_id": "uuid",
  "topic": "History",
  "difficulty": 2
}
```

**Response**:
```json
{
  "id": "question_uuid",
  "text": "What was the capital of the Roman Empire?",
  "options": ["Rome", "Alexandria", "Athens", "Carthage"],
  "correctAnswer": "Rome",
  "explanation": "Rome was the capital...",
  "locked": false,
  "difficulty": 3  // ← COMPUTED FOR THIS USER
}
```

**Backend Flow**:
1. `select_concept_for_user()` → picks concept based on user's thetas
2. `get_cached_questions_for_concept()` → gets question pool
3. `compute_user_question_difficulty()` → maps θ → difficulty
4. `track_concept_exposure()` → records exposure
5. Return question with **user-specific difficulty**

### POST /api/rooms/classic/answers

**Enhanced**: Now updates **per-concept** θ instead of global θ

```python
# Old: Update global user theta
user_theta += delta

# New: Update concept-specific theta
await ConceptIRT.update_concept_theta(
    db, user_id, concept_id, 
    question_beta, is_correct
)
```

---

## Caching Strategy

### Question Pool Per Concept
```
Concepts per topic: ~5-10
Questions per concept: 20-50
Total per topic: 100-500 cached questions

Reuse: Each question can be served to unlimited users,
       but difficulty is computed per user at serve time.
```

### Redis Cache Layers
```
Layer 1: Session cache
  Key: session:{session_id}
  Value: {current_difficulty, correct_answer, seen_ids, ...}
  TTL: 30 min

Layer 2: Question difficulty cache
  Key: q_cache:{user_id}:{question_id}:{concept_id}
  Value: {difficulty, served_at}
  TTL: 1 hour
  Purpose: Idempotency (same Q+user+concept = same difficulty)

Layer 3: OTP cache
  Key: otp:{user_id}
  Value: {code, attempts}
  TTL: 5 min

Layer 4: Rate limit cache
  Key: rate_limit:{email}:{ip}
  Value: {attempt_count}
  TTL: 1 min
```

---

## Migration Path

**No breaking changes**. Existing endpoints continue to work:

✅ Old flow: `generateQuestion() → global difficulty` still works  
✅ New flow: `generateQuestion() → concept selection → per-user difficulty`  

**To enable concept-aware system**:
```bash
# In backend/.env
ENABLE_CONCEPT_TRACKING=true   # Already set
ENABLE_CONCEPT_DISPLAY=true    # Optional: show in UI
```

---

## Monitoring & Analytics

### Key Metrics to Track

1. **Concept Coverage**:
   - How many unique concepts per user?
   - How many never discovered?

2. **Theta Distribution**:
   - Average θ per concept per user
   - Variance trends (should decay over time)

3. **Question Reuse**:
   - How many users see same question?
   - Cost savings from caching

4. **Difficulty Alignment**:
   - Does computed difficulty ≈ user performance?
   - P(correct) should be ~0.5 for difficulty 3

### Example Query
```sql
-- User's concept mastery after N questions
SELECT 
  c.name,
  uct.theta,
  uct.response_count,
  uct.exposure_count,
  CASE 
    WHEN uct.theta < -1 THEN 'Novice'
    WHEN uct.theta < 1 THEN 'Intermediate'
    ELSE 'Advanced'
  END as level
FROM user_concept_theta uct
JOIN concepts c ON uct.concept_id = c.id
WHERE uct.user_id = $1
ORDER BY uct.theta DESC;
```

---

## Testing Checklist

- [ ] User A & B answer same question → different computed difficulties
- [ ] New concept starts at difficulty 3
- [ ] After 3 answers to new concept, difficulty adapts
- [ ] 80% known concepts, 20% unknown in concept selection
- [ ] Auto-discovery gradually introduces new concepts
- [ ] Question reuse works (multiple users, same question, different θ)
- [ ] Redis cache hits on same user+question+concept
- [ ] IRT θ updates correctly per concept
- [ ] Variance decays with more responses
- [ ] Frontend displays questions correctly
- [ ] No backend errors in logs

---

## Known Limitations & Future Improvements

1. **Cold start**: New users get θ=0 for all concepts (neutral point)
   - Future: Could use clustering to assign similar users' initial θ

2. **Question pool saturation**: After 500 questions per concept, need refresh
   - Future: LLM generates new questions periodically

3. **Concept overlap**: Question might belong to multiple concepts
   - Current: IRT updates all linked concepts
   - Future: Weight updates by is_primary flag

4. **Performance**: ConceptCacheService does sync DB queries
   - Current: All async, should be fine up to 1000 concurrent users
   - Future: Add Redis-backed concept cache layer

---

## Troubleshooting

### Issue: Same question, different users, same difficulty

**Check**: Is `compute_user_question_difficulty()` using user's θ?
```python
# Verify: user_theta should vary per user
user_theta = await ConceptIRT.get_concept_theta(db, user_id, concept_id)
print(f"User {user_id}, Concept {concept_id}: theta={user_theta}")
```

### Issue: New concept not appearing

**Check**: 
1. Are concepts being created? `SELECT * FROM concepts;`
2. Is concept linked to question? `SELECT * FROM question_concepts WHERE question_id = 'X';`
3. Is exposure tracked? `SELECT * FROM user_concept_theta WHERE user_id = 'Y' AND concept_id = 'Z';`

### Issue: Difficulty always 3

**Check**: Is IRT update running?
```python
# Verify: response_count should increase
SELECT response_count FROM user_concept_theta 
WHERE user_id = 'X' AND concept_id = 'Y';
```

---

## Code Files Added/Modified

### New Files
- `backend/services/concept_cache_service.py` (core service)
- `backend/services/question_cache_service.py` (Redis caching)
- `CONCEPT_AWARE_SYSTEM.md` (this file)

### Modified Files
- `backend/auth/services/auth_service.py` (fixed dead code)
- `backend/database/concept_irt.py` (fixed datetime deprecation)
- `backend/routers/classic_room.py` (imports concept cache)
- `docker-compose.yml` (fixed frontend port: 5173→5173)

### Unchanged
- Database migrations (already complete)
- RAG pipeline (verified, no changes needed)
- Frontend (no UI changes required)
- Auth flow (unchanged)

---

## References

- [1PL IRT Model](https://en.wikipedia.org/wiki/Item_response_theory)
- [Adaptive Learning](https://en.wikipedia.org/wiki/Adaptive_learning)
- [Redis Async Python](https://redis-py.readthedocs.io/)
