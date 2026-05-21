"""
scripts/decay_theta.py — Theta decay for inactive users.

Run daily via cron or manually:
    python scripts/decay_theta.py

For users inactive > 14 days:
    - theta = theta * 0.95 (slight regression toward mean)
    - n_responses = max(0, n_responses - 1) (reduce confidence)

This prevents stale ability estimates from persisting indefinitely.
"""
import asyncio
import logging
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, update as sqlalchemy_update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import UserConceptTheta
from dependencies import get_async_session_context


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# Configuration
DECAY_FACTOR = 0.95  # Multiply theta by this factor
INACTIVE_DAYS = 14   # Consider user inactive after this many days
MIN_RESPONSE_DECAY = 1  # Reduce response_count by this amount


async def decay_inactive_thetas():
    """
    Apply decay to all user_concept_theta records where last_updated > 14 days ago.
    """
    cutoff = utc_now() - timedelta(days=INACTIVE_DAYS)
    
    logger.info(f"Starting theta decay for users inactive since {cutoff.isoformat()}")
    
    affected_count = 0
    
    async with get_async_session_context() as db:
        # Find all theta records with last_updated before cutoff
        stmt = select(UserConceptTheta).where(
            UserConceptTheta.last_updated < cutoff
        )
        result = await db.execute(stmt)
        stale_records = result.scalars().all()
        
        for record in stale_records:
            old_theta = record.theta
            old_responses = record.response_count
            
            # Apply decay
            new_theta = old_theta * DECAY_FACTOR
            new_responses = max(0, old_responses - MIN_RESPONSE_DECAY)
            
            # Update the record
            update_stmt = (
                sqlalchemy_update(UserConceptTheta)
                .where(UserConceptTheta.id == record.id)
                .values(
                    theta=new_theta,
                    response_count=new_responses,
                    last_updated=utc_now(),  # Mark as touched
                )
            )
            await db.execute(update_stmt)
            
            logger.info(
                f"Decayed theta for user {record.user_id}, concept {record.concept_id}: "
                f"theta {old_theta:.3f} → {new_theta:.3f}, "
                f"responses {old_responses} → {new_responses}"
            )
            
            affected_count += 1
        
        await db.commit()
    
    logger.info(f"Theta decay complete. {affected_count} records updated.")
    return affected_count


async def main():
    logger.info("=" * 60)
    logger.info("AdaptIQ Theta Decay Script")
    logger.info("=" * 60)
    
    affected = await decay_inactive_thetas()
    
    logger.info("=" * 60)
    logger.info(f"Done. {affected} theta records decayed.")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
