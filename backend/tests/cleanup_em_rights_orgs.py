# Cleanup of TEST_EMR orgs created by test_eventmap_rights_iter.py (by id only, preview DB).
import json
import shutil
import os
import requests
from pymongo import MongoClient

API = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/") + "/api"
mdb = MongoClient("mongodb://localhost:27017")["test_database"]
orgs = json.load(open("/tmp/em_rights_orgs.json"))
sa = requests.Session()
sa.post(f"{API}/auth/login", json={"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"})
for o in orgs.values():
    assert o["name"].startswith("TEST_")
    for c in ("addon_grants", "addon_activations", "addon_usage", "eventmap_tracks", "eventmap_videos"):
        mdb[c].delete_many({"org_id": o["id"]})
    real = (mdb.organizations.find_one({"id": o["id"]}) or {}).get("nome") or o["name"]
    assert real.startswith("TEST_"), real
    r = sa.delete(f"{API}/platform/organizations/{o['id']}", json={"confirm_name": real})
    mdb.users.delete_one({"email": o["email"], "org_id": None})
    shutil.rmtree(f"/app/backend/storage_data/eventmap/{o['id']}", ignore_errors=True)
    print(o["name"], r.status_code, r.text[:200])
