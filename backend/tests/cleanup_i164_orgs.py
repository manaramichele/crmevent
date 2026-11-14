# Deletes TEST_I164 orgs recorded in /tmp/i164_orgs.json (created by test_iter164_routes_staff_videodel.py with KEEP_ORG=1)
import json
import os

import requests
from pymongo import MongoClient

API = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/") + "/api"
mdb = MongoClient(os.environ.get("MONGO_URL"))[os.environ.get("DB_NAME")]
s = requests.Session()
s.post(f"{API}/auth/login", json={"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"})
for k, v in json.load(open("/tmp/i164_orgs.json")).items():
    org = mdb.organizations.find_one({"id": v["oid"]}, {"nome": 1, "name": 1})
    if not org:
        print(k, "already deleted")
        continue
    name = org.get("nome") or org.get("name")
    print(k, v["oid"], name, s.delete(f"{API}/platform/organizations/{v['oid']}", json={"confirm_name": name}).status_code)
