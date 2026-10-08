"""Iter 88 — maps-attachments + lead_demo_action (Meet simulato)."""
import io
import os
import re
import pytest
import requests

def _load_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        for line in open("/app/frontend/.env"):
            if line.startswith("REACT_APP_BACKEND_URL="):
                v = line.split("=", 1)[1].strip()
                break
    return v.rstrip("/")

BASE = _load_url()
SA = ("manara.michele.pro@gmail.com", "CrmEvent2026!")
QA = ("qa.eventi@crmeventqa.it", "QaEvents2026!")

GPX_SAMPLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">
<trk><name>TEST_</name><trkseg>
<trkpt lat="45.0" lon="9.0"></trkpt>
<trkpt lat="45.01" lon="9.01"></trkpt>
</trkseg></trk></gpx>"""
PDF_SAMPLE = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
# 1x1 PNG
PNG_SAMPLE = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
              b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf"
              b"\xc0\x00\x00\x00\x03\x00\x01\x5b\xe4\xd2\xd1\x00\x00\x00\x00IEND\xaeB`\x82")
TXT_SAMPLE = b"TEST_misc\n"


def login(creds):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": creds[0], "password": creds[1]})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def qa():
    return login(QA)


@pytest.fixture(scope="module")
def sa():
    return login(SA)


def _upload(sess, filename, content, ctype):
    r = sess.post(f"{BASE}/api/upload", files={"file": (filename, io.BytesIO(content), ctype)})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def event_id(qa):
    r = qa.get(f"{BASE}/api/events")
    assert r.status_code == 200
    events = r.json()
    assert events, "QA org has no events — can't run maps tests"
    return events[0]["id"]


@pytest.fixture(scope="module")
def created(qa, event_id):
    """Create 4 maps with TEST_ prefix: no-attach, gpx-only, pdf-only, all-four."""
    gpx = _upload(qa, "TEST_iter88.gpx", GPX_SAMPLE, "application/gpx+xml")
    pdf = _upload(qa, "TEST_iter88.pdf", PDF_SAMPLE, "application/pdf")
    png = _upload(qa, "TEST_iter88.png", PNG_SAMPLE, "image/png")
    misc = _upload(qa, "TEST_iter88.csv", b"a,b\n1,2\n", "text/csv")

    def mk(payload):
        r = qa.post(f"{BASE}/api/maps", json={"evento_id": event_id, "tipologia": "Percorso", **payload})
        assert r.status_code == 200, r.text
        return r.json()["id"]

    ids = {
        "none": mk({"nome": "TEST_iter88 none"}),
        "gpx": mk({"nome": "TEST_iter88 gpx", "gpx_url": gpx["url"]}),
        "pdf": mk({"nome": "TEST_iter88 pdf", "pdf_url": pdf["url"]}),
        "all": mk({"nome": "TEST_iter88 all",
                   "gpx_url": gpx["url"],
                   "pdf_url": pdf["url"] + "?x=1",  # query string must be ignored
                   "immagine_url": png["url"],
                   "file_url": misc["url"]}),
        "ghost": mk({"nome": "TEST_iter88 ghost",
                     "gpx_url": "/api/files/nonexistent-id-xyz",
                     "pdf_url": "https://external.example.com/foo.pdf"}),
    }
    yield {"ids": ids, "uploads": {"gpx": gpx, "pdf": pdf, "png": png, "misc": misc}}
    # cleanup
    for mid in ids.values():
        qa.delete(f"{BASE}/api/maps/{mid}")
    for u in [gpx, pdf, png, misc]:
        qa.delete(f"{BASE}/api/files/{u['id']}") if False else None  # files endpoint has no DELETE used here


# ---------------- maps-attachments ----------------

def test_maps_attachments_structure(qa, event_id, created):
    r = qa.get(f"{BASE}/api/maps-attachments", params={"evento_id": event_id})
    assert r.status_code == 200, r.text
    data = r.json()
    ids = created["ids"]
    # none → []
    assert data.get(ids["none"]) == []
    # gpx-only
    g = data[ids["gpx"]]
    assert len(g) == 1 and g[0]["kind"] == "gpx" and g[0]["field"] == "gpx_url"
    # pdf-only
    p = data[ids["pdf"]]
    assert len(p) == 1 and p[0]["kind"] == "pdf" and p[0]["field"] == "pdf_url"
    # all four
    a = data[ids["all"]]
    kinds = {x["kind"] for x in a}
    fields = {x["field"] for x in a}
    assert fields == {"gpx_url", "pdf_url", "immagine_url", "file_url"}, fields
    assert {"gpx", "pdf", "image"}.issubset(kinds), kinds
    assert len(a) == 4
    # ghost: external http included, inexistent /api/files/... excluded
    gh = data[ids["ghost"]]
    assert any(x["url"].startswith("https://external.example.com") for x in gh)
    assert not any("nonexistent-id-xyz" in x["url"] for x in gh)


def test_maps_attachments_query_string_pdf_resolved(qa, event_id, created):
    """The stored pdf_url has ?x=1 — endpoint must still verify it exists in db.files."""
    r = qa.get(f"{BASE}/api/maps-attachments", params={"evento_id": event_id})
    data = r.json()
    all_items = data[created["ids"]["all"]]
    pdf_item = next(x for x in all_items if x["field"] == "pdf_url")
    # Must resolve the file (name present proves db lookup succeeded)
    assert pdf_item.get("name") == "TEST_iter88.pdf", pdf_item


def test_maps_attachments_pdf_url_is_200(qa, created):
    pdf_url = created["uploads"]["pdf"]["url"]  # /api/files/{id}
    r = qa.get(f"{BASE}{pdf_url}")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf")


def test_maps_attachments_cross_org_blocked(sa, event_id):
    """Super Admin has no org_id → maps-attachments should 403 (require_admin blocks SA) or empty."""
    r = sa.get(f"{BASE}/api/maps-attachments", params={"evento_id": event_id})
    # require_admin typically rejects SA
    assert r.status_code in (401, 403, 404, 428), r.status_code


# ---------------- Demo (Meet simulato) ----------------

@pytest.fixture
def lead_id(sa):
    """Create a TEST_ lead via public endpoint then grab its id."""
    import datetime as dt
    tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    email = f"TEST_iter88_{os.urandom(3).hex()}@example.com"
    r = requests.post(f"{BASE}/api/leads", json={
        "nome": "TEST", "cognome": "Iter88", "email": email,
        "privacy": True, "marketing_consent": False,
        "demo_data": tomorrow, "demo_ora": "10:30",
    })
    assert r.status_code == 200, r.text
    lid = r.json()["id"]
    yield lid
    # cleanup
    sa.delete(f"{BASE}/api/leads/{lid}")


def test_lead_demo_confirm_meet_sim(sa, lead_id):
    r = sa.post(f"{BASE}/api/leads/{lead_id}/demo", json={"action": "confirm"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["demo_status"] == "confermata"
    link = body.get("demo_meet_link")
    assert link and link.startswith("https://meet.google.com/sim-"), link


def test_lead_demo_reschedule_keeps_same_link(sa, lead_id):
    import datetime as dt
    r0 = sa.post(f"{BASE}/api/leads/{lead_id}/demo", json={"action": "confirm"})
    link1 = r0.json().get("demo_meet_link")
    assert link1 and link1.startswith("https://meet.google.com/sim-"), r0.text
    new_date = (dt.date.today() + dt.timedelta(days=2)).isoformat()
    r = sa.post(f"{BASE}/api/leads/{lead_id}/demo",
                json={"action": "reschedule", "demo_data": new_date, "demo_ora": "15:00"})
    assert r.status_code == 200, r.text
    assert r.json()["demo_status"] == "riprogrammata"
    assert r.json()["demo_meet_link"] == link1


def test_lead_demo_cancel_clears_link(sa, lead_id):
    sa.post(f"{BASE}/api/leads/{lead_id}/demo", json={"action": "confirm"})
    r = sa.post(f"{BASE}/api/leads/{lead_id}/demo", json={"action": "cancel"})
    assert r.status_code == 200, r.text
    assert r.json()["demo_status"] == "annullata"
    assert r.json().get("demo_meet_link") in (None, "")


def test_lead_demo_requires_superadmin(lead_id):
    qa_sess = login(QA)
    r = qa_sess.post(f"{BASE}/api/leads/{lead_id}/demo", json={"action": "confirm"})
    assert r.status_code in (401, 403), r.status_code
