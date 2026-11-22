# Iter 205 UI fixture (white-page regression /staff-volontari): 2 TEST orgs, persons with distinct taglie. `python ui_iter205_setup.py clean` to remove.
import json
import sys
import uuid

import requests
from pymongo import MongoClient

BASE = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0].rstrip("/")
ENV = dict(l.strip().split("=", 1) for l in open("/app/backend/.env") if "=" in l)
mdb = MongoClient(ENV["MONGO_URL"].strip('"'))[ENV["DB_NAME"].strip('"')]
STATE = "/tmp/ui205.json"
D1, D2 = "2026-12-19", "2026-12-20"
SL = {"mattina": {"attiva": True, "start": "08:00", "end": "13:00"}, "pomeriggio": {"attiva": True, "start": "13:00", "end": "20:00"}}

if len(sys.argv) > 1 and sys.argv[1] == "clean":
    st = json.load(open(STATE))
    for o in st["orgs"]:
        org, email = o["org"], o["email"]
        for c in ("availabilities", "staff", "avail_links", "events", "persons", "teams", "audit_log", "audit_logs", "notifications"):
            mdb[c].delete_many({"org_id": org})
        mdb.settings.delete_many({"id": org})
        mdb.memberships.delete_many({"org_id": org})
        mdb.organizations.delete_many({"id": org})
        mdb.users.delete_many({"email": email})
        print("cleaned", org)
    sys.exit(0)


def reg(tag, label):
    s = requests.Session()
    email = f"test_ui205{label.lower()}_{tag}@example.com"
    r = s.post(f"{BASE}/api/auth/register-organization", json={"nome": "Test", "cognome": "Ui", "email": email, "password": "TestPass123!",
                                                               "org_name": f"TEST_UI205{label}_{tag}", "telefono": "+39 333 1111111", "accept_terms": True})
    assert r.status_code == 200, r.text
    return s, email, mdb.users.find_one({"email": email})["org_id"]


tag = uuid.uuid4().hex[:6]
s, email, org = reg(tag, "A")
ev = s.post(f"{BASE}/api/events", json={"nome": f"TEST_EvMain {tag}", "data_inizio": D1, "data_fine": D2, "stato": "pianificato",
                                        "fasce_disponibilita": {D1: SL, D2: SL}}).json()["id"]
ev2 = s.post(f"{BASE}/api/events", json={"nome": f"TEST_EvAltro {tag}", "data_inizio": D1, "data_fine": D1, "stato": "pianificato",
                                         "fasce_disponibilita": {D1: SL}}).json()["id"]
s.post(f"{BASE}/api/teams", json={"nome": "Alfa", "evento_id": ev})
P = {}
for key, nome, tg, evid, cat in (("xl", "TEST_Xlarge", "XL", ev, "staff"), ("m", "TEST_Medium", "M", ev, "volontario"),
                                 ("s", "TEST_Small", "S", ev2, "staff"), ("s2", "TEST_Smallvol", "S", ev2, "volontario")):
    r = s.post(f"{BASE}/api/persons", json={"nome": nome, "cognome": f"TEST_{key}", "taglia": tg})
    assert r.status_code in (200, 201), r.text
    P[key] = r.json()["id"]
    s.post(f"{BASE}/api/staff", json={"persona_id": P[key], "evento_id": evid, "categoria": cat})
uncl = s.post(f"{BASE}/api/persons", json={"nome": "TEST_Nocat", "cognome": "TEST_U", "taglia": "L"}).json()["id"]
av = s.put(f"{BASE}/api/persons/{P['xl']}/availability/{ev}", json={"days": [{"date": D1, "fasce": ["mattina"]}, {"date": D2, "fasce": ["mattina", "pomeriggio"]}]})
assert av.status_code == 200, av.text

sb, emailb, orgb = reg(tag, "B")
evb = sb.post(f"{BASE}/api/events", json={"nome": f"TEST_EvOrgB {tag}", "data_inizio": D1, "data_fine": D1, "stato": "pianificato"}).json()["id"]
pb = sb.post(f"{BASE}/api/persons", json={"nome": "TEST_Orgbonly", "cognome": "TEST_B", "taglia": "XXL"}).json()["id"]
sb.post(f"{BASE}/api/staff", json={"persona_id": pb, "evento_id": evb, "categoria": "staff"})

st = {"orgs": [{"org": org, "email": email}, {"org": orgb, "email": emailb}], "org": org, "orgb": orgb, "email": email, "pwd": "TestPass123!",
      "ev": ev, "ev2": ev2, "evb": evb, "P": P, "uncl": uncl, "pb": pb, "tag": tag}
json.dump(st, open(STATE, "w"))
print(json.dumps(st))
