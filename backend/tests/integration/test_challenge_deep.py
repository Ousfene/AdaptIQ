"""Deep challenge journey script (manual).

This file is intentionally NOT a pytest test module: it performs a long,
stateful end-to-end journey and assumes a running backend and seeded data.

Run from the backend folder:
    python tests/integration/test_challenge_deep.py
"""

import sys
import time

import requests

if __name__ != "__main__":
    import pytest

    pytest.skip(
        "Standalone deep integration script; run with python tests/integration/test_challenge_deep.py",
        allow_module_level=True,
    )

BASE = "http://localhost:8000"
T = 60

def p(msg):
    print(msg, flush=True)

# Login as testscholar (has activity, admin)
r = requests.post(f"{BASE}/api/auth/login", json={"email":"testscholar@gmail.com","password":"TestPass123!"}, timeout=T)
TOKEN = r.json()["access_token"]
UID = r.json()["user"]["id"]
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

p("=" * 60)
p("DEEP CHALLENGE MODE TEST — ALL 5 LEVELS")
p("=" * 60)

# Get initial rank
r = requests.get(f"{BASE}/api/challenge/user/{UID}/rank", headers=H, timeout=T)
rank = r.json()
p(f"\nInitial: rank={rank['current_rank']} pts={rank['rank_points']} available_levels={rank['available_levels']}")

# Start session at level 1
r = requests.post(f"{BASE}/api/challenge/start-session", headers=H, timeout=T, json={
    "user_id": UID, "topic": "History", "starting_level": 1
})
if r.status_code != 200:
    p(f"FAIL: start-session returned {r.status_code}: {r.text[:200]}")
    sys.exit(1)
ch = r.json()
SID = ch["session_id"]
p(f"\nSession: {SID[:8]} level={ch.get('current_level',1)} rank={ch.get('current_rank','E')}")
p(f"Available levels: {ch.get('available_levels', [])}")

# Test all 5 levels: 2 questions per level = 10 questions
results = []
for level in range(1, 6):
    p(f"\n--- LEVEL {level} ---")
    for qi in range(2):
        # Generate question at this level
        r = requests.post(f"{BASE}/api/challenge/generate-question", headers=H, timeout=T, json={
            "session_id": SID, "user_id": UID, "topic": "History", "level": level
        })
        if r.status_code != 200:
            p(f"  GenQ ERROR: {r.status_code} {r.text[:150]}")
            results.append({"level": level, "q": qi+1, "gen": "FAIL", "ans": "SKIP"})
            continue
        
        cq = r.json()
        qid = cq["id"]
        qtext = cq["text"][:80]
        opts = cq["options"]
        pts_value = cq.get("points_value", "?")
        p(f"  Q{qi+1}: [{pts_value}pts] {qtext}...")
        p(f"        Options: {' | '.join(opts[:4])}")
        
        # Answer correctly on first Q per level, wrong on second
        if qi == 0:
            # Try to answer correctly — pick first option
            ans = opts[0]
        else:
            # Deliberately pick last option (may be wrong)
            ans = opts[-1]
        
        r = requests.post(f"{BASE}/api/challenge/submit-answer", headers=H, timeout=T, json={
            "session_id": SID, "question_id": qid, "user_id": UID,
            "answer": ans, "time_taken": 5.0 + level
        })
        if r.status_code != 200:
            p(f"  Ans ERROR: {r.status_code} {r.text[:150]}")
            results.append({"level": level, "q": qi+1, "gen": "OK", "ans": "FAIL"})
            continue
        
        ca = r.json()
        p(f"        Result: correct={ca['is_correct']} pts={ca['points_change']} "
          f"new_level={ca.get('new_level','?')} streak_c={ca['streak_correct']} streak_w={ca['streak_wrong']}")
        
        if ca.get("force_level_change"):
            flc = ca["force_level_change"]
            p(f"        FORCE LEVEL CHANGE: {flc['direction']} -- {flc['reason']}")
        
        correct_ans = ca.get("correct_answer", "?")
        p(f"        Correct answer: {correct_ans}")
        p(f"        Explanation: {ca.get('explanation','')[:100]}")
        
        results.append({
            "level": level, "q": qi+1, "gen": "OK", "ans": "OK",
            "correct": ca["is_correct"], "pts": ca["points_change"],
            "new_level": ca.get("new_level")
        })

# Get session status
p(f"\n--- SESSION STATUS ---")
r = requests.get(f"{BASE}/api/challenge/session/{SID}", headers=H, timeout=T)
if r.status_code == 200:
    ss = r.json()
    p(f"  total={ss['total_questions']} correct={ss['correct_answers']} level={ss['current_level']} "
      f"rank_pts={ss['rank_points']} streak_c={ss['streak_correct']} streak_w={ss['streak_wrong']}")

# End session
r = requests.post(f"{BASE}/api/challenge/session/{SID}/end", headers=H, timeout=T, json={"user_id": UID})
if r.status_code == 200:
    ce = r.json()
    p(f"\n--- END SESSION ---")
    p(f"  total={ce['total_questions']} correct={ce['correct_answers']}")
    p(f"  total_points_earned={ce['total_points_earned']}")
    p(f"  new_rank={ce['new_rank']} new_rank_points={ce['new_rank_points']} rank_changed={ce['rank_changed']}")

# Final rank
r = requests.get(f"{BASE}/api/challenge/user/{UID}/rank", headers=H, timeout=T)
rank2 = r.json()
p(f"\nFinal: rank={rank2['current_rank']} pts={rank2['rank_points']} sessions={rank2['total_sessions']}")

# ── EDGE CASES ──
p(f"\n{'='*60}")
p("EDGE CASE TESTS")
p("=" * 60)

# 1. Try to start with invalid level
p("\n[EDGE] Start with level 6 (invalid)...")
r = requests.post(f"{BASE}/api/challenge/start-session", headers=H, timeout=T, json={
    "user_id": UID, "topic": "History", "starting_level": 6
})
p(f"  status={r.status_code} (expect 422)")

# 2. Try to start with level 0
p("[EDGE] Start with level 0 (invalid)...")
r = requests.post(f"{BASE}/api/challenge/start-session", headers=H, timeout=T, json={
    "user_id": UID, "topic": "History", "starting_level": 0
})
p(f"  status={r.status_code} (expect 422)")

# 3. Submit empty answer
p("[EDGE] Submit empty answer...")
r = requests.post(f"{BASE}/api/challenge/start-session", headers=H, timeout=T, json={
    "user_id": UID, "topic": "Geography", "starting_level": 1
})
edge_sid = r.json()["session_id"]
r = requests.post(f"{BASE}/api/challenge/generate-question", headers=H, timeout=T, json={
    "session_id": edge_sid, "user_id": UID, "topic": "Geography", "level": 1
})
edge_qid = r.json()["id"]
r = requests.post(f"{BASE}/api/challenge/submit-answer", headers=H, timeout=T, json={
    "session_id": edge_sid, "question_id": edge_qid, "user_id": UID,
    "answer": "", "time_taken": 5
})
p(f"  status={r.status_code} detail={r.text[:100]}")

# 4. Change level mid-session
p("[EDGE] Change level (up)...")
r = requests.patch(f"{BASE}/api/challenge/session/{edge_sid}/change-level", headers=H, timeout=T, json={
    "direction": "up", "reason": "test"
})
p(f"  status={r.status_code} body={r.text[:100]}")

# 5. Change level (down)
p("[EDGE] Change level (down)...")
r = requests.patch(f"{BASE}/api/challenge/session/{edge_sid}/change-level", headers=H, timeout=T, json={
    "direction": "down", "reason": "test"
})
p(f"  status={r.status_code} body={r.text[:100]}")

# End edge session
requests.post(f"{BASE}/api/challenge/session/{edge_sid}/end", headers=H, timeout=T, json={"user_id": UID})

p(f"\n{'='*60}")
p("DONE")
