# Iter 204 UI fixture: TEST org + event with fasce, staff (public form), volunteer, legacy person. `python ui_iter204_setup.py clean` to remove.
import json
import os
import sys
import uuid

import requests
from pymongo import MongoClient

BASE = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0].rstrip("/")
ENV = dict(l.strip().split("=", 1) for l in open("/app/backend/.env") if "=" in l)
mdb = MongoClient(ENV["MONGO_URL"].strip('"'))[ENV["DB_NAME"].strip('"')]
STATE = "/tmp/ui204.json"
D1, D2 = "2026-12-19", "2026-12-20"
SL = {"mattina": {"attiva": True, "start": "08:00", "end": "13:00"}, "pomeriggio": {"attiva": True, "start": "13:00", "end": "20:00"}}

if len(sys.argv) > 1 and sys.argv[1] == "clean":
    st = json.load(open(STATE))
    org = st["org"]
    for c in ("availabilities", "staff", "avail_links", "events", "persons", "teams", "audit_log", "audit_logs"):
        mdb[c].delete_many({"org_id": org})
    mdb.settings.delete_many({"id": org})
    mdb.memberships.delete_many({"org_id": org})
    mdb.organizations.delete_many({"id": org})
    mdb.users.delete_many({"email": st["email"]})
    print("cleaned", org)
    sys.exit(0)

tag = uuid.uuid4().hex[:6]
s = requests.Session()
email = f"test_ui204_{tag}@example.com"
r = s.post(f"{BASE}/api/auth/register-organization", json={"nome": "Test", "cognome": "Ui", "email": email, "password": "TestPass123!",
                                                           "org_name": f"TEST_UI204_{tag}", "telefono": "+39 333 1111111", "accept_terms": True})
assert r.status_code == 200, r.text
org = mdb.users.find_one({"email": email})["org_id"]
ev = s.post(f"{BASE}/api/events", json={"nome": f"TEST_Ev Copertura {tag}", "data_inizio": D1, "data_fine": D2, "stato": "pianificato",
                                        "fasce_disponibilita": {D1: SL, D2: SL}}).json()["id"]
ev2 = s.post(f"{BASE}/api/events", json={"nome": f"aTEST_Ev Altro {tag}", "data_inizio": D1, "data_fine": D1, "stato": "pianificato", "fasce_disponibilita": {D1: SL}}).json()["id"]
for nm in ("zeta team", "Alfa", "beta", "Delta"):
    s.post(f"{BASE}/api/teams", json={"nome": nm, "evento_id": ev})
s.post(f"{BASE}/api/teams", json={"nome": "AAA_OtherEvent", "evento_id": ev2})
code = s.post(f"{BASE}/api/events/{ev}/availability/link").json()["code"]
pub = {"nome": "TEST_Staffpub", "cognome": "TEST_Uno", "cellulare": "+39 333 2223334", "email": f"test_sp_{tag}@example.com", "data_nascita": "1990-01-01",
       "days": [{"date": D1, "disponibile": True, "fasce": ["mattina"]}, {"date": D2, "disponibile": True, "fasce": ["mattina", "pomeriggio"]}],
       "preferenza_attivita": "Altro", "preferenza_altro": "TEST", "privacy": True}
pr = requests.post(f"{BASE}/api/public/availability/{code}", json=pub, headers={"X-Forwarded-For": f"10.99.{int(tag[:2],16)}.1"})
assert pr.status_code == 200, pr.text
sp = mdb.availabilities.find_one({"org_id": org, "submitted.email": pub["email"]})["persona_id"]
links = [x for x in s.get(f"{BASE}/api/staff").json() if x["persona_id"] == sp]
if links:
    s.put(f"{BASE}/api/staff/{links[0]['id']}", json={"persona_id": sp, "evento_id": ev, "categoria": "staff"})
else:
    s.post(f"{BASE}/api/staff", json={"persona_id": sp, "evento_id": ev, "categoria": "staff"})
vol = s.post(f"{BASE}/api/persons", json={"nome": "TEST_Volo", "cognome": "TEST_Due"}).json()["id"]
s.post(f"{BASE}/api/staff", json={"persona_id": vol, "evento_id": ev, "categoria": "volontario"})
leg = s.post(f"{BASE}/api/persons", json={"nome": "TEST_Legacy", "cognome": "TEST_Tre"}).json()["id"]
s.post(f"{BASE}/api/staff", json={"persona_id": leg, "evento_id": ev, "categoria": "staff"})
mdb.availabilities.insert_one({"id": f"TEST_leg_{tag}", "org_id": org, "evento_id": ev, "persona_id": leg,
                               "days": [{"date": D1, "fase": "evento", "dalle": "08:00", "alle": "13:00"},
                                        {"date": D2, "fase": "evento", "dalle": "10:00", "alle": "15:00"}],
                               "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00"})
st = {"org": org, "email": email, "pwd": "TestPass123!", "ev": ev, "ev2": ev2, "sp": sp, "vol": vol, "leg": leg, "leg_av": f"TEST_leg_{tag}", "tag": tag}
json.dump(st, open(STATE, "w"))
print(json.dumps(st))
