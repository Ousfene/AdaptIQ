"""
services/decay_service.py — Inactivity decay for user concept theta.

Users who haven't played for a while should have their theta estimates
decay toward 0 (neutral) to account for knowledge decay over time.

This prevents the system from assuming users retain all knowledge indefinitely.
"""
import logging
from datetime import datetime, timezone, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update as sqlalchemy_update

from database.models import UserConceptTheta
from config import INACTIVITY_DECAY_DAYS, INACTIVITY_DECAY_FACTOR

logger = logging.getLogger(__name__)

# Theta bounds (same as IRT module)
THETA_MIN = -3.0
THETA_MAX = 3.0


def utc_now_naive() -> datetime:
    """Get current UTC time without timezone info (for DB compatibility)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def apply_inactivity_decay(db: AsyncSession, user_id: UUID) -> int:
    """
    Apply inactivity decay to user's concept theta estimates.
    
    For each concept where last_updated is older than INACTIVITY_DECAY_DAYS:
    1. Calculate how many decay periods have passed
    2. Decay theta toward 0 by DECAY_FACTOR per period
    3. Increase variance (uncertainty) slightly
    4. Update last_updated to now
    
    Args:
        db: Database session
        user_id: User to decay
        
    Returns:
        Number of concepts that were decayed
        
    Example:
        If theta=2.0, decay_factor=0.1, and 2 periods passed:
        new_theta = 2.0 * (1 - 0.1)^2 = 2.0 * 0.81 = 1.62
        
    This ensures users who return after a break aren't thrown into
    content that's too difficult based on stale ability estimates.
    """
    cutoff = utc_now_naive() - timedelta(days=INACTIVITY_DECAY_DAYS)
    
    # Find concepts not updated since cutoff
    stmt = select(UserConceptTheta).where(
        (UserConceptTheta.user_id == user_id) &
        (UserConceptTheta.last_updated < cutoff)
    )
    result = await db.execute(stmt)
    stale_concepts = result.scalars().all()
    
    if not stale_concepts:
        return 0
    
    decayed_count = 0
    now = utc_now_naive()
    
    # ═══════ IRT-6 FIX: Calculate decay once, store results ═══════
    # Pre-calculate all decay values to avoid duplicate computation
    decay_updates = []  # List of (uct_id, new_theta, new_variance) tuples
    
    for uct in stale_concepts:
        # Calculate decay periods (how many 2-week periods since last update)
        days_inactive = (now - uct.last_updated).days
        decay_periods = days_inactive // INACTIVITY_DECAY_DAYS
        
        if decay_periods < 1:
            continue
        
        # Decay theta toward 0
        # Formula: new_theta = old_theta * (1 - decay_factor)^periods
        decay_multiplier = (1 - INACTIVITY_DECAY_FACTOR) ** decay_periods
        new_theta = uct.theta * decay_multiplier
        
        # Clamp to valid range
        new_theta = max(THETA_MIN, min(THETA_MAX, new_theta))
        
        # Increase variance (uncertainty) - we're less confident after inactivity
        # Cap at 1.0 (maximum uncertainty)
        new_variance = min(1.0, uct.theta_variance + 0.1 * decay_periods)
        
        # Store calculated values for later update
        decay_updates.append((uct.id, new_theta, new_variance))
        
        logger.info(
            "decay_applied",
            extra={
                "user_id": str(user_id),
                "concept_id": str(uct.concept_id),
                "days_inactive": days_inactive,
                "decay_periods": decay_periods,
                "old_theta": round(uct.theta, 3),
                "new_theta": round(new_theta, 3),
                "old_variance": round(uct.theta_variance, 3),
                "new_variance": round(new_variance, 3),
            }
        )
        
        decayed_count += 1
    
    # Apply all updates in batch
    if decay_updates:
        for uct_id, new_theta, new_variance in decay_updates:
            stmt = (
                sqlalchemy_update(UserConceptTheta)
                .where(UserConceptTheta.id == uct_id)
                .values(
                    theta=new_theta,
                    theta_variance=new_variance,
                    last_updated=now,
                )
            )
            await db.execute(stmt)
        
        await db.flush()
        logger.info(
            "inactivity_decay_complete",
            extra={
                "user_id": str(user_id),
                "concepts_decayed": decayed_count,
            }
        )
    # ═════════════════════════════════════════════════════════════
    
    return decayed_count


async def get_decay_status(db: AsyncSession, user_id: UUID) -> dict:
    """
    Get decay status for a user (for debugging/admin).
    
    Returns dict with:
    - total_concepts: Number of concepts user has theta for
    - stale_concepts: Number that would be decayed
    - oldest_update: Oldest last_updated date
    """
    # Get all concepts for user
    stmt = select(UserConceptTheta).where(UserConceptTheta.user_id == user_id)
    result = await db.execute(stmt)
    all_concepts = result.scalars().all()
    
    if not all_concepts:
        return {
            "total_concepts": 0,
            "stale_concepts": 0,
            "oldest_update": None,
        }
    
    cutoff = utc_now_naive() - timedelta(days=INACTIVITY_DECAY_DAYS)
    stale = [c for c in all_concepts if c.last_updated < cutoff]
    oldest = min(c.last_updated for c in all_concepts)
    
    return {
        "total_concepts": len(all_concepts),
        "stale_concepts": len(stale),
        "oldest_update": oldest.isoformat() if oldest else None,
        "decay_threshold_days": INACTIVITY_DECAY_DAYS,
    }
