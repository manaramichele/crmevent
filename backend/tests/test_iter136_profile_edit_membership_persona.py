# Iteration 136: Super Admin profile edit also updates Persona linked via memberships.persona_id (org-scoped)
import os
import uuid
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
SA = ("manara.michele.pro@gmail.com", "CrmEvent2026!")
mdb = MongoClient(os.environ.get("MONGO_URL"))[os.environ.get("DB_NAME")]


def _xff():
    return {"X-Forwarded-For": f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"}


def _register(prefix):
    em = f"test_{prefix}_{uuid.uuid4().hex[:6]}@example.com"
    r = requests.post(f"{BASE_URL}/api/auth/register-organization", headers=_xff(), json={
        "nome": "Tizio", "cognome": "Prova", "email": em, "password": "TestPass123!",
        "org_name": f"TEST_Org136_{prefix}_{uuid.uuid4().hex[:4]}", "telefono": "+393401234567", "accept_terms": True})
    assert r.status_code == 200, r.text
    return mdb.users.find_one({"email": em}, {"_id": 0})


@pytest.fixture(scope="module")
def ctx():
    sa = requests.Session()
    r = sa.post(f"{BASE_URL}/api/auth/login", json={"email": SA[0], "password": SA[1]}, headers=_xff())
    assert r.status_code == 200, r.text
    u1 = _register("mp1")
    u2 = _register("mp2")
    org_a, org_b = u1["org_id"], u2["org_id"]
    pid = f"TEST_p136_{uuid.uuid4().hex[:6]}"
    # persona in org A linked through u1's membership
    mdb.persons.insert_one({"id": pid, "org_id": org_a, "nome": "Tizio", "cognome": "Prova",
                            "email": u1["email"], "cellulare": "+393401234567"})
    # same id persona in another org (must NOT be touched) + unrelated persona in org B
    mdb.persons.insert_one({"id": pid, "org_id": org_b, "nome": "Altro", "cognome": "Org",
                            "email": "other_org@example.com", "cellulare": "+393409999999"})
    mdb.memberships.update_one({"user_id": u1["user_id"], "org_id": org_a}, {"$set": {"persona_id": pid}})
    mdb.users.update_one({"user_id": u1["user_id"]}, {"$unset": {"person_id": ""}, "$set": {"google_sub": "TEST_gsub_136"}})
    mem_before = mdb.memberships.find_one({"user_id": u1["user_id"], "org_id": org_a}, {"_id": 0})
    yield {"sa": sa, "u1": u1, "u2": u2, "pid": pid, "org_a": org_a, "org_b": org_b, "mem_before": mem_before}
    uids = [u1["user_id"], u2["user_id"]]
    mdb.memberships.delete_many({"$or": [{"user_id": {"$in": uids}}, {"org_id": {"$in": [org_a, org_b]}}]})
    mdb.users.delete_many({"user_id": {"$in": uids}})
    mdb.persons.delete_many({"id": pid})
    for o in (org_a, org_b):
        mdb.organizations.delete_many({"id": o})
        mdb.settings.delete_many({"id": o})
        mdb.subscriptions.delete_many({"org_id": o})
        mdb.audit_logs.delete_many({"org_id": o})


class TestMembershipPersonaSync:
    def test_name_phone_updates_membership_persona(self, ctx):
        u1 = ctx["u1"]
        r = ctx["sa"].patch(f"{BASE_URL}/api/platform/users/{u1['user_id']}/profile",
                            json={"nome": "Gianni", "cognome": "Verdi", "email": u1["email"], "telefono": "+393471112233"})
        assert r.status_code == 200, r.text
        assert set(r.json()["changes"]) == {"nome", "cognome", "cellulare"}
        p = mdb.persons.find_one({"id": ctx["pid"], "org_id": ctx["org_a"]}, {"_id": 0})
        assert (p["nome"], p["cognome"], p["cellulare"]) == ("Gianni", "Verdi", "+393471112233")
        other = mdb.persons.find_one({"id": ctx["pid"], "org_id": ctx["org_b"]}, {"_id": 0})
        assert (other["nome"], other["cognome"], other["email"], other["cellulare"]) == ("Altro", "Org", "other_org@example.com", "+393409999999")

    def test_members_list_reflects(self, ctx):
        r = ctx["sa"].get(f"{BASE_URL}/api/platform/organizations/{ctx['org_a']}/members")
        assert r.status_code == 200
        m = next(x for x in r.json() if x["user_id"] == ctx["u1"]["user_id"])
        assert m["nome"] == "Gianni" and m["cognome"] == "Verdi" and m["telefono"] == "+393471112233"

    def test_email_clash(self, ctx):
        r = ctx["sa"].patch(f"{BASE_URL}/api/platform/users/{ctx['u1']['user_id']}/profile",
                            json={"nome": "Gianni", "cognome": "Verdi", "email": ctx["u2"]["email"].upper(),
                                  "telefono": "+393471112233", "confirm_email_change": True})
        assert r.status_code == 400 and "Esiste già" in r.json()["detail"]

    def test_email_requires_confirm(self, ctx):
        r = ctx["sa"].patch(f"{BASE_URL}/api/platform/users/{ctx['u1']['user_id']}/profile",
                            json={"nome": "Gianni", "cognome": "Verdi", "email": "test_new136@example.com", "telefono": "+393471112233"})
        assert r.status_code == 400

    def test_email_change_updates_persona_and_login(self, ctx):
        u1 = ctx["u1"]
        new_em = f"test_renamed136_{uuid.uuid4().hex[:6]}@example.com"
        r = ctx["sa"].patch(f"{BASE_URL}/api/platform/users/{u1['user_id']}/profile",
                            json={"nome": "Gianni", "cognome": "Verdi", "email": new_em, "telefono": "+393471112233", "confirm_email_change": True})
        assert r.status_code == 200, r.text
        assert r.json()["changes"] == ["email"]
        p = mdb.persons.find_one({"id": ctx["pid"], "org_id": ctx["org_a"]}, {"_id": 0})
        assert p["email"] == new_em
        other = mdb.persons.find_one({"id": ctx["pid"], "org_id": ctx["org_b"]}, {"_id": 0})
        assert other["email"] == "other_org@example.com"
        ok = requests.post(f"{BASE_URL}/api/auth/login", json={"email": new_em, "password": "TestPass123!"}, headers=_xff())
        assert ok.status_code == 200, ok.text
        bad = requests.post(f"{BASE_URL}/api/auth/login", json={"email": u1["email"], "password": "TestPass123!"}, headers=_xff())
        assert bad.status_code in (400, 401)

    def test_membership_and_identity_untouched(self, ctx):
        mem = mdb.memberships.find_one({"user_id": ctx["u1"]["user_id"], "org_id": ctx["org_a"]}, {"_id": 0})
        b = ctx["mem_before"]
        for k in ("role", "active", "persona_id", "org_id", "id"):
            assert mem.get(k) == b.get(k), k
        u = mdb.users.find_one({"user_id": ctx["u1"]["user_id"]}, {"_id": 0})
        assert u["google_sub"] == "TEST_gsub_136"
        assert u["role"] == ctx["u1"]["role"] and u["org_id"] == ctx["org_a"]
