# Shared setup/cleanup helpers for Super Admin "book demo on behalf" tests (TEST_ data only)
import os
import time
import uuid
from datetime import datetime, timezone

import bcrypt
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0].strip('"').rstrip("/")
SA_EMAIL, SA_PW = "manara.michele.pro@gmail.com", "CrmEvent2026!"
PW = "TestPass123!"


def mdb():
    env = dict(l.split("=", 1) for l in open("/app/backend/.env").read().splitlines() if "=" in l)
    return MongoClient(env["MONGO_URL"].strip('"'))[env["DB_NAME"].strip('"')]


def login(email, pw):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    tok = r.json().get("token") or r.json().get("access_token")
    if tok:
        s.headers["Authorization"] = f"Bearer {tok}"
    return s


def open_config(sa):
    r = sa.put(f"{BASE_URL}/api/platform/demo/config", json={"weekly": [{"weekday": d, "start": "09:00", "end": "18:00"} for d in range(7)],
                                                          "closed_dates": [], "min_notice_hours": 0, "horizon_days": 30})
    assert r.status_code == 200, r.text


def setup_org(tag):
    """Owner via API + 2 extra members inserted directly (membership role 'user')."""
    ts = f"{tag.lower()}{int(time.time())}"
    owner_email = f"test_demo_owner_{ts}@example.com"
    r = requests.post(f"{BASE_URL}/api/auth/register-organization", json={"nome": "Owner", "cognome": f"Test{tag}", "email": owner_email, "password": PW,
                                                                          "org_name": f"TEST_DemoOrg_{ts}", "telefono": "+393471234567", "accept_terms": True})
    assert r.status_code == 200, r.text
    db = mdb()
    owner = db.users.find_one({"email": owner_email}, {"_id": 0})
    org_id = owner["org_id"]
    members = []
    for i in (2, 3):
        uid, email, now = f"user_{uuid.uuid4().hex[:12]}", f"test_demo_member{i}_{ts}@example.com", datetime.now(timezone.utc).isoformat()
        db.users.insert_one({"user_id": uid, "email": email, "name": f"Membro{i} Test{tag}", "nome": f"Membro{i}", "cognome": f"Test{tag}",
                             "password_hash": bcrypt.hashpw(PW.encode(), bcrypt.gensalt()).decode(), "role": "member", "auth_provider": "password",
                             "org_id": org_id, "active": True, "created_at": now, "welcome_demo": "dismissed", "telefono": "+393471112233", "accepted_terms_at": now})
        db.memberships.insert_one({"id": uuid.uuid4().hex, "user_id": uid, "org_id": org_id, "role": "user", "active": True, "permissions": {},
                                   "created_at": now, "updated_at": now})
        members.append({"user_id": uid, "email": email})
    return {"org_id": org_id, "owner": {"user_id": owner["user_id"], "email": owner_email}, "m2": members[0], "m3": members[1]}


def cleanup(ctx):
    db = mdb()
    uids = [ctx["owner"]["user_id"], ctx["m2"]["user_id"], ctx["m3"]["user_id"]]
    emails = [ctx["owner"]["email"], ctx["m2"]["email"], ctx["m3"]["email"]]
    lead_ids = [l["id"] for l in db.leads.find({"$or": [{"email": {"$in": emails}}, {"org_id": ctx["org_id"]}]}, {"id": 1})]
    db.demo_slot_locks.delete_many({"lead_id": {"$in": lead_ids}})
    db.leads.delete_many({"id": {"$in": lead_ids}})
    db.demo_requests.delete_many({"$or": [{"org_id": ctx["org_id"]}, {"email": {"$in": emails}}]})
    db.support_sessions.delete_many({"org_id": ctx["org_id"]})
    db.memberships.delete_many({"org_id": ctx["org_id"]})
    db.user_sessions.delete_many({"user_id": {"$in": uids}})
    db.users.delete_many({"user_id": {"$in": uids}})
    for c in ("subscriptions", "org_settings", "audit_logs", "saas_brevo_sync"):
        db[c].delete_many({"org_id": ctx["org_id"]})
    db.organizations.delete_many({"id": ctx["org_id"]})
    for c in ("saas_brevo_sync", "brevo_tracker_log"):
        db[c].delete_many({"email": {"$in": emails}})
