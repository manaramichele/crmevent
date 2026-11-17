# Control Room Phase 2 retest of iteration_168 fixes: org context for collaboratore, PUT merge semantics, presence kind check, checkout admin-only
import os
import pytest, requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
API = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/") + "/api"
PWD = "TestCR2026!"
ORG_A = "e2356cc12b95447eb15b53d5aad01d32"
EV_A = "08e8a867893f4e2b835e2d43dd4fe65d"
OPS = f"{API}/controlroom/events/{EV_A}/ops"


def _login(email, org=None):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": PWD})
    if r.status_code != 200:
        pytest.skip(f"login failed {email}: {r.status_code}")
    tok = s.cookies.get("access_token")
    if tok:
        s.headers["Authorization"] = f"Bearer {tok}"
    if org:
        s.headers["X-Org-Id"] = org
    return s


@pytest.fixture(scope="module")
def A():
    return _login("test_cr_a@crmevent-test.it")


@pytest.fixture(scope="module")
def C():
    return _login("test_cr_c@crmevent-test.it", ORG_A)


@pytest.fixture(scope="module")
def C_noorg():
    return _login("test_cr_c@crmevent-test.it")


@pytest.fixture(scope="module")
def created(A):
    items = []
    yield items
    for kind, oid in reversed(items):
        A.delete(f"{OPS}/{kind}/{oid}")


# Collaboratore org context on Phase-1 endpoints
class TestCollabOrgContext:
    def test_events_list_org_a(self, C):
        r = C.get(f"{API}/controlroom/events")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["can_purchase"] is False
        ids = [e["id"] for e in d["events"]]
        assert EV_A in ids, d
        assert next(e for e in d["events"] if e["id"] == EV_A)["active"] is True

    def test_status_org_a(self, C):
        r = C.get(f"{API}/controlroom/events/{EV_A}/status")
        assert r.status_code == 200, r.text
        assert r.json()["active"] is True

    def test_without_header_primary_org(self, C_noorg):
        r = C_noorg.get(f"{API}/controlroom/events")
        assert r.status_code == 200
        assert EV_A not in [e["id"] for e in r.json()["events"]]

    def test_collab_writes_403(self, C):
        d = C.get(OPS).json()
        assert d["perms"]["edit"] is False
        assert C.post(f"{OPS}/posts", json={"nome": "TEST_x"}).status_code == 403
        if d["posts"]:
            p = d["posts"][0]
            assert C.put(f"{OPS}/posts/{p['id']}", json={"nome": "TEST_hack", "version": p["version"]}).status_code == 403
            assert C.delete(f"{OPS}/posts/{p['id']}").status_code == 403
        if d["resources"]:
            x = d["resources"][0]
            assert C.post(f"{OPS}/resources/{x['id']}/presence", json={"presente": True}).status_code == 403
            assert C.patch(f"{OPS}/resources/{x['id']}/status", json={"stato": "impegnato", "version": x["version"]}).status_code == 403

    def test_checkout_admin_only(self, C):
        r = C.post(f"{API}/controlroom/events/{EV_A}/checkout", json={"origin_url": "https://x.it"})
        assert r.status_code == 403, r.text

    def test_fake_org_header(self):
        s = _login("test_cr_c@crmevent-test.it", "nonexistent_org_id_xyz")
        r = s.get(f"{API}/controlroom/events")
        assert r.status_code in (200, 403), r.text
        if r.status_code == 200:
            assert EV_A not in [e["id"] for e in r.json()["events"]]


# PUT merge semantics + presence kind check
class TestMergeAndPresence:
    def test_put_partial_keeps_fields(self, A, created):
        r = A.post(f"{OPS}/posts", json={"nome": "TEST_Merge", "codice": "TM1", "categoria": "ristoro", "km": 3, "lat": 45.3, "lng": 9.3, "previsti": 4, "note": "keep"})
        assert r.status_code == 200, r.text
        p = r.json(); created.append(("posts", p["id"]))
        r = A.put(f"{OPS}/posts/{p['id']}", json={"nome": "TEST_Merge2", "version": 1})
        assert r.status_code == 200, r.text
        g = next(x for x in A.get(OPS).json()["posts"] if x["id"] == p["id"])
        assert g["nome"] == "TEST_Merge2" and g["codice"] == "TM1" and g["categoria"] == "ristoro"
        assert g["km"] == 3 and g["lat"] == 45.3 and g["previsti"] == 4 and g["note"] == "keep" and g["version"] == 2
        # explicit null clears
        r = A.put(f"{OPS}/posts/{p['id']}", json={"note": None, "version": 2})
        assert r.status_code == 200
        g = next(x for x in A.get(OPS).json()["posts"] if x["id"] == p["id"])
        assert g["note"] is None and g["codice"] == "TM1"

    def test_put_partial_resource_keeps_gps(self, A, created):
        r = A.post(f"{OPS}/resources", json={"kind": "mezzo", "tipologia": "ambulanza", "codice": "TEST_AMBM", "gps_device_id": "DEVM", "gps_device_type": "tracker", "targa": "AB123"})
        assert r.status_code == 200, r.text
        m = r.json(); created.append(("resources", m["id"]))
        r = A.put(f"{OPS}/resources/{m['id']}", json={"note": "n1", "version": 1})
        assert r.status_code == 200, r.text
        g = next(x for x in A.get(OPS).json()["resources"] if x["id"] == m["id"])
        assert g["codice"] == "TEST_AMBM" and g["targa"] == "AB123" and g["tipologia"] == "ambulanza"
        assert (g.get("gps") or {}).get("device_id") == "DEVM", g.get("gps")
        assert g["note"] == "n1"
        # presence on mezzo -> 404
        assert A.post(f"{OPS}/resources/{m['id']}/presence", json={"presente": True}).status_code == 404

    def test_presence_squadra_404_persona_ok(self, A, created):
        r = A.post(f"{OPS}/resources", json={"kind": "squadra", "nome": "TEST_SqP"})
        sq = r.json(); created.append(("resources", sq["id"]))
        assert A.post(f"{OPS}/resources/{sq['id']}/presence", json={"presente": True}).status_code == 404
        r = A.post(f"{OPS}/resources", json={"kind": "persona", "nome": "TEST_PersP"})
        pe = r.json(); created.append(("resources", pe["id"]))
        assert A.post(f"{OPS}/resources/{pe['id']}/presence", json={"presente": True}).status_code == 200
        g = next(x for x in A.get(OPS).json()["resources"] if x["id"] == pe["id"])
        assert g["presente"] is True

    def test_put_wrong_version_409(self, A, created):
        pid = next(o for k, o in created if k == "posts")
        assert A.put(f"{OPS}/posts/{pid}", json={"nome": "x", "version": 999}).status_code == 409
        assert A.put(f"{OPS}/posts/{pid}", json={"nome": "x"}).status_code == 409
