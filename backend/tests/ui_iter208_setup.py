# UI setup/cleanup for iteration 208 (bulk fascia filter + mobile delete). Usage: python ui_iter208_setup.py setup|cleanup
import os, sys, json, uuid, requests
from pymongo import MongoClient
B = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
EV1, ORG = "59cced67e8d84c7caef5d0436d072ef8", "42744eae0ca84875b89d86a80e7bd985"
F = "/tmp/ui208.json"
env = dict(l.strip().split("=", 1) for l in open("/app/backend/.env") if "=" in l)
mdb = MongoClient(env["MONGO_URL"].strip('"'))[env["DB_NAME"].strip('"')]
s = requests.Session()
assert s.post(f"{B}/api/auth/login", json={"email": "test_dc_3e68a3@example.com", "password": "TestPass123!"}).ok
if sys.argv[1] == "setup":
    out = {}
    for tag, cat, st in (("BkOk", "volontario", "confermato"), ("BkDc", "da_classificare", "confermato"), ("BkUn", "volontario", "da_contattare"), ("MobDel", "da_classificare", "da_contattare")):
        p = s.post(f"{B}/api/persons", json={"nome": tag, "cognome": f"TEST_{tag}", "email": f"test_{uuid.uuid4().hex[:8]}@example.com"}).json()
        s.post(f"{B}/api/staff", json={"persona_id": p["id"], "evento_id": EV1, "categoria": cat, "stato": st, "ruolo": "" if tag == "MobDel" else "TEST_M208UI"})
        out[tag] = p["id"]
    json.dump(out, open(F, "w")); print(json.dumps(out))
else:
    for pid in json.load(open(F)).values():
        for c in ("staff", "availabilities", "deleted_requests"):
            mdb[c].delete_many({"org_id": ORG, "persona_id": pid})
        mdb.persons.delete_many({"org_id": ORG, "id": pid})
    print("cleaned")
