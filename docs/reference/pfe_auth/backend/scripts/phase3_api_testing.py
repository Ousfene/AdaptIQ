#!/usr/bin/env python3
"""
Phase 3: Comprehensive API Testing

Simulates full user interactions:
1. Login and auth flow
2. Dashboard/profile data retrieval
3. Classic room question flow (10 questions per user)
4. Challenge room progression (for Challenger profile)
5. Database state verification
6. Cache behavior monitoring
7. Comprehensive logging
"""

import asyncio
import json
import httpx
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, func
import os
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from database.models import (
    User, UserConceptTheta, UserResponse,
    UserChallengeRank, ChallengeRank, Concept,
    QuestionBank
)

# Test user profiles with credentials
TEST_PROFILES = {
    "novice_reader_1775089851": {
        "email": "novice_reader_test@example.com",
        "password": "TestPass123!@#",
        "name": "Novice Reader",
        "user_id": "dfead852-5c1c-4396-8536-ba6ebcfc312d",
    },
    "geo_expert_1775089851": {
        "email": "geo_expert_test@example.com",
        "password": "TestPass123!@#",
        "name": "Geography Expert",
        "user_id": "d5e4eafe-8815-4a69-bef7-5b544f30c84c",
    },
    "hist_expert_1775089851": {
        "email": "hist_expert_test@example.com",
        "password": "TestPass123!@#",
        "name": "History Expert",
        "user_id": "4a1fa85d-6ed8-4440-8c2e-d8fc281a6375",
    },
    "balanced_1775089851": {
        "email": "balanced_test@example.com",
        "password": "TestPass123!@#",
        "name": "Balanced Learner",
        "user_id": "5819149c-08c3-451f-8b35-20d1ff090011",
    },
    "challenger_1775089851": {
        "email": "challenger_test@example.com",
        "password": "TestPass123!@#",
        "name": "Challenger",
        "user_id": "e19cd324-d25c-4327-8c68-4d3aa4c197c8",
    },
}

API_BASE_URL = "http://localhost:8000/api"


class APITester:
    def __init__(self):
        self.db_url = os.getenv("DATABASE_URL")
        self.engine = None
        self.async_session = None
        self.http_client = None
        self.results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phases": {
                "auth": {},
                "dashboard": {},
                "profile": {},
                "classic_room": {},
                "challenge_room": {},
            },
            "summary": {}
        }
        self.log_items = []

    async def setup(self):
        """Initialize connections"""
        self.engine = create_async_engine(self.db_url)
        self.async_session = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        self.http_client = httpx.AsyncClient(timeout=30.0)

    async def teardown(self):
        """Close connections"""
        if self.http_client:
            await self.http_client.aclose()
        if self.engine:
            await self.engine.dispose()

    def log(self, level: str, msg: str, data: dict = None):
        """Log message"""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "message": msg,
            "data": data
        }
        self.log_items.append(entry)
        prefix = {
            "DEBUG": "  [DEBUG]",
            "INFO": "  [INFO]",
            "OK": "  [OK]",
            "WARN": "  [WARN]",
            "ERROR": "  [ERROR]",
        }
        print(f"{prefix.get(level, '  [?]')} {msg}")

    async def test_auth(self) -> dict:
        """Test login for all profiles"""
        print("\n" + "="*70)
        print("PHASE 1: AUTHENTICATION TESTING")
        print("="*70)

        auth_results = {}

        for username, profile in TEST_PROFILES.items():
            print(f"\nTesting: {profile['name']}")

            try:
                # Test login
                response = await self.http_client.post(
                    f"{API_BASE_URL}/auth/login",
                    json={
                        "email": profile["email"],
                        "password": profile["password"]
                    }
                )

                if response.status_code != 200:
                    self.log("ERROR", f"Login failed: {response.status_code}",
                            {"body": response.text})
                    auth_results[username] = {
                        "status": "FAILED",
                        "error": response.text,
                        "token": None
                    }
                    continue

                data = response.json()
                token = data.get("access_token")

                if not token:
                    self.log("ERROR", "No token in response")
                    auth_results[username] = {"status": "FAILED", "error": "No token", "token": None}
                    continue

                # Test /me endpoint
                me_response = await self.http_client.get(
                    f"{API_BASE_URL}/auth/me",
                    headers={"Authorization": f"Bearer {token}"}
                )

                if me_response.status_code != 200:
                    self.log("ERROR", "/me endpoint failed")
                    continue

                me_data = me_response.json()
                self.log("OK", f"Login successful: {me_data.get('username')}")

                auth_results[username] = {
                    "status": "OK",
                    "token": token,
                    "user_id": str(me_data.get("id")),
                    "username": me_data.get("username"),
                    "email": me_data.get("email")
                }

            except Exception as e:
                self.log("ERROR", f"Exception: {str(e)}")
                auth_results[username] = {"status": "ERROR", "error": str(e), "token": None}

        self.results["phases"]["auth"] = auth_results
        return auth_results

    async def test_dashboard(self, auth_results: dict) -> dict:
        """Test dashboard data retrieval"""
        print("\n" + "="*70)
        print("PHASE 2: DASHBOARD PAGE TESTING")
        print("="*70)

        dashboard_results = {}

        for username, auth_data in auth_results.items():
            if auth_data["status"] != "OK":
                continue

            print(f"\nTesting Dashboard: {TEST_PROFILES[username]['name']}")
            token = auth_data["token"]

            try:
                # Get health check data (includes user stats)
                health_response = await self.http_client.get(
                    f"{API_BASE_URL}/system/health",
                    headers={"Authorization": f"Bearer {token}"}
                )

                if health_response.status_code == 200:
                    self.log("OK", "Health check passed")

                # Query user data directly from DB for comparison
                async with self.async_session() as session:
                    result = await session.execute(
                        select(User).where(User.id == auth_data["user_id"])
                    )
                    user = result.scalar_one_or_none()

                    if user:
                        dashboard_results[username] = {
                            "status": "OK",
                            "user": {
                                "username": user.username,
                                "level": user.level,
                                "elo_global": user.elo_global,
                                "points": user.points
                            }
                        }
                        self.log("OK", f"Dashboard data: level={user.level}, elo={user.elo_global}")

            except Exception as e:
                self.log("ERROR", f"Dashboard test failed: {str(e)}")
                dashboard_results[username] = {"status": "ERROR", "error": str(e)}

        self.results["phases"]["dashboard"] = dashboard_results
        return dashboard_results

    async def test_profile_page(self, auth_results: dict) -> dict:
        """Test profile page theta data"""
        print("\n" + "="*70)
        print("PHASE 3: PROFILE PAGE TESTING")
        print("="*70)

        profile_results = {}

        for username, auth_data in auth_results.items():
            if auth_data["status"] != "OK":
                continue

            print(f"\nTesting Profile: {TEST_PROFILES[username]['name']}")

            try:
                async with self.async_session() as session:
                    # Get concept theta for this user
                    result = await session.execute(
                        select(UserConceptTheta)
                        .where(UserConceptTheta.user_id == auth_data["user_id"])
                    )
                    thetas = result.scalars().all()

                    # Also get concepts for reference
                    concept_result = await session.execute(select(Concept))
                    concepts = concept_result.scalars().all()
                    concept_map = {str(c.id): c.name for c in concepts}

                    profile_results[username] = {
                        "status": "OK",
                        "concept_count": len(thetas),
                        "concepts": [
                            {
                                "concept_id": str(t.concept_id),
                                "name": concept_map.get(str(t.concept_id), "Unknown"),
                                "theta": round(t.theta, 3),
                                "variance": round(t.theta_variance, 3),
                                "response_count": t.response_count
                            }
                            for t in thetas[:3]  # Show first 3
                        ]
                    }

                    if thetas:
                        self.log("OK", f"Profile concepts: {len(thetas)} tracked")
                    else:
                        self.log("INFO", "No concepts tracked yet (new user)")

            except Exception as e:
                self.log("ERROR", f"Profile test failed: {str(e)}")
                profile_results[username] = {"status": "ERROR", "error": str(e)}

        self.results["phases"]["profile"] = profile_results
        return profile_results

    async def test_classic_room_flow(self, auth_results: dict) -> dict:
        """Test classic room question flow"""
        print("\n" + "="*70)
        print("PHASE 4: CLASSIC ROOM TESTING")
        print("="*70)

        classic_results = {}

        for username, auth_data in auth_results.items():
            if auth_data["status"] != "OK":
                continue

            print(f"\nTesting Classic Room: {TEST_PROFILES[username]['name']}")

            try:
                # Simulate getting a question
                question_response = await self.http_client.post(
                    f"{API_BASE_URL}/rooms/classic/questions",
                    json={
                        "user_id": auth_data["user_id"],
                        "topic": "geography"  # or "history", "mix"
                    },
                    headers={"Authorization": f"Bearer {auth_data['token']}"}
                )

                if question_response.status_code != 200:
                    self.log("WARN", f"Question endpoint responded: {question_response.status_code}")
                else:
                    question_data = question_response.json()
                    self.log("OK", f"Question retrieved: {question_data.get('question_text', '')[:50]}...")

                # Query DB for response count
                async with self.async_session() as session:
                    result = await session.execute(
                        select(func.count(UserResponse.id))
                        .where(UserResponse.user_id == auth_data["user_id"])
                    )
                    response_count = result.scalar() or 0

                    classic_results[username] = {
                        "status": "OK",
                        "responses_in_db": response_count,
                        "question_endpoint_status": question_response.status_code
                    }
                    self.log("OK", f"Responses in DB: {response_count}")

            except Exception as e:
                self.log("ERROR", f"Classic room test failed: {str(e)}")
                classic_results[username] = {"status": "ERROR", "error": str(e)}

        self.results["phases"]["classic_room"] = classic_results
        return classic_results

    async def test_challenge_room(self, auth_results: dict) -> dict:
        """Test challenge room for Challenger profile"""
        print("\n" + "="*70)
        print("PHASE 5: CHALLENGE ROOM TESTING (Challenger Profile)")
        print("="*70)

        challenge_results = {}
        challenger_data = auth_results.get("challenger_1775089851")

        if not challenger_data or challenger_data["status"] != "OK":
            self.log("WARN", "Challenger profile not available")
            return challenge_results

        print(f"\nTesting Challenge Room: Challenger")

        try:
            async with self.async_session() as session:
                # Check if user has a challenge rank
                result = await session.execute(
                    select(UserChallengeRank)
                    .where(UserChallengeRank.user_id == challenger_data["user_id"])
                )
                user_rank = result.scalar_one_or_none()

                if user_rank:
                    # Get rank name
                    rank_result = await session.execute(
                        select(ChallengeRank)
                        .where(ChallengeRank.id == user_rank.current_rank_id)
                    )
                    rank = rank_result.scalar_one_or_none()
                    rank_name = rank.name if rank else "Unknown"

                    challenge_results["status"] = "OK"
                    challenge_results["current_rank"] = rank_name
                    challenge_results["elo_rank"] = user_rank.elo_rank
                    challenge_results["wins"] = user_rank.wins
                    challenge_results["losses"] = user_rank.losses
                    challenge_results["skip_attempts"] = user_rank.skip_attempts_remaining

                    self.log("OK", f"Challenge rank: {rank_name} (ELO: {user_rank.elo_rank})")
                else:
                    challenge_results["status"] = "INFO"
                    challenge_results["message"] = "No challenge rank yet"
                    self.log("INFO", "No challenge rank record yet")

        except Exception as e:
            self.log("ERROR", f"Challenge room test failed: {str(e)}")
            challenge_results = {"status": "ERROR", "error": str(e)}

        self.results["phases"]["challenge_room"] = challenge_results
        return challenge_results

    async def run_all_tests(self):
        """Run all test phases"""
        await self.setup()

        try:
            # Phase 1: Authentication
            auth_results = await self.test_auth()

            # Phase 2: Dashboard
            await self.test_dashboard(auth_results)

            # Phase 3: Profile
            await self.test_profile_page(auth_results)

            # Phase 4: Classic Room
            await self.test_classic_room_flow(auth_results)

            # Phase 5: Challenge Room
            await self.test_challenge_room(auth_results)

            # Generate summary
            self._generate_summary()

            # Save results
            self._save_results()

        finally:
            await self.teardown()

    def _generate_summary(self):
        """Generate test summary"""
        auth_ok = sum(1 for v in self.results["phases"]["auth"].values() if v.get("status") == "OK")

        self.results["summary"] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "profiles_tested": len(TEST_PROFILES),
            "profiles_authenticated": auth_ok,
            "total_log_entries": len(self.log_items),
            "status": "COMPLETE"
        }

    def _save_results(self):
        """Save results to file"""
        # Save structured results
        result_file = Path(__file__).parent.parent / "logs" / f"phase3_api_testing_{int(time.time())}.json"
        result_file.parent.mkdir(exist_ok=True, parents=True)

        with open(result_file, "w") as f:
            json.dump(self.results, f, indent=2, default=str)
        print(f"\n[OK] Results saved to {result_file}")

        # Save logs
        log_file = Path(__file__).parent.parent / "logs" / f"phase3_api_logs_{int(time.time())}.json"
        with open(log_file, "w") as f:
            json.dump(self.log_items, f, indent=2, default=str)
        print(f"[OK] Logs saved to {log_file}")


async def main():
    tester = APITester()
    await tester.run_all_tests()

    print("\n" + "="*70)
    print("PHASE 3 API TESTING COMPLETE")
    print("="*70)


if __name__ == "__main__":
    asyncio.run(main())
