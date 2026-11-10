# Cleans up ONLY the TEST_ org created by seed_menu_scroll_test.py (by its exact org_id / admin email from /tmp/menuscroll_ids.json)
import json, os, sys
from pymongo import MongoClient
env = dict(l.strip().split("=", 1) for l in open("/app/backend/.env") if "=" in l)
db = MongoClient(env["MONGO_URL"].strip('"'))[env["DB_NAME"].strip('"')]
ids = json.load(open("/tmp/menuscroll_ids.json"))
u = db.users.find_one({"email": ids["email"]})
assert u and ids["email"].startswith("test_"), "user not found"
org = u["org_id"]; uid = u.get("user_id") or u.get("id")
orgdoc = db.organizations.find_one({"$or": [{"id": org}, {"org_id": org}]}, {"name": 1, "nome": 1})
print("org", org, orgdoc)
assert orgdoc and "TEST_" in str(orgdoc), "org name not TEST_"
dry = "--do" not in sys.argv
total = 0
for c in db.list_collection_names():
    q = {"$or": [{"org_id": org}, {"user_id": uid}, {"email": ids["email"]}]}
    n = db[c].count_documents(q)
    if c == "organizations": q = {"$or": [{"id": org}, {"org_id": org}]}; n = db[c].count_documents(q)
    if n:
        print(c, n); total += n
        if not dry: db[c].delete_many(q)
print("total", total, "DRY" if dry else "DELETED")
