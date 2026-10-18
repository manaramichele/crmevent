# Marketplace purchases + Stripe (TEST mode): checkout single/recurring, webhook activation/expiry/failed/paid,
# org mismatch, free activation, SA grant/orgs/stripe-sync/manual price, cancel/resume/portal, permissions, YouTube video.
# Run: cd /app/backend/tests && python -m pytest test_marketplace_stripe.py -v -n 0
import hashlib
import hmac
import json
import time
import uuid

import bcrypt
import pytest
import requests
import stripe
from pymongo import MongoClient

BASE_URL = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0].rstrip("/")
API = f"{BASE_URL}/api"
ENV = dict(l.split("=", 1) for l in open("/app/backend/.env").read().splitlines() if "=" in l)
ENV = {k: v.strip().strip('"') for k, v in ENV.items()}
DB = MongoClient(ENV["MONGO_URL"])[ENV["DB_NAME"]]
stripe.api_key = ENV["STRIPE_SECRET_KEY"]
WH = ENV["STRIPE_WEBHOOK_SECRET"]
SA_EMAIL, SA_PW = "manara.michele.pro@gmail.com", "CrmEvent2026!"
TS = str(int(time.time()))
PW = "Password123!"
ORIGIN = BASE_URL
S = {}
BILLING = {"tipo": "azienda", "ragione_sociale": "TEST_MKT Srl", "indirizzo": "Via Roma 1", "cap": "20100", "citta": "Milano",
           "provincia": "MI", "paese": "IT", "partita_iva": "12345678901", "codice_sdi": "0000000"}


def _register(tag):
    s = requests.Session()
    email = f"test_mkt{tag}_{TS}@example.com"
    r = s.post(f"{API}/auth/register-organization", json={"nome": "Test", "cognome": tag, "email": email, "password": PW,
                                                          "org_name": f"TEST_MKT {tag} {TS}", "telefono": "+393471234567", "accept_terms": True})
    assert r.status_code in (200, 201), r.text
    me = s.get(f"{API}/auth/me").json()
    org = me.get("org_id") or (me.get("organization") or {}).get("id")
    br = s.put(f"{API}/account/billing", json=BILLING)
    assert br.status_code == 200, br.text
    return s, email, org


def _svc(name, price, ptype, **kw):
    body = {"name": f"TEST_{name}_{TS}", "description": "test", "category": "Altro", "price": price, "price_type": ptype,
            "status": "available", "visible": True, "purchasable": True, "tech_ready": True, "scope": "org", **kw}
    r = S["sa"].post(f"{API}/platform/marketplace/services", json=body)
    assert r.status_code == 200, r.text
    S["svcs"].append(r.json()["id"])
    return r.json()


def _webhook(t, obj):
    payload = json.dumps({"id": f"evt_test_{uuid.uuid4().hex[:12]}", "object": "event", "type": t, "data": {"object": obj},
                          "api_version": "2024-06-20", "created": int(time.time())})
    ts = int(time.time())
    sig = hmac.new(WH.encode(), f"{ts}.{payload}".encode(), hashlib.sha256).hexdigest()
    return requests.post(f"{API}/stripe/webhook", data=payload, headers={"stripe-signature": f"t={ts},v1={sig}", "Content-Type": "application/json"})


def _checkout(sess, sid):
    return sess.post(f"{API}/marketplace/services/{sid}/checkout", json={"origin_url": ORIGIN})


def _pending(org, sid):
    return DB.marketplace_purchases.find_one({"org_id": org, "service_id": sid, "status": "pending"}, {"_id": 0}, sort=[("created_at", -1)])


@pytest.fixture(scope="module", autouse=True)
def setup_and_cleanup():
    sa = requests.Session()
    assert sa.post(f"{API}/auth/login", json={"email": SA_EMAIL, "password": SA_PW}).status_code == 200
    S.update(sa=sa, svcs=[], subs=[])
    S["a"], S["a_email"], S["a_org"] = _register("A")
    S["b"], S["b_email"], S["b_org"] = _register("B")
    uid = f"user_test_{uuid.uuid4().hex[:10]}"
    S["m_email"] = f"test_mktm_{TS}@example.com"
    now = "2026-01-01T00:00:00+00:00"
    DB.users.insert_one({"user_id": uid, "email": S["m_email"], "name": "Test Member", "password_hash": bcrypt.hashpw(PW.encode(), bcrypt.gensalt()).decode(),
                         "role": "member", "auth_provider": "password", "telefono": "+393331112222", "org_id": S["a_org"], "picture": "", "active": True,
                         "accepted_terms_at": now, "terms_version": "x", "privacy_version": "x", "created_at": now, "registered_at": now})
    DB.memberships.insert_one({"id": uuid.uuid4().hex, "user_id": uid, "org_id": S["a_org"], "role": "user", "active": True, "permissions": {}, "created_at": now, "updated_at": now})
    m = requests.Session()
    S["m"] = m if m.post(f"{API}/auth/login", json={"email": S["m_email"], "password": PW}).status_code == 200 else None
    S["monthly"] = _svc("Monthly", 9, "monthly")
    S["once"] = _svc("Once", 5, "one_time")
    S["free"] = _svc("Free", 0, "monthly")
    yield
    for sub in S["subs"]:
        try:
            stripe.Subscription.cancel(sub)
        except Exception:
            pass
    for sid in S["svcs"]:
        sp = (DB.marketplace_services.find_one({"id": sid}) or {}).get("stripe_prices") or {}
        for v in sp.values():
            try:
                stripe.Price.modify(v["price_id"], active=False)
                stripe.Product.modify(v["product_id"], active=False)
            except Exception:
                pass
    orgs = [S["a_org"], S["b_org"]]
    users = [u["user_id"] for u in DB.users.find({"$or": [{"org_id": {"$in": orgs}}, {"email": {"$in": [S["a_email"], S["b_email"], S["m_email"]]}}]})]
    for c in DB.list_collection_names():
        if c != "audit_logs":
            DB[c].delete_many({"org_id": {"$in": orgs}})
    DB.memberships.delete_many({"user_id": {"$in": users}})
    DB.users.delete_many({"user_id": {"$in": users}})
    DB.organizations.delete_many({"id": {"$in": orgs}})
    DB.marketplace_services.delete_many({"id": {"$in": S["svcs"]}})
    DB.marketplace_purchases.delete_many({"service_id": {"$in": S["svcs"]}})


class TestCheckout:
    def test_paid_monthly_checkout_pending(self):
        r = _checkout(S["a"], S["monthly"]["id"])
        assert r.status_code == 200, r.text
        assert "checkout.stripe.com" in r.json()["checkout_url"]
        p = _pending(S["a_org"], S["monthly"]["id"])
        assert p and p["source"] == "stripe" and p["stripe_mode"] == "test" and p["stripe_price_id"].startswith("price_")
        S["mon_pid"], S["mon_sess"] = p["id"], p["stripe_session_id"]
        svc = next(x for x in S["a"].get(f"{API}/marketplace/services").json()["services"] if x["id"] == S["monthly"]["id"])
        assert svc["active"] is False
        sess = stripe.checkout.Session.retrieve(p["stripe_session_id"])
        assert sess.mode == "subscription" and sess.metadata["kind"] == "marketplace" and sess.metadata["purchase_id"] == p["id"]

    def test_price_reused_on_second_checkout(self):
        r = _checkout(S["a"], S["monthly"]["id"])
        assert r.status_code == 200
        ps = DB.marketplace_purchases.find({"org_id": S["a_org"], "service_id": S["monthly"]["id"], "status": "pending"})
        assert len({p["stripe_price_id"] for p in ps}) == 1

    def test_expired_trial_can_checkout_and_iscritti_write(self):
        DB.organizations.update_one({"id": S["b_org"]}, {"$set": {"saas.trial_end": "2020-01-01T00:00:00+00:00"}})
        ev = uuid.uuid4().hex
        DB.events.insert_one({"id": ev, "org_id": S["b_org"], "nome": "TEST_EV", "created_at": "2026-01-01T00:00:00+00:00"})
        # readonly enforced on a normal write
        ro = S["b"].post(f"{API}/events", json={"nome": "TEST_x"})
        print("events write expired:", ro.status_code, ro.text[:200])
        r = _checkout(S["b"], S["once"]["id"])
        assert r.status_code == 200, r.text
        assert "checkout.stripe.com" in r.json()["checkout_url"]
        iscr = DB.marketplace_services.find_one({"key": "archivio-iscritti"}, {"_id": 0, "id": 1})
        g = S["sa"].post(f"{API}/platform/marketplace/services/{iscr['id']}/grant", json={"org_id": S["b_org"], "note": "TEST"})
        assert g.status_code == 200, g.text
        e = S["b"].post(f"{API}/iscritti/edizioni", json={"event_id": ev, "anno": 2026, "edizione": "1a", "gare": []})
        assert e.status_code == 200, e.text
        assert ro.status_code == 403 and "plan_readonly" in ro.text


class TestWebhook:
    def _sess_obj(self, p, org=None, status="complete", pay="paid", sub=None):
        return {"id": p["stripe_session_id"], "object": "checkout.session", "status": status, "payment_status": pay, "subscription": sub,
                "metadata": {"kind": "marketplace", "purchase_id": p["id"], "org_id": org or p["org_id"], "service_id": p["service_id"]}}

    def test_one_time_completed_activates(self):
        assert _checkout(S["a"], S["once"]["id"]).status_code == 200
        p = _pending(S["a_org"], S["once"]["id"])
        r = _webhook("checkout.session.completed", self._sess_obj(p))
        assert r.status_code == 200, r.text
        q = DB.marketplace_purchases.find_one({"id": p["id"]})
        assert q["status"] == "active" and q["activated_at"]
        S["once_pid"] = p["id"]
        # replay idempotent
        assert _webhook("checkout.session.completed", self._sess_obj(p)).status_code == 200
        assert DB.marketplace_purchases.find_one({"id": p["id"]})["status"] == "active"

    def test_bad_signature_rejected(self):
        r = requests.post(f"{API}/stripe/webhook", data="{}", headers={"stripe-signature": "t=1,v1=bad"})
        assert r.status_code == 400

    def test_org_mismatch_not_activated(self):
        assert _checkout(S["a"], S["once"]["id"]).status_code == 200
        p = _pending(S["a_org"], S["once"]["id"])
        assert _webhook("checkout.session.completed", self._sess_obj(p, org=S["b_org"])).status_code == 200
        assert DB.marketplace_purchases.find_one({"id": p["id"]})["status"] == "pending"
        S["mismatch_pid"] = p["id"]

    def test_unpaid_not_activated(self):
        p = DB.marketplace_purchases.find_one({"id": S["mismatch_pid"]})
        assert _webhook("checkout.session.completed", self._sess_obj(p, pay="unpaid")).status_code == 200
        assert DB.marketplace_purchases.find_one({"id": p["id"]})["status"] == "pending"

    def test_session_expired(self):
        p = DB.marketplace_purchases.find_one({"id": S["mismatch_pid"]})
        assert _webhook("checkout.session.expired", self._sess_obj(p, status="expired", pay="unpaid")).status_code == 200
        assert DB.marketplace_purchases.find_one({"id": p["id"]})["status"] == "expired"

    def test_subscription_lifecycle(self):
        p = DB.marketplace_purchases.find_one({"id": S["mon_pid"]})
        cust = DB.organizations.find_one({"id": S["a_org"]})["subscription"]["stripe_customer_id"]
        pm = stripe.PaymentMethod.attach("pm_card_visa", customer=cust)
        stripe.Customer.modify(cust, invoice_settings={"default_payment_method": pm.id})
        md = {"kind": "marketplace", "purchase_id": p["id"], "org_id": S["a_org"], "service_id": p["service_id"]}
        sub = stripe.Subscription.create(customer=cust, items=[{"price": p["stripe_price_id"]}], metadata=md)
        S["subs"].append(sub.id)
        S["sub"], S["cust"], S["md"] = sub.id, cust, md
        r = _webhook("checkout.session.completed", self._sess_obj(p, sub=sub.id))
        assert r.status_code == 200, r.text
        q = DB.marketplace_purchases.find_one({"id": p["id"]})
        assert q["status"] == "active" and q["stripe_subscription_id"] == sub.id and q["current_period_end"], q

    def test_invoice_failed_then_paid(self):
        now = int(time.time())
        inv = {"id": f"in_test_{TS}", "object": "invoice", "customer": S["cust"], "subscription": S["sub"], "total": 900, "subtotal": 900,
               "currency": "eur", "created": now, "number": "TEST-1", "metadata": {},
               "parent": {"subscription_details": {"subscription": S["sub"], "metadata": S["md"]}},
               "lines": {"data": [{"period": {"start": now, "end": now + 31 * 86400}, "metadata": {}}]},
               "last_finalization_error": {"message": "Card declined TEST"}}
        assert _webhook("invoice.payment_failed", inv).status_code == 200
        q = DB.marketplace_purchases.find_one({"id": S["mon_pid"]})
        assert q["status"] == "past_due" and "declined" in (q.get("last_payment_error") or ""), q.get("status")
        inv.pop("last_finalization_error")
        assert _webhook("invoice.paid", inv).status_code == 200
        q = DB.marketplace_purchases.find_one({"id": S["mon_pid"]})
        assert q["status"] == "active" and q.get("last_payment_error") is None
        assert q["current_period_end"].startswith(time.strftime("%Y-%m-%d", time.gmtime(now + 31 * 86400)))
        assert _webhook("invoice.paid", inv).status_code == 200  # replay
        rows = list(DB.invoices.find({"stripe_invoice_id": inv["id"]}))
        assert len(rows) == 1, len(rows)
        assert rows[0]["kind"] == "marketplace" and rows[0]["marketplace_purchase_id"] == S["mon_pid"] and rows[0]["is_test"] is True
        assert rows[0]["org_id"] == S["a_org"] and rows[0]["totale"] == 9.0

    def test_saas_org_unaffected(self):
        o = DB.organizations.find_one({"id": S["a_org"]}, {"_id": 0, "saas": 1})
        assert not (o.get("saas") or {}).get("stripe_subscription_id")

    def test_dup_active_recurring_rejected(self):
        r = _checkout(S["a"], S["monthly"]["id"])
        assert r.status_code == 400 and "già attivo" in r.text


class TestCancelResumePortal:
    def test_cancel_resume_subscription(self):
        r = S["a"].post(f"{API}/marketplace/purchases/{S['mon_pid']}/cancel")
        assert r.status_code == 200, r.text
        assert r.json()["cancel_at_period_end"] is True and r.json()["status"] == "active"
        assert stripe.Subscription.retrieve(S["sub"]).cancel_at_period_end is True
        r = S["a"].post(f"{API}/marketplace/purchases/{S['mon_pid']}/resume")
        assert r.status_code == 200 and r.json()["cancel_at_period_end"] is False

    def test_portal(self):
        r = S["a"].post(f"{API}/marketplace/portal", json={"origin_url": ORIGIN})
        assert r.status_code == 200, r.text
        assert "billing.stripe.com" in r.json()["url"]

    def test_one_time_cancel_rejected(self):
        r = S["a"].post(f"{API}/marketplace/purchases/{S['once_pid']}/cancel")
        assert r.status_code == 400


class TestFree:
    def test_free_activation_dup_cancel_and_others_remain(self):
        r = _checkout(S["a"], S["free"]["id"])
        assert r.status_code == 200 and r.json() == {"activated": True}
        p = DB.marketplace_purchases.find_one({"org_id": S["a_org"], "service_id": S["free"]["id"]})
        assert p["source"] == "free" and p["status"] == "active"
        d = _checkout(S["a"], S["free"]["id"])
        assert d.status_code == 400 and "Servizio già attivo" in d.text
        act = {x["id"]: x["active"] for x in S["a"].get(f"{API}/marketplace/services").json()["services"]}
        assert act[S["free"]["id"]] and act[S["monthly"]["id"]] and act[S["once"]["id"]]
        c = S["a"].post(f"{API}/marketplace/purchases/{p['id']}/cancel")
        assert c.status_code == 200 and c.json()["status"] == "canceled"
        act = {x["id"]: x["active"] for x in S["a"].get(f"{API}/marketplace/services").json()["services"]}
        assert not act[S["free"]["id"]] and act[S["monthly"]["id"]] and act[S["once"]["id"]]
        my = S["a"].get(f"{API}/marketplace/my").json()
        assert all(x["status"] != "pending" for x in my)
        S["free_pid"] = p["id"]


class TestPermissions:
    def test_member_cannot_checkout_or_cancel(self):
        if not S["m"]:
            pytest.skip("member login failed")
        assert _checkout(S["m"], S["once"]["id"]).status_code == 403
        assert S["m"].post(f"{API}/marketplace/purchases/{S['mon_pid']}/cancel").status_code == 403

    def test_cross_org_cancel_404(self):
        assert S["b"].post(f"{API}/marketplace/purchases/{S['mon_pid']}/cancel").status_code == 404

    def test_cross_org_confirmation_403(self):
        r = S["b"].get(f"{API}/marketplace/checkout-confirmation", params={"session_id": DB.marketplace_purchases.find_one({"id": S["mon_pid"]})["stripe_session_id"]})
        assert r.status_code == 403

    def test_org_admin_cannot_use_platform(self):
        assert S["a"].get(f"{API}/platform/marketplace/orgs").status_code in (401, 403)


class TestSuperAdmin:
    def test_orgs_and_grant(self):
        orgs = S["sa"].get(f"{API}/platform/marketplace/orgs").json()
        assert any(o["id"] == S["a_org"] for o in orgs)
        g = S["sa"].post(f"{API}/platform/marketplace/services/{S['monthly']['id']}/grant", json={"org_id": S["b_org"], "note": "TEST grant"})
        assert g.status_code == 200, g.text
        assert g.json()["source"] == "manual" and g.json()["status"] == "active"
        d = S["sa"].post(f"{API}/platform/marketplace/services/{S['monthly']['id']}/grant", json={"org_id": S["b_org"]})
        assert d.status_code == 400
        assert S["sa"].post(f"{API}/platform/marketplace/services/{S['monthly']['id']}/grant", json={"org_id": "nope"}).status_code == 404
        rows = S["sa"].get(f"{API}/platform/marketplace/purchases").json()
        assert any(r["id"] == g.json()["id"] and r["org_name"] for r in rows)

    def test_stripe_sync_and_manual_price(self):
        svc = _svc("Yearly", 12, "yearly")
        r = S["sa"].post(f"{API}/platform/marketplace/services/{svc['id']}/stripe-sync")
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["price_id"].startswith("price_") and j["product_id"].startswith("prod_") and j["stripe_mode"] == "test"
        pr = stripe.Price.retrieve(j["price_id"])
        assert pr.unit_amount == 1200 and pr.recurring.interval == "year"
        assert S["sa"].post(f"{API}/platform/marketplace/services/{S['free']['id']}/stripe-sync").status_code == 400
        body = {k: svc.get(k) for k in ("name", "description", "category", "price", "price_type", "status", "visible", "purchasable", "tech_ready", "scope")}
        bad = S["sa"].put(f"{API}/platform/marketplace/services/{svc['id']}", json={**body, "stripe_price_id": S["monthly_price"] if "monthly_price" in S else
                          DB.marketplace_services.find_one({"id": S["monthly"]["id"]})["stripe_prices"]["test"]["price_id"]})
        assert bad.status_code == 400, bad.text
        nf = S["sa"].put(f"{API}/platform/marketplace/services/{svc['id']}", json={**body, "stripe_price_id": "price_doesnotexist"})
        assert nf.status_code == 400
        good = stripe.Price.create(product=j["product_id"], currency="eur", unit_amount=1200, recurring={"interval": "year"})
        ok = S["sa"].put(f"{API}/platform/marketplace/services/{svc['id']}", json={**body, "stripe_price_id": good.id})
        assert ok.status_code == 200, ok.text
        cur = S["sa"].get(f"{API}/platform/marketplace/services").json()
        row = next(x for x in cur["services"] if x["id"] == svc["id"])
        assert row["stripe"]["price_id"] == good.id and row["stripe"]["source"] == "manual"

    @pytest.mark.parametrize("url,vid", [("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
                                         ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=5", "dQw4w9WgXcQ"),
                                         ("https://youtube.com/shorts/abcdefghijk", "abcdefghijk")])
    def test_video_urls(self, url, vid):
        s = S["free"]
        body = {k: s.get(k) for k in ("name", "description", "category", "price", "price_type", "status", "visible", "purchasable", "tech_ready", "scope")}
        r = S["sa"].put(f"{API}/platform/marketplace/services/{s['id']}", json={**body, "video_url": url, "video_title": "TEST tutorial"})
        assert r.status_code == 200 and r.json()["video_id"] == vid
        pub = next(x for x in S["a"].get(f"{API}/marketplace/services").json()["services"] if x["id"] == s["id"])
        assert pub["video_id"] == vid and pub["video_title"] == "TEST tutorial"

    def test_video_invalid(self):
        s = S["free"]
        body = {k: s.get(k) for k in ("name", "description", "category", "price", "price_type", "status", "visible", "purchasable", "tech_ready", "scope")}
        r = S["sa"].put(f"{API}/platform/marketplace/services/{s['id']}", json={**body, "video_url": "https://vimeo.com/123"})
        assert r.status_code == 400
        r = S["sa"].put(f"{API}/platform/marketplace/services/{s['id']}", json={**body, "video_url": ""})
        assert r.status_code == 200 and r.json()["video_id"] is None
