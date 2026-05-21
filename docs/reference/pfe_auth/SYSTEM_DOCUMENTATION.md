# 🎓 AdaptIQ - Complete System Documentation

## Table of Contents
1. [System Overview](#system-overview)
2. [Database Schema](#database-schema)
3. [Authentication System](#authentication-system)
4. [IRT Adaptive Engine](#irt-adaptive-engine)
5. [Classic Room (Training Mode)](#classic-room-training-mode)
6. [Challenge Room (Competitive Mode)](#challenge-room-competitive-mode)
7. [RAG Pipeline & Question Generation](#rag-pipeline--question-generation)
8. [Frontend Architecture](#frontend-architecture)
9. [API Reference](#api-reference)
10. [Constants & Configuration](#constants--configuration)

---

## System Overview

AdaptIQ is an **adaptive learning quiz platform** that uses **Item Response Theory (IRT)** to personalize question difficulty at the **concept level** (not just topic level).

### Key Features
- **Concept-Level Tracking**: "Egyptian Empire" vs "Roman Empire" tracked separately
- **Zone of Proximal Development (ZPD)**: Questions where user has 60-75% success chance
- **Spaced Repetition**: Wrong answers queued for review after 7 sessions
- **Dual Modes**: Classic (training) and Challenge (competitive)

### Tech Stack
| Component | Technology |
|-----------|------------|
| Backend | FastAPI (Python 3.12+), SQLAlchemy async |
| Database | PostgreSQL 16 |
| Cache | Redis 7 |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS 4 |
| LLM | Groq API (Llama 3.1-8B-instant) |

---

## Database Schema

### 1. `users` Table
User accounts and global stats.

| Column          | Type         | Description                                   |
| --------------- | ------------ | --------------------------------------------- |
| `id`            | UUID (PK)    | Primary key, auto-generated                   |
| `email`         | VARCHAR(255) | Unique, indexed                               |
| `username`      | VARCHAR(100) | Unique                                        |
| `password_hash` | VARCHAR(255) | bcrypt hash, never plaintext                  |
| `points`        | INTEGER      | Total points earned (default: 0)              |
| `level`         | VARCHAR(30)  | Display level: "Novice", "Intermediate", etc. |
| `elo_global`    | FLOAT        | Challenge Room ELO rating (default: 0.0)      |
| `created_at`    | DATETIME     | Account creation timestamp                    |
| `last_login`    | DATETIME     | Last successful login (nullable)              |
| `is_active`     | BOOLEAN      | Account active status (default: true)         |
| `is_admin`      | BOOLEAN      | Admin privileges (default: false)             |

---

### 2. `concepts` Table
Knowledge domain concepts that questions test.

| Column        | Type         | Description                                   |
| ------------- | ------------ | --------------------------------------------- |
| `id`          | UUID (PK)    | Primary key                                   |
| `name`        | VARCHAR(255) | Unique concept name (e.g., "Egyptian Empire") |
| `topic`       | VARCHAR(50)  | Parent topic: "geography" or "history"        |
| `description` | TEXT         | Brief description of the concept              |
| `created_at`  | DATETIME     | When concept was created                      |

**Example Concepts:**
- Geography: "Amazon River Basin", "Sahara Desert", "Himalayan Range", "Mediterranean Sea"
- History: "Egyptian Empire", "Roman Empire", "Mongol Empire", "Ottoman Empire"

---

### 3. `question_bank` Table
Cached MCQ questions with IRT calibration parameters.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID (PK) | Primary key |
| `question_text` | TEXT | The question text |
| `correct_answer` | TEXT | The correct answer string |
| `options_json` | TEXT | JSON array of all options |
| `explanation` | TEXT | Educational explanation shown after answer |
| `hint` | TEXT | Cached hint (nullable, avoids LLM re-generation) |
| `topic` | VARCHAR(20) | "geography" or "history" |
| `difficulty_irt` | FLOAT | IRT β parameter [-3.0 to +3.0] (default: 2.5) |
| `discrimination` | FLOAT | IRT discrimination (default: 1.0, not used in 1PL) |
| `usage_count` | INTEGER | Times used in sessions (default: 0) |
| `times_seen` | INTEGER | Total times served to users |
| `created_at` | DATETIME | Question creation time |
| `last_served_at` | DATETIME | Last time question was shown |
| `source` | VARCHAR(30) | Origin: "llm", "seed", or "rag" |
| `primary_concept_id` | UUID (FK) | Links to main concept tested |

**Indexes:**
- `ix_question_bank_topic_diff` on (`topic`, `difficulty_irt`)

---

### 4. `question_concepts` Table
Many-to-many link between questions and concepts.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID (PK) | Primary key |
| `question_id` | UUID (FK) | References `question_bank.id` |
| `concept_id` | UUID (FK) | References `concepts.id` |
| `is_primary` | BOOLEAN | True if this is the main concept tested |
| `created_at` | DATETIME | Link creation time |

---

### 5. `user_concept_theta` Table
**Per-user, per-concept IRT ability tracking** - the heart of adaptive learning.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID (PK) | Primary key |
| `user_id` | UUID (FK) | References `users.id` |
| `concept_id` | UUID (FK) | References `concepts.id` |
| `theta` | FLOAT | IRT ability estimate [-3.0 to +3.0] (default: 0.0) |
| `theta_variance` | FLOAT | Uncertainty in estimate (default: 1.0, decays with data) |
| `response_count` | INTEGER | Number of answers that calibrated this theta |
| `last_updated` | DATETIME | Last theta update time |
| `created_at` | DATETIME | Record creation time |
| `first_seen_at` | DATETIME | When user first saw this concept |
| `exposure_count` | INTEGER | How many times concept was shown |
| `mastery_level` | VARCHAR(20) | "BEGINNER", "LEARNING", "PROFICIENT", "ADVANCED" |
| `last_played_at` | DATETIME | Last time user practiced this concept |
| `updated_at` | DATETIME | Last record update |
| `concept_state` | VARCHAR(20) | "EXPLORING", "LEARNING", "MASTERED" |

**Indexes:**
- `ix_user_concept_theta_user` on (`user_id`)
- `ix_user_concept_theta_concept` on (`concept_id`)
- `ix_user_concept_theta_updated` on (`last_updated`)

---

### 6. `user_concept_repeat_queue` Table
Spaced repetition queue for concepts user got wrong.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID (PK) | Primary key |
| `user_id` | UUID (FK) | References `users.id` |
| `concept_id` | UUID (FK) | References `concepts.id` |
| `question_id` | UUID (FK) | Specific question to repeat |
| `repeat_probability` | FLOAT | Priority weight (default: 0.5) |
| `due_after_session` | INTEGER | Show after N more sessions completed |
| `created_at` | DATETIME | Queue entry creation time |

**Index:** `ix_repeat_queue_user_due` on (`user_id`, `due_after_session`)

---

### 7. `user_responses` Table
**Every answer ever submitted** - drives IRT recalibration.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID (PK) | Primary key |
| `user_id` | UUID (FK) | References `users.id` |
| `session_id` | UUID | The quiz session this belongs to |
| `question_id` | UUID (FK) | References `question_bank.id` |
| `topic` | VARCHAR(20) | "geography" or "history" |
| `difficulty_sent` | INTEGER | Difficulty level shown (1-5) |
| `answered_correct` | BOOLEAN | Whether answer was correct |
| `time_taken` | INTEGER | Seconds to answer |
| `used_hint` | BOOLEAN | Whether hint was used |
| `created_at` | DATETIME | Answer submission time |

**Index:** `ix_user_responses_user_topic` on (`user_id`, `topic`)

---

### 8. `classic_sessions` Table
Classic Room quiz session tracking.

| Column               | Type        | Description                              |
| -------------------- | ----------- | ---------------------------------------- |
| `id`                 | UUID (PK)   | Primary key (session_id)                 |
| `user_id`            | UUID (FK)   | References `users.id`                    |
| `topic`              | VARCHAR(20) | "geography", "history", or "mix"         |
| `questions_answered` | INTEGER     | Count of answered questions (default: 0) |
| `correct_count`      | INTEGER     | Count of correct answers (default: 0)    |
| `created_at`         | DATETIME    | Session start time                       |
| `ended_at`           | DATETIME    | Session end time (nullable)              |

---

### 9. `challenge_ranks` Table
Rank definitions for Challenge Room.

| Column          | Type         | Description                        |
| --------------- | ------------ | ---------------------------------- |
| `id`            | INTEGER (PK) | Rank ID (1=Bronze, 2=Silver, etc.) |
| `name`          | VARCHAR(50)  | Rank name (unique)                 |
| `min_elo`       | FLOAT        | Minimum ELO to reach this rank     |
| `n_options`     | INTEGER      | Number of answer options           |
| `has_timer`     | BOOLEAN      | Whether rank has time limit        |
| `timer_seconds` | INTEGER      | Time limit in seconds (nullable)   |

**Rank Configuration:**

| Rank ID | Name     | Options | Timer | Question β Range           |
| ------- | -------- | ------- | ----- | -------------------------- |
| 1       | Bronze   | 2       | None  | [-2.0, -1.0] (Easy)        |
| 2       | Silver   | 4       | None  | [-1.0, +0.5] (Medium-Easy) |
| 3       | Gold     | 4       | None  | [0.0, +1.0] (Medium)       |
| 4       | Platinum | 4       | 30s   | [+0.5, +1.5] (Medium-Hard) |
| 5       | Diamond  | 4       | 20s   | [+1.0, +2.5] (Hard)        |

**Rank Differences Explained:**

| Feature            | Bronze       | Silver       | Gold        | Platinum     | Diamond      |
| ------------------ | ------------ | ------------ | ----------- | ------------ | ------------ |
| **Options**        | 2 (binary)   | 4            | 4           | 4            | 4            |
| **Timer**          | ❌ No         | ❌ No         | ❌ No        | ⏱️ 30 sec    | ⏱️ 20 sec    |
| **Difficulty**     | Very Easy    | Easy         | Medium      | Hard         | Very Hard    |
| **Question IRT β** | -2.0 to -1.0 | -1.0 to +0.5 | 0.0 to +1.0 | +0.5 to +1.5 | +1.0 to +2.5 |
| **Win Threshold**  | 70%          | 70%          | 70%         | 70%          | 70%          |

---

### 10. `user_challenge_rank` Table
User's current rank and challenge stats.

| Column | Type | Description |
|--------|------|-------------|
| `user_id` | UUID (PK, FK) | References `users.id` |
| `current_rank_id` | INTEGER (FK) | Current rank (default: 1 = Bronze) |
| `wins` | INTEGER | Total match wins (default: 0) |
| `losses` | INTEGER | Total match losses (default: 0) |
| `skip_attempts_remaining` | INTEGER | Skip attempts left (default: 3) |
| `last_skip_at` | DATETIME | Last skip attempt time (for 24h cooldown) |

---

### 11. `challenge_matches` Table
Individual challenge match records.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID (PK) | Match ID |
| `user_id` | UUID (FK) | References `users.id` |
| `rank_id` | INTEGER (FK) | Rank played |
| `questions_answered` | INTEGER | Questions completed |
| `score` | FLOAT | Final score (0.0 to 1.0) |
| `time_taken` | INTEGER | Total seconds |
| `created_at` | DATETIME | Match start time |
| `result` | VARCHAR(20) | "win", "loss", "draw", "incomplete" |
| `is_skip_attempt` | BOOLEAN | Whether this was a skip attempt |

---

## Authentication System

### JWT Token Structure
```json
{
  "sub": "550e8400-e29b-41d4-a716-446655440000",  // User UUID
  "exp": 1712138400,                               // Expiry (60 min from issue)
  "iat": 1712134800,                               // Issued at
  "jti": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"   // Unique token ID
}
```

### Password Requirements
- Minimum 8 characters
- At least 1 lowercase letter
- At least 1 uppercase letter
- At least 1 digit
- At least 1 special character (`!@#$%^&*()-_=+[]{};:,.?/`)

### Token Revocation
When user logs out or resets password:
1. Redis key set: `auth:revoked_after:{user_id}` = timestamp
2. On each request, token's `iat` compared to revocation timestamp
3. If `iat < revoked_after`, token is rejected

### OTP for Password Reset
- 6-digit code, cryptographically secure
- Stored in Redis as SHA256 hash
- 10-minute expiry
- Max 5 verification attempts
- Redis keys: `otp:password_reset:{email}`, `otp_attempts:password_reset:{email}`

---

## IRT Adaptive Engine

### The Core Formula (1-Parameter Logistic Model)

```
P(correct | θ, β) = 1 / (1 + exp(-(θ - β)))
```

| Symbol | Name | Range | Description |
|--------|------|-------|-------------|
| θ (theta) | User Ability | [-3.0, +3.0] | Higher = more skilled |
| β (beta) | Question Difficulty | [-3.0, +3.0] | Higher = harder |
| P | Probability | [0, 1] | Chance of correct answer |

### Theta Update After Each Answer

```python
def update_theta(theta: float, beta: float, correct: bool) -> float:
    p = 1 / (1 + exp(-(theta - beta)))     # Predicted probability
    gradient = (1 if correct else 0) - p    # Observed - predicted
    new_theta = theta + 0.3 * gradient      # LEARN_RATE = 0.3
    return clamp(new_theta, -3.0, +3.0)
```

**Example:**
- User θ = 0.5, Question β = 1.0
- P(correct) = 1/(1+exp(0.5)) ≈ 0.38 (38%)
- User answers **correctly**: gradient = 1 - 0.38 = 0.62
- New θ = 0.5 + 0.3 × 0.62 = **0.69** ↑

### Zone of Proximal Development (ZPD)

Target questions where user has **60-75% chance of success**.

```python
def target_beta_range(theta: float) -> tuple[float, float]:
    # For P=0.75 (easier): β = θ + ln(0.333) ≈ θ - 1.10
    beta_low = theta + log(1/0.75 - 1)
    
    # For P=0.60 (harder): β = θ + ln(0.667) ≈ θ - 0.41
    beta_high = theta + log(1/0.60 - 1)
    
    return (beta_low, beta_high)
```

**Example ZPD Ranges:**

| User θ | β Range (ZPD) | Target Difficulty |
|--------|---------------|-------------------|
| -2.0 | [-3.0, -2.4] | Very Easy (1) |
| -1.0 | [-2.1, -1.4] | Easy (1-2) |
| 0.0 | [-1.1, -0.4] | Medium (2-3) |
| +1.0 | [-0.1, +0.6] | Medium-Hard (3-4) |
| +2.0 | [+0.9, +1.6] | Hard (4-5) |

### Difficulty Mapping (β → 1-5 Scale)

```python
BETA_BREAKPOINTS = [-1.5, -0.5, 0.5, 1.5]

# β < -1.5  → Difficulty 1 (Very Easy)
# β < -0.5  → Difficulty 2 (Easy)
# β < +0.5  → Difficulty 3 (Medium)
# β < +1.5  → Difficulty 4 (Hard)
# β >= +1.5 → Difficulty 5 (Very Hard)
```

### Warm-Up Period

Before trusting theta estimates, user needs at least 5 responses per concept.

```python
MIN_RESPONSES_FOR_CONFIDENCE = 5

if response_count < 5:
    # Cold start: use wide difficulty range
    beta_range = (-2.0, +2.0)
else:
    # Warm mode: use precise ZPD
    beta_range = target_beta_range(theta)
```

---

## Classic Room (Training Mode)

### Session Flow

```
1. User selects topic (Geography / History / Mix)
2. Backend selects 5 concepts for session (scoring algorithm)
3. System selects 10 questions based on IRT ZPD
4. For each question:
   - Timer: 30 seconds
   - Hints available (-3 points)
   - Correct answer revealed after submission
   - Theta updated per concept
   - Spaced repetition check
5. Summary with score & accuracy
```

### Concept Selection Algorithm

```python
# If user has < 5 responses for concept → Cold Start (random moderate)
# If user has ≥ 5 responses → Score-based selection:

score = (
    0.40 * mastery_gap +    # Room to grow: (3.0 - θ) / 6.0
    0.30 * recency_bonus +  # Days since practice / 14 (capped at 1.0)
    0.20 * repeat_due +     # 1.0 if in repeat queue, else 0.0
    0.10 * zpd_fit          # Questions available in ZPD (0.5 default)
)
```

### Spaced Repetition Logic

```python
REPEAT_DUE_SESSIONS = 7                    # Sessions until repeat
WRONG_ANSWER_REPEAT_PROBABILITY = 0.25     # 25% chance on wrong
CORRECT_ANSWER_REPEAT_PROBABILITY = 0.01   # 1% chance on correct

if not is_correct and random() < 0.25:
    add_to_repeat_queue(user_id, concept_id, due_after=7)
elif is_correct and random() < 0.01:
    add_to_repeat_queue(user_id, concept_id, due_after=7)
```

### Session Redis State

```python
session_state = {
    "user_id": "uuid-string",
    "topic": "geography",
    "concept_ids": ["uuid1", "uuid2", "uuid3", "uuid4", "uuid5"],
    "theta_snapshot": {
        "uuid1": 0.5,
        "uuid2": -0.3,
        # ...
    },
    "confidence_snapshot": {
        "uuid1": True,   # Has ≥5 responses
        "uuid2": False,  # Cold start
    },
    "questions_asked": ["q-uuid1", "q-uuid2"],
    "current_question_id": "q-uuid3"
}
```

---

## Challenge Room (Competitive Mode)

### Unlock Requirements
- Must complete **at least 5 classic questions** first
- Cannot play **below** current rank (anti-farming)
- Can only play current rank or **+1 rank** (skip attempt)

### Skip Attempt Rules
- 3 skip attempts available
- 24-hour cooldown after each attempt
- Win = instant promotion + reset attempts to 3
- Lose = lose 1 attempt, stay at current rank

### Match Flow

```
1. Check eligibility (5+ classic, not farming, skip rules)
2. Create match record in DB
3. Select 10 questions for rank difficulty
4. For each question:
   - Bronze: 2 options, no timer
   - Silver/Gold: 4 options, no timer
   - Platinum: 4 options, 30s timer
   - Diamond: 4 options, 20s timer
5. Timer violation = automatic incorrect
6. Show 2-second feedback after each answer
7. Match ends: Calculate score
   - Win if ≥70% correct
   - Lose otherwise
8. Update rank (promote on win at current rank)
9. Show full review of all questions
```

### Match Redis State

```python
match_state = {
    "user_id": "uuid-string",
    "rank_id": 2,
    "is_skip_attempt": False,
    "questions_asked": ["q-uuid1"],
    "current_question": {
        "id": "q-uuid1",
        "text": "...",
        "options": ["A", "B", "C", "D"],
        "correct_index": 2,
        "topic": "history",
        "difficulty": 3
    },
    "current_explanation": "The answer is...",
    "correct_count": 0,
    "total_time": 0,
    "question_shown_at": 1712134800.0,
    "answered_questions": [
        {
            "question_text": "...",
            "options": ["A", "B", "C", "D"],
            "user_answer_index": 1,
            "correct_answer_index": 2,
            "was_correct": False,
            "explanation": "..."
        }
    ]
}
```

### Question Selection by Rank

```python
rank_beta_map = {
    1: (-2.0, -1.0),  # Bronze: Easy
    2: (-1.0, +0.5),  # Silver: Medium-Easy
    3: (0.0, +1.0),   # Gold: Medium
    4: (+0.5, +1.5),  # Platinum: Medium-Hard
    5: (+1.0, +2.5),  # Diamond: Hard
}

# For Bronze rank only (n_options=2):
# Keep correct answer + 1 random wrong answer
# Shuffle to randomize position
```

---

## RAG Pipeline & Question Generation

### 3-Agent Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ 1. ROUTER AGENT                                              │
│    Decides source weights based on topic + difficulty        │
│    Default: {wikipedia: 70%, huggingface: 20%, wikidata: 10%}│
├─────────────────────────────────────────────────────────────┤
│ 2. RETRIEVER AGENT                                           │
│    Fetches context from weighted sources                     │
│    - Wikipedia: Article summaries                            │
│    - Wikidata: SPARQL facts                                  │
│    - HuggingFace: Pre-generated Q&A                         │
├─────────────────────────────────────────────────────────────┤
│ 3. VALIDATOR AGENT                                           │
│    Checks question quality before serving                    │
│    - Has 4 distinct options?                                │
│    - Explanation doesn't reveal answer?                     │
│    - Text length ≥ 10 characters?                           │
└─────────────────────────────────────────────────────────────┘
```

### LLM Question Generation Prompt

```
System: You are an expert educational MCQ generator.
Return ONLY valid JSON:

{
  "text": "the question",
  "correct": "the correct answer",
  "wrong1": "plausible wrong answer",
  "wrong2": "plausible wrong answer", 
  "wrong3": "plausible wrong answer",
  "explanation": "1-2 sentences explaining WHY",
  "concept": "specific concept tested (e.g., 'Roman Empire')",
  "concept_description": "brief 1-sentence description"
}

RULES:
- All wrong answers must be plausible
- Explanation must NOT restate the question
- Difficulty should match target level
```

### Hint Generation (Never Reveals Answer)

```python
HINT_SYSTEM_PROMPT = """
You are a quiz hint generator. Give short cryptic hints.
Never reveal the answer. Max 20 words.

GOOD: "Think about events in early 20th century."
BAD: "The answer involves Napoleon." (reveals subject)
"""

# Safety check:
if hint.lower().startswith(correct_answer[:8].lower()):
    return "Think about the broader context of this topic."
```

---

## Frontend Architecture

### Route Structure

| Route              | Protection     | Component        | Purpose                       |
| ------------------ | -------------- | ---------------- | ----------------------------- |
| `/`                | Public         | `Home`           | Landing page                  |
| `/login`           | PublicRoute    | `Login`          | Auth (redirects if logged in) |
| `/signup`          | PublicRoute    | `Signup`         | Registration                  |
| `/forgot-password` | Public         | `ForgotPassword` | Password recovery             |
| `/reset-password`  | Public         | `ResetPassword`  | OTP verification              |
| `/dashboard`       | ProtectedRoute | `Dashboard`      | Main hub                      |
| `/rooms/classic`   | ProtectedRoute | `ClassicRoom`    | Training mode                 |
| `/rooms/challenge` | ProtectedRoute | `ChallengeRoom`  | Competitive mode              |
| `/concept-mastery` | ProtectedRoute | `ConceptMastery` | Learning analytics            |
| `/profile`         | ProtectedRoute | `Profile`        | User profile                  |

### Auth Context State

```typescript
interface AuthState {
  user: { id: string; email: string; username: string } | null;
  token: string | null;
  isLoading: boolean;
}

// Storage:
localStorage.setItem('adaptiq_token', token);
localStorage.setItem('adaptiq_user_id', userId);
```

### Classic Room UI Flow

```
┌─────────────────────────────────────────────┐
│ STEP 1: TOPIC SELECTION                      │
│                                              │
│   Choose Your Path                           │
│   ○ History       ○ Geography    ○ Mixed     │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ STEP 2: QUIZ GAMEPLAY                        │
│                                              │
│ Question 3/10    2 correct    Timer: 25s    │
│ ┌─────────────────────────────────────────┐ │
│ │ What is the capital of France?          │ │
│ └─────────────────────────────────────────┘ │
│   ○ London                                  │
│   ● Paris (selected)                        │
│   ○ Berlin                                  │
│   ○ Madrid                                  │
│                                              │
│ [Get Hint] (-3 points)                      │
│                                              │
│ After answer:                               │
│ ┌─────────────────────────────────────────┐ │
│ │ ✓ Correct!                              │ │
│ │ Learn More: Paris has been...           │ │
│ └─────────────────────────────────────────┘ │
│ [Next Question →]                           │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ STEP 3: SUMMARY                              │
│                                              │
│ 🏆 Quiz Complete!                            │
│ Score: 8/10 (80%)                           │
│ Points: 72                                  │
│ Hints Used: 1                               │
│                                              │
│ [Return to Dashboard]                       │
└─────────────────────────────────────────────┘
```

### Challenge Room UI Flow

```
┌─────────────────────────────────────────────┐
│ STEP 1: LOBBY                                │
│                                              │
│ RANKED CHALLENGES                            │
│ Current Rank: 🥈 Silver                      │
│ Win/Loss: 5/3                               │
│ Skip Attempts: 2 remaining                  │
│                                              │
│ [START RANKED MATCH]                        │
│ [SKIP TO GOLD (2 left)]                     │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ STEP 2: MATCH                                │
│                                              │
│ Silver | Score: 60% | Q: 4 left | Time: 28s │
│ ┌─────────────────────────────────────────┐ │
│ │ Which river is longest in Europe?       │ │
│ └─────────────────────────────────────────┘ │
│   ○ Danube (your answer)                   │
│   ● Volga ← Correct                        │
│   ○ Rhine                                  │
│   ○ Thames                                 │
│                                              │
│ ┌── FEEDBACK (2 seconds) ──────────────────┐│
│ │ ✗ Incorrect                              ││
│ │ The Volga River is 3,530 km long...      ││
│ └──────────────────────────────────────────┘│
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ STEP 3: SUMMARY + REVIEW                     │
│                                              │
│ 🏆 VICTORY!                                  │
│ Score: 85%                                  │
│ Rank: Silver → Gold                         │
│                                              │
│ REVIEW YOUR ANSWERS                         │
│ ▼ Q1: Which river... ✓                      │
│   Your answer: Volga (Correct)             │
│   Learn More: The Volga is...              │
│ ▼ Q2: Capital of... ✗                       │
│   Your answer: Berlin (Wrong)              │
│   Correct: Paris                           │
│   Learn More: Paris has been...            │
└─────────────────────────────────────────────┘
```

---

## API Reference

### Authentication Endpoints

| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| POST | `/api/auth/register` | No | Create account |
| POST | `/api/auth/login` | No | Login |
| GET | `/api/auth/me` | Bearer | Get current user |
| POST | `/api/auth/logout` | Bearer | Revoke token |
| POST | `/api/auth/forgot-password` | No | Send OTP |
| POST | `/api/auth/reset-password` | No | Reset with OTP |

### Classic Room Endpoints

| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| POST | `/api/rooms/classic/start` | Bearer | Start session |
| POST | `/api/rooms/classic/answer/{session_id}` | Bearer | Submit answer |
| POST | `/api/rooms/classic/hint/{session_id}` | Bearer | Get hint |
| GET | `/api/rooms/classic/metrics/{session_id}` | Bearer | Get session metrics |

### Challenge Room Endpoints

| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| GET | `/api/rooms/challenge/status` | Bearer | Get rank & stats |
| POST | `/api/rooms/challenge/start` | Bearer | Start match |
| POST | `/api/rooms/challenge/answer/{match_id}` | Bearer | Submit answer |
| POST | `/api/rooms/challenge/end/{match_id}` | Bearer | End match & get review |

### System Endpoints

| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| GET | `/api/system/health` | No | Basic health check |
| GET | `/api/system/health/detailed` | No | Detailed health |
| GET | `/api/system/test-question` | No | Test question |

---

## Constants & Configuration

### IRT Constants
```python
THETA_INIT = 0.0              # Starting user ability
BETA_INIT = 0.0               # Starting question difficulty
LEARN_RATE = 0.3              # Theta update step size
THETA_RANGE = (-3.0, +3.0)    # Ability bounds
BETA_RANGE = (-3.0, +3.0)     # Difficulty bounds
ZPD_P_LOW = 0.60              # Target 60% success
ZPD_P_HIGH = 0.75             # Target 75% success
```

### Session Constants
```python
MAX_QUESTIONS_PER_SESSION = 10
QUIZ_TIME_LIMIT_SECONDS = 30
MIN_RESPONSES_FOR_CONFIDENCE = 5  # Warm-up period
```

### Spaced Repetition
```python
REPEAT_DUE_SESSIONS = 7                    # Sessions until repeat
WRONG_ANSWER_REPEAT_PROBABILITY = 0.25     # 25% queue on wrong
CORRECT_ANSWER_REPEAT_PROBABILITY = 0.01   # 1% queue on correct
```

### Challenge Constants
```python
MIN_CLASSIC_GAMES_FOR_CHALLENGE = 5
QUESTIONS_PER_MATCH = 10
WIN_THRESHOLD = 0.70  # 70% correct to win
SKIP_COOLDOWN_HOURS = 24
```

### Inactivity Decay
```python
INACTIVITY_DECAY_DAYS = 14       # Start decay after 2 weeks
INACTIVITY_DECAY_FACTOR = 0.1    # 10% theta decay per period
```

### Redis TTLs
```python
SESSION_TTL_SECONDS = 3600       # 1 hour
OTP_EXPIRE_SECONDS = 600         # 10 minutes
RATE_LIMIT_TTL = 60              # 1 minute
```

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         USER JOURNEY                                 │
└─────────────────────────────────────────────────────────────────────┘

1. SIGNUP/LOGIN
   Frontend ──→ POST /auth/register ──→ Backend validates
                                         ↓
                                    Create User in DB
                                         ↓
                                    Generate JWT
                                         ↓
   Frontend ←── { access_token, user } ←─┘

2. START CLASSIC SESSION
   Frontend ──→ POST /rooms/classic/start {topic}
                         ↓
                Apply inactivity decay
                         ↓
                Select 5 concepts (scoring)
                         ↓
                Select first question (ZPD)
                         ↓
                Store session in Redis
                         ↓
   Frontend ←── { session_id, first_question } ←─┘

3. ANSWER QUESTION
   Frontend ──→ POST /rooms/classic/answer/{session_id}
               { question_id, selected_index }
                         ↓
                Verify answer server-side
                         ↓
                Update theta (IRT)
                         ↓
                Check spaced repetition
                         ↓
                Select next question
                         ↓
   Frontend ←── { correct, explanation, next_question } ←─┘

4. CHALLENGE MATCH
   Frontend ──→ POST /rooms/challenge/start {rank_id}
                         ↓
                Validate eligibility
                         ↓
                Create match record
                         ↓
                Select question for rank
                         ↓
   Frontend ←── { match_id, first_question } ←─┘
                         ↓
               (10 questions with feedback)
                         ↓
   Frontend ──→ POST /rooms/challenge/end/{match_id}
                         ↓
                Calculate score
                         ↓
                Update rank (if win)
                         ↓
   Frontend ←── { result, score, questions_review } ←─┘
```

---

*Last Updated: April 2026*
*Version: 1.1.0*
