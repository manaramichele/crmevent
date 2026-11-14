# Event Map rights: plan-included videos (min 1), GOLD/SILVER/BRONZE activation limits, purchase grant (DB-simulated, no Stripe),
# Super Admin manual grant/revoke, generation reservation (no double charge), failed generation releases the video.
# Created orgs are written to /tmp/em_rights_orgs.json; run tests/cleanup_em_rights_orgs.py afterwards.
import json
import os
import time
import uuid
from datetime import datetime, timezone

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
SA_EMAIL, SA_PW = "manara.michele.pro@gmail.com", "CrmEvent2026!"
PW = "TestEventMap2026!"
GPX = os.path.join(os.path.dirname(__file__), "fixtures", "pisa_run.gpx")
ORGS_FILE = "/tmp/em_rights_orgs.json"
STORAGE_ROOT = "/app/backend/storage_data"
mdb = MongoClient("mongodb://localhost:27017")["test_database"]  # preview DB only
ORGS = {}


def _save():
    json.dump(ORGS, open(ORGS_FILE, "w"))


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return s


def _org(label, plan, sa, n_events):
    s = requests.Session()
    em = f"test_emr_{label}_{uuid.uuid4().hex[:8]}@example.com"
    name = f"TEST_EMR {label} {uuid.uuid4().hex[:4]}"
    r = s.post(f"{API}/auth/register-organization", json={"nome": "TEST", "cognome": "EMR", "email": em, "password": PW,
                                                          "org_name": name, "telefono": "+393471234567", "accept_terms": True})
    assert r.status_code in (200, 201), r.text
    oid = s.get(f"{API}/auth/me").json()["org_id"]
    ORGS[label] = {"id": oid, "name": name, "email": em, "events": []}
    _save()
    r = sa.put(f"{API}/platform/saas/orgs/{oid}/admin", json={"plan": plan, "status": "active"})
    assert r.status_code == 200, r.text
    for i in range(n_events):
        ev = s.post(f"{API}/events", json={"nome": f"TEST_EMR {label} Run {i + 1}", "data_inizio": "2026-12-13"})
        assert ev.status_code in (200, 201), ev.text
        ORGS[label]["events"].append(ev.json()["id"])
    _save()
    return s, oid, ORGS[label]["events"]


def _hub(s):
    r = s.get(f"{API}/addons/eventmap")
    assert r.status_code == 200, r.text
    return r.json()


def _rights(s, eid):
    r = s.get(f"{API}/eventmap/events/{eid}")
    assert r.status_code == 200, r.text
    return r.json()["rights"]


def _upload(s, eid):
    with open(GPX, "rb") as f:
        r = s.post(f"{API}/eventmap/events/{eid}/tracks", files={"file": ("pisa_run.gpx", f, "application/gpx+xml")})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _video(s, eid, tid):
    return s.post(f"{API}/eventmap/events/{eid}/videos", json={"track_id": tid, "style": "dark", "format": "9:16", "duration": 15, "music": None})


def _wait(s, vid, timeout=240):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = s.get(f"{API}/eventmap/videos/{vid}").json()
        if v["status"] in ("completed", "error"):
            return v
        time.sleep(4)
    raise AssertionError("video timeout")


@pytest.fixture(scope="module")
def sa():
    return _login(SA_EMAIL, SA_PW)


@pytest.fixture(scope="module")
def gold(sa):
    return _org("gold", "gold", sa, 4)


@pytest.fixture(scope="module")
def silver(sa):
    return _org("silver", "silver", sa, 2)


@pytest.fixture(scope="module")
def bronze(sa):
    return _org("bronze", "bronze", sa, 1)


@pytest.fixture(scope="module")
def bronze0(sa):
    return _org("bronze0", "bronze", sa, 1)


# --- config ---
def test_config_rejects_zero_videos(sa):
    cfg = sa.get(f"{API}/platform/addons/config").json()
    print("preview config eventmap", cfg["eventmap"])
    body = {"planner_included": cfg["planner"]["included"], "planner_price": cfg["planner"].get("price"),
            "eventmap_included": cfg["eventmap"]["included"], "eventmap_included_videos": 0, "eventmap_packages": cfg["eventmap"].get("packages") or []}
    r = sa.put(f"{API}/platform/addons/config", json=body)
    assert r.status_code == 422, r.text
    assert sa.get(f"{API}/platform/addons/config").json()["eventmap"] == cfg["eventmap"]


def test_public_included_min_one():
    d = requests.get(f"{API}/public/addons-included").json()
    assert d["eventmap_included_videos"] >= 1, d


# --- GOLD ---
def test_gold_before_activation(gold):
    s, _, evs = gold
    h = _hub(s)
    print("gold hub pre", {k: h[k] for k in ("plan", "mode", "included", "included_used", "videos_total", "videos_used", "unrestricted")})
    assert h["plan"] == "gold" and h["included"] == 3 and h["included_used"] == 0 and h["videos_total"] == 0
    rg = _rights(s, evs[0])
    assert rg["active"] is False


def test_gold_activate_one(gold):
    s, _, evs = gold
    r = s.post(f"{API}/addons/eventmap/events/{evs[0]}/activate")
    assert r.status_code == 200 and r.json()["source"] == "included", r.text
    h = _hub(s)
    assert (h["included"], h["included_used"], h["videos_total"], h["videos_used"], h["videos_available"]) == (3, 1, 1, 0, 1), h
    rg = _rights(s, evs[0])
    assert rg["active"] is True and rg["videos_remaining"] == 1 and rg["videos_total"] == 1 and rg["in_progress"] == 0, rg
    vc = s.get(f"{API}/addons/eventmap/events/{evs[0]}/video-check").json()
    assert vc["allowed"] is True and vc["videos_available"] == 1, vc
    assert next(e for e in h["events"] if e["id"] == evs[0])["active"] is True


def test_gold_activate_three_and_fourth_refused(gold):
    s, _, evs = gold
    for e in evs[1:3]:
        r = s.post(f"{API}/addons/eventmap/events/{e}/activate")
        assert r.status_code == 200, r.text
    h = _hub(s)
    assert h["included_used"] == 3 and h["videos_total"] == 3 and h["videos_available"] == 3, h
    r = s.post(f"{API}/addons/eventmap/events/{evs[3]}/activate")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "addon_required", r.text
    assert _rights(s, evs[3])["active"] is False
    for e in evs[:3]:
        assert _rights(s, e)["videos_remaining"] == 3


# --- SILVER ---
def test_silver_one_included(silver):
    s, _, evs = silver
    assert s.post(f"{API}/addons/eventmap/events/{evs[0]}/activate").status_code == 200
    h = _hub(s)
    assert (h["included"], h["included_used"], h["videos_total"], h["videos_available"]) == (1, 1, 1, 1), h
    r = s.post(f"{API}/addons/eventmap/events/{evs[1]}/activate")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "addon_required", r.text
    assert _rights(s, evs[0])["videos_remaining"] == 1


# --- SILVER generation: reservation + exactly one consumption ---
def test_silver_generation_success(silver):
    s, _, evs = silver
    tid = _upload(s, evs[0])
    r = _video(s, evs[0], tid)
    assert r.status_code == 200, r.text
    vid = r.json()["id"]
    rg = _rights(s, evs[0])
    assert rg["in_progress"] == 1 and rg["videos_remaining"] == 0 and rg["videos_used"] == 0, rg
    r2 = _video(s, evs[0], tid)
    assert r2.status_code == 403 and r2.json()["detail"]["code"] == "addon_videos", r2.text
    v = _wait(s, vid)
    assert v["status"] == "completed", v
    rg = _rights(s, evs[0])
    assert (rg["videos_used"], rg["videos_remaining"], rg["in_progress"]) == (1, 0, 0), rg
    h = _hub(s)
    assert h["videos_used"] == 1 and h["videos_available"] == 0
    assert mdb.eventmap_videos.find_one({"id": vid})["consumed"] is True
    ORGS["silver"]["vid"] = vid
    _save()


# --- SA manual grant + revoke (silver) ---
def test_sa_grant_and_revoke(silver, sa):
    s, oid, evs = silver
    r = sa.post(f"{API}/platform/addons/orgs/{oid}/grants", json={"product": "eventmap", "events_total": 1, "videos_total": 2, "note": "TEST_grant"})
    assert r.status_code == 200, r.text
    gid = r.json()["id"]
    h = _hub(s)
    assert h["videos_total"] == 3 and h["videos_available"] == 2 and h["grant_free"] == 1 and h["granted"] == 1, h
    assert s.post(f"{API}/addons/eventmap/events/{evs[1]}/activate").json()["source"] == "superadmin"
    rg = _rights(s, evs[1])
    assert rg["active"] and rg["videos_remaining"] == 2, rg
    assert _rights(s, evs[0])["videos_remaining"] == 2  # same pool, same rights everywhere
    sa_view = sa.get(f"{API}/platform/addons/orgs/{oid}").json()["eventmap"]
    assert sa_view["videos_total"] == 3 and sa_view["videos_used"] == 1
    assert sa.post(f"{API}/platform/addons/grants/{gid}/revoke").status_code == 200
    h = _hub(s)
    assert h["videos_total"] == 1 and h["videos_available"] == 0, h
    assert _rights(s, evs[1])["active"] is False
    g = mdb.addon_grants.find_one({"id": gid})
    assert g["status"] == "revoked" and len(g["history"]) == 2
    assert mdb.addon_activations.find_one({"org_id": oid, "event_id": evs[1]}) is not None  # history kept


# --- BRONZE ---
def test_bronze_requires_purchase(bronze):
    s, _, evs = bronze
    h = _hub(s)
    assert h["included"] == 0 and h["videos_total"] == 0
    r = s.post(f"{API}/addons/eventmap/events/{evs[0]}/activate")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "addon_required", r.text


def _purchase_grant(oid, videos):
    gid = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    mdb.addon_grants.insert_one({"id": gid, "org_id": oid, "product": "eventmap", "source": "purchase", "status": "active", "events_total": 1,
                                 "formats": [], "videos_total": videos, "package_id": None, "package_name": "TEST_sim", "price": 1.0,
                                 "event_id": None, "expires_at": None, "activated_at": now, "created_at": now, "history": []})
    return gid


def test_bronze_after_purchase(bronze):
    s, oid, evs = bronze
    _purchase_grant(oid, 2)
    r = s.post(f"{API}/addons/eventmap/events/{evs[0]}/activate")
    assert r.status_code == 200 and r.json()["source"] == "purchase", r.text
    h = _hub(s)
    assert h["purchased"] == 1 and h["videos_total"] == 2 and h["videos_available"] == 2, h
    assert _rights(s, evs[0])["videos_remaining"] == 2


def test_bronze_purchase_zero_videos(bronze0):
    """Base 'Attivazione per evento' with videos 0: event active but 0 videos -> report behaviour."""
    s, oid, evs = bronze0
    _purchase_grant(oid, 0)
    assert s.post(f"{API}/addons/eventmap/events/{evs[0]}/activate").status_code == 200
    rg = _rights(s, evs[0])
    vc = s.get(f"{API}/addons/eventmap/events/{evs[0]}/video-check").json()
    print("bronze purchase with 0 videos rights:", rg, vc)
    assert rg["active"] is True


# --- failure releases the reservation (gold) ---
def test_gold_failed_generation_releases(gold):
    s, _, evs = gold
    tid = _upload(s, evs[0])
    t = mdb.eventmap_tracks.find_one({"id": tid})
    os.remove(os.path.join(STORAGE_ROOT, t["storage"]["path"]))
    r = _video(s, evs[0], tid)
    assert r.status_code == 200, r.text
    v = _wait(s, r.json()["id"], 120)
    print("failed video", v.get("status"), v.get("error"))
    assert v["status"] == "error"
    rg = _rights(s, evs[0])
    assert (rg["videos_used"], rg["videos_remaining"], rg["in_progress"]) == (0, 3, 0), rg
    assert _hub(s)["videos_used"] == 0
