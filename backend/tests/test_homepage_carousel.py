# Marketing → Home Page carousel (iteration 174): public carousel, SA settings/logos, publish/exclude, auto_new, webp logos, auth
import io, os, uuid, time
import pytest, requests
from PIL import Image
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env"); load_dotenv("/app/backend/.env")
BASE = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = BASE + "/api"
SA_EMAIL, SA_PWD = "manara.michele.pro@gmail.com", "CrmEvent2026!"
DEFAULT_TITLE = "Scelto dai migliori organizzatori di eventi"
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
TAG = uuid.uuid4().hex[:5]


def _login(email, pwd):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pwd})
    assert r.status_code == 200, r.text
    s.headers["Authorization"] = f"Bearer {s.cookies.get('access_token')}"
    return s


def _png(w, h, color):
    b = io.BytesIO(); Image.new("RGB", (w, h), color).save(b, "PNG"); return b.getvalue()


@pytest.fixture(scope="module")
def sa():
    return _login(SA_EMAIL, SA_PWD)


@pytest.fixture(scope="module")
def org(sa):
    email = f"test_hp_{TAG}@crmevent-test.it"
    r = requests.post(f"{API}/auth/register-organization", json={"nome": "TEST", "cognome": "HP", "email": email, "password": "TestHP2026!",
                                                                 "org_name": f"TEST_HP Org {TAG}", "telefono": "+393331234567", "accept_terms": True})
    assert r.status_code == 200, r.text
    u = mdb.users.find_one({"email": email}, {"_id": 0, "user_id": 1, "org_id": 1})
    adm = _login(email, "TestHP2026!")
    st = {"adm": adm, "uid": u["user_id"], "oid": u["org_id"], "events": [], "files": []}
    yield st
    for eid in st["events"]:
        adm.delete(f"{API}/events/{eid}")
        mdb.homepage_logo_cache.delete_one({"_id": eid})
    for fid in st["files"]:
        mdb.files.delete_one({"id": fid})
    sa.put(f"{API}/homepage/settings", json={"carousel_enabled": True, "carousel_title": DEFAULT_TITLE, "auto_new": False})
    mdb.users.delete_one({"user_id": u["user_id"]}); mdb.organizations.delete_one({"id": u["org_id"]})
    mdb.subscriptions.delete_many({"org_id": u["org_id"]}); mdb.memberships.delete_many({"user_id": u["user_id"]})


def _upload(st, w, h, color):
    r = st["adm"].post(f"{API}/upload", files={"file": (f"logo_{w}x{h}.png", _png(w, h, color), "image/png")})
    assert r.status_code == 200, r.text
    st["files"].append(r.json()["id"]); return r.json()["url"]


def _event(st, nome, logo):
    r = st["adm"].post(f"{API}/events", json={"nome": nome, "logo_url": logo})
    assert r.status_code == 200, r.text
    st["events"].append(r.json()["id"]); return r.json()["id"]


def _pub():
    r = requests.get(f"{API}/public/home-carousel", params={"_": time.time()})
    assert r.status_code == 200
    return r.json()


class TestHomepageCarousel:
    def test_auth_required(self, org):
        for m, p, kw in [("get", "/homepage/settings", {}), ("put", "/homepage/settings", {"json": {"carousel_enabled": True, "carousel_title": "abc", "auto_new": False}}),
                         ("get", "/homepage/logos", {}), ("post", "/homepage/logos/x", {"json": {"status": "approved"}})]:
            assert getattr(requests, m)(f"{API}{p}", **kw).status_code == 401
            assert getattr(org["adm"], m)(f"{API}{p}", **kw).status_code == 403

    def test_public_shape(self):
        d = _pub()
        assert set(d) == {"enabled", "title", "logos"} and isinstance(d["logos"], list)

    def test_settings_validation(self, sa):
        assert sa.put(f"{API}/homepage/settings", json={"carousel_enabled": True, "carousel_title": "ab", "auto_new": False}).status_code == 422
        assert sa.post(f"{API}/homepage/logos/nonexistent", json={"status": "approved"}).status_code == 404
        assert sa.post(f"{API}/homepage/logos/nonexistent", json={"status": "bogus"}).status_code == 422

    def test_flow(self, sa, org):
        s = sa.put(f"{API}/homepage/settings", json={"carousel_enabled": True, "carousel_title": DEFAULT_TITLE, "auto_new": False}).json()
        assert s["auto_new"] is False
        z = _event(org, f"zeta TEST_{TAG}", _upload(org, 400, 400, "red"))
        a = _event(org, f"Alfa TEST_{TAG}", _upload(org, 1600, 400, "blue"))
        b = _event(org, f"beta TEST_{TAG}", _upload(org, 300, 900, "green"))
        ext = _event(org, f"Gamma TEST_{TAG}", "https://example.com/logo.png")
        rows = {r["id"]: r for r in sa.get(f"{API}/homepage/logos").json()}
        for e in (z, a, b):
            assert rows[e]["status"] == "pending" and rows[e]["valid"] is True and rows[e]["org_nome"] == f"TEST_HP Org {TAG}"
        assert rows[ext]["valid"] is False
        assert requests.get(f"{API}/public/home-logos/{z}.webp").status_code == 404
        pv = requests.get(f"{API}/public/home-logos/{z}.webp?preview=1")
        assert pv.status_code == 200 and pv.headers["content-type"] == "image/webp"
        assert z not in [l["id"] for l in _pub()["logos"]]
        # organizer cannot self-publish via extra field
        org["adm"].put(f"{API}/events/{z}", json={"homepage_logo": {"status": "approved"}})
        assert mdb.events.find_one({"id": z}).get("homepage_logo") is None
        # publish
        for e in (z, a, b):
            assert sa.post(f"{API}/homepage/logos/{e}", json={"status": "approved"}).json() == {"ok": True}
        logos = [l for l in _pub()["logos"] if TAG in l["name"]]
        assert [l["id"] for l in logos] == [a, b, z]
        assert set(logos[0]) == {"id", "name", "src"}
        # external logo cannot be published (not in public list even if approved)
        sa.post(f"{API}/homepage/logos/{ext}", json={"status": "approved"})
        assert ext not in [l["id"] for l in _pub()["logos"]]
        # webp sizes & cache
        for e, (mw, mh) in ((z, (320, 320)), (a, (640, 160)), (b, (320 * 0 + 107, 320))):
            r = requests.get(f"{BASE}{next(l['src'] for l in logos if l['id'] == e)}")
            assert r.status_code == 200 and r.headers["content-type"] == "image/webp"
            # preview ingress rewrites Cache-Control to no-store; verify the header the app itself emits
            loc = requests.get(f"http://localhost:8001{next(l['src'] for l in logos if l['id'] == e)}")
            assert "max-age=604800" in loc.headers.get("cache-control", ""), loc.headers
            im = Image.open(io.BytesIO(r.content)); assert im.format == "WEBP" and im.width <= 640 and im.height <= 320
            print(e, im.size)
        # change logo -> new ?v=
        old_src = next(l["src"] for l in logos if l["id"] == z)
        assert org["adm"].put(f"{API}/events/{z}", json={"logo_url": _upload(org, 800, 200, "yellow")}).status_code == 200
        new_src = next(l["src"] for l in _pub()["logos"] if l["id"] == z)
        assert new_src != old_src
        im = Image.open(io.BytesIO(requests.get(f"{BASE}{new_src}").content)); assert im.size == (640, 160)
        # exclude
        sa.post(f"{API}/homepage/logos/{b}", json={"status": "excluded"})
        assert b not in [l["id"] for l in _pub()["logos"]]
        assert requests.get(f"{API}/public/home-logos/{b}.webp").status_code == 404
        sa.put(f"{API}/homepage/settings", json={"carousel_enabled": True, "carousel_title": DEFAULT_TITLE, "auto_new": True})
        assert b not in [l["id"] for l in _pub()["logos"]]
        # auto_new: new event auto-published, older pending stays pending
        p_old = _event(org, f"Delta TEST_{TAG}", _upload(org, 200, 200, "black"))
        mdb.events.update_one({"id": p_old}, {"$set": {"created_at": "2020-01-01T00:00:00+00:00"}})
        n = _event(org, f"epsilon TEST_{TAG}", _upload(org, 200, 200, "purple"))
        ids = [l["id"] for l in _pub()["logos"]]
        assert n in ids and p_old not in ids
        rows = {r["id"]: r for r in sa.get(f"{API}/homepage/logos").json()}
        assert rows[n]["status"] == "published" and rows[p_old]["status"] == "pending" and rows[b]["status"] == "excluded"
        # toggling auto_new off and on again resets auto_since
        sa.put(f"{API}/homepage/settings", json={"carousel_enabled": True, "carousel_title": DEFAULT_TITLE, "auto_new": False})
        assert n not in [l["id"] for l in _pub()["logos"]]
        # reset to default (null) status
        sa.post(f"{API}/homepage/logos/{a}", json={"status": None})
        assert a not in [l["id"] for l in _pub()["logos"]]
        sa.post(f"{API}/homepage/logos/{a}", json={"status": "approved"})
        # disabled carousel + title
        sa.put(f"{API}/homepage/settings", json={"carousel_enabled": False, "carousel_title": f"TEST_ Titolo {TAG}", "auto_new": False})
        d = _pub(); assert d["enabled"] is False and d["logos"] == [] and d["title"] == f"TEST_ Titolo {TAG}"
        g = sa.get(f"{API}/homepage/settings").json(); assert g["carousel_title"] == f"TEST_ Titolo {TAG}" and "_id" not in g
        sa.put(f"{API}/homepage/settings", json={"carousel_enabled": True, "carousel_title": DEFAULT_TITLE, "auto_new": False})
        # delete event removes it
        assert org["adm"].delete(f"{API}/events/{z}").status_code == 200
        assert z not in [l["id"] for l in _pub()["logos"]]
        assert requests.get(f"{API}/public/home-logos/{z}.webp").status_code == 404
        assert z not in {r["id"] for r in sa.get(f"{API}/homepage/logos").json()}
