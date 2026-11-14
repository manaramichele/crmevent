# Event Map "Logo evento": upload PNG logo, read image, preview with/without logo, video with logo (1 x 15s render + frame check)
# Uses demo org TEST_EventMap Org (kept) + a temporary TEST_ org (other-org / not-active checks), deleted at the end.
import io
import os
import subprocess
import tempfile
import time
import uuid

import imageio_ffmpeg
import pytest
import requests
from PIL import Image

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
SA = ("manara.michele.pro@gmail.com", "CrmEvent2026!")
DEMO = ("test_em_1794651032@example.com", "TestEventMap2026!")
EID, TID, OLD_LOGO = "87d6098128cc4feda081e8a7de01b32f", "7e5c4f419d704699a99aab6b6f6a94b7", "8666f51365544e129a5d7e23996371b7"
LOGO_PNG = "/tmp/test_logo.png"
ST = {}


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return s


def _png(color=(255, 0, 0, 255), size=(200, 100)):
    b = io.BytesIO()
    Image.new("RGBA", size, color).save(b, "PNG")
    return b.getvalue()


@pytest.fixture(scope="module")
def demo():
    return _login(*DEMO)


@pytest.fixture(scope="module")
def other():
    s = requests.Session()
    em = f"test_emlogo_{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{API}/auth/register-organization", json={"nome": "TEST", "cognome": "Logo", "email": em, "password": "TestEventMap2026!",
                                                          "org_name": f"TEST_EMLogo {uuid.uuid4().hex[:4]}", "telefono": "+393471234567", "accept_terms": True})
    assert r.status_code in (200, 201), r.text
    oid = s.get(f"{API}/auth/me").json()["org_id"]
    open("/tmp/em_logo_org.txt", "w").write(oid)
    yield s
    sa = _login(*SA)
    from pymongo import MongoClient
    name = (MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))["test_database"].organizations.find_one({"id": oid}) or {}).get("nome")
    assert (name or "").upper().startswith("TEST_"), name
    d = sa.delete(f"{API}/platform/organizations/{oid}", json={"confirm_name": name})
    print("cleanup org", oid, d.status_code, d.text[:200])


# --- upload ---
def test_upload_png_transparent(demo):
    r = demo.post(f"{API}/eventmap/events/{EID}/logos", files={"file": ("TEST_logo.png", open(LOGO_PNG, "rb"), "image/png")})
    assert r.status_code == 200, r.text
    d = r.json()
    assert isinstance(d["id"], str) and d["width"] == 800 and d["height"] == 300 and d["transparent"] is True
    assert "storage" not in d and "org_id" not in d
    ST["lid"] = d["id"]


def test_upload_rejects_jpeg(demo):
    b = io.BytesIO(); Image.new("RGB", (50, 50), "blue").save(b, "JPEG")
    r = demo.post(f"{API}/eventmap/events/{EID}/logos", files={"file": ("fake.png", b.getvalue(), "image/png")})
    assert r.status_code == 400, r.text


def test_upload_rejects_text(demo):
    r = demo.post(f"{API}/eventmap/events/{EID}/logos", files={"file": ("x.png", b"not an image", "image/png")})
    assert r.status_code == 400


def test_upload_rejects_over_5mb(demo):
    r = demo.post(f"{API}/eventmap/events/{EID}/logos", files={"file": ("big.png", _png() + os.urandom(5 * 1024 * 1024), "image/png")})
    assert r.status_code == 400 and "5 MB" in r.text, r.text


def test_upload_not_active_403_and_other_org_404(other):
    ev = other.post(f"{API}/events", json={"nome": "TEST_Logo Event", "data_inizio": "2026-12-13"}).json()
    ST["oev"] = ev["id"]
    r = other.post(f"{API}/eventmap/events/{ev['id']}/logos", files={"file": ("l.png", _png(), "image/png")})
    assert r.status_code == 403, r.text
    r = other.post(f"{API}/eventmap/events/{EID}/logos", files={"file": ("l.png", _png(), "image/png")})
    assert r.status_code == 404


# --- read ---
def test_event_state_lists_logos(demo):
    d = demo.get(f"{API}/eventmap/events/{EID}").json()
    ids = [l["id"] for l in d["logos"]]
    assert ST["lid"] in ids and OLD_LOGO in ids
    assert all("storage" not in l for l in d["logos"])
    assert d["event"]["has_logo"] is False


def test_logo_image_png(demo):
    r = demo.get(f"{API}/eventmap/events/{EID}/logos/{ST['lid']}/image")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content[:4] == b"\x89PNG"
    assert Image.open(io.BytesIO(r.content)).size == (800, 300)


def test_logo_image_event_404_without_anagrafica_logo(demo):
    assert demo.get(f"{API}/eventmap/events/{EID}/logos/event/image").status_code == 404


def test_logo_image_unknown_404(demo):
    assert demo.get(f"{API}/eventmap/events/{EID}/logos/nope123/image").status_code == 404


def test_other_org_cannot_read_logo(other):
    assert other.get(f"{API}/eventmap/events/{EID}/logos/{ST['lid']}/image").status_code == 404
    assert other.get(f"{API}/eventmap/events/{ST['oev']}/logos/{ST['lid']}/image").status_code == 404


def test_event_anagrafica_logo_served(other):
    up = other.post(f"{API}/upload", files={"file": ("TEST_ev_logo.png", _png((0, 0, 255, 255)), "image/png")})
    assert up.status_code == 200, up.text
    ev = other.post(f"{API}/events", json={"nome": "TEST_Logo Event 2", "data_inizio": "2026-12-13", "logo_url": up.json()["url"]}).json()
    st = other.get(f"{API}/eventmap/events/{ev['id']}").json()
    assert st["event"]["has_logo"] is True
    r = other.get(f"{API}/eventmap/events/{ev['id']}/logos/event/image")
    assert r.status_code == 200 and r.content[:4] == b"\x89PNG"


# --- preview ---
def _tr_region(jpg):
    im = Image.open(io.BytesIO(jpg)).convert("RGB")
    W, H = im.size
    return im, im.crop((int(W * 0.6), 0, W, int(H * 0.2)))


def _whiteish(region):
    px = list(region.getdata())
    return sum(1 for p in px if min(p) > 200) / len(px)


@pytest.mark.parametrize("fmt", ["9:16", "1:1", "16:9"])
def test_preview_with_and_without_logo(demo, fmt):
    a = demo.post(f"{API}/eventmap/tracks/{TID}/preview", json={"style": "dark", "format": fmt, "logo": ST["lid"]}, timeout=120)
    b = demo.post(f"{API}/eventmap/tracks/{TID}/preview", json={"style": "dark", "format": fmt, "logo": None}, timeout=120)
    assert a.status_code == 200 and b.status_code == 200, (a.text[:200], b.text[:200])
    assert a.headers["content-type"] == "image/jpeg" and a.content[:2] == b"\xff\xd8"
    _, ra = _tr_region(a.content)
    _, rb = _tr_region(b.content)
    wa, wb = _whiteish(ra), _whiteish(rb)
    print(fmt, "white ratio with/without logo", wa, wb)
    assert wa > wb + 0.1  # logo box (white rounded rect) present top-right only with logo
    open(f"/tmp/em_prev_{fmt.replace(':', 'x')}.jpg", "wb").write(a.content)


def test_preview_unknown_logo_404(demo):
    r = demo.post(f"{API}/eventmap/tracks/{TID}/preview", json={"style": "dark", "format": "9:16", "logo": "unknownid"}, timeout=60)
    assert r.status_code == 404


# --- video ---
def test_video_unknown_logo_404(demo):
    r = demo.post(f"{API}/eventmap/events/{EID}/videos", json={"track_id": TID, "duration": 15, "format": "9:16", "logo": "unknownid"})
    assert r.status_code == 404, r.text


def test_video_with_logo_frames(demo):
    before = demo.get(f"{API}/eventmap/events/{EID}").json()["rights"]
    r = demo.post(f"{API}/eventmap/events/{EID}/videos", json={"track_id": TID, "duration": 15, "format": "1:1", "style": "dark", "music": "sportiva", "logo": ST["lid"]})
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["logo"] == ST["lid"] and v["status"] == "queued"
    vid = v["id"]
    open("/tmp/em_logo_vid.txt", "w").write(vid)
    for _ in range(80):
        time.sleep(3)
        s = demo.get(f"{API}/eventmap/videos/{vid}").json()
        if s["status"] in ("completed", "error"):
            break
    assert s["status"] == "completed", s
    assert s["logo"] == ST["lid"]
    after = demo.get(f"{API}/eventmap/events/{EID}").json()["rights"]
    assert after["videos_used"] == before["videos_used"] + 1
    f = demo.get(f"{API}/eventmap/videos/{vid}/file")
    assert f.status_code == 200 and f.headers["content-type"] == "video/mp4"
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    with tempfile.TemporaryDirectory() as tmp:
        mp4 = os.path.join(tmp, "v.mp4"); open(mp4, "wb").write(f.content)
        open("/tmp/em_logo_video.mp4", "wb").write(f.content)
        for t in (0.3, 7.5, 14.7):
            out = f"/tmp/em_frame_{t}.png"
            subprocess.run([ff, "-y", "-ss", str(t), "-i", mp4, "-frames:v", "1", out], capture_output=True, check=True)
            im = Image.open(out).convert("RGB")
            W, H = im.size
            reg = im.crop((int(W * 0.6), 0, W, int(H * 0.2)))
            w = _whiteish(reg)
            print("frame", t, im.size, "white ratio top-right", w)
            assert w > 0.15, f"logo box not detected at t={t}"
