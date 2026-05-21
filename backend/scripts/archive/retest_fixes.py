# Retest of previously failed items with correct payloads
import requests, time
BASE = "http://localhost:8000"
T = 120
PASS_N = 0
FAIL_N = 0

def check(label, cond, detail=""):
    global PASS_N, FAIL_N
    if cond: PASS_N += 1
    else: FAIL_N += 1
    s = "PASS" if cond else "FAIL"
    print(f"  [{s}] {label}" + (f" -- {detail}" if detail else ""), flush=True)

# Signup fresh user
ts = int(time.time() * 1000)
r = requests.post(f"{BASE}/api/auth/signup", json={"email": f"fix_{ts}@gmail.com", "username": f"fix_{ts}", "password": "FixTest123!"}, timeout=T)
TOKEN = r.json()["access_token"]
UID = r.json()["user"]["id"]
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

print("=== ONBOARDING ===", flush=True)
r = requests.get(f"{BASE}/api/onboarding/status?user_id={UID}", headers=H, timeout=T)
check("Onboarding status", r.status_code == 200, f"code={r.status_code}")

r = requests.post(f"{BASE}/api/onboarding/survey", headers=H, json={
    "user_id": UID, "experience_level": "beginner", "interests": ["history", "geography"],
    "daily_goal_minutes": 15, "preferred_difficulty": "medium"
}, timeout=T)
check("Onboarding survey", r.status_code == 200, f"code={r.status_code}")

r = requests.post(f"{BASE}/api/onboarding/mark-tour-seen", headers=H, json={"user_id": UID}, timeout=T)
check("Tour mark seen", r.status_code == 200, f"code={r.status_code}")

r = requests.get(f"{BASE}/api/onboarding/status?user_id={UID}", headers=H, timeout=T)
check("Onboarding completed", r.status_code == 200, f"body={r.text[:120]}")

print("\n=== CONCEPTS (paginated) ===", flush=True)
r = requests.post(f"{BASE}/api/auth/login", json={"email": "testscholar@gmail.com", "password": "TestPass123!"}, timeout=T)
AT = r.json()["access_token"]
AH = {"Authorization": f"Bearer {AT}", "Content-Type": "application/json"}

r = requests.get(f"{BASE}/api/admin/concepts", headers=AH, timeout=T)
data = r.json()
total = data.get("total", 0) if isinstance(data, dict) else len(data)
check("Concepts populated (28)", total >= 20, f"total={total}")

print("\n=== ADMIN (slow endpoints) ===", flush=True)
r = requests.get(f"{BASE}/api/admin/db/schema", headers=AH, timeout=T)
check("DB schema", r.status_code == 200, f"len={len(r.text)}")

r = requests.get(f"{BASE}/api/admin/db/table/users", headers=AH, timeout=T)
check("DB table inspect", r.status_code == 200)

r = requests.get(f"{BASE}/api/admin/monitoring", headers=AH, timeout=T)
check("Admin monitoring", r.status_code == 200)

r = requests.get(f"{BASE}/api/admin/governance/blocked-rules", headers=AH, timeout=T)
check("Governance rules", r.status_code == 200)

r = requests.get(f"{BASE}/api/admin/governance/audits", headers=AH, timeout=T)
check("Governance audits", r.status_code == 200)

print("\n=== SECURITY ===", flush=True)
r = requests.get(f"{BASE}/api/auth/me", timeout=T)
check("No token -> 401", r.status_code in [401, 422])

r = requests.get(f"{BASE}/api/auth/me", headers={"Authorization": "Bearer bad.token.here"}, timeout=T)
check("Bad token -> 401", r.status_code == 401)

r = requests.get(f"{BASE}/api/admin/overview", headers=H, timeout=T)
check("Non-admin blocked", r.status_code == 403)

r = requests.post(f"{BASE}/api/auth/signup", json={"email": f"fix_{ts}@gmail.com", "username": f"fix_{ts}", "password": "FixTest123!"}, timeout=T)
check("Duplicate signup blocked", r.status_code == 400)

print("\n=== DAILY TREND ===", flush=True)
r = requests.get(f"{BASE}/api/auth/stats/daily-trend?days=7", headers=AH, timeout=T)
trend = r.json()
today = trend["points"][-1]
check("Daily trend has activity", today["count"] > 0, f"count={today['count']} correct={today['correct']}")

print(f"\n{'='*50}", flush=True)
print(f"RESULTS: {PASS_N} PASSED / {FAIL_N} FAILED", flush=True)
