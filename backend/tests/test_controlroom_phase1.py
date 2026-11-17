# Control Room Phase 1: listing, checkout (Stripe test), confirmation, entitlement, webhook, activation/refund logic
import os, uuid, asyncio
import pytest, requests, bcrypt, stripe
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = BASE_URL + "/api"
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
SA = ("manara.michele.pro@gmail.com", "CrmEvent2026!")
BILLING = {"tipo": "azienda", "paese": "IT", "ragione_sociale": "TEST_Srl", "partita_iva": "01234567890", "indirizzo": "Via Roma 1",
           "cap": "20100", "citta": "Milano", "provincia": "MI", "codice_sdi": "0000000"}


def _new_org(label):
    s = requests.Session()
    em = f"test_cr_{label}_{uuid.uuid4().hex[:6]}@example.com"
    r = s.post(f"{API}/auth/register-organization", json={"nome": "TEST", "cognome": "CR", "email": em, "password": "TestCr2026!",
               "org_name": f"TEST_CR {label}", "telefono": "+393471234567", "accept_terms": True})
    assert r.status_code in (200, 201), r.text
    me = s.get(f"{API}/auth/me").json()
    oid = me.get("org_id") or me["user"]["org_id"]
    ev = s.post(f"{API}/events", json={"nome": f"TEST_CR_Ev_{label}", "data_inizio": "2026-12-10"}).json()["id"]
    return {"s": s, "email": em, "org_id": oid, "event": ev}


@pytest.fixture(scope="module")
def ctx():
    a, b = _new_org("A"), _new_org("B")
    # staff member of org A inserted directly
    staff_email = f"test_cr_staff_{uuid.uuid4().hex[:6]}@example.com"
    staff_uid = "user_test_" + uuid.uuid4().hex[:10]
    mdb.users.insert_one({"user_id": staff_uid, "email": staff_email, "name": "TEST Staff", "role": "staff", "auth_provider": "password",
                          "org_id": a["org_id"], "active": True, "password_hash": bcrypt.hashpw(b"TestCr2026!", bcrypt.gensalt()).decode()})
    mdb.memberships.insert_one({"id": uuid.uuid4().hex, "user_id": staff_uid, "org_id": a["org_id"], "role": "staff", "active": True, "permissions": {}})
    st = requests.Session()
    st.post(f"{API}/auth/login", json={"email": staff_email, "password": "TestCr2026!"})
    yield {"a": a, "b": b, "staff": st}
    # cleanup by ids
    mdb.controlroom_purchases.delete_many({"org_id": {"$in": [a["org_id"], b["org_id"]]}})
    mdb.users.delete_one({"user_id": staff_uid})
    mdb.memberships.delete_many({"user_id": staff_uid})
    sa = requests.Session(); sa.post(f"{API}/auth/login", json={"email": SA[0], "password": SA[1]})
    for o in (a, b):
        n = (mdb.organizations.find_one({"id": o["org_id"]}) or {}).get("nome")
        if n:
            sa.delete(f"{API}/platform/organizations/{o['org_id']}", json={"confirm_name": n})
        mdb.users.delete_many({"email": o["email"]})


class TestListAndStatus:
    def test_events_admin(self, ctx):
        r = ctx["a"]["s"].get(f"{API}/controlroom/events")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["price_net"] == 119 and d["can_purchase"] is True
        e = next(x for x in d["events"] if x["id"] == ctx["a"]["event"])
        assert e["active"] is False and e["pending"] is False
        assert all(x["id"] != ctx["b"]["event"] for x in d["events"])

    def test_events_staff(self, ctx):
        r = ctx["staff"].get(f"{API}/controlroom/events")
        assert r.status_code == 200, r.text
        assert r.json()["can_purchase"] is False

    def test_status_unpaid_and_cross_org(self, ctx):
        r = ctx["a"]["s"].get(f"{API}/controlroom/events/{ctx['a']['event']}/status")
        assert r.status_code == 200 and r.json()["active"] is False
        r = ctx["a"]["s"].get(f"{API}/controlroom/events/{ctx['b']['event']}/status")
        assert r.status_code == 404


class TestCheckout:
    def test_staff_forbidden(self, ctx):
        r = ctx["staff"].post(f"{API}/controlroom/events/{ctx['a']['event']}/checkout", json={"origin_url": BASE_URL})
        assert r.status_code == 403, r.text

    def test_missing_billing(self, ctx):
        r = ctx["a"]["s"].post(f"{API}/controlroom/events/{ctx['a']['event']}/checkout", json={"origin_url": BASE_URL})
        assert r.status_code == 400, r.text
        assert "fatturazione" in r.json()["detail"]

    def test_cross_org_404(self, ctx):
        r = ctx["a"]["s"].post(f"{API}/controlroom/events/{ctx['b']['event']}/checkout", json={"origin_url": BASE_URL})
        assert r.status_code == 404, r.text

    def test_checkout_creates_session(self, ctx):
        s, ev = ctx["a"]["s"], ctx["a"]["event"]
        assert s.put(f"{API}/account/billing", json=BILLING).status_code == 200
        r1 = s.post(f"{API}/controlroom/events/{ev}/checkout", json={"origin_url": BASE_URL})
        assert r1.status_code == 200, r1.text
        assert r1.json()["checkout_url"].startswith("https://checkout.stripe.com")
        r2 = s.post(f"{API}/controlroom/events/{ev}/checkout", json={"origin_url": BASE_URL})
        assert r2.status_code == 200, r2.text
        ps = list(mdb.controlroom_purchases.find({"org_id": ctx["a"]["org_id"], "event_id": ev}).sort("created_at", 1))
        assert [p["status"] for p in ps] == ["expired", "pending"]
        stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
        sess = stripe.checkout.Session.retrieve(ps[-1]["stripe_session_id"], expand=["line_items"])
        assert sess.mode == "payment" and sess.metadata["kind"] == "controlroom"
        li = sess.line_items.data[0]
        assert li.description == "CONTROL ROOM — 119,00 € / EVENTO" or li.price.product
        prod = stripe.Product.retrieve(li.price.product)
        assert prod.name == "CONTROL ROOM — 119,00 € / EVENTO"
        assert prod.description == "Evento: TEST_CR_Ev_A"
        assert li.price.unit_amount == 11900
        assert sess.total_details.amount_tax > 0, sess.total_details
        print("amount_total", sess.amount_total, "tax", sess.total_details.amount_tax)
        ctx["session_id"] = ps[-1]["stripe_session_id"]
        # list shows pending
        e = next(x for x in s.get(f"{API}/controlroom/events").json()["events"] if x["id"] == ev)
        assert e["pending"] is True and e["active"] is False

    def test_confirmation_unpaid_stays_pending(self, ctx):
        sid = ctx.get("session_id")
        assert sid
        r = ctx["a"]["s"].get(f"{API}/controlroom/confirmation", params={"session_id": sid})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "pending"
        assert ctx["a"]["s"].get(f"{API}/controlroom/events/{ctx['a']['event']}/status").json()["active"] is False

    def test_confirmation_cross_org_403(self, ctx):
        r = ctx["b"]["s"].get(f"{API}/controlroom/confirmation", params={"session_id": ctx["session_id"]})
        assert r.status_code == 403, r.text

    def test_confirmation_invalid_session(self, ctx):
        r = ctx["a"]["s"].get(f"{API}/controlroom/confirmation", params={"session_id": "cs_test_invalid123"})
        assert r.status_code in (400, 404), f"{r.status_code} {r.text[:200]}"


class TestWebhook:
    def test_unsigned_webhook_rejected(self):
        r = requests.post(f"{API}/stripe/webhook", json={"type": "checkout.session.completed", "data": {"object": {"metadata": {"kind": "controlroom"}}}})
        assert r.status_code == 400

    def test_activation_and_refund_logic(self, ctx):
        """Direct handler test with motor: paid session activates, idempotent, duplicate_paid, refund."""
        import sys
        sys.path.insert(0, "/app/backend")
        import controlroom
        from motor.motor_asyncio import AsyncIOMotorClient

        async def run():
            adb = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
            audits = []
            async def audit(*a, **k): audits.append(a[1])
            async def dep(*a, **k): return {}
            cr = controlroom.build(adb, {"require_admin": dep, "require_superadmin": dep, "get_current_user": dep, "audit": audit,
                                         "ensure_customer": dep, "billing_missing": lambda b: [], "tax_rate_id": lambda: None,
                                         "stripe_mode": "test", "logger": None})
            org, ev = ctx["a"]["org_id"], ctx["a"]["event"]
            p = await adb.controlroom_purchases.find_one({"org_id": org, "event_id": ev, "status": "pending"})
            md = {"kind": "controlroom", "purchase_id": p["id"], "org_id": org, "event_id": ev}
            # unpaid complete -> stays pending
            await cr["handle_webhook"]("checkout.session.completed", {"metadata": md, "status": "complete", "payment_status": "unpaid"})
            assert (await adb.controlroom_purchases.find_one({"id": p["id"]}))["status"] == "pending"
            # tampered metadata -> ignored
            await cr["handle_webhook"]("checkout.session.completed", {"metadata": {**md, "org_id": ctx["b"]["org_id"]}, "status": "complete", "payment_status": "paid"})
            assert (await adb.controlroom_purchases.find_one({"id": p["id"]}))["status"] == "pending"
            paid = {"metadata": md, "status": "complete", "payment_status": "paid", "payment_intent": "pi_TEST_cr1", "amount_total": 14518}
            await cr["handle_webhook"]("checkout.session.completed", paid)
            await cr["handle_webhook"]("checkout.session.completed", paid)  # idempotent
            doc = await adb.controlroom_purchases.find_one({"id": p["id"]})
            assert doc["status"] == "active" and doc["payment_intent"] == "pi_TEST_cr1"
            assert audits.count("controlroom_paid") == 1
            await cr["require_active"](org, ev)
            # duplicate paid on the expired one
            exp = await adb.controlroom_purchases.find_one({"org_id": org, "event_id": ev, "status": "expired"})
            md2 = {**md, "purchase_id": exp["id"]}
            await cr["handle_webhook"]("checkout.session.completed", {"metadata": md2, "status": "complete", "payment_status": "paid", "payment_intent": "pi_TEST_cr2"})
            assert (await adb.controlroom_purchases.find_one({"id": exp["id"]}))["status"] == "duplicate_paid"
            # refund not fully refunded -> ignored
            assert await cr["on_refund"]({"payment_intent": "pi_TEST_cr1", "refunded": False}) is False
            assert await cr["on_refund"]({"payment_intent": "pi_TEST_cr1", "refunded": True}) is True
            assert (await adb.controlroom_purchases.find_one({"id": p["id"]}))["status"] == "refunded"
            assert await cr["on_refund"]({"payment_intent": "pi_TEST_cr2", "refunded": True}) is True
            # unrelated charge -> False (falls through to PARTNER)
            assert await cr["on_refund"]({"payment_intent": "pi_unrelated", "refunded": True}) is False
            # expired webhook on pending
        asyncio.run(run())
        r = ctx["a"]["s"].get(f"{API}/controlroom/events/{ctx['a']['event']}/status")
        assert r.json()["active"] is False

    def test_paid_then_status_active_via_api(self, ctx):
        """Activate via handler then check public API reflects active + checkout 409."""
        org, ev = ctx["a"]["org_id"], ctx["a"]["event"]
        pid = uuid.uuid4().hex
        mdb.controlroom_purchases.insert_one({"id": pid, "org_id": org, "event_id": ev, "event_name": "TEST_CR_Ev_A", "status": "active", "amount_net": 119.0, "created_at": "2026-01-01"})
        r = ctx["a"]["s"].get(f"{API}/controlroom/events/{ev}/status")
        assert r.json()["active"] is True and r.json()["purchase"]["id"] == pid
        r = ctx["a"]["s"].post(f"{API}/controlroom/events/{ev}/checkout", json={"origin_url": BASE_URL})
        assert r.status_code == 409
        mdb.controlroom_purchases.delete_one({"id": pid})


class TestSuperadmin:
    def test_sa_list_and_checkout_without_org(self, ctx):
        sa = requests.Session(); sa.post(f"{API}/auth/login", json={"email": SA[0], "password": SA[1]})
        r = sa.get(f"{API}/platform/controlroom/purchases")
        assert r.status_code == 200 and isinstance(r.json(), list)
        assert ctx["a"]["s"].get(f"{API}/platform/controlroom/purchases").status_code == 403
        r = sa.post(f"{API}/controlroom/events/{ctx['a']['event']}/checkout", json={"origin_url": BASE_URL})
        assert r.status_code != 500, r.text[:200]
