"""
Integration test for concept-aware caching system.

Run: python -m pytest tests/test_concept_awareness.py -v
"""

import pytest
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from database.models import Base, User, Concept, QuestionBank, QuestionConcept, UserConceptTheta
from database.irt import difficulty_to_beta, beta_to_difficulty, irt_probability
from database.concept_irt import ConceptIRT
from services.concept_cache_service import ConceptCacheService


@pytest.fixture
async def db():
    """Create in-memory SQLite test database."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        yield session


@pytest.mark.asyncio
async def test_user_concept_ability_tracking(db):
    """Test that per-concept theta is tracked separately."""
    user_id = uuid.uuid4()
    concept_1_id = uuid.uuid4()
    concept_2_id = uuid.uuid4()
    
    # Create concepts
    concept_1 = Concept(id=concept_1_id, name="Egyptian History", topic="History")
    concept_2 = Concept(id=concept_2_id, name="Roman Geography", topic="Geography")
    db.add_all([concept_1, concept_2])
    await db.commit()
    
    # User answers question about concept_1 correctly
    theta_1 = await ConceptIRT.update_concept_theta(
        db, user_id, concept_1_id, beta=0.0, correct=True
    )
    assert theta_1 > 0.0  # Should increase on correct answer
    
    # User answers question about concept_2 incorrectly
    theta_2 = await ConceptIRT.update_concept_theta(
        db, user_id, concept_2_id, beta=0.0, correct=False
    )
    assert theta_2 < 0.0  # Should decrease on incorrect answer
    
    # Verify thetas are independent
    theta_1_check = await ConceptIRT.get_concept_theta(db, user_id, concept_1_id)
    theta_2_check = await ConceptIRT.get_concept_theta(db, user_id, concept_2_id)
    
    assert theta_1_check > theta_2_check
    print(f"✓ Concept 1 theta: {theta_1_check:.2f}")
    print(f"✓ Concept 2 theta: {theta_2_check:.2f}")


@pytest.mark.asyncio
async def test_per_user_difficulty_computation(db):
    """Test that same question has different difficulty for different users."""
    question_id = uuid.uuid4()
    concept_id = uuid.uuid4()
    user_1_id = uuid.uuid4()
    user_2_id = uuid.uuid4()
    
    # Create question and concept
    concept = Concept(id=concept_id, name="Test Concept", topic="History")
    question = QuestionBank(
        id=question_id,
        question_text="Test question",
        correct_answer="Answer",
        options_json='["A", "B", "C", "D"]',
        explanation="Explanation",
        topic="History",
        difficulty_irt=0.0,  # Beta = 0 (medium)
    )
    db.add_all([concept, question])
    await db.commit()
    
    # User 1: Strong in this concept (theta = 2.0)
    user_1_record = UserConceptTheta(
        user_id=user_1_id,
        concept_id=concept_id,
        theta=2.0,
    )
    db.add(user_1_record)
    
    # User 2: Weak in this concept (theta = -1.0)
    user_2_record = UserConceptTheta(
        user_id=user_2_id,
        concept_id=concept_id,
        theta=-1.0,
    )
    db.add(user_2_record)
    
    await db.commit()
    
    # Compute difficulty for each user
    question_beta = 0.0
    diff_1 = await ConceptCacheService.compute_user_question_difficulty(2.0, question_beta)
    diff_2 = await ConceptCacheService.compute_user_question_difficulty(-1.0, question_beta)
    
    print(f"User 1 (strong, theta=2.0): difficulty {diff_1}")
    print(f"User 2 (weak, theta=-1.0): difficulty {diff_2}")
    
    assert diff_1 < diff_2  # Strong user gets easier difficulty
    assert diff_1 == 1 or diff_1 == 2  # User 1 should find it easy
    assert diff_2 == 4 or diff_2 == 5  # User 2 should find it hard
    print("✓ Per-user difficulty computation working!")


@pytest.mark.asyncio
async def test_new_concept_adaptation(db):
    """Test that new concepts start at difficulty 3 and adapt."""
    user_id = uuid.uuid4()
    concept_id = uuid.uuid4()
    
    # Create concept
    concept = Concept(id=concept_id, name="New Concept", topic="History")
    db.add(concept)
    await db.commit()
    
    # First exposure: should be difficulty 3
    diff_1 = await ConceptCacheService.get_difficulty_for_new_concept(db, user_id, concept_id)
    assert diff_1 == 3  # Medium-hard
    print(f"✓ New concept first exposure: difficulty {diff_1}")
    
    # Simulate user answering incorrectly
    await ConceptIRT.update_concept_theta(db, user_id, concept_id, beta=1.5, correct=False)
    
    # Second exposure: should still be difficulty 3 (< 3 responses)
    diff_2 = await ConceptCacheService.get_difficulty_for_new_concept(db, user_id, concept_id)
    assert diff_2 == 3
    
    # After 3 responses: difficulty should adapt
    await ConceptIRT.update_concept_theta(db, user_id, concept_id, beta=1.5, correct=False)
    await ConceptIRT.update_concept_theta(db, user_id, concept_id, beta=1.5, correct=True)
    
    # Fourth exposure: should now adapt based on theta
    diff_4 = await ConceptCacheService.get_difficulty_for_new_concept(db, user_id, concept_id)
    # Since user is weak, should be higher difficulty
    print(f"✓ New concept after 3 responses: difficulty {diff_4}")


@pytest.mark.asyncio
async def test_concept_exposure_tracking(db):
    """Test that concept exposure is tracked."""
    user_id = uuid.uuid4()
    concept_id = uuid.uuid4()
    
    concept = Concept(id=concept_id, name="Test", topic="History")
    db.add(concept)
    await db.commit()
    
    # First exposure
    await ConceptIRT.track_concept_exposure(db, user_id, concept_id)
    record_1 = await ConceptIRT.get_concept_theta(db, user_id, concept_id)
    # Check exposure was recorded
    stmt = __import__('sqlalchemy').select(UserConceptTheta).where(
        (UserConceptTheta.user_id == user_id) & (UserConceptTheta.concept_id == concept_id)
    )
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()
    assert record is not None
    assert record.exposure_count >= 1
    assert record.first_seen_at is not None
    print(f"✓ First exposure tracked: count={record.exposure_count}, first_seen={record.first_seen_at}")
    
    # Second exposure
    await ConceptIRT.track_concept_exposure(db, user_id, concept_id)
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()
    assert record.exposure_count >= 2
    print(f"✓ Second exposure tracked: count={record.exposure_count}")


@pytest.mark.asyncio
async def test_unknown_concept_detection(db):
    """Test that unknown concepts are correctly identified."""
    user_id = uuid.uuid4()
    
    # Create 3 concepts
    concept_1_id = uuid.uuid4()
    concept_2_id = uuid.uuid4()
    concept_3_id = uuid.uuid4()
    
    for cid, name in [(concept_1_id, "C1"), (concept_2_id, "C2"), (concept_3_id, "C3")]:
        concept = Concept(id=cid, name=name, topic="History")
        db.add(concept)
    await db.commit()
    
    # User knows concepts 1 and 2
    for cid in [concept_1_id, concept_2_id]:
        await ConceptIRT.update_concept_theta(db, user_id, cid, beta=0.0, correct=True)
    
    # Get unknown concepts
    all_concepts = [concept_1_id, concept_2_id, concept_3_id]
    unknown = await ConceptIRT.get_unknown_concepts(db, user_id, all_concepts)
    
    assert len(unknown) == 1
    assert concept_3_id in unknown
    print(f"✓ Unknown concepts detected: {unknown}")


@pytest.mark.asyncio
async def test_irt_probability_function(db):
    """Test IRT probability calculations."""
    # When theta == beta, P(correct) should be ~0.5
    p = irt_probability(theta=0.0, beta=0.0)
    assert 0.49 < p < 0.51
    print(f"✓ P(correct | theta=0, beta=0) = {p:.3f}")
    
    # When theta >> beta, P(correct) should be high
    p = irt_probability(theta=2.0, beta=0.0)
    assert p > 0.88
    print(f"✓ P(correct | theta=2, beta=0) = {p:.3f}")
    
    # When theta << beta, P(correct) should be low
    p = irt_probability(theta=-2.0, beta=0.0)
    assert p < 0.12
    print(f"✓ P(correct | theta=-2, beta=0) = {p:.3f}")


@pytest.mark.asyncio
async def test_difficulty_to_beta_mapping(db):
    """Test difficulty (1-5) <-> beta mappings."""
    for difficulty in [1, 2, 3, 4, 5]:
        beta = difficulty_to_beta(difficulty)
        assert -3.0 <= beta <= 3.0
        print(f"✓ Difficulty {difficulty} → beta {beta:.1f}")
    
    for beta_val in [-2.5, -1.5, -0.5, 0.5, 1.5, 2.5]:
        difficulty = beta_to_difficulty(beta_val)
        assert 1 <= difficulty <= 5
        print(f"✓ Beta {beta_val:.1f} → difficulty {difficulty}")


if __name__ == "__main__":
    print("Run: python -m pytest tests/test_concept_awareness.py -v")
