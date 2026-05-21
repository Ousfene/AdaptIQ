"""
scripts/profile_challenge_ranks.py — Live API profiling for all 5 challenge ranks.

Phase 1: Set user rank via DB for each rank test
Phase 2: Hit API endpoints to profile each rank

Run: cd backend && python scripts/profile_challenge_ranks.py
"""
import asyncio
import sys
import uuid
import json
import random
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from config import DATABASE_URL
from database.models import User, UserChallengeRank, ChallengeRank, UserResponse, QuestionBank
from auth.core.security import hash_password

import httpx

API_BASE = "http://localhost:8000"
PASSWORD = "TestPass123!"

RANK_EXPECTATIONS = {
    1: {"name": "Bronze",   "n_options": 2, "has_timer": False, "timer_seconds": None,  "beta_range": "easy (-2 to -1)"},
    2: {"name": "Silver",   "n_options": 4, "has_timer": False, "timer_seconds": None,  "beta_range": "easy-med (-1 to 0.5)"},
    3: {"name": "Gold",     "n_options": 4, "has_timer": True,  "timer_seconds": 45,    "beta_range": "medium (0 to 1)"},
    4: {"name": "Platinum", "n_options": 4, "has_timer": True,  "timer_seconds": 30,    "beta_range": "med-hard (0.5 to 1.5)"},
    5: {"name": "Diamond",  "n_options": 4, "has_timer": True,  "timer_seconds": 25,    "beta_range": "hard (1 to 2.5)"},
}


async def setup_rank_in_db(rank_id: int, engine):
    """Set balanced@test.com to the given rank."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        result = await db.execute(select(User).where(User.email == "balanced@test.com"))
        user = result.scalar_one_or_none()
        if not user:
            print(f"  ❌ User balanced@test.com not found!")
            return False

        ucr_result = await db.execute(
            select(UserChallengeRank).where(UserChallengeRank.user_id == user.id)
        )
        ucr = ucr_result.scalar_one_or_none()

        if not ucr:
            ucr = UserChallengeRank(
                user_id=user.id,
                current_rank_id=rank_id,
                wins=0,
                losses=0,
                skip_attempts_remaining=3,
            )
            db.add(ucr)
        else:
            ucr.current_rank_id = rank_id

        await db.commit()
    return True


async def profile_rank(client: httpx.AsyncClient, token: str, rank_id: int):
    """Profile a single challenge rank by playing a full 10-question match."""
    expect = RANK_EXPECTATIONS[rank_id]
    label = expect["name"]
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    passed = 0
    failed = 0
    issues = []

    print(f"\n{'═' * 60}")
    print(f"  RANK {rank_id}: {label.upper()}")
    print(f"  Expected: {expect['n_options']} opts | timer={'{}s'.format(expect['timer_seconds']) if expect['has_timer'] else 'none'} | β {expect['beta_range']}")
    print(f"{'═' * 60}")

    # ── 1. Check status ──────────────────────────────────────────
    try:
        status_resp = await client.get(f"{API_BASE}/api/rooms/challenge/status", headers=headers)
    except Exception as e:
        print(f"  ❌ Status request failed: {e}")
        return 0, 1

    if status_resp.status_code != 200:
        print(f"  ❌ Status failed: {status_resp.status_code} {status_resp.text[:200]}")
        return 0, 1

    status = status_resp.json()
    cr = status["current_rank"]

    if cr["id"] == rank_id:
        print(f"  ✅ Status: rank_id={rank_id} ({cr['name']})")
        passed += 1
    else:
        print(f"  ❌ Status: expected rank {rank_id}, got {cr['id']}")
        failed += 1

    if cr["n_options"] == expect["n_options"]:
        print(f"  ✅ Options config: {cr['n_options']}")
        passed += 1
    else:
        print(f"  ❌ Options config: got {cr['n_options']}, expected {expect['n_options']}")
        failed += 1

    timer_ok = cr["has_timer"] == expect["has_timer"]
    timer_s = cr.get("timer_seconds")
    if timer_ok and (not expect["has_timer"] or timer_s == expect["timer_seconds"]):
        t = f"{timer_s}s" if cr["has_timer"] else "none"
        print(f"  ✅ Timer: {t}")
        passed += 1
    else:
        print(f"  ❌ Timer mismatch: got has_timer={cr['has_timer']}, timer={timer_s}")
        failed += 1

    # ── 2. Start match ───────────────────────────────────────────
    try:
        start_resp = await client.post(f"{API_BASE}/api/rooms/challenge/start", headers=headers, json={
            "rank_id": rank_id,
            "is_skip_attempt": False,
        })
    except Exception as e:
        print(f"  ❌ Start request failed: {e}")
        return passed, failed + 1

    if start_resp.status_code != 200:
        print(f"  ❌ Start failed: {start_resp.status_code} {start_resp.text[:200]}")
        return passed, failed + 1

    start_data = start_resp.json()
    match_id = start_data["match_id"]
    first_q = start_data["first_question"]

    print(f"  ✅ Match started: {match_id[:8]}...")
    passed += 1

    # Check option count on first question
    n_opts = len(first_q["options"])
    if n_opts == expect["n_options"]:
        print(f"  ✅ Q1 options: {n_opts} (correct for {label})")
        passed += 1
    else:
        print(f"  ❌ Q1 options: got {n_opts}, expected {expect['n_options']}")
        failed += 1
        issues.append(f"Q1 opts={n_opts}")

    # ── 3. Answer 10 questions ───────────────────────────────────
    current_question = first_q
    correct_count = 0
    all_questions = [first_q]
    difficulties = [first_q.get("difficulty", 0)]

    for q_num in range(1, 11):
        answer_index = 0  # Always pick first option
        time_taken = 10

        try:
            answer_resp = await client.post(
                f"{API_BASE}/api/rooms/challenge/answer/{match_id}",
                headers=headers,
                json={
                    "question_id": current_question["id"],
                    "selected_index": answer_index,
                    "time_taken_seconds": time_taken,
                },
            )
        except Exception as e:
            print(f"  ❌ Q{q_num} request failed: {e}")
            failed += 1
            break

        if answer_resp.status_code != 200:
            print(f"  ❌ Q{q_num} answer failed: {answer_resp.status_code} {answer_resp.text[:200]}")
            failed += 1
            break

        answer_data = answer_resp.json()
        was_correct = answer_data["correct"]
        if was_correct:
            correct_count += 1

        if q_num < 10:
            next_q = answer_data.get("next_question")
            if next_q:
                all_questions.append(next_q)
                difficulties.append(next_q.get("difficulty", 0))
                n_opts = len(next_q["options"])
                if n_opts != expect["n_options"]:
                    issues.append(f"Q{q_num+1} opts={n_opts}")
                current_question = next_q
            else:
                print(f"  ⚠️  Q{q_num}: no next question")
                break

    # Check match ended
    if len(all_questions) >= 10:
        print(f"  ✅ All 10 questions served")
        passed += 1
    else:
        print(f"  ❌ Only {len(all_questions)} questions served")
        failed += 1

    # ── 4. End match ─────────────────────────────────────────────
    try:
        end_resp = await client.post(
            f"{API_BASE}/api/rooms/challenge/end/{match_id}",
            headers=headers,
        )
    except Exception as e:
        print(f"  ❌ End request failed: {e}")
        failed += 1
        end_resp = None

    if end_resp and end_resp.status_code == 200:
        end_data = end_resp.json()
        result = end_data["result"]
        score = end_data["score"]
        accuracy = correct_count / max(len(all_questions), 1) * 100
        expected_result = "win" if accuracy >= 70 else "loss"

        if result == expected_result:
            print(f"  ✅ Result: {result.upper()} ({correct_count}/{len(all_questions)} = {accuracy:.0f}%)")
            passed += 1
        else:
            print(f"  ❌ Result: got '{result}', expected '{expected_result}' ({accuracy:.0f}%)")
            failed += 1
    elif end_resp:
        print(f"  ❌ End failed: {end_resp.status_code} {end_resp.text[:200]}")
        failed += 1

    # ── Summary ──────────────────────────────────────────────────
    avg_diff = sum(difficulties) / len(difficulties) if difficulties else 0
    topics = set(q.get("topic", "?") for q in all_questions)

    print(f"\n  📊 Profile: {len(all_questions)}q | avg_diff={avg_diff:.1f}/5 | topics={', '.join(topics)} | {correct_count}/{len(all_questions)} correct")
    if issues:
        print(f"  ⚠️  Issues: {'; '.join(issues)}")

    return passed, failed


async def main():
    print("=" * 60)
    print("  CHALLENGE ROOM RANK PROFILING")
    print("  Testing all 5 ranks via live API")
    print("=" * 60)

    # Phase 1: DB engine
    engine = create_async_engine(DATABASE_URL, echo=False)

    # Phase 2: Login
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(f"{API_BASE}/api/auth/login", json={
            "email": "balanced@test.com",
            "password": PASSWORD,
        })
        if resp.status_code != 200:
            print(f"  ❌ Login failed: {resp.status_code} {resp.text}")
            sys.exit(1)
        token = resp.json()["access_token"]
        print(f"  ✅ Logged in as balanced@test.com")

        total_passed = 0
        total_failed = 0

        for rank_id in range(1, 6):
            # Set rank in DB
            ok = await setup_rank_in_db(rank_id, engine)
            if not ok:
                total_failed += 1
                continue
            
            # Small delay for DB to settle
            await asyncio.sleep(0.5)

            # Profile this rank via API
            p, f = await profile_rank(client, token, rank_id)
            total_passed += p
            total_failed += f

    await engine.dispose()

    # Final summary
    print("\n" + "=" * 60)
    total = total_passed + total_failed
    print(f"  RESULTS: {total_passed}/{total} passed, {total_failed}/{total} failed")
    if total_failed == 0:
        print("  🎉 ALL CHALLENGE RANK PROFILES PASSED!")
    else:
        print(f"  ⚠️  {total_failed} test(s) failed")
    print("=" * 60)

    return total_failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
