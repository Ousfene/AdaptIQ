"""
services/concept_cache_service.py — Per-concept question caching with user-specific difficulty.

Core feature: Same question served to multiple users, but each user gets computed difficulty
based on their per-concept IRT θ.

Example:
- Question Q1 has cached difficulty_irt = 2.0 (medium)
- User A's θ for "History" = 1.5 (below avg) → served at difficulty 2 (harder for them)
- User B's θ for "History" = -0.5 (weak) → served at difficulty 3 (much harder for them)
- User C's θ for "History" = 2.5 (strong) → served at difficulty 1 (easier for them)

Caching strategy:
- Question pool: 50-100 cached questions per topic+concept
- Serving policy: weighted random selection favoring weak concepts + 20% auto-discovery
- TTL: Redis cache per (user_id, concept_id) → question_id mapping
"""

import logging
import random
from datetime import datetime, timezone
from uuid import UUID
from typing import Optional
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import redis.asyncio as aioredis

from database.models import (
    QuestionBank,
    Concept,
    QuestionConcept,
    UserConceptTheta,
)
from database.irt import (
    irt_probability,
    beta_to_difficulty,
    difficulty_to_beta,
    THETA_RANGE,
)
from database.concept_irt import ConceptIRT

logger = logging.getLogger(__name__)

# Constants
MIN_CACHE_POOL_SIZE = 3  # Minimum questions to serve from a concept
AUTO_DISCOVERY_PROBABILITY = 0.20  # 20% of questions from unknown concepts
NEW_CONCEPT_DIFFICULTY = 3  # New concepts start at difficulty 3 (medium-hard)
NEW_CONCEPT_MIN_EXPOSURE = 3  # After 3 exposures, adapt difficulty based on performance


class ConceptCacheService:
    """Intelligent question caching per concept with per-user difficulty adaptation."""

    def __init__(self, redis_client: Optional[aioredis.Redis] = None):
        self.redis = redis_client
        self.cache_ttl = 3600  # 1 hour per user-concept question cache

    @staticmethod
    async def get_or_create_concepts_for_question(
        db: AsyncSession,
        question_id: UUID,
        concept_names: list[str],
        topic: str,
    ) -> list[UUID]:
        """
        Ensure concepts exist in DB, link to question.
        Returns list of concept IDs.
        """
        concept_ids = []
        for concept_name in concept_names:
            # Try to find existing concept
            stmt = select(Concept).where(Concept.name == concept_name)
            result = await db.execute(stmt)
            concept = result.scalar_one_or_none()

            if not concept:
                # Create new concept
                concept = Concept(
                    name=concept_name,
                    topic=topic,
                    description=f"Auto-generated concept for {topic}",
                )
                db.add(concept)
                await db.flush()

            concept_ids.append(concept.id)

            # Link question to concept (if not already linked)
            stmt = select(QuestionConcept).where(
                (QuestionConcept.question_id == question_id)
                & (QuestionConcept.concept_id == concept.id)
            )
            result = await db.execute(stmt)
            existing_link = result.scalar_one_or_none()

            if not existing_link:
                qc = QuestionConcept(
                    question_id=question_id,
                    concept_id=concept.id,
                    is_primary=(concept_name == concept_names[0]),  # First concept is primary
                )
                db.add(qc)

        await db.commit()
        return concept_ids

    @staticmethod
    async def get_question_concepts(
        db: AsyncSession,
        question_id: UUID,
    ) -> list[UUID]:
        """Get all concept IDs linked to a question."""
        stmt = select(QuestionConcept.concept_id).where(
            QuestionConcept.question_id == question_id
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_user_concept_abilities(
        db: AsyncSession,
        user_id: UUID,
    ) -> dict[UUID, float]:
        """
        Get user's theta for all known concepts.
        Returns: {concept_id: theta_value}
        """
        stmt = select(UserConceptTheta).where(UserConceptTheta.user_id == user_id)
        result = await db.execute(stmt)
        records = result.scalars().all()
        return {rec.concept_id: rec.theta for rec in records}

    @staticmethod
    async def get_available_concepts_for_topic(
        db: AsyncSession,
        topic: str,
    ) -> list[UUID]:
        """Get all concept IDs for a topic."""
        stmt = select(Concept.id).where(Concept.topic == topic)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def select_concept_for_user(
        db: AsyncSession,
        user_id: UUID,
        topic: str,
    ) -> Optional[UUID]:
        """
        Select target concept for user with adaptive strategy:
        - 80% pick weak concept (inverse θ weighting) from known concepts
        - 20% pick unknown concept (auto-discovery)

        Returns concept_id or None if no concepts available.
        """
        # Get all concepts in this topic
        available = await ConceptCacheService.get_available_concepts_for_topic(db, topic)
        if not available:
            logger.warning(f"No concepts found for topic {topic}")
            return None

        # Get user's known concepts
        user_thetas = await ConceptCacheService.get_user_concept_abilities(db, user_id)
        known_concepts = [cid for cid in available if cid in user_thetas]
        unknown_concepts = [cid for cid in available if cid not in user_thetas]

        # Strategy: 80% known (weak areas), 20% unknown (discovery)
        if unknown_concepts and random.random() < AUTO_DISCOVERY_PROBABILITY:
            return random.choice(unknown_concepts)

        if not known_concepts:
            # No known concepts: pick random unknown
            return random.choice(unknown_concepts) if unknown_concepts else None

        # Pick weak concept (lowest theta) with probability weighting
        # Weak concepts (low θ) get higher selection probability
        thetas = [(cid, user_thetas.get(cid, 0.0)) for cid in known_concepts]
        # Invert theta: lower theta = higher weight
        # Weight = (max_theta - current_theta) normalized
        max_theta = max([t for _, t in thetas]) if thetas else 0.0
        min_theta = min([t for _, t in thetas]) if thetas else 0.0
        range_theta = max(max_theta - min_theta, 0.1)  # Avoid division by zero

        weights = [(max_theta - t) / range_theta for _, t in thetas]
        total_weight = sum(weights)
        if total_weight <= 0:
            return random.choice(known_concepts)

        # Weighted random selection
        normalized_weights = [w / total_weight for w in weights]
        return random.choices(known_concepts, weights=normalized_weights, k=1)[0]

    @staticmethod
    async def get_cached_questions_for_concept(
        db: AsyncSession,
        concept_id: UUID,
        limit: int = 20,
    ) -> list[UUID]:
        """
        Get question IDs linked to a concept (cache pool).
        Priority: most recently served questions.
        """
        stmt = (
            select(QuestionBank.id)
            .join(QuestionConcept)
            .where(QuestionConcept.concept_id == concept_id)
            .order_by(QuestionBank.last_served_at.desc().nulls_last())
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def compute_user_question_difficulty(
        user_theta: float,
        question_beta: float,
    ) -> int:
        """
        Compute effective difficulty for user based on their θ vs question β.

        Map: IRT β → difficulty (1-5 scale)
        - User's expected P(correct) = irt_probability(user_theta, question_beta)
        - If P > 0.8 → difficulty 1 (very easy for this user)
        - If 0.6 < P ≤ 0.8 → difficulty 2 (easy)
        - If 0.4 < P ≤ 0.6 → difficulty 3 (medium)
        - If 0.2 < P ≤ 0.4 → difficulty 4 (hard)
        - If P ≤ 0.2 → difficulty 5 (very hard)
        """
        p_correct = irt_probability(user_theta, question_beta)

        if p_correct > 0.8:
            return 1
        elif p_correct > 0.6:
            return 2
        elif p_correct > 0.4:
            return 3
        elif p_correct > 0.2:
            return 4
        else:
            return 5

    @staticmethod
    async def get_difficulty_for_new_concept(
        db: AsyncSession,
        user_id: UUID,
        concept_id: UUID,
    ) -> int:
        """
        Get appropriate difficulty for new concept.

        Rules:
        - First 3 exposures: difficulty 3 (medium-hard, balanced learning)
        - After 3 exposures: adapt based on performance in UserConceptTheta.response_count
          - If response_count < 3: still learning → difficulty 3
          - If response_count >= 3: adapt based on θ (same logic as known concept)
        """
        stmt = select(UserConceptTheta).where(
            (UserConceptTheta.user_id == user_id)
            & (UserConceptTheta.concept_id == concept_id)
        )
        result = await db.execute(stmt)
        record = result.scalar_one_or_none()

        if not record or record.response_count < NEW_CONCEPT_MIN_EXPOSURE:
            return NEW_CONCEPT_DIFFICULTY  # Start at difficulty 3

        # Adapt based on user's theta for this concept
        user_theta = record.theta
        # Map NEW_CONCEPT_DIFFICULTY to β
        target_beta = difficulty_to_beta(NEW_CONCEPT_DIFFICULTY)
        adjusted_difficulty = await ConceptCacheService.compute_user_question_difficulty(
            user_theta, target_beta
        )
        return adjusted_difficulty

    @staticmethod
    async def select_and_serve_question(
        db: AsyncSession,
        redis_client: Optional[aioredis.Redis],
        user_id: UUID,
        topic: str,
    ) -> Optional[dict]:
        """
        Main entry point: Select concept → pick question → compute difficulty.

        Returns dict with:
        {
            'question_id': UUID,
            'question_text': str,
            'options': list[str],
            'difficulty': int (1-5, user-specific),
            'concept_id': UUID,
            'original_difficulty': int (question's stored difficulty),
        }
        or None if no questions available.
        """
        # Step 1: Select concept
        concept_id = await ConceptCacheService.select_concept_for_user(db, user_id, topic)
        if not concept_id:
            logger.warning(f"No concepts available for topic {topic}")
            return None

        # Step 2: Get cached questions for concept
        question_ids = await ConceptCacheService.get_cached_questions_for_concept(
            db, concept_id, limit=20
        )
        if not question_ids:
            logger.warning(f"No cached questions for concept {concept_id}")
            return None

        # Step 3: Pick random question from pool
        question_id = random.choice(question_ids)
        stmt = select(QuestionBank).where(QuestionBank.id == question_id)
        result = await db.execute(stmt)
        question = result.scalar_one_or_none()

        if not question:
            logger.warning(f"Question {question_id} not found")
            return None

        # Step 4: Get user's theta for this concept
        user_theta = await ConceptIRT.get_concept_theta(db, user_id, concept_id)

        # Step 5: Compute user-specific difficulty
        user_difficulty = await ConceptCacheService.compute_user_question_difficulty(
            user_theta, question.difficulty_irt
        )

        # If new concept (θ=0 and response_count < 3), apply special logic
        stmt = select(UserConceptTheta).where(
            (UserConceptTheta.user_id == user_id)
            & (UserConceptTheta.concept_id == concept_id)
        )
        result = await db.execute(stmt)
        theta_record = result.scalar_one_or_none()

        if theta_record and theta_record.response_count < NEW_CONCEPT_MIN_EXPOSURE:
            # First time seeing this concept (or very new)
            user_difficulty = await ConceptCacheService.get_difficulty_for_new_concept(
                db, user_id, concept_id
            )

        # Step 6: Track exposure
        await ConceptIRT.track_concept_exposure(db, user_id, concept_id)

        # Step 7: Update last_served_at for question
        question.last_served_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await db.commit()

        # Parse options from JSON
        try:
            options = json.loads(question.options_json)
        except Exception:
            options = []

        return {
            "question_id": str(question_id),
            "question_text": question.question_text,
            "options": options,
            "difficulty": user_difficulty,
            "concept_id": str(concept_id),
            "original_difficulty": beta_to_difficulty(question.difficulty_irt),
        }

    @staticmethod
    def cache_key(user_id: UUID, concept_id: UUID, question_id: UUID) -> str:
        """Redis cache key for question context."""
        return f"question:cache:{user_id}:{concept_id}:{question_id}"

    async def cache_question_context(
        self,
        user_id: UUID,
        concept_id: UUID,
        question_id: UUID,
        difficulty: int,
    ) -> None:
        """Store computed difficulty in Redis cache for idempotency."""
        if not self.redis:
            return

        key = self.cache_key(user_id, concept_id, question_id)
        data = json.dumps({"difficulty": difficulty})
        await self.redis.setex(key, self.cache_ttl, data)

    async def get_cached_question_context(
        self,
        user_id: UUID,
        concept_id: UUID,
        question_id: UUID,
    ) -> Optional[int]:
        """Retrieve cached difficulty. Returns None if cache miss."""
        if not self.redis:
            return None

        key = self.cache_key(user_id, concept_id, question_id)
        data = await self.redis.get(key)
        if not data:
            return None

        try:
            return json.loads(data)["difficulty"]
        except Exception:
            return None
