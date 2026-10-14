# Iteration 135: availability event-day + mandatory activity preference; Super Admin profile edit; Brevo profile sync unit tests
import os
import sys
import time
import uuid
import asyncio
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
SA = ("manara.michele.pro@gmail.com", "CrmEvent2026!")
QA = ("qa.eventi@crmeventqa.it", "QaEvents2026!")
QA_ORG = "org_qa_eventi"

_mongo = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
mdb = _mongo[os.environ.get("DB_NAME", "test_database")]


def login(email, pwd):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pwd})
    assert r.status_code == 200, r.text
    return s


def _xff():
    return {"X-Forwarded-For": f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"}


# ---------------- Availability ----------------
@pytest.fixture(scope="module")
def avail_ctx():
    s = login(*QA)
    s.headers.update({"X-Org-Id": QA_ORG})
    ev = {"nome": "TEST_AvailEventDay", "data_inizio_allestimento": "2026-11-08", "data_inizio": "2026-11-10",
          "data_fine": "2026-11-11", "data_fine_disallestimento": "2026-11-13", "localita": "Milano"}
    r = s.post(f"{BASE_URL}/api/events", json=ev)
    assert r.status_code in (200, 201), r.text
    eid = r.json()["id"]
    r = s.post(f"{BASE_URL}/api/events/{eid}/availability/link")
    assert r.status_code == 200, r.text
    code = r.json()["code"]
    info = requests.get(f"{BASE_URL}/api/public/availability/{code}").json()
    yield {"eid": eid, "code": code, "info": info, "s": s}
    mdb.availabilities.delete_many({"evento_id": eid})
    mdb.avail_links.delete_many({"evento_id": eid})
    mdb.persons.delete_many({"org_id": QA_ORG, "email": {"$regex": "^test_avail_"}})
    mdb.events.delete_many({"id": eid})


def _body(days, pref="Nessuna preferenza", altro=None, email=None):
    return {"nome": "TEST_Mario", "cognome": "Rossi", "cellulare": f"+39333{uuid.uuid4().int % 10**7:07d}",
            "email": email or f"test_avail_{uuid.uuid4().hex[:8]}@example.com",
            "data_nascita": "1990-01-01", "days": [{"date": d, "disponibile": True} for d in days],
            "preferenza_attivita": pref, "preferenza_altro": altro, "privacy": True}


class TestAvailability:
    def test_days_phases(self, avail_ctx):
        days = avail_ctx["info"]["days"]
        f = {d["date"]: d["fase"] for d in days}
        assert f["2026-11-08"] == "allestimento" and f["2026-11-09"] == "allestimento"
        assert f["2026-11-10"] == "evento" and f["2026-11-11"] == "evento"
        assert f["2026-11-12"] == "disallestimento" and f["2026-11-13"] == "disallestimento"

    def test_only_setup_teardown_rejected(self, avail_ctx):
        r = requests.post(f"{BASE_URL}/api/public/availability/{avail_ctx['code']}",
                          json=_body(["2026-11-08", "2026-11-12"]), headers=_xff())
        assert r.status_code == 400, r.text
        assert r.json()["detail"] == "Seleziona almeno un giorno dell'evento in cui sei disponibile."

    def test_one_event_day_ok(self, avail_ctx):
        r = requests.post(f"{BASE_URL}/api/public/availability/{avail_ctx['code']}",
                          json=_body(["2026-11-10"]), headers=_xff())
        assert r.status_code == 200, r.text

    def test_multi_event_days_with_setup_ok(self, avail_ctx):
        em = f"test_avail_multi_{uuid.uuid4().hex[:6]}@example.com"
        r = requests.post(f"{BASE_URL}/api/public/availability/{avail_ctx['code']}",
                          json=_body(["2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12"], pref="Altro", altro="Fotografo", email=em),
                          headers=_xff())
        assert r.status_code == 200, r.text
        a = mdb.availabilities.find_one({"evento_id": avail_ctx["eid"], "email": em})
        assert a and len(a["days"]) == 4
        assert a["preferenza_attivita"] == "Altro" and a["preferenza_altro"] == "Fotografo"

    # iter137: activity preference is OPTIONAL again (user decision)
    def test_missing_pref_accepted(self, avail_ctx):
        r = requests.post(f"{BASE_URL}/api/public/availability/{avail_ctx['code']}",
                          json=_body(["2026-11-10"], pref=None), headers=_xff())
        assert r.status_code == 200, r.text

    def test_altro_without_text_accepted(self, avail_ctx):
        r = requests.post(f"{BASE_URL}/api/public/availability/{avail_ctx['code']}",
                          json=_body(["2026-11-10"], pref="Altro", altro="  "), headers=_xff())
        assert r.status_code == 200, r.text

    def test_no_days_rejected(self, avail_ctx):
        r = requests.post(f"{BASE_URL}/api/public/availability/{avail_ctx['code']}",
                          json=_body([]), headers=_xff())
        assert r.status_code == 400


# ---------------- Profile edit ----------------
def _register(prefix):
    s = requests.Session()
    em = f"TEST_{prefix}_{uuid.uuid4().hex[:6]}@example.com".lower()
    r = s.post(f"{BASE_URL}/api/auth/register-organization", json={
        "nome": "Tizio", "cognome": "Prova", "email": em, "password": "TestPass123!",
        "org_name": f"TEST_Org_{prefix}_{uuid.uuid4().hex[:4]}", "telefono": "+393401234567", "accept_terms": True})
    assert r.status_code == 200, r.text
    u = mdb.users.find_one({"email": em}, {"_id": 0})
    return u, s


@pytest.fixture(scope="module")
def prof_ctx():
    sa = login(*SA)
    u1, s1 = _register("pe1")
    u2, _ = _register("pe2")
    # extra org membership for u1 (multi-org) + linked persona + google_sub marker
    extra_org = mdb.users.find_one({"user_id": u2["user_id"]})["org_id"]
    mdb.memberships.insert_one({"id": f"TEST_m_{uuid.uuid4().hex[:6]}", "user_id": u1["user_id"], "org_id": extra_org,
                                "role": "operatore", "active": True, "created_at": "x"})
    pid = f"TEST_p_{uuid.uuid4().hex[:6]}"
    mdb.persons.insert_one({"id": pid, "org_id": u1["org_id"], "nome": "Tizio", "cognome": "Prova",
                            "email": u1["email"], "cellulare": "+393401234567"})
    mdb.users.update_one({"user_id": u1["user_id"]}, {"$set": {"person_id": pid, "google_sub": "TEST_gsub_123"}})
    created_orgs = [u1["org_id"], u2["org_id"]]
    yield {"sa": sa, "u1": mdb.users.find_one({"user_id": u1["user_id"]}, {"_id": 0}), "u2": u2, "s1": s1, "pid": pid}
    uids = [u1["user_id"], u2["user_id"]]
    mdb.memberships.delete_many({"user_id": {"$in": uids}})
    mdb.users.delete_many({"user_id": {"$in": uids}})
    mdb.persons.delete_many({"id": pid})
    for o in created_orgs:
        for c in ("organizations",):
            mdb[c].delete_many({"id": o})
        mdb.settings.delete_many({"id": o})
        mdb.subscriptions.delete_many({"org_id": o})


class TestProfileEdit:
    def test_non_superadmin_forbidden(self, prof_ctx):
        u1 = prof_ctx["u1"]
        r = prof_ctx["s1"].patch(f"{BASE_URL}/api/platform/users/{u1['user_id']}/profile",
                                 json={"nome": "X", "email": u1["email"], "telefono": "+393401234567"})
        assert r.status_code == 403

    def test_name_phone_change(self, prof_ctx):
        u1 = prof_ctx["u1"]
        before_mems = sorted([(m["org_id"], m["role"]) for m in mdb.memberships.find({"user_id": u1["user_id"]})])
        r = prof_ctx["sa"].patch(f"{BASE_URL}/api/platform/users/{u1['user_id']}/profile",
                                 json={"nome": "caio", "cognome": "nuovo", "email": u1["email"], "telefono": "+39 347 555 1234"})
        assert r.status_code == 200, r.text
        j = r.json()
        assert set(j["changes"]) >= {"nome", "cognome", "cellulare"}
        assert j["brevo"] == "non_configurato"
        u = mdb.users.find_one({"user_id": u1["user_id"]})
        assert u["nome"] == "Caio" and u["cognome"] == "Nuovo" and u["telefono"] == "+393475551234"
        assert u["name"] == "Caio Nuovo"
        assert u["role"] == u1["role"] and u["org_id"] == u1["org_id"] and u.get("google_sub") == "TEST_gsub_123"
        after_mems = sorted([(m["org_id"], m["role"]) for m in mdb.memberships.find({"user_id": u1["user_id"]})])
        assert before_mems == after_mems and len(after_mems) == 2
        p = mdb.persons.find_one({"id": prof_ctx["pid"]})
        assert p["nome"] == "Caio" and p["cognome"] == "Nuovo" and p["cellulare"] == "+393475551234"

    def test_invalid_phone(self, prof_ctx):
        u1 = prof_ctx["u1"]
        r = prof_ctx["sa"].patch(f"{BASE_URL}/api/platform/users/{u1['user_id']}/profile",
                                 json={"nome": "Caio", "cognome": "Nuovo", "email": u1["email"], "telefono": "12"})
        assert r.status_code == 400

    def test_email_change_requires_confirm(self, prof_ctx):
        u1 = prof_ctx["u1"]
        r = prof_ctx["sa"].patch(f"{BASE_URL}/api/platform/users/{u1['user_id']}/profile",
                                 json={"nome": "Caio", "cognome": "Nuovo", "email": "test_newmail_x@example.com", "telefono": "+393475551234"})
        assert r.status_code == 400
        assert "Conferma" in r.json()["detail"]

    def test_email_clash_case_insensitive(self, prof_ctx):
        u1, u2 = prof_ctx["u1"], prof_ctx["u2"]
        r = prof_ctx["sa"].patch(f"{BASE_URL}/api/platform/users/{u1['user_id']}/profile",
                                 json={"nome": "Caio", "cognome": "Nuovo", "email": u2["email"].upper(), "telefono": "+393475551234",
                                       "confirm_email_change": True})
        assert r.status_code == 400
        assert "Esiste già" in r.json()["detail"]

    def test_email_change_confirmed_and_login(self, prof_ctx):
        u1 = prof_ctx["u1"]
        new_email = f"TEST_renamed_{uuid.uuid4().hex[:6]}@Example.com"
        users_before = mdb.users.count_documents({})
        r = prof_ctx["sa"].patch(f"{BASE_URL}/api/platform/users/{u1['user_id']}/profile",
                                 json={"nome": "Caio", "cognome": "Nuovo", "email": new_email, "telefono": "+393475551234",
                                       "confirm_email_change": True})
        assert r.status_code == 200, r.text
        assert "email" in r.json()["changes"]
        assert mdb.users.count_documents({}) == users_before
        u = mdb.users.find_one({"user_id": u1["user_id"]})
        assert u["email"] == new_email.lower()
        assert u.get("google_sub") == "TEST_gsub_123" and u["role"] == u1["role"]
        assert mdb.memberships.count_documents({"user_id": u1["user_id"], "active": True}) == 2
        p = mdb.persons.find_one({"id": prof_ctx["pid"]})
        assert p["email"] == new_email.lower()
        assert mdb.persons.count_documents({"org_id": u1["org_id"], "email": new_email.lower()}) == 1
        # login with new email works, old doesn't
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": new_email.lower(), "password": "TestPass123!"})
        assert r.status_code == 200, r.text
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": u1["email"], "password": "TestPass123!"})
        assert r.status_code in (400, 401)
        # audit log
        a = mdb.audit_log.find_one({"action": "account_profile_updated", "meta.user_id": u1["user_id"],
                                    "meta.changes.email": {"$exists": True}}, sort=[("_id", -1)]) \
            or mdb.audit_logs.find_one({"action": "account_profile_updated", "meta.user_id": u1["user_id"],
                                        "meta.changes.email": {"$exists": True}}, sort=[("_id", -1)])
        assert a is not None
        assert a["meta"]["changes"]["email"]["prima"] == u1["email"]
        assert a["meta"]["changes"]["email"]["dopo"] == new_email.lower()

    def test_no_change_noop(self, prof_ctx):
        u = mdb.users.find_one({"user_id": prof_ctx["u1"]["user_id"]})
        r = prof_ctx["sa"].patch(f"{BASE_URL}/api/platform/users/{u['user_id']}/profile",
                                 json={"nome": u["nome"], "cognome": u["cognome"], "email": u["email"], "telefono": u["telefono"]})
        assert r.status_code == 200 and r.json()["changes"] == []

    def test_superadmin_not_editable(self, prof_ctx):
        sa_u = mdb.users.find_one({"role": "superadmin"})
        r = prof_ctx["sa"].patch(f"{BASE_URL}/api/platform/users/{sa_u['user_id']}/profile",
                                 json={"nome": "X", "email": sa_u["email"], "telefono": "+393401234567"})
        assert r.status_code == 400


# ---------------- Brevo unit tests ----------------
sys.path.insert(0, "/app/backend")


@pytest.fixture(scope="module")
def srv():
    import server  # noqa
    return server


class TestBrevoProfileSync:
    def _run(self, srv, monkeypatch, responses, old, new):
        calls = []

        async def fake_req(method, path, json=None, params=None):
            calls.append((method, path, json))
            return responses.pop(0)
        monkeypatch.setattr(srv.brevo_funnel, "is_configured", lambda: True)
        monkeypatch.setattr(srv.brevo_funnel, "_request", fake_req)
        res = asyncio.get_event_loop().run_until_complete(srv._brevo_profile_sync(old, new, "Caio", "Nuovo", "+393475551234")) \
            if False else asyncio.run(srv._brevo_profile_sync(old, new, "Caio", "Nuovo", "+393475551234"))
        return res, calls

    def test_not_configured(self, srv, monkeypatch):
        monkeypatch.setattr(srv.brevo_funnel, "is_configured", lambda: False)
        assert asyncio.run(srv._brevo_profile_sync("a@x.it", "b@x.it", "A", "B", None)) == "non_configurato"

    def test_rename(self, srv, monkeypatch):
        res, calls = self._run(srv, monkeypatch, [(204, None, None)], "old@x.it", "new@x.it")
        assert res == "aggiornato"
        assert calls[0][0] == "PUT" and calls[0][1] == "/v3/contacts/old%40x.it"
        assert calls[0][2]["attributes"] == {"EMAIL": "new@x.it", "NOME": "Caio", "COGNOME": "Nuovo", "CELLULARE": "+393475551234"}

    def test_same_email_no_email_attr(self, srv, monkeypatch):
        res, calls = self._run(srv, monkeypatch, [(204, None, None)], "old@x.it", "old@x.it")
        assert res == "aggiornato" and "EMAIL" not in calls[0][2]["attributes"]

    def test_404(self, srv, monkeypatch):
        res, calls = self._run(srv, monkeypatch, [(404, None, "not found")], "old@x.it", "new@x.it")
        assert res == "contatto_assente" and len(calls) == 1

    def test_conflict_updates_new(self, srv, monkeypatch):
        res, calls = self._run(srv, monkeypatch, [(400, None, "duplicate"), (204, None, None)], "old@x.it", "new@x.it")
        assert res == "aggiornato_contatto_esistente"
        assert calls[1][1] == "/v3/contacts/new%40x.it" and "EMAIL" not in calls[1][2]["attributes"]

    def test_exception_errore(self, srv, monkeypatch):
        async def boom(*a, **k):
            raise RuntimeError("x")
        monkeypatch.setattr(srv.brevo_funnel, "is_configured", lambda: True)
        monkeypatch.setattr(srv.brevo_funnel, "_request", boom)
        assert asyncio.run(srv._brevo_profile_sync("a@x.it", "b@x.it", "A", "B", None)) == "errore"
