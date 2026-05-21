"""
database/concept_irt.py — Per-concept IRT theta tracking.

Extends the global IRT system to track user ability per-concept instead of globally.
Enables adaptive learning that recognizes specific knowledge strengths and weaknesses.

Same 1PL IRT model as global system, but applied at concept level:
    P(correct | θ_concept, β) = 1 / (1 + exp(-(θ_concept - β)))

where θ_concept is the user's ability in a specific knowledge domain.
"""

from __future__ import annotations
import logging
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update as sqlalchemy_update, func

from database.models import UserConceptTheta, Concept
from database.irt import (
    irt_probability,
    update_theta,
    THETA_RANGE,
    LEARN_RATE,
)

logger = logging.getLogger(__name__)

# Variance decay: each new response reduces uncertainty slightly
# With n responses, variance = 1.0 * (0.95 ** n)
# After 10 responses, variance ≈ 0.60 (still learning)
# After 50 responses, variance ≈ 0.08 (confident estimate)
VARIANCE_DECAY_FACTOR = 0.95

# Warm-up period: don't trust theta estimates until user has answered enough questions
# Prevents marking a concept as "easy" after just 2 lucky guesses
MIN_RESPONSES_FOR_CONFIDENCE = 5


class ConceptThetaResult:
    """Result of fetching user's concept theta with confidence info."""
    __slots__ = ('theta', 'response_count', 'variance', 'is_confident')
    
    def __init__(self, theta: float, response_count: int, variance: float):
        self.theta = theta
        self.response_count = response_count
        self.variance = variance
        self.is_confident = response_count >= MIN_RESPONSES_FOR_CONFIDENCE


class ConceptIRT:
    """Per-concept IRT theta updates and retrieval."""

    @staticmethod
    async def update_concept_theta(
        db: AsyncSession,
        user_id: UUID,
        concept_id: UUID,
        beta: float,  # Question difficulty
        correct: bool,
    ) -> float:
        """
        Update user's theta for a specific concept using IRT.

        Returns the new theta value.
        """
        # Get or create theta record
        stmt = select(UserConceptTheta).where(
            (UserConceptTheta.user_id == user_id)
            & (UserConceptTheta.concept_id == concept_id)
        )
        result = await db.execute(stmt)
        theta_record = result.scalar_one_or_none()

        if not theta_record:
            # Create new concept theta for this user
            theta_record = UserConceptTheta(
                user_id=user_id,
                concept_id=concept_id,
                theta=0.0,
                theta_variance=1.0,
                response_count=0,
            )
            db.add(theta_record)
            await db.flush()

        # IRT update: δθ = α * (response - P(correct))
        p = irt_probability(theta_record.theta, beta)
        gradient = (1 if correct else 0) - p
        new_theta = theta_record.theta + LEARN_RATE * gradient
        new_theta = max(THETA_RANGE[0], min(THETA_RANGE[1], new_theta))

        # Uncertainty decays as more responses collected
        new_variance = theta_record.theta_variance * VARIANCE_DECAY_FACTOR

        # Update record in memory (for return value calculation only)
        theta_record.theta = new_theta
        theta_record.theta_variance = new_variance
        # NOTE: Do NOT increment response_count here - the SQL statement below does it atomically

        # Use sqlalchemy update for atomic operation
        # CRITICAL: Use SQL expression for response_count to avoid race condition
        stmt = (
            sqlalchemy_update(UserConceptTheta)
            .where(
                (UserConceptTheta.user_id == user_id)
                & (UserConceptTheta.concept_id == concept_id)
            )
            .values(
                theta=new_theta,
                theta_variance=new_variance,
                response_count=UserConceptTheta.response_count + 1,  # Atomic increment
                last_updated=datetime.now(timezone.utc).replace(tzinfo=None),  # CRITICAL FIX 4.1
            )
        )
        await db.execute(stmt)
        await db.flush()

        return new_theta

    @staticmethod
    async def get_concept_theta(
        db: AsyncSession,
        user_id: UUID,
        concept_id: UUID,
    ) -> float:
        """Fetch user's current theta for a concept (or 0.0 if not tracked yet)."""
        stmt = select(UserConceptTheta).where(
            (UserConceptTheta.user_id == user_id)
            & (UserConceptTheta.concept_id == concept_id)
        )
        result = await db.execute(stmt)
        record = result.scalar_one_or_none()
        return record.theta if record else 0.0

    @staticmethod
    async def get_concept_theta_with_confidence(
        db: AsyncSession,
        user_id: UUID,
        concept_id: UUID,
    ) -> ConceptThetaResult:
        """
        Fetch user's concept theta WITH confidence information.
        
        Returns ConceptThetaResult with:
        - theta: current ability estimate
        - response_count: how many answers contributed
        - variance: uncertainty (lower = more confident)
        - is_confident: True if response_count >= MIN_RESPONSES_FOR_CONFIDENCE
        
        Use is_confident to decide whether to trust the theta for difficulty selection.
        If not confident, use wider difficulty range to gather more data.
        """
        stmt = select(UserConceptTheta).where(
            (UserConceptTheta.user_id == user_id)
            & (UserConceptTheta.concept_id == concept_id)
        )
        result = await db.execute(stmt)
        record = result.scalar_one_or_none()
        
        if record:
            return ConceptThetaResult(
                theta=record.theta,
                response_count=record.response_count,
                variance=record.theta_variance,
            )
        else:
            # New concept: no data, not confident
            return ConceptThetaResult(theta=0.0, response_count=0, variance=1.0)

    @staticmethod
    async def get_concept_thetas(
        db: AsyncSession,
        user_id: UUID,
        concept_ids: list[UUID],
    ) -> dict[UUID, float]:
        """Fetch multiple concept thetas for a user in one query."""
        if not concept_ids:
            return {}

        stmt = select(UserConceptTheta).where(
            (UserConceptTheta.user_id == user_id)
            & (UserConceptTheta.concept_id.in_(concept_ids))
        )
        result = await db.execute(stmt)
        records = result.scalars().all()

        # Build dict: concept_id → theta
        theta_map = {record.concept_id: record.theta for record in records}

        # Fill missing concepts with default theta=0.0
        return {cid: theta_map.get(cid, 0.0) for cid in concept_ids}

    @staticmethod
    async def get_weakest_concept_theta(
        db: AsyncSession,
        user_id: UUID,
        concept_ids: list[UUID],
    ) -> float:
        """
        Get the WEAKEST (lowest) concept theta from a list.
        Used for zone of proximal development: focus learning on gaps.

        Returns 0.0 if no concepts found (unfamiliar domain).
        """
        if not concept_ids:
            return 0.0

        thetas = await ConceptIRT.get_concept_thetas(db, user_id, concept_ids)
        return min(thetas.values()) if thetas else 0.0

    @staticmethod
    async def get_average_concept_theta(
        db: AsyncSession,
        user_id: UUID,
        concept_ids: list[UUID],
    ) -> float:
        """Get average theta across multiple concepts."""
        if not concept_ids:
            return 0.0

        thetas = await ConceptIRT.get_concept_thetas(db, user_id, concept_ids)
        values = list(thetas.values())
        return sum(values) / len(values) if values else 0.0

    @staticmethod
    async def get_user_concept_count(
        db: AsyncSession,
        user_id: UUID,
    ) -> int:
        """Count how many unique concepts user has encountered."""
        stmt = select(func.count(UserConceptTheta.concept_id)).where(
            UserConceptTheta.user_id == user_id
        )
        result = await db.execute(stmt)
        count = result.scalar()
        return count or 0

    @staticmethod
    async def get_unknown_concepts(
        db: AsyncSession,
        user_id: UUID,
        potential_concept_ids: list[UUID],
    ) -> list[UUID]:
        """
        Return concepts from the list that the user has NOT encountered yet.
        Used for auto-discovery.
        """
        if not potential_concept_ids:
            return []

        stmt = select(UserConceptTheta.concept_id).where(
            (UserConceptTheta.user_id == user_id)
            & (UserConceptTheta.concept_id.in_(potential_concept_ids))
        )
        result = await db.execute(stmt)
        known_ids = set(result.scalars().all())

        # Return concepts NOT in known set
        return [cid for cid in potential_concept_ids if cid not in known_ids]

    @staticmethod
    async def track_concept_exposure(
        db: AsyncSession,
        user_id: UUID,
        concept_id: UUID,
    ) -> None:
        """
        Increment exposure_count for a concept.
        Set first_seen_at if this is the user's first time seeing it.
        """
        stmt = select(UserConceptTheta).where(
            (UserConceptTheta.user_id == user_id)
            & (UserConceptTheta.concept_id == concept_id)
        )
        result = await db.execute(stmt)
        theta_record = result.scalar_one_or_none()

        if not theta_record:
            # First exposure: create new record with first_seen_at set
            from datetime import timezone
            theta_record = UserConceptTheta(
                user_id=user_id,
                concept_id=concept_id,
                theta=0.0,  # Start neutral
                theta_variance=1.0,  # High uncertainty
                response_count=0,
                exposure_count=1,
                first_seen_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            db.add(theta_record)
            await db.flush()
        else:
            # Increment exposure counter
            stmt = (
                sqlalchemy_update(UserConceptTheta)
                .where(
                    (UserConceptTheta.user_id == user_id)
                    & (UserConceptTheta.concept_id == concept_id)
                )
                .values(exposure_count=UserConceptTheta.exposure_count + 1)
            )
            await db.execute(stmt)
            await db.flush()
