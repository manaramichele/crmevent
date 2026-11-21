# Gruppi di appartenenza tab: POST /api/staff/groups-pdf (filters, org isolation, content)
import os
import re
import zlib

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
DEMO = "b7f40862230441b9a0bedabefe8dab49"
OTHER = "org_qa_eventi"
EMAIL = "manara.michele.pro@gmail.com"
PWD = "CrmEvent2026!"


def pdf_text(b: bytes) -> str:
    import base64
    out = []
    for obj in b.split(b"endobj"):
        if b"stream" not in obj or b"/Image" in obj:
            continue
        hdr, _, rest = obj.partition(b"stream")
        raw = rest.split(b"endstream")[0].strip()
        try:
            if b"ASCII85" in hdr:
                raw = base64.a85decode(raw.rstrip(b"~>").lstrip(b"<~"))
            if b"Flate" in hdr:
                raw = zlib.decompress(raw)
        except Exception:
            continue
        out += [x.decode("latin-1") for x in re.findall(rb"\(((?:[^()\\]|\\.)*)\)\s*Tj", raw)]
    return " ".join(out)


@pytest.fixture(scope="module")
def s():
    ss = requests.Session()
    r = ss.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PWD})
    if r.status_code != 200:
        pytest.skip("login failed")
    return ss


def post(s, org, body):
    return s.post(f"{BASE_URL}/api/staff/groups-pdf", json=body, headers={"X-Org-Id": org})


class TestGroupsPdf:
    def test_all_groups(self, s):
        r = post(s, DEMO, {"evento_id": None, "gruppo": None})
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("application/pdf")
        assert r.content[:4] == b"%PDF"
        assert r.headers.get("x-export-count") == "9"
        assert "tuttiigruppi" in r.headers.get("content-disposition", "").lower()
        t = pdf_text(r.content)
        print(t[:1500])
        for n in ("Bianchi", "Ferrari", "Colombo", "Conti", "Tutti gli eventi", "Cognome", "Mansione", "Taglia", "Non indicata"):
            assert n in t, n
        assert "@example.com" not in t
        # alphabetical: ASD before Croce before Protezione
        i1, i2, i3 = t.find("TEST_ASD Podistica Pisa"), t.find("TEST_Croce Rossa"), t.find("TEST_Protezione Civile")
        assert -1 < i1 < i2 < i3

    def test_single_group(self, s):
        r = post(s, DEMO, {"evento_id": None, "gruppo": "TEST_Croce Rossa"})
        assert r.status_code == 200
        assert r.headers.get("x-export-count") == "3"
        t = pdf_text(r.content)
        for n in ("Bianchi", "Ricci", "Bruno"):
            assert n in t
        for n in ("Ferrari", "Colombo", "Conti", "Gallo"):
            assert n not in t

    def test_event_filter(self, s):
        r = post(s, DEMO, {"evento_id": "demo_evt_tri", "gruppo": None})
        assert r.status_code == 200
        t = pdf_text(r.content)
        print("TRI:", r.headers.get("x-export-count"), t[:800])
        assert "Sunset Triathlon 2027" in t
        assert "Ricci" in t and "Ferrari" in t
        assert "Bianchi" not in t and "Conti" not in t
        assert r.headers.get("x-export-count") == "2"

    def test_event_and_group(self, s):
        r = post(s, DEMO, {"evento_id": "demo_evt_trail", "gruppo": "TEST_Protezione Civile"})
        assert r.status_code == 200
        assert r.headers.get("x-export-count") == "1"
        assert "Colombo" in pdf_text(r.content)

    def test_unknown_event_404(self, s):
        r = post(s, DEMO, {"evento_id": "nope_evt", "gruppo": None})
        assert r.status_code == 404

    def test_unknown_group_empty(self, s):
        r = post(s, DEMO, {"evento_id": None, "gruppo": "TEST_Inesistente"})
        assert r.status_code == 200
        assert r.headers.get("x-export-count") == "0"

    def test_org_isolation(self, s):
        r = post(s, OTHER, {"evento_id": None, "gruppo": None})
        assert r.status_code == 200
        t = pdf_text(r.content)
        for n in ("Bianchi", "Ferrari", "TEST_Croce Rossa"):
            assert n not in t
        r2 = post(s, OTHER, {"evento_id": None, "gruppo": "TEST_Croce Rossa"})
        assert r2.headers.get("x-export-count") == "0"
        r3 = post(s, OTHER, {"evento_id": "demo_evt_tri", "gruppo": None})
        assert r3.status_code == 404

    def test_unauthenticated(self):
        r = requests.post(f"{BASE_URL}/api/staff/groups-pdf", json={})
        assert r.status_code in (401, 403)
