# Setup for iteration 138: 2 TEST_ events (with/without setup-teardown) + availability links in org_qa_eventi. "cleanup" removes.
import os, sys, requests
from pymongo import MongoClient
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
if "cleanup" in sys.argv:
    for ev in mdb.events.find({"nome": {"$regex": "^TEST_"}, "org_id": "org_qa_eventi"}):
        print(ev["nome"], "avail", mdb.availabilities.delete_many({"evento_id": ev["id"]}).deleted_count,
              "links", mdb.avail_links.delete_many({"evento_id": ev["id"]}).deleted_count)
        mdb.events.delete_one({"id": ev["id"]})
    print("persons", mdb.persons.delete_many({"org_id": "org_qa_eventi", "email": {"$regex": "^test_(ui|avail)138"}}).deleted_count)
    sys.exit()
s = requests.Session()
s.post(f"{BASE}/api/auth/login", json={"email": "qa.eventi@crmeventqa.it", "password": "QaEvents2026!"})
s.headers.update({"X-Org-Id": "org_qa_eventi"})
e1 = s.post(f"{BASE}/api/events", json={"nome": "TEST_AV138_SETUP", "data_inizio_allestimento": "2026-11-08", "data_inizio": "2026-11-10",
                                        "data_fine": "2026-11-11", "data_fine_disallestimento": "2026-11-13", "localita": "Milano"}).json()
e2 = s.post(f"{BASE}/api/events", json={"nome": "TEST_AV138_PLAIN", "data_inizio": "2026-12-01", "data_fine": "2026-12-03", "localita": "Roma"}).json()
c1 = s.post(f"{BASE}/api/events/{e1['id']}/availability/link").json()["code"]
c2 = s.post(f"{BASE}/api/events/{e2['id']}/availability/link").json()["code"]
print(f"E1={e1['id']} C1={c1}\nE2={e2['id']} C2={c2}")
