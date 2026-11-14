# Setup/teardown helper for Event Map races UI test: `python em_races_ui_setup.py setup|teardown`
import io
import json
import os
import sys
import uuid

import requests
from pymongo import MongoClient

API = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/") + "/api"
SA = ("manara.michele.pro@gmail.com", "CrmEvent2026!")
F = "/tmp/em_races_ui.json"
GPX = open(os.path.join(os.path.dirname(__file__), "fixtures", "pisa_run.gpx"), "rb").read()


def login(e, p):
    s = requests.Session()
    assert s.post(f"{API}/auth/login", json={"email": e, "password": p}).status_code == 200
    return s


if sys.argv[1] == "setup":
    sa = login(*SA)
    s = requests.Session()
    em, name = f"test_emui_{uuid.uuid4().hex[:8]}@example.com", f"TEST_EMUI {uuid.uuid4().hex[:4]}"
    r = s.post(f"{API}/auth/register-organization", json={"nome": "TEST", "cognome": "UI", "email": em, "password": "TestEventMap2026!",
                                                          "org_name": name, "telefono": "+393471234567", "accept_terms": True})
    assert r.status_code in (200, 201), r.text
    oid = s.get(f"{API}/auth/me").json()["org_id"]
    sa.put(f"{API}/platform/saas/orgs/{oid}/admin", json={"plan": "silver", "status": "active"})
    eid = s.post(f"{API}/events", json={"nome": "TEST_UI Pisa Run", "data_inizio": "2026-12-13"}).json()["id"]
    sa.post(f"{API}/platform/addons/orgs/{oid}/grants", json={"product": "eventmap", "events_total": 1, "videos_total": 3, "note": "TEST_ui"})
    assert s.post(f"{API}/addons/eventmap/events/{eid}/activate").status_code == 200
    for n, d in (("Maratona.gpx", GPX), ("Mezza.gpx", GPX.replace(b"</gpx>", b"<!-- m --></gpx>"))):
        assert s.post(f"{API}/eventmap/events/{eid}/tracks", files={"file": (n, io.BytesIO(d), "application/gpx+xml")}).status_code == 200
    json.dump({"oid": oid, "name": name, "email": em, "pw": "TestEventMap2026!", "eid": eid}, open(F, "w"))
    print(json.load(open(F)))
else:
    d = json.load(open(F))
    sa = login(*SA)
    print(sa.delete(f"{API}/platform/organizations/{d['oid']}", json={"confirm_name": d["name"]}).text[:300])
    db = MongoClient("mongodb://localhost:27017")["test_database"]
    print("orphan races removed", db.eventmap_races.delete_many({"org_id": d["oid"]}).deleted_count)
