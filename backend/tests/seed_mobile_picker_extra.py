# Adds 15 TEST_ staff persons to event 0 of the menuscroll seed (for StaffAssignSelect/TeamMembersDialog sheet scroll tests)
import json, requests
BASE = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0].rstrip("/")
ids = json.load(open("/tmp/menuscroll_ids.json"))
s = requests.Session(); print(s.post(f"{BASE}/api/auth/login", json={"email": ids["email"], "password": ids["password"]}).status_code)
ev = ids["events"][0]
for i in range(15):
    p = s.post(f"{BASE}/api/persons", json={"nome": f"TEST_N{i:02d}", "cognome": f"TEST_Staff{i:02d}", "email": f"test_staff{i:02d}_mp@example.com"}).json()
    ids["persons"].append(p["id"])
    st = s.post(f"{BASE}/api/staff", json={"persona_id": p["id"], "evento_id": ev, "categoria": "staff" if i % 2 else "volontario"}).json()
    ids["staff"].append(st.get("id"))
json.dump(ids, open("/tmp/menuscroll_ids.json", "w")); print(len(ids["persons"]), len(ids["staff"]))
