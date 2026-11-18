# Setup/teardown helper for UI test of planner water tools: creates TEST_ org (gold) + event + planner add-on. Usage: python setup_water_ui.py [cleanup <oid> <email>]
import os, sys, uuid, requests
from pymongo import MongoClient
API = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/") + "/api"
mdb = MongoClient("mongodb://localhost:27017")["test_database"]
sa = requests.Session(); sa.post(f"{API}/auth/login", json={"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"})
if len(sys.argv) > 1 and sys.argv[1] == "cleanup":
    oid, email = sys.argv[2], sys.argv[3]
    name = mdb.organizations.find_one({"id": oid})["nome"]
    print(sa.delete(f"{API}/platform/organizations/{oid}", json={"confirm_name": name}).status_code)
    u = mdb.users.find_one({"email": email})
    if u: print(sa.delete(f"{API}/platform/users/{u.get('user_id') or u.get('id')}").status_code)
    sys.exit()
s = requests.Session(); name = f"TEST_NUOTO UI {uuid.uuid4().hex[:4]}"; email = f"test_nuoto_ui_{uuid.uuid4().hex[:6]}@example.com"
s.post(f"{API}/auth/register-organization", json={"nome": "TEST", "cognome": "NUOTO", "email": email, "password": "TestPlanner2026!", "org_name": name, "telefono": "+393471234567", "accept_terms": True})
oid = s.get(f"{API}/auth/me").json()["org_id"]
sa.put(f"{API}/platform/saas/orgs/{oid}/admin", json={"plan": "gold", "status": "active"})
eid = s.post(f"{API}/events", json={"nome": "TEST Triathlon", "data_inizio": "2026-12-13"}).json()["id"]
s.post(f"{API}/addons/planner/events/{eid}/activate")
print(oid, email, eid)
