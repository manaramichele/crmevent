# Promo Reels campaign (Marketing → Email & Brevo → Video): SA list, static media, RBAC, meta/timeline validation, render versions
import copy
import os
import re
import subprocess
import tempfile
import time
import pytest
import requests
import imageio_ffmpeg

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
SA = {"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"}
ORG = {"email": "demo.crmevent@gmail.com", "password": "DemoCrm#2026pv"}
SLUGS = ["presentazione-45", "eventi-15", "staff-15", "sponsor-15", "planner-15", "map-15", "organizzazione-15"]
FF = imageio_ffmpeg.get_ffmpeg_exe()


def login(c):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=c)
    if r.status_code != 200:
        pytest.skip(f"login failed {c['email']}: {r.status_code}")
    return s


@pytest.fixture(scope="module")
def sa():
    return login(SA)


@pytest.fixture(scope="module")
def snapshot(sa):
    data = sa.get(f"{BASE_URL}/api/promo-reels").json()
    snap = {r["slug"]: copy.deepcopy(r) for r in data["reels"]}
    yield snap
    # restore meta + timeline + current version
    for slug, r in snap.items():
        sa.put(f"{BASE_URL}/api/promo-reels/{slug}", json={k: r.get(k) for k in ("title", "description", "hashtags", "publish_status", "publish_date", "link_instagram", "link_facebook", "link_youtube")})
        sa.put(f"{BASE_URL}/api/promo-reels/{slug}/timeline", json=r["timeline"])
        sa.post(f"{BASE_URL}/api/promo-reels/{slug}/versions/{slug}-v1/current")


def probe(content):
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(content)
        p = f.name
    out = subprocess.run([FF, "-hide_banner", "-i", p], capture_output=True, text=True).stderr
    os.unlink(p)
    return out


class TestList:
    def test_list(self, sa, snapshot):
        r = sa.get(f"{BASE_URL}/api/promo-reels")
        assert r.status_code == 200
        d = r.json()
        assert d["campaign"] == "CAMPAGNA CRMEVENT – PRESENTAZIONE PIATTAFORMA"
        assert [x["slug"] for x in d["reels"]] == SLUGS
        for x in d["reels"]:
            assert x["current_version_id"] == f"{x['slug']}-v1", x["slug"]
            v1 = next(v for v in x["versions"] if v["id"] == f"{x['slug']}-v1")
            assert v1["urls"]["mp4"] == f"/media/reels/{x['slug']}-v1.mp4"
            assert v1["urls"]["mp4_nomusic"] == f"/media/reels/{x['slug']}-v1-nomusic.mp4"
            assert v1["urls"]["cover"] == f"/media/reels/{x['slug']}-v1-cover.jpg"
            assert "_id" not in x
        assert len(d["music"]) > 0 and len(d["assets"]) > 0


class TestStatic:
    @pytest.mark.parametrize("slug", SLUGS)
    def test_static_media(self, slug):
        for suf, ct in ((".mp4", "video/mp4"), ("-nomusic.mp4", "video/mp4"), ("-cover.jpg", "image/jpeg")):
            r = requests.get(f"{BASE_URL}/media/reels/{slug}-v1{suf}")
            assert r.status_code == 200, (slug, suf)
            assert r.headers["content-type"].startswith(ct), (slug, suf, r.headers["content-type"])
            assert len(r.content) > 10000
        m = probe(requests.get(f"{BASE_URL}/media/reels/{slug}-v1.mp4").content)
        n = probe(requests.get(f"{BASE_URL}/media/reels/{slug}-v1-nomusic.mp4").content)
        assert "h264" in m and "1080x1920" in m, m
        assert "Audio:" in m, f"music version has no audio: {slug}"
        assert "Audio:" not in n, f"nomusic version has audio: {slug}"
        dur = re.search(r"Duration: (\d+):(\d+):([\d.]+)", m)
        secs = int(dur.group(2)) * 60 + float(dur.group(3))
        if slug == "presentazione-45":
            assert 40 <= secs <= 47, secs
        else:
            assert 14 <= secs <= 16, secs


class TestRBAC:
    def test_anonymous(self):
        for m, u in (("get", ""), ("put", "/eventi-15"), ("put", "/eventi-15/timeline"), ("post", "/eventi-15/render"),
                     ("post", "/eventi-15/versions/eventi-15-v1/current"), ("get", "/eventi-15/versions/eventi-15-v1/file/mp4")):
            r = getattr(requests, m)(f"{BASE_URL}/api/promo-reels{u}", json={})
            assert r.status_code in (401, 403), (m, u, r.status_code)

    def test_org_admin(self):
        s = login(ORG)
        for m, u in (("get", ""), ("put", "/eventi-15"), ("put", "/eventi-15/timeline"), ("post", "/eventi-15/render"),
                     ("post", "/eventi-15/versions/eventi-15-v1/current"), ("get", "/eventi-15/versions/eventi-15-v1/file/mp4")):
            r = getattr(s, m)(f"{BASE_URL}/api/promo-reels{u}", json={"title": "x"})
            assert r.status_code in (401, 403), (m, u, r.status_code)


class TestMeta:
    def test_update_meta(self, sa, snapshot):
        body = {"title": "TEST_Titolo", "description": "TEST_desc", "hashtags": "#test", "publish_status": "programmato", "publish_date": "2026-12-01",
                "link_instagram": "https://instagram.com/p/x", "link_facebook": "https://fb.com/x", "link_youtube": "https://youtu.be/x"}
        r = sa.put(f"{BASE_URL}/api/promo-reels/staff-15", json=body)
        assert r.status_code == 200
        g = next(x for x in sa.get(f"{BASE_URL}/api/promo-reels").json()["reels"] if x["slug"] == "staff-15")
        for k, v in body.items():
            assert g[k] == v, k

    def test_invalid_status(self, sa, snapshot):
        r = sa.put(f"{BASE_URL}/api/promo-reels/staff-15", json={"title": "x", "publish_status": "boh"})
        assert r.status_code == 422

    def test_unknown_slug(self, sa):
        assert sa.put(f"{BASE_URL}/api/promo-reels/nope", json={"title": "x"}).status_code == 404


class TestTimeline:
    def _tl(self, snapshot, slug="staff-15"):
        return copy.deepcopy(snapshot[slug]["timeline"])

    def test_unknown_asset(self, sa, snapshot):
        t = self._tl(snapshot); t["sections"][0]["scenes"][0]["asset"] = "../../server.py"
        assert sa.put(f"{BASE_URL}/api/promo-reels/staff-15/timeline", json=t).status_code == 422

    def test_invalid_crop(self, sa, snapshot):
        t = self._tl(snapshot); t["sections"][0]["scenes"][0]["crop"] = [0, 0, 10]
        assert sa.put(f"{BASE_URL}/api/promo-reels/staff-15/timeline", json=t).status_code == 422
        t["sections"][0]["scenes"][0]["crop"] = [-5, 0, 100, 100]
        assert sa.put(f"{BASE_URL}/api/promo-reels/staff-15/timeline", json=t).status_code == 422

    def test_unknown_music(self, sa, snapshot):
        t = self._tl(snapshot); t["music"] = "nonexistent"
        assert sa.put(f"{BASE_URL}/api/promo-reels/staff-15/timeline", json=t).status_code == 422

    def test_bad_hook_dur_type(self, sa, snapshot):
        t = self._tl(snapshot); t["hook"]["dur"] = "abc"
        r = sa.put(f"{BASE_URL}/api/promo-reels/staff-15/timeline", json=t)
        assert r.status_code == 422, f"non-numeric hook.dur -> {r.status_code}"

    def test_valid_edit(self, sa, snapshot):
        t = self._tl(snapshot); t["hook"]["text"] = "TEST_HOOK"
        r = sa.put(f"{BASE_URL}/api/promo-reels/staff-15/timeline", json=t)
        assert r.status_code == 200
        g = next(x for x in sa.get(f"{BASE_URL}/api/promo-reels").json()["reels"] if x["slug"] == "staff-15")
        assert g["timeline"]["hook"]["text"] == "TEST_HOOK"


class TestRender:
    def test_render_flow(self, sa, snapshot):
        r = sa.post(f"{BASE_URL}/api/promo-reels/eventi-15/render")
        assert r.status_code == 200, r.text
        v = r.json(); vid = v["id"]
        assert v["status"] == "queued" and v["version"] >= 2
        r2 = sa.post(f"{BASE_URL}/api/promo-reels/eventi-15/render")
        assert r2.status_code == 409
        seen, st = set(), None
        for _ in range(60):
            reel = next(x for x in sa.get(f"{BASE_URL}/api/promo-reels").json()["reels"] if x["slug"] == "eventi-15")
            cur = next(x for x in reel["versions"] if x["id"] == vid)
            st = cur["status"]; seen.add(st)
            if st in ("completed", "error"):
                break
            time.sleep(3)
        print("statuses seen", seen, cur.get("error"))
        assert st == "completed", cur
        assert reel["current_version_id"] == vid
        assert any(x["id"] == "eventi-15-v1" for x in reel["versions"])
        assert cur["urls"]["mp4"].startswith("/api/promo-reels/eventi-15/versions/")
        f = sa.get(f"{BASE_URL}/api/promo-reels/eventi-15/versions/{vid}/file/mp4")
        assert f.status_code == 200 and f.headers["content-type"].startswith("video/mp4") and len(f.content) > 10000
        info = probe(f.content)
        assert "1080x1920" in info and "h264" in info and "Audio:" in info
        d = sa.get(f"{BASE_URL}/api/promo-reels/eventi-15/versions/{vid}/file/mp4?download=1")
        assert "attachment" in d.headers.get("content-disposition", "")
        n = sa.get(f"{BASE_URL}/api/promo-reels/eventi-15/versions/{vid}/file/mp4_nomusic")
        assert n.status_code == 200 and "Audio:" not in probe(n.content)
        c = sa.get(f"{BASE_URL}/api/promo-reels/eventi-15/versions/{vid}/file/cover")
        assert c.status_code == 200 and c.headers["content-type"].startswith("image/jpeg")
        assert sa.get(f"{BASE_URL}/api/promo-reels/eventi-15/versions/{vid}/file/bogus").status_code == 404
        # v1 static redirect
        rr = sa.get(f"{BASE_URL}/api/promo-reels/eventi-15/versions/eventi-15-v1/file/mp4", allow_redirects=False)
        assert rr.status_code in (302, 307)
        s = sa.post(f"{BASE_URL}/api/promo-reels/eventi-15/versions/eventi-15-v1/current")
        assert s.status_code == 200
        reel = next(x for x in sa.get(f"{BASE_URL}/api/promo-reels").json()["reels"] if x["slug"] == "eventi-15")
        assert reel["current_version_id"] == "eventi-15-v1"
        assert sa.post(f"{BASE_URL}/api/promo-reels/eventi-15/versions/nope/current").status_code == 404
