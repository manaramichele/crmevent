"""Tests the immediate STOP + reconcile of the demo funnel enrollment (preview)."""
import os, re, datetime as dt
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
API_URL = re.search(r"REACT_APP_BACKEND_URL=(.+)", open("/app/frontend/.env").read()).group(1).strip()
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
SUPER = {"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"}
now = dt.datetime.now(dt.timezone.utc).isoformat()

def mk_enrollment(lead_id, email):
    db.leads.delete_many({"id": lead_id}); db.funnel_enrollments.delete_many({"lead_id": lead_id})
    db.leads.insert_one({"id": lead_id, "email": email, "funnel_status": "demo_started", "user_id": None, "created_at": now})
    steps = [{"step": 1, "template_key": "demo_1", "scheduled_at": now, "sent_at": now, "status": "sent", "brevo_message_id": "m1", "error": None}]
    for i, d in [(2, 1), (3, 3), (4, 6)]:
        steps.append({"step": i, "template_key": f"demo_{i}", "scheduled_at": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=d)).isoformat(),
                      "sent_at": None, "status": "scheduled", "brevo_message_id": None, "error": None})
    db.funnel_enrollments.insert_one({"id": "enr_" + lead_id, "funnel_key": "demo", "lead_id": lead_id, "email": email,
                                      "status": "active", "stop_reason": None, "entered_at": now, "steps": steps, "created_at": now, "updated_at": now})

s = requests.Session()
assert s.post(f"{API_URL}/api/auth/login", json=SUPER).status_code == 200

# --- Test A: lead_funnel trial_started → immediate stop ---
LID = "lead_stoptest_A"
mk_enrollment(LID, "stoptestA@example.it")
r = requests.post(f"{API_URL}/api/leads/{LID}/funnel", json={"status": "trial_started"}); assert r.status_code == 200, r.text
enr = db.funnel_enrollments.find_one({"id": "enr_" + LID})
assert enr["status"] == "stopped" and enr["stop_reason"] == "trial_started" and enr.get("stopped_at"), enr
assert all(st["status"] == "canceled" for st in enr["steps"] if st["step"] in (2, 3, 4)), enr["steps"]
assert enr["steps"][0]["status"] == "sent"
print("TEST A lead_funnel trial_started → enrollment stopped + steps 2/3/4 canceled: PASS")

# --- Test B: idempotency (second call, no error, no change) ---
r = requests.post(f"{API_URL}/api/leads/{LID}/funnel", json={"status": "trial_started"}); assert r.status_code == 200
enr2 = db.funnel_enrollments.find_one({"id": "enr_" + LID})
assert enr2["status"] == "stopped" and sum(1 for st in enr2["steps"] if st["status"] == "canceled") == 3
print("TEST B idempotent re-stop: PASS")

# --- Test C: reconcile closes converted lead (user_id set, funnel_status=demo_started) ---
LID2 = "lead_recon_C"
mk_enrollment(LID2, "reconC@example.it")
db.leads.update_one({"id": LID2}, {"$set": {"user_id": "user_fake_123"}})  # converted, but funnel_status still demo_started
r = requests.post(f"{API_URL}/api/platform/funnels/demo/reconcile", cookies=s.cookies); assert r.status_code == 200, r.text
enrc = db.funnel_enrollments.find_one({"id": "enr_" + LID2})
assert enrc["status"] == "stopped" and enrc["stop_reason"] == "trial_started", enrc
assert all(st["status"] == "canceled" for st in enrc["steps"] if st["step"] in (2, 3, 4))
leadc = db.leads.find_one({"id": LID2})
assert leadc["funnel_status"] == "trial_started" and leadc.get("funnel_ts_trial_started"), leadc
print("TEST C reconcile closes converted lead + normalises status: PASS")

# --- Test D: reconcile idempotent (already stopped → no active left) ---
r = requests.post(f"{API_URL}/api/platform/funnels/demo/reconcile", cookies=s.cookies); assert r.status_code == 200
print("TEST D reconcile idempotent: PASS (closed=%s)" % r.json()["closed"])

# cleanup
for lid in (LID, LID2):
    db.leads.delete_many({"id": lid}); db.funnel_enrollments.delete_many({"lead_id": lid})
print("\nALL STOP/RECONCILE TESTS PASSED")
