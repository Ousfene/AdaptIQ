# AdaptIQ Implementation Action Plan
## Specific Issues, Code Examples, and Fix Instructions

**Status**: Ready for Development
**Last Updated**: 2026-04-02
**Priority**: Critical Path Items First

---

## ISSUE #1: Frontend Form Locking Missing (2 hours)

### Problem
Users can click multiple answer options before the question is fully loaded or before submission completes. This causes:
- Confusing "answer submitted for wrong question" errors
- Double submissions
- State inconsistency

### Location
`frontend/src/pages/ClassicRoom.tsx` - Answer option buttons

### Current Code (BROKEN)
```typescript
// Line ~150 (approximate)
<div className="grid grid-cols-2 gap-4 mt-8">
  {currentQuestion?.options.map((option, idx) => (
    <button
      key={idx}
      onClick={() => handleSelectAnswer(option)}
      className="p-4 bg-blue-500 hover:bg-blue-600 text-white rounded"
    >
      {option}
    </button>
  ))}
</div>
```

### Issues in Current Code
1. ❌ No `disabled` attribute based on loading state
2. ❌ No check if question is fully loaded before allowing clicks
3. ❌ No visual feedback during submission
4. ❌ Multiple clicks not prevented

### Fixed Code
```typescript
const [isLoadingQuestion, setIsLoadingQuestion] = useState(false);
const [isSubmittingAnswer, setIsSubmittingAnswer] = useState(false);
const [selectedOption, setSelectedOption] = useState<string | null>(null);

const handleSelectAnswer = async (option: string) => {
  // Prevent double-click
  if (isSubmittingAnswer) return;

  setSelectedOption(option);
  setIsSubmittingAnswer(true);

  try {
    const response = await apiService.submitAnswer({
      user_id: userId,
      session_id: sessionId,
      question_id: currentQuestion.id,
      selected_answer: option,
      used_hint: hintUsed
    });

    if (response.ok) {
      // Move to next question...
    } else {
      setSelectedOption(null);  // Reset if failed
    }
  } finally {
    setIsSubmittingAnswer(false);
  }
};

const isButtonDisabled = isLoadingQuestion || isSubmittingAnswer || !currentQuestion;

return (
  <div className="grid grid-cols-2 gap-4 mt-8">
    {currentQuestion?.options.map((option, idx) => (
      <button
        key={idx}
        onClick={() => handleSelectAnswer(option)}
        disabled={isButtonDisabled}
        className={`p-4 rounded text-white font-semibold transition-all ${
          isButtonDisabled
            ? 'bg-gray-400 cursor-not-allowed opacity-50'
            : 'bg-blue-500 hover:bg-blue-600 cursor-pointer'
        } ${
          selectedOption === option && isSubmittingAnswer
            ? 'bg-green-500 ring-4 ring-green-300'
            : ''
        }`}
      >
        {isSubmittingAnswer && selectedOption === option ? (
          <span className="flex items-center gap-2">
            <span className="animate-spin">⏳</span>
            Submitting...
          </span>
        ) : (
          option
        )}
      </button>
    ))}
  </div>
);
```

### Testing
```typescript
// Add test for form locking
it('should disable answer buttons during submission', async () => {
  render(<ClassicRoom />);

  const answerButtons = screen.getAllByRole('button', { name: /^[A-D]$/ });
  const firstButton = answerButtons[0];

  // Button should be enabled initially
  expect(firstButton).not.toBeDisabled();

  // Click answer (should be disabled now)
  fireEvent.click(firstButton);
  expect(firstButton).toBeDisabled();

  // Wait for submission
  await waitFor(() => {
    expect(firstButton).not.toBeDisabled();
  });
});
```

### Checklist
- [ ] Add `isSubmittingAnswer` state hook
- [ ] Add `selectedOption` state hook to show which was clicked
- [ ] Update button className to show disabled state
- [ ] Update onClick handler to prevent double-click
- [ ] Add loading spinner text during submission
- [ ] Test: Click button, verify disabled, wait for response
- [ ] Test: Click another button, verify ignored
- [ ] Verify form still works on slow networks (>1s response)

---

## ISSUE #2: Concept-Aware Question Filtering Missing (8 hours)

### Problem
Currently, questions are selected randomly or by topic only. The system doesn't prioritize question covering concepts the user is weak in. This defeats the entire adaptive learning premise.

### Current Code (BROKEN)
**File**: `backend/routers/classic_room.py`, line ~85 (question generation)

```python
async def post_question(body: GenerateQuestionRequest, request: Request):
    # ...
    concept_name = body.concept or "history"  # Just use whatever user provided

    # ISSUE: Just pick random question from topic, ignore user's knowledge
    question = await get_random_question(topic=concept_name)

    session["current_question"] = str(question["id"])
    return question
```

### What's Missing
1. ❌ No query of user's per-concept theta
2. ❌ No filtering of questions by concept
3. ❌ No ranking by how weak user is in that concept
4. ❌ Concepts not extracted from generated questions

### Fixed Implementation

#### Step 1: Auto-Extract Concepts (in RAG pipeline)
**File**: `backend/rag/agentic.py`

```python
async def extract_concepts_from_question(question_text: str, answer_text: str) -> List[str]:
    """
    Use LLM to extract specific concepts (e.g., "Roman Empire", "Egyptian Dynasty")
    from question + answer.
    """
    prompt = f"""
    Given this quiz question and answer, extract 2-3 SPECIFIC historical/geographical concepts:

    Question: {question_text}
    Correct Answer: {answer_text}

    Extract specific topics like "Roman Empire", "Egyptian Dynasty", "Byzantine Empire", etc.
    Do NOT use broad categories like "history" or "geography".

    Format: ["concept1", "concept2", "concept3"]
    """

    response = await llm_client.generate(prompt, temperature=0.3)

    try:
        concepts = json.loads(response)
        return concepts[:3]  # Limit to 3
    except:
        return ["general_history"]  # Fallback
```

#### Step 2: Store Concepts in Database
**File**: `backend/database/models.py`

```python
class QuestionConcept(Base):
    """Link between questions and concepts they test."""
    __tablename__ = "question_concepts"

    id = Column(UUID, primary_key=True, default=uuid4)
    question_id = Column(UUID, ForeignKey("question_bank.id"), nullable=False)
    concept_id = Column(UUID, ForeignKey("concepts.id"), nullable=False)
    relevance_score = Column(Float, default=1.0)  # 0-1, how core to question

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_question_concepts_question', 'question_id'),
        Index('idx_question_concepts_concept', 'concept_id'),
        UniqueConstraint('question_id', 'concept_id', name='uq_question_concept'),
    )
```

#### Step 3: Query User's Weak Concepts
**File**: `backend/routers/classic_room.py`

```python
async def get_user_weak_concepts(user_id: UUID, session: AsyncSession) -> List[Dict]:
    """
    Get concepts where user's theta is below 0 (hasn't mastered).
    Ordered by weakest first.
    """
    stmt = select(
        UserConceptTheta.concept_id,
        UserConceptTheta.theta,
        Concept.name
    ).join(Concept).where(
        UserConceptTheta.user_id == user_id,
        UserConceptTheta.theta < 0.0  # Not mastered yet
    ).order_by(UserConceptTheta.theta)  # Weakest first

    result = await session.execute(stmt)
    return [
        {"concept_id": r[0], "theta": r[1], "name": r[2]}
        for r in result
    ]

async def get_questions_for_concept(
    concept_id: UUID,
    difficulty_target: float,
    session: AsyncSession,
    exclude_question_ids: List[UUID] = None
) -> List[Dict]:
    """
    Get questions testing this concept, ordered by difficulty match.
    Avoids recently shown questions.
    """
    stmt = select(QuestionBank).join(
        QuestionConcept,
        QuestionBank.id == QuestionConcept.question_id
    ).where(
        QuestionConcept.concept_id == concept_id,
        ~QuestionBank.id.in_(exclude_question_ids or [])
    ).order_by(
        # Prefer difficulty closest to target
        func.abs(QuestionBank.difficulty_irt - difficulty_target)
    )

    result = await session.execute(stmt)
    return [row[0].to_dict() for row in result.fetchall()]
```

#### Step 4: Updated Question Generation Endpoint
**File**: `backend/routers/classic_room.py`, GET /api/rooms/classic/questions

```python
async def post_question(body: GenerateQuestionRequest, request: Request):
    """
    Generate or retrieve question adapted to user's knowledge gaps.
    """
    user_id = body.user_id
    session_id = body.session_id
    topic_filter = body.concept  # "history", "geography", "mix"

    async with AsyncSessionLocal() as session:
        # Get user's weak concepts (theta < 0)
        weak_concepts = await get_user_weak_concepts(user_id, session)

        if not weak_concepts:
            # User has mastered all concepts, give random question
            focus_concept = None
        else:
            # Focus on weakest concept
            focus_concept = weak_concepts[0]

        # Get user's theta for this concept
        if focus_concept:
            concept_theta = focus_concept["theta"]
        else:
            concept_theta = 0.0  # Default

        # Calculate target difficulty via ZPD
        target_difficulty = select_difficulty_for_zpd(concept_theta)

        # Get recently shown questions (cache in session)
        session_data = await session_service.get_session(str(session_id))
        recently_shown = session_data.get("recent_questions", [])[-5:]

        # Query database for question
        if focus_concept:
            questions = await get_questions_for_concept(
                focus_concept["concept_id"],
                target_difficulty,
                session,
                exclude_question_ids=recently_shown
            )
        else:
            questions = await get_random_questions_by_difficulty(
                target_difficulty,
                session,
                topic_filter=topic_filter,
                exclude_question_ids=recently_shown
            )

        if questions:
            question = questions[0]  # Already ranked by difficulty match
        else:
            # Fallback: Generate new question
            question = await generate_and_cache_question(
                concept=focus_concept.get("name") if focus_concept else topic_filter,
                difficulty_level=next_difficulty
            )

        # Record that we showed this question
        session_data["current_question_id"] = str(question["id"])
        session_data["question_shown_at"] = datetime.utcnow().timestamp()
        session_data.setdefault("recent_questions", []).append(str(question["id"]))
        session_data["recent_questions"] = session_data["recent_questions"][-10:]  # Keep last 10

        await session_service.set_session(str(session_id), session_data)

        return question
```

### Database Migration
**File**: `backend/alembic/versions/XXXX_add_question_concepts.py`

```python
"""Add question concept tracking."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
import uuid

def upgrade():
    # Create question_concepts table
    op.create_table(
        'question_concepts',
        sa.Column('id', UUID(as_uuid=True), nullable=False, default=uuid.uuid4),
        sa.Column('question_id', UUID(as_uuid=True), nullable=False),
        sa.Column('concept_id', UUID(as_uuid=True), nullable=False),
        sa.Column('relevance_score', sa.Float(), nullable=False, server_default='1.0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['question_id'], ['question_bank.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['concept_id'], ['concepts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('question_id', 'concept_id', name='uq_question_concept'),
    )

    op.create_index('idx_question_concepts_question', 'question_concepts', ['question_id'])
    op.create_index('idx_question_concepts_concept', 'question_concepts', ['concept_id'])

def downgrade():
    op.drop_index('idx_question_concepts_concept', 'question_concepts')
    op.drop_index('idx_question_concepts_question', 'question_concepts')
    op.drop_table('question_concepts')
```

### Testing
```python
# backend/tests/test_concept_filtering.py
import pytest
from backend.routers.classic_room import get_user_weak_concepts, get_questions_for_concept
from backend.database.models import UserConceptTheta, Concept, QuestionConcept, QuestionBank

@pytest.mark.asyncio
async def test_weak_concepts_ranked_by_theta():
    """Weakest concepts appear first."""
    user_id = uuid.uuid4()

    # Setup: user with theta -2.0 for history, -0.5 for geography
    async with AsyncSessionLocal() as session:
        await create_test_concept(session, "history")
        await create_test_concept(session, "geography")

        history_concept = await get_concept_by_name(session, "history")
        geo_concept = await get_concept_by_name(session, "geography")

        # Set theta values
        await set_user_concept_theta(session, user_id, history_concept.id, -2.0)
        await set_user_concept_theta(session, user_id, geo_concept.id, -0.5)

        # Get weak concepts
        weak = await get_user_weak_concepts(user_id, session)

        # History should come first (theta=-2.0 < -0.5)
        assert weak[0]["name"] == "history"
        assert weak[1]["name"] == "geography"

@pytest.mark.asyncio
async def test_questions_ranked_by_difficulty_match():
    """Questions closest to target difficulty ranked first."""
    concept_id = uuid.uuid4()
    target_difficulty = 0.5  # Medium

    async with AsyncSessionLocal() as session:
        # Create questions: easy (-1.0), medium (0.5), hard (2.0)
        await create_question(session, concept_id, difficulty_irt=-1.0)
        medium_q = await create_question(session, concept_id, difficulty_irt=0.5)
        await create_question(session, concept_id, difficulty_irt=2.0)

        questions = await get_questions_for_concept(concept_id, target_difficulty, session)

        # Medium difficulty should be first
        assert questions[0]["id"] == medium_q.id
```

### Checklist
- [ ] Create QuestionConcept model in models.py
- [ ] Create alembic migration script
- [ ] Run: `alembic upgrade head`
- [ ] Update RAG to extract concepts
- [ ] Update classic_room.py with get_user_weak_concepts()
- [ ] Update classic_room.py with get_questions_for_concept()
- [ ] Update POST /questions endpoint to use concept filtering
- [ ] Test: Get question for weak concept
- [ ] Test: Questions ranked by difficulty match
- [ ] Verify: user_concept_theta table has data for new users

---

## ISSUE #3: Challenge Room Not Implemented (40 hours)

### Problem
Entire challenge room feature is missing - no endpoints, no database tables, no logic, no frontend.

### Required Database Tables

**Run these migrations**:

```python
# backend/alembic/versions/001_challenge_room_setup.py

def upgrade():
    # Challenge rank definitions (Bronze, Silver, Gold, etc)
    op.create_table(
        'challenge_ranks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('rank_name', sa.String(50), nullable=False),
        sa.Column('level', sa.Integer(), nullable=False),  # 1-5
        sa.Column('min_options', sa.Integer(), nullable=False),  # 2, 3, 4, 4, 0
        sa.Column('time_limit_seconds', sa.Integer(), nullable=False),  # 45, 40, 35, 30, 25
        sa.Column('elo_threshold', sa.Integer(), nullable=False),  # Min ELO to access
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    # User's current challenge rank + ELO
    op.create_table(
        'user_challenge_ranks',
        sa.Column('id', UUID(as_uuid=True), primary_key=False),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('current_rank_id', sa.Integer(), nullable=False),
        sa.Column('elo', sa.Integer(), nullable=False, server_default='1200'),
        sa.Column('matches_played', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('matches_won', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('win_streak', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('skip_attempts_remaining', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('skip_cooldown_until', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['current_rank_id'], ['challenge_ranks.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', name='uq_user_challenge_rank'),
    )

    # Match history
    op.create_table(
        'challenge_matches',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('rank_id', sa.Integer(), nullable=False),
        sa.Column('questions_count', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('correct_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('score', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('elo_before', sa.Integer(), nullable=False),
        sa.Column('elo_after', sa.Integer(), nullable=False),
        sa.Column('elo_change', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),  # in_progress, completed, abandoned, timeout
        sa.Column('total_time_seconds', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('ended_at', sa.DateTime()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['rank_id'], ['challenge_ranks.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_challenge_matches_user', 'challenge_matches', ['user_id', 'started_at'])
```

### Backend Endpoints to Implement

**File**: `backend/routers/challenge.py` (currently stubbed)

```python
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from backend.dependencies import get_db, get_current_user
from backend.schemas import (
    ChallengeStatusResponse,
    ChallengeStartRequest,
    ChallengeStartResponse,
    ChallengeAnswerRequest,
    ChallengeResultResponse,
)
from backend.database.models import (
    User, UserChallengeRank, ChallengeMatch, ChallengeRank, QuestionBank
)
from datetime import datetime, timedelta
import uuid

router = APIRouter(prefix="/api/rooms/challenge", tags=["challenge"])

# ── GET /status: Get user's current rank and progress ──────────────────────
@router.get("/status", response_model=ChallengeStatusResponse)
async def get_challenge_status(
    user_id: UUID,
    session: AsyncSession = Depends(get_db),
):
    """
    Get user's current challenge rank, ELO, win/loss record.
    """
    stmt = select(UserChallengeRank).where(
        UserChallengeRank.user_id == user_id
    )
    user_rank = await session.scalar(stmt)

    if not user_rank:
        # First time in challenge room -> start as Bronze
        user_rank = UserChallengeRank(
            id=uuid.uuid4(),
            user_id=user_id,
            current_rank_id=1,  # Bronze
            elo=1200,
            matches_played=0,
            matches_won=0,
        )
        session.add(user_rank)
        await session.commit()

    return ChallengeStatusResponse(
        rank_name="Bronze",  # Get from lookup
        elo=user_rank.elo,
        matches_played=user_rank.matches_played,
        matches_won=user_rank.matches_won,
        win_rate=user_rank.matches_won / user_rank.matches_played if user_rank.matches_played > 0 else 0,
    )

# ── POST /start: Start a new match ──────────────────────────────────────────
@router.post("/start", response_model=ChallengeStartResponse)
async def start_challenge_match(
    body: ChallengeStartRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """
    Begin a challenge match at specified rank (or current rank).

    Returns: match_id, first question, timer limit
    """
    user_id = body.user_id
    rank_id = body.rank_id or None  # If None, use user's current rank

    # Get user's challenge rank
    stmt = select(UserChallengeRank).where(
        UserChallengeRank.user_id == user_id
    )
    user_rank = await session.scalar(stmt)

    if not user_rank:
        raise HTTPException(status_code=403, detail="Must complete 10 classic quizzes first")

    # Validate user can access requested rank
    if rank_id:
        if rank_id > user_rank.current_rank_id + 1:
            raise HTTPException(
                status_code=403,
                detail="Can only skip to rank directly above yours"
            )
        if rank_id > user_rank.current_rank_id and user_rank.skip_attempts_remaining <= 0:
            if user_rank.skip_cooldown_until and datetime.utcnow() < user_rank.skip_cooldown_until:
                raise HTTPException(
                    status_code=429,
                    detail=f"Skip cooled until {user_rank.skip_cooldown_until}"
                )
    else:
        rank_id = user_rank.current_rank_id

    # Get rank details
    rank = await session.get(ChallengeRank, rank_id)

    # Create match
    match = ChallengeMatch(
        id=uuid.uuid4(),
        user_id=user_id,
        rank_id=rank_id,
        elo_before=user_rank.elo,
        status="in_progress",
        started_at=datetime.utcnow(),
    )
    session.add(match)
    await session.commit()

    # Store in Redis for quick access
    match_state = {
        "match_id": str(match.id),
        "user_id": str(user_id),
        "rank_id": rank_id,
        "questions_answered": 0,
        "correct_count": 0,
        "total_time": 0,
        "started_at": datetime.utcnow().timestamp(),
    }
    await redis_client.setex(
        f"match:{match.id}",
        3600,  # 1 hour TTL
        json.dumps(match_state)
    )

    # Get first question
    next_q = await get_next_challenge_question(user_id, rank)

    return ChallengeStartResponse(
        match_id=str(match.id),
        question=next_q,
        time_limit_seconds=rank.time_limit_seconds,
        total_questions=5,
    )

# ── POST /answer: Submit answer to challenge question ──────────────────────
@router.post("/answer", response_model=ChallengeResultResponse)
async def submit_challenge_answer(
    body: ChallengeAnswerRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """
    Submit answer to challenge question.
    - Check server-side time
    - Calculate points
    - Determine win/loss
    - Return next question or results
    """
    user_id = body.user_id
    match_id = body.match_id
    question_id = body.question_id
    selected_answer = body.selected_answer

    # Get match from Redis
    match_state_json = await redis_client.get(f"match:{match_id}")
    if not match_state_json:
        raise HTTPException(status_code=410, detail="Match expired")

    match_state = json.loads(match_state_json)

    # Calculate server-side time taken
    question_shown_at = match_state.get("question_shown_at", datetime.utcnow().timestamp())
    now = datetime.utcnow().timestamp()
    time_taken_seconds = now - question_shown_at

    # Get rank for timer limit
    rank = await session.get(ChallengeRank, match_state["rank_id"])
    time_limit = rank.time_limit_seconds

    # Check if timed out
    if time_taken_seconds > time_limit:
        # Mark as timeout loss
        match_state["status"] = "timeout"
        match_state["result"] = "loss"
        # Calculate ELO change...
        # Update match in DB...
        return ChallengeResultResponse(
            status="timeout",
            message=f"Time exceeded {time_limit}s limit",
            next_question=None,
            match_results={"elo_change": -20},
        )

    # Get question to check answer
    question = await session.get(QuestionBank, question_id)
    is_correct = selected_answer.lower().strip() == question.correct_answer.lower().strip()

    # Track: questions_answered, correct_count
    match_state["questions_answered"] += 1
    if is_correct:
        match_state["correct_count"] += 1
        points = 100 - int(time_taken_seconds)  # Bonus for speed
    else:
        points = 0

    match_state["score"] = match_state.get("score", 0) + points
    match_state["total_time"] = match_state.get("total_time", 0) + int(time_taken_seconds)

    # Check if match complete (5 questions answered)
    questions_count = 5
    if match_state["questions_answered"] >= questions_count:
        # Calculate ELO change
        win_rate = match_state["correct_count"] / questions_count
        elo_delta = calculate_elo_change(
            user_elo=match_state["elo_before"],
            opponent_elo=2000,  # Simple model: always play "2000 Elo" difficulty
            result=(1 if win_rate > 0.5 else 0),  # Win if >50% correct
            k_factor=40,
        )

        match_state["elo_after"] = match_state["elo_before"] + elo_delta
        match_state["status"] = "completed"

        # Update database match record
        match = await session.get(ChallengeMatch, UUID(match_id))
        match.correct_count = match_state["correct_count"]
        match.score = match_state["score"]
        match.elo_after = match_state["elo_after"]
        match.elo_change = elo_delta
        match.total_time_seconds = match_state["total_time"]
        match.status = "completed"
        match.ended_at = datetime.utcnow()

        # Update user rank
        user_rank = await session.scalar(
            select(UserChallengeRank).where(
                UserChallengeRank.user_id == user_id
            )
        )
        user_rank.elo = match_state["elo_after"]
        user_rank.matches_played += 1
        if elo_delta > 0:
            user_rank.matches_won += 1
            user_rank.win_streak += 1
        else:
            user_rank.win_streak = 0

        # Rank up at thresholds (simplified)
        if user_rank.elo >= 1400 and user_rank.current_rank_id < 5:
            user_rank.current_rank_id += 1

        await session.commit()

        return ChallengeResultResponse(
            status="completed",
            message=f"Match complete! ELO: {match_state['elo_before']} → {match_state['elo_after']}",
            next_question=None,
            match_results={
                "total_questions": questions_count,
                "correct": match_state["correct_count"],
                "accuracy": f"{100 * match_state['correct_count'] / questions_count:.0f}%",
                "elo_before": match_state["elo_before"],
                "elo_after": match_state["elo_after"],
                "elo_change": elo_delta,
                "total_time": match_state["total_time"],
            }
        )
    else:
        # Get next question
        next_q = await get_next_challenge_question(user_id, rank)
        match_state["question_shown_at"] = datetime.utcnow().timestamp()

        # Update Redis
        await redis_client.setex(
            f"match:{match_id}",
            3600,
            json.dumps(match_state)
        )

        return ChallengeResultResponse(
            status="in_progress",
            message="Correct!" if is_correct else "Incorrect",
            next_question=next_q,
            match_results=None,
        )
```

### Helper Functions

```python
async def get_next_challenge_question(
    user_id: UUID,
    rank: ChallengeRank,
    session: AsyncSession,
) -> Dict:
    """
    Get next question for challenge room.
    - Appropriate difficulty for rank
    - Limited options based on rank (2 at Bronze, 4 at higher)
    - Not recently answered
    """
    # Get user's theta (approximate ability)
    theta = await get_average_user_theta(user_id, session)

    # Map rank to difficulty target
    difficulty_map = {
        1: -0.5,   # Bronze: easy
        2: 0.0,    # Silver: medium
        3: 0.5,    # Gold: harder
        4: 1.0,    # Platinum: very hard
        5: 1.5,    # Diamond: extreme
    }
    target_difficulty = difficulty_map[rank.level]

    # Get random question at that difficulty
    stmt = select(QuestionBank).where(
        QuestionBank.difficulty_irt.between(target_difficulty - 0.3, target_difficulty + 0.3)
    ).order_by(func.random()).limit(1)

    question = await session.scalar(stmt)

    # Shuffle options but keep track of correct position
    options = question.options.copy()
    correct_index = options.index(question.correct_answer)
    random.shuffle(options)
    new_correct_index = options.index(question.correct_answer)

    # Limit options based on rank
    if rank.level == 1:
        # Bronze: 2 options (2 plausible, 2 obviously wrong)
        # Keep correct + 1 plausible...
        options = options[:2]

    return {
        "id": str(question.id),
        "text": question.text,
        "options": options,
        "is_multiple_choice": rank.level <= 4,  # At diamond, open-ended
    }

def calculate_elo_change(user_elo: int, opponent_elo: int, result: int, k_factor: int) -> int:
    """
    Calculate ELO change using standard formula.
    result: 1 for win, 0.5 for draw, 0 for loss
    """
    expected = 1 / (1 + 10 ** ((opponent_elo - user_elo) / 400))
    elo_change = k_factor * (result - expected)
    return int(round(elo_change))
```

### Frontend (Complete Challenge Room Page)

**File**: `frontend/src/pages/ChallengeRoom.tsx`

```typescript
import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import apiService from '../services/apiService';

interface ChallengeQuestion {
  id: string;
  text: string;
  options: string[];
  is_multiple_choice: boolean;
}

interface MatchState {
  match_id: string;
  current_question: ChallengeQuestion;
  time_limit_seconds: number;
  total_questions: number;
  questions_answered: number;
  correct_count: number;
  is_submitted: boolean;
}

export default function ChallengeRoom() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [match, setMatch] = useState<MatchState | null>(null);
  const [selectedAnswer, setSelectedAnswer] = useState<string | null>(null);
  const [timeRemaining, setTimeRemaining] = useState<number>(45);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Start match on mount
  useEffect(() => {
    startMatch();
  }, []);

  // Timer countdown
  useEffect(() => {
    if (!match || match.is_submitted) return;

    const timer = setInterval(() => {
      setTimeRemaining(prev => {
        if (prev <= 1) {
          // Time's up - auto-submit
          handleTimeout();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [match]);

  const startMatch = async () => {
    try {
      const response = await apiService.startChallenge({
        user_id: user!.id,
      });

      setMatch({
        ...response,
        is_submitted: false,
        questions_answered: 0,
        correct_count: 0,
      });
      setTimeRemaining(response.time_limit_seconds);
      setIsLoading(false);
    } catch (err) {
      setError(String(err));
      setIsLoading(false);
    }
  };

  const handleTimeout = async () => {
    // Submit with timeout flag
    const response = await apiService.submitChallengeAnswer({
      user_id: user!.id,
      match_id: match!.match_id,
      question_id: match!.current_question.id,
      selected_answer: '',
      timed_out: true,
    });

    if (response.status === 'completed') {
      showResults(response.match_results);
    }
  };

  const handleSubmitAnswer = async (answer: string) => {
    if (!match) return;

    setMatch({...match, is_submitted: true});

    try {
      const response = await apiService.submitChallengeAnswer({
        user_id: user!.id,
        match_id: match.match_id,
        question_id: match.current_question.id,
        selected_answer: answer,
      });

      if (response.status === 'completed') {
        showResults(response.match_results);
      } else {
        // Next question
        setMatch({
          ...match,
          current_question: response.next_question,
          questions_answered: match.questions_answered + 1,
          correct_count: response.next_question.is_correct
            ? match.correct_count + 1
            : match.correct_count,
          is_submitted: false,
        });
        setTimeRemaining(match.time_limit_seconds);
        setSelectedAnswer(null);
      }
    } catch (err) {
      setError(String(err));
      setMatch({...match, is_submitted: false});
    }
  };

  const showResults = (results: any) => {
    // Show results modal or navigate to results page
    navigate('/challenge-results', { state: results });
  };

  if (isLoading) return <div className="p-8">Loading...</div>;
  if (error) return <div className="p-8 text-red-600">Error: {error}</div>;
  if (!match) return null;

  const progressPercent = (match.questions_answered / match.total_questions) * 100;
  const timerColor = timeRemaining <= 10 ? 'text-red-600' : 'text-white';

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-900 to-black p-8">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="flex justify-between items-center mb-8">
          <h1 className="text-4xl font-bold text-white">Challenge Mode</h1>
          <div className={`text-4xl font-bold ${timerColor}`}>
            {Math.floor(timeRemaining / 60)}:{String(timeRemaining % 60).padStart(2, '0')}
          </div>
        </div>

        {/* Progress */}
        <div className="mb-8">
          <div className="text-white mb-2">
            Question {match.questions_answered + 1} of {match.total_questions}
          </div>
          <div className="w-full bg-gray-700 rounded-full h-4">
            <div
              className="bg-gradient-to-r from-blue-500 to-purple-500 h-4 rounded-full transition-all"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>

        {/* Question */}
        <div className="bg-gray-800 rounded-lg p-8 mb-8">
          <p className="text-white text-2xl font-semibold mb-6">
            {match.current_question.text}
          </p>

          {/* Options */}
          {match.current_question.is_multiple_choice ? (
            <div className="grid grid-cols-1 gap-4">
              {match.current_question.options.map((option, idx) => (
                <button
                  key={idx}
                  onClick={() => handleSubmitAnswer(option)}
                  disabled={match.is_submitted}
                  className={`p-4 text-left rounded transition-all ${
                    match.is_submitted
                      ? 'opacity-50 cursor-not-allowed'
                      : 'hover:bg-purple-600 cursor-pointer'
                  } ${
                    selectedAnswer === option
                      ? 'bg-purple-500 border-2 border-white'
                      : 'bg-gray-700'
                  }`}
                >
                  {option}
                </button>
              ))}
            </div>
          ) : (
            // Open-ended at Diamond rank
            <input
              type="text"
              placeholder="Type your answer..."
              disabled={match.is_submitted}
              className="w-full p-4 rounded bg-gray-700 text-white"
            />
          )}
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 gap-4 text-white">
          <div className="bg-gray-700 p-4 rounded">
            <div className="text-gray-300">Correct</div>
            <div className="text-3xl font-bold">{match.correct_count}/{match.questions_answered}</div>
          </div>
          <div className="bg-gray-700 p-4 rounded">
            <div className="text-gray-300">Accuracy</div>
            <div className="text-3xl font-bold">
              {match.questions_answered > 0
                ? Math.round((100 * match.correct_count) / match.questions_answered)
                : 0}%
            </div>
          </div>
          <div className="bg-gray-700 p-4 rounded">
            <div className="text-gray-300">Time Used</div>
            <div className="text-3xl font-bold">
              {match.time_limit_seconds * match.questions_answered - timeRemaining}s
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
```

### Checklist
- [ ] Create migrations for 3 new tables
- [ ] Run: `alembic upgrade head`
- [ ] Implement GET /status endpoint
- [ ] Implement POST /start endpoint
- [ ] Implement POST /answer endpoint
- [ ] Create helper functions (get_next_question, calculate_elo)
- [ ] Test: Start match → get question
- [ ] Test: Submit correct answer → points
- [ ] Test: Submit incorrect answer → no points
- [ ] Test: Timeout → loss
- [ ] Create ChallengeRoom.tsx component
- [ ] Test: Full match flow (5 questions)
- [ ] Create leaderboard page
- [ ] Test E2E: Register → Classic (10 Q) → Challenge

---

## ISSUE #4: Question Repetition System (6 hours)

See next section...

---

## ISSUE #5: ELO Decay System (4 hours)

### Problem
Inactive users maintain their ELO indefinitely, causing stale leaderboards.

### Solution: Per-Week Decay

```python
# backend/database/models.py

class UserActivityLog(Base):
    """Track when user takes quizzes for decay calc."""
    __tablename__ = "user_activity_log"

    id = Column(UUID, primary_key=True, default=uuid4)
    user_id = Column(UUID, ForeignKey("users.id"), ondelete="CASCADE")
    activity_type = Column(String(50))  # quiz_taken, challenge_match
    activity_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_user_activity_user_activity', 'user_id', 'activity_at'),
    )

# backend/scripts/apply_elo_decay.py
async def decay_inactive_users():
    """
    Run daily: For users inactive >30 days, apply -5 ELO per week.
    """
    async with AsyncSessionLocal() as session:
        # Get users inactive >30 days
        cutoff = datetime.utcnow() - timedelta(days=30)

        stmt = select(UserChallengeRank).where(
            ~exists(
                select(1).from_(UserActivityLog).where(
                    UserActivityLog.user_id == UserChallengeRank.user_id,
                    UserActivityLog.activity_at > cutoff
                )
            )
        )

        inactive_users = await session.scalars(stmt)

        for user_rank in inactive_users:
            # Get last activity
            last_activity = await session.scalar(
                select(UserActivityLog)
                .where(UserActivityLog.user_id == user_rank.user_id)
                .order_by(UserActivityLog.activity_at.desc())
                .limit(1)
            )

            if not last_activity:
                continue

            # Calculate weeks inactive
            weeks_inactive = (datetime.utcnow() - last_activity.activity_at).days // 7

            # Apply decay: -5 per week
            elo_loss = weeks_inactive * 5
            user_rank.elo = max(1000, user_rank.elo - elo_loss)  # Min 1000

        await session.commit()
```

---

## ISSUE #6: Test User Profiles (2 hours)

Create diverse test users with varied concept knowledge:

```python
# backend/scripts/create_test_users.py

async def create_test_profiles():
    """Create 5 test users with varied concept knowledge."""
    async with AsyncSessionLocal() as session:
        profiles = [
            {
                "email": "expert_egyptian@test.com",
                "username": "EgyptExpert",
                "concepts": {"Egyptian History": 2.0, "Roman History": -1.5, "Byzantine": -1.0},
            },
            {
                "email": "expert_roman@test.com",
                "username": "RomanScholar",
                "concepts": {"Roman History": 2.0, "Egyptian History": -1.5, "Byzantine": 0.5},
            },
            {
               "email": "beginner@test.com",
                "username": "Learner",
                "concepts": {k: -2.0 for k in ["Egyptian", "Roman", "Byzantine"]},
            },
            {
                "email": "balanced@test.com",
                "username": "Balanced",
                "concepts": {"Egyptian": 0.3, "Roman": 0.2, "Byzantine": 0.1},
            },
            {
                "email": "master@test.com",
                "username": "Master",
                "concepts": {k: 1.5 for k in ["Egyptian", "Roman", "Byzantine"]},
            },
        ]

        for profile in profiles:
            # Create user
            user = User(
                id=uuid.uuid4(),
                email=profile["email"],
                username=profile["username"],
                password_hash=hash_password("Test1234!")
            )
            session.add(user)
            await session.flush()

            # Create concepts and set theta
            for concept_name, theta in profile["concepts"].items():
                concept = await session.scalar(
                    select(Concept).where(Concept.name == concept_name)
                )
                if not concept:
                    concept = Concept(id=uuid.uuid4(), name=concept_name)
                    session.add(concept)
                    await session.flush()

                user_theta = UserConceptTheta(
                    id=uuid.uuid4(),
                    user_id=user.id,
                    concept_id=concept.id,
                    theta=theta
                )
                session.add(user_theta)

        await session.commit()
        print("✅ Created 5 test users with varied concept knowledge")
```

---

## Summary of All Issues & Fixes

| # | Issue | Impact | Effort | Status |
|---|-------|--------|--------|--------|
| 1 | Form locking missing | Users click before load | 2h | 📝 Plan ready |
| 2 | Concept filtering missing | System not adaptive | 8h | 📝 Plan ready |
| 3 | Challenge room missing | Feature unavailable | 40h | 📝 Plan ready |
| 4 | Question repetition missing | Learning ineffective | 6h | 📝 Plan pending |
| 5 | ELO decay missing | Stale leaderboards | 4h | 📝 Plan pending |
| 6 | Test users missing | Can't test varied scenarios | 2h | 📝 Plan pending |

**Total Development Time**: ~60 hours over 3 weeks

**Critical Path** (must do first):
1. Form locking (2h)
2. Challenge room backend (20h)
3. Challenge room frontend (20h)
4. Concept filtering (8h)
5. E2E tests (10h)

---

**Generated**: 2026-04-02
**Project**: AdaptIQ
**Role**: Technical Lead / Architect
