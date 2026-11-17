# Control Room Phase 3: interventi (codici, flusso stati, assegnazioni), mobile operatore, messaggi, notifiche, ruoli, note sanitarie, allegati, diario
import os, uuid, concurrent.futures as cf
from datetime import datetime, timedelta, timezone
import pytest, requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = BASE_URL + "/api"
PWD = "TestCR2026!"
ORG_A = "e2356cc12b95447eb15b53d5aad01d32"
EV_A = "08e8a867893f4e2b835e2d43dd4fe65d"
OPS = f"{API}/controlroom/events/{EV_A}/ops"
MB = f"{API}/cr-mobile"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _login(email, org=None):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": PWD})
    if r.status_code != 200:
        pytest.skip(f"login failed {email}: {r.status_code}")
    s.headers["Authorization"] = f"Bearer {s.cookies.get('access_token')}"
    if org:
        s.headers["X-Org-Id"] = org
    return s


def state(s):
    r = s.get(OPS)
    assert r.status_code == 200, r.text
    return r.json()


def itv(s, iid):
    return next(i for i in state(s)["interventions"] if i["id"] == iid)


def res_state(s, rid):
    return next(x for x in state(s)["resources"] if x["id"] == rid)


@pytest.fixture(scope="module")
def A():
    return _login("test_cr_a@crmevent-test.it")


@pytest.fixture(scope="module")
def C():
    return _login("test_cr_c@crmevent-test.it", ORG_A)


@pytest.fixture(scope="module")
def W(A):
    """Fixture world: 2 sectors, 1 post, 4 resources, 1 invite; cleanup at end (interventions annulled: no delete endpoint)."""
    made, itvs = [], []
    def mk(kind, body):
        r = A.post(f"{OPS}/{kind}", json=body)
        assert r.status_code == 200, r.text
        made.append((kind, r.json()["id"]))
        return r.json()["id"]
    w = {"itvs": itvs}
    w["S1"] = mk("sectors", {"nome": "TEST_P3 S1", "km_inizio": 0, "km_fine": 10})
    w["S2"] = mk("sectors", {"nome": "TEST_P3 S2", "km_inizio": 10.5, "km_fine": 20})
    w["P1"] = mk("posts", {"nome": "TEST_P3 Post1", "sector_id": w["S1"], "km": 3, "lng": 9.19, "lat": 45.46})
    w["R1"] = mk("resources", {"kind": "persona", "nome": "TEST_P3 Mario", "post_id": w["P1"]})
    w["R2"] = mk("resources", {"kind": "squadra", "nome": "TEST_P3 Squadra", "sector_id": w["S1"]})
    w["R3"] = mk("resources", {"kind": "mezzo", "nome": "TEST_P3 Polizia", "tipologia": "polizia", "autorizzazione_ente": True, "sector_id": w["S1"]})
    w["R4"] = mk("resources", {"kind": "persona", "nome": "TEST_P3 Luca", "sector_id": w["S2"]})
    r = A.post(f"{OPS}/invites", json={"resource_id": w["R1"], "days": 1})
    assert r.status_code == 200, r.text
    w["tok"], w["inv"] = r.json()["token"], r.json()["id"]
    yield w
    for iid in itvs:
        try:
            it = itv(A, iid)
            if it["stato"] not in ("chiuso", "annullato"):
                A.post(f"{OPS}/interventions/{iid}/status", json={"to": "annullato", "motivo": "TEST cleanup", "force": True, "note": "cleanup", "version": it["version"]})
        except StopIteration:
            pass
    A.delete(f"{OPS}/invites/{w['inv']}")
    for kind, oid in reversed(made):
        A.delete(f"{OPS}/{kind}/{oid}")


def new_itv(s, w, **kw):
    body = {"tipologia": "sanitario", "priorita": "alta", "descrizione": "TEST_P3 itv", **kw}
    if not any(k in kw for k in ("post_id", "lng", "km", "riferimento", "sector_id")):
        body["post_id"] = w["P1"]
    r = s.post(f"{OPS}/interventions", json=body)
    if r.status_code == 200:
        w["itvs"].append(r.json()["id"])
    return r


def st(s, iid, to, **kw):
    v = kw.pop("version", None) or itv(s, iid)["version"]
    return s.post(f"{OPS}/interventions/{iid}/status", json={"to": to, "version": v, **kw})


class TestCreate:
    def test_validation(self, A, W):
        assert new_itv(A, W, riferimento=None, descrizione="TEST_P3 x", sector_id=None, post_id=None).status_code in (400, 422)
        r = A.post(f"{OPS}/interventions", json={"tipologia": "sanitario", "priorita": "alta", "descrizione": "TEST_P3 nopos"})
        assert r.status_code == 400, r.text
        r = A.post(f"{OPS}/interventions", json={"tipologia": "nope", "priorita": "alta", "descrizione": "TEST_P3", "riferimento": "x"})
        assert r.status_code == 400
        r = A.post(f"{OPS}/interventions", json={"priorita": "alta", "descrizione": "TEST_P3", "riferimento": "x"})
        assert r.status_code in (400, 422)

    def test_reference_only_da_confermare_and_nearest_post(self, A, W):
        r = new_itv(A, W, riferimento="TEST_P3 incrocio", post_id=None)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["da_confermare"] is True and d["lng"] is None and d["codice"].startswith("INT-")
        r = new_itv(A, W, lng=9.1905, lat=45.4605)
        assert r.json()["post_vicina_id"] == W["P1"] and r.json()["da_confermare"] is False

    def test_parallel_codes_unique(self, A, W):
        with cf.ThreadPoolExecutor(10) as ex:
            rs = list(ex.map(lambda i: new_itv(A, W, riferimento=f"TEST_P3 par {i}", post_id=None), range(10)))
        assert all(r.status_code == 200 for r in rs), [r.text for r in rs if r.status_code != 200]
        nums = sorted(r.json()["numero"] for r in rs)
        assert len(set(nums)) == 10 and nums == list(range(nums[0], nums[0] + 10))
        assert all(r.json()["codice"] == f"INT-{r.json()['numero']:03d}" for r in rs)


class TestStatusFlow:
    def test_flow(self, A, W):
        iid = new_itv(A, W).json()["id"]
        assert st(A, iid, "sul_posto").status_code == 409
        assert st(A, iid, "preso_in_carico").status_code == 200
        it = itv(A, iid)
        assert it["t_presa"] and it["stato"] == "preso_in_carico"
        assert st(A, iid, "squadra_inviata", version=it["version"] - 1).status_code == 409  # stale version
        assert st(A, iid, "risolto", force=True).status_code == 403  # force without note
        assert st(A, iid, "risolto", force=True, note="radio").status_code == 200
        assert st(A, iid, "chiuso").status_code == 200
        it = itv(A, iid)
        assert it["t_risoluzione"] and it["t_chiusura"] and it["stato"] == "chiuso"
        assert st(A, iid, "sul_posto").status_code == 400  # reopen w/o motivo
        assert st(A, iid, "sul_posto", motivo="ripreso").status_code == 200
        it = itv(A, iid)
        assert len(it["history"]) == 4 and it["history"][-1]["motivo"] == "ripreso" and it["history"][1]["forzato"] is True
        rows = A.get(f"{OPS}/diary", params={"intervention_id": iid}).json()["rows"]
        assert {"apertura", "presa_in_carico", "risoluzione", "chiusura", "riapertura"} <= {r["type"] for r in rows}

    def test_annullato_needs_motivo(self, A, W):
        iid = new_itv(A, W).json()["id"]
        assert st(A, iid, "annullato").status_code == 400
        assert st(A, iid, "annullato", motivo="falso allarme").status_code == 200
        assert itv(A, iid)["stato"] == "annullato"


class TestAssign:
    def test_assign_confirm_revoke_overlap(self, A, W):
        i1 = new_itv(A, W).json()["id"]
        i2 = new_itv(A, W).json()["id"]
        r = A.post(f"{OPS}/interventions/{i1}/assign", json={"resource_ids": [W["R2"]]})
        assert r.status_code == 200 and r.json()["assigned"] == 1
        it = itv(A, i1)
        assert it["assignments"][0]["stato"] == "non_confermata" and it["attesa_conferma"] and not it["senza_squadra"]
        assert res_state(A, W["R2"])["stato"] == "impegnato"
        assert A.post(f"{OPS}/interventions/{i1}/assign", json={"resource_ids": [W["R2"]]}).status_code == 400  # already
        assert A.post(f"{OPS}/interventions/{i2}/assign", json={"resource_ids": [W["R2"]]}).status_code == 200
        s = state(A)
        assert W["R2"] in s["overlaps"] and len(s["overlaps"][W["R2"]]) == 2
        k = s["kpi"]
        for key in ("interventi_aperti", "interventi_critici", "interventi_senza_squadra", "interventi_attesa_conferma", "interventi_in_corso", "interventi_risolti"):
            assert key in k
        assert k["interventi_attesa_conferma"] >= 2
        assert A.post(f"{OPS}/interventions/{i1}/assignments/{W['R2']}/confirm", json={"via": "radio"}).status_code == 200
        assert itv(A, i1)["assignments"][0]["stato"] == "confermata"
        assert A.post(f"{OPS}/interventions/{i1}/assignments/{W['R2']}/confirm", json={"via": "radio"}).status_code == 409
        assert A.delete(f"{OPS}/interventions/{i1}/assignments/{W['R2']}").status_code == 200
        assert res_state(A, W["R2"])["stato"] == "impegnato"  # still on i2
        assert A.delete(f"{OPS}/interventions/{i2}/assignments/{W['R2']}").status_code == 200
        assert res_state(A, W["R2"])["stato"] == "disponibile"

    def test_external_vehicle(self, A, W):
        iid = new_itv(A, W).json()["id"]
        assert A.post(f"{OPS}/interventions/{iid}/assign", json={"resource_ids": [W["R3"]]}).status_code == 400
        assert A.post(f"{OPS}/interventions/{iid}/assign", json={"resource_ids": [W["R3"]], "conferma_esterni": True}).status_code == 200
        A.delete(f"{OPS}/interventions/{iid}/assignments/{W['R3']}")


class TestMobile:
    def test_home_and_checkin(self, A, W):
        r = requests.get(f"{MB}/{W['tok']}")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["operator"]["nome"] == "TEST_P3 Mario" and d["post"]["id"] == W["P1"] and d["event"]["nome"]
        assert len(d["itv_types"]) >= 11
        assert requests.post(f"{MB}/{W['tok']}/checkin", json={"presente": True}).json()["presente"] is True
        assert res_state(A, W["R1"])["presente"] is True

    def test_report_idempotent_and_priority(self, A, W):
        cid = uuid.uuid4().hex
        body = {"client_id": cid, "tipologia": "ostacolo", "descrizione": "TEST_P3 field", "priorita": "critica", "pos_mode": "postazione"}
        r1 = requests.post(f"{MB}/{W['tok']}/reports", json=body)
        assert r1.status_code == 200, r1.text
        W["itvs"].append(r1.json()["id"])
        r2 = requests.post(f"{MB}/{W['tok']}/reports", json=body)
        assert r2.json()["codice"] == r1.json()["codice"] and r2.json().get("duplicate") is True
        it = itv(A, r1.json()["id"])
        assert it["origine"] == "campo" and it["priorita"] == "media"  # can_set_priority false -> default type priority
        W["report_id"] = it["id"]
        r3 = requests.post(f"{MB}/{W['tok']}/reports", json={"client_id": uuid.uuid4().hex, "tipologia": "altro", "descrizione": "TEST_P3 manual", "pos_mode": "manuale", "riferimento": "TEST_P3 bivio"})
        assert r3.status_code == 200, r3.text
        W["itvs"].append(r3.json()["id"])
        assert itv(A, r3.json()["id"])["da_confermare"] is True

    def test_actions(self, A, W):
        iid = new_itv(A, W).json()["id"]
        assert requests.post(f"{MB}/{W['tok']}/interventions/{iid}/action", json={"action": "conferma"}).status_code == 403  # not assigned
        A.post(f"{OPS}/interventions/{iid}/assign", json={"resource_ids": [W["R1"]]})
        mine = [i for i in requests.get(f"{MB}/{W['tok']}").json()["interventions"] if i["id"] == iid]
        assert mine and mine[0]["my_assignment"]["stato"] == "non_confermata"
        for act, exp in (("conferma", "preso_in_carico"), ("partito", "squadra_inviata"), ("arrivato", "sul_posto"), ("risolto", "risolto")):
            r = requests.post(f"{MB}/{W['tok']}/interventions/{iid}/action", json={"action": act})
            assert r.status_code == 200, f"{act}: {r.text}"
            assert itv(A, iid)["stato"] == exp
        assert itv(A, iid)["assignments"][0]["stato"] == "confermata"
        assert st(A, iid, "chiuso").status_code == 200
        assert requests.post(f"{MB}/{W['tok']}/interventions/{iid}/action", json={"action": "aggiorna", "note": "x"}).status_code == 409

    def test_refuse(self, A, W):
        iid = new_itv(A, W).json()["id"]
        A.post(f"{OPS}/interventions/{iid}/assign", json={"resource_ids": [W["R1"]]})
        assert requests.post(f"{MB}/{W['tok']}/interventions/{iid}/action", json={"action": "rifiuta"}).status_code == 400
        assert requests.post(f"{MB}/{W['tok']}/interventions/{iid}/action", json={"action": "rifiuta", "note": "lontano"}).status_code == 200
        a = itv(A, iid)["assignments"][0]
        assert a["stato"] == "rifiutata" and a["motivo"] == "lontano"

    def test_photo_and_attachment_auth(self, A, W):
        iid = W.get("report_id") or pytest.skip("no report")
        u = f"{MB}/{W['tok']}/interventions/{iid}/photo"
        r = requests.post(u, files={"file": ("a.png", PNG, "image/png")})
        assert r.status_code == 200, r.text
        aid = r.json()["id"]
        assert requests.post(u, files={"file": ("a.txt", b"hello world", "text/plain")}).status_code == 415
        assert requests.post(u, files={"file": ("big.png", PNG + b"\x00" * (8 * 1024 * 1024), "image/png")}).status_code == 413
        au = f"{OPS}/interventions/{iid}/attachments/{aid}"
        assert requests.get(au).status_code == 401
        g = A.get(au)
        assert g.status_code == 200 and g.content[:8] == PNG[:8]

    def test_revoked_and_expired(self, A, W):
        r = A.post(f"{OPS}/invites", json={"resource_id": W["R4"], "days": 1})
        tok, inv = r.json()["token"], r.json()["id"]
        assert requests.get(f"{MB}/{tok}").status_code == 200
        assert A.delete(f"{OPS}/invites/{inv}").status_code == 200
        assert requests.get(f"{MB}/{tok}").status_code == 401
        assert requests.get(f"{MB}/invalid-token-xyz").status_code == 401
        # expired: set expires_at in the past on our own invite
        from pymongo import MongoClient
        db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        r = A.post(f"{OPS}/invites", json={"resource_id": W["R4"], "days": 1})
        tok2, inv2 = r.json()["token"], r.json()["id"]
        db.cr_invites.update_one({"id": inv2}, {"$set": {"expires_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()}})
        assert requests.get(f"{MB}/{tok2}").status_code == 401
        A.delete(f"{OPS}/invites/{inv2}")


class TestMessages:
    def test_delivery_read(self, A, W):
        r = A.post(f"{OPS}/messages", json={"to_type": "operatore", "to_id": W["R1"], "text": "TEST_P3 msg"})
        assert r.status_code == 200 and r.json()["recipients"] == 1
        mid = r.json()["id"]
        m = lambda: next(x for x in state(A)["messages"] if x["id"] == mid)
        assert m()["n_delivered"] == 0 and m()["n_read"] == 0
        requests.get(f"{MB}/{W['tok']}")
        assert m()["n_delivered"] == 1 and m()["n_read"] == 0
        requests.post(f"{MB}/{W['tok']}/messages/read")
        assert m()["n_read"] == 1

    def test_targets(self, A, W):
        assert A.post(f"{OPS}/messages", json={"to_type": "settore", "to_id": W["S1"], "text": "TEST_P3 sett"}).json()["recipients"] >= 1
        assert A.post(f"{OPS}/messages", json={"to_type": "tutti", "text": "TEST_P3 all"}).json()["recipients"] >= 1
        assert A.post(f"{OPS}/messages", json={"to_type": "operatore", "to_id": W["R2"], "text": "TEST_P3 none"}).json()["recipients"] == 0
        assert A.post(f"{OPS}/messages", json={"to_type": "operatore", "text": "x"}).status_code == 400

    def test_inbound(self, A, W):
        assert requests.post(f"{MB}/{W['tok']}/messages", json={"text": "TEST_P3 dal campo"}).status_code == 200
        assert state(A)["unread_inbound"] >= 1
        assert A.post(f"{OPS}/messages/read").status_code == 200
        assert state(A)["unread_inbound"] == 0

    def test_notifications(self, A, W):
        new_itv(A, W, priorita="critica")
        assert state(A)["unread"] >= 1
        assert A.post(f"{OPS}/notifications/read").status_code == 200
        assert state(A)["unread"] == 0


class TestRolesHealthDiary:
    def test_roles_scope(self, A, C, W):
        assert C.get(f"{OPS}/members").status_code == 403
        ms = A.get(f"{OPS}/members").json()["members"]
        c = next(m for m in ms if m["email"] == "test_cr_c@crmevent-test.it")
        prev = c["cr_role"]
        try:
            assert C.put(f"{OPS}/roles", json={"user_id": c["user_id"], "role": "responsabile"}).status_code == 403
            assert A.put(f"{OPS}/roles", json={"user_id": c["user_id"], "role": "coordinatore", "sector_ids": [W["S1"]]}).status_code == 200
            assert state(C)["perms"]["role"] == "coordinatore"
            r = new_itv(C, W)  # post P1 in S1
            assert r.status_code == 200, r.text
            ic = r.json()["id"]
            assert new_itv(C, W, km=15, post_id=None).status_code == 403
            ia = new_itv(A, W, km=15, post_id=None).json()["id"]
            assert itv(A, ia)["sector_id"] == W["S2"]
            assert st(C, ia, "preso_in_carico").status_code == 403
            assert st(C, ic, "preso_in_carico").status_code == 200
            assert st(C, ic, "risolto", force=True, note="x").status_code == 403
            assert C.post(f"{OPS}/interventions/{ic}/assign", json={"resource_ids": [W["R4"]]}).status_code == 403
            assert C.post(f"{OPS}/interventions/{ic}/assign", json={"resource_ids": [W["R2"]]}).status_code == 200
            assert C.get(f"{OPS}/interventions/{ic}/health").status_code == 403
            assert C.get(f"{OPS}/diary/export").status_code == 403
            A.put(f"{OPS}/roles", json={"user_id": c["user_id"], "role": "visualizzatore"})
            assert new_itv(C, W).status_code == 403
            assert C.post(f"{OPS}/messages", json={"to_type": "tutti", "text": "TEST_P3"}).status_code == 403
        finally:
            A.put(f"{OPS}/roles", json={"user_id": c["user_id"], "role": prev, "sector_ids": c["sector_ids"]})

    def test_health(self, A, W):
        iid = new_itv(A, W).json()["id"]
        assert A.post(f"{OPS}/interventions/{iid}/health", json={"text": "TEST_P3 allergia"}).status_code == 200
        n = A.get(f"{OPS}/interventions/{iid}/health").json()["notes"]
        assert n and n[0]["text"] == "TEST_P3 allergia"
        assert "allergia" not in str(state(A)["diary"])

    def test_diary(self, A, W):
        rows = A.get(f"{OPS}/diary", params={"type": "assegnazione"}).json()["rows"]
        assert rows and all(r["type"] == "assegnazione" for r in rows)
        ats = [r["at"] for r in rows]
        assert ats == sorted(ats)
        e = A.get(f"{OPS}/diary/export")
        assert e.status_code == 200 and "text/csv" in e.headers["content-type"]
        assert e.text.lstrip("\ufeff").startswith("data_ora_utc;tipo;intervento;utente;descrizione")


class TestTenant:
    def test_org_b_isolated(self, A, W):
        B = _login("test_cr_b@crmevent-test.it")
        assert B.get(OPS).status_code in (403, 404)
        iid = W["itvs"][0]
        assert B.post(f"{OPS}/interventions/{iid}/status", json={"to": "annullato", "motivo": "x", "version": 1}).status_code in (403, 404)
        assert B.get(f"{OPS}/interventions/{iid}/attachments/x").status_code in (403, 404)
