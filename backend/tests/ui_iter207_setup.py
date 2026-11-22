# UI setup/cleanup for iteration 207 (Da classificare delete). Usage: python ui_iter207_setup.py setup|cleanup
import os, sys, json, uuid, requests
from pymongo import MongoClient
B = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
EV1, EV2, ORG = "59cced67e8d84c7caef5d0436d072ef8", "72bd01373a3441e2b78b69a92b127530", "42744eae0ca84875b89d86a80e7bd985"
F = "/tmp/ui207.json"
env = dict(l.strip().split("=", 1) for l in open("/app/backend/.env") if "=" in l)
mdb = MongoClient(env["MONGO_URL"].strip('"'))[env["DB_NAME"].strip('"')]
s = requests.Session()
assert s.post(f"{B}/api/auth/login", json={"email": "test_dc_3e68a3@example.com", "password": "TestPass123!"}).ok

if sys.argv[1] == "setup":
    out = {}
    for tag, evs in (("UiDel", [EV1]), ("UiTwo", [EV1, EV2]), ("UiCov", [EV1])):
        p = s.post(f"{B}/api/persons", json={"nome": tag, "cognome": f"TEST_{tag}", "email": f"test_{uuid.uuid4().hex[:8]}@example.com"}).json()
        links = [s.post(f"{B}/api/staff", json={"persona_id": p["id"], "evento_id": e, "categoria": "da_classificare", "stato": "da_contattare"}).json()["id"] for e in evs]
        r = s.put(f"{B}/api/persons/{p['id']}/availability/{EV1}", json={"days": [{"date": "2026-12-20", "fasce": ["mattina", "pomeriggio"]}]})
        out[tag] = {"id": p["id"], "links": links}
    json.dump(out, open(F, "w")); print(json.dumps(out))
else:
    out = json.load(open(F))
    for v in out.values():
        pid = v["id"]
        for c in ("staff", "availabilities", "deleted_requests"):
            mdb[c].delete_many({"org_id": ORG, "persona_id": pid})
        mdb.persons.delete_many({"org_id": ORG, "id": pid})
    print("cleaned")
