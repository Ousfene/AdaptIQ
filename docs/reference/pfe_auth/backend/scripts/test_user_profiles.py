"""
backend/scripts/test_user_profiles.py — Create and execute test profiles for comprehensive evaluation.

This script:
1. Creates 5 test users with different knowledge profiles
2. Initiates classic room sessions for each
3. Logs all interactions to JSON and database
4. Tracks theta changes and session progression
5. Generates test report

Run: python scripts/test_user_profiles.py
"""

import asyncio
import uuid
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.models import User
from dependencies import get_async_session_context
from auth.core.security import hash_password
from services.log_aggregator import get_aggregator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test profile configurations
TEST_PROFILES = {
    "novice_reader": {
        "description": "Beginner in all topics",
        "email": "novice_reader_test@example.com",
        "username": f"novice_reader_{int(datetime.now(timezone.utc).timestamp())}",
        "password": "TestPass123!@#",
        "initial_theta": -2.0,
        "topics": ["geography", "history"],
    },
    "geo_expert": {
        "description": "Expert in geography, novice in history",
        "email": "geo_expert_test@example.com",
        "username": f"geo_expert_{int(datetime.now(timezone.utc).timestamp())}",
        "password": "TestPass123!@#",
        "initial_theta": 2.0,  # Geography
        "topics": ["geography", "history"],
    },
    "hist_expert": {
        "description": "Expert in history, novice in geography",
        "email": "hist_expert_test@example.com",
        "username": f"hist_expert_{int(datetime.now(timezone.utc).timestamp())}",
        "password": "TestPass123!@#",
        "initial_theta": 2.0,  # History
        "topics": ["history", "geography"],
    },
    "balanced": {
        "description": "Intermediate in both topics",
        "email": "balanced_test@example.com",
        "username": f"balanced_{int(datetime.now(timezone.utc).timestamp())}",
        "password": "TestPass123!@#",
        "initial_theta": 0.0,
        "topics": ["geography", "history"],
    },
    "challenger": {
        "description": "For challenge room focus testing",
        "email": "challenger_test@example.com",
        "username": f"challenger_{int(datetime.now(timezone.utc).timestamp())}",
        "password": "TestPass123!@#",
        "initial_theta": 1.0,
        "topics": ["mixed"],
    },
}


async def create_test_user(
    db: AsyncSession,
    profile_name: str,
    profile_config: dict,
) -> User | None:
    """Create a test user with the given profile configuration."""
    try:
        # Check if user already exists
        stmt = select(User).where(User.email == profile_config["email"])
        existing = await db.execute(stmt)
        if existing.scalar_one_or_none():
            logger.info(f"User {profile_name} already exists, skipping creation")
            return existing.scalar_one()

        # Create new user
        user = User(
            id=uuid.uuid4(),
            email=profile_config["email"],
            username=profile_config["username"],
            password_hash=hash_password(profile_config["password"]),
            elo_global=0.0,
            is_active=True,
            is_admin=False,
        )

        db.add(user)
        await db.flush()
        await db.commit()

        logger.info(f"✅ Created test user: {profile_name} ({profile_config['username']})")

        # Log to aggregator
        aggregator = get_aggregator()
        aggregator.log_event(
            event_type="test_user_created",
            category="testing",
            data={
                "profile": profile_name,
                "description": profile_config["description"],
                "username": profile_config["username"],
                "initial_theta": profile_config.get("initial_theta", 0.0),
                "topics": profile_config["topics"],
            },
            user_id=user.id,
        )

        return user

    except Exception as e:
        logger.error(f"❌ Failed to create user {profile_name}: {e}")
        return None


async def main():
    """Create test users and prepare for testing."""
    logger.info("=" * 60)
    logger.info("AdaptIQ Comprehensive Testing - Phase 2: Test Profile Creation")
    logger.info("=" * 60)

    aggregator = get_aggregator()

    try:
        async with get_async_session_context() as db:
            logger.info("\nCreating test user profiles...")
            logger.info("-" * 60)

            created_users = {}
            for profile_name, profile_config in TEST_PROFILES.items():
                user = await create_test_user(db, profile_name, profile_config)
                if user:
                    created_users[profile_name] = user

            logger.info(f"\n✅ Created {len(created_users)} test profiles")
            logger.info("-" * 60)

            # Export logs
            log_file = aggregator.export_session_logs("test_profiles_created")
            logger.info(f"\n📊 Logs exported to: {log_file}")

            # Print summary
            logger.info("\n" + "=" * 60)
            logger.info("Test Profile Summary")
            logger.info("=" * 60)
            for profile_name, user in created_users.items():
                config = TEST_PROFILES[profile_name]
                logger.info(f"\n{profile_name.upper()}")
                logger.info(f"  Description: {config['description']}")
                logger.info(f"  Username: {config['username']}")
                logger.info(f"  Email: {config['email']}")
                logger.info(f"  User ID: {user.id}")
                logger.info(f"  Topics: {', '.join(config['topics'])}")

            logger.info("\n" + "=" * 60)
            logger.info("✅ Phase 2 Complete: Test users created and ready for testing")
            logger.info("=" * 60)
            logger.info("\nNext steps:")
            logger.info("1. Start backend: python main.py")
            logger.info("2. Start frontend: npm run dev")
            logger.info("3. Run comprehensive page tests with each profile")
            logger.info("4. Monitor logs in backend/logs/ directory")

    except Exception as e:
        logger.error(f"❌ Error in test user creation: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
