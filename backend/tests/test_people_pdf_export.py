# People PDF export (Staff / Volontari / Team) - POST /api/staff/export-pdf
import os
import io
import re
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
EMAIL = "test_pdf_1794985461@example.com"
PWD = "TestPass123!"
EV = "c19d9ac404f84f41b5021b191eeb17c0"
URL = f"{BASE_URL}/api/staff/export-pdf"


def pdf_text(content):
    import fitz
    d = fitz.open(stream=content, filetype="pdf")
    return "\n".join(p.get_text() for p in d), d.page_count


@pytest.fixture(scope="module")
def s():
    ss = requests.Session()
    r = ss.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PWD})
    if r.status_code != 200:
        pytest.skip(f"login failed {r.status_code} {r.text}")
    tok = r.json().get("token") or r.json().get("access_token")
    if tok:
        ss.headers["Authorization"] = f"Bearer {tok}"
    return ss


@pytest.fixture(scope="module")
def staff_rows(s):
    r = s.get(f"{BASE_URL}/api/staff", params={"evento_id": EV})
    assert r.status_code == 200
    return r.json()


def test_staff_export_basic(s):
    r = s.post(URL, json={"section": "staff", "evento_id": EV, "columns": ["telefono", "team"]})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content[:4] == b"%PDF"
    assert r.headers["X-Export-Count"] == "2"
    cd = r.headers["content-disposition"]
    assert re.search(r'CRMEvent_Staff_MezzaMaratonaDiProva_\d{4}-\d{2}-\d{2}\.pdf', cd), cd
    txt, _ = pdf_text(r.content)
    assert "Rossi" in txt and "Verdi" in txt
    assert "Bianchi" not in txt and "Zeta1" not in txt
    assert "Elenco Staff" in txt and "Telefono" in txt


def test_volontari_export_only_volunteers(s):
    r = s.post(URL, json={"section": "volontari", "evento_id": EV, "columns": []})
    assert r.status_code == 200
    assert r.headers["X-Export-Count"] == "48"
    assert "CRMEvent_Volontari_" in r.headers["content-disposition"]
    txt, pages = pdf_text(r.content)
    assert "Rossi" not in txt and "Verdi" not in txt
    assert "Bianchi" in txt and "Neri" in txt
    assert pages >= 2
    assert "Telefono" not in txt


def test_volontari_with_staff_person_ids_filtered_by_categoria(s, staff_rows):
    # pass all person ids -> backend must still return only volunteers
    ids = list({x["persona_id"] for x in staff_rows}) if isinstance(staff_rows, list) else []
    r = s.post(URL, json={"section": "volontari", "evento_id": EV, "person_ids": ids, "columns": []})
    assert r.status_code == 200
    assert r.headers["X-Export-Count"] == "48"
    r2 = s.post(URL, json={"section": "staff", "evento_id": EV, "person_ids": ids, "columns": []})
    assert r2.headers["X-Export-Count"] == "2"


def test_person_ids_subset(s, staff_rows):
    persons = s.get(f"{BASE_URL}/api/persons").json()
    persons = persons if isinstance(persons, list) else persons.get("items", [])
    rossi = [p["id"] for p in persons if p.get("cognome") == "Rossi"]
    assert rossi
    r = s.post(URL, json={"section": "staff", "evento_id": EV, "person_ids": rossi, "columns": []})
    assert r.headers["X-Export-Count"] == str(len(rossi))
    txt, _ = pdf_text(r.content)
    assert "Rossi" in txt and "Verdi" not in txt


def test_empty_person_ids(s):
    r = s.post(URL, json={"section": "staff", "evento_id": EV, "person_ids": [], "columns": []})
    assert r.status_code == 200
    assert r.headers["X-Export-Count"] == "0"
    txt, _ = pdf_text(r.content)
    assert "Nessuna persona" in txt


def test_team_export_grouped(s):
    teams = s.get(f"{BASE_URL}/api/teams", params={"evento_id": EV}).json()
    teams = teams if isinstance(teams, list) else teams.get("items", [])
    names = sorted(t["nome"] for t in teams if t.get("evento_id") == EV)
    assert "Accoglienza" in names and "Ristoro" in names
    r = s.post(URL, json={"section": "team", "evento_id": EV, "columns": ["team"]})
    assert r.status_code == 200
    assert "CRMEvent_Team_" in r.headers["content-disposition"]
    txt, _ = pdf_text(r.content)
    assert txt.index("Accoglienza") < txt.index("Ristoro")
    # single team
    rist = [t["id"] for t in teams if t["nome"] == "Ristoro"]
    r2 = s.post(URL, json={"section": "team", "evento_id": EV, "team_ids": rist, "columns": []})
    txt2, _ = pdf_text(r2.content)
    assert "Ristoro" in txt2 and "Accoglienza" not in txt2
    assert int(r2.headers["X-Export-Count"]) <= int(r.headers["X-Export-Count"])


def test_landscape_when_many_columns(s):
    import fitz
    r = s.post(URL, json={"section": "staff", "evento_id": EV, "columns": ["telefono", "team", "taglia"]})
    p = fitz.open(stream=r.content, filetype="pdf")[0].rect
    assert p.width > p.height
    r = s.post(URL, json={"section": "staff", "evento_id": EV, "columns": ["telefono"]})
    p = fitz.open(stream=r.content, filetype="pdf")[0].rect
    assert p.width < p.height


def test_invalid_section(s):
    r = s.post(URL, json={"section": "foo", "evento_id": EV, "columns": []})
    assert r.status_code == 400


def test_unknown_event_404(s):
    r = s.post(URL, json={"section": "staff", "evento_id": "nonexistent", "columns": []})
    assert r.status_code == 404


def test_unauthenticated():
    r = requests.post(URL, json={"section": "staff", "evento_id": EV, "columns": []})
    assert r.status_code in (401, 403)


def test_no_data_modification(s, staff_rows):
    before = s.get(f"{BASE_URL}/api/staff", params={"evento_id": EV}).json()
    s.post(URL, json={"section": "staff", "evento_id": EV, "columns": ["telefono"]})
    after = s.get(f"{BASE_URL}/api/staff", params={"evento_id": EV}).json()
    assert before == after


class TestCrossOrg:
    org_ids = []

    def test_other_org_cannot_export(self, s):
        ts = int(time.time())
        o = requests.Session()
        r = o.post(f"{BASE_URL}/api/auth/register-organization", json={
            "nome": "T", "cognome": "X", "email": f"test_pdfx_{ts}@example.com", "password": "TestPass123!",
            "org_name": f"TEST_PdfX {ts}", "telefono": "+39 333 123 4567", "accept_terms": True})
        assert r.status_code in (200, 201), r.text
        d = r.json()
        tok = d.get("token") or d.get("access_token")
        if tok:
            o.headers["Authorization"] = f"Bearer {tok}"
        print("NEW ORG RESP KEYS", list(d.keys()), d.get("user", {}).get("org_id"))
        r = o.post(URL, json={"section": "staff", "evento_id": EV, "columns": []})
        assert r.status_code == 404, r.status_code
