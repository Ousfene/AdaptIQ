import uuid

import requests
import threading

BASE = "http://127.0.0.1:8000"
TIMEOUT = 30


def signup_and_login() -> tuple[str, str]:
    run_id = uuid.uuid4().hex[:8]
    email = f"idem_{run_id}@example.com"
    username = f"idem_{run_id}"
    password = "TestPass123!"

    r = requests.post(
        f"{BASE}/api/auth/signup",
        json={"email": email, "username": username, "password": password},
        timeout=TIMEOUT,
    )
    r.raise_for_status()

    return login(email, password)


def login(email, password):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()["access_token"], r.json()["user"]["id"]


def test_submit_answer_idempotent():
    token, uid = signup_and_login()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Start a short session
    r = requests.post(f"{BASE}/api/challenge/start-session", headers=headers, timeout=TIMEOUT, json={
        "user_id": uid, "topic": "Geography", "starting_level": 1
    })
    r.raise_for_status()
    sid = r.json()["session_id"]

    # Generate a question
    r = requests.post(f"{BASE}/api/challenge/generate-question", headers=headers, timeout=TIMEOUT, json={
        "session_id": sid, "user_id": uid, "topic": "Geography", "level": 1
    })
    r.raise_for_status()
    cq = r.json()
    qid = cq["id"]
    opts = cq.get("options") or []
    assert opts, "Expected generated question to include options"
    answer = opts[0]

    responses = [None, None]

    def submit(idx):
        try:
            rr = requests.post(f"{BASE}/api/challenge/submit-answer", headers=headers, timeout=TIMEOUT, json={
                "session_id": sid, "question_id": qid, "user_id": uid,
                "answer": answer, "time_taken": 1.0
            })
            responses[idx] = rr
        except Exception as e:
            responses[idx] = e

    # Fire two submits concurrently to simulate double-click race
    t1 = threading.Thread(target=submit, args=(0,))
    t2 = threading.Thread(target=submit, args=(1,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Ensure both returned a successful response object
    assert isinstance(responses[0], requests.Response), f"First request failed: {responses[0]}"
    assert isinstance(responses[1], requests.Response), f"Second request failed: {responses[1]}"
    assert responses[0].status_code == 200
    assert responses[1].status_code == 200

    a0 = responses[0].json()
    a1 = responses[1].json()

    # Both responses should reference the same stored answer id (idempotent replay)
    assert a0.get("id") and a1.get("id")
    assert a0.get("id") == a1.get("id"), "Duplicate submits did not return the same answer id"

    # Cleanup: end session
    requests.post(f"{BASE}/api/challenge/session/{sid}/end", headers=headers, timeout=TIMEOUT, json={"user_id": uid})
