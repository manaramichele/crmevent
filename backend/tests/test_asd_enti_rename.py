# Gestione Società: rename (marketplace) + Enti e Federazioni (/api/asd/enti) + tesseramenti ente_id, isolation, super admin
import os
import uuid

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
SUPER = ("manara.michele.pro@gmail.com", "CrmEvent2026!")
PWD = "TestAsd2026!"


def _env(key):
    for line in open("/app/backend/.env"):
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"')


MDB = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]
ORGS = []


def register(tag, active=True):
    s = requests.Session()
    email = f"test_enti_{tag.lower()}_{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{BASE_URL}/api/auth/register-organization", json={
        "nome": "TEST", "cognome": tag, "email": email, "password": PWD, "org_name": f"TEST_ENTI_{tag}_{uuid.uuid4().hex[:4]}",
        "telefono": "+393331234567", "accept_terms": True})
    assert r.status_code == 200, r.text
    org = MDB.users.find_one({"email": email})["org_id"]
    ORGS.append((org, email))
    if active:
        MDB.org_services.insert_one({"org_id": org, "service": "gestione-societa", "active": True})
    s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": PWD})
    return {"s": s, "org": org, "email": email}


@pytest.fixture(scope="module")
def A():
    return register("A")


@pytest.fixture(scope="module")
def B():
    return register("B")


@pytest.fixture(scope="module")
def C():
    return register("C", active=False)


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    for org, email in ORGS:
        for c in ("persons", "asd_soci", "asd_tesseramenti", "asd_quote", "asd_certificati", "asd_adempimenti",
                  "org_services", "memberships", "subscriptions", "audit_logs"):
            MDB[c].delete_many({"org_id": org})
        MDB.settings.delete_one({"id": org})
        MDB.organizations.delete_one({"id": org})
        MDB.users.delete_many({"email": email})


def socio(s, h=None):
    r = s.post(f"{BASE_URL}/api/asd/soci", json={"nome": "TEST_Ente", "cognome": "TEST_Socio" + uuid.uuid4().hex[:5]}, headers=h or {})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def enti(s, h=None):
    r = s.get(f"{BASE_URL}/api/asd/enti", headers=h or {})
    assert r.status_code == 200, r.text
    return r.json()


class TestRename:
    def test_marketplace_service(self, A):
        r = A["s"].get(f"{BASE_URL}/api/marketplace/services")
        assert r.status_code == 200, r.text
        d = r.json()
        svcs = d if isinstance(d, list) else d.get("services") or d.get("items") or []
        svc = next(x for x in svcs if x.get("key") == "gestione-societa")
        assert svc["name"] == "Gestione Società"
        assert float(svc["price"]) == 99.0 and svc.get("price_type") == "yearly"
        db_svc = MDB.marketplace_services.find_one({"key": "gestione-societa"})
        assert db_svc["name"] == "Gestione Società"
        meta = MDB.schema_meta.find_one({"id": "rename_gestione_societa_v1"})
        assert meta and "backup" in meta
        assert "Associazione Sportiva" not in r.text


class TestEnti:
    def test_defaults(self, A):
        d = enti(A["s"])
        items = d["items"]
        assert len(items) == 26 and d["can_manage"] is True
        assert sum(e["tipo"] == "eps" for e in items) == 13 and sum(e["tipo"] == "federazione" for e in items) == 13
        csi = next(e for e in items if e["id"] == "csi")
        assert csi["label"] == "CSI – Centro Sportivo Italiano" and csi["active"] is True and csi["usage"] == 0
        assert set(d["tipi"]) >= {"federazione", "eps", "altro"}

    def test_add_duplicate_edit(self, A):
        s = A["s"]
        r = s.post(f"{BASE_URL}/api/asd/enti", json={"sigla": "TEST_FX", "nome": "TEST Federazione X", "tipo": "federazione"})
        assert r.status_code == 200, r.text
        e = r.json()
        assert e["label"] == "TEST_FX – TEST Federazione X" and e["active"] is True
        assert any(x["id"] == e["id"] for x in enti(s)["items"])
        for body, field in (({"sigla": "test_fx", "tipo": "altro"}, "sigla"), ({"sigla": "csi"}, "sigla"),
                            ({"sigla": "TEST_NEW", "nome": "centro sportivo italiano"}, "nome"), ({"sigla": "  "}, "sigla")):
            r = s.post(f"{BASE_URL}/api/asd/enti", json=body)
            assert r.status_code == 400, (body, r.text)
            assert r.json()["detail"]["field"] == field
        r = s.put(f"{BASE_URL}/api/asd/enti/{e['id']}", json={"sigla": "TEST_FY", "nome": "TEST Federazione Y", "tipo": "eps"})
        assert r.status_code == 200 and r.json()["label"] == "TEST_FY – TEST Federazione Y"
        r = s.put(f"{BASE_URL}/api/asd/enti/{e['id']}", json={"sigla": "FIDAL"})
        assert r.status_code == 400 and r.json()["detail"]["field"] == "sigla"
        assert s.put(f"{BASE_URL}/api/asd/enti/nonexistent", json={"sigla": "ZZZ"}).status_code == 404
        r = s.delete(f"{BASE_URL}/api/asd/enti/{e['id']}")
        assert r.status_code == 200
        assert not any(x["id"] == e["id"] for x in enti(s)["items"])

    def test_order(self, A):
        s = A["s"]
        ids = [e["id"] for e in enti(s)["items"]]
        new = [ids[-1]] + ids[:-1]
        assert s.put(f"{BASE_URL}/api/asd/enti/order", json={"ids": new}).status_code == 200
        assert [e["id"] for e in enti(s)["items"]] == new
        assert s.put(f"{BASE_URL}/api/asd/enti/order", json={"ids": ids}).status_code == 200

    def test_tesseramenti_flow(self, A):
        s = A["s"]
        sid = socio(s)
        base = {"socio_id": sid, "stagione": "2025/2026"}
        r = s.post(f"{BASE_URL}/api/asd/tesseramenti", json=base)
        assert r.status_code == 400 and r.json()["detail"]["field"] == "ente_id"
        r = s.post(f"{BASE_URL}/api/asd/tesseramenti", json={**base, "ente_id": "nope"})
        assert r.status_code == 400 and r.json()["detail"]["field"] == "ente_id"
        e = s.post(f"{BASE_URL}/api/asd/enti", json={"sigla": "TEST_EU", "nome": "TEST Ente Uso", "tipo": "altro"}).json()
        r = s.post(f"{BASE_URL}/api/asd/tesseramenti", json={**base, "ente_id": e["id"], "numero_tessera": "T1"})
        assert r.status_code == 200, r.text
        t = r.json()
        assert t["ente_id"] == e["id"] and t["ente"] == "TEST_EU – TEST Ente Uso"
        assert next(x for x in enti(s)["items"] if x["id"] == e["id"])["usage"] == 1
        # used -> cannot delete
        r = s.delete(f"{BASE_URL}/api/asd/enti/{e['id']}")
        assert r.status_code == 409
        # disable
        assert s.post(f"{BASE_URL}/api/asd/enti/{e['id']}/stato", json={"active": False}).status_code == 200
        assert next(x for x in enti(s)["items"] if x["id"] == e["id"])["active"] is False
        r = s.post(f"{BASE_URL}/api/asd/tesseramenti", json={**base, "ente_id": e["id"]})
        assert r.status_code == 400 and r.json()["detail"]["field"] == "ente_id"
        # edit tesseramento keeping disabled ente
        r = s.put(f"{BASE_URL}/api/asd/tesseramenti/{t['id']}", json={**base, "ente_id": e["id"], "numero_tessera": "T2"})
        assert r.status_code == 200, r.text
        assert r.json()["numero_tessera"] == "T2" and r.json()["ente_id"] == e["id"]
        row = next(x for x in s.get(f"{BASE_URL}/api/asd/tesseramenti", params={"socio_id": sid}).json() if x["id"] == t["id"])
        assert row["ente_attivo"] is False and row["ente_nome"] == "TEST_EU – TEST Ente Uso"
        # switching edit to another active ente works; switching back to disabled rejected
        r = s.put(f"{BASE_URL}/api/asd/tesseramenti/{t['id']}", json={**base, "ente_id": "csi"})
        assert r.status_code == 200 and r.json()["ente"] == "CSI – Centro Sportivo Italiano"
        r = s.put(f"{BASE_URL}/api/asd/tesseramenti/{t['id']}", json={**base, "ente_id": e["id"]})
        assert r.status_code == 400
        assert s.put(f"{BASE_URL}/api/asd/tesseramenti/{t['id']}", json={**base, "ente_id": e["id"]}).status_code == 400
        # re-enable, back to custom, rename -> ente_nome updates
        assert s.post(f"{BASE_URL}/api/asd/enti/{e['id']}/stato", json={"active": True}).status_code == 200
        assert s.put(f"{BASE_URL}/api/asd/tesseramenti/{t['id']}", json={**base, "ente_id": e["id"]}).status_code == 200
        assert s.put(f"{BASE_URL}/api/asd/enti/{e['id']}", json={"sigla": "TEST_EU2", "nome": "TEST Ente Rinominato", "tipo": "altro"}).status_code == 200
        row = next(x for x in s.get(f"{BASE_URL}/api/asd/tesseramenti", params={"socio_id": sid}).json() if x["id"] == t["id"])
        assert row["ente_nome"] == "TEST_EU2 – TEST Ente Rinominato" and row["ente_attivo"] is True
        # delete tesseramento -> ente deletable
        assert s.delete(f"{BASE_URL}/api/asd/tesseramenti/{t['id']}").status_code == 200
        assert s.delete(f"{BASE_URL}/api/asd/enti/{e['id']}").status_code == 200

    def test_edit_without_ente_id_rejected(self, A):
        s = A["s"]
        sid = socio(s)
        t = s.post(f"{BASE_URL}/api/asd/tesseramenti", json={"socio_id": sid, "stagione": "2025/2026", "ente_id": "fidal"}).json()
        r = s.put(f"{BASE_URL}/api/asd/tesseramenti/{t['id']}", json={"socio_id": sid, "stagione": "2025/2026"})
        assert r.status_code == 400


class TestIsolation:
    def test_org_b_separate(self, A, B):
        a = A["s"].post(f"{BASE_URL}/api/asd/enti", json={"sigla": "TEST_ONLYA", "tipo": "altro"}).json()
        bi = enti(B["s"])["items"]
        assert len(bi) == 26 and not any(x["id"] == a["id"] for x in bi)
        assert B["s"].put(f"{BASE_URL}/api/asd/enti/{a['id']}", json={"sigla": "HACK"}).status_code == 404
        assert B["s"].delete(f"{BASE_URL}/api/asd/enti/{a['id']}").status_code == 404
        # same sigla allowed in B
        assert B["s"].post(f"{BASE_URL}/api/asd/enti", json={"sigla": "TEST_ONLYA", "tipo": "altro"}).status_code == 200
        # B cannot use A's ente in tesseramento
        r = B["s"].post(f"{BASE_URL}/api/asd/tesseramenti", json={"socio_id": socio(B["s"]), "stagione": "2025/2026", "ente_id": a["id"]})
        assert r.status_code == 400

    def test_inactive_module(self, C):
        s = C["s"]
        assert s.get(f"{BASE_URL}/api/asd/enti").status_code == 403
        assert s.post(f"{BASE_URL}/api/asd/enti", json={"sigla": "TEST_X"}).status_code == 403
        assert s.get(f"{BASE_URL}/api/asd/status").json()["active"] is False

    def test_unauth(self):
        assert requests.get(f"{BASE_URL}/api/asd/enti").status_code == 401


class TestSuperAdmin:
    def test_superadmin_x_org(self, A):
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/auth/login", json={"email": SUPER[0], "password": SUPER[1]})
        if r.status_code != 200:
            pytest.skip("superadmin login failed")
        h = {"X-Org-Id": A["org"]}
        d = enti(s, h)
        assert d["can_manage"] is True
        e = s.post(f"{BASE_URL}/api/asd/enti", json={"sigla": "TEST_SA", "nome": "TEST Super", "tipo": "eps"}, headers=h)
        assert e.status_code == 200, e.text
        eid = e.json()["id"]
        assert s.put(f"{BASE_URL}/api/asd/enti/{eid}", json={"sigla": "TEST_SA2", "tipo": "eps"}, headers=h).status_code == 200
        assert s.post(f"{BASE_URL}/api/asd/enti/{eid}/stato", json={"active": False}, headers=h).status_code == 200
        assert any(x["id"] == eid and not x["active"] for x in enti(A["s"])["items"])
        assert s.delete(f"{BASE_URL}/api/asd/enti/{eid}", headers=h).status_code == 200
        assert s.get(f"{BASE_URL}/api/asd/enti").status_code in (400, 403, 428)
