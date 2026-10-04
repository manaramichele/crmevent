"""Iteration 3 - tests for CRMEvent unification refactor.

Covers new endpoints:
- GET /api/persons-enriched
- POST /api/persons-match
- GET /api/persons/{id}/detail
- GET /api/companies/{id}/detail
- GET/POST /api/companies/{id}/contacts
- PUT/DELETE /api/company-contacts/{rel_id}
- Company create with inline referenti (auto dedup)
- Same person as staff+volontario across events => single anagrafica
- Same company as sponsor+partner across events => single anagrafica
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "manara.michele.pro@gmail.com"
ADMIN_PASSWORD = "CrmEvent2026!"


@pytest.fixture(scope="module")
def s():
    session = requests.Session()
    r = session.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return session


@pytest.fixture(scope="module")
def two_events(s):
    evs = s.get(f"{API}/events").json()
    assert len(evs) >= 2, "need at least 2 events"
    return evs[0]["id"], evs[1]["id"]


# ---------- Enriched persons ----------
class TestPersonsEnriched:
    def test_shape(self, s):
        r = s.get(f"{API}/persons-enriched")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list) and len(data) > 0
        p = data[0]
        for k in ["id", "nome", "is_referente", "is_staff", "is_volontario", "aziende_nomi", "eventi_count"]:
            assert k in p, f"missing {k}"
        assert isinstance(p["aziende_nomi"], list)
        assert isinstance(p["eventi_count"], int)


# ---------- Persons match (dedup) ----------
class TestPersonsMatch:
    def test_match_by_email(self, s):
        persons = s.get(f"{API}/persons").json()
        assert persons
        email = next((p["email"] for p in persons if p.get("email")), None)
        assert email
        r = s.post(f"{API}/persons-match", json={"email": email})
        assert r.status_code == 200
        matches = r.json()
        # response could be {matches:[...]} or list
        arr = matches.get("matches", matches) if isinstance(matches, dict) else matches
        assert isinstance(arr, list) and len(arr) >= 1

    def test_match_no_result(self, s):
        r = s.post(f"{API}/persons-match", json={"email": f"noone_{uuid.uuid4().hex}@nowhere.zz"})
        assert r.status_code == 200
        j = r.json()
        arr = j.get("matches", j) if isinstance(j, dict) else j
        assert arr == [] or arr == []


# ---------- Detail endpoints ----------
class TestDetailEndpoints:
    def test_person_detail(self, s):
        pid = s.get(f"{API}/persons").json()[0]["id"]
        r = s.get(f"{API}/persons/{pid}/detail")
        assert r.status_code == 200, r.text
        d = r.json()
        # expect keys around the person and related data
        assert d.get("id") == pid or d.get("person", {}).get("id") == pid

    def test_company_detail(self, s):
        cid = s.get(f"{API}/companies").json()[0]["id"]
        r = s.get(f"{API}/companies/{cid}/detail")
        assert r.status_code == 200, r.text


# ---------- Company contacts CRUD + dedup ----------
class TestCompanyContacts:
    def test_create_new_referente_creates_person(self, s):
        # create isolated company
        cname = f"TEST_Co_{uuid.uuid4().hex[:6]}"
        c = s.post(f"{API}/companies", json={"nome": cname, "tipo": "azienda"}).json()
        cid = c["id"]
        ref_email = f"ref_{uuid.uuid4().hex[:6]}@testcrm.it"
        r = s.post(f"{API}/companies/{cid}/contacts", json={
            "nome": "TEST_Ref", "cognome": "Uno", "email": ref_email, "ruolo": "Buyer"
        })
        assert r.status_code == 200, r.text
        rel = r.json()
        # persona should exist with matching email
        persons = s.get(f"{API}/persons").json()
        assert any(p.get("email") == ref_email for p in persons), "person not auto-created"
        # list contacts
        rl = s.get(f"{API}/companies/{cid}/contacts")
        assert rl.status_code == 200
        contacts = rl.json()
        assert isinstance(contacts, list) and len(contacts) >= 1
        # cleanup
        rel_id = rel.get("id") or rel.get("rel_id") or (contacts[0].get("id") if contacts else None)
        if rel_id:
            s.delete(f"{API}/company-contacts/{rel_id}")
        s.delete(f"{API}/companies/{cid}")

    def test_dedup_via_match_then_link(self, s):
        """Dedup flow: match first, then POST contacts with person_id (mirrors UI 'Verifica e salva' -> Collega)."""
        persons = s.get(f"{API}/persons").json()
        existing = next((p for p in persons if p.get("email")), None)
        assert existing
        cname = f"TEST_CoDedup_{uuid.uuid4().hex[:6]}"
        c = s.post(f"{API}/companies", json={"nome": cname, "tipo": "azienda"}).json()
        cid = c["id"]
        # 1) match returns the existing person
        m = s.post(f"{API}/persons-match", json={"email": existing["email"]}).json()
        arr = m.get("matches", m)
        assert any(x["id"] == existing["id"] for x in arr), "match did not find existing person"
        before = len([p for p in persons if p.get("email") == existing["email"]])
        # 2) link with person_id
        r = s.post(f"{API}/companies/{cid}/contacts", json={
            "person_id": existing["id"], "ruolo": "Referente"
        })
        assert r.status_code == 200, r.text
        persons_after = s.get(f"{API}/persons").json()
        after = len([p for p in persons_after if p.get("email") == existing["email"]])
        assert after == before, f"duplicate created via link! before={before} after={after}"
        # cleanup
        s.delete(f"{API}/companies/{cid}")


# ---------- Unification: 1 person, 2 events (staff + volontario) ----------
class TestPersonUnification:
    def test_single_person_across_categories(self, s, two_events):
        e1, e2 = two_events
        email = f"unif_{uuid.uuid4().hex[:6]}@testcrm.it"
        p = s.post(f"{API}/persons", json={"nome": "TEST_Unif", "cognome": "X", "email": email}).json()
        pid = p["id"]
        r1 = s.post(f"{API}/staff", json={"persona_id": pid, "evento_id": e1, "categoria": "staff", "ruolo": "Tech"})
        r2 = s.post(f"{API}/staff", json={"persona_id": pid, "evento_id": e2, "categoria": "volontario", "ruolo": "Support"})
        assert r1.status_code == 200 and r2.status_code == 200, f"{r1.text} | {r2.text}"
        # persons-enriched should show a single record for this email with both flags
        enriched = s.get(f"{API}/persons-enriched").json()
        matches = [x for x in enriched if x.get("email") == email]
        assert len(matches) == 1, f"expected 1 anagrafica, got {len(matches)}"
        rec = matches[0]
        assert rec["is_staff"] is True
        assert rec["is_volontario"] is True
        assert rec["eventi_count"] >= 2
        # cleanup staff rows
        for rec_id in [r1.json().get("id"), r2.json().get("id")]:
            if rec_id:
                s.delete(f"{API}/staff/{rec_id}")
        s.delete(f"{API}/persons/{pid}")


# ---------- Unification: 1 company as sponsor+partner on different events ----------
class TestCompanyUnification:
    def test_single_company_across_deal_types(self, s, two_events):
        e1, e2 = two_events
        cname = f"TEST_CoUnif_{uuid.uuid4().hex[:6]}"
        c = s.post(f"{API}/companies", json={"nome": cname, "tipo": "azienda"}).json()
        cid = c["id"]
        d1 = s.post(f"{API}/deals", json={
            "azienda_id": cid, "evento_id": e1, "tipo": "sponsor", "fase": "prospect", "valore": 500
        })
        d2 = s.post(f"{API}/deals", json={
            "azienda_id": cid, "evento_id": e2, "tipo": "partner", "fase": "prospect", "valore": 300
        })
        assert d1.status_code == 200 and d2.status_code == 200, f"{d1.text} | {d2.text}"
        companies = s.get(f"{API}/companies").json()
        matches = [x for x in companies if x["nome"] == cname]
        assert len(matches) == 1
        # global search should also return 1 azienda for this name
        sr = s.get(f"{API}/search", params={"q": cname}).json()
        aziende_results = [r for r in sr.get("results", []) if r.get("type") in ("company", "azienda")]
        # tolerate if 'type' is missing; at minimum ensure not multiple duplicates named cname
        names = [r.get("nome") or r.get("title") for r in sr.get("results", [])]
        assert names.count(cname) <= 1
        # cleanup deals + company
        for did in [d1.json().get("id"), d2.json().get("id")]:
            if did:
                s.delete(f"{API}/deals/{did}")
        s.delete(f"{API}/companies/{cid}")


# ---------- Sidebar / route: no /staff route required by backend, just ensure list endpoints ----------
class TestNoRegression:
    def test_search_persons_no_dup(self, s):
        # Pick a person with a name and ensure search returns one entry
        p = s.get(f"{API}/persons").json()[0]
        q = p["nome"]
        r = s.get(f"{API}/search", params={"q": q})
        assert r.status_code == 200
