# UI setup for iteration 137: TEST_ event + availability link in org_qa_eventi (prints code). Run with "cleanup" to remove.
import os, sys, requests
from pymongo import MongoClient
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
if "cleanup" in sys.argv:
    for ev in mdb.events.find({"nome": {"$regex": "^TEST_"}, "org_id": "org_qa_eventi"}):
        print("avail", mdb.availabilities.delete_many({"evento_id": ev["id"]}).deleted_count,
              "links", mdb.avail_links.delete_many({"evento_id": ev["id"]}).deleted_count)
        mdb.events.delete_one({"id": ev["id"]})
    print("persons", mdb.persons.delete_many({"org_id": "org_qa_eventi", "email": {"$regex": "^test_(ui|avail)137"}}).deleted_count)
    sys.exit()
s = requests.Session()
s.post(f"{BASE}/api/auth/login", json={"email": "qa.eventi@crmeventqa.it", "password": "QaEvents2026!"})
s.headers.update({"X-Org-Id": "org_qa_eventi"})
eid = s.post(f"{BASE}/api/events", json={"nome": "TEST_UI137", "data_inizio_allestimento": "2026-11-08", "data_inizio": "2026-11-10",
                                         "data_fine": "2026-11-11", "data_fine_disallestimento": "2026-11-13", "localita": "Milano"}).json()["id"]
print(s.post(f"{BASE}/api/events/{eid}/availability/link").json()["code"])
