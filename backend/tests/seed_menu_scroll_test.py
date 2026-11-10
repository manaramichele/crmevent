# Seeds TEST_ org with event, 2 events, 1 person, presence and 18 teams for dropdown-scroll UI testing
import os, json, uuid, requests

BASE = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0].rstrip("/")
s = requests.Session()
email = f"test_menuscroll_{uuid.uuid4().hex[:6]}@example.com"
pw = "TestPass123!"
r = s.post(f"{BASE}/api/auth/register-organization", json={"nome": "TEST_Menu", "cognome": "Scroll", "email": email,
           "password": pw, "org_name": "TEST_MenuScroll Org", "telefono": "+393331234567", "accept_terms": True})
print("register", r.status_code, r.text[:200])
ids = {"email": email, "password": pw, "events": [], "teams": [], "persons": [], "staff": []}
for i in range(12):
    e = s.post(f"{BASE}/api/events", json={"nome": f"TEST_Evento {i:02d}"})
    if e.status_code >= 300:
        print("event", e.status_code, e.text[:200]); break
    ids["events"].append(e.json()["id"])
ev = ids["events"][0]
p = s.post(f"{BASE}/api/persons", json={"nome": "TEST_Mario", "cognome": "TEST_Rossi", "email": "test_mario_ms@example.com"})
print("person", p.status_code, p.text[:150])
pid = p.json()["id"]; ids["persons"].append(pid)
st = s.post(f"{BASE}/api/staff", json={"persona_id": pid, "evento_id": ev, "categoria": "volontario"})
print("staff", st.status_code, st.text[:150]); ids["staff"].append(st.json().get("id"))
for i in range(18):
    t = s.post(f"{BASE}/api/teams", json={"nome": f"TEST_Team {i:02d}", "evento_id": ev})
    if t.status_code >= 300:
        print("team", t.status_code, t.text[:200]); break
    ids["teams"].append(t.json()["id"])
print(json.dumps({k: (v if not isinstance(v, list) else len(v)) for k, v in ids.items()}))
json.dump(ids, open("/tmp/menuscroll_ids.json", "w"))
