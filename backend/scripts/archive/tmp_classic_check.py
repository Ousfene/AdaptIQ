import requests

BASE = "http://localhost:8000"

login = requests.post(
    f"{BASE}/api/auth/login",
    json={"email": "challenge.c@example.com", "password": "TestPass123!"},
    timeout=10,
)
login.raise_for_status()
token = login.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

q = requests.post(
    f"{BASE}/api/rooms/classic/questions",
    json={"topic": "history", "difficulty": 2},
    headers=headers,
    timeout=10,
)
print("Q", q.status_code)
qd = q.json()
print("session_id", qd.get("session_id"))
print("question_id", qd.get("id"))
print("question_text", qd.get("text"))
print("options", qd.get("options"))

h = requests.post(
    f"{BASE}/api/rooms/classic/hints",
    json={
        "question_id": qd.get("id"),
        "question_text": qd.get("text"),
        "correct_answer": "",
    },
    headers=headers,
    timeout=10,
)
print("H", h.status_code, h.text[:120])

a = requests.post(
    f"{BASE}/api/rooms/classic/answers",
    json={
        "session_id": qd.get("session_id"),
        "question_id": qd.get("id"),
        "selected_answer": (qd.get("options") or [""])[0],
        "time_taken": 4,
        "used_hint": False,
    },
    headers=headers,
    timeout=10,
)
print("A", a.status_code, a.text[:200])
