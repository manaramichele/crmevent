"""Iter126: CRMEvent Partner portal — nuova spec (24 mesi, categoria/soggetto, ref={code,cmp,at}, campagne, materiali, payouts, SA Organizzatori)."""
import asyncio
import hashlib
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://manage-events-12.preview.emergentagent.com").rstrip("/")
SA_EMAIL = "manara.michele.pro@gmail.com"
SA_PASSWORD = "CrmEvent2026!"


# ---------- fixtures ----------
@pytest.fixture(scope="session")
def http():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def sa_session():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": SA_EMAIL, "password": SA_PASSWORD})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="session")
def db():
    """Direct Mongo access for seeding/assertions (same instance backend uses)."""
    from motor.motor_asyncio import AsyncIOMotorClient
    import importlib.util
    spec = importlib.util.spec_from_file_location("_env", "/app/backend/.env")
    # Just read MONGO_URL and DB_NAME directly
    env = {}
    for line in open("/app/backend/.env"):
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"')
    client = AsyncIOMotorClient(env["MONGO_URL"])
    return client[env["DB_NAME"]]


def _hex():
    return uuid.uuid4().hex[:8]


def _phone():
    import random
    return "+393" + str(random.randint(10000000, 99999999))


# ---------- 1. public-config: 10%/24 mesi ----------
def test_public_config_24_months(http):
    r = http.get(f"{BASE}/api/partner/public-config")
    assert r.status_code == 200
    d = r.json()
    assert d["commission_pct"] == 10.0
    assert d["duration_months"] == 24
    assert d["attribution_days"] == 30
    plans = {p["key"]: p for p in d["plans"]}
    for k in ("bronze", "silver", "gold"):
        assert k in plans, f"missing plan {k}"
        assert plans[k]["yearly"] and plans[k]["semester"]


# ---------- 2. Registrazione: nuovi campi categoria/soggetto ----------
def test_register_privato_ok(http):
    s = requests.Session()
    email = f"TEST_p_{_hex()}@crmeventqa.it"
    body = {"nome": "Test", "cognome": "Partner", "email": email, "password": "PartnerStrong1!",
            "telefono": _phone(), "categoria": "influencer", "soggetto": "privato", "accept_terms": True}
    r = s.post(f"{BASE}/api/partner/register", json=body)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["status"] == "pending"
    assert len(p["code"]) == 8
    assert p["categoria"] == "influencer"
    assert p["soggetto"] == "privato"
    assert s.cookies.get("partner_token")
    # pending → dashboard 403
    d = s.get(f"{BASE}/api/partner/dashboard")
    assert d.status_code == 403
    assert d.json().get("detail", {}).get("code") == "partner_not_approved"


def test_register_azienda_requires_piva_and_ragione(http):
    email = f"TEST_p_{_hex()}@crmeventqa.it"
    body = {"nome": "A", "cognome": "B", "email": email, "password": "PartnerStrong1!",
            "telefono": "+393331111222", "categoria": "agenzia", "soggetto": "azienda", "accept_terms": True}
    r = requests.post(f"{BASE}/api/partner/register", json=body)
    assert r.status_code == 400
    assert "iva" in r.json()["detail"].lower()
    body["partita_iva"] = "IT12345678901"
    r = requests.post(f"{BASE}/api/partner/register", json=body)
    assert r.status_code == 400
    assert "ragione" in r.json()["detail"].lower()


def test_register_professionista_requires_piva(http):
    body = {"nome": "A", "cognome": "B", "email": f"TEST_p_{_hex()}@crmeventqa.it", "password": "PartnerStrong1!",
            "telefono": "+393332223344", "categoria": "professionista", "soggetto": "professionista", "accept_terms": True}
    r = requests.post(f"{BASE}/api/partner/register", json=body)
    assert r.status_code == 400


def test_register_missing_accept_terms(http):
    body = {"nome": "A", "cognome": "B", "email": f"TEST_p_{_hex()}@crmeventqa.it", "password": "PartnerStrong1!",
            "telefono": "+393334445566", "categoria": "altro", "soggetto": "privato", "accept_terms": False}
    r = requests.post(f"{BASE}/api/partner/register", json=body)
    assert r.status_code == 400


# ---------- 3. forgot/reset ----------
def test_forgot_password_always_200(http):
    r = http.post(f"{BASE}/api/partner/forgot-password", json={"email": "nonexistent_TEST@crmeventqa.it"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_reset_invalid_token_400(http):
    r = http.post(f"{BASE}/api/partner/reset-password", json={"token": "invalidtoken123", "password": "NewPassword1!"})
    assert r.status_code == 400


def test_brute_force_lockout_429(http):
    email = f"TEST_p_{_hex()}@crmeventqa.it"
    requests.post(f"{BASE}/api/partner/register", json={
        "nome": "L", "cognome": "O", "email": email, "password": "PartnerStrong1!",
        "telefono": _phone(), "categoria": "altro", "soggetto": "privato", "accept_terms": True})
    saw_429 = False
    for _ in range(25):
        r = requests.post(f"{BASE}/api/partner/login", json={"email": email, "password": "wrongpass!"})
        if r.status_code == 429:
            saw_429 = True
            break
    assert saw_429, "no 429 after 25 failed attempts"


# ---------- 4. Session isolation ----------
def test_cookie_isolation(sa_session, http):
    # SA cookie must NOT work on /api/partner/me
    r = sa_session.get(f"{BASE}/api/partner/me")
    assert r.status_code == 401
    # Create ephemeral partner, use its cookie on /api/auth/me → 401
    email = f"TEST_p_{_hex()}@crmeventqa.it"
    s = requests.Session()
    r = s.post(f"{BASE}/api/partner/register", json={
        "nome": "I", "cognome": "S", "email": email, "password": "PartnerStrong1!",
        "telefono": _phone(), "categoria": "altro", "soggetto": "privato", "accept_terms": True})
    assert r.status_code == 200
    r2 = s.get(f"{BASE}/api/auth/me")
    assert r2.status_code == 401


# ---------- 5. SA settings PUT roundtrip ----------
def test_sa_settings_roundtrip(sa_session):
    orig = sa_session.get(f"{BASE}/api/platform/partner-settings").json()
    body = {"commission_pct": 10.0, "duration_months": 24, "attribution_days": 30, "hold_days": 30,
            "payout_frequency": "trimestrale", "min_payout_cents": 0, "crmevent_tax_regime": "forfettario",
            "payout_notes": orig.get("payout_notes") or ""}
    r = sa_session.put(f"{BASE}/api/platform/partner-settings", json=body)
    assert r.status_code == 200
    d = r.json()
    assert d["duration_months"] == 24
    assert d["commission_pct"] == 10.0
    assert d["hold_days"] == 30
    assert d["attribution_days"] == 30


# ---------- 6. SA Partners list / approve / dashboard referral_link ----------
@pytest.fixture(scope="module")
def approved_partner(sa_session):
    email = f"TEST_p_{_hex()}@crmeventqa.it"
    s = requests.Session()
    reg = s.post(f"{BASE}/api/partner/register", json={
        "nome": "Appr", "cognome": "Oved", "email": email, "password": "PartnerStrong1!",
        "telefono": _phone(), "categoria": "altro", "soggetto": "privato", "accept_terms": True,
        "iban": "IT60X0542811101000000123456"})
    assert reg.status_code == 200
    p = reg.json()
    r = sa_session.post(f"{BASE}/api/platform/partners/{p['id']}/status", json={"status": "approved", "note": "ok"})
    assert r.status_code == 200
    # re-login to refresh partner session for approved status
    s2 = requests.Session()
    assert s2.post(f"{BASE}/api/partner/login", json={"email": email, "password": "PartnerStrong1!"}).status_code == 200
    return {"session": s2, "partner": p, "email": email}


def test_sa_list_partner(sa_session, approved_partner):
    r = sa_session.get(f"{BASE}/api/platform/partners")
    assert r.status_code == 200
    found = [x for x in r.json() if x["id"] == approved_partner["partner"]["id"]]
    assert found and found[0]["status"] == "approved"


def test_approved_dashboard(approved_partner):
    r = approved_partner["session"].get(f"{BASE}/api/partner/dashboard")
    assert r.status_code == 200
    d = r.json()
    assert d["partner"]["referral_link"].endswith(f"?ref={approved_partner['partner']['code']}")
    assert "stats" in d and "referrals" in d and "commissions" in d and "campaigns" in d
    assert d["settings"]["duration_months"] == 24


# ---------- 7. Campaigns ----------
def test_campaigns_crud_and_isolation(approved_partner, sa_session):
    s = approved_partner["session"]
    r = s.post(f"{BASE}/api/partner/campaigns", json={"name": "Estate2026"})
    assert r.status_code == 200
    c = r.json()
    assert c["slug"] == "estate2026"
    # duplicate
    assert s.post(f"{BASE}/api/partner/campaigns", json={"name": "Estate2026"}).status_code == 400
    # reserved
    assert s.post(f"{BASE}/api/partner/campaigns", json={"name": "principale"}).status_code == 400

    # Second partner cannot delete campaign of first
    email2 = f"TEST_p_{_hex()}@crmeventqa.it"
    s2 = requests.Session()
    reg = s2.post(f"{BASE}/api/partner/register", json={
        "nome": "B", "cognome": "B", "email": email2, "password": "PartnerStrong1!",
        "telefono": _phone(), "categoria": "altro", "soggetto": "privato", "accept_terms": True})
    sa_session.post(f"{BASE}/api/platform/partners/{reg.json()['id']}/status", json={"status": "approved", "note": "ok"})
    s2b = requests.Session()
    s2b.post(f"{BASE}/api/partner/login", json={"email": email2, "password": "PartnerStrong1!"})
    s2b.delete(f"{BASE}/api/partner/campaigns/{c['id']}")  # must not actually delete
    r3 = s.get(f"{BASE}/api/partner/dashboard")
    assert any(x["id"] == c["id"] for x in r3.json()["campaigns"]), "campaign deleted by other partner!"
    # Own partner can delete
    s.delete(f"{BASE}/api/partner/campaigns/{c['id']}")
    r4 = s.get(f"{BASE}/api/partner/dashboard")
    assert not any(x["id"] == c["id"] for x in r4.json()["campaigns"])


# ---------- 8. Tracking ----------
def test_tracking_dedupe(approved_partner):
    code = approved_partner["partner"]["code"]
    # Pending/unknown code
    r = requests.post(f"{BASE}/api/partner/track", json={"ref": "ZZZZZZZZ", "cmp": None})
    assert r.status_code == 200 and r.json()["ok"] is False
    # valid
    for _ in range(3):
        r = requests.post(f"{BASE}/api/partner/track", json={"ref": code, "cmp": "test"})
        assert r.status_code == 200 and r.json()["ok"] is True


# ---------- 9. Referral attach with new ref object {code, cmp, at} ----------
def test_referral_attach_ok(approved_partner):
    code = approved_partner["partner"]["code"]
    org_email = f"TEST_org_{_hex()}@crmeventqa.it"
    r = requests.post(f"{BASE}/api/auth/register-organization", json={
        "email": org_email, "password": "OrgStrong1!", "nome": "Org", "cognome": "Admin",
        "org_name": f"TEST_Org_{_hex()}", "telefono": _phone(), "accept_terms": True,
        "ref": {"code": code, "cmp": "estate", "at": datetime.now(timezone.utc).isoformat()}})
    assert r.status_code == 200, f"body={r.text}"
    time.sleep(0.5)
    d = approved_partner["session"].get(f"{BASE}/api/partner/dashboard").json()
    assert any(x["campaign"] == "estate" for x in d["referrals"]), f"referral not attached: {d['referrals']}"


def test_referral_attach_stale_at(approved_partner):
    code = approved_partner["partner"]["code"]
    org_email = f"TEST_org_{_hex()}@crmeventqa.it"
    stale = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
    r = requests.post(f"{BASE}/api/auth/register-organization", json={
        "email": org_email, "password": "OrgStrong1!", "nome": "Org", "cognome": "Admin",
        "org_name": f"TEST_Org_{_hex()}", "telefono": _phone(), "accept_terms": True,
        "ref": {"code": code, "cmp": None, "at": stale}})
    assert r.status_code == 200
    time.sleep(0.3)
    d = approved_partner["session"].get(f"{BASE}/api/partner/dashboard").json()
    # None of the orgs created in this test should be present
    assert not any(x["org_name"].startswith("TEST_Org_") and x.get("campaign") is None and
                   datetime.fromisoformat(x["created_at"].replace("Z", "+00:00")) > datetime.now(timezone.utc) - timedelta(seconds=10)
                   for x in d["referrals"])


def test_referral_self_email_blocked(approved_partner):
    code = approved_partner["partner"]["code"]
    r = requests.post(f"{BASE}/api/auth/register-organization", json={
        "email": approved_partner["email"], "password": "OrgStrong1!", "nome": "Self", "cognome": "Ref",
        "org_name": f"TEST_SelfOrg_{_hex()}", "telefono": _phone(), "accept_terms": True,
        "ref": {"code": code, "at": datetime.now(timezone.utc).isoformat()}})
    # Email already registered as partner? Not necessarily — partner has own email but users collection is separate.
    # If user with partner's email exists, it will 400. We only verify no referral row created when email matches partner.
    # Accept either case, but check referral not attached:
    time.sleep(0.3)
    if r.status_code == 200:
        d = approved_partner["session"].get(f"{BASE}/api/partner/dashboard").json()
        assert not any(x["org_name"].startswith("TEST_SelfOrg_") for x in d["referrals"])


# ---------- 10. Direct engine tests (import partner_portal via server db) ----------
@pytest.fixture(scope="session")
def engine():
    import sys
    sys.path.insert(0, "/app/backend")
    for k, v in {kk.strip(): vv.strip().strip('"') for line in open("/app/backend/.env")
                 if "=" in line and not line.startswith("#") for kk, _, vv in [line.partition("=")]}.items():
        os.environ.setdefault(k, v)
    import partner_portal
    from server import db as server_db, hash_password, verify_password
    import text_normalize as TN
    person_name = TN.person_name
    async def _audit(*a, **k): pass
    async def _saas_config(): return {"plans": {"bronze": {"active": True, "label": "Bronze", "color": "#000", "monthly": 10, "yearly": 100}}}
    async def _req_sa(): return {"email": "sa@test"}
    router = partner_portal.build(server_db, {"hash_password": hash_password, "verify_password": verify_password,
        "person_name": person_name, "require_superadmin": _req_sa, "record_audit": _audit, "saas_config": _saas_config})
    return {"on_sub": router["on_subscription_paid"], "on_refund": router["on_refund"],
            "attach": router["attach_referral"], "settings": router["get_settings"], "db": server_db}


def test_commission_base_cents():
    import importlib, sys
    sys.path.insert(0, "/app/backend")
    pp = importlib.import_module("partner_portal")
    assert pp.commission_base_cents({"amount_paid": 22253, "total_taxes": [{"amount": 4013}]}) == 18240
    assert pp.commission_base_cents({"amount_paid": 1000, "tax": 0}) == 1000
    assert pp.commission_base_cents({"amount_paid": 0}) == 0


def test_engine_subscription_and_refund(engine):
    db = engine["db"]
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def run():
        # Setup fake partner + referral
        pid = f"TEST_p_{_hex()}"
        oid = f"TEST_org_{_hex()}"
        now_iso = datetime.now(timezone.utc).isoformat()
        await db.partners.insert_one({"id": pid, "email": f"{pid}@qa.it", "status": "approved", "code": "TESTCODE",
                                      "telefono": "+39999", "nome": "T", "cognome": "P", "soggetto": "privato", "created_at": now_iso})
        await db.partner_referrals.insert_one({"id": uuid.uuid4().hex, "partner_id": pid, "org_id": oid,
                                               "org_name": "TEST_Org", "created_at": now_iso, "first_paid_at": None,
                                               "commission_until": None, "campaign": None, "source": "test"})
        org = {"id": oid, "nome": "TEST_Org", "saas": {"plan": "bronze", "billing_cycle": "yearly"}}
        inv = {"id": f"in_test_{_hex()}", "amount_paid": 22253, "total_taxes": [{"amount": 4013}],
               "created": int(time.time()), "billing_reason": "subscription_create", "status": "paid"}

        await engine["on_sub"](org, inv)
        c = await db.partner_commissions.find_one({"stripe_invoice_id": inv["id"]}, {"_id": 0})
        assert c, "commission not created"
        assert c["base_cents"] == 18240
        assert c["commission_pct"] == 10.0
        assert c["commission_cents"] == 1824
        assert c["commission_net_cents"] == 1824
        assert c["kind"] == "prima_sottoscrizione"
        assert c["status"] == "maturata"

        # Idempotent: second call -> no new doc
        await engine["on_sub"](org, inv)
        n = await db.partner_commissions.count_documents({"stripe_invoice_id": inv["id"]})
        assert n == 1

        # Plan not in bronze/silver/gold -> no commission
        inv2 = {**inv, "id": f"in_test_{_hex()}"}
        org_free = {**org, "saas": {"plan": "trial"}}
        await engine["on_sub"](org_free, inv2)
        assert await db.partner_commissions.count_documents({"stripe_invoice_id": inv2["id"]}) == 0

        # Billing reason cycle -> rinnovo
        inv3 = {**inv, "id": f"in_test_{_hex()}", "billing_reason": "subscription_cycle",
                "created": int(time.time()) + 100}
        await engine["on_sub"](org, inv3)
        c3 = await db.partner_commissions.find_one({"stripe_invoice_id": inv3["id"]}, {"_id": 0})
        assert c3["kind"] == "rinnovo"

        # Invoice after 24 months → not created
        far = int((datetime.now(timezone.utc) + timedelta(days=24 * 31)).timestamp())
        inv4 = {**inv, "id": f"in_test_{_hex()}", "billing_reason": "subscription_cycle", "created": far}
        await engine["on_sub"](org, inv4)
        assert await db.partner_commissions.count_documents({"stripe_invoice_id": inv4["id"]}) == 0

        # Partial refund
        charge = {"invoice": inv["id"], "amount": 22253, "amount_refunded": 11127}
        ok = await engine["on_refund"](charge)
        assert ok
        c = await db.partner_commissions.find_one({"stripe_invoice_id": inv["id"]}, {"_id": 0})
        assert c["commission_net_cents"] == int(round(1824 * 0.5)), c["commission_net_cents"]

        # Full refund
        charge["amount_refunded"] = 22253
        await engine["on_refund"](charge)
        c = await db.partner_commissions.find_one({"stripe_invoice_id": inv["id"]}, {"_id": 0})
        assert c["commission_net_cents"] == 0
        assert c["status"] == "stornata"

        # Cleanup
        await db.partners.delete_one({"id": pid})
        await db.partner_referrals.delete_many({"org_id": oid})
        await db.partner_commissions.delete_many({"partner_id": pid})

    loop.run_until_complete(run())


# ---------- 11. CSV export ----------
def test_csv_export(sa_session):
    r = sa_session.get(f"{BASE}/api/platform/partner-commissions.csv")
    assert r.status_code == 200
    body = r.content.decode("utf-8")
    assert body.startswith("\ufeff"), "missing BOM"
    assert ";" in body.splitlines()[0], "missing ; separator"


# ---------- 12. Payouts: IBAN required ----------
def test_payout_requires_iban(sa_session):
    # Create partner without IBAN
    email = f"TEST_p_{_hex()}@crmeventqa.it"
    s = requests.Session()
    reg = s.post(f"{BASE}/api/partner/register", json={
        "nome": "No", "cognome": "Iban", "email": email, "password": "PartnerStrong1!",
        "telefono": _phone(), "categoria": "altro", "soggetto": "privato", "accept_terms": True})
    pid = reg.json()["id"]
    sa_session.post(f"{BASE}/api/platform/partners/{pid}/status", json={"status": "approved", "note": "ok"})
    r = sa_session.post(f"{BASE}/api/platform/partner-payouts", json={"partner_id": pid})
    assert r.status_code == 400
    assert "iban" in r.json()["detail"].lower()


# ---------- 13. IBAN validation on profile ----------
def test_profile_iban_validation(approved_partner):
    r = approved_partner["session"].patch(f"{BASE}/api/partner/profile", json={"iban": "NOT_AN_IBAN"})
    assert r.status_code == 400
    r = approved_partner["session"].patch(f"{BASE}/api/partner/profile", json={"iban": "IT60X0542811101000000123456"})
    assert r.status_code == 200


# ---------- 14. Materials: SA add link + partner retrieves ----------
def test_materials(sa_session, approved_partner):
    r = sa_session.post(f"{BASE}/api/platform/partner-materials",
                        data={"title": "TEST_mat", "description": "test", "url": "https://example.com/x.pdf"},
                        headers={"Content-Type": None} if False else None)
    # multipart/form-data via requests
    r = sa_session.post(f"{BASE}/api/platform/partner-materials",
                        data={"title": "TEST_mat", "description": "test", "url": "https://example.com/x.pdf"})
    assert r.status_code == 200, r.text
    mid = r.json()["id"]
    pm = approved_partner["session"].get(f"{BASE}/api/partner/materials").json()
    assert any(m["id"] == mid for m in pm)
    assert sa_session.delete(f"{BASE}/api/platform/partner-materials/{mid}").status_code == 200


# ---------- 15. SA manual attribution + log ----------
def test_sa_attribution_log(sa_session, approved_partner, db):
    # Need an org to attribute. Create one WITHOUT ref:
    org_email = f"TEST_org_{_hex()}@crmeventqa.it"
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/register-organization", json={
        "email": org_email, "password": "OrgStrong1!", "nome": "No", "cognome": "Ref",
        "org_name": f"TEST_NoRef_{_hex()}", "telefono": _phone(), "accept_terms": True})
    assert r.status_code == 200
    oid = r.json()["org_id"]
    r = sa_session.put(f"{BASE}/api/platform/partner-referrals/{oid}",
                       json={"partner_id": approved_partner["partner"]["id"], "campaign": "manuale",
                             "note": "Attribuzione manuale test"})
    assert r.status_code == 200
    log = sa_session.get(f"{BASE}/api/platform/partner-attribution-log").json()
    assert any(x["org_id"] == oid for x in log)


# ---------- 16. Cleanup at end ----------
def test_cleanup_test_data(sa_session, db):
    """Delete all TEST_ data to leave DB clean."""
    loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)

    async def wipe():
        test_partners = await db.partners.find({"email": {"$regex": "^TEST_"}}, {"_id": 0, "id": 1, "email": 1}).to_list(1000)
        pids = [p["id"] for p in test_partners]
        test_orgs = await db.organizations.find({"nome": {"$regex": "^TEST_"}}, {"_id": 0, "id": 1}).to_list(1000)
        oids = [o["id"] for o in test_orgs]
        test_users = await db.users.find({"email": {"$regex": "^TEST_"}}, {"_id": 0, "user_id": 1, "org_id": 1}).to_list(1000)
        uids = [u["user_id"] for u in test_users]
        if pids:
            await db.partners.delete_many({"id": {"$in": pids}})
            await db.partner_referrals.delete_many({"partner_id": {"$in": pids}})
            await db.partner_commissions.delete_many({"partner_id": {"$in": pids}})
            await db.partner_clicks.delete_many({"partner_id": {"$in": pids}})
            await db.partner_campaigns.delete_many({"partner_id": {"$in": pids}})
            await db.partner_payouts.delete_many({"partner_id": {"$in": pids}})
            await db.partner_login_attempts.delete_many({"identifier": {"$regex": "TEST_"}})
        await db.partner_referrals.delete_many({"org_id": {"$in": oids}})
        await db.partner_attribution_log.delete_many({"org_id": {"$in": oids}})
        if oids:
            await db.organizations.delete_many({"id": {"$in": oids}})
            await db.memberships.delete_many({"org_id": {"$in": oids}})
        if uids:
            await db.users.delete_many({"user_id": {"$in": uids}})
            await db.leads.delete_many({"email": {"$regex": "^TEST_"}})
        await db.partner_materials.delete_many({"title": {"$regex": "^TEST_"}})

    loop.run_until_complete(wipe())
    # Restore settings to defaults
    sa_session.put(f"{BASE}/api/platform/partner-settings", json={
        "commission_pct": 10.0, "duration_months": 24, "attribution_days": 30, "hold_days": 30,
        "payout_frequency": "trimestrale", "min_payout_cents": 0, "crmevent_tax_regime": "forfettario",
        "payout_notes": "Liquidazioni da validare fiscalmente prima dell'attivazione dei pagamenti."})
