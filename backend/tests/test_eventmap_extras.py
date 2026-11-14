# Event Map extras: custom date settings, speeds, aid stations (GPX detection + manual editor), elevation profile,
# preview (no credit), real video renders (duration/resolution/frames), credits on failure, org isolation.
import json
import os
import subprocess
import time
import uuid

import imageio_ffmpeg
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures")
OUT = "/tmp/em_extras"
os.makedirs(OUT, exist_ok=True)
mdb = MongoClient("mongodb://localhost:27017")["test_database"]  # preview DB only

OWNER = ("test_em_1794651032@example.com", "TestEventMap2026!")
SA = ("manara.michele.pro@gmail.com", "CrmEvent2026!")
OID = "4343e7742dd04ff8ad9d9157b34176ac"
EID = "87d6098128cc4feda081e8a7de01b32f"
STATE = {}
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return s


def _upload(s, name):
    with open(os.path.join(FIX, name), "rb") as f:
        r = s.post(f"{API}/eventmap/events/{EID}/tracks", files={"file": (name, f, "application/gpx+xml")})
    assert r.status_code == 200, r.text
    STATE.setdefault("tracks", []).append(r.json()["id"])
    return r.json()


def _used():
    u = mdb.addon_usage.find_one({"org_id": OID, "product": "eventmap"}) or {}
    return u.get("videos_used", 0)


def _wait(s, vid, timeout=420):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = s.get(f"{API}/eventmap/videos/{vid}").json()
        if v["status"] in ("completed", "error"):
            return v
        time.sleep(5)
    raise AssertionError(f"video timeout {vid}")


def _probe(path):
    p = subprocess.run([FFMPEG, "-i", path], capture_output=True, text=True)
    return p.stderr


@pytest.fixture(scope="module")
def owner():
    return _login(*OWNER)


@pytest.fixture(scope="module")
def sa():
    return _login(*SA)


@pytest.fixture(scope="module")
def other():
    s = requests.Session()
    em = f"test_emx_{uuid.uuid4().hex[:8]}@example.com"
    name = f"TEST_EMX Other {uuid.uuid4().hex[:4]}"
    r = s.post(f"{API}/auth/register-organization", json={"nome": "TEST", "cognome": "EMX", "email": em, "password": "TestEmx2026!",
                                                          "org_name": name, "telefono": "+393471234567", "accept_terms": True})
    assert r.status_code in (200, 201), r.text
    oid = s.get(f"{API}/auth/me").json()["org_id"]
    STATE["other"] = {"id": oid, "name": name}
    json.dump(STATE, open(os.path.join(OUT, "state.json"), "w"))
    yield s
    sa = _login(*SA)
    r = sa.delete(f"{API}/platform/organizations/{oid}", json={"confirm_name": name})
    print("cleanup other org", r.status_code, r.text[:200])


@pytest.fixture(scope="module")
def hill(owner):
    return _upload(owner, "hill_aid.gpx")


@pytest.fixture(scope="module")
def flat(owner):
    return _upload(owner, "pisa_run.gpx")


# --- options ---
def test_options_speeds(owner):
    d = owner.get(f"{API}/eventmap/options").json()
    assert [(x["key"], x["label"]) for x in d["speeds"]] == [("slow", "Lenta"), ("normal", "Normale"), ("fast", "Veloce")]


# --- grant videos (SA) ---
def test_grant_videos(owner, sa):
    r = sa.post(f"{API}/platform/addons/orgs/{OID}/grants", json={"product": "eventmap", "events_total": 1, "videos_total": 4, "note": "TEST_emx grant"})
    assert r.status_code in (200, 201), r.text
    rg = owner.get(f"{API}/eventmap/events/{EID}").json()["rights"]
    print("rights after grant", rg)
    assert rg["active"] and (rg["videos_remaining"] is None or rg["videos_remaining"] >= 3)


# --- GPX parsing: elevation + aid detection ---
def test_upload_hill(hill):
    assert hill["has_elevation"] is True
    for k in ("ele_min", "ele_max", "ele_gain"):
        assert isinstance(hill[k], (int, float)), k
    aid = hill["aid_detected"]
    assert [a["name"] for a in aid] == ["Ristoro Ponte", "Ristoro Arrivo"], aid
    assert abs(aid[0]["km"] - 1.07) < 0.05 and aid[0]["desc"] == "Acqua e sali"
    assert abs(aid[1]["km"] - 2.09) < 0.05
    wp = [w["name"] if isinstance(w, dict) else w for w in hill["waypoints"]]
    assert wp == ["Belvedere"], hill["waypoints"]


def test_upload_flat(flat):
    assert flat["has_elevation"] is False
    assert flat["aid_detected"] == []


# --- event state ---
def test_event_state(owner, hill):
    d = owner.get(f"{API}/eventmap/events/{EID}").json()
    ev = mdb.events.find_one({"id": EID})
    assert d["event"]["data_iso"] == (ev.get("data_inizio") or "")[:10]
    assert "date" in d["settings"]
    t = next(t for t in d["tracks"] if t["id"] == hill["id"])
    assert "preview" not in t and "storage" not in t
    assert [a["name"] for a in t["aid_stations"]] == ["Ristoro Ponte", "Ristoro Arrivo"]


# --- settings date ---
def test_settings_date(owner):
    before = mdb.events.find_one({"id": EID})["data_inizio"]
    r = owner.put(f"{API}/eventmap/events/{EID}/settings", json={"date": None})
    assert r.status_code == 200 and r.json()["date"] is None
    d = owner.get(f"{API}/eventmap/events/{EID}").json()
    assert d["event"]["data"] and d["settings"]["date"] is None
    r = owner.put(f"{API}/eventmap/events/{EID}/settings", json={"date": "20-12-2026"})
    assert r.status_code == 422
    r = owner.put(f"{API}/eventmap/events/{EID}/settings", json={"date": "2026-13-45"})
    print("impossible date status", r.status_code)
    STATE["bad_date_status"] = r.status_code
    r = owner.put(f"{API}/eventmap/events/{EID}/settings", json={"date": "2026-12-20"})
    assert r.status_code == 200 and r.json()["date"] == "2026-12-20"
    d = owner.get(f"{API}/eventmap/events/{EID}").json()
    assert d["event"]["data"] == "20 dicembre 2026" and d["settings"]["date"] == "2026-12-20"
    assert mdb.events.find_one({"id": EID})["data_inizio"] == before
    assert mdb.eventmap_settings.find_one({"org_id": OID, "event_id": EID})["date"] == "2026-12-20"


# --- aid stations editor ---
def test_aid_edit(owner, hill):
    tid = hill["id"]
    items = [{"name": "TEST_Manuale", "km": 1.5, "desc": "Gel", "source": "manual"},
             {"name": "Ristoro Ponte", "km": 1.07, "desc": "Acqua e sali", "source": "gpx"}]
    r = owner.put(f"{API}/eventmap/tracks/{tid}/aid-stations", json={"items": items})
    assert r.status_code == 200, r.text
    a = r.json()["aid_stations"]
    assert [x["km"] for x in a] == [1.07, 1.5] and all("lat" in x and "lon" in x for x in a)
    assert a[0]["source"] == "gpx" and a[1]["source"] == "manual"
    r = owner.put(f"{API}/eventmap/tracks/{tid}/aid-stations", json={"items": [{"name": "X", "km": 99, "desc": ""}]})
    assert r.status_code == 400
    r = owner.put(f"{API}/eventmap/tracks/{tid}/aid-stations", json={"items": []})
    assert r.status_code == 200 and r.json()["aid_stations"] == []
    t = next(t for t in owner.get(f"{API}/eventmap/events/{EID}").json()["tracks"] if t["id"] == tid)
    assert t["aid_stations"] == []
    # restore detected + one manual for video
    r = owner.put(f"{API}/eventmap/tracks/{tid}/aid-stations", json={"items": [
        {"name": "Ristoro Ponte", "km": 1.07, "desc": "Acqua e sali", "source": "gpx"},
        {"name": "Ristoro Arrivo", "km": 2.09, "desc": "", "source": "gpx"}]})
    assert r.status_code == 200


# --- preview ---
@pytest.mark.parametrize("speed,fmt,aid,ele", [("slow", "9:16", True, True), ("normal", "1:1", False, False), ("fast", "16:9", True, True)])
def test_preview(owner, hill, speed, fmt, aid, ele):
    u0 = _used()
    r = owner.post(f"{API}/eventmap/tracks/{hill['id']}/preview", json={"style": "dark", "format": fmt, "speed": speed, "show_aid": aid, "show_elevation": ele}, timeout=180)
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg", r.text[:200]
    open(os.path.join(OUT, f"preview_{speed}_{fmt.replace(':', 'x')}.jpg"), "wb").write(r.content)
    assert _used() == u0


def test_preview_flat_and_invalid(owner, flat):
    r = owner.post(f"{API}/eventmap/tracks/{flat['id']}/preview", json={"format": "16:9", "speed": "normal"}, timeout=180)
    assert r.status_code == 200
    open(os.path.join(OUT, "preview_flat.jpg"), "wb").write(r.content)
    r = owner.post(f"{API}/eventmap/tracks/{flat['id']}/preview", json={"speed": "turbo"})
    assert r.status_code == 400


# --- isolation ---
def test_isolation(other, hill, owner):
    tid = hill["id"]
    assert other.get(f"{API}/eventmap/events/{EID}").status_code == 404
    assert other.put(f"{API}/eventmap/events/{EID}/settings", json={"date": "2026-01-01"}).status_code == 404
    assert other.put(f"{API}/eventmap/tracks/{tid}/aid-stations", json={"items": []}).status_code == 404
    assert other.post(f"{API}/eventmap/tracks/{tid}/preview", json={}).status_code == 404
    assert other.post(f"{API}/eventmap/events/{EID}/videos", json={"track_id": tid}).status_code == 404
    assert mdb.eventmap_settings.find_one({"org_id": OID, "event_id": EID})["date"] == "2026-12-20"
    t = next(t for t in owner.get(f"{API}/eventmap/events/{EID}").json()["tracks"] if t["id"] == tid)
    assert len(t["aid_stations"]) == 2


# --- failed render keeps credits ---
def test_failed_render_no_credit(owner, flat):
    up = _upload(owner, "pisa_run.gpx")
    mdb.eventmap_tracks.update_one({"id": up["id"]}, {"$set": {"storage.path": f"eventmap/{OID}/missing/{uuid.uuid4().hex}.gpx", "storage.backend": "local"}})
    u0 = _used()
    rg0 = owner.get(f"{API}/eventmap/events/{EID}").json()["rights"]
    r = owner.post(f"{API}/eventmap/events/{EID}/videos", json={"track_id": up["id"], "format": "9:16", "duration": 15})
    assert r.status_code == 200, r.text
    v = _wait(owner, r.json()["id"], 120)
    STATE.setdefault("videos", []).append(v["id"])
    assert v["status"] == "error", v
    assert _used() == u0
    rg1 = owner.get(f"{API}/eventmap/events/{EID}").json()["rights"]
    assert rg1["videos_remaining"] == rg0["videos_remaining"], (rg0, rg1)


# --- real videos ---
CASES = [("hill", 15, "fast", "9:16", "sportiva", (1080, 1920)), ("hill", 30, "normal", "1:1", None, (1080, 1080)), ("flat", 60, "slow", "16:9", None, (1920, 1080))]


@pytest.mark.parametrize("which,dur,speed,fmt,music,res", CASES)
def test_video(owner, hill, flat, which, dur, speed, fmt, music, res):
    t = hill if which == "hill" else flat
    u0 = _used()
    r = owner.post(f"{API}/eventmap/events/{EID}/videos", json={"track_id": t["id"], "style": "dark", "format": fmt, "duration": dur, "music": music,
                                                                 "speed": speed, "show_aid": True, "show_elevation": True})
    assert r.status_code == 200, r.text
    d = r.json()
    STATE.setdefault("videos", []).append(d["id"])
    assert d["date"] == "2026-12-20" and d["speed"] == speed and d["show_aid"] is True
    assert d["show_elevation"] is (which == "hill")
    assert len(d["aid_stations"]) == (2 if which == "hill" else 0)
    v = _wait(owner, d["id"], 600)
    assert v["status"] == "completed", v
    assert _used() == u0 + 1
    f = owner.get(f"{API}/eventmap/videos/{d['id']}/file?download=1")
    assert f.status_code == 200 and f.headers["content-type"] == "video/mp4"
    p = os.path.join(OUT, f"{which}_{dur}.mp4")
    open(p, "wb").write(f.content)
    info = _probe(p)
    print(info[-800:])
    assert f"{res[0]}x{res[1]}" in info
    import re
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", info)
    secs = int(m.group(2)) * 60 + float(m.group(3))
    assert abs(secs - dur) < 0.6, secs
    assert ("Audio" in info) == bool(music)
    for frac in (0.1, 0.5, 0.85, 0.995):
        subprocess.run([FFMPEG, "-y", "-ss", f"{dur * frac:.2f}", "-i", p, "-frames:v", "1", "-q:v", "6",
                        os.path.join(OUT, f"{which}_{dur}_{int(frac * 100)}.jpg")], capture_output=True)


def test_zz_cleanup_tracks():
    json.dump(STATE, open(os.path.join(OUT, "state.json"), "w"))
    print("STATE", STATE)
