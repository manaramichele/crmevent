"""Iter 89 — Subscriptions BRONZE/SILVER/GOLD backend tests."""
import os
import time
import uuid
import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

from pymongo import MongoClient
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://manage-events-12.preview.emergentagent.com").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
CRON_SECRET = os.environ.get("WEBHOOK_CRON_SECRET", "bDuAedGYrYjy-3jNFc5bl2S978rceWtj5UpfQrHtHE4")

SA_EMAIL = "manara.michele.pro@gmail.com"
SA_PW = "CrmEvent2026!"
LEGACY_EMAIL = "qa.eventi@crmeventqa.it"
LEGACY_PW = "QaEvents2026!"
SAAS1_EMAIL = "test_saas1@crmeventqa.it"
SAAS1_PW = "TestSaas2026!"
SAAS1_ORG = "6050eef5d3c34f9eaaf7fb9246a9dbfe"
SAAS2_EMAIL = "test_saas2@crmeventqa.it"
SAAS2_PW = "TestSaas2026!"


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw}, timeout=20)
    assert r.status_code == 200, f"Login {email} failed: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="session")
def sa_sess():
    return _login(SA_EMAIL, SA_PW)


@pytest.fixture(scope="session")
def saas1_sess():
    return _login(SAAS1_EMAIL, SAAS1_PW)


@pytest.fixture(scope="session")
def saas2_sess():
    return _login(SAAS2_EMAIL, SAAS2_PW)


@pytest.fixture(scope="session")
def legacy_sess():
    return _login(LEGACY_EMAIL, LEGACY_PW)


# --------- 1. Public plans ---------
def test_plans_public_no_auth():
    r = requests.get(f"{BASE_URL}/api/saas/plans-public", timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d["trial_days"] == 14
    assert d["trial_plan"] == "gold"
    assert d["trial_video_quota"] == 3
    plans = {p["key"]: p for p in d["plans"]}
    assert set(plans.keys()) >= {"bronze", "silver", "gold"}
    assert plans["bronze"]["monthly"] == 19.0 and plans["bronze"]["yearly"] == 182.4
    assert plans["silver"]["monthly"] == 49.0 and plans["silver"]["yearly"] == 470.4
    assert plans["gold"]["monthly"] == 79.0 and plans["gold"]["yearly"] == 758.4
    assert plans["bronze"]["video_quota"] == 0
    assert plans["silver"]["video_quota"] == 3
    assert plans["gold"]["video_quota"] == -1
    # Features matrix
    assert "calendar" in plans["bronze"]["features"]
    assert "aziende" not in plans["bronze"]["features"]
    assert "aziende" in plans["silver"]["features"]
    assert "sponsor" not in plans["silver"]["features"]
    assert "sponsor" in plans["gold"]["features"]
    assert "ospitalita" in plans["gold"]["features"]


# --------- 2. Register new org => trial GOLD 14d ---------
_test_orgs_to_clean = []


def test_register_creates_trial_gold():
    uniq = uuid.uuid4().hex[:8]
    email = f"TEST_regtrial_{uniq}@example.com"
    body = {"nome": "TEST", "cognome": "User", "email": email, "password": "StrongPwd2026!",
            "org_name": f"TEST_RegTrial_{uniq}", "telefono": "+393401234567", "accept_terms": True}
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/register-organization", json=body, timeout=20)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    org_id = data.get("org_id") or data.get("user", {}).get("org_id")
    assert org_id
    _test_orgs_to_clean.append((org_id, email))
    # /api/auth/me contains saas object
    me = s.get(f"{BASE_URL}/api/auth/me", timeout=10).json()
    assert "saas" in me, f"no saas in /auth/me: {list(me.keys())}"
    assert me["saas"].get("enabled") is True
    assert me["saas"].get("mode") == "trial"
    assert me["saas"].get("plan") == "gold"
    # /saas/me
    sm = s.get(f"{BASE_URL}/api/saas/me", timeout=10).json()
    assert sm["mode"] == "trial"
    assert sm["days_left"] == 14
    assert sm["video"]["mode"] == "plan"
    assert sm["video"]["quota"] == 3
    assert sm["video"]["period"] == "trial"
    # no signup bonus for subscription orgs
    cr = s.get(f"{BASE_URL}/api/credits/balance", timeout=10)
    # subscription orgs may hide credits; if returned, no signup_bonus flag
    if cr.status_code == 200:
        d = cr.json()
        assert not d.get("signup_bonus_granted"), f"subscription org got signup bonus: {d}"


# --------- 3. Gating via mongo manipulation ---------
def test_bronze_gating_blocks_aziende():
    import datetime as dt
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    uniq = uuid.uuid4().hex[:8]
    email = f"TEST_bronze_{uniq}@example.com"
    body = {"nome": "T", "cognome": "B", "email": email, "password": "StrongPwd2026!",
            "org_name": f"TEST_Bronze_{uniq}", "telefono": "+393401234567", "accept_terms": True}
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/register-organization", json=body, timeout=20)
    assert r.status_code == 200
    org_id = r.json().get("org_id") or r.json().get("user", {}).get("org_id")
    _test_orgs_to_clean.append((org_id, email))
    # Force BRONZE active, trial ended
    past = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).isoformat()
    db.organizations.update_one({"id": org_id}, {"$set": {
        "saas.plan": "bronze", "saas.stripe_status": "active", "saas.billing_cycle": "monthly",
        "saas.trial_end": past, "saas.trial_status": "converted",
        "saas.current_period_start": past,
        "saas.current_period_end": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=30)).isoformat(),
        "saas.activated_at": past, "saas.billing_anchor": past}})
    # Events OK, companies 403 plan_feature
    r1 = s.get(f"{BASE_URL}/api/events", timeout=10)
    assert r1.status_code == 200, r1.text[:200]
    r2 = s.get(f"{BASE_URL}/api/companies", timeout=10)
    assert r2.status_code == 403, r2.text[:200]
    d = r2.json().get("detail") or {}
    assert isinstance(d, dict) and d.get("code") == "plan_feature", f"got: {d}"
    # Upgrade to SILVER => companies OK, deals (sponsor) 403, hospitality 403
    db.organizations.update_one({"id": org_id}, {"$set": {"saas.plan": "silver"}})
    r3 = s.get(f"{BASE_URL}/api/companies", timeout=10)
    assert r3.status_code == 200
    r4 = s.get(f"{BASE_URL}/api/deals", timeout=10)
    assert r4.status_code == 403
    assert (r4.json().get("detail") or {}).get("code") == "plan_feature"
    # hospitality: /api/lodgings or /api/meals (feature=ospitalita)
    r5 = s.get(f"{BASE_URL}/api/lodgings", timeout=10)
    assert r5.status_code == 403
    client.close()


def test_readonly_when_trial_expired_and_no_plan():
    import datetime as dt
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    uniq = uuid.uuid4().hex[:8]
    email = f"TEST_ro_{uniq}@example.com"
    body = {"nome": "T", "cognome": "R", "email": email, "password": "StrongPwd2026!",
            "org_name": f"TEST_RO_{uniq}", "telefono": "+393401234567", "accept_terms": True}
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/register-organization", json=body, timeout=20)
    assert r.status_code == 200
    org_id = r.json().get("org_id") or r.json().get("user", {}).get("org_id")
    _test_orgs_to_clean.append((org_id, email))
    past = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).isoformat()
    db.organizations.update_one({"id": org_id}, {"$set": {
        "saas.plan": None, "saas.stripe_status": None, "saas.trial_end": past,
        "saas.trial_status": "expired"}})
    # GET events OK (readable)
    r1 = s.get(f"{BASE_URL}/api/events", timeout=10)
    assert r1.status_code == 200
    # POST event blocked with plan_readonly
    r2 = s.post(f"{BASE_URL}/api/events", json={"nome": "X", "data_inizio": "2026-12-01", "data_fine": "2026-12-02"}, timeout=10)
    assert r2.status_code == 403
    d = r2.json().get("detail") or {}
    assert d.get("code") == "plan_readonly", f"got: {d}"
    # /api/saas/me still works
    r3 = s.get(f"{BASE_URL}/api/saas/me", timeout=10)
    assert r3.status_code == 200
    # /api/account/billing (GET) still works
    r4 = s.get(f"{BASE_URL}/api/account/billing", timeout=10)
    assert r4.status_code in (200, 404)
    client.close()


# --------- 4. test_saas1 (GOLD paid Stripe TEST) ---------
def test_saas1_me_is_gold_active(saas1_sess):
    r = saas1_sess.get(f"{BASE_URL}/api/saas/me", timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d["enabled"] is True
    assert d["mode"] in ("active", "past_due", "trial")
    assert d["plan"] == "gold"
    assert d["video"]["unlimited"] is True


def test_saas1_change_preview_upgrade_to_yearly(saas1_sess):
    r = saas1_sess.get(f"{BASE_URL}/api/saas/change-preview?plan=gold&cycle=yearly", timeout=20)
    # Could be 200 kind=upgrade, or 400 if currently not monthly
    assert r.status_code in (200, 400), r.text[:200]
    if r.status_code == 200:
        d = r.json()
        # If current is monthly gold, cycling to yearly is an upgrade
        assert d["kind"] in ("upgrade", "same", "downgrade")
        if d["kind"] == "upgrade":
            assert "amount_due" in d


def test_saas1_downgrade_schedules_pending(saas1_sess):
    # Trigger downgrade to bronze/monthly => scheduled, not immediate
    r = saas1_sess.post(f"{BASE_URL}/api/saas/change",
                        json={"plan": "bronze", "cycle": "monthly"}, timeout=30)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert d["immediate"] is False
    assert d.get("pending_change") and d["pending_change"]["plan"] == "bronze"
    # Cancel the pending change to leave state clean
    r2 = saas1_sess.post(f"{BASE_URL}/api/saas/change/cancel-pending", timeout=20)
    assert r2.status_code == 200


def test_saas1_cancel_then_resume(saas1_sess):
    r = saas1_sess.post(f"{BASE_URL}/api/saas/cancel", timeout=20)
    assert r.status_code == 200
    assert r.json()["state"].get("cancel_at_period_end") is True
    r2 = saas1_sess.post(f"{BASE_URL}/api/saas/resume", timeout=20)
    assert r2.status_code == 200
    assert r2.json()["state"].get("cancel_at_period_end") is False


# --------- 5. Checkout requires billing details ---------
def test_checkout_billing_missing(saas2_sess):
    # saas2 is trial, no billing set likely
    r = saas2_sess.post(f"{BASE_URL}/api/saas/checkout",
                        json={"plan": "bronze", "cycle": "monthly", "origin_url": BASE_URL}, timeout=20)
    # Expect 400 billing_missing OR 200 checkout_url if billing is already filled
    assert r.status_code in (200, 400), r.text[:300]
    if r.status_code == 400:
        d = r.json().get("detail") or {}
        assert d.get("code") == "billing_missing", f"got: {d}"
    else:
        assert "checkout_url" in r.json()


# --------- 6. Super Admin platform endpoints ---------
def test_platform_saas_orgs(sa_sess):
    r = sa_sess.get(f"{BASE_URL}/api/platform/saas/organizations?scope=platform", timeout=20)
    assert r.status_code == 200
    arr = r.json()
    assert isinstance(arr, list)


def test_platform_saas_config_version_increments(sa_sess):
    r = sa_sess.get(f"{BASE_URL}/api/platform/saas/config?scope=platform", timeout=10)
    assert r.status_code == 200
    cfg = r.json()
    v0 = int(cfg.get("version", 1))
    body = {"trial_days": cfg["trial_days"], "trial_video_quota": cfg["trial_video_quota"],
            "plans": {k: {kk: cfg["plans"][k][kk] for kk in ("label", "color", "tagline", "monthly", "yearly", "features", "video_quota", "active")}
                      for k in ("bronze", "silver", "gold")}}
    r2 = sa_sess.put(f"{BASE_URL}/api/platform/saas/config?scope=platform", json=body, timeout=15)
    assert r2.status_code == 200, r2.text[:300]
    assert int(r2.json()["version"]) == v0 + 1
    # history
    rh = sa_sess.get(f"{BASE_URL}/api/platform/saas/config/history?scope=platform", timeout=10)
    assert rh.status_code == 200
    assert len(rh.json()) >= 1


def test_platform_migration_report(sa_sess):
    r = sa_sess.get(f"{BASE_URL}/api/platform/saas/migration-report?scope=platform", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert "orgs" in d and "totals" in d


def test_non_superadmin_cannot_access_platform(saas1_sess):
    r = saas1_sess.get(f"{BASE_URL}/api/platform/saas/organizations?scope=platform", timeout=10)
    assert r.status_code == 403


# --------- 7. Cron ---------
def test_cron_trial_tick_unauthorized():
    r = requests.post(f"{BASE_URL}/api/cron/saas-trial-tick", timeout=10)
    assert r.status_code == 401


def test_cron_trial_tick_with_bearer():
    r = requests.post(f"{BASE_URL}/api/cron/saas-trial-tick",
                      headers={"Authorization": f"Bearer {CRON_SECRET}"}, timeout=10)
    assert r.status_code == 200
    assert r.json().get("accepted") is True


# --------- 8. Legacy org regression ---------
def test_legacy_org_no_plan_gating(legacy_sess):
    me = legacy_sess.get(f"{BASE_URL}/api/auth/me", timeout=10).json()
    saas = me.get("saas") or {}
    assert saas.get("enabled") is False or saas == {} or not saas, f"legacy should have saas enabled=False, got {saas}"
    # Credits should still be accessible
    r = legacy_sess.get(f"{BASE_URL}/api/credits/balance", timeout=10)
    assert r.status_code == 200
    # Should be able to GET companies (no plan gating)
    r2 = legacy_sess.get(f"{BASE_URL}/api/companies", timeout=10)
    assert r2.status_code == 200


# --------- 9. Video support info for trial org ---------
def test_video_support_info_trial(saas2_sess):
    r = saas2_sess.get(f"{BASE_URL}/api/video-support/info", timeout=10)
    assert r.status_code == 200
    d = r.json()
    pol = d.get("plan") or {}
    assert pol.get("mode") == "plan"
    assert pol.get("trial") is True
    assert pol.get("quota") == 3


def test_video_quota_exhausted_blocks_booking(saas2_sess):
    """Pre-fill the quota and verify booking returns 403 video_quota."""
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    # Find saas2 org id and set quota to 3/3 for trial period
    me = saas2_sess.get(f"{BASE_URL}/api/saas/me", timeout=10).json()
    org_id = None
    # discover from auth/me
    am = saas2_sess.get(f"{BASE_URL}/api/auth/me", timeout=10).json()
    org_id = am.get("org_id") or (am.get("organizations") or [{}])[0].get("org_id")
    assert org_id
    db.saas_video_quota.update_one({"org_id": org_id, "period": "trial"},
                                   {"$set": {"used": 3}}, upsert=True)
    # Try to book — should 403 video_quota
    import datetime as dt
    slot = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=2)).strftime("%Y-%m-%dT10:00")
    r = saas2_sess.post(f"{BASE_URL}/api/video-support/bookings",
                        json={"slot_key": slot, "confirm_cost": 0}, timeout=15)
    assert r.status_code == 403, r.text[:300]
    detail = r.json().get("detail") or {}
    assert detail.get("code") == "video_quota", f"got: {detail}"
    # Verify /info reflects allowed=false
    info = saas2_sess.get(f"{BASE_URL}/api/video-support/info", timeout=10).json()
    assert info["plan"].get("allowed") is False
    # Cleanup — reset quota
    db.saas_video_quota.delete_one({"org_id": org_id, "period": "trial"})
    client.close()


def test_video_bronze_email_only():
    """Bronze orgs should get support=email in video policy."""
    import datetime as dt
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    uniq = uuid.uuid4().hex[:8]
    email = f"TEST_vb_{uniq}@example.com"
    body = {"nome": "T", "cognome": "V", "email": email, "password": "StrongPwd2026!",
            "org_name": f"TEST_VBronze_{uniq}", "telefono": "+393401234567", "accept_terms": True}
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/register-organization", json=body, timeout=20)
    assert r.status_code == 200
    org_id = r.json().get("org_id") or r.json().get("user", {}).get("org_id")
    _test_orgs_to_clean.append((org_id, email))
    past = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).isoformat()
    db.organizations.update_one({"id": org_id}, {"$set": {
        "saas.plan": "bronze", "saas.stripe_status": "active", "saas.billing_cycle": "monthly",
        "saas.trial_end": past, "saas.trial_status": "converted",
        "saas.current_period_start": past,
        "saas.current_period_end": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=30)).isoformat(),
        "saas.activated_at": past, "saas.billing_anchor": past}})
    info = s.get(f"{BASE_URL}/api/video-support/info", timeout=10).json()
    pol = info.get("plan") or {}
    assert pol.get("allowed") is False
    assert pol.get("support") == "email", f"expected support=email, got {pol}"
    client.close()


def test_video_gold_unlimited(saas1_sess):
    info = saas1_sess.get(f"{BASE_URL}/api/video-support/info", timeout=10).json()
    pol = info.get("plan") or {}
    assert pol.get("mode") == "plan"
    assert pol.get("unlimited") is True
    assert pol.get("priority") is True


# --------- 10. Events in subscription org => credit_state attivo ---------
def test_event_create_subscription_is_attivo(saas2_sess):
    # saas2 is in trial (gold) — can create events, credit_state should be 'attivo'
    body = {"nome": f"TEST_ev_{uuid.uuid4().hex[:6]}", "data_inizio": "2026-12-20", "data_fine": "2026-12-21"}
    r = saas2_sess.post(f"{BASE_URL}/api/events", json=body, timeout=15)
    assert r.status_code in (200, 201), r.text[:300]
    ev = r.json()
    assert ev.get("credit_state") == "attivo", f"got {ev.get('credit_state')}"
    # cleanup
    saas2_sess.delete(f"{BASE_URL}/api/events/{ev['id']}", timeout=10)


# --------- Teardown: cleanup TEST_ orgs ---------
def test_zz_cleanup():
    """Cleanup created TEST_ orgs and users directly in mongo."""
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    for org_id, email in _test_orgs_to_clean:
        db.organizations.delete_one({"id": org_id})
        db.memberships.delete_many({"org_id": org_id})
        db.users.delete_many({"email": email})
        db.events.delete_many({"org_id": org_id})
        db.saas_video_quota.delete_many({"org_id": org_id})
        db.credit_ledger.delete_many({"org_id": org_id})
        db.saas_emails.delete_many({"org_id": org_id})
    client.close()
    assert True
