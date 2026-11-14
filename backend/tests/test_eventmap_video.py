# Event Map video generator: options, tracks upload/validation, preview, gating (403), generation queue, download, counters, cross-org isolation
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
SA_EMAIL, SA_PW = "manara.michele.pro@gmail.com", "CrmEvent2026!"
READY_EMAIL, READY_PW = "test_em_1794651032@example.com", "TestEventMap2026!"
GPX = os.path.join(os.path.dirname(__file__), "fixtures", "pisa_run.gpx")
CREATED_ORGS = []
STATE = {}


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return s


def _org(label, plan, sa):
    s = requests.Session()
    em = f"test_emv_{label}_{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{API}/auth/register-organization", json={
        "nome": "TEST", "cognome": "EMV", "email": em, "password": "TestEventMap2026!",
        "org_name": f"TEST_EMV {label}", "telefono": "+393471234567", "accept_terms": True})
    assert r.status_code in (200, 201), r.text
    oid = s.get(f"{API}/auth/me").json()["org_id"]
    CREATED_ORGS.append((oid, em))
    if plan:
        r = sa.put(f"{API}/platform/saas/orgs/{oid}/admin", json={"plan": plan, "status": "active"})
        assert r.status_code == 200, r.text
    ev = s.post(f"{API}/events", json={"nome": f"TEST_EMV Run {label}", "data_inizio": "2026-12-13"})
    assert ev.status_code in (200, 201), ev.text
    return s, oid, ev.json()["id"]


@pytest.fixture(scope="module")
def sa():
    return _login(SA_EMAIL, SA_PW)


@pytest.fixture(scope="module")
def silver(sa):
    s, oid, eid = _org("silver", "silver", sa)
    yield s, oid, eid
    print("CREATED_ORGS", CREATED_ORGS)


def test_options(silver):
    s, _, _ = silver
    d = s.get(f"{API}/eventmap/options").json()
    keys = [x["key"] for x in d["styles"]]
    assert keys == ["dark", "streets", "satellite"]
    assert d["styles"][2]["disabled"] is True and "MapTiler" in d["styles"][2]["note"]
    assert [f["key"] for f in d["formats"]] == ["9:16", "1:1", "16:9"]
    assert d["durations"] == [15, 30, 60]
    assert {m["key"] for m in d["music"]} == {"sportiva", "emozionale", "elettronica", "cinematografica"}
    for m in d["music"]:
        r = requests.get(f"{BASE_URL}{m['preview']}")
        assert r.status_code == 200 and len(r.content) > 100000, m
        assert "audio" in r.headers.get("content-type", "") or r.content[:3] in (b"ID3", b"\xff\xfb"), r.headers


def test_options_requires_auth():
    assert requests.get(f"{API}/eventmap/options").status_code in (401, 403)


def test_upload_invalid(silver):
    s, _, eid = silver
    r = s.post(f"{API}/eventmap/events/{eid}/tracks", files={"file": ("bad.gpx", b"<gpx></gpx>", "application/gpx+xml")})
    assert r.status_code == 400, r.text
    r = s.post(f"{API}/eventmap/events/{eid}/tracks", files={"file": ("x.txt", b"hello", "text/plain")})
    assert r.status_code == 400 and ".gpx" in r.text
    r = s.post(f"{API}/eventmap/events/{eid}/tracks", files={"file": ("junk.gpx", b"\x00\x01notxml", "application/gpx+xml")})
    assert r.status_code == 400, r.text


def test_upload_valid_and_state(silver):
    s, _, eid = silver
    with open(GPX, "rb") as f:
        r = s.post(f"{API}/eventmap/events/{eid}/tracks", files={"file": ("pisa_run.gpx", f, "application/gpx+xml")})
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["distance_m"] > 1000 and t["points"] > 10 and "storage" not in t and "_id" not in t
    STATE["tid"] = t["id"]
    st = s.get(f"{API}/eventmap/events/{eid}").json()
    assert st["event"]["id"] == eid and st["event"]["data"] == "13 dicembre 2026"
    assert any(x["id"] == t["id"] for x in st["tracks"])
    assert st["rights"]["active"] is False
    assert isinstance(st["maps"], list) and st["videos"] == []


def test_preview_jpeg(silver):
    s, _, _ = silver
    r = s.post(f"{API}/eventmap/tracks/{STATE['tid']}/preview", json={"style": "streets", "format": "1:1"}, timeout=120)
    assert r.status_code == 200, r.text[:300]
    assert r.headers["content-type"].startswith("image/jpeg") and r.content[:2] == b"\xff\xd8"
    r = s.post(f"{API}/eventmap/tracks/{STATE['tid']}/preview", json={"style": "satellite", "format": "1:1"})
    assert r.status_code == 400


def test_video_not_active_403(silver):
    s, _, eid = silver
    r = s.post(f"{API}/eventmap/events/{eid}/videos", json={"track_id": STATE["tid"], "duration": 15})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "addon_required"


def test_activate_then_no_videos_403(silver):
    s, _, eid = silver
    r = s.post(f"{API}/addons/eventmap/events/{eid}/activate")
    assert r.status_code == 200, r.text
    r = s.post(f"{API}/eventmap/events/{eid}/videos", json={"track_id": STATE["tid"], "duration": 15})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "addon_videos", r.text


def test_invalid_options_400(silver, sa):
    s, oid, eid = silver
    r = sa.post(f"{API}/platform/addons/orgs/{oid}/grants", json={"product": "eventmap", "source": "superadmin", "events_total": 1, "videos_total": 1})
    assert r.status_code == 200, r.text
    for body in ({"duration": 20}, {"format": "4:3"}, {"style": "satellite"}, {"music": "jazz"}):
        r = s.post(f"{API}/eventmap/events/{eid}/videos", json={"track_id": STATE["tid"], "duration": 15, **body})
        assert r.status_code == 400, (body, r.text)
    r = s.post(f"{API}/eventmap/events/{eid}/videos", json={"track_id": "nope", "duration": 15})
    assert r.status_code == 404


def test_generate_and_over_limit(silver):
    s, _, eid = silver
    r = s.post(f"{API}/eventmap/events/{eid}/videos", json={"track_id": STATE["tid"], "duration": 15, "format": "9:16", "music": "sportiva"})
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["status"] == "queued" and "org_id" not in v
    STATE["vid"] = v["id"]
    rg = s.get(f"{API}/eventmap/events/{eid}").json()["rights"]
    assert rg["in_progress"] == 1 and rg["videos_remaining"] == 0 and rg["videos_used"] == 0
    # in-flight job reserves the slot
    r = s.post(f"{API}/eventmap/events/{eid}/videos", json={"track_id": STATE["tid"], "duration": 15})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "addon_videos"


def test_poll_until_completed(silver):
    s, _, _ = silver
    seen, deadline = set(), time.time() + 420
    while time.time() < deadline:
        d = s.get(f"{API}/eventmap/videos/{STATE['vid']}").json()
        seen.add(d["status"])
        if d["status"] in ("completed", "error"):
            break
        time.sleep(5)
    print("statuses seen", seen, "final", d.get("status"), d.get("error"))
    assert d["status"] == "completed", d
    assert d["progress"] == 100 and d["size"] > 50000 and "storage" not in d


def test_download_and_counter(silver):
    s, _, eid = silver
    r = s.get(f"{API}/eventmap/videos/{STATE['vid']}/file?download=1")
    assert r.status_code == 200 and r.headers["content-type"] == "video/mp4"
    assert "attachment" in r.headers["content-disposition"] and r.content[4:8] == b"ftyp"
    open("/tmp/emv_test.mp4", "wb").write(r.content)
    r2 = s.get(f"{API}/eventmap/videos/{STATE['vid']}/file")
    assert "inline" in r2.headers["content-disposition"]
    rg = s.get(f"{API}/eventmap/events/{eid}").json()["rights"]
    assert rg["videos_used"] == 1 and rg["in_progress"] == 0 and rg["videos_remaining"] == 0


def test_cross_org(silver, sa):
    s2, _, eid2 = _org("other", "silver", sa)
    _, _, eid = silver
    assert s2.get(f"{API}/eventmap/videos/{STATE['vid']}").status_code == 404
    assert s2.get(f"{API}/eventmap/videos/{STATE['vid']}/file?download=1").status_code == 404
    assert s2.get(f"{API}/eventmap/events/{eid}").status_code == 404
    assert s2.post(f"{API}/eventmap/tracks/{STATE['tid']}/preview", json={}).status_code == 404
    assert s2.post(f"{API}/eventmap/events/{eid2}/videos", json={"track_id": STATE["tid"]}).status_code == 404


def test_ready_org_zero_remaining():
    s = _login(READY_EMAIL, READY_PW)
    me = s.get(f"{API}/auth/me").json()
    evs = s.get(f"{API}/events").json()
    evs = evs if isinstance(evs, list) else evs.get("items", evs.get("events", []))
    states = [s.get(f"{API}/eventmap/events/{e['id']}").json() for e in evs]
    act = [x for x in states if x.get("rights", {}).get("active")]
    assert act, "ready org must have an active event"
    print("ready org", me.get("org_id"), act[0]["rights"], len(act[0]["videos"]))
    assert len([v for v in act[0]["videos"] if v["status"] == "completed"]) >= 3


def test_public_addons_included():
    r = requests.get(f"{API}/public/addons-included")
    assert r.status_code == 200
    d = r.json()
    print("addons-included", d)
    assert d
