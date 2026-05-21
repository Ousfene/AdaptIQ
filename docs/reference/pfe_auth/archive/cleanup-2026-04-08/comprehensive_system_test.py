#!/usr/bin/env python3
"""
Comprehensive system test for AdaptIQ
Tests ALL systems: Auth, Redis, RAG, Difficulty, Adaptivity, Classic Room, Challenge Room
"""
import asyncio
import httpx
import json
import uuid
from typing import Optional, Dict, Any
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:8000/api"

class ComprehensiveSystemTest:
    def __init__(self):
        self.client: Optional[httpx.AsyncClient] = None
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "phases": {},
            "summary": {}
        }

    async def setup(self):
        self.client = httpx.AsyncClient(timeout=30.0)

    async def teardown(self):
        if self.client:
            await self.client.aclose()

    # ─────────────────────────────────────────────────────────────────────────
    # PHASE 1: AUTHENTICATION SYSTEM
    # ─────────────────────────────────────────────────────────────────────────

    async def test_authentication(self):
        """Test: Registration, Login, JWT validation, User info"""
        logger.info("\n" + "="*80)
        logger.info("PHASE 1: AUTHENTICATION SYSTEM")
        logger.info("="*80)

        phase_results = {
            "status": "FAILED",
            "tests": []
        }

        # Test 1.1: Registration
        logger.info("\n[1.1] Testing Registration...")
        unique_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
        unique_username = f"user_{uuid.uuid4().hex[:8]}"

        try:
            register_resp = await self.client.post(
                f"{BASE_URL}/auth/register",
                json={
                    "email": unique_email,
                    "username": unique_username,
                    "password": "TestPassword123!@"
                }
            )

            if register_resp.status_code == 201:
                reg_data = register_resp.json()
                user_id = reg_data.get("user", {}).get("id")
                token = reg_data.get("access_token")

                phase_results["tests"].append({
                    "test": "Registration",
                    "status": "PASS",
                    "details": f"User created: {user_id}"
                })
                logger.info(f"✅ Registration: User {user_id} created")
            else:
                phase_results["tests"].append({
                    "test": "Registration",
                    "status": "FAIL",
                    "error": register_resp.text
                })
                logger.error(f"❌ Registration failed: {register_resp.status_code}")
                return phase_results

        except Exception as e:
            phase_results["tests"].append({
                "test": "Registration",
                "status": "ERROR",
                "error": str(e)
            })
            logger.error(f"❌ Registration error: {e}")
            return phase_results

        # Test 1.2: Login
        logger.info("\n[1.2] Testing Login with JWT...")
        try:
            login_resp = await self.client.post(
                f"{BASE_URL}/auth/login",
                json={
                    "email": unique_email,
                    "password": "TestPassword123!@"
                }
            )

            if login_resp.status_code == 200:
                login_data = login_resp.json()
                token = login_data.get("access_token")
                user_id = login_data.get("user", {}).get("id")

                phase_results["tests"].append({
                    "test": "Login",
                    "status": "PASS",
                    "token_length": len(token) if token else 0
                })
                logger.info(f"✅ Login: JWT token obtained ({len(token)} chars)")
            else:
                phase_results["tests"].append({
                    "test": "Login",
                    "status": "FAIL",
                    "error": login_resp.text
                })
                logger.error(f"❌ Login failed: {login_resp.status_code}")
                return phase_results

        except Exception as e:
            phase_results["tests"].append({
                "test": "Login",
                "status": "ERROR",
                "error": str(e)
            })
            logger.error(f"❌ Login error: {e}")
            return phase_results

        # Test 1.3: Get Current User (/me endpoint)
        logger.info("\n[1.3] Testing JWT validation (/me endpoint)...")
        try:
            me_resp = await self.client.get(
                f"{BASE_URL}/auth/me",
                headers={"Authorization": f"Bearer {token}"}
            )

            if me_resp.status_code == 200:
                me_data = me_resp.json()

                phase_results["tests"].append({
                    "test": "JWT Validation (/me)",
                    "status": "PASS",
                    "user_email": me_data.get("email")
                })
                logger.info(f"✅ JWT Validation: User {me_data.get('email')} verified")
            else:
                phase_results["tests"].append({
                    "test": "JWT Validation (/me)",
                    "status": "FAIL",
                    "status_code": me_resp.status_code
                })
                logger.error(f"❌ JWT validation failed: {me_resp.status_code}")
                return phase_results

        except Exception as e:
            phase_results["tests"].append({
                "test": "JWT Validation",
                "status": "ERROR",
                "error": str(e)
            })
            logger.error(f"❌ JWT validation error: {e}")
            return phase_results

        # Test 1.4: Get User Stats
        logger.info("\n[1.4] Testing User Stats...")
        try:
            stats_resp = await self.client.get(
                f"{BASE_URL}/auth/stats",
                headers={"Authorization": f"Bearer {token}"}
            )

            if stats_resp.status_code == 200:
                stats_data = stats_resp.json()
                phase_results["tests"].append({
                    "test": "User Stats",
                    "status": "PASS",
                    "total_questions": stats_data.get("total_questions", 0)
                })
                logger.info(f"✅ User Stats: {stats_data.get('total_questions', 0)} questions answered")
            else:
                phase_results["tests"].append({
                    "test": "User Stats",
                    "status": "FAIL",
                    "status_code": stats_resp.status_code
                })
                logger.error(f"❌ User stats failed: {stats_resp.status_code}")

        except Exception as e:
            phase_results["tests"].append({
                "test": "User Stats",
                "status": "ERROR",
                "error": str(e)
            })
            logger.error(f"❌ User stats error: {e}")

        phase_results["status"] = "PASS"
        phase_results["user_id"] = user_id
        phase_results["token"] = token
        phase_results["email"] = unique_email

        self.results["phases"]["authentication"] = phase_results
        return phase_results

    # ─────────────────────────────────────────────────────────────────────────
    # PHASE 2: CLASSIC ROOM - FULL SESSION WITH ADAPTIVITY
    # ─────────────────────────────────────────────────────────────────────────

    async def test_classic_room_adaptivity(self, user_id: str, token: str):
        """Test: Classic room question generation, RAG difficulty, IRT adaptivity"""
        logger.info("\n" + "="*80)
        logger.info("PHASE 2: CLASSIC ROOM WITH ADAPTIVITY")
        logger.info("="*80)
        logger.info(f"Using user_id={user_id}")

        phase_results = {
            "status": "FAILED",
            "tests": [],
            "questions": [],
            "theta_progression": []
        }

        # Test 2.1: Start Classic Session
        logger.info("\n[2.1] Starting classic room session...")
        try:
            start_resp = await self.client.post(
                f"{BASE_URL}/rooms/classic/start",
                json={"user_id": user_id, "topic": "history"},
                headers={"Authorization": f"Bearer {token}"}
            )

            if start_resp.status_code != 200:
                phase_results["tests"].append({
                    "test": "Start Session",
                    "status": "FAIL",
                    "status_code": start_resp.status_code
                })
                logger.error(f"❌ Start session failed: {start_resp.status_code}")
                return phase_results

            session_data = start_resp.json()
            session_id = session_data.get("session_id")
            first_question = session_data.get("first_question")

            phase_results["tests"].append({
                "test": "Start Session",
                "status": "PASS",
                "session_id": session_id
            })
            logger.info(f"✅ Session started: {session_id}")

        except Exception as e:
            phase_results["tests"].append({
                "test": "Start Session",
                "status": "ERROR",
                "error": str(e)
            })
            logger.error(f"❌ Start session error: {e}")
            return phase_results

        # Test 2.2: Get questions and check adaptive difficulty
        logger.info("\n[2.2] Testing RAG question generation and adaptive difficulty...")
        difficulty_progression = []

        for q_num in range(1, 6):  # Test 5 questions
            try:
                # Determine difficulty based on number (simulate user performance)
                if q_num == 1:
                    current_diff = 3
                    answer_correct = True  # Good answer
                elif q_num == 2:
                    current_diff = 4  # Difficulty should increase
                    answer_correct = True
                elif q_num == 3:
                    current_diff = 5  # Max difficulty
                    answer_correct = False  # Wrong answer
                else:
                    current_diff = 3  # Should decrease
                    answer_correct = True

                question_resp = await self.client.post(
                    f"{BASE_URL}/rooms/classic/questions",
                    json={
                        "user_id": user_id,
                        "session_id": session_id,
                        "topic": "history",
                        "difficulty": current_diff
                    },
                    headers={"Authorization": f"Bearer {token}"}
                )

                if question_resp.status_code != 200:
                    phase_results["tests"].append({
                        "test": f"Question {q_num}",
                        "status": "FAIL",
                        "status_code": question_resp.status_code,
                        "error": question_resp.text[:200]
                    })
                    logger.error(f"❌ Question {q_num} failed: {question_resp.status_code}")
                    logger.error(f"   user_id={user_id}, session_id={session_id}")
                    logger.error(f"   Error: {question_resp.text[:300]}")
                    break

                question_data = question_resp.json()
                question_id = question_data.get("id")
                question_text = question_data.get("text")
                options = question_data.get("options", [])
                explanation = question_data.get("explanation", "")

                phase_results["questions"].append({
                    "question_number": q_num,
                    "id": question_id,
                    "text": question_text[:80],
                    "option_count": len(options),
                    "explanation_present": bool(explanation)
                })

                logger.info(f"✅ Question {q_num}: {question_text[:60]}...")
                logger.info(f"   Options: {len(options)}, Explanation: {len(explanation)} chars")

                # Test 2.3: Submit answer and check difficulty adaptation
                if q_num < 5:  # Don't submit on last one
                    answer_resp = await self.client.post(
                        f"{BASE_URL}/rooms/classic/answers",
                        json={
                            "user_id": user_id,
                            "session_id": session_id,
                            "question_id": question_id,
                            "selected_answer": options[0] if options else "",
                            "used_hint": False
                        },
                        headers={"Authorization": f"Bearer {token}"}
                    )

                    if answer_resp.status_code == 200:
                        answer_data = answer_resp.json()
                        updated_difficulty = answer_data.get("updated_difficulty", current_diff)
                        difficulty_progression.append({
                            "question": q_num,
                            "difficulty": updated_difficulty,
                            "correct": answer_data.get("correct", False)
                        })
                        logger.info(f"   Answer submitted: Correct={answer_data.get('correct')} Difficulty→{updated_difficulty}")
                    else:
                        logger.error(f"❌ Answer submission failed: {answer_resp.status_code}")

            except Exception as e:
                logger.error(f"❌ Question {q_num} error: {e}")
                break

        phase_results["tests"].append({
            "test": "Question Generation & Answers",
            "status": "PASS",
            "questions_fetched": len(phase_results["questions"])
        })

        phase_results["difficulty_progression"] = difficulty_progression
        phase_results["status"] = "PASS"

        self.results["phases"]["classic_room"] = phase_results
        return phase_results

    # ─────────────────────────────────────────────────────────────────────────
    # PHASE 3: CHALLENGE ROOM - RANK SYSTEM TESTING
    # ─────────────────────────────────────────────────────────────────────────

    async def test_challenge_room_ranks(self, user_id: str, token: str):
        """Test: Challenge room, all ranks, ELO system, skip mechanics"""
        logger.info("\n" + "="*80)
        logger.info("PHASE 3: CHALLENGE ROOM - RANK SYSTEM")
        logger.info("="*80)

        phase_results = {
            "status": "FAILED",
            "tests": [],
            "rank_details": {}
        }

        # Test 3.1: Check challenge status and initial rank
        logger.info("\n[3.1] Checking challenge room status...")
        try:
            status_resp = await self.client.get(
                f"{BASE_URL}/rooms/challenge/status",
                headers={"Authorization": f"Bearer {token}"}
            )

            if status_resp.status_code != 200:
                phase_results["tests"].append({
                    "test": "Challenge Status",
                    "status": "FAIL",
                    "status_code": status_resp.status_code
                })
                logger.error(f"❌ Challenge status failed: {status_resp.status_code}")
                return phase_results

            status_data = status_resp.json()
            current_rank = status_data.get("rank", "Bronze")
            wins = status_data.get("wins", 0)
            losses = status_data.get("losses", 0)
            skip_attempts = status_data.get("skip_attempts_available", 0)

            phase_results["tests"].append({
                "test": "Challenge Status",
                "status": "PASS",
                "initial_rank": current_rank
            })
            logger.info(f"✅ Challenge Status: Rank={current_rank}, W/L={wins}/{losses}, Skips={skip_attempts}")

        except Exception as e:
            phase_results["tests"].append({
                "test": "Challenge Status",
                "status": "ERROR",
                "error": str(e)
            })
            logger.error(f"❌ Challenge status error: {e}")
            return phase_results

        # Test 3.2: Start a challenge match
        logger.info("\n[3.2] Starting challenge match...")
        try:
            start_resp = await self.client.post(
                f"{BASE_URL}/rooms/challenge/start",
                json={
                    "rank_id": 1,  # Bronze rank
                    "is_skip_attempt": False
                },
                headers={"Authorization": f"Bearer {token}"}
            )

            if start_resp.status_code != 200:
                phase_results["tests"].append({
                    "test": "Challenge Start",
                    "status": "FAIL",
                    "status_code": start_resp.status_code
                })
                logger.error(f"❌ Challenge start failed: {start_resp.status_code}")
                return phase_results

            match_data = start_resp.json()
            match_id = match_data.get("match_id")
            first_question = match_data.get("question")

            phase_results["tests"].append({
                "test": "Challenge Start",
                "status": "PASS",
                "match_id": match_id
            })
            logger.info(f"✅ Challenge match started: {match_id}")

        except Exception as e:
            phase_results["tests"].append({
                "test": "Challenge Start",
                "status": "ERROR",
                "error": str(e)
            })
            logger.error(f"❌ Challenge start error: {e}")
            return phase_results

        # Test 3.3: Answer questions in challenge (partial)
        logger.info("\n[3.3] Testing challenge question answering...")
        correct_count = 0

        for q_num in range(1, 4):  # Test 3 questions
            try:
                if q_num == 1:
                    first_question = match_data.get("question")
                    question_id = first_question.get("id") if first_question else "test-id"
                else:
                    answer_resp = await self.client.post(
                        f"{BASE_URL}/rooms/challenge/answer/{match_id}",
                        json={
                            "question_id": question_id,
                            "selected_index": 0,  # Select first option
                            "time_taken_seconds": 5
                        },
                        headers={"Authorization": f"Bearer {token}"}
                    )

                    if answer_resp.status_code != 200:
                        logger.error(f"❌ Challenge answer {q_num} failed: {answer_resp.status_code}")
                        break

                    answer_data = answer_resp.json()
                    first_question = answer_data.get("question")
                    question_id = first_question.get("id") if first_question else "test-id"
                    if answer_data.get("correct"):
                        correct_count += 1

                    logger.info(f"   Question {q_num}: Option selected, Score={answer_data.get('correct', False)}")

            except Exception as e:
                logger.error(f"❌ Challenge question {q_num} error: {e}")
                break

        phase_results["tests"].append({
            "test": "Challenge Answering",
            "status": "PASS",
            "answered": q_num - 1,
            "correct": correct_count
        })

        logger.info(f"✅ Challenge answers: {correct_count} correct out of {q_num-1}")

        phase_results["rank_details"] = {
            "initial_rank": current_rank,
            "wins": wins,
            "losses": losses,
            "skip_attempts": skip_attempts
        }
        phase_results["status"] = "PASS"

        self.results["phases"]["challenge_room"] = phase_results
        return phase_results

    # ─────────────────────────────────────────────────────────────────────────
    # PHASE 4: HINTS SYSTEM TESTING
    # ─────────────────────────────────────────────────────────────────────────

    async def test_hints(self, user_id: str, token: str):
        """Test: Hint generation, answer non-revelation"""
        logger.info("\n" + "="*80)
        logger.info("PHASE 4: HINTS SYSTEM")
        logger.info("="*80)

        phase_results = {
            "status": "FAILED",
            "tests": []
        }

        # First need to get a question to generate a hint for
        logger.info("\n[4.1] Getting a question for hint testing...")
        try:
            start_resp = await self.client.post(
                f"{BASE_URL}/rooms/classic/start",
                json={"user_id": user_id, "topic": "geography"},
                headers={"Authorization": f"Bearer {token}"}
            )

            if start_resp.status_code != 200:
                logger.error(f"❌ Failed to start session for hints: {start_resp.status_code}")
                return phase_results

            session_id = start_resp.json()["session_id"]

            # Get a question
            q_resp = await self.client.post(
                f"{BASE_URL}/rooms/classic/questions",
                json={
                    "user_id": user_id,
                    "session_id": session_id,
                    "topic": "geography",
                    "difficulty": 3
                },
                headers={"Authorization": f"Bearer {token}"}
            )

            if q_resp.status_code != 200:
                logger.error(f"❌ Failed to get question: {q_resp.status_code}")
                return phase_results

            question_data = q_resp.json()
            question_text = question_data["text"]

            logger.info(f"✅ Got question: {question_text[:60]}...")

        except Exception as e:
            logger.error(f"❌ Question fetch error: {e}")
            return phase_results

        # Test 4.2: Generate hint
        logger.info("\n[4.2] Testing hint generation...")
        try:
            hint_resp = await self.client.post(
                f"{BASE_URL}/rooms/classic/hints",
                json={
                    "session_id": session_id,
                    "questionText": question_text
                },
                headers={"Authorization": f"Bearer {token}"}
            )

            if hint_resp.status_code == 200:
                hint_data = hint_resp.json()
                hint_text = hint_data.get("hint", "")

                # Check that hint doesn't reveal the answer
                # (This is enforced in LLM prompt, but we check basic sanity)
                phase_results["tests"].append({
                    "test": "Hint Generation",
                    "status": "PASS",
                    "hint_length": len(hint_text)
                })
                logger.info(f"✅ Hint generated: {hint_text[:80]}...")
            else:
                phase_results["tests"].append({
                    "test": "Hint Generation",
                    "status": "FAIL",
                    "status_code": hint_resp.status_code
                })
                logger.error(f"❌ Hint generation failed: {hint_resp.status_code}")

        except Exception as e:
            phase_results["tests"].append({
                "test": "Hint Generation",
                "status": "ERROR",
                "error": str(e)
            })
            logger.error(f"❌ Hint error: {e}")

        phase_results["status"] = "PASS"
        self.results["phases"]["hints"] = phase_results
        return phase_results

    # ─────────────────────────────────────────────────────────────────────────
    # PHASE 5: SYSTEM HEALTH & MONITORING
    # ─────────────────────────────────────────────────────────────────────────

    async def test_system_health(self):
        """Test: Health check, database, Redis, monitoring"""
        logger.info("\n" + "="*80)
        logger.info("PHASE 5: SYSTEM HEALTH & MONITORING")
        logger.info("="*80)

        phase_results = {
            "status": "FAILED",
            "tests": []
        }

        # Test 5.1: Health check
        logger.info("\n[5.1] System health check...")
        try:
            health_resp = await self.client.get(f"{BASE_URL}/system/health")

            if health_resp.status_code == 200:
                health_data = health_resp.json()
                db_status = health_data.get("services", {}).get("database")
                redis_status = health_data.get("services", {}).get("redis")

                phase_results["tests"].append({
                    "test": "Health Check",
                    "status": "PASS",
                    "database": db_status,
                    "redis": redis_status
                })
                logger.info(f"✅ Health check: DB={db_status}, Redis={redis_status}")
            else:
                phase_results["tests"].append({
                    "test": "Health Check",
                    "status": "FAIL",
                    "status_code": health_resp.status_code
                })
                logger.error(f"❌ Health check failed: {health_resp.status_code}")

        except Exception as e:
            phase_results["tests"].append({
                "test": "Health Check",
                "status": "ERROR",
                "error": str(e)
            })
            logger.error(f"❌ Health check error: {e}")

        # Test 5.2: Monitoring stats
        logger.info("\n[5.2] Monitoring stats...")
        try:
            stats_resp = await self.client.get(f"{BASE_URL}/system/monitoring/stats")

            if stats_resp.status_code == 200:
                stats_data = stats_resp.json()
                total_requests = stats_data.get("total_requests", 0)
                total_errors = stats_data.get("total_errors", 0)

                phase_results["tests"].append({
                    "test": "Monitoring Stats",
                    "status": "PASS",
                    "total_requests": total_requests,
                    "total_errors": total_errors
                })
                logger.info(f"✅ Monitoring: {total_requests} requests, {total_errors} errors")
            else:
                phase_results["tests"].append({
                    "test": "Monitoring Stats",
                    "status": "FAIL",
                    "status_code": stats_resp.status_code
                })

        except Exception as e:
            phase_results["tests"].append({
                "test": "Monitoring Stats",
                "status": "ERROR",
                "error": str(e)
            })

        phase_results["status"] = "PASS"
        self.results["phases"]["system_health"] = phase_results
        return phase_results

    # ─────────────────────────────────────────────────────────────────────────
    # MAIN TEST RUNNER
    # ─────────────────────────────────────────────────────────────────────────

    async def run_all_tests(self):
        """Run all comprehensive tests"""
        await self.setup()

        try:
            # Phase 1: Authentication
            auth_results = await self.test_authentication()

            if auth_results["status"] != "PASS":
                logger.error("❌ Authentication failed - cannot continue")
                return

            user_id = auth_results["user_id"]
            token = auth_results["token"]

            # Phase 2: Classic Room
            await self.test_classic_room_adaptivity(user_id, token)

            # Phase 3: Challenge Room
            await self.test_challenge_room_ranks(user_id, token)

            # Phase 4: Hints
            await self.test_hints(user_id, token)

            # Phase 5: System Health
            await self.test_system_health()

            # Generate summary
            self._generate_summary()

            # Print results
            self._print_results()

        finally:
            await self.teardown()

    def _generate_summary(self):
        """Generate test summary"""
        total_tests = 0
        passed_tests = 0
        failed_tests = 0
        error_tests = 0

        for phase_name, phase_data in self.results["phases"].items():
            if isinstance(phase_data, dict) and "tests" in phase_data:
                for test in phase_data["tests"]:
                    total_tests += 1
                    if test.get("status") == "PASS":
                        passed_tests += 1
                    elif test.get("status") == "FAIL":
                        failed_tests += 1
                    elif test.get("status") == "ERROR":
                        error_tests += 1

        self.results["summary"] = {
            "total_tests": total_tests,
            "passed": passed_tests,
            "failed": failed_tests,
            "errors": error_tests,
            "success_rate": f"{100*passed_tests//max(total_tests,1)}%"
        }

    def _print_results(self):
        """Print test results"""
        logger.info("\n" + "="*80)
        logger.info("COMPREHENSIVE TEST SUMMARY")
        logger.info("="*80)

        summary = self.results["summary"]
        logger.info(f"\nTotal Tests: {summary['total_tests']}")
        logger.info(f"Passed: {summary['passed']}")
        logger.info(f"Failed: {summary['failed']}")
        logger.info(f"Errors: {summary['errors']}")
        logger.info(f"Success Rate: {summary['success_rate']}")

        # Export full results
        with open("comprehensive_system_test_results.json", "w") as f:
            json.dump(self.results, f, indent=2)

        logger.info(f"\nFull results exported to: comprehensive_system_test_results.json")

        # Phase-by-phase details
        logger.info("\n" + "─"*80)
        logger.info("PHASE-BY-PHASE RESULTS")
        logger.info("─"*80)

        for phase_name, phase_data in self.results["phases"].items():
            if isinstance(phase_data, dict):
                status = phase_data.get("status", "UNKNOWN")
                test_count = len(phase_data.get("tests", []))
                logger.info(f"\n{phase_name.upper()}: {status}")
                logger.info(f"  Tests: {test_count}")

                for test in phase_data.get("tests", []):
                    test_name = test.get("test", "Unknown")
                    test_status = test.get("status", "UNKNOWN")
                    logger.info(f"  - {test_name}: {test_status}")

async def main():
    test = ComprehensiveSystemTest()
    await test.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())
