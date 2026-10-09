"""Iter117: GET /api/maps-attachments - verify kind resolution for different attachment types,
org isolation, migrated file records (missing is_deleted / missing original_filename / legacy URLs)."""
import os
import io
import uuid
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ['REACT_APP_BACKEND_URL'].rstrip('/') if 'REACT_APP_BACKEND_URL' in os.environ else "https://manage-events-12.preview.emergentagent.com"
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'test_database')

EMAIL = "qa.eventi@crmeventqa.it"
PWD = "QaEvents2026!"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PWD}, timeout=20)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    me = s.get(f"{BASE_URL}/api/auth/me", timeout=20).json()
    s.headers.update({"X-Org-Id": me["org_id"]})
    s.org_id = me["org_id"]
    return s


@pytest.fixture(scope="module")
def db():
    c = MongoClient(MONGO_URL)
    return c[DB_NAME]


@pytest.fixture(scope="module")
def event_ctx(session):
    # Create TEST_ event
    r = session.post(f"{BASE_URL}/api/events", json={
        "nome": f"TEST_ITER117_EV_{uuid.uuid4().hex[:6]}",
        "data_inizio": "2026-06-01", "data_fine": "2026-06-02",
    }, timeout=20)
    assert r.status_code in (200, 201), r.text
    ev = r.json()
    yield ev
    # cleanup
    session.delete(f"{BASE_URL}/api/events/{ev['id']}", timeout=20)


def _upload(session, filename, content, content_type):
    files = {"file": (filename, io.BytesIO(content), content_type)}
    r = session.post(f"{BASE_URL}/api/upload", files=files, timeout=30)
    assert r.status_code == 200, f"upload {filename}: {r.status_code} {r.text}"
    return r.json()  # {id, url, filename}


def test_kinds_resolution_full_matrix(session, db, event_ctx):
    """Upload gpx, pdf, jpg, png, kml, kmz via /api/upload; create map; assert kinds."""
    gpx = _upload(session, "track.gpx", b"<gpx></gpx>", "application/gpx+xml")
    pdf = _upload(session, "doc.pdf", b"%PDF-1.4\n%EOF", "application/pdf")
    jpg = _upload(session, "pic.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 100, "image/jpeg")
    png = _upload(session, "pic.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 100, "image/png")
    # NOTE: /api/upload rejects kml/kmz (unsupported_type). Seed directly in db.files to represent
    # legacy/migrated or externally-ingested KML/KMZ attachments.
    kml_fid = f"TEST_ITER117_KML_{uuid.uuid4().hex[:8]}"
    db.files.insert_one({"id": kml_fid, "org_id": session.org_id,
        "original_filename": "map.kml", "content_type": "application/vnd.google-earth.kml+xml",
        "storage_path": f"uploads/{session.org_id}/{kml_fid}.kml", "is_deleted": False})
    kmz_fid = f"TEST_ITER117_KMZ_{uuid.uuid4().hex[:8]}"
    db.files.insert_one({"id": kmz_fid, "org_id": session.org_id,
        "original_filename": "map.kmz", "content_type": "application/vnd.google-earth.kmz",
        "storage_path": f"uploads/{session.org_id}/{kmz_fid}.kmz", "is_deleted": False})
    kml = {"url": f"/api/files/{kml_fid}"}
    kmz = {"url": f"/api/files/{kmz_fid}"}

    # Map 1: gpx + pdf + jpg
    r = session.post(f"{BASE_URL}/api/maps", json={
        "evento_id": event_ctx["id"], "nome": "TEST_ITER117_M1",
        "gpx_url": gpx["url"], "pdf_url": pdf["url"], "immagine_url": jpg["url"],
    }, timeout=20)
    assert r.status_code in (200, 201), r.text
    m1 = r.json()

    # Map 2: png as immagine + kml as file
    r = session.post(f"{BASE_URL}/api/maps", json={
        "evento_id": event_ctx["id"], "nome": "TEST_ITER117_M2",
        "immagine_url": png["url"], "file_url": kml["url"],
    }, timeout=20)
    assert r.status_code in (200, 201), r.text
    m2 = r.json()

    # Map 3: kmz as file
    r = session.post(f"{BASE_URL}/api/maps", json={
        "evento_id": event_ctx["id"], "nome": "TEST_ITER117_M3",
        "file_url": kmz["url"],
    }, timeout=20)
    m3 = r.json()

    # Map 4: no attachments
    r = session.post(f"{BASE_URL}/api/maps", json={
        "evento_id": event_ctx["id"], "nome": "TEST_ITER117_M_EMPTY",
    }, timeout=20)
    m_empty = r.json()

    r = session.get(f"{BASE_URL}/api/maps-attachments", params={"evento_id": event_ctx["id"]}, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()

    def kinds(mid):
        return {(it["field"], it["kind"]) for it in data.get(mid, [])}

    assert kinds(m1["id"]) == {("gpx_url", "gpx"), ("pdf_url", "pdf"), ("immagine_url", "image")}
    assert kinds(m2["id"]) == {("immagine_url", "image"), ("file_url", "file")}
    assert kinds(m3["id"]) == {("file_url", "file")}
    # Map empty: no attachments → []
    assert data.get(m_empty["id"]) == []

    # cleanup maps
    for mid in [m1["id"], m2["id"], m3["id"], m_empty["id"]]:
        session.delete(f"{BASE_URL}/api/maps/{mid}", timeout=20)


def test_migrated_file_no_is_deleted_field(session, db, event_ctx):
    """Insert a files doc directly in Mongo with NO is_deleted field, legacy pdf; verify resolves."""
    fid = f"TEST_ITER117_FID_{uuid.uuid4().hex[:8]}"
    db.files.insert_one({
        "id": fid, "org_id": session.org_id,
        "original_filename": "x.pdf", "content_type": "application/pdf",
        "storage_path": f"uploads/{session.org_id}/{fid}.pdf",
        # NOTE: no is_deleted field
    })
    r = session.post(f"{BASE_URL}/api/maps", json={
        "evento_id": event_ctx["id"], "nome": "TEST_ITER117_MIG1",
        "pdf_url": f"/api/files/{fid}",
    }, timeout=20)
    mp = r.json()
    try:
        r = session.get(f"{BASE_URL}/api/maps-attachments", params={"evento_id": event_ctx["id"]}, timeout=20)
        items = r.json().get(mp["id"], [])
        assert len(items) == 1
        assert items[0]["kind"] == "pdf"
        assert items[0]["field"] == "pdf_url"
    finally:
        session.delete(f"{BASE_URL}/api/maps/{mp['id']}", timeout=20)
        db.files.delete_one({"id": fid})


def test_file_record_no_original_filename_storage_kml(session, db, event_ctx):
    """File record without original_filename but storage_path ends .kml → kind file."""
    fid = f"TEST_ITER117_FID_{uuid.uuid4().hex[:8]}"
    db.files.insert_one({
        "id": fid, "org_id": session.org_id,
        "content_type": "application/octet-stream",
        "storage_path": f"uploads/{session.org_id}/{fid}.kml",
        "is_deleted": False,
    })
    r = session.post(f"{BASE_URL}/api/maps", json={
        "evento_id": event_ctx["id"], "nome": "TEST_ITER117_MIG2",
        "file_url": f"/api/files/{fid}",
    }, timeout=20)
    mp = r.json()
    try:
        r = session.get(f"{BASE_URL}/api/maps-attachments", params={"evento_id": event_ctx["id"]}, timeout=20)
        items = r.json().get(mp["id"], [])
        assert len(items) == 1
        assert items[0]["kind"] == "file"
    finally:
        session.delete(f"{BASE_URL}/api/maps/{mp['id']}", timeout=20)
        db.files.delete_one({"id": fid})


def test_legacy_external_http_pdf(session, event_ctx):
    """Legacy external http URL ending .pdf → kind pdf (resolved as external link)."""
    r = session.post(f"{BASE_URL}/api/maps", json={
        "evento_id": event_ctx["id"], "nome": "TEST_ITER117_MIG3",
        "pdf_url": "https://example.com/legacy/old.pdf",
    }, timeout=20)
    mp = r.json()
    try:
        r = session.get(f"{BASE_URL}/api/maps-attachments", params={"evento_id": event_ctx["id"]}, timeout=20)
        items = r.json().get(mp["id"], [])
        assert len(items) == 1, items
        assert items[0]["kind"] == "pdf"
    finally:
        session.delete(f"{BASE_URL}/api/maps/{mp['id']}", timeout=20)


def test_legacy_relative_png(session, event_ctx):
    """Legacy relative URL '/uploads/old.png' → kind image."""
    r = session.post(f"{BASE_URL}/api/maps", json={
        "evento_id": event_ctx["id"], "nome": "TEST_ITER117_MIG4",
        "immagine_url": "/uploads/old.png",
    }, timeout=20)
    mp = r.json()
    try:
        r = session.get(f"{BASE_URL}/api/maps-attachments", params={"evento_id": event_ctx["id"]}, timeout=20)
        items = r.json().get(mp["id"], [])
        assert len(items) == 1, items
        assert items[0]["kind"] == "image"
    finally:
        session.delete(f"{BASE_URL}/api/maps/{mp['id']}", timeout=20)


def test_cross_org_isolation(session, db, event_ctx):
    """File belonging to another org → not returned (isolation)."""
    fid = f"TEST_ITER117_OTHER_{uuid.uuid4().hex[:8]}"
    db.files.insert_one({
        "id": fid, "org_id": "OTHER_ORG_FAKE_XYZ",
        "original_filename": "secret.pdf", "content_type": "application/pdf",
        "storage_path": f"uploads/other/{fid}.pdf", "is_deleted": False,
    })
    r = session.post(f"{BASE_URL}/api/maps", json={
        "evento_id": event_ctx["id"], "nome": "TEST_ITER117_ISO",
        "pdf_url": f"/api/files/{fid}",
    }, timeout=20)
    mp = r.json()
    try:
        r = session.get(f"{BASE_URL}/api/maps-attachments", params={"evento_id": event_ctx["id"]}, timeout=20)
        items = r.json().get(mp["id"], [])
        # URL references /api/files/<id> → regex matched, but org mismatch returns None → not included
        assert items == [], f"Expected empty due to isolation, got {items}"
    finally:
        session.delete(f"{BASE_URL}/api/maps/{mp['id']}", timeout=20)
        db.files.delete_one({"id": fid})
