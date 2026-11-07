# Calendario Eventi Italia — Fase 2: fonti, verifica accesso, collegamento feed, sync, cron, settings
import os
import time
import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api/platform/cal"
EMAIL, PWD = "manara.michele.pro@gmail.com", "CrmEvent2026!"
ICS = "https://calendar.google.com/calendar/ical/it.italian%23holiday%40group.v.calendar.google.com/public/basic.ics"
EXTERNAL = ["fidal", "raceup", "wedosport", "runningaround", "fitri", "myfitri", "ironman"]
CREATED = {"sources": [], "builtin_touched": set()}


def _db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def sa():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PWD})
    if r.status_code != 200:
        pytest.skip("login failed")
    return s


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    db = _db()
    pre_existing_builtin = {d["id"] for d in db.cal_sources.find({}, {"id": 1})}
    settings_before = db.cal_settings.find_one({"id": "main"}, {"_id": 0})
    yield
    for sid in CREATED["sources"]:
        eids = [e["id"] for e in db.cal_events.find({"sources.source": sid}, {"id": 1})]
        if eids:
            db.cal_duplicates.delete_many({"$or": [{"a": {"$in": eids}}, {"b": {"$in": eids}}]})
            db.cal_conflicts.delete_many({"event_id": {"$in": eids}})
            db.cal_history.delete_many({"entity_id": {"$in": eids}})
            db.cal_events.delete_many({"id": {"$in": eids}})
        db.cal_imports.delete_many({"source": sid})
        db.cal_sources.delete_one({"id": sid})
    for sid in CREATED["builtin_touched"]:
        if sid not in pre_existing_builtin:
            db.cal_sources.delete_one({"id": sid})
    if settings_before is not None:
        db.cal_settings.replace_one({"id": "main"}, settings_before)


# --- access control
class TestAccess:
    def test_no_auth(self):
        for m, p in [("get", "/sources"), ("post", "/sync"), ("get", "/settings"), ("post", "/sources/fidal/sync")]:
            r = getattr(requests, m)(f"{API}{p}")
            assert r.status_code in (401, 403), (p, r.status_code)

    def test_cron_no_auth(self):
        assert requests.post(f"{BASE_URL}/api/cron/cal-italia-sync").status_code == 401
        assert requests.post(f"{BASE_URL}/api/cron/cal-italia-sync", headers={"Authorization": "Bearer wrong"}).status_code == 401


# --- built-in sources verification state
class TestBuiltinSources:
    def test_list(self, sa):
        r = sa.get(f"{API}/sources")
        assert r.status_code == 200
        d = r.json()
        by = {s["id"]: s for s in d["sources"]}
        for k in EXTERNAL:
            assert by[k]["verifica"]["esito"] == "non_consentita", k
            assert by[k]["stato"] == "non_disponibile", k
            assert len(by[k]["verifica"]["evidenze"]) >= 1
        assert by["manuale"]["stato"] == "attiva"
        assert "imports" in d and "raccolta_automatica" in d
        assert d["formati"] == ["csv", "xlsx", "json", "ics"]

    def test_fidal_conn_sync_blocked(self, sa):
        r = sa.put(f"{API}/sources/fidal/connessione", json={"feed_url": "https://example.com/x.csv", "formato": "csv"})
        assert r.status_code == 400
        r = sa.post(f"{API}/sources/fidal/sync")
        assert r.status_code == 400
        r = sa.post(f"{API}/sources/fidal/test")
        assert r.status_code == 400

    def test_manuale_verifica_blocked(self, sa):
        assert sa.put(f"{API}/sources/manuale/verifica", json={"esito": "non_consentita"}).status_code == 400

    def test_unknown_source_404(self, sa):
        assert sa.put(f"{API}/sources/nope_xyz/verifica", json={"esito": "non_consentita"}).status_code == 404

    def test_verifica_flow(self, sa):
        CREATED["builtin_touched"].add("fidal")
        r = sa.put(f"{API}/sources/fidal/verifica", json={"esito": "consentita"})
        assert r.status_code == 400
        r = sa.put(f"{API}/sources/fidal/verifica", json={"esito": "consentita", "metodo": "  ", "prova": "x"})
        assert r.status_code == 400
        r = sa.put(f"{API}/sources/fidal/verifica", json={"esito": "bogus"})
        assert r.status_code == 400
        r = sa.put(f"{API}/sources/fidal/verifica", json={"esito": "consentita", "metodo": "TEST_API", "prova": "TEST_accordo"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["verifica"]["esito"] == "consentita" and d["stato"] == "disabilitata"
        assert d["verifica"]["evidenze"]  # evidence preserved
        # internal URL rejected on connessione
        r = sa.put(f"{API}/sources/fidal/connessione", json={"feed_url": "http://127.0.0.1:8001/x", "formato": "csv"})
        assert r.status_code == 400
        r = sa.put(f"{API}/sources/fidal/connessione", json={"feed_url": "https://example.com/feed.csv", "formato": "csv", "attiva": True})
        assert r.status_code == 200, r.text
        assert r.json()["stato"] == "attiva"
        # back to non_consentita -> disabled
        r = sa.put(f"{API}/sources/fidal/verifica", json={"esito": "non_consentita"})
        assert r.status_code == 200
        d = r.json()
        assert d["stato"] == "non_disponibile" and d["attiva"] is False
        assert sa.post(f"{API}/sources/fidal/sync").status_code == 400


# --- custom authorized source with public ICS feed
class TestCustomSource:
    def test_internal_urls_rejected(self, sa):
        for u in ["http://127.0.0.1/x.ics", "http://localhost:8001/api", "http://10.0.0.1/a", "ftp://example.com/a", "http://169.254.169.254/latest"]:
            r = sa.post(f"{API}/sources", json={"nome": "TEST_bad", "feed_url": u, "formato": "ics", "metodo": "TEST_m", "prova": "TEST_p"})
            assert r.status_code == 400, (u, r.status_code)

    def test_missing_metodo_prova(self, sa):
        r = sa.post(f"{API}/sources", json={"nome": "TEST_bad", "feed_url": ICS, "formato": "ics"})
        assert r.status_code == 422

    def test_bad_format(self, sa):
        r = sa.post(f"{API}/sources", json={"nome": "TEST_bad", "feed_url": ICS, "formato": "pdf", "metodo": "TEST_m", "prova": "TEST_p"})
        assert r.status_code == 400

    def test_ics_create_test_sync_twice(self, sa):
        r = sa.post(f"{API}/sources", json={"nome": "TEST_Festività ICS", "disciplina": "*", "feed_url": ICS, "formato": "ics",
                                            "metodo": "TEST_feed pubblico", "prova": "TEST_Google public calendar"})
        assert r.status_code == 200, r.text
        s = r.json()
        sid = s["id"]
        CREATED["sources"].append(sid)
        assert s["custom"] is True and s["stato"] == "attiva" and s["verifica"]["esito"] == "consentita"
        lst = {x["id"]: x for x in sa.get(f"{API}/sources").json()["sources"]}
        assert sid in lst
        r = sa.post(f"{API}/sources/{sid}/test")
        assert r.status_code == 200, r.text
        t = r.json()
        print("test total", t["total"], t["columns"], t["mapping"])
        assert t["total"] > 100
        assert "nome" in t["mapping"].values()
        # sync 1
        r = sa.post(f"{API}/sources/{sid}/sync")
        assert r.status_code == 200
        first = self._wait(sa, sid, None)
        print("sync1", first)
        assert first.get("ultimo_esito") == "ok"
        res1 = first["ultimo_risultato"]
        assert res1.get("created", 0) > 100
        ev_count = first["eventi"]
        # sync 2 -> linked, no duplicates
        r = sa.post(f"{API}/sources/{sid}/sync")
        assert r.status_code == 200
        second = self._wait(sa, sid, first["ultima_sync"])
        res2 = second["ultimo_risultato"]
        print("sync2", res2, "eventi", second["eventi"])
        assert res2.get("created", 0) == 0
        assert res2.get("linked", 0) == res1.get("created", 0)
        assert second["eventi"] == ev_count
        db = _db()
        assert db.cal_events.count_documents({"sources.source": sid}) == ev_count
        imps = [i for i in sa.get(f"{API}/sources").json()["imports"] if i.get("source") == sid]
        assert len(imps) >= 2 and all(i["kind"] == "sync" for i in imps)

    @staticmethod
    def _wait(sa, sid, prev):
        for _ in range(60):
            time.sleep(2)
            s = next(x for x in sa.get(f"{API}/sources").json()["sources"] if x["id"] == sid)
            if s.get("ultima_sync") and s["ultima_sync"] != prev and s["stato"] != "in_aggiornamento":
                return s
            if s.get("ultimo_esito") == "errore":
                return s
        pytest.fail("sync timeout")

    def test_sync_all(self, sa):
        r = sa.post(f"{API}/sync")
        assert r.status_code == 200
        assert r.json()["fonti"] >= 1
        if CREATED["sources"]:
            sid = CREATED["sources"][-1]
            prev = next(x for x in sa.get(f"{API}/sources").json()["sources"] if x["id"] == sid)["ultima_sync"]
            self._wait(sa, sid, prev)


# --- settings raccolta_automatica
class TestSettings:
    def test_toggle(self, sa):
        cur = sa.get(f"{API}/settings").json()
        for v in (True, False):
            r = sa.put(f"{API}/settings", json={**{k: cur[k] for k in ("giorni_post_evento", "intervallo_min_giorni")}, "raccolta_automatica": v})
            assert r.status_code == 200 and r.json()["raccolta_automatica"] is v
            assert sa.get(f"{API}/sources").json()["raccolta_automatica"] is v
