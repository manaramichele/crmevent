# Setup for addon UI tests: fresh Silver org with 2 events + trial org; also checks 'purchased' counter with abandoned checkouts
import os, uuid, json, requests
API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
sa = requests.Session(); sa.post(f"{API}/auth/login", json={"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"})
out = {}
for label in ("UISilver", "UITrial"):
    s = requests.Session(); em = f"test_addon_{label.lower()}_{uuid.uuid4().hex[:6]}@example.com"
    s.post(f"{API}/auth/register-organization", json={"nome": "TEST", "cognome": "UI", "email": em, "password": "TestAddon2026!",
           "org_name": f"TEST_Addon {label}", "telefono": "+393471234567", "accept_terms": True})
    me = s.get(f"{API}/auth/me").json(); oid = me.get("org_id") or me["user"]["org_id"]
    evs = [s.post(f"{API}/events", json={"nome": f"TEST_UI_Ev{i}", "data_inizio": f"2026-12-1{i}"}).json()["id"] for i in (1, 2)]
    if label == "UISilver":
        sa.put(f"{API}/platform/saas/orgs/{oid}/admin", json={"plan": "silver", "status": "active"})
    out[label] = {"email": em, "org_id": oid, "events": evs}
# purchased counter check on a 3rd org (abandoned checkouts)
cfg = sa.get(f"{API}/platform/addons/config").json()
body = {"planner_included": cfg["planner"]["included"], "planner_price": 10.0, "eventmap_included": cfg["eventmap"]["included"],
        "eventmap_included_videos": cfg["eventmap"].get("included_videos", 0), "eventmap_packages": cfg["eventmap"].get("packages") or []}
s = requests.Session(); em = f"test_addon_purch_{uuid.uuid4().hex[:6]}@example.com"
s.post(f"{API}/auth/register-organization", json={"nome": "TEST", "cognome": "P", "email": em, "password": "TestAddon2026!",
       "org_name": "TEST_Addon Purch", "telefono": "+393471234567", "accept_terms": True})
me = s.get(f"{API}/auth/me").json(); oid = me.get("org_id") or me["user"]["org_id"]
e = s.post(f"{API}/events", json={"nome": "TEST_P", "data_inizio": "2026-12-01"}).json()["id"]
sa.put(f"{API}/platform/saas/orgs/{oid}/admin", json={"plan": "bronze", "status": "active"})
s.put(f"{API}/account/billing", json={"tipo": "azienda", "paese": "IT", "ragione_sociale": "TEST_Srl", "partita_iva": "01234567890", "indirizzo": "Via Roma 1",
      "cap": "20100", "citta": "Milano", "provincia": "MI", "codice_sdi": "0000000"})
try:
    sa.put(f"{API}/platform/addons/config", json=body)
    for _ in range(3):
        print("checkout", s.post(f"{API}/addons/planner/checkout", json={"origin_url": "https://x", "event_id": e}).status_code)
    st = s.get(f"{API}/addons/planner").json()
    print("purchased counter after 3 unpaid checkouts:", st["purchased"], "grant_free:", st["grant_free"])
    row = next(x for x in sa.get(f"{API}/platform/addons/orgs").json() if x["id"] == oid)
    print("SA row planner:", row["planner"])
finally:
    body["planner_price"] = cfg["planner"].get("price")
    print("restore", sa.put(f"{API}/platform/addons/config", json=body).status_code, "price now", sa.get(f"{API}/platform/addons/config").json()["planner"]["price"])
out["Purch"] = {"email": em, "org_id": oid}
print(json.dumps(out))
json.dump(out, open("/tmp/ui_addon.json", "w"))
