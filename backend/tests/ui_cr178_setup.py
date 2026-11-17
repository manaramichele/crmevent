# UI setup helper iteration 178: create/delete a TEST_ org admin (non-SA) for promo/info page checks. Usage: python ui_cr178_setup.py setup|cleanup
import json, os, sys, uuid
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
API = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/") + "/api"
F = "/tmp/cr178.json"
SA = {"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"}

if sys.argv[1] == "setup":
    s = requests.Session()
    email = f"test_cr178_{uuid.uuid4().hex[:8]}@example.com"
    name = f"TEST_CR178_{uuid.uuid4().hex[:6]}"
    r = s.post(f"{API}/auth/register-organization", json={"nome": "Test", "cognome": "CR", "email": email, "password": "TestPass123!",
                                                           "org_name": name, "telefono": "+393331234567", "accept_terms": True})
    assert r.status_code == 200, r.text
    me = s.get(f"{API}/auth/me").json()
    out = {"email": email, "password": "TestPass123!", "org_id": me.get("org_id"), "user_id": me.get("user_id"), "org_name": name}
    json.dump(out, open(F, "w")); print(json.dumps(out))
else:
    out = json.load(open(F))
    sa = requests.Session(); sa.post(f"{API}/auth/login", json=SA)
    print("org", sa.delete(f"{API}/platform/organizations/{out['org_id']}", json={"confirm_name": out["org_name"]}).status_code)
    print("user", sa.delete(f"{API}/platform/users/{out['user_id']}").status_code)
