# Control Room Phase 2 (ops): access/permissions, sectors, posts, resources, staff import, presence, status, interventions, settings, concurrency
import os, uuid
import pytest, requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = BASE_URL + "/api"
PWD = "TestCR2026!"
ORG_A = "9bb535b289f74a2395a6114ff0e2f0b5"
EV_A = "09e1b85e1b774b79956a31fd139a60c8"
OPS = f"{API}/controlroom/events/{EV_A}/ops"


def _login(email, org=None):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": PWD})
    if r.status_code != 200:
        pytest.skip(f"login failed {email}: {r.status_code} {r.text[:200]}")
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
def B():
    return _login("test_cr_b@crmevent-test.it")


@pytest.fixture(scope="module")
def C():
    return _login("test_cr_c@crmevent-test.it", ORG_A)


@pytest.fixture(scope="module")
def created(A):
    items = []
    yield items
    for kind, oid in reversed(items):
        A.delete(f"{OPS}/{kind}/{oid}")


def state(s):
    r = s.get(OPS)
    assert r.status_code == 200, r.text
    return r.json()


def find(lst, oid):
    return next((x for x in lst if x["id"] == oid), None)


class TestAccess:
    def test_admin_state(self, A):
        d = state(A)
        for k in ("event", "settings", "sectors", "posts", "resources", "interventions", "kpi", "alerts", "routes", "perms", "rev"):
            assert k in d
        assert d["perms"]["edit"] is True and d["perms"]["contacts"] is True
        assert d["event"]["id"] == EV_A
        assert "_id" not in d["settings"] and "org_id" not in d["settings"]

    def test_route_gpx(self, A):
        r = A.get(f"{OPS}/route")
        assert r.status_code == 200, r.text
        rt = r.json()["route"]
        assert rt and len(rt["coordinates"]) > 2

    def test_rev(self, A):
        r = A.get(f"{OPS}/rev")
        assert r.status_code == 200 and isinstance(r.json()["rev"], int)

    def test_inactive_event_402(self, A):
        evs = A.get(f"{API}/controlroom/events").json()["events"]
        ina = next((e for e in evs if "Non attivo" in (e.get("nome") or "")), None)
        assert ina, [e.get("nome") for e in evs]
        assert ina["active"] is False
        r = A.get(f"{API}/controlroom/events/{ina['id']}/ops")
        assert r.status_code == 402, r.text

    def test_org_b_isolated(self, B):
        r = B.get(OPS)
        assert r.status_code == 404, r.text
        r = B.post(f"{OPS}/sectors", json={"nome": "TEST_hack"})
        assert r.status_code == 404, r.text

    def test_collab_readonly(self, C):
        d = state(C)
        assert d["perms"]["edit"] is False
        print("collab contacts perm:", d["perms"]["contacts"])
        assert C.post(f"{OPS}/sectors", json={"nome": "TEST_x"}).status_code == 403
        assert C.post(f"{OPS}/interventions", json={"titolo": "TEST_x"}).status_code == 403
        assert C.get(f"{OPS}/staff").status_code == 403
        if d["posts"]:
            p = d["posts"][0]
            assert C.patch(f"{OPS}/posts/{p['id']}/position", json={"lng": 9, "lat": 45, "version": p["version"]}).status_code == 403
        assert C.put(f"{OPS}/settings", json={"status": "in_corso", "version": d["settings"]["version"]}).status_code == 403

    def test_unauth(self):
        assert requests.get(OPS).status_code in (401, 403)


class TestSectorsPosts:
    def test_sector_and_post_flow(self, A, created):
        r = A.post(f"{OPS}/sectors", json={"nome": "TEST_Settore", "codice": "TS", "km_inizio": 1, "km_fine": 3, "telefono": "+39333111222"})
        assert r.status_code == 200, r.text
        sec = r.json(); created.append(("sectors", sec["id"]))
        assert A.post(f"{OPS}/sectors", json={"nome": "TEST_bad", "km_inizio": 5, "km_fine": 2}).status_code == 400
        r = A.post(f"{OPS}/posts", json={"nome": "TEST_Post", "codice": "TP1", "categoria": "ristoro", "sector_id": sec["id"], "km": 2,
                                         "lat": 45.1, "lng": 9.1, "previsti": 2})
        assert r.status_code == 200, r.text
        p = r.json(); created.append(("posts", p["id"]))
        assert p["lat"] == 45.1 and p["version"] == 1
        assert A.post(f"{OPS}/posts", json={"nome": "TEST_bad", "categoria": "nonexist"}).status_code == 400
        assert A.post(f"{OPS}/posts", json={"nome": "TEST_bad", "sector_id": "nope"}).status_code == 400
        d = state(A)
        sp = find(d["posts"], p["id"]); ss = find(d["sectors"], sec["id"])
        assert sp["presenti"] == 0 and sp["mancanti"] == 2
        assert ss["summary"]["postazioni"] == 1
        # position: stale -> 409, correct -> ok
        r = A.patch(f"{OPS}/posts/{p['id']}/position", json={"lng": 9.2, "lat": 45.2, "version": 99})
        assert r.status_code == 409, r.text
        r = A.patch(f"{OPS}/posts/{p['id']}/position", json={"lng": 9.2, "lat": 45.2, "version": 1})
        assert r.status_code == 200, r.text
        sp = find(state(A)["posts"], p["id"])
        assert sp["lat"] == 45.2 and sp["lng"] == 9.2 and sp["version"] == 2
        # edit stale -> 409; correct -> ok
        assert A.put(f"{OPS}/posts/{p['id']}", json={"nome": "TEST_Post2", "categoria": "ristoro", "version": 1}).status_code == 409
        r = A.put(f"{OPS}/posts/{p['id']}", json={**{k: sp[k] for k in ("codice", "categoria", "sector_id", "km", "lat", "lng", "previsti")}, "nome": "TEST_Post2", "version": 2})
        assert r.status_code == 200, r.text
        assert find(state(A)["posts"], p["id"])["nome"] == "TEST_Post2"
        # duplicate
        r = A.post(f"{OPS}/posts/{p['id']}/duplicate")
        assert r.status_code == 200, r.text
        dup = r.json(); created.append(("posts", dup["id"]))
        assert dup["nome"].endswith("(copia)") and dup["codice"] == "TP1-2"
        # delete dup
        assert A.delete(f"{OPS}/posts/{dup['id']}").status_code == 200
        assert find(state(A)["posts"], dup["id"]) is None
        assert A.delete(f"{OPS}/posts/{dup['id']}").status_code == 404
        created.remove(("posts", dup["id"]))
        pytest.shared = {"sec": sec["id"], "post": p["id"]}


class TestResources:
    def test_manual_resources(self, A, created):
        sh = getattr(pytest, "shared", {})
        r = A.post(f"{OPS}/resources", json={"kind": "persona", "nome": "TEST_Mario", "telefono": "+39333000111", "post_id": sh.get("post")})
        assert r.status_code == 200, r.text
        created.append(("resources", r.json()["id"]))
        assert A.post(f"{OPS}/resources", json={"kind": "persona"}).status_code == 400
        r = A.post(f"{OPS}/resources", json={"kind": "squadra", "nome": "TEST_Squadra"})
        assert r.status_code == 200, r.text; created.append(("resources", r.json()["id"]))
        r = A.post(f"{OPS}/resources", json={"kind": "mezzo", "tipologia": "ambulanza", "codice": "TEST_AMB9", "gps_device_id": "DEV123", "gps_device_type": "tracker"})
        assert r.status_code == 200, r.text
        amb = r.json(); created.append(("resources", amb["id"]))
        assert amb["gps"]["status"] == "non_collegato" and amb["gps"]["last_lat"] is None and amb.get("lat") is None
        r = A.post(f"{OPS}/resources", json={"kind": "mezzo", "tipologia": "polizia", "codice": "TEST_POL"})
        assert r.status_code == 400, r.text
        r = A.post(f"{OPS}/resources", json={"kind": "mezzo", "tipologia": "polizia", "codice": "TEST_POL", "autorizzazione_ente": True})
        assert r.status_code == 200, r.text; created.append(("resources", r.json()["id"]))
        assert A.post(f"{OPS}/resources", json={"kind": "mezzo", "tipologia": "carro", "codice": "X"}).status_code == 400
        # KPI ambulanze disponibili + status change
        k0 = state(A)["kpi"]
        r = A.patch(f"{OPS}/resources/{amb['id']}/status", json={"stato": "impegnato", "version": 1})
        assert r.status_code == 200, r.text
        assert A.patch(f"{OPS}/resources/{amb['id']}/status", json={"stato": "disponibile", "version": 1}).status_code == 409
        d = state(A); k1 = d["kpi"]
        assert k1["ambulanze_disponibili"] == k0["ambulanze_disponibili"] - 1
        assert k1["risorse_impegnate"] == k0["risorse_impegnate"] + 1
        r = A.patch(f"{OPS}/resources/{amb['id']}/status", json={"stato": "non_raggiungibile", "version": 2})
        assert r.status_code == 200
        d = state(A)
        assert d["kpi"]["non_raggiungibili"] == k0["non_raggiungibili"] + 1
        assert any(a["ref"] == ["resources", amb["id"]] for a in d["alerts"])
        # presence on manual persona
        pid = created[-4][1] if False else next(x["id"] for x in d["resources"] if x.get("nome") == "TEST_Mario")
        kv = d["kpi"]["volontari_presenti"]
        assert A.post(f"{OPS}/resources/{pid}/presence", json={"presente": True}).status_code == 200
        d = state(A)
        assert d["kpi"]["volontari_presenti"] == kv + 1
        if sh.get("post"):
            p = find(d["posts"], sh["post"])
            assert p["presenti"] == 1 and p["mancanti"] == 1 and p["presidio"] == "parziale"
        # edit persona resource
        x = find(d["resources"], pid)
        r = A.put(f"{OPS}/resources/{pid}", json={**x, "nome": "TEST_Mario2"})
        assert r.status_code == 200, r.text

    def test_staff_import_no_duplicates(self, A, created):
        r = A.get(f"{OPS}/staff")
        assert r.status_code == 200, r.text
        st = r.json()["staff"]
        free = [x for x in st if not x["in_control_room"]]
        used = [x for x in st if x["in_control_room"]]
        print("staff total", len(st), "free", len(free), "used", len(used))
        if used:
            r = A.post(f"{OPS}/resources/from-staff", json={"staff_ids": [used[0]["staff_id"]]})
            assert r.status_code == 200 and r.json()["added"] == 0
        if not free:
            pytest.skip("no free staff to import")
        sh = getattr(pytest, "shared", {})
        f = free[0]
        r = A.post(f"{OPS}/resources/from-staff", json={"staff_ids": [f["staff_id"]], "post_id": sh.get("post"), "caposquadra_staff_id": f["staff_id"]})
        assert r.status_code == 200 and r.json()["added"] == 1, r.text
        r = A.post(f"{OPS}/resources/from-staff", json={"staff_ids": [f["staff_id"]]})
        assert r.json()["added"] == 0
        d = state(A)
        res = next(x for x in d["resources"] if x.get("persona_id") == f["persona_id"])
        created.append(("resources", res["id"]))
        assert res["nome"] == f["nome"] and res["caposquadra"] is True and res["post_id"] == sh.get("post")
        # manual create with same persona_id -> 409
        assert A.post(f"{OPS}/resources", json={"kind": "persona", "persona_id": f["persona_id"]}).status_code == 409
        # update imported persona (frontend may not send nome)
        body = {k: res.get(k) for k in ("kind", "post_id", "sector_id", "stato", "caposquadra", "persona_id")}
        body["version"] = res["version"]; body["turno"] = "TEST_T1"
        r = A.put(f"{OPS}/resources/{res['id']}", json=body)
        assert r.status_code == 200, r.text
        r2 = find(state(A)["resources"], res["id"])
        assert r2["nome"] == f["nome"] and r2["turno"] == "TEST_T1"


class TestInterventionsSettings:
    def test_intervention(self, A, created):
        k0 = state(A)["kpi"]
        r = A.post(f"{OPS}/interventions", json={"titolo": "TEST_Malore", "priorita": "urgente", "km": 2})
        assert r.status_code == 200, r.text
        it = r.json(); created.append(("interventions", it["id"]))
        k1 = state(A)["kpi"]
        assert k1["interventi_aperti"] == k0["interventi_aperti"] + 1 and k1["interventi_urgenti"] == k0["interventi_urgenti"] + 1
        r = A.put(f"{OPS}/interventions/{it['id']}", json={**it, "stato": "chiuso"})
        assert r.status_code == 200, r.text
        d = state(A)
        assert d["kpi"]["interventi_aperti"] == k0["interventi_aperti"]
        assert find(d["interventions"], it["id"])["chiuso_by"]

    def test_settings(self, A):
        s = state(A)["settings"]
        old = s["status"]
        assert A.put(f"{OPS}/settings", json={"status": "in_corso", "version": s["version"] + 50}).status_code == 409
        r = A.put(f"{OPS}/settings", json={"status": "in_corso", "responsabile": "TEST_Resp", "version": s["version"]})
        assert r.status_code == 200, r.text
        s2 = state(A)["settings"]
        assert s2["status"] == "in_corso" and s2["responsabile"] == "TEST_Resp"
        cats = s2["categories"] + [{"key": "test_cat", "label": "TEST_Cat"}]
        assert A.put(f"{OPS}/settings", json={"categories": cats, "version": s2["version"]}).status_code == 200
        s3 = state(A)["settings"]
        assert any(c["key"] == "test_cat" for c in s3["categories"])
        # removing a used category is refused
        bad = [c for c in s3["categories"] if c["key"] != "ristoro"]
        if any(p["categoria"] == "ristoro" for p in state(A)["posts"]):
            assert A.put(f"{OPS}/settings", json={"categories": bad, "version": s3["version"]}).status_code == 400
        # restore
        s3 = state(A)["settings"]
        r = A.put(f"{OPS}/settings", json={"status": old, "responsabile": s["responsabile"], "categories": [c for c in s3["categories"] if c["key"] != "test_cat"], "version": s3["version"]})
        assert r.status_code == 200, r.text

    def test_rev_increments(self, A, created):
        r0 = A.get(f"{OPS}/rev").json()["rev"]
        r = A.post(f"{OPS}/sectors", json={"nome": "TEST_rev"})
        created.append(("sectors", r.json()["id"]))
        assert A.get(f"{OPS}/rev").json()["rev"] > r0

    def test_invalid_kind_and_422(self, A):
        assert A.post(f"{OPS}/foo", json={}).status_code == 404
        assert A.post(f"{OPS}/sectors", json={"nome": ""}).status_code == 422


class TestPhase1Regression:
    def test_events_and_price(self, A):
        r = A.get(f"{API}/controlroom/events")
        assert r.status_code == 200 and r.json()["price_net"] == 119
        e = next(x for x in r.json()["events"] if x["id"] == EV_A)
        assert e["active"] is True
