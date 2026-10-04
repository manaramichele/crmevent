"""Iteration 40 - Consumo crediti centralizzato per Assistente CRMEvent (POST /api/support/chat).

Verifica che:
- domanda utile (answered=true) addebita 1 credito del servizio ai_assistant;
- domanda non utile (fuori contesto, answered=false) NON addebita (release);
- idempotenza per stesso request_id;
- due request_id diversi => due addebiti;
- saldo insufficiente => HTTP 402 e nessuna risposta AI;
- isolamento multi-tenant: addebito solo sull'org dell'utente autenticato;
- /api/credits/balance aggiornato immediatamente.
"""
import os
import uuid
import time
import pytest
import requests

def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    env_path = "/app/frontend/.env"
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().strip('"').rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL non configurato")


BASE_URL = _load_backend_url()

QA_EMAIL = "qa.eventi@crmeventqa.it"
QA_PASSWORD = "QaEvents2026!"
QA_ORG_ID = "org_qa_eventi"
SA_EMAIL = "manara.michele.pro@gmail.com"
SA_PASSWORD = "CrmEvent2026!"
SERVICE_KEY = "ai_assistant"
SERVICE_COST = 1  # da catalogo (asserito nel test)

USEFUL_Q = "Come posso creare un nuovo evento in CRMEvent?"
NON_USEFUL_Q = "Qual e la ricetta della carbonara?"


# ---------------- Fixtures ----------------
@pytest.fixture(scope="module")
def qa_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": QA_EMAIL, "password": QA_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Login QA fallito: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def sa_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": SA_EMAIL, "password": SA_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Login SA fallito: {r.status_code} {r.text}"
    return s


# ---------------- Helpers ----------------
def _balance(sess) -> int:
    r = sess.get(f"{BASE_URL}/api/credits/balance", timeout=30)
    assert r.status_code == 200, f"/credits/balance: {r.status_code} {r.text}"
    return int(r.json()["balance"])


def _ledger(sa_sess, org_id=QA_ORG_ID, limit=50):
    r = sa_sess.get(f"{BASE_URL}/api/platform/orgs/{org_id}/credits?limit={limit}", timeout=30)
    assert r.status_code == 200, f"ledger: {r.status_code} {r.text}"
    return r.json()


def _adjust(sa_sess, org_id, amount, note):
    r = sa_sess.post(f"{BASE_URL}/api/platform/orgs/{org_id}/credits/adjust",
                     json={"amount": amount, "note": note,
                           "idempotency_key": f"iter40-{uuid.uuid4().hex[:10]}"},
                     timeout=30)
    assert r.status_code == 200, f"adjust: {r.status_code} {r.text}"
    return r.json()


def _chat(sess, q, request_id=None, conversation_id=None):
    payload = {"question": q}
    if request_id:
        payload["request_id"] = request_id
    if conversation_id:
        payload["conversation_id"] = conversation_id
    return sess.post(f"{BASE_URL}/api/support/chat", json=payload, timeout=120)


# ---------------- Tests ----------------
def test_01_service_catalog_ai_assistant(sa_session):
    """Il servizio ai_assistant esiste nel catalogo con costo 1 e consumo attivo."""
    r = sa_session.get(f"{BASE_URL}/api/platform/credit-services", timeout=30)
    assert r.status_code == 200, r.text
    rows = r.json()
    if isinstance(rows, dict):
        rows = rows.get("services", [])
    svc = next((x for x in rows if x.get("key") == SERVICE_KEY), None)
    assert svc is not None, "Servizio ai_assistant assente nel catalogo"
    assert svc.get("active") is True, f"Servizio non attivo: {svc}"
    assert int(svc.get("unit_cost")) == SERVICE_COST, f"Costo diverso da {SERVICE_COST}: {svc}"


def test_02_useful_question_debits_one_credit(qa_session, sa_session):
    """Domanda utile => -1 credito, ledger ai_assistant committed."""
    b0 = _balance(qa_session)
    rid = f"iter40-useful-{uuid.uuid4().hex[:10]}"
    r = _chat(qa_session, USEFUL_Q, request_id=rid)
    assert r.status_code == 200, f"support/chat: {r.status_code} {r.text}"
    data = r.json()
    assert data.get("answered") is True, f"Attesa risposta utile, ricevuto: {data}"
    # saldo aggiornato
    b1 = _balance(qa_session)
    assert b1 == b0 - SERVICE_COST, f"Saldo atteso {b0 - SERVICE_COST}, trovato {b1}"
    # ledger
    led = _ledger(sa_session)
    row = next((x for x in led["ledger"]
                if x.get("reason_code") == SERVICE_KEY
                and x.get("note") == "Assistente CRMEvent"
                and x.get("status") == "committed"
                and x.get("amount") == -SERVICE_COST), None)
    assert row is not None, f"Movimento committed ai_assistant non trovato nel ledger: {led['ledger'][:5]}"
    assert row.get("user_id"), "user_id mancante nel movimento"
    assert row.get("org_id") == QA_ORG_ID, f"org_id errato: {row.get('org_id')}"


def test_03_idempotency_same_request_id(qa_session, sa_session):
    """Stesso request_id => un solo addebito."""
    rid = f"iter40-idem-{uuid.uuid4().hex[:10]}"
    b0 = _balance(qa_session)
    r1 = _chat(qa_session, USEFUL_Q, request_id=rid)
    assert r1.status_code == 200, r1.text
    assert r1.json().get("answered") is True
    b1 = _balance(qa_session)
    assert b1 == b0 - SERVICE_COST, f"primo addebito: atteso {b0 - SERVICE_COST} trovato {b1}"
    # secondo invio con stesso request_id
    r2 = _chat(qa_session, USEFUL_Q, request_id=rid)
    assert r2.status_code == 200, r2.text
    b2 = _balance(qa_session)
    assert b2 == b1, f"Idempotenza violata: saldo cambiato da {b1} a {b2}"
    # un solo movimento col medesimo idempotency_key
    led = _ledger(sa_session, limit=100)
    key = f"ai_assistant:{rid}"
    matching = [x for x in led["ledger"] if x.get("idempotency_key") == key]
    assert len(matching) == 1, f"Attesa 1 riga idempotente, trovate {len(matching)}: {matching}"


def test_04_two_different_request_ids_debit_twice(qa_session):
    """Due request_id diversi => -2."""
    b0 = _balance(qa_session)
    r1 = _chat(qa_session, USEFUL_Q, request_id=f"iter40-diff1-{uuid.uuid4().hex[:8]}")
    assert r1.status_code == 200 and r1.json().get("answered") is True
    r2 = _chat(qa_session, USEFUL_Q, request_id=f"iter40-diff2-{uuid.uuid4().hex[:8]}")
    assert r2.status_code == 200 and r2.json().get("answered") is True
    b1 = _balance(qa_session)
    assert b1 == b0 - 2 * SERVICE_COST, f"Atteso {b0 - 2 * SERVICE_COST}, trovato {b1}"


def test_05_non_useful_question_no_debit_and_released(qa_session, sa_session):
    """Domanda fuori contesto => nessun addebito; ledger movimento released."""
    b0 = _balance(qa_session)
    rid = f"iter40-nouseful-{uuid.uuid4().hex[:10]}"
    r = _chat(qa_session, NON_USEFUL_Q, request_id=rid)
    assert r.status_code == 200, r.text
    data = r.json()
    # Il sistema deve rispondere con answered=false (fallback / fuori contesto)
    assert data.get("answered") is False, f"Attesa answered=false per domanda fuori contesto: {data}"
    b1 = _balance(qa_session)
    assert b1 == b0, f"Saldo cambiato per domanda non utile: {b0} -> {b1}"
    led = _ledger(sa_session, limit=100)
    key = f"ai_assistant:{rid}"
    row = next((x for x in led["ledger"] if x.get("idempotency_key") == key), None)
    assert row is not None, "Movimento ai_assistant non registrato per domanda non utile"
    assert row.get("status") == "released", f"Status atteso 'released', trovato {row.get('status')}"


def test_06_insufficient_balance_returns_402_and_no_charge(qa_session, sa_session):
    """Azzera saldo org QA, chiama support/chat => 402 (nessuna risposta AI, nessun addebito commit).
    Ripristina il saldo con un adjust positivo di pari importo."""
    b0 = _balance(qa_session)
    adjust_amount = -b0 if b0 > 0 else 0
    try:
        if adjust_amount < 0:
            _adjust(sa_session, QA_ORG_ID, adjust_amount, "iter40 azzera per test insufficiente")
        assert _balance(qa_session) == 0, "Saldo non azzerato correttamente"
        rid = f"iter40-noc-{uuid.uuid4().hex[:10]}"
        r = _chat(qa_session, USEFUL_Q, request_id=rid)
        assert r.status_code == 402, f"Atteso 402, ricevuto {r.status_code}: {r.text}"
        # Nessun movimento committed per questo request_id
        led = _ledger(sa_session, limit=100)
        key = f"ai_assistant:{rid}"
        committed = [x for x in led["ledger"]
                     if x.get("idempotency_key") == key and x.get("status") == "committed"]
        assert not committed, f"Movimento committed non atteso: {committed}"
        # Saldo rimasto a 0
        assert _balance(qa_session) == 0, "Saldo modificato dopo 402"
    finally:
        # RIPRISTINO sempre, anche su failure
        if adjust_amount < 0:
            _adjust(sa_session, QA_ORG_ID, -adjust_amount, "iter40 ripristino saldo post-test")
        # verifica che il saldo sia tornato a b0
        time.sleep(0.3)
        br = _balance(qa_session)
        assert br == b0, f"Ripristino saldo fallito: era {b0}, ora {br}"


def test_07_multi_tenant_isolation(sa_session):
    """Nessun movimento ai_assistant di iter40 su altre org diverse da org_qa_eventi."""
    # Elenca orgs e ispeziona ledger (prime 100 righe) di ciascuna; verifica che
    # i movimenti con note='Assistente CRMEvent' siano SOLO per QA_ORG_ID.
    r = sa_session.get(f"{BASE_URL}/api/platform/organizations", timeout=30)
    if r.status_code != 200:
        pytest.skip(f"Lista org non accessibile: {r.status_code}")
    orgs = r.json()
    offenders = []
    for o in orgs:
        oid = o.get("id") or o.get("org_id")
        if not oid or oid == QA_ORG_ID:
            continue
        led = _ledger(sa_session, org_id=oid, limit=100)
        for x in led.get("ledger", []):
            if x.get("reason_code") == SERVICE_KEY and x.get("note") == "Assistente CRMEvent":
                offenders.append({"org": oid, "row": x})
    assert not offenders, f"Addebiti ai_assistant trovati su altre org: {offenders[:3]}"


def test_08_balance_immediate_after_chat(qa_session):
    """/credits/balance deve riflettere subito il nuovo saldo dopo l'addebito."""
    b0 = _balance(qa_session)
    r = _chat(qa_session, USEFUL_Q, request_id=f"iter40-imm-{uuid.uuid4().hex[:8]}")
    assert r.status_code == 200 and r.json().get("answered") is True
    # Nessuna attesa aggiuntiva
    b1 = _balance(qa_session)
    assert b1 == b0 - SERVICE_COST, f"Saldo non aggiornato immediatamente: {b0} -> {b1}"
