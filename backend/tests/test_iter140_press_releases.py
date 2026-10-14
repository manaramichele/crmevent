# Marketplace · Comunicati stampa (press): activation, isolation, AI generation, editor/approval, send flow w/o Brevo,
# contacts CRUD/import/export/unsubscribe, settings, automations, role guard, cron.
# Run: pytest tests/test_iter140_press_releases.py -n 0  (module-level state, single worker)
import asyncio
import os
import time
import uuid

import bcrypt
import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
QA = ("qa.eventi@crmeventqa.it", "QaEvents2026!")
SA = ("manara.michele.pro@gmail.com", "CrmEvent2026!")
ORG = "org_qa_eventi"
EV = "ev_qa_1"
MEM_EMAIL = f"test_press_{uuid.uuid4().hex[:6]}@crmeventqa.it"
MEM_PW = "TestMember2026!"
MEM_UID = "user_TEST_" + uuid.uuid4().hex[:10]
S = {}


def db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def login(email, pw):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module", autouse=True)
def setup_member():
    now = "2026-01-01T00:00:00+00:00"
    d = db()
    d.users.insert_one({"user_id": MEM_UID, "email": MEM_EMAIL, "name": "TEST Press Member", "role": "member",
                        "auth_provider": "password", "org_id": ORG, "active": True, "picture": "",
                        "password_hash": bcrypt.hashpw(MEM_PW.encode(), bcrypt.gensalt()).decode(),
                        "accepted_terms_at": now, "created_at": now})
    d.memberships.insert_one({"id": "mem_TEST_" + uuid.uuid4().hex[:8], "user_id": MEM_UID, "org_id": ORG, "role": "user",
                              "active": True, "permissions": {}, "added_by": "user_qaeventi", "created_at": now, "updated_at": now})
    yield


@pytest.fixture(scope="module")
def qa():
    return login(*QA)


@pytest.fixture(scope="module")
def sa():
    return login(*SA)


@pytest.fixture(scope="module")
def mem():
    return login(MEM_EMAIL, MEM_PW)


@pytest.fixture(scope="module")
def other():
    email = f"test_press_o_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{BASE_URL}/api/auth/register-organization", json={
        "nome": "TEST", "cognome": "Press", "email": email, "password": "TestPass2026!",
        "org_name": f"TEST_PressOrg_{uuid.uuid4().hex[:6]}", "telefono": "+393331234567", "accept_terms": True})
    assert r.status_code == 200, r.text
    u = db().users.find_one({"email": email}, {"_id": 0})
    S["other_org"] = u["org_id"]
    S["other_email"] = email
    return login(email, "TestPass2026!")


# ---- activation / gating ----
def test_inactive_org_403(other):
    r = other.get(f"{BASE_URL}/api/press/dashboard")
    assert r.status_code == 403
    assert "non attivo" in r.json()["detail"]
    st = other.get(f"{BASE_URL}/api/press/status").json()
    assert st["active"] is False


def test_sa_list_and_activate_other(sa, other):
    r = sa.get(f"{BASE_URL}/api/platform/press/orgs")
    assert r.status_code == 200
    rows = {o["org_id"]: o for o in r.json()}
    assert rows[ORG]["active"] is True
    assert rows[S["other_org"]]["active"] is False
    r = sa.post(f"{BASE_URL}/api/platform/press/orgs/{S['other_org']}/activate", json={"active": True})
    assert r.status_code == 200 and r.json()["active"] is True
    assert other.get(f"{BASE_URL}/api/press/dashboard").status_code == 200
    rows = {o["org_id"]: o for o in sa.get(f"{BASE_URL}/api/platform/press/orgs").json()}
    assert rows[S["other_org"]]["active"] is True
    assert sa.post(f"{BASE_URL}/api/platform/press/orgs/nope_org/activate", json={"active": True}).status_code == 404


def test_non_sa_cannot_activate(qa):
    r = qa.post(f"{BASE_URL}/api/platform/press/orgs/{ORG}/activate", json={"active": True})
    assert r.status_code in (401, 403)


# ---- generation (1 real AI call) ----
def test_event_data_and_generate(qa):
    r = qa.get(f"{BASE_URL}/api/press/events/{EV}/data", params={"tipo": "post_evento"})
    assert r.status_code == 200
    j = r.json()
    assert j["data"]["nome_evento"] == "Maratona QA"
    assert "Risultati / vincitori" in j["missing"]
    t = time.time()
    r = qa.post(f"{BASE_URL}/api/press/generate", json={"event_id": EV, "tipo": "presentazione", "extra": "", "tono": "istituzionale"}, timeout=120)
    print("AI seconds", round(time.time() - t, 1))
    assert r.status_code == 200, r.text
    rel = r.json()
    assert rel["status"] == "bozza" and rel["titolo"] and rel["testo"]
    S["rid"] = rel["id"]
    assert qa.post(f"{BASE_URL}/api/press/generate", json={"event_id": EV, "tipo": "xxx"}).status_code == 400


def test_save_versions_approve_reset(qa):
    rid = S["rid"]
    r = qa.put(f"{BASE_URL}/api/press/releases/{rid}", json={"titolo": "TEST_Titolo", "testo": "Corpo di prova.\n\nSecondo paragrafo.",
                                                            "citazioni": [{"testo": "Ciao", "autore": "Org"}], "foto": [{"url": "https://x.it/a.jpg", "didascalia": "c"}],
                                                            "oggetto_email": "TEST oggetto"})
    assert r.status_code == 200 and r.json()["titolo"] == "TEST_Titolo"
    g = qa.get(f"{BASE_URL}/api/press/releases/{rid}").json()
    assert g["titolo"] == "TEST_Titolo" and len(g["versions"]) >= 2
    a = qa.post(f"{BASE_URL}/api/press/releases/{rid}/approve")
    assert a.status_code == 200 and a.json()["approved_at"]
    qa.put(f"{BASE_URL}/api/press/releases/{rid}", json={"titolo": "TEST_Titolo2", "testo": "Corpo."})
    g = qa.get(f"{BASE_URL}/api/press/releases/{rid}").json()
    assert g["approved_at"] is None and g["status"] == "bozza"
    p = qa.get(f"{BASE_URL}/api/press/releases/{rid}/preview")
    assert p.status_code == 200 and "TEST_Titolo2" in p.text


# ---- isolation ----
def test_cross_org_isolation(other):
    rid = S["rid"]
    assert other.get(f"{BASE_URL}/api/press/releases/{rid}").status_code == 404
    assert other.put(f"{BASE_URL}/api/press/releases/{rid}", json={"titolo": "hack"}).status_code == 404
    assert other.post(f"{BASE_URL}/api/press/releases/{rid}/approve").status_code == 404
    assert other.get(f"{BASE_URL}/api/press/events/{EV}/data").status_code == 404
    d = other.get(f"{BASE_URL}/api/press/dashboard").json()
    assert all(x["org_id"] == S["other_org"] for x in d["releases"]) and d["total"] == 0


# ---- contacts ----
def test_contacts_crud(qa, other):
    r = qa.post(f"{BASE_URL}/api/press/contacts", json={"nome": "Mario", "cognome": "TEST_Rossi", "email": "Test_Press1@Example.com",
                                                        "testata": "Gazzetta", "tipologia_media": "Quotidiano", "regione": "Lombardia"})
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["email"] == "test_press1@example.com" and "unsub_token" not in c
    S["cid"] = c["id"]
    assert qa.post(f"{BASE_URL}/api/press/contacts", json={"email": "TEST_PRESS1@example.com"}).status_code == 400
    assert qa.post(f"{BASE_URL}/api/press/contacts", json={"email": "bad"}).status_code == 400
    r = qa.put(f"{BASE_URL}/api/press/contacts/{c['id']}", json={**c, "testata": "Corriere"})
    assert r.status_code == 200 and r.json()["testata"] == "Corriere"
    assert other.put(f"{BASE_URL}/api/press/contacts/{c['id']}", json={"email": "x@y.it"}).status_code == 404
    assert other.delete(f"{BASE_URL}/api/press/contacts/{c['id']}").status_code == 404
    assert all(x["org_id"] == S["other_org"] for x in other.get(f"{BASE_URL}/api/press/contacts").json())
    # second contact: suspended, third: deleted
    r2 = qa.post(f"{BASE_URL}/api/press/contacts", json={"email": "test_press2@example.com", "stato": "sospeso", "tipologia_media": "Radio"})
    assert r2.status_code == 200
    r3 = qa.post(f"{BASE_URL}/api/press/contacts", json={"email": "test_press3@example.com"}).json()
    assert qa.delete(f"{BASE_URL}/api/press/contacts/{r3['id']}").status_code == 200
    emails = [x["email"] for x in qa.get(f"{BASE_URL}/api/press/contacts").json()]
    assert "test_press3@example.com" not in emails
    found = qa.get(f"{BASE_URL}/api/press/contacts", params={"q": "corriere"}).json()
    assert [x["email"] for x in found] == ["test_press1@example.com"]
    assert [x["email"] for x in qa.get(f"{BASE_URL}/api/press/contacts", params={"media": "Radio"}).json()] == ["test_press2@example.com"]


def test_import_and_export(qa):
    csv_text = "nome;cognome;email;testata;tipologia\nA;TEST_A;test_imp1@example.com;T1;Blog\nB;TEST_B;TEST_IMP1@example.com;T2;Blog\nC;TEST_C;notanemail;T3;Blog\nD;TEST_D;test_press1@example.com;T4;Blog\n"
    r = qa.post(f"{BASE_URL}/api/press/contacts/import", json={"csv_text": csv_text, "base_giuridica": "legittimo_interesse"})
    assert r.status_code == 200, r.text
    assert r.json() == {"added": 1, "duplicates": 2, "invalid": 1}
    assert qa.post(f"{BASE_URL}/api/press/contacts/import", json={"csv_text": csv_text, "base_giuridica": "zzz"}).status_code == 400
    e = qa.get(f"{BASE_URL}/api/press/contacts/export")
    assert e.status_code == 200 and "text/csv" in e.headers["content-type"]
    assert "test_imp1@example.com" in e.text and "unsub_token" not in e.text


def test_recipients_count(qa):
    db().press_contacts.insert_one({"id": "TEST_nobasis", "org_id": ORG, "email": "test_nobasis@example.com", "stato": "attivo", "base_giuridica": None, "unsub_token": "TEST_tok_nb"})
    r = qa.post(f"{BASE_URL}/api/press/releases/{S['rid']}/recipients", json={})
    assert r.status_code == 200
    # active+basis: test_press1, test_imp1 ; excluded: sospeso + no basis
    assert r.json()["count"] == 2 and r.json()["excluded"] == 2
    r = qa.post(f"{BASE_URL}/api/press/releases/{S['rid']}/recipients", json={"media": ["Blog"]})
    assert r.json()["count"] == 1


def test_unsubscribe_cannot_reactivate(qa):
    tok = db().press_contacts.find_one({"id": S["cid"]})["unsub_token"]
    r = requests.get(f"{BASE_URL}/api/public/press/unsubscribe/{tok}")
    assert r.status_code == 200 and "Non riceverai" in r.text
    assert db().press_contacts.find_one({"id": S["cid"]})["stato"] == "opposto"
    c = [x for x in qa.get(f"{BASE_URL}/api/press/contacts").json() if x["id"] == S["cid"]][0]
    r = qa.put(f"{BASE_URL}/api/press/contacts/{S['cid']}", json={**c, "stato": "attivo"})
    assert r.status_code == 200 and r.json()["stato"] == "opposto"
    assert db().press_contacts.find_one({"id": S["cid"]})["stato"] == "opposto"
    assert "Link non valido" in requests.get(f"{BASE_URL}/api/public/press/unsubscribe/bogus").text


# ---- settings ----
def test_settings(qa):
    r = qa.put(f"{BASE_URL}/api/press/settings", json={"sender_name": "QA Ufficio Stampa", "sender_email": "x@crmevent.it"})
    assert r.status_code == 400
    r = qa.put(f"{BASE_URL}/api/press/settings", json={"sender_name": "QA Ufficio Stampa", "sender_email": "stampa@crmeventqa.it",
                                                       "reply_to": "rt@crmeventqa.it", "referente": "TEST Ref", "telefono": "+39 333"})
    assert r.status_code == 200 and r.json()["sender_email"] == "stampa@crmeventqa.it" and r.json()["sender_verified"] is False
    assert qa.get(f"{BASE_URL}/api/press/settings").json()["settings"]["referente"] == "TEST Ref"
    v = qa.post(f"{BASE_URL}/api/press/settings/verify-sender")
    assert v.status_code == 400 and v.json()["detail"] == "Brevo non configurato sulla piattaforma"


# ---- send flow w/o Brevo ----
def test_send_flow_without_brevo(qa):
    rid = S["rid"]
    assert qa.post(f"{BASE_URL}/api/press/releases/{rid}/send", json={"mode": "now"}).status_code == 400  # not approved
    t = qa.post(f"{BASE_URL}/api/press/releases/{rid}/test", json={"email": "qa.eventi@crmeventqa.it"})
    assert t.status_code == 400 and "verificato" in t.json()["detail"]
    assert qa.post(f"{BASE_URL}/api/press/releases/{rid}/approve").status_code == 200
    s = qa.post(f"{BASE_URL}/api/press/releases/{rid}/send", json={"mode": "now"})
    assert s.status_code == 400 and "verificato" in s.json()["detail"]
    # simulate verified sender to reach delivery path
    db().press_settings.update_one({"org_id": ORG}, {"$set": {"sender_verified": True}})
    s = qa.post(f"{BASE_URL}/api/press/releases/{rid}/send", json={"mode": "scheduled", "send_at": "2020-01-01T10:00:00+01:00"})
    assert s.status_code == 400
    s = qa.post(f"{BASE_URL}/api/press/releases/{rid}/send", json={"mode": "scheduled", "send_at": "2099-01-01T10:00:00+01:00"})
    assert s.status_code == 200 and s.json()["status"] == "programmato" and s.json()["recipients_count"] == 1
    c = qa.post(f"{BASE_URL}/api/press/releases/{rid}/cancel")
    assert c.status_code == 200
    g = qa.get(f"{BASE_URL}/api/press/releases/{rid}").json()
    assert g["status"] == "bozza" and g["approved_at"] is None
    assert qa.post(f"{BASE_URL}/api/press/releases/{rid}/cancel").status_code == 400
    qa.post(f"{BASE_URL}/api/press/releases/{rid}/approve")
    s = qa.post(f"{BASE_URL}/api/press/releases/{rid}/send", json={"mode": "now"})
    assert s.status_code == 200, s.text
    for _ in range(20):
        g = qa.get(f"{BASE_URL}/api/press/releases/{rid}").json()
        if g["status"] not in ("programmato", "in_invio"):
            break
        time.sleep(1)
    assert g["status"] == "errore" and g["error"] == "Brevo non configurato"
    rep = qa.get(f"{BASE_URL}/api/press/releases/{rid}/report")
    assert rep.status_code == 200
    assert qa.put(f"{BASE_URL}/api/press/releases/{rid}", json={"titolo": "x"}).status_code in (200, 400)


# ---- automation + role guard ----
def test_automation(qa):
    r = qa.put(f"{BASE_URL}/api/press/automations/{EV}", json={"enabled": True, "delay_days": 2, "send_time": "11:30"})
    assert r.status_code == 200 and r.json()["require_approval"] is True
    a = [x for x in qa.get(f"{BASE_URL}/api/press/settings").json()["automations"] if x["event_id"] == EV][0]
    assert a["enabled"] is True and a["delay_days"] == 2 and a["send_time"] == "11:30"
    assert qa.put(f"{BASE_URL}/api/press/automations/{EV}", json={"enabled": True, "delay_days": 99}).status_code == 400
    assert qa.put(f"{BASE_URL}/api/press/automations/{EV}", json={"enabled": False}).status_code == 200


def test_member_readonly(mem):
    st = mem.get(f"{BASE_URL}/api/press/status").json()
    assert st["active"] is True and st["can_edit"] is False
    assert mem.get(f"{BASE_URL}/api/press/dashboard").status_code == 200
    assert mem.get(f"{BASE_URL}/api/press/contacts").status_code == 200
    assert mem.post(f"{BASE_URL}/api/press/contacts", json={"email": "test_m@example.com"}).status_code == 403
    assert mem.put(f"{BASE_URL}/api/press/releases/{S['rid']}", json={"titolo": "m"}).status_code == 403
    assert mem.put(f"{BASE_URL}/api/press/settings", json={"sender_name": "m"}).status_code == 403
    assert mem.put(f"{BASE_URL}/api/press/automations/{EV}", json={"enabled": True}).status_code == 403
    assert mem.post(f"{BASE_URL}/api/press/generate", json={"event_id": EV, "tipo": "presentazione"}).status_code == 403


def test_cron_auth():
    assert requests.post(f"{BASE_URL}/api/cron/press-tick").status_code == 401
    r = requests.post(f"{BASE_URL}/api/cron/press-tick", headers={"Authorization": f"Bearer {os.environ['WEBHOOK_CRON_SECRET']}"})
    assert r.status_code == 200 and r.json()["accepted"] is True


def test_deactivate_other(sa, other):
    assert sa.post(f"{BASE_URL}/api/platform/press/orgs/{S['other_org']}/activate", json={"active": False}).status_code == 200
    assert other.get(f"{BASE_URL}/api/press/dashboard").status_code == 403
