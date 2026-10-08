"""Iter 90 — Welcome demo booking (post-registration) + Super Admin demo config."""
import os
import time
import uuid

import pytest
import requests

def _load_env():
    try:
        for ln in open("/app/frontend/.env", "r", encoding="utf-8"):
            if ln.startswith("REACT_APP_BACKEND_URL="):
                return ln.split("=", 1)[1].strip()
    except Exception:
        pass
    return os.environ.get("REACT_APP_BACKEND_URL", "")

BASE = _load_env().rstrip("/")
assert BASE, "REACT_APP_BACKEND_URL not configured"
SA_EMAIL = "manara.michele.pro@gmail.com"
SA_PASSWORD = "CrmEvent2026!"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def sa():
    return _login(SA_EMAIL, SA_PASSWORD)


@pytest.fixture(scope="module")
def created_orgs():
    orgs = []
    yield orgs
    # cleanup via Mongo
    try:
        from pymongo import MongoClient  # noqa
        mu = os.environ.get("MONGO_URL"); dbn = os.environ.get("DB_NAME")
        if mu and dbn:
            cli = MongoClient(mu)
            d = cli[dbn]
            for info in orgs:
                oid = info.get("org_id"); uid = info.get("user_id"); email = info.get("email")
                if oid:
                    d.organizations.delete_many({"id": oid})
                    d.memberships.delete_many({"org_id": oid})
                    d.saas_subscriptions.delete_many({"org_id": oid})
                    d.leads.delete_many({"org_id": oid})
                    d.demo_slot_locks.delete_many({"lead_id": {"$exists": True}, **({"created_at": {"$exists": True}})})
                if uid:
                    d.users.delete_many({"user_id": uid})
                if email:
                    d.users.delete_many({"email": email})
                    d.leads.delete_many({"email": email})
            cli.close()
    except Exception as e:
        print("cleanup error:", e)


def _register(email_prefix: str):
    s = requests.Session()
    email = f"{email_prefix}_{uuid.uuid4().hex[:6]}@crmeventqa.it"
    payload = {
        "nome": "Test", "cognome": "Welcome", "email": email, "password": "TestPass2026!",
        "org_name": f"TEST_WelcomeOrg_{uuid.uuid4().hex[:6]}", "telefono": "+393331112233",
        "accept_terms": True,
    }
    r = s.post(f"{BASE}/api/auth/register-organization", json=payload, timeout=25)
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text}"
    data = r.json()
    return s, data, email


# ============== Registration & welcome_demo flag ==============

def test_register_sets_welcome_demo_pending(created_orgs):
    s, data, email = _register("test_ui_welcome")
    assert data.get("welcome_demo") == "pending"
    assert data.get("role") in ("admin",)
    assert data.get("org_role") == "admin_org"
    created_orgs.append({"org_id": data.get("org_id"), "user_id": data.get("user_id"), "email": email, "session": s})


# ============== /api/demo/welcome info and prefill ==============

def test_demo_welcome_info_prefill(created_orgs):
    s = created_orgs[0]["session"]
    r = s.get(f"{BASE}/api/demo/welcome", timeout=15)
    assert r.status_code == 200
    j = r.json()
    assert j.get("state") == "pending"
    assert j.get("booking") in (None, {})
    assert j.get("duration_min") == 30
    pf = j.get("prefill") or {}
    assert pf.get("email") == created_orgs[0]["email"]
    assert pf.get("nome") == "Test"
    assert pf.get("organizzazione", "").startswith("TEST_WelcomeOrg_")


# ============== Slots are returned ==============

def test_demo_slots_available(created_orgs):
    s = created_orgs[0]["session"]
    r = s.get(f"{BASE}/api/demo/slots", timeout=15)
    assert r.status_code == 200
    slots = r.json().get("slots") or []
    assert isinstance(slots, list)
    assert len(slots) > 0, "Expected at least 1 slot per existing SA config (Mon-Fri 10-12)"
    # Shape
    s0 = slots[0]
    assert "slot_key" in s0 and "T" in s0["slot_key"]
    created_orgs[0]["first_slot"] = s0["slot_key"]


# ============== Book + anti-overlap with video_support ==============

def test_book_demo_and_persistence(created_orgs):
    info = created_orgs[0]
    s = info["session"]
    slot = info["first_slot"]
    r = s.post(f"{BASE}/api/demo/welcome/book",
               json={"slot_key": slot, "nome": "Test", "cognome": "Welcome",
                     "telefono": "+393331112233", "organizzazione": "TEST_WelcomeOrg"}, timeout=25)
    assert r.status_code == 200, f"book failed {r.status_code} {r.text}"
    j = r.json()
    assert j.get("ok") is True
    assert j.get("slot_key") == slot
    assert j.get("meet_link", "").startswith(("https://meet.google.com/", "https://"))
    # Welcome re-check -> booking present
    r2 = s.get(f"{BASE}/api/demo/welcome", timeout=10)
    j2 = r2.json()
    assert j2.get("booking") is not None
    assert j2.get("booking", {}).get("demo_slot") == slot
    # welcome_demo flag turned to booked (reflected via /auth/me)
    me = s.get(f"{BASE}/api/auth/me", timeout=10)
    assert me.status_code == 200
    assert me.json().get("welcome_demo") == "booked"


def test_slot_disappears_from_demo_and_video_slots(created_orgs):
    info = created_orgs[0]
    s = info["session"]
    slot = info["first_slot"]
    r = s.get(f"{BASE}/api/demo/slots", timeout=15)
    assert r.status_code == 200
    keys = {x["slot_key"] for x in r.json().get("slots") or []}
    assert slot not in keys, "Booked slot still visible in /api/demo/slots"
    # Also check /api/video-support/slots does not list this slot (anti-overlap)
    r = s.get(f"{BASE}/api/video-support/slots", timeout=15)
    if r.status_code == 200:
        vkeys = {x.get("slot_key") for x in (r.json().get("slots") or [])}
        assert slot not in vkeys, "Booked demo slot leaking into video-support slots"


def test_double_book_returns_409(created_orgs):
    # Second new org tries to book same slot
    s2, data2, email2 = _register("test_ui_dup")
    created_orgs.append({"org_id": data2.get("org_id"), "user_id": data2.get("user_id"), "email": email2, "session": s2})
    slot = created_orgs[0]["first_slot"]
    r = s2.post(f"{BASE}/api/demo/welcome/book",
                json={"slot_key": slot, "nome": "Dup", "telefono": "+393330000000"}, timeout=20)
    assert r.status_code == 409, f"expected 409, got {r.status_code} {r.text}"


# ============== Dismiss flow ==============

def test_dismiss_sets_welcome_demo_dismissed(created_orgs):
    s3, data3, email3 = _register("test_ui_skip")
    created_orgs.append({"org_id": data3.get("org_id"), "user_id": data3.get("user_id"), "email": email3, "session": s3})
    r = s3.post(f"{BASE}/api/demo/welcome/dismiss", timeout=10)
    assert r.status_code == 200
    me = s3.get(f"{BASE}/api/auth/me", timeout=10).json()
    assert me.get("welcome_demo") == "dismissed"
    # Second dismiss is idempotent (no error, state unchanged)
    r = s3.post(f"{BASE}/api/demo/welcome/dismiss", timeout=10)
    assert r.status_code == 200
    me2 = s3.get(f"{BASE}/api/auth/me", timeout=10).json()
    assert me2.get("welcome_demo") == "dismissed"


# ============== Super Admin demo config ==============

def test_sa_demo_config_get(sa):
    r = sa.get(f"{BASE}/api/platform/demo/config", timeout=15)
    assert r.status_code == 200
    j = r.json()
    assert "weekly" in j and "closed_dates" in j
    assert isinstance(j.get("weekly"), list)
    assert j.get("min_notice_hours") is not None
    assert j.get("horizon_days") is not None


def test_sa_demo_config_put_and_roundtrip(sa):
    # Preserve current config
    cur = sa.get(f"{BASE}/api/platform/demo/config", timeout=15).json()
    cur_body = {"weekly": cur.get("weekly") or [], "closed_dates": cur.get("closed_dates") or [],
                "min_notice_hours": cur.get("min_notice_hours") or 12, "horizon_days": cur.get("horizon_days") or 30}
    # Put the same thing (idempotent)
    r = sa.put(f"{BASE}/api/platform/demo/config", json=cur_body, timeout=15)
    assert r.status_code == 200
    j = r.json()
    assert len(j.get("weekly") or []) == len(cur_body["weekly"])
    # Invalid window -> 400
    bad = dict(cur_body)
    bad["weekly"] = [{"weekday": 1, "start": "12:00", "end": "10:00"}]
    r = sa.put(f"{BASE}/api/platform/demo/config", json=bad, timeout=15)
    assert r.status_code == 400


def test_non_sa_cannot_get_or_put_platform_demo(created_orgs):
    s = created_orgs[0]["session"]
    r = s.get(f"{BASE}/api/platform/demo/config", timeout=10)
    assert r.status_code in (401, 403)
    r = s.put(f"{BASE}/api/platform/demo/config", json={"weekly": [], "closed_dates": [], "min_notice_hours": 12, "horizon_days": 30}, timeout=10)
    assert r.status_code in (401, 403)


# ============== Superadmin not eligible for welcome demo ==============

def test_superadmin_not_eligible(sa):
    r = sa.get(f"{BASE}/api/demo/welcome", timeout=10)
    # SA has no org -> require_admin should reject (428/403/401 depending on impl)
    assert r.status_code in (401, 403, 428)
