# Setup/cleanup helper for Gruppo di appartenenza UI tests (Nova org). Usage: python tests/ui_gruppi_setup.py setup|cleanup
import sys, bcrypt
sys.path.insert(0, "/app/backend/tests")
import os
os.environ.setdefault("REACT_APP_BACKEND_URL", "x")
from test_gruppi_appartenenza import _mongo
db = _mongo()
ORG = "nova_events_test_org"
UID, EMAIL, PW = "TEST_ui_gr_admin", "test_ui_gr_admin@example.com", "TestGr2026!"
if sys.argv[1] == "setup":
    if not db.users.find_one({"user_id": UID}):
        db.users.insert_one({"user_id": UID, "email": EMAIL, "name": "TEST_ UI Gr Admin", "role": "admin", "org_id": ORG, "auth_provider": "password",
                             "active": True, "password_hash": bcrypt.hashpw(PW.encode(), bcrypt.gensalt()).decode()})
        db.memberships.insert_one({"id": f"TEST_m_{UID}", "user_id": UID, "org_id": ORG, "role": "admin_org", "active": True})
    for p in db.persons.find({"org_id": ORG, "nome": {"$regex": "^TEST_"}}, {"_id": 0, "id": 1, "nome": 1, "email": 1, "gruppo_appartenenza": 1}):
        print(p)
    print(db.settings.find_one({"id": ORG}, {"_id": 0, "gruppi_appartenenza": 1}))
else:
    emails = ["test_ui_gr_a@example.com", "test_ui_gr_b@example.com"]
    for p in db.persons.find({"org_id": ORG, "email": {"$in": emails}}, {"id": 1}):
        for c in ("availabilities", "staff"):
            db[c].delete_many({"org_id": ORG, "persona_id": p["id"]})
        db.persons.delete_one({"org_id": ORG, "id": p["id"]})
    db.settings.update_one({"id": ORG}, {"$pull": {"gruppi_appartenenza": {"$regex": "^TEST_"}}})
    db.memberships.delete_many({"user_id": UID}); db.users.delete_many({"user_id": UID})
    for c in ("access_users", "access_logins", "access_sessions", "user_sessions"):
        db[c].delete_many({"user_id": UID})
    print("cleaned")
