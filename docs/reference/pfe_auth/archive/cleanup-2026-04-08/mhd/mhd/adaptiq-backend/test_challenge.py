"""
test_challenge.py — Challenge Room backend test script.

Run from inside your adaptiq-backend folder:
    python test_challenge.py

What it does:
  1. Health check
  2. Get user rank
  3. Start a challenge session
  4. Get session state
  5. Generate a question
  6. Submit the correct answer
  7. Force a level change (up)
  8. End the session

No browser needed. No CORS issues. Runs in ~30 seconds.
Prints pass/fail for each step and a summary at the end.
"""

import asyncio
import httpx
import uuid
import json
import time
import sys

# ── Config ────────────────────────────────────────────────────────────────
BASE_URL  = "http://localhost:8000"
USER_ID   = str(uuid.uuid4())   # fresh user each run
TOPIC     = "Mixed"
LEVEL     = 1                   # start at level 1 (always available for rank E)
TIMEOUT   = 60.0                # generous timeout for LLM calls

# ── Shared state passed between tests ────────────────────────────────────
ctx = {
    "session_id"  : None,
    "question_id" : None,
    "correct_ans" : None,
    "options"     : None,
}

# ── Helpers ───────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

results = []

def pprint(data):
    """Print JSON response, truncated if very long."""
    s = json.dumps(data, indent=2)
    lines = s.split("\n")
    if len(lines) > 30:
        print("\n".join(lines[:30]))
        print(f"  ... ({len(lines) - 30} more lines)")
    else:
        print(s)

async def run_test(name: str, coro):
    """Run one test coroutine, catch errors, print result."""
    print(f"\n{CYAN}{'─'*55}{RESET}")
    print(f"{BOLD}TEST: {name}{RESET}")
    t0 = time.perf_counter()
    try:
        result = await coro
        ms = int((time.perf_counter() - t0) * 1000)
        print(f"{GREEN}✓ PASS{RESET}  ({ms}ms)")
        pprint(result)
        results.append((name, True, ms, None))
        return result
    except Exception as e:
        ms = int((time.perf_counter() - t0) * 1000)
        print(f"{RED}✗ FAIL{RESET}  ({ms}ms)")
        print(f"  {RED}Error: {e}{RESET}")
        results.append((name, False, ms, str(e)))
        return None


# ═══════════════════════════════════════════════════════════════════════
# TEST FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════

async def test_health(client: httpx.AsyncClient):
    r = await client.get(f"{BASE_URL}/health")
    r.raise_for_status()
    data = r.json()
    assert data["status"] == "ok", f"Expected status=ok, got {data['status']}"
    assert "database" in data["services"], "Missing 'database' in services"
    print(f"  Services: {data['services']}")
    return data


async def test_get_rank(client: httpx.AsyncClient):
    r = await client.get(f"{BASE_URL}/api/challenge/user/{USER_ID}/rank")
    r.raise_for_status()
    data = r.json()
    assert "current_rank"     in data, "Missing current_rank"
    assert "rank_points"      in data, "Missing rank_points"
    assert "available_levels" in data, "Missing available_levels"
    assert data["current_rank"] == "E",         f"New user should be rank E, got {data['current_rank']}"
    assert 1 in data["available_levels"],        "Level 1 should be available for rank E"
    assert 2 in data["available_levels"],        "Level 2 should be available for rank E"
    assert 5 not in data["available_levels"],    "Level 5 should NOT be available for rank E (anti-farming check)"
    print(f"  Rank: {data['current_rank']} | Available levels: {data['available_levels']}")
    return data


async def test_rank_gate_blocked(client: httpx.AsyncClient):
    """Trying to start at level 5 as rank E must be rejected (403)."""
    r = await client.post(
        f"{BASE_URL}/api/challenge/start-session",
        json={"user_id": USER_ID, "topic": TOPIC, "starting_level": 5}
    )
    assert r.status_code == 403, f"Expected 403 for level 5 with rank E, got {r.status_code}"
    print(f"  Correctly rejected level 5 for rank E → 403")
    return {"blocked": True, "status_code": r.status_code}


async def test_start_session(client: httpx.AsyncClient):
    r = await client.post(
        f"{BASE_URL}/api/challenge/start-session",
        json={"user_id": USER_ID, "topic": TOPIC, "starting_level": LEVEL}
    )
    r.raise_for_status()
    data = r.json()
    assert "session_id"   in data, "Missing session_id"
    assert "current_level" in data, "Missing current_level"
    assert data["current_level"] == LEVEL, f"Expected level {LEVEL}, got {data['current_level']}"
    assert data["rank_points"] == 0, "Session should start with 0 rank_points"
    ctx["session_id"] = data["session_id"]
    print(f"  Session: {ctx['session_id'][:16]}... | Level: {data['current_level']} | Rank: {data['current_rank']}")
    return data


async def test_get_session(client: httpx.AsyncClient):
    assert ctx["session_id"], "No session — start_session must run first"
    r = await client.get(f"{BASE_URL}/api/challenge/session/{ctx['session_id']}")
    r.raise_for_status()
    data = r.json()
    assert data["is_completed"] == False,            "Session should not be completed yet"
    assert data["current_level"] == LEVEL,           f"Level mismatch: expected {LEVEL}"
    assert data["streak_correct"] == 0,              "Correct streak should be 0 at start"
    assert data["streak_wrong"]   == 0,              "Wrong streak should be 0 at start"
    print(f"  State: level={data['current_level']} streak_c={data['streak_correct']} streak_w={data['streak_wrong']}")
    return data


async def test_generate_question(client: httpx.AsyncClient):
    """This is the slow test — LLM takes 5-20 seconds."""
    assert ctx["session_id"], "No session — start_session must run first"
    print(f"  {YELLOW}Calling LLM... (may take 10-20s){RESET}")
    r = await client.post(
        f"{BASE_URL}/api/challenge/generate-question",
        json={
            "session_id": ctx["session_id"],
            "user_id"   : USER_ID,
            "topic"     : TOPIC,
            "level"     : LEVEL,
        }
    )
    r.raise_for_status()
    data = r.json()
    assert "id"           in data, "Missing id"
    assert "text"         in data, "Missing text"
    assert "options"      in data, "Missing options"
    assert "correctAnswer" in data, "Missing correctAnswer"
    assert len(data["options"]) >= 2,                 "Question must have at least 2 options"
    assert data["correctAnswer"] in data["options"],  "Correct answer must be in options list"
    assert "points_value" in data,                    "Missing points_value (challenge-specific field)"
    assert data["level"] == LEVEL,                    f"Level mismatch: expected {LEVEL}"

    ctx["question_id"] = data["id"]
    ctx["correct_ans"] = data["correctAnswer"]
    ctx["options"]     = data["options"]

    print(f"  Q: {data['text'][:70]}...")
    print(f"  Options: {data['options']}")
    print(f"  Correct: {data['correctAnswer']} | Points value: {data['points_value']}")
    return data


async def test_submit_correct_answer(client: httpx.AsyncClient):
    assert ctx["session_id"],  "No session"
    assert ctx["question_id"], "No question — generate_question must run first"
    r = await client.post(
        f"{BASE_URL}/api/challenge/submit-answer",
        json={
            "session_id" : ctx["session_id"],
            "question_id": ctx["question_id"],
            "user_id"    : USER_ID,
            "answer"     : ctx["correct_ans"],
            "time_taken" : 7.3,
        }
    )
    r.raise_for_status()
    data = r.json()
    assert data["is_correct"]      == True,  "Should be correct (we sent the correct answer)"
    assert data["points_change"]   >  0,     f"Correct answer should give positive points, got {data['points_change']}"
    assert data["new_rank_points"] >  0,     "Session rank_points should be > 0 after correct answer"
    print(f"  Correct ✓ | Points: +{data['points_change']} | Running total: {data['new_rank_points']}")
    print(f"  Streaks: correct={data['streak_correct']} wrong={data['streak_wrong']} | Level: {data['new_level']}")
    if data.get("force_level_change"):
        print(f"  {YELLOW}Level change triggered: {data['force_level_change']}{RESET}")
    return data


async def test_duplicate_answer_blocked(client: httpx.AsyncClient):
    """Submitting the same question twice in the same session must return 409."""
    assert ctx["session_id"],  "No session"
    assert ctx["question_id"], "No question"
    r = await client.post(
        f"{BASE_URL}/api/challenge/submit-answer",
        json={
            "session_id" : ctx["session_id"],
            "question_id": ctx["question_id"],
            "user_id"    : USER_ID,
            "answer"     : ctx["correct_ans"],
            "time_taken" : 1.0,
        }
    )
    assert r.status_code == 409, f"Expected 409 for duplicate answer, got {r.status_code}"
    print(f"  Correctly blocked duplicate submission → 409")
    return {"blocked": True, "status_code": r.status_code}


async def test_change_level(client: httpx.AsyncClient):
    assert ctx["session_id"], "No session"
    r = await client.patch(
        f"{BASE_URL}/api/challenge/session/{ctx['session_id']}/change-level",
        json={"direction": "up", "reason": "manual test trigger"}
    )
    r.raise_for_status()
    data = r.json()
    assert "new_level" in data,          "Missing new_level in response"
    assert data["direction"] == "up",    "Direction should be 'up'"
    assert data["new_level"] <= 5,       "Level cannot exceed 5"
    print(f"  Level changed → {data['new_level']} ({data['reason']})")
    return data


async def test_end_session(client: httpx.AsyncClient):
    assert ctx["session_id"], "No session"
    r = await client.post(
        f"{BASE_URL}/api/challenge/session/{ctx['session_id']}/end"
    )
    r.raise_for_status()
    data = r.json()
    assert "total_questions"      in data, "Missing total_questions"
    assert "total_points_earned"  in data, "Missing total_points_earned"
    assert "new_rank"             in data, "Missing new_rank"
    assert "new_rank_points"      in data, "Missing new_rank_points"
    assert data["new_rank"] in ("E","D","C","B","A"), f"Invalid rank: {data['new_rank']}"
    print(f"  Session ended ✓")
    print(f"  Questions: {data['total_questions']} | Points earned: {data['total_points_earned']}")
    print(f"  Rank: {data['new_rank']} | Global rank_points: {data['new_rank_points']}")
    if data.get("rank_changed"):
        print(f"  {GREEN}RANK PROMOTION!{RESET}")
    return data


async def test_idempotent_end(client: httpx.AsyncClient):
    """Ending an already-completed session must not crash — it's idempotent."""
    assert ctx["session_id"], "No session"
    r = await client.post(
        f"{BASE_URL}/api/challenge/session/{ctx['session_id']}/end"
    )
    assert r.status_code == 200, f"Second end call should return 200 (idempotent), got {r.status_code}"
    print(f"  Second end call returned 200 (idempotent ✓)")
    return r.json()


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

async def main():
    print(f"\n{BOLD}{'═'*55}")
    print(f"  AdaptIQ Challenge Room — Backend Test Suite")
    print(f"{'═'*55}{RESET}")
    print(f"  Backend : {BASE_URL}")
    print(f"  User ID : {USER_ID[:16]}...")
    print(f"  Topic   : {TOPIC}  |  Starting level: {LEVEL}")
    print(f"{'─'*55}")

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:

        # ── Group 1: Health ───────────────────────────────────────────
        print(f"\n{BOLD}[ HEALTH ]{RESET}")
        await run_test("Health check",  test_health(client))

        # ── Group 2: Rank + anti-farming gate ─────────────────────────
        print(f"\n{BOLD}[ RANK & ANTI-FARMING ]{RESET}")
        await run_test("Get user rank (new user = E)",  test_get_rank(client))
        await run_test("Level gate: rank E cannot start at level 5",  test_rank_gate_blocked(client))

        # ── Group 3: Session lifecycle ────────────────────────────────
        print(f"\n{BOLD}[ SESSION LIFECYCLE ]{RESET}")
        await run_test("Start session at level 1",   test_start_session(client))
        await run_test("Get session state",          test_get_session(client))

        # ── Group 4: Question + answer ────────────────────────────────
        print(f"\n{BOLD}[ QUESTION & ANSWER ]{RESET}")
        await run_test("Generate question (LLM call)", test_generate_question(client))
        await run_test("Submit correct answer",        test_submit_correct_answer(client))
        await run_test("Duplicate answer blocked",     test_duplicate_answer_blocked(client))

        # ── Group 5: Level change ─────────────────────────────────────
        print(f"\n{BOLD}[ LEVEL CHANGE ]{RESET}")
        await run_test("Force level change (up)",  test_change_level(client))

        # ── Group 6: Session end ──────────────────────────────────────
        print(f"\n{BOLD}[ SESSION END ]{RESET}")
        await run_test("End session",              test_end_session(client))
        await run_test("End session (idempotent)", test_idempotent_end(client))

    # ── Summary ────────────────────────────────────────────────────────
    print(f"\n{BOLD}{'═'*55}")
    print(f"  RESULTS")
    print(f"{'═'*55}{RESET}")

    passed = sum(1 for _, ok, _, _ in results if ok)
    failed = sum(1 for _, ok, _, _ in results if not ok)

    for name, ok, ms, err in results:
        icon  = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
        color = GREEN if ok else RED
        print(f"  {icon} {color}{name}{RESET}  ({ms}ms)")
        if err:
            print(f"      {RED}└── {err}{RESET}")

    total = len(results)
    print(f"\n  {BOLD}{passed}/{total} passed{RESET}", end="  ")
    if failed == 0:
        print(f"{GREEN}All tests passed ✓{RESET}")
    else:
        print(f"{RED}{failed} failed{RESET}")
        print(f"\n  {YELLOW}Check the errors above — common causes:{RESET}")
        print(f"  • Backend not running → run: uvicorn main:app --reload")
        print(f"  • DB not running      → run: docker-compose up -d postgres redis")
        print(f"  • GROQ_API_KEY missing → check your .env file")
        sys.exit(1)

    print()


if __name__ == "__main__":
    asyncio.run(main())
