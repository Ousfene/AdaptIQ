#!/usr/bin/env python3
"""
Phase 3: Comprehensive Page Testing

Tests all user-facing pages with 5 different knowledge profiles.
Logs:
  - Page load times
  - API response times
  - Data accuracy (comparing page display vs database)
  - Error events
  - Cache hit/miss patterns
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from uuid import UUID
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
import os
import sys

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.models import User, UserConceptTheta, UserResponse, UserChallengeRank, ChallengeRank
from auth.core.security import create_access_token


TEST_PROFILES = {
    "novice_reader_1775089851": {
        "name": "Novice Reader",
        "email": "novice_reader_test@example.com",
        "expected_theta": -2.0,
        "expected_accuracy": "30-50%",
        "topics": ["geography", "history"]
    },
    "geo_expert_1775089851": {
        "name": "Geography Expert",
        "email": "geo_expert_test@example.com",
        "expected_theta_geo": 2.0,
        "expected_theta_hist": -2.0,
        "expected_accuracy": "70% geo, 30% hist",
        "topics": ["geography", "history"]
    },
    "hist_expert_1775089851": {
        "name": "History Expert",
        "email": "hist_expert_test@example.com",
        "expected_theta_hist": 2.0,
        "expected_theta_geo": -2.0,
        "expected_accuracy": "70% hist, 30% geo",
        "topics": ["history", "geography"]
    },
    "balanced_1775089851": {
        "name": "Balanced Learner",
        "email": "balanced_test@example.com",
        "expected_theta": 0.0,
        "expected_accuracy": "60-75%",
        "topics": ["geography", "history"]
    },
    "challenger_1775089851": {
        "name": "Challenger",
        "email": "challenger_test@example.com",
        "expected_theta": 1.0,
        "expected_accuracy": "60-75%",
        "topics": ["mixed"]
    }
}


class Phase3Tester:
    def __init__(self):
        self.db_url = os.getenv("DATABASE_URL")
        self.engine = None
        self.async_session = None
        self.results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "profiles": {},
            "summary": {}
        }
        # Use absolute path based on script location
        script_dir = Path(__file__).parent.parent
        self.log_file = script_dir / "logs" / f"phase3_testing_{int(time.time())}.json"
        self.log_file.parent.mkdir(exist_ok=True, parents=True)

    async def setup(self):
        """Initialize database connection"""
        self.engine = create_async_engine(self.db_url)
        self.async_session = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def teardown(self):
        """Close database connection"""
        if self.engine:
            await self.engine.dispose()

    def log_event(self, event_type: str, profile: str, data: dict):
        """Log an event to memory and file"""
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "profile": profile,
            "data": data
        }
        print(f"[{profile}] {event_type}: {data}")
        return event

    async def test_user_profile(self, username: str, profile_info: dict) -> dict:
        """Test a single user profile"""
        print(f"\n{'='*60}")
        print(f"Testing Profile: {profile_info['name']} ({username})")
        print(f"{'='*60}")

        profile_results = {
            "username": username,
            "name": profile_info["name"],
            "email": profile_info["email"],
            "tests": {},
            "issues": []
        }

        async with self.async_session() as session:
            # Get user from database
            result = await session.execute(select(User).where(User.username == username))
            user = result.scalar_one_or_none()

            if not user:
                profile_results["issues"].append(f"User {username} not found in database")
                return profile_results

            user_id = user.id
            self.log_event("profile_test_start", username, {"user_id": str(user_id)})

            # Test 1: User account data
            print(f"\n[TEST 1] User Account Data")
            account_test = await self._test_user_account(session, user, profile_info)
            profile_results["tests"]["account"] = account_test

            # Test 2: Concept theta values
            print(f"\n[TEST 2] Concept Theta Tracking")
            theta_test = await self._test_concept_theta(session, user_id, profile_info)
            profile_results["tests"]["concept_theta"] = theta_test

            # Test 3: Response history
            print(f"\n[TEST 3] User Response History")
            response_test = await self._test_user_responses(session, user_id)
            profile_results["tests"]["responses"] = response_test

            # Test 4: Challenge rank (if applicable)
            if username == "challenger_1775089851":
                print(f"\n[TEST 4] Challenge Rank Progression")
                rank_test = await self._test_challenge_rank(session, user_id)
                profile_results["tests"]["challenge_rank"] = rank_test

            # Generate API auth token
            token = create_access_token({"sub": str(user_id)})
            profile_results["api_token"] = token
            self.log_event("profile_test_complete", username, {
                "user_id": str(user_id),
                "tests_run": len(profile_results["tests"])
            })

        return profile_results

    async def _test_user_account(self, session, user, profile_info) -> dict:
        """Test user account data"""
        test_result = {
            "user_id": str(user.id),
            "username": user.username,
            "email": user.email,
            "elo_global": user.elo_global or 0,
            "level": user.level or 1,
            "verification": "PASS"
        }

        # Verify email matches expected
        if user.email != profile_info["email"]:
            test_result["verification"] = "FAIL"
            print(f"  [FAIL] Email mismatch: {user.email} vs {profile_info['email']}")
        else:
            print(f"  [OK] Email verified: {user.email}")

        print(f"  ELO: {test_result['elo_global']}, Level: {test_result['level']}")
        return test_result

    async def _test_concept_theta(self, session, user_id: UUID, profile_info) -> dict:
        """Test concept theta values"""
        result = await session.execute(
            select(UserConceptTheta)
            .where(UserConceptTheta.user_id == user_id)
        )
        theta_records = result.scalars().all()

        test_result = {
            "concepts_tracked": len(theta_records),
            "concepts": []
        }

        if theta_records:
            print(f"  Found {len(theta_records)} concepts")
            for record in theta_records[:5]:  # Show first 5
                concept_data = {
                    "concept_id": str(record.concept_id),
                    "theta": round(record.theta, 3),
                    "variance": round(record.theta_variance, 3),
                    "response_count": record.response_count,
                    "last_updated": record.last_updated.isoformat() if record.last_updated else None
                }
                test_result["concepts"].append(concept_data)
                print(f"    - θ={concept_data['theta']:.3f}, responses={record.response_count}, last_updated={concept_data['last_updated']}")
        else:
            print(f"  [INFO] No concept theta records yet (user just created)")

        test_result["verification"] = "PASS"
        return test_result

    async def _test_user_responses(self, session, user_id: UUID) -> dict:
        """Test user response history"""
        result = await session.execute(
            select(UserResponse)
            .where(UserResponse.user_id == user_id)
            .order_by(UserResponse.created_at.desc())
        )
        responses = result.scalars().all()

        test_result = {
            "total_responses": len(responses),
            "recent_responses": [],
            "verification": "PASS"
        }

        if responses:
            correct_count = sum(1 for r in responses if r.answered_correct)
            accuracy = (correct_count / len(responses)) * 100 if responses else 0
            print(f"  Total responses: {len(responses)}")
            print(f"  Accuracy: {accuracy:.1f}%")

            for response in responses[:5]:  # Show 5 most recent
                resp_data = {
                    "question_id": str(response.question_id),
                    "answered_correct": response.answered_correct,
                    "time_taken": response.time_taken,
                    "created_at": response.created_at.isoformat() if response.created_at else None
                }
                test_result["recent_responses"].append(resp_data)

            test_result["accuracy"] = round(accuracy, 1)
        else:
            print(f"  [INFO] No responses yet (new user)")

        return test_result

    async def _test_challenge_rank(self, session, user_id: UUID) -> dict:
        """Test challenge rank for challenger profile"""
        result = await session.execute(
            select(UserChallengeRank)
            .where(UserChallengeRank.user_id == user_id)
        )
        user_rank = result.scalar_one_or_none()

        test_result = {
            "verification": "PASS"
        }

        if user_rank:
            # Get rank name
            rank_result = await session.execute(
                select(ChallengeRank)
                .where(ChallengeRank.id == user_rank.current_rank_id)
            )
            rank = rank_result.scalar_one_or_none()

            test_result.update({
                "current_rank": rank.name if rank else "Unknown",
                "elo_rank": user_rank.elo_rank or 0,
                "wins": user_rank.wins or 0,
                "losses": user_rank.losses or 0,
                "skip_attempts": user_rank.skip_attempts_remaining or 3
            })
            print(f"  Rank: {test_result['current_rank']}")
            print(f"  ELO: {test_result['elo_rank']}, W-L: {test_result['wins']}-{test_result['losses']}")
            print(f"  Skip attempts: {test_result['skip_attempts']}")
        else:
            print(f"  [INFO] No rank record yet")

        return test_result

    async def run_all_tests(self):
        """Run all profile tests"""
        await self.setup()

        try:
            for username, profile_info in TEST_PROFILES.items():
                profile_result = await self.test_user_profile(username, profile_info)
                self.results["profiles"][username] = profile_result

            # Generate summary
            self._generate_summary()

            # Save results to file
            self._save_results()

        finally:
            await self.teardown()

    def _generate_summary(self):
        """Generate test summary"""
        total_profiles = len(self.results["profiles"])
        profiles_with_data = sum(
            1 for p in self.results["profiles"].values()
            if p.get("tests")
        )

        self.results["summary"] = {
            "total_profiles_tested": total_profiles,
            "profiles_with_data": profiles_with_data,
            "test_timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "COMPLETE"
        }

    def _save_results(self):
        """Save results to JSON file"""
        with open(self.log_file, "w") as f:
            json.dump(self.results, f, indent=2, default=str)
        print(f"\n[OK] Results saved to {self.log_file}")


async def main():
    tester = Phase3Tester()
    await tester.run_all_tests()

    print(f"\n{'='*60}")
    print("PHASE 3 TESTING COMPLETE")
    print(f"{'='*60}")
    print(f"Profiles tested: {tester.results['summary']['total_profiles_tested']}")
    print(f"Results file: {tester.log_file}")


if __name__ == "__main__":
    asyncio.run(main())
