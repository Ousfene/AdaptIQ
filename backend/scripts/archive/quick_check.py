import requests
T = 30

print("Health:", requests.get("http://localhost:8000/health", timeout=5).json()["status"])

login = requests.post("http://localhost:8000/api/auth/login", 
    json={"email":"testscholar@gmail.com","password":"TestPass123!"}, timeout=10).json()
H = {"Authorization": f"Bearer {login['access_token']}"}

for ep in ["/api/admin/db/table/users", "/api/admin/monitoring", 
           "/api/admin/governance/blocked-rules", "/api/admin/governance/audits"]:
    try:
        r = requests.get(f"http://localhost:8000{ep}", headers=H, timeout=T)
        print(f"  {ep}: {r.status_code}")
    except:
        print(f"  {ep}: TIMEOUT")

# Security
r = requests.get("http://localhost:8000/api/auth/me", timeout=10)
print(f"  No token: {r.status_code}")
r = requests.get("http://localhost:8000/api/auth/me", headers={"Authorization":"Bearer bad"}, timeout=10)
print(f"  Bad token: {r.status_code}")

# Daily trend
r = requests.get("http://localhost:8000/api/auth/stats/daily-trend?days=7", headers=H, timeout=10)
today = r.json()["points"][-1]
cnt = today["count"]
cor = today["correct"]
pts = today["points"]
print(f"  Daily trend today: {cnt}q {cor}c {pts}p")
print("ALL DONE")
