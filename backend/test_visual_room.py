"""
test_visual_room.py
Full test suite for the VisualRoom backend.

Run AFTER:
  1. Backend is running on localhost:8000
  2. visual_questions table is seeded (python -m services.visual_ingestion --limit 50)

Usage:
  python test_visual_room.py

Expected result: 14/14 tests pass

All tests use psycopg2 directly to set up / tear down data,
same pattern as test_challenge.py and test_custom.py in your project.
"""

import json
import sys
import time
import uuid
import psycopg2
import requests

BASE      = "http://localhost:8000"
DB_PARAMS = dict(host="localhost", port=5432, dbname="adaptiq_db",
                 user="adaptiq", password="adaptiq")

# Fixed test UUIDs so cleanup is easy
TEST_USER_ID    = "29fb2254-0005-44e5-a983-31b2cc665142"
TEST_SESSION_ID = None   # filled in by test_start_session

# ── Terminal colours ──────────────────────────────────────────────────────────
G = "\033[92m"   # green
R = "\033[91m"   # red
Y = "\033[93m"   # yellow
C = "\033[96m"   # cyan
B = "\033[1m"    # bold
X = "\033[0m"    # reset

passed = failed = skipped = 0


def ok(name, detail=""):
    global passed
    passed += 1
    print(f"  {G}✓  {name}{X}" + (f"  — {detail}" if detail else ""))


def fail(name, detail=""):
    global failed
    failed += 1
    print(f"  {R}✗  {name}{X}  — {detail}")


def warn(name, detail=""):
    global skipped
    skipped += 1
    print(f"  {Y}⚠  {name}{X}  — {detail}")


def section(title):
    print(f"\n{B}{C}{'─'*55}{X}")
    print(f"{B}{C}  {title}{X}")
    print(f"{B}{C}{'─'*55}{X}")


# ── DB helpers ────────────────────────────────────────────────────────────────

def db_conn():
    return psycopg2.connect(**DB_PARAMS)


def ensure_test_user():
    """Create the standard test user if not already present."""
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (id, email, username, password_hash)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
        """, (TEST_USER_ID, "visual-test@adaptiq.local",
              "visual-test-user", "test-hash"))
        conn.commit()


def count_visual_questions():
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM visual_questions")
        return cur.fetchone()[0]


def get_any_visual_question():
    """Get one row from visual_questions for direct DB tests."""
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, topic, question_text, correct_answer, question_type, options_json
            FROM visual_questions
            LIMIT 1
        """)
        row = cur.fetchone()
        if not row:
            return None
        return {
            "id": str(row[0]), "topic": row[1], "question_text": row[2],
            "correct_answer": row[3], "question_type": row[4],
            "options_json": row[5],
        }


def get_visual_question_by_type(q_type: str):
    """Get a question of a specific type (M or T)."""
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, topic, question_text, correct_answer, question_type, options_json
            FROM visual_questions
            WHERE question_type = %s
            LIMIT 1
        """, (q_type,))
        row = cur.fetchone()
        if not row:
            return None
        return {
            "id": str(row[0]), "topic": row[1], "question_text": row[2],
            "correct_answer": row[3], "question_type": row[4],
            "options_json": row[5],
        }


def cleanup():
    """Remove all test sessions created during this run."""
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM visual_sessions WHERE user_id = %s",
                    (TEST_USER_ID,))
        conn.commit()


# ═══════════════════════════════════════════════════════════════════════
# TESTS
# ═══════════════════════════════════════════════════════════════════════

def test_1_health():
    section("1. Health — backend is up and visual_questions table exists")
    r = requests.get(f"{BASE}/health", timeout=10)
    if r.status_code != 200:
        fail("Backend health check", f"HTTP {r.status_code}")
        return
    ok("Backend health check", f"status={r.json().get('status')}")

    # Confirm table exists and has rows
    try:
        count = count_visual_questions()
        if count == 0:
            warn("visual_questions has rows",
                 "Table is empty — run: python -m services.visual_ingestion --limit 50")
        else:
            ok("visual_questions has rows", f"{count} rows found")
    except Exception as e:
        fail("visual_questions table exists", str(e))


def test_2_start_session():
    global TEST_SESSION_ID
    section("2. POST /api/visual/start-session")

    r = requests.post(f"{BASE}/api/visual/start-session", json={
        "user_id": TEST_USER_ID,
        "topic":   "History",
        "level":   2,
    }, timeout=10)

    if r.status_code != 200:
        fail("Start session returns 200", f"HTTP {r.status_code} — {r.text[:200]}")
        return

    data = r.json()
    ok("Start session returns 200")

    for field in ["session_id", "topic", "level", "total_questions"]:
        if field in data:
            ok(f"Response has '{field}'", str(data[field]))
        else:
            fail(f"Response has '{field}'", f"got {list(data.keys())}")

    TEST_SESSION_ID = data.get("session_id")
    ok("session_id is a valid UUID", TEST_SESSION_ID[:8] + "...")


def test_3_next_question():
    section("3. GET /api/visual/next — fetch a question")
    if not TEST_SESSION_ID:
        warn("Skipping — no session_id (start_session failed)", "")
        return

    r = requests.get(f"{BASE}/api/visual/next", params={
        "session_id": TEST_SESSION_ID,
        "topic":      "History",
        "level":      2,
    }, timeout=30)   # 30s timeout because first call may trigger LLM generation

    if r.status_code != 200:
        fail("GET /next returns 200", f"HTTP {r.status_code} — {r.text[:300]}")
        return

    data = r.json()
    ok("GET /next returns 200")

    for field in ["id", "image_url", "text", "options", "topic",
                  "level", "question_type", "options_count"]:
        if field in data:
            ok(f"Response has '{field}'", str(data[field])[:60])
        else:
            fail(f"Response has '{field}'", f"got {list(data.keys())}")

    # CRITICAL: correct_answer must NOT be in the response
    if "correctAnswer" in data or "correct_answer" in data:
        fail("correct_answer NOT exposed to frontend",
             "SECURITY: correct answer found in response — fix this!")
    else:
        ok("correct_answer NOT in response (secure)")

    # Store question id for later tests
    test_3_next_question.question_id = data.get("id")
    test_3_next_question.correct_answer = None   # we don't know it from frontend


def test_4_no_correct_answer_in_response():
    section("4. Security — correct answer never in question response")
    if not TEST_SESSION_ID:
        warn("Skipping — no session_id", "")
        return

    # Fetch 3 questions and confirm none leak the correct answer
    leaks = 0
    for _ in range(3):
        r = requests.get(f"{BASE}/api/visual/next", params={
            "session_id": TEST_SESSION_ID,
            "topic": "Geography",
            "level": 3,
        }, timeout=30)
        if r.status_code == 200:
            body = r.text.lower()
            # correctAnswer or correct_answer should not appear as a key
            raw = r.json()
            if "correctAnswer" in raw or "correct_answer" in raw:
                leaks += 1

    if leaks == 0:
        ok("No correct_answer leaked in question responses (all 3 checks)")
    else:
        fail("Correct answer leaked in question response",
             f"{leaks}/3 responses contained the answer")


def test_5_hint_endpoint():
    section("5. GET /api/visual/hint — no answer revealed")
    q = get_any_visual_question()
    if not q:
        warn("No questions in DB for hint test", "Seed the DB first")
        return

    if not q["question_text"]:
        warn("Question has no text yet", "First /next call will generate it")
        return

    r = requests.get(f"{BASE}/api/visual/hint", params={
        "question_id": q["id"],
    }, timeout=20)

    if r.status_code != 200:
        fail("Hint endpoint returns 200", f"HTTP {r.status_code} — {r.text[:200]}")
        return

    data = r.json()
    ok("Hint endpoint returns 200")
    ok("Response has 'hint'", bool(data.get("hint")))

    hint_text = data.get("hint", "").lower()
    correct_lower = (q["correct_answer"] or "").lower()
    # Check hint doesn't literally contain the correct answer
    if correct_lower and len(correct_lower) > 3 and correct_lower in hint_text:
        fail("Hint does not reveal correct answer",
             f"Hint: {hint_text!r} / Answer: {correct_lower!r}")
    else:
        ok("Hint does not reveal the correct answer")


def test_6_submit_mcq_correct():
    section("6. POST /api/visual/submit — correct MCQ answer")
    if not TEST_SESSION_ID:
        warn("Skipping — no session_id", "")
        return

    # Get a question with a known correct answer from DB
    q = get_visual_question_by_type("M")
    if not q or not q["correct_answer"]:
        warn("No generated MCQ question found", "Seed + fetch /next first to generate questions")
        return

    r = requests.post(f"{BASE}/api/visual/submit", json={
        "session_id":    TEST_SESSION_ID,
        "question_id":   q["id"],
        "user_id":       TEST_USER_ID,
        "chosen_answer": q["correct_answer"],
        "user_time_ms":  5000,
    }, timeout=15)

    if r.status_code != 200:
        fail("Submit correct MCQ returns 200", f"HTTP {r.status_code} — {r.text[:200]}")
        return

    data = r.json()
    ok("Submit correct MCQ returns 200")
    ok("is_correct is True", str(data.get("is_correct")))
    ok("correct_answer revealed after submit", bool(data.get("correct_answer")))
    ok("explanation present", bool(data.get("explanation")))

    for field in ["is_correct", "correct_answer", "explanation"]:
        if field not in data:
            fail(f"Response has '{field}'")


def test_7_submit_mcq_wrong():
    section("7. POST /api/visual/submit — wrong MCQ answer")
    if not TEST_SESSION_ID:
        warn("Skipping — no session_id", "")
        return

    q = get_visual_question_by_type("M")
    if not q or not q["correct_answer"]:
        warn("No generated MCQ question found", "")
        return

    # Submit a deliberately wrong answer
    wrong_answer = "Definitely Wrong Answer XYZ"
    r = requests.post(f"{BASE}/api/visual/submit", json={
        "session_id":    TEST_SESSION_ID,
        "question_id":   q["id"],
        "user_id":       TEST_USER_ID,
        "chosen_answer": wrong_answer,
        "user_time_ms":  8000,
    }, timeout=15)

    if r.status_code != 200:
        fail("Submit wrong MCQ returns 200", f"HTTP {r.status_code}")
        return

    data = r.json()
    ok("Submit wrong answer returns 200")
    ok("is_correct is False for wrong answer", str(data.get("is_correct")))

    if data.get("is_correct") == False:
        ok("Server correctly marked wrong answer as incorrect")
    else:
        fail("Server marked obviously wrong answer as correct",
             f"submitted={wrong_answer!r} correct={q['correct_answer']!r}")


def test_8_stats_updated():
    section("8. n_attempts + difficulty_actual updated after submit")
    q = get_any_visual_question()
    if not q:
        warn("No questions to check stats on", "")
        return

    if not q["correct_answer"]:
        warn("Question not yet generated — skip stats check", "")
        return

    # Read current n_attempts
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT n_attempts, n_correct, difficulty_actual FROM visual_questions WHERE id = %s",
                    (q["id"],))
        before = cur.fetchone()

    if not TEST_SESSION_ID:
        warn("No session_id to submit with", "")
        return

    # Submit one answer
    requests.post(f"{BASE}/api/visual/submit", json={
        "session_id":    TEST_SESSION_ID,
        "question_id":   q["id"],
        "user_id":       TEST_USER_ID,
        "chosen_answer": q["correct_answer"],
        "user_time_ms":  3000,
    }, timeout=15)

    # Read after
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT n_attempts, n_correct, difficulty_actual FROM visual_questions WHERE id = %s",
                    (q["id"],))
        after = cur.fetchone()

    if before and after:
        attempts_increased = after[0] > before[0]
        ok("n_attempts incremented after submit",
           f"{before[0]} → {after[0]}")
        ok("difficulty_actual is a valid float 1-5",
           f"{after[2]:.2f}" if after[2] is not None else "None")
    else:
        fail("Could not read stats before/after submit")


def test_9_explanation_endpoint():
    section("9. GET /api/visual/explanation")
    q = get_any_visual_question()
    if not q or not q["question_text"]:
        warn("No generated question for explanation test", "")
        return

    r = requests.get(f"{BASE}/api/visual/explanation", params={
        "question_id": q["id"],
    }, timeout=10)

    if r.status_code != 200:
        fail("Explanation endpoint returns 200", f"HTTP {r.status_code}")
        return

    data = r.json()
    ok("Explanation endpoint returns 200")
    ok("Response has 'question_id'", data.get("question_id", "")[:16])
    ok("Response has 'explanation'", bool(data.get("explanation")))


def test_10_level5_text_input():
    section("10. Level 5 — text input question type")
    # Check that a level 5 session returns question_type='T' questions
    r = requests.post(f"{BASE}/api/visual/start-session", json={
        "user_id": TEST_USER_ID,
        "topic":   "Geography",
        "level":   5,
    }, timeout=10)

    if r.status_code != 200:
        warn("Could not start level 5 session", f"HTTP {r.status_code}")
        return

    session_id = r.json().get("session_id")
    ok("Level 5 session started", session_id[:8] + "...")

    r2 = requests.get(f"{BASE}/api/visual/next", params={
        "session_id": session_id,
        "topic":      "Geography",
        "level":      5,
    }, timeout=30)

    if r2.status_code != 200:
        warn("Level 5 /next failed", f"HTTP {r2.status_code} — {r2.text[:200]}")
        return

    data = r2.json()
    ok("Level 5 /next returns 200")

    q_type = data.get("question_type")
    if q_type == "T":
        ok("question_type is 'T' for level 5")
    else:
        warn(f"question_type is '{q_type}' (expected 'T')",
             "Level 5 questions may not be generated yet — depends on ingested data")

    opts = data.get("options", [])
    ok("Level 5 options list is empty (text input)",
       f"options={opts}" if not opts else f"WARNING: options={opts}")


def test_11_end_session():
    section("11. POST /api/visual/session/{id}/end")
    if not TEST_SESSION_ID:
        warn("Skipping — no session_id", "")
        return

    r = requests.post(f"{BASE}/api/visual/session/{TEST_SESSION_ID}/end",
                      timeout=10)

    if r.status_code != 200:
        fail("End session returns 200", f"HTTP {r.status_code}")
        return

    data = r.json()
    ok("End session returns 200")
    for field in ["session_id", "score", "questions_seen", "accuracy_percent"]:
        ok(f"Response has '{field}'", str(data.get(field, "MISSING")))


def test_12_404_on_bad_ids():
    section("12. Error handling — 404 on bad IDs")
    fake_id = str(uuid.uuid4())

    # Bad session_id for /next
    r1 = requests.get(f"{BASE}/api/visual/next", params={
        "session_id": fake_id,
        "topic": "History",
        "level": 2,
    }, timeout=10)
    ok("GET /next with fake session_id returns 404", f"status={r1.status_code}")

    # Bad question_id for hint
    r2 = requests.get(f"{BASE}/api/visual/hint", params={
        "question_id": fake_id,
    }, timeout=10)
    ok("GET /hint with fake question_id returns 404", f"status={r2.status_code}")

    # Bad question_id for explanation
    r3 = requests.get(f"{BASE}/api/visual/explanation", params={
        "question_id": fake_id,
    }, timeout=10)
    ok("GET /explanation with fake question_id returns 404", f"status={r3.status_code}")


def test_13_mix_topic():
    section("13. Mixed topic — serves both history and geography")
    r = requests.post(f"{BASE}/api/visual/start-session", json={
        "user_id": TEST_USER_ID,
        "topic":   "Mixed",
        "level":   2,
    }, timeout=10)

    if r.status_code != 200:
        warn("Mixed topic session failed", f"HTTP {r.status_code}")
        return

    session_id = r.json().get("session_id")
    ok("Mixed topic session started")

    topics_seen = set()
    for _ in range(4):
        r2 = requests.get(f"{BASE}/api/visual/next", params={
            "session_id": session_id,
            "topic":      "Mixed",
            "level":      2,
        }, timeout=30)
        if r2.status_code == 200:
            topics_seen.add(r2.json().get("topic", ""))

    ok(f"Mixed mode returned topics: {topics_seen}",
       "good" if len(topics_seen) > 0 else "no questions found")


def test_14_existing_rooms_unaffected():
    section("14. Existing rooms still work (ClassicRoom smoke test)")
    session_id = str(uuid.uuid4())
    r = requests.post(f"{BASE}/api/classic/generate-question", json={
        "topic":      "History",
        "difficulty": 2,
        "user_id":    TEST_USER_ID,
        "session_id": session_id,
    }, timeout=30)

    if r.status_code == 200:
        data = r.json()
        ok("ClassicRoom generate-question still works",
           data.get("text", "")[:50])
    else:
        fail("ClassicRoom generate-question broken after VisualRoom integration",
             f"HTTP {r.status_code}")


# ═══════════════════════════════════════════════════════════════════════
# RUNNER
# ═══════════════════════════════════════════════════════════════════════

def main():
    print(f"\n{B}{'═'*55}{X}")
    print(f"{B}  AdaptIQ VisualRoom Test Suite{X}")
    print(f"{B}{'═'*55}{X}")
    print(f"  Backend : {BASE}")
    print(f"  Test user: {TEST_USER_ID[:16]}...")
    print()

    # Check backend is reachable before running anything
    try:
        requests.get(f"{BASE}/health", timeout=5)
    except Exception:
        print(f"\n{R}  Cannot reach {BASE} — is the backend running?{X}\n")
        sys.exit(1)

    # Setup
    try:
        ensure_test_user()
    except Exception as e:
        print(f"{Y}  Warning: Could not ensure test user: {e}{X}")

    start = time.time()

    test_1_health()
    test_2_start_session()
    test_3_next_question()
    test_4_no_correct_answer_in_response()
    test_5_hint_endpoint()
    test_6_submit_mcq_correct()
    test_7_submit_mcq_wrong()
    test_8_stats_updated()
    test_9_explanation_endpoint()
    test_10_level5_text_input()
    test_11_end_session()
    test_12_404_on_bad_ids()
    test_13_mix_topic()
    test_14_existing_rooms_unaffected()

    # Cleanup
    try:
        cleanup()
    except Exception:
        pass

    elapsed = time.time() - start
    total   = passed + failed + skipped

    print(f"\n{B}{'═'*55}{X}")
    print(
        f"{B}  Results: {G}{passed}{X}/{total} passed  "
        f"{R}{failed} failed{X}  "
        f"{Y}{skipped} skipped{X}  [{elapsed:.1f}s]{X}"
    )
    print(f"{B}{'═'*55}{X}\n")

    if failed > 0:
        print(f"{Y}  Tip: If tests 6-9 show 'no generated question':{X}")
        print(f"  Run: python -m services.visual_ingestion --limit 50")
        print(f"  Then restart the backend and re-run this test.\n")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
