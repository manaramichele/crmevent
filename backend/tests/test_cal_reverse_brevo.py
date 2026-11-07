# Calendario Eventi Italia — Ricerca inversa da Brevo: brevo lists (not configured), search jobs gating/suspension, findings review, settings, cron auth
import os
import time
import uuid
import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api/platform/cal/reverse"
EMAIL, PWD = "manara.michele.pro@gmail.com", "CrmEvent2026!"
T = uuid.uuid4().hex[:6]
C = {"contacts": [], "findings": [], "jobs": [], "events": [], "orgs": []}


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
    jobs_before = {j["id"] for j in db.cal_rv_jobs.find({}, {"id": 1})}
    orgs_before = {o["id"] for o in db.cal_organizers.find({}, {"id": 1})}
    rv_before = (db.cal_settings.find_one({"id": "main"}, {"_id": 0, "rv": 1}) or {}).get("rv")
    yield
    new_jobs = [j["id"] for j in db.cal_rv_jobs.find({"id": {"$nin": list(jobs_before)}}, {"id": 1})]
    db.cal_rv_jobs.delete_many({"id": {"$in": new_jobs}})
    db.cal_rv_contacts.delete_many({"id": {"$in": C["contacts"]}})
    db.cal_rv_findings.delete_many({"id": {"$in": C["findings"]}})
    new_orgs = [o["id"] for o in db.cal_organizers.find({"id": {"$nin": list(orgs_before)}, "nome": {"$regex": "^TEST_"}}, {"id": 1})]
    ids = C["events"] + new_orgs
    db.cal_history.delete_many({"entity_id": {"$in": ids}})
    db.cal_duplicates.delete_many({"$or": [{"a": {"$in": C["events"]}}, {"b": {"$in": C["events"]}}]})
    db.cal_events.delete_many({"id": {"$in": C["events"]}})
    db.cal_organizers.delete_many({"id": {"$in": new_orgs}})
    if rv_before is None:
        db.cal_settings.update_one({"id": "main"}, {"$unset": {"rv": ""}})
    else:
        db.cal_settings.update_one({"id": "main"}, {"$set": {"rv": rv_before}})


def seed_contact(email, societa=None):
    cid = uuid.uuid4().hex
    dom = email.split("@")[-1]
    _db().cal_rv_contacts.insert_one({"id": cid, "email": email, "societa": societa, "dominio": None if dom == "gmail.com" else dom,
                                      "stato_ricerca": "da_analizzare", "eventi": [], "fonti": []})
    C["contacts"].append(cid)
    return cid


def seed_finding(nome):
    fid = uuid.uuid4().hex
    _db().cal_rv_findings.insert_one({"id": fid, "key": f"test:{fid}", "contact_id": "TEST_c", "email": f"test_{T}@example.org", "nome": nome,
                                      "disciplina": "running", "data_inizio": None, "data_fine": None, "anno": None, "stato": "data_da_confermare",
                                      "stato_evento": "confermata", "attendibilita": 50, "organizzatore": f"TEST_Org_{T}", "organizer_id": None,
                                      "fonte_url": "https://example.org/gara", "estratto": "TEST", "verificato_il": "2026-01-01T00:00:00+00:00"})
    C["findings"].append(fid)
    return fid


def wait_job(sa, jid, states=("sospeso", "completato", "annullato"), t=20):
    for _ in range(t * 2):
        j = next((x for x in sa.get(f"{API}/status").json()["jobs"] if x["id"] == jid), None)
        if j and j["status"] in states:
            return j
        time.sleep(0.5)
    return j


class TestBasics:
    def test_status(self, sa):
        r = sa.get(f"{API}/status")
        assert r.status_code == 200
        d = r.json()
        assert d["brave_configurato"] is False
        assert set(d["kpi"]) >= {"totale_contatti", "analizzati", "organizzatori_identificati", "eventi_trovati", "eventi_verificati",
                                 "eventi_da_verificare", "senza_eventi", "errori"}

    def test_requires_auth(self):
        assert requests.get(f"{API}/status").status_code in (401, 403)

    def test_brevo_lists_not_configured(self, sa):
        r = sa.get(f"{API}/brevo/lists")
        assert r.status_code == 400 and "Brevo non configurato" in r.json()["detail"]

    def test_import_not_configured(self, sa):
        r = sa.post(f"{API}/import", json={"list_ids": [1]})
        assert r.status_code == 400 and "Brevo non configurato" in r.json()["detail"]
        assert sa.post(f"{API}/import", json={"list_ids": []}).status_code == 422

    def test_cron_unauth(self):
        assert requests.post(f"{BASE_URL}/api/cron/cal-italia-reverse-update").status_code == 401
        assert requests.post(f"{BASE_URL}/api/cron/cal-italia-reverse-update", headers={"Authorization": "Bearer wrong"}).status_code == 401

    def test_settings(self, sa):
        body = {"aggiornamento_notturno": False, "intervallo_giorni": 14, "max_per_notte": 120, "cache_giorni": 5}
        r = sa.put(f"{API}/settings", json=body)
        assert r.status_code == 200 and r.json() == body
        assert sa.get(f"{API}/status").json()["settings"] == body
        assert sa.put(f"{API}/settings", json={**body, "intervallo_giorni": 0}).status_code == 422


class TestJobs:
    def test_group_before_test(self, sa):
        if sa.get(f"{API}/status").json()["test_completato"]:
            pytest.skip("test already completed in DB")
        for sc in ("gruppo", "tutti"):
            r = sa.post(f"{API}/search", json={"scope": sc, "size": 50})
            assert r.status_code == 400 and "test" in r.json()["detail"]
        assert sa.post(f"{API}/search", json={"scope": "bogus"}).status_code == 400

    def test_test_job_suspends_without_brave(self, sa):
        db = _db()
        c1 = seed_contact(f"test_{T}@test-asd-{T}.it", f"TEST_ASD {T}")
        r = sa.post(f"{API}/search", json={"scope": "test"})
        assert r.status_code == 200, r.text
        jid = r.json()["job_id"]
        j = wait_job(sa, jid)
        assert j["status"] == "sospeso" and "BRAVE_API_KEY" in (j.get("motivo") or "")
        assert db.cal_rv_contacts.find_one({"id": c1})["stato_ricerca"] == "errore"
        # resume -> suspends again (still no key)
        r = sa.post(f"{API}/jobs/{jid}/riprendi")
        assert r.status_code == 200
        wait_job(sa, jid)
        assert sa.post(f"{API}/jobs/{jid}/bogus").status_code == 400
        assert sa.post(f"{API}/jobs/{jid}/annulla").status_code == 200
        j = next(x for x in sa.get(f"{API}/status").json()["jobs"] if x["id"] == jid)
        assert j["status"] == "annullato"
        assert sa.post(f"{API}/jobs/{jid}/riprendi").status_code == 400

    def test_gmail_only_dati_insufficienti(self, sa):
        db = _db()
        pend = db.cal_rv_contacts.count_documents({"stato_ricerca": "da_analizzare", "id": {"$nin": C["contacts"]}})
        if pend:
            pytest.skip("other pending contacts exist")
        c2 = seed_contact(f"test_{T}_solo@gmail.com")
        r = sa.post(f"{API}/search", json={"scope": "selezione", "contact_ids": [c2]})
        assert r.status_code == 200, r.text
        j = wait_job(sa, r.json()["job_id"])
        assert j["status"] == "completato"
        c = db.cal_rv_contacts.find_one({"id": c2})
        assert c["stato_ricerca"] == "dati_insufficienti" and c.get("nota")
        rows = sa.get(f"{API}/contacts", params={"stato": "dati_insufficienti", "q": f"test_{T}_solo"}).json()
        assert rows["total"] == 1


class TestFindings:
    def test_approve_without_date_400(self, sa):
        fid = seed_finding(f"TEST_Gara RV {T}")
        rows = sa.get(f"{API}/findings", params={"stato": "da_verificare,data_da_confermare"}).json()["rows"]
        assert any(x["id"] == fid for x in rows)
        r = sa.post(f"{API}/findings/{fid}/review", json={"action": "approva"})
        assert r.status_code == 400 and "data" in r.json()["detail"]

    def test_approve_with_date(self, sa):
        db = _db()
        fid = C["findings"][0]
        r = sa.post(f"{API}/findings/{fid}/review", json={"action": "approva", "data_inizio": "2027-03-14", "comune": "TEST_Comune"})
        assert r.status_code == 200, r.text
        eid = r.json()["event_id"]
        C["events"].append(eid)
        ev = db.cal_events.find_one({"id": eid})
        assert ev["nome"].startswith("TEST_Gara RV") and ev["data_inizio"] == "2027-03-14"
        assert any(s["source"] == "ricerca_brevo" for s in ev["sources"])
        f = db.cal_rv_findings.find_one({"id": fid})
        assert f["stato"] == "approvato" and f["event_id"] == eid and f["anno"] == 2027
        assert ev.get("organizer_id")

    def test_reject(self, sa):
        fid = seed_finding(f"TEST_Gara RV2 {T}")
        r = sa.post(f"{API}/findings/{fid}/review", json={"action": "scarta"})
        assert r.status_code == 200
        assert _db().cal_rv_findings.find_one({"id": fid})["stato"] == "scartato"
        assert sa.post(f"{API}/findings/nope/review", json={"action": "scarta"}).status_code == 400
