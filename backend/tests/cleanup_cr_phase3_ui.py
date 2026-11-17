# Cleanup for Control Room Phase 3 UI test data: annul TEST_UI interventions, revoke invites of / delete TEST_UI resources
import os, requests
from dotenv import load_dotenv
load_dotenv("/app/frontend/.env")
API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
OPS = f"{API}/controlroom/events/2ffc1b48b9f34bf9901da7aa1eb7f0b7/ops"
s = requests.Session()
s.post(f"{API}/auth/login", json={"email": "test_cr_a@crmevent-test.it", "password": "TestCR2026!"})
s.headers["Authorization"] = f"Bearer {s.cookies.get('access_token')}"
d = s.get(OPS).json()
for i in d["interventions"]:
    if i["descrizione"].startswith("TEST_UI") and i["stato"] not in ("chiuso", "annullato"):
        r = s.post(f"{OPS}/interventions/{i['id']}/status", json={"to": "annullato", "motivo": "TEST cleanup", "force": True, "note": "cleanup", "version": i["version"]})
        print("annul", i["codice"], r.status_code)
ids = {x["id"] for x in d["resources"] if (x.get("nome") or "").startswith("TEST_UI")}
for inv in d.get("invites", []):
    if inv["resource_id"] in ids and not inv.get("revoked_at"):
        print("revoke", s.delete(f"{OPS}/invites/{inv['id']}").status_code)
for rid in ids:
    print("del res", s.delete(f"{OPS}/resources/{rid}").status_code)
d = s.get(OPS).json()
print("open", [(i["codice"], i["descrizione"]) for i in d["interventions"] if i["stato"] not in ("chiuso", "annullato")])
print("resources", [x.get("nome") for x in d["resources"]])
