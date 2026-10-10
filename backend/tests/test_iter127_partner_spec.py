"""Iter127: CRMEvent Partner — nuova spec registrazione (tipologia/accept_terms+privacy/no cookie), Brevo sync, SA list/approve/code, CORS, public-config."""
import os
import re
import uuid

import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://manage-events-12.preview.emergentagent.com").rstrip("/")
SA_EMAIL = "manara.michele.pro@gmail.com"
SA_PASSWORD = "CrmEvent2026!"


def _hex():
    return uuid.uuid4().hex[:8]


def _phone():
    import random
    return "+393" + str(random.randint(10000000, 99999999))


# ---------- Fixtures ----------
@pytest.fixture(scope="session")
def sa_session():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": SA_EMAIL, "password": SA_PASSWORD})
    assert r.status_code == 200, r.text
    return s


def _env():
    env = {}
    for line in open("/app/backend/.env"):
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"')
    return env


def _db_sync():
    """Synchronous pymongo DB for tests (avoids motor event-loop issues)."""
    from pymongo import MongoClient
    e = _env()
    return MongoClient(e["MONGO_URL"])[e["DB_NAME"]]


@pytest.fixture(scope="session")
def db():
    return _db_sync()


# ---------- 1. public-config ----------
def test_public_config_has_plans_with_semester_and_yearly():
    r = requests.get(f"{BASE}/api/partner/public-config")
    assert r.status_code == 200
    d = r.json()
    assert d["commission_pct"] == 10.0
    assert d["duration_months"] == 24
    plans = {p["key"]: p for p in d["plans"]}
    for k in ("bronze", "silver", "gold"):
        assert k in plans
        assert plans[k].get("yearly") and plans[k].get("semester")


# ---------- 2. CORS preflight for partner.crmevent.it ----------
def test_cors_preflight_partner_crmevent():
    r = requests.options(
        f"{BASE}/api/partner/register",
        headers={
            "Origin": "https://partner.crmevent.it",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert r.status_code in (200, 204)
    acao = r.headers.get("access-control-allow-origin", "")
    assert "partner.crmevent.it" in acao


# ---------- 3. Register: valid persona_fisica, no cookie, status pending, no code ----------
def test_register_persona_fisica_ok(db):
    import asyncio
    s = requests.Session()
    email = f"TEST_p_{_hex()}@example.com"
    phone_raw = "333 123 4567"
    body = {
        "nome": "Mario", "cognome": "Rossi", "email": email,
        "telefono": phone_raw, "tipologia": "persona_fisica",
        "password": "Partner123!", "password_confirm": "Partner123!",
        "accept_terms": True, "accept_privacy": True,
    }
    r = s.post(f"{BASE}/api/partner/register", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("ok") is True
    assert data.get("status") == "pending"
    # No partner_token cookie should be set at register (no auto-login)
    assert s.cookies.get("partner_token") is None, f"unexpected auto-login cookie: {s.cookies.get_dict()}"

    # DB check
    import time
    time.sleep(0.3)
    doc = db.partners.find_one({"email": email.lower()}, {"_id": 0})
    assert doc is not None, f"partner not persisted for email {email}"
    assert doc["status"] == "pending"
    assert doc["tipologia"] == "persona_fisica"
    assert doc["telefono"].startswith("+39"), f"telefono not normalized: {doc['telefono']}"
    # 'code' must NOT be present (only generated on approval)
    assert not doc.get("code"), f"code should be empty before approval: {doc.get('code')}"


# ---------- 4. Register validations ----------
def test_register_password_mismatch():
    body = {"nome": "A", "cognome": "B", "email": f"TEST_p_{_hex()}@example.com",
            "telefono": _phone(), "tipologia": "persona_fisica",
            "password": "Partner123!", "password_confirm": "Different123!",
            "accept_terms": True, "accept_privacy": True}
    r = requests.post(f"{BASE}/api/partner/register", json=body)
    assert r.status_code == 400
    assert "password" in r.json()["detail"].lower()


def test_register_missing_consent():
    body = {"nome": "A", "cognome": "B", "email": f"TEST_p_{_hex()}@example.com",
            "telefono": _phone(), "tipologia": "persona_fisica",
            "password": "Partner123!", "password_confirm": "Partner123!",
            "accept_terms": True, "accept_privacy": False}
    r = requests.post(f"{BASE}/api/partner/register", json=body)
    assert r.status_code == 400


def test_register_azienda_without_ragione():
    body = {"nome": "A", "cognome": "B", "email": f"TEST_p_{_hex()}@example.com",
            "telefono": _phone(), "tipologia": "azienda",
            "password": "Partner123!", "password_confirm": "Partner123!",
            "accept_terms": True, "accept_privacy": True}
    r = requests.post(f"{BASE}/api/partner/register", json=body)
    assert r.status_code == 400
    assert "ragione" in r.json()["detail"].lower()


def test_register_invalid_phone():
    body = {"nome": "A", "cognome": "B", "email": f"TEST_p_{_hex()}@example.com",
            "telefono": "abc", "tipologia": "persona_fisica",
            "password": "Partner123!", "password_confirm": "Partner123!",
            "accept_terms": True, "accept_privacy": True}
    r = requests.post(f"{BASE}/api/partner/register", json=body)
    assert r.status_code in (400, 422)


def test_register_duplicate_email_409():
    email = f"TEST_p_{_hex()}@example.com"
    body = {"nome": "A", "cognome": "B", "email": email,
            "telefono": _phone(), "tipologia": "persona_fisica",
            "password": "Partner123!", "password_confirm": "Partner123!",
            "accept_terms": True, "accept_privacy": True}
    r1 = requests.post(f"{BASE}/api/partner/register", json=body)
    assert r1.status_code == 200
    r2 = requests.post(f"{BASE}/api/partner/register", json=body)
    assert r2.status_code == 409


# ---------- 5. Login pending + dashboard 403 ----------
def test_pending_login_and_dashboard_403():
    s = requests.Session()
    email = f"TEST_p_{_hex()}@example.com"
    pwd = "Partner123!"
    body = {"nome": "P", "cognome": "P", "email": email,
            "telefono": _phone(), "tipologia": "persona_fisica",
            "password": pwd, "password_confirm": pwd,
            "accept_terms": True, "accept_privacy": True}
    assert requests.post(f"{BASE}/api/partner/register", json=body).status_code == 200
    r = s.post(f"{BASE}/api/partner/login", json={"email": email, "password": pwd})
    assert r.status_code == 200
    assert s.cookies.get("partner_token")
    d = s.get(f"{BASE}/api/partner/dashboard")
    assert d.status_code == 403
    detail = d.json().get("detail", {})
    code = detail.get("code") if isinstance(detail, dict) else detail
    assert code == "partner_not_approved"


# ---------- 6. Super Admin approve → code generated ----------
@pytest.fixture(scope="module")
def approved_partner(sa_session):
    s = requests.Session()
    email = f"TEST_p_{_hex()}@example.com"
    pwd = "Partner123!"
    body = {"nome": "App", "cognome": "Rov", "email": email,
            "telefono": _phone(), "tipologia": "persona_fisica",
            "password": pwd, "password_confirm": pwd,
            "accept_terms": True, "accept_privacy": True}
    reg = requests.post(f"{BASE}/api/partner/register", json=body)
    assert reg.status_code == 200
    # fetch id via SA listing
    lst = sa_session.get(f"{BASE}/api/platform/partners").json()
    me = next((x for x in lst if x["email"] == email.lower()), None)
    assert me, "partner not found in SA list"
    pid = me["id"]
    # Before approval: no code
    assert not me.get("code")
    # Approve
    r = sa_session.post(f"{BASE}/api/platform/partners/{pid}/status",
                        json={"status": "approved", "note": "test"})
    assert r.status_code == 200, r.text
    # After approval: code must be present and 8 chars
    lst2 = sa_session.get(f"{BASE}/api/platform/partners").json()
    me2 = next((x for x in lst2 if x["id"] == pid), None)
    assert me2 and me2.get("code") and len(me2["code"]) == 8
    # Partner can log in and dashboard works
    s2 = requests.Session()
    assert s2.post(f"{BASE}/api/partner/login", json={"email": email, "password": pwd}).status_code == 200
    return {"session": s2, "pid": pid, "email": email, "code": me2["code"]}


def test_approve_generates_code_and_dashboard_ok(approved_partner):
    r = approved_partner["session"].get(f"{BASE}/api/partner/dashboard")
    assert r.status_code == 200
    d = r.json()
    assert d["partner"].get("code") == approved_partner["code"]
    assert d["partner"].get("referral_link", "").endswith(f"?ref={approved_partner['code']}")


# ---------- 7. SA list has brevo_sync field ----------
def test_sa_list_has_brevo_sync_field(sa_session, approved_partner):
    lst = sa_session.get(f"{BASE}/api/platform/partners").json()
    me = next((x for x in lst if x["id"] == approved_partner["pid"]), None)
    assert me is not None
    # brevo_sync key must be present (status may be 'error' because Brevo not configured in preview)
    assert "brevo_sync" in me, f"keys: {list(me.keys())}"
    bs = me["brevo_sync"] or {}
    # In preview Brevo is NOT configured — expected status is 'error' with message
    if bs:
        assert bs.get("status") in ("ok", "error"), f"unexpected brevo_sync status: {bs}"


# ---------- 8. SA bulk Brevo sync ----------
def test_sa_brevo_sync_bulk(sa_session):
    r = sa_session.post(f"{BASE}/api/platform/partners/brevo-sync", json={"only_failed": True})
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("total", "ok", "failed"):
        assert k in d, f"missing key {k}: {d}"


def test_sa_brevo_sync_one(sa_session, approved_partner):
    r = sa_session.post(f"{BASE}/api/platform/partners/{approved_partner['pid']}/brevo-sync")
    assert r.status_code == 200, r.text
    d = r.json()
    # In preview without BREVO_API_KEY -> ok=false expected
    assert d.get("ok") is False
    assert "Brevo" in (d.get("error") or "") or d.get("status") == "error"


# ---------- 9. Cleanup ----------
def test_cleanup(sa_session, db):
    import re as _re
    rx = {"$regex": "^(TEST_|test_)"}
    parts = list(db.partners.find({"email": rx}, {"_id": 0, "id": 1}))
    pids = [p["id"] for p in parts]
    if pids:
        db.partners.delete_many({"id": {"$in": pids}})
        db.partner_referrals.delete_many({"partner_id": {"$in": pids}})
        db.partner_commissions.delete_many({"partner_id": {"$in": pids}})
        db.partner_clicks.delete_many({"partner_id": {"$in": pids}})
        db.partner_campaigns.delete_many({"partner_id": {"$in": pids}})
        db.partner_payouts.delete_many({"partner_id": {"$in": pids}})
    db.partner_login_attempts.delete_many({"identifier": {"$regex": "(TEST_|test_)"}})
    orgs = list(db.organizations.find({"nome": rx}, {"_id": 0, "id": 1}))
    oids = [o["id"] for o in orgs]
    if oids:
        db.organizations.delete_many({"id": {"$in": oids}})
        db.memberships.delete_many({"org_id": {"$in": oids}})
        db.partner_referrals.delete_many({"org_id": {"$in": oids}})
    users = list(db.users.find({"email": rx}, {"_id": 0, "user_id": 1}))
    uids = [u["user_id"] for u in users]
    if uids:
        db.users.delete_many({"user_id": {"$in": uids}})
