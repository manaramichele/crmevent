# Calendario Eventi Italia — Fase 3 Brevo: status, senders/list/template (not configured), templates, recipients preview, simulated send, comms, unsubscribe
import os
import time
from datetime import date, timedelta
import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api/platform/cal"
EMAIL, PWD = "manara.michele.pro@gmail.com", "CrmEvent2026!"
REG = "TEST_Regione3"
C = {"orgs": [], "events": [], "campaigns": []}
D8 = (date.today() - timedelta(days=8)).isoformat()


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
    tpl_before = {t["id"] for t in db.cal_templates.find({}, {"id": 1})}
    settings_before = db.cal_settings.find_one({"id": "main"}, {"_id": 0})
    yield
    ids = C["orgs"] + C["events"]
    db.cal_history.delete_many({"entity_id": {"$in": ids}})
    db.cal_comms.delete_many({"org_id": {"$in": C["orgs"]}})
    db.cal_campaigns.delete_many({"id": {"$in": C["campaigns"]}})
    db.cal_events.delete_many({"id": {"$in": C["events"]}})
    db.cal_organizers.delete_many({"id": {"$in": C["orgs"]}})
    db.cal_templates.delete_many({"id": {"$nin": list(tpl_before)}})
    if settings_before is not None:
        db.cal_settings.replace_one({"id": "main"}, settings_before)


def mk_org(sa, nome, email=None, escluso=False, idoneo=True):
    r = sa.post(f"{API}/organizers", json={"nome": nome, "email_organizzativa": email, "regione": REG, "escluso_campagne": escluso})
    assert r.status_code == 200, r.text
    oid = r.json()["id"]
    C["orgs"].append(oid)
    if idoneo:
        p = sa.put(f"{API}/organizers/{oid}/privacy", json={"status": "idoneo", "fonte": "sito ufficiale", "finalita": "B2B", "base_giuridica": "legittimo interesse"})
        assert p.status_code == 200, p.text
    return oid


def mk_ev(sa, nome, oid, d=D8):
    r = sa.post(f"{API}/events", json={"nome": nome, "data_inizio": d, "stato": "conclusa", "regione": REG, "organizer_id": oid, "comune": "Testopoli"})
    assert r.status_code == 200, r.text
    ev = r.json()
    eid = ev.get("id") or (ev.get("event") or {}).get("id")
    assert eid, ev
    C["events"].append(eid)
    return eid


class TestNotConfigured:
    def test_status(self, sa):
        r = sa.get(f"{API}/brevo/status")
        assert r.status_code == 200
        d = r.json()
        assert d["configured"] is False
        assert d["list_name"] == "CRMEvent \u2014 Organizzatori Eventi Italia"
        assert [t["id"] for t in d["templates"]] == ["post_evento", "richiamo"]

    @pytest.mark.parametrize("m,p", [("get", "/brevo/senders"), ("post", "/brevo/list/sync"), ("post", "/templates/post_evento/brevo"), ("post", "/templates/post_evento/test")])
    def test_brevo_calls_400(self, sa, m, p):
        r = getattr(sa, m)(f"{API}{p}", **({"json": {}} if m == "post" else {}))
        print(p, r.status_code, r.text[:200])
        assert r.status_code == 400, r.text
        assert r.json().get("detail")

    def test_put_sender_400(self, sa):
        r = sa.put(f"{API}/brevo/sender", json={"sender_id": 1})
        assert r.status_code == 400, r.text

    def test_no_auth(self):
        for m, p in [("get", "/brevo/status"), ("post", "/campaigns/preview"), ("get", "/comms"), ("get", "/templates")]:
            assert getattr(requests, m)(f"{API}{p}").status_code in (401, 403)


class TestTemplates:
    def test_list(self, sa):
        d = sa.get(f"{API}/templates").json()
        assert len(d["templates"]) == 2 and "UNSUB_URL" in d["params"]
        assert all("params.UNSUB_URL" in t["html"] for t in d["templates"])

    def test_reject_without_unsub(self, sa):
        r = sa.put(f"{API}/templates/richiamo", json={"nome": "Richiamo", "oggetto": "Ciao test", "html": "<p>nessun link di disiscrizione qui</p>"})
        assert r.status_code == 400 and "UNSUB_URL" in r.json()["detail"]

    def test_unknown_404(self, sa):
        r = sa.put(f"{API}/templates/nope", json={"nome": "xx", "oggetto": "xx", "html": "<p>{{ params.UNSUB_URL }} aaaaaaaaaa</p>"})
        assert r.status_code == 404

    def test_save_valid(self, sa):
        html = "<p>TEST_ ciao {{ params.ORGANIZZATORE }}</p><a href='{{ params.UNSUB_URL }}'>x</a>"
        r = sa.put(f"{API}/templates/richiamo", json={"nome": "Richiamo TEST", "oggetto": "Oggetto TEST", "html": html})
        assert r.status_code == 200, r.text
        g = [t for t in sa.get(f"{API}/templates").json()["templates"] if t["id"] == "richiamo"][0]
        assert g["nome"] == "Richiamo TEST" and g["html"] == html


class TestPreviewSend:
    def test_flow(self, sa):
        ok = mk_org(sa, "TEST_P3 Org Idoneo", "test_p3_ok@example.com")
        dv = mk_org(sa, "TEST_P3 Org DaVerificare", "test_p3_dv@example.com", idoneo=False)
        ne = mk_org(sa, "TEST_P3 Org NoEmail", None)
        ex = mk_org(sa, "TEST_P3 Org Escluso", "test_p3_ex@example.com", escluso=True)
        e1 = mk_ev(sa, "TEST_P3 Maratona Alfa", ok)
        e2 = mk_ev(sa, "TEST_P3 Trail Beta Montagna", ok)
        mk_ev(sa, "TEST_P3 Corsa Gamma", dv)
        mk_ev(sa, "TEST_P3 Mezza Delta", ne)
        mk_ev(sa, "TEST_P3 Ciclo Epsilon", ex)
        flt = {"template_id": "post_evento", "regione": REG}
        r = sa.post(f"{API}/campaigns/preview", json=flt)
        assert r.status_code == 200, r.text
        p = r.json()
        print("inclusi", [(x["organizzatore"], x["evento"], x["data_comunicazione"]) for x in p["inclusi"]])
        print("esclusi", [(x["organizzatore"], x["evento"], x["motivo"]) for x in p["esclusi"]])
        assert len(p["inclusi"]) == 1 and p["inclusi"][0]["org_id"] == ok
        assert p["inclusi"][0]["data_comunicazione"] == (date.today() - timedelta(days=1)).isoformat()
        mot = {x["organizzatore"]: x["motivo"] for x in p["esclusi"]}
        assert "da_verificare" in mot["TEST_P3 Org DaVerificare"]
        assert mot["TEST_P3 Org NoEmail"] == "Email mancante"
        assert mot["TEST_P3 Org Escluso"] == "Escluso dalle campagne"
        dup = [x for x in p["esclusi"] if x["org_id"] == ok]
        assert len(dup) == 1 and dup[0]["motivo"] == "Organizzatore gi\u00e0 incluso per un altro evento"
        assert dup[0]["event_id"] in (e1, e2)
        firma = p["firma"]

        # send validations
        r = sa.post(f"{API}/campaigns/send", json={**flt, "firma": firma, "conferma": "no", "simulazione": True})
        assert r.status_code == 400
        r = sa.post(f"{API}/campaigns/send", json={**flt, "firma": "wrong", "conferma": "INVIA", "simulazione": True})
        assert r.status_code == 409
        r = sa.post(f"{API}/campaigns/send", json={**flt, "firma": firma, "conferma": "INVIA", "simulazione": False})
        assert r.status_code == 400, r.text
        stato_before = sa.get(f"{API}/organizers/{ok}").json().get("stato_commerciale")
        r = sa.post(f"{API}/campaigns/send", json={**flt, "firma": firma, "conferma": "INVIA", "simulazione": True})
        assert r.status_code == 200, r.text
        cid = r.json()["campaign_id"]
        C["campaigns"].append(cid)
        assert r.json()["destinatari"] == 1 and r.json()["simulazione"] is True
        time.sleep(2)
        camp = [c for c in sa.get(f"{API}/campaigns").json()["campaigns"] if c["id"] == cid][0]
        assert camp["status"] == "completata" and camp["inviati"] == 1 and camp["errori"] == 0
        cm = sa.get(f"{API}/comms", params={"campaign_id": cid}).json()
        assert len(cm["rows"]) == 1 and cm["rows"][0]["status"] == "simulato" and cm["rows"][0]["org_id"] == ok
        assert cm["totali"].get("simulato", 0) >= 1
        assert len(sa.get(f"{API}/comms", params={"status": "simulato", "q": "TEST_P3 Org Idoneo"}).json()["rows"]) >= 1
        assert len(sa.get(f"{API}/comms", params={"status": "inviato", "q": "TEST_P3 Org Idoneo"}).json()["rows"]) == 0
        o = sa.get(f"{API}/organizers/{ok}").json()
        assert o.get("stato_commerciale") == stato_before
        assert len(o["communications"]) == 1 and o["communications"][0]["status"] == "simulato"
        dash = sa.get(f"{API}/dashboard")
        print("dashboard", dash.status_code, str(dash.json())[:300] if dash.ok else dash.text[:200])

        # unsubscribe
        r = requests.get(f"{BASE_URL}/api/public/cal/unsubscribe/invalid_token_123456789012345")
        assert r.status_code == 200 and "Link non valido" in r.text
        tok = _db().cal_organizers.find_one({"id": ok})["unsub_token"]
        assert tok
        r = requests.get(f"{BASE_URL}/api/public/cal/unsubscribe/{tok}")
        assert r.status_code == 200 and "Disiscrizione registrata" in r.text
        o = sa.get(f"{API}/organizers/{ok}").json()
        assert o["privacy"]["status"] == "disiscritto"
        p2 = sa.post(f"{API}/campaigns/preview", json=flt).json()
        assert len(p2["inclusi"]) == 0
        assert all("disiscritto" in x["motivo"] for x in p2["esclusi"] if x["org_id"] == ok)
        # cannot return to idoneo
        r = sa.put(f"{API}/organizers/{ok}/privacy", json={"status": "idoneo", "fonte": "a", "finalita": "b", "base_giuridica": "c"})
        assert r.status_code == 400
        # no-recipient send -> 400
        r = sa.post(f"{API}/campaigns/send", json={**flt, "firma": p2["firma"], "conferma": "INVIA", "simulazione": True})
        assert r.status_code == 400
