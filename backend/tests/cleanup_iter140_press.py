# Cleanup for iteration 140 press-release testing: removes press data for QA org + TEST_ orgs, TEST_ users/memberships/orgs,
# and deactivates (deletes) org_services comunicati-stampa for org_qa_eventi.
import os

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
test_orgs = [o["id"] for o in db.organizations.find({"nome": {"$regex": "^TEST_Press"}}, {"_id": 0, "id": 1})]
orgs = ["org_qa_eventi", "TEST_press_org"] + test_orgs
for c in ("press_releases", "press_versions", "press_contacts", "press_sends", "press_settings", "press_automations",
          "press_notifications", "press_brevo_lists"):
    print(c, db[c].delete_many({"org_id": {"$in": orgs}}).deleted_count)
print("org_services", db.org_services.delete_many({"org_id": {"$in": orgs}, "service": "comunicati-stampa"}).deleted_count)
uids = [u["user_id"] for u in db.users.find({"$or": [{"email": {"$regex": "^test_press"}}, {"org_id": {"$in": test_orgs}}]}, {"_id": 0, "user_id": 1})]
print("memberships", db.memberships.delete_many({"$or": [{"user_id": {"$in": uids}}, {"org_id": {"$in": test_orgs}}]}).deleted_count)
print("users", db.users.delete_many({"user_id": {"$in": uids}}).deleted_count)
for c in db.list_collection_names():
    if c.startswith("saas_") or c in ("subscriptions", "user_sessions", "audit_logs", "demo_bookings"):
        n = db[c].delete_many({"org_id": {"$in": test_orgs}}).deleted_count
        if n:
            print(c, n)
print("organizations", db.organizations.delete_many({"id": {"$in": test_orgs}}).deleted_count)
