# Event Map "Gare": independent races per event (CRUD, copy settings, legacy auto-race, from-tracks, GPX dedupe,
# race preview, race videos with versioning + credits consumed only on completion, download filename, legacy video endpoint).
# Creates one TEST_ silver org (+SA grant) and deletes it at the end.
import io
import json
import os
import time
import uuid

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
SA = ("manara.michele.pro@gmail.com", "CrmEvent2026!")
PW = "TestEventMap2026!"
GPX = open(os.path.join(os.path.dirname(__file__), "fixtures", "pisa_run.gpx"), "rb").read()
GPX2 = GPX.replace(b"</gpx>", b"<!-- v2 --></gpx>")
GPX3 = GPX.replace(b"</gpx>", b"<!-- v3 --></gpx>")
mdb = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[os.environ.get("DB_NAME", "test_database")]
ST = {}


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return s


def _up(s, eid, data, name):
    return s.post(f"{API}/eventmap/events/{eid}/tracks", files={"file": (name, io.BytesIO(data), "application/gpx+xml")})


def _state(s, eid):
    r = s.get(f"{API}/eventmap/events/{eid}")
    assert r.status_code == 200, r.text
    return r.json()


def _wait(s, vid, timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = s.get(f"{API}/eventmap/videos/{vid}").json()
        if v["status"] in ("completed", "error"):
            return v
        time.sleep(4)
    raise AssertionError("video timeout")


@pytest.fixture(scope="module")
def sa():
    return _login(*SA)


@pytest.fixture(scope="module")
def org(sa):
    s = requests.Session()
    em = f"test_emraces_{uuid.uuid4().hex[:8]}@example.com"
    name = f"TEST_EMRaces {uuid.uuid4().hex[:4]}"
    r = s.post(f"{API}/auth/register-organization", json={"nome": "TEST", "cognome": "Races", "email": em, "password": PW,
                                                          "org_name": name, "telefono": "+393471234567", "accept_terms": True})
    assert r.status_code in (200, 201), r.text
    oid = s.get(f"{API}/auth/me").json()["org_id"]
    json.dump({"oid": oid, "name": name, "email": em}, open("/tmp/em_races_org.json", "w"))
    assert sa.put(f"{API}/platform/saas/orgs/{oid}/admin", json={"plan": "silver", "status": "active"}).status_code == 200
    evs = []
    for i in range(3):
        ev = s.post(f"{API}/events", json={"nome": f"TEST_Races Event {i + 1}", "data_inizio": "2026-12-13"})
        assert ev.status_code in (200, 201), ev.text
        evs.append(ev.json()["id"])
    yield s, oid, evs
    if os.environ.get("KEEP_ORG"):
        return
    d = sa.delete(f"{API}/platform/organizations/{oid}", json={"confirm_name": name})
    print("cleanup org", oid, d.status_code, d.text[:200])


# --- gating ---
def test_create_race_requires_addon(org):
    s, _, evs = org
    r = s.post(f"{API}/eventmap/events/{evs[0]}/races", json={"name": "Maratona"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "addon_required", r.text


def test_activate_and_grant(org, sa):
    s, oid, evs = org
    assert s.post(f"{API}/addons/eventmap/events/{evs[0]}/activate").status_code == 200
    r = sa.post(f"{API}/platform/addons/orgs/{oid}/grants", json={"product": "eventmap", "events_total": 2, "videos_total": 4, "note": "TEST_races"})
    assert r.status_code == 200, r.text
    for e in evs[1:]:
        assert s.post(f"{API}/addons/eventmap/events/{e}/activate").status_code == 200
    rg = _state(s, evs[0])["rights"]
    assert rg["active"] and rg["videos_remaining"] == 5, rg
    ST["remaining0"] = rg["videos_remaining"]


# --- single legacy track -> auto race ---
def test_single_track_auto_race(org):
    s, _, evs = org
    r = _up(s, evs[0], GPX, "pisa_run.gpx")
    assert r.status_code == 200, r.text
    ST["t1"] = r.json()["id"]
    d = _state(s, evs[0])
    assert len(d["races"]) == 1 and d["races"][0]["track_id"] == ST["t1"] and d["races"][0]["name"] == "pisa_run", d["races"]
    assert d["unassigned_tracks"] == []
    ST["auto_race"] = d["races"][0]["id"]
    d2 = _state(s, evs[0])
    assert len(d2["races"]) == 1  # idempotent


def test_gpx_dedupe(org):
    s, _, evs = org
    r = _up(s, evs[0], GPX, "copy.gpx")
    assert r.status_code == 200 and r.json()["duplicate"] is True and r.json()["id"] == ST["t1"], r.text
    assert mdb.eventmap_tracks.count_documents({"event_id": evs[0]}) == 1


# --- three races, independent settings ---
def test_three_races_independent(org):
    s, _, evs = org
    t2 = _up(s, evs[0], GPX2, "mezza.gpx").json()["id"]
    t3 = _up(s, evs[0], GPX3, "christmas.gpx").json()["id"]
    ST["t2"], ST["t3"] = t2, t3
    ids = []
    for n in ("Maratona", "Mezza Maratona", "Christmas Run"):
        r = s.post(f"{API}/eventmap/events/{evs[0]}/races", json={"name": n})
        assert r.status_code == 200, r.text
        assert r.json()["name"] == n and r.json()["track_id"] is None
        ids.append(r.json()["id"])
    ST["races"] = ids
    cfg = [
        {"title": "Maratona di Pisa", "subtitle": "42K", "date": "2026-12-13", "distance_km": 42.195, "track_id": ST["t1"], "logo": None,
         "style": "dark", "format": "16:9", "duration": 15, "speed": "fast", "music": None, "show_aid": False, "show_elevation": True},
        {"title": "Mezza di Pisa", "subtitle": "Half", "date": "2026-12-14", "distance_km": 21.097, "track_id": t2, "logo": None,
         "style": "streets", "format": "1:1", "duration": 30, "speed": "slow", "music": "emozionale", "show_aid": True, "show_elevation": False},
        {"title": "Christmas Run", "subtitle": "Fun", "date": "2026-12-24", "distance_km": 6.9, "track_id": t3, "logo": None,
         "style": "dark", "format": "9:16", "duration": 60, "speed": "normal", "music": "elettronica", "show_aid": True, "show_elevation": True},
    ]
    for rid, c in zip(ids, cfg):
        r = s.put(f"{API}/eventmap/races/{rid}", json=c)
        assert r.status_code == 200, r.text
        for k, v in c.items():
            assert r.json()[k] == v, (k, r.json()[k], v)
    ST["cfg"] = cfg
    # edit one -> others unchanged
    assert s.put(f"{API}/eventmap/races/{ids[1]}", json={"title": "Mezza EDIT"}).status_code == 200
    d = _state(s, evs[0])
    by = {x["id"]: x for x in d["races"]}
    for rid, c in zip(ids, cfg):
        exp = {**c, "title": "Mezza EDIT"} if rid == ids[1] else c
        for k, v in exp.items():
            assert by[rid][k] == v, (rid, k, by[rid][k], v)
    assert by[ids[1]]["subtitle"] == "Half"  # partial update keeps others


def test_race_validation(org):
    s, _, evs = org
    rid = ST["races"][0]
    assert s.put(f"{API}/eventmap/races/{rid}", json={"style": "xxx"}).status_code == 400
    assert s.put(f"{API}/eventmap/races/{rid}", json={"duration": 45}).status_code == 400
    assert s.put(f"{API}/eventmap/races/{rid}", json={"date": "2026-02-31"}).status_code == 422
    assert s.put(f"{API}/eventmap/races/{rid}", json={"distance_km": 0}).status_code == 422
    assert s.put(f"{API}/eventmap/races/{rid}", json={"name": "  "}).status_code == 400
    assert s.post(f"{API}/eventmap/events/{evs[0]}/races", json={}).status_code == 400
    assert s.put(f"{API}/eventmap/races/nope", json={"title": "x"}).status_code == 404
    # track from another event refused
    r = _up(s, evs[2], GPX, "other.gpx")
    assert r.status_code == 200, r.text
    ST["t_ev3"] = r.json()["id"]
    assert s.put(f"{API}/eventmap/races/{rid}", json={"track_id": ST["t_ev3"]}).status_code == 400
    # reset to defaults (null) allowed for date/distance
    r = s.put(f"{API}/eventmap/races/{ST['races'][2]}", json={"date": None, "distance_km": None})
    assert r.status_code == 200 and r.json()["date"] is None and r.json()["distance_km"] is None
    s.put(f"{API}/eventmap/races/{ST['races'][2]}", json={"date": "2026-12-24", "distance_km": 6.9})


def test_copy_settings_only(org):
    s, _, evs = org
    src, dst = ST["races"][1], ST["races"][2]
    r = s.post(f"{API}/eventmap/races/{dst}/copy-from/{src}")
    assert r.status_code == 200, r.text
    d = r.json()
    c_src, c_dst = ST["cfg"][1], ST["cfg"][2]
    for k in ("logo", "style", "format", "duration", "music", "speed", "show_aid", "show_elevation"):
        assert d[k] == c_src[k], k
    for k in ("title", "subtitle", "date", "distance_km", "track_id"):
        assert d[k] == c_dst[k], k
    assert d["name"] == "Christmas Run"
    assert s.post(f"{API}/eventmap/races/{dst}/copy-from/{dst}").status_code == 400


def test_race_preview(org):
    s, _, evs = org
    r = s.post(f"{API}/eventmap/races/{ST['races'][0]}/preview")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and r.content[:2] == b"\xff\xd8", r.text[:200]
    nr = s.post(f"{API}/eventmap/events/{evs[0]}/races", json={"name": "TEST_NoTrack"}).json()
    ST["notrack"] = nr["id"]
    r = s.post(f"{API}/eventmap/races/{nr['id']}/preview")
    assert r.status_code == 400, r.text
    assert s.post(f"{API}/eventmap/races/{nr['id']}/videos").status_code == 400
    assert _state(s, evs[0])["rights"]["videos_remaining"] == ST["remaining0"]  # races/preview consume nothing


def test_race_video_versions_and_credits(org):
    s, oid, evs = org
    rid = ST["races"][0]
    used0 = (mdb.addon_usage.find_one({"org_id": oid, "product": "eventmap"}) or {}).get("videos_used", 0)
    r = s.post(f"{API}/eventmap/races/{rid}/videos")
    assert r.status_code == 200, r.text
    v1 = r.json()
    assert v1["race_id"] == rid and v1["race_name"] == "Maratona" and v1["title"] == "Maratona di Pisa" and v1["subtitle"] == "42K"
    assert v1["distance_display_m"] == 42195.0 and v1["date"] == "2026-12-13" and v1["version"] == 1
    assert v1["format"] == "16:9" and v1["duration"] == 15 and v1["speed"] == "fast" and v1["show_aid"] is False
    mid = (mdb.addon_usage.find_one({"org_id": oid, "product": "eventmap"}) or {}).get("videos_used", 0)
    assert mid == used0  # not consumed while queued
    done = _wait(s, v1["id"])
    assert done["status"] == "completed", done
    used1 = mdb.addon_usage.find_one({"org_id": oid, "product": "eventmap"})["videos_used"]
    assert used1 == used0 + 1
    assert _state(s, evs[0])["rights"]["videos_remaining"] == ST["remaining0"] - 1
    r2 = s.post(f"{API}/eventmap/races/{rid}/videos")
    assert r2.status_code == 200 and r2.json()["version"] == 2
    done2 = _wait(s, r2.json()["id"])
    assert done2["status"] == "completed", done2
    assert mdb.addon_usage.find_one({"org_id": oid, "product": "eventmap"})["videos_used"] == used0 + 2
    d = _state(s, evs[0])
    vids = {v["id"]: v for v in d["videos"]}
    assert v1["id"] in vids and r2.json()["id"] in vids and vids[v1["id"]]["status"] == "completed"
    assert vids[v1["id"]]["race_label"] == "Maratona"
    ST["v1"], ST["v2"] = v1["id"], r2.json()["id"]


def test_download_name(org):
    s, _, _ = org
    r = s.get(f"{API}/eventmap/videos/{ST['v1']}/file?download=1")
    assert r.status_code == 200 and r.content[4:8] == b"ftyp"
    cd = r.headers["content-disposition"]
    assert cd.startswith("attachment") and "Maratona" in cd and "16x9-15s" in cd, cd
    cd2 = s.get(f"{API}/eventmap/videos/{ST['v2']}/file?download=1").headers["content-disposition"]
    assert "-v2.mp4" in cd2, cd2


def test_legacy_video_endpoint(org):
    s, _, evs = org
    r = s.post(f"{API}/eventmap/events/{evs[0]}/videos", json={"track_id": ST["t1"], "style": "dark", "format": "9:16", "duration": 15, "music": None})
    assert r.status_code == 200, r.text
    v = _wait(s, r.json()["id"])
    assert v["status"] == "completed", v
    lbl = {x["id"]: x["race_label"] for x in _state(s, evs[0])["videos"]}[v["id"]]
    assert lbl in ("pisa_run", "Maratona"), lbl  # label from race linked to track


def test_delete_race_keeps_tracks_and_videos(org):
    s, _, evs = org
    rid = ST["races"][0]
    assert s.delete(f"{API}/eventmap/races/{rid}").status_code == 200
    d = _state(s, evs[0])
    assert rid not in [x["id"] for x in d["races"]]
    assert ST["t1"] in [t["id"] for t in d["tracks"]]
    vids = {v["id"]: v for v in d["videos"]}
    assert ST["v1"] in vids and vids[ST["v1"]]["race_label"] == "Maratona"
    assert s.get(f"{API}/eventmap/videos/{ST['v1']}/file").status_code == 200
    assert s.delete(f"{API}/eventmap/races/{rid}").status_code == 404


# --- multiple tracks without races -> unassigned + from-tracks ---
def test_from_tracks(org):
    s, _, evs = org
    e = evs[1]
    a = _up(s, e, GPX, "Maratona.gpx").json()["id"]
    b = _up(s, e, GPX2, "Mezza.gpx").json()["id"]
    d = _state(s, e)
    assert d["races"] == [] and set(d["unassigned_tracks"]) == {a, b}, (d["races"], d["unassigned_tracks"])
    r = s.post(f"{API}/eventmap/events/{e}/races/from-tracks")
    assert r.status_code == 200, r.text
    cr = r.json()["created"]
    assert sorted(x["name"] for x in cr) == ["Maratona", "Mezza"] and {x["track_id"] for x in cr} == {a, b}
    d = _state(s, e)
    assert len(d["races"]) == 2 and d["unassigned_tracks"] == []
    assert s.post(f"{API}/eventmap/events/{e}/races/from-tracks").json()["created"] == []
    assert mdb.eventmap_tracks.count_documents({"event_id": e}) == 2  # no GPX duplication
