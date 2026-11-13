# Cleanup for iteration 154 planner-demo homepage tests (only records created by the test run)
import os
import requests
import pymongo
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
db = pymongo.MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

print("stats today", list(db.planner_demo_stats.find({"evento": {"$in": ["signup", "import"]}}, {"_id": 0})))
s = requests.Session()
s.post(f"{BASE}/api/auth/login", json={"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"})
for org_id, name in [("2ee23cac3a1b4f7a8bffe57c64073b37", "TEST_PDemoUI Org 489480")]:
    r = s.delete(f"{BASE}/api/platform/organizations/{org_id}", json={"confirm_name": name})
    print("org delete", r.status_code, r.text[:200])
print("left planner_projects", db.planner_projects.count_documents({"org_id": "2ee23cac3a1b4f7a8bffe57c64073b37"}),
      "events", db.events.count_documents({"org_id": "2ee23cac3a1b4f7a8bffe57c64073b37"}))
for em in ["test_pdemo_d0523e@example.com", "test_pdemoui_489480@example.com"]:
    u = db.users.find_one({"email": em})
    if u:
        print("memberships", db.memberships.delete_many({"user_id": u["user_id"]}).deleted_count if "memberships" in db.list_collection_names() else "n/a")
        print("user del", em, db.users.delete_one({"email": em}).deleted_count)
print("settings del", db.planner_demo_settings.delete_one({"_id": "main"}).deleted_count)
print("stats TEST_ del", db.planner_demo_stats.delete_many({"valore": {"$in": ["TEST_v", "TEST_rl"]}}).deleted_count)
