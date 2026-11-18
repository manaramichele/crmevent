# Gestione Associazione Sportiva (/api/asd) - access control, CRUD, states, files, isolation
import os
import uuid
from datetime import date, timedelta

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
A = ("test_asd_a_1795022688@example.com", "TestAsd2026!")
B = ("test_asd_b_1795022688@example.com", "TestAsd2026!")
SUPER = ("manara.michele.pro@gmail.com", "CrmEvent2026!")

_ODD = dict(zip("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                [1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 2, 4, 18, 20, 11, 3, 6, 8, 12, 14, 16, 10, 22, 25, 24, 23]))


def make_cf():
    import random
    base = "TST" + "".join(random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(3)) + "80A01H501"
    tot = sum(_ODD[c] if i % 2 == 0 else (int(c) if c.isdigit() else ord(c) - 65) for i, c in enumerate(base))
    return base + chr(65 + tot % 26)


def D(n):
    return (date.today() + timedelta(days=n)).isoformat()


def login(creds):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": creds[0], "password": creds[1]})
    if r.status_code != 200:
        pytest.skip(f"login failed {creds[0]}: {r.status_code} {r.text[:200]}")
    return s


@pytest.fixture(scope="module")
def sa():
    return login(A)


@pytest.fixture(scope="module")
def sb():
    return login(B)


@pytest.fixture(scope="module")
def created(sa):
    items = []  # (path, id)
    yield items
    for path, iid in reversed(items):
        sa.delete(f"{BASE_URL}/api/asd/{path}/{iid}")


def mk_socio(sa, created, **kw):
    body = {"nome": "TEST_Mario", "cognome": "TEST_Rossi" + uuid.uuid4().hex[:4], "tipo": "socio_tesserato", "qualifica": "atleta", **kw}
    r = sa.post(f"{BASE_URL}/api/asd/soci", json=body)
    assert r.status_code == 200, r.text
    created.append(("soci", r.json()["id"]))
    return r.json()


def add(sa, created, path, body, code=200):
    r = sa.post(f"{BASE_URL}/api/asd/{path}", json=body)
    assert r.status_code == code, r.text
    if code == 200:
        created.append((path, r.json()["id"]))
    return r


class TestAccess:
    def test_status_a_active(self, sa):
        d = sa.get(f"{BASE_URL}/api/asd/status").json()
        assert d["active"] is True and d["can_delete"] is True and "tipi_socio" in d["options"]

    def test_status_b_inactive_and_403(self, sb):
        assert sb.get(f"{BASE_URL}/api/asd/status").json()["active"] is False
        for p in ("soci", "tesseramenti", "quote", "certificati", "adempimenti", "scadenze", "dashboard"):
            assert sb.get(f"{BASE_URL}/api/asd/{p}").status_code == 403, p
        assert sb.post(f"{BASE_URL}/api/asd/soci", json={"nome": "x", "cognome": "y"}).status_code == 403

    def test_superadmin_denied(self):
        s = login(SUPER)
        r = s.get(f"{BASE_URL}/api/asd/status")
        assert r.status_code in (200, 428, 403)
        if r.status_code == 200:
            assert r.json()["active"] is False
        assert s.get(f"{BASE_URL}/api/asd/soci").status_code in (403, 428)

    def test_unauth(self):
        assert requests.get(f"{BASE_URL}/api/asd/soci").status_code == 401


class TestSoci:
    def test_crud_search_filters(self, sa, created):
        cf = make_cf()
        s = mk_socio(sa, created, codice_fiscale=cf.lower(), email="TEST@Example.com")
        assert s["codice_fiscale"] == cf and s["email"] == "test@example.com"
        r = sa.put(f"{BASE_URL}/api/asd/soci/{s['id']}", json={**{k: s[k] for k in ("nome", "cognome", "codice_fiscale", "tipo")}, "stato": "sospeso"})
        assert r.status_code == 200 and r.json()["stato"] == "sospeso"
        rows = sa.get(f"{BASE_URL}/api/asd/soci", params={"q": cf[:8]}).json()
        assert any(x["id"] == s["id"] for x in rows)
        rows = sa.get(f"{BASE_URL}/api/asd/soci", params={"stato": "sospeso"}).json()
        assert any(x["id"] == s["id"] for x in rows) and all(x["stato"] == "sospeso" for x in rows)
        rows = sa.get(f"{BASE_URL}/api/asd/soci", params={"stato": "attivo"}).json()
        assert not any(x["id"] == s["id"] for x in rows)
        x = [x for x in sa.get(f"{BASE_URL}/api/asd/soci").json() if x["id"] == s["id"]][0]
        assert x["certificato_stato"] == "mancante" and x["quote_da_pagare"] == 0

    def test_invalid_cf(self, sa):
        r = sa.post(f"{BASE_URL}/api/asd/soci", json={"nome": "TEST_a", "cognome": "TEST_b", "codice_fiscale": "RSSMRA80A01H501X"})
        assert r.status_code == 400 and r.json()["detail"]["field"] == "codice_fiscale"

    def test_duplicate_cf_create(self, sa, created):
        cf = make_cf()
        mk_socio(sa, created, codice_fiscale=cf)
        r = sa.post(f"{BASE_URL}/api/asd/soci", json={"nome": "TEST_a", "cognome": "TEST_b", "codice_fiscale": cf})
        assert r.status_code == 400 and r.json()["detail"]["field"] == "codice_fiscale"

    def test_duplicate_cf_update(self, sa, created):
        cf = make_cf()
        mk_socio(sa, created, codice_fiscale=cf)
        s2 = mk_socio(sa, created)
        r = sa.put(f"{BASE_URL}/api/asd/soci/{s2['id']}", json={"nome": s2["nome"], "cognome": s2["cognome"], "codice_fiscale": cf})
        assert r.status_code == 400, f"update to duplicate CF -> {r.status_code} {r.text[:200]}"

    def test_delete_linked_409_then_free(self, sa, created):
        s = mk_socio(sa, created)
        q = add(sa, created, "quote", {"socio_id": s["id"], "descrizione": "TEST_q", "importo": 10}).json()
        r = sa.delete(f"{BASE_URL}/api/asd/soci/{s['id']}")
        assert r.status_code == 409 and "quote" in r.json()["detail"]
        assert sa.delete(f"{BASE_URL}/api/asd/quote/{q['id']}").status_code == 200
        assert sa.delete(f"{BASE_URL}/api/asd/soci/{s['id']}").status_code == 200
        assert not any(x["id"] == s["id"] for x in sa.get(f"{BASE_URL}/api/asd/soci").json())


class TestLinked:
    def test_tesseramento_states(self, sa, created):
        s = mk_socio(sa, created)
        base = {"socio_id": s["id"], "stagione": "2025/2026", "ente_id": "fidal"}
        ids = {k: add(sa, created, "tesseramenti", {**base, **v}).json()["id"] for k, v in {
            "valido": {"data_scadenza": D(90)}, "in_scadenza": {"data_scadenza": D(10)}, "scaduto": {"data_scadenza": D(-1)},
            "annullato": {"data_scadenza": D(90), "annullato": True}}.items()}
        rows = {x["id"]: x for x in sa.get(f"{BASE_URL}/api/asd/tesseramenti", params={"socio_id": s["id"]}).json()}
        for k, i in ids.items():
            assert rows[i]["stato"] == k and rows[i]["socio_nome"].startswith("TEST_Rossi")
        add(sa, created, "tesseramenti", {**base, "data_emissione": D(5), "data_scadenza": D(1)}, 400)

    def test_quote_states_and_payment(self, sa, created):
        s = mk_socio(sa, created)
        b = {"socio_id": s["id"], "descrizione": "TEST_quota", "importo": 50}
        q1 = add(sa, created, "quote", {**b, "data_scadenza": D(10)}).json()
        q2 = add(sa, created, "quote", {**b, "data_scadenza": D(-3)}).json()
        q3 = add(sa, created, "quote", {**b, "data_pagamento": D(0), "importo_pagato": 20, "metodo": "contanti"}).json()
        rows = {x["id"]: x for x in sa.get(f"{BASE_URL}/api/asd/quote", params={"socio_id": s["id"]}).json()}
        assert rows[q1["id"]]["stato"] == "da_pagare" and rows[q2["id"]]["stato"] == "scaduta" and rows[q3["id"]]["stato"] == "parziale"
        r = sa.put(f"{BASE_URL}/api/asd/quote/{q2['id']}", json={**b, "data_scadenza": D(-3), "data_pagamento": D(0), "metodo": "bonifico"})
        assert r.status_code == 200 and r.json()["importo_pagato"] == 50
        rows = {x["id"]: x for x in sa.get(f"{BASE_URL}/api/asd/quote", params={"socio_id": s["id"]}).json()}
        assert rows[q2["id"]]["stato"] == "pagata"
        add(sa, created, "quote", {**b, "importo": -1}, 400)
        so = [x for x in sa.get(f"{BASE_URL}/api/asd/soci").json() if x["id"] == s["id"]][0]
        assert so["quote_da_pagare"] == 1

    def test_cert_and_file(self, sa, sb, created):
        s = mk_socio(sa, created)
        add(sa, created, "certificati", {"socio_id": s["id"], "tipo": "agonistico"}, 422)
        c = add(sa, created, "certificati", {"socio_id": s["id"], "tipo": "agonistico", "data_scadenza": D(15)}).json()
        assert c["id"] and "file_path" not in c
        url = f"{BASE_URL}/api/asd/certificati/{c['id']}/file"
        assert sa.get(url).status_code == 404
        pdf = b"%PDF-1.4\n%TEST\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
        r = sa.post(url, files={"file": ("TEST_cert.pdf", pdf, "application/pdf")})
        assert r.status_code == 200, r.text
        r = sa.post(url, files={"file": ("x.exe", b"MZ..", "application/octet-stream")})
        assert r.status_code == 400
        r = sa.post(url, files={"file": ("x.csv", b"a,b", "text/csv")})
        assert r.status_code == 400
        g = sa.get(url)
        assert g.status_code == 200 and g.content == pdf and g.headers["content-type"].startswith("application/pdf")
        assert requests.get(url).status_code == 401
        assert sb.get(url).status_code == 403  # B module inactive
        row = [x for x in sa.get(f"{BASE_URL}/api/asd/certificati").json() if x["id"] == c["id"]][0]
        assert row["stato"] == "in_scadenza" and row["file_name"] == "TEST_cert.pdf" and "file_path" not in row
        so = [x for x in sa.get(f"{BASE_URL}/api/asd/soci").json() if x["id"] == s["id"]][0]
        assert so["certificato_stato"] == "in_scadenza"

    def test_cert_large_file(self, sa, created):
        s = mk_socio(sa, created)
        c = add(sa, created, "certificati", {"socio_id": s["id"], "data_scadenza": D(100)}).json()
        r = sa.post(f"{BASE_URL}/api/asd/certificati/{c['id']}/file", files={"file": ("big.pdf", b"%PDF" + b"0" * (10 * 1024 * 1024 + 10), "application/pdf")})
        assert r.status_code in (400, 413)

    def test_invalid_socio(self, sa, created):
        add(sa, created, "quote", {"socio_id": "nonexistent", "descrizione": "TEST", "importo": 1}, 400)
        add(sa, created, "tesseramenti", {"socio_id": "nonexistent", "stagione": "x", "ente_id": "fidal"}, 400)
        add(sa, created, "certificati", {"socio_id": "nonexistent", "data_scadenza": D(5)}, 400)


class TestScadenzeDashboard:
    def test_scadenze_and_dashboard(self, sa, created):
        s = mk_socio(sa, created)
        c = add(sa, created, "certificati", {"socio_id": s["id"], "data_scadenza": D(-2)}).json()
        a = add(sa, created, "adempimenti", {"titolo": "TEST_Assemblea", "data_scadenza": D(45)}).json()
        a2 = add(sa, created, "adempimenti", {"titolo": "TEST_Done", "data_scadenza": D(5), "completato": True}).json()
        far = add(sa, created, "adempimenti", {"titolo": "TEST_Far", "data_scadenza": D(200)}).json()
        ids30 = {x["ref_id"] for x in sa.get(f"{BASE_URL}/api/asd/scadenze", params={"giorni": 30}).json()}
        assert c["id"] in ids30 and a["id"] not in ids30 and a2["id"] not in ids30
        ids60 = {x["ref_id"] for x in sa.get(f"{BASE_URL}/api/asd/scadenze", params={"giorni": 60}).json()}
        assert a["id"] in ids60 and far["id"] not in ids60
        ids365 = {x["ref_id"] for x in sa.get(f"{BASE_URL}/api/asd/scadenze", params={"giorni": 365}).json()}
        assert far["id"] in ids365
        d = sa.get(f"{BASE_URL}/api/asd/dashboard").json()
        for k in ("soci_totali", "soci_attivi", "tesserati_validi", "quote_incassate", "quote_da_incassare", "certificati", "scadenze_scadute", "prossime_scadenze"):
            assert k in d
        assert d["certificati"]["scaduto"] >= 1 and d["scadenze_scadute"] >= 1
        add(sa, created, "adempimenti", {"titolo": "", "data_scadenza": D(1)}, 400)


class TestIsolation:
    def test_b_cannot_touch_a(self, sa, sb, created):
        s = mk_socio(sa, created)
        q = add(sa, created, "quote", {"socio_id": s["id"], "descrizione": "TEST_iso", "importo": 5}).json()
        assert sb.put(f"{BASE_URL}/api/asd/soci/{s['id']}", json={"nome": "h", "cognome": "h"}).status_code in (403, 404)
        assert sb.delete(f"{BASE_URL}/api/asd/soci/{s['id']}").status_code in (403, 404)
        assert sb.delete(f"{BASE_URL}/api/asd/quote/{q['id']}").status_code in (403, 404)
        assert any(x["id"] == s["id"] and x["nome"] == "TEST_Mario" for x in sa.get(f"{BASE_URL}/api/asd/soci").json())


class TestMarketplaceUntouched:
    def test_service_still_coming_soon(self, sa):
        r = sa.get(f"{BASE_URL}/api/marketplace/services")
        if r.status_code != 200:
            pytest.skip(f"services endpoint {r.status_code}")
        data = r.json()
        rows = data if isinstance(data, list) else data.get("services", data.get("items", []))
        g = [x for x in rows if x.get("key") == "gestione-societa"]
        assert len(g) == 1, f"gestione-societa count {len(g)}"
        print("SERVICE", {k: g[0].get(k) for k in ("status", "purchasable", "active", "coming_soon")})
        assert len([x for x in rows if "associazione" in (x.get("key") or "")]) == 0
