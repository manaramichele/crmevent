# Cleanup for test_access_monitor.py when run with KEEP_ACCESS_TEST_DATA=1 (deletes only ids recorded in /tmp/access_test_created.json).
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("KEEP_ACCESS_TEST_DATA", "0")
import test_access_monitor as T  # noqa: E402  (cleanup() also removes audit rows)

created = json.load(open("/tmp/access_test_created.json"))
emails = [u["email"] for u in T.db.users.find({"user_id": {"$in": created["users"]}}, {"email": 1})]
T.cleanup(created)
a = T.db.audit_logs.delete_many({"$or": [{"target_email": {"$in": emails}}, {"org_id": {"$in": created["orgs"]}}]})
print("deleted audit rows:", a.deleted_count)
for c in ("users", "memberships", "access_users", "access_logins", "access_sessions", "access_reminders"):
    print(c, T.db[c].count_documents({"user_id": {"$in": created["users"]}}))
print("orgs", T.db.organizations.count_documents({"id": {"$in": created["orgs"]}}))
print("access_runs", T.db.access_runs.count_documents({}))
print("config", T.db.access_reminder_config.find_one({}, {"_id": 0}))
