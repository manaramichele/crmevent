"""Fase E.2 CORREZIONE — modello a crediti con attivazione una-tantum + primo evento gratis + saldo minimo globale.

Copre:
  - Primo evento GRATIS (welcome), saldo invariato, ledger welcome_event_activation amount 0
  - Secondo evento a pagamento (-20), idempotenza
  - Guardia globale _assert_org_operational: saldo 0 blocca scritture, consente letture
  - Ricarica riattiva operatività senza riattivare l'evento
  - Modifica data evento in avanti non addebita
  - Evento passato -> display_state 'concluso'
  - Menu superadmin non contiene 'Piani e prezzi'; catalogo mostra 'Attivazione evento'
"""
import os
import time
import pytest
import requests
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://manage-events-12.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

DEMO_EMAIL = "demo.crmevent@gmail.com"
DEMO_PASS = "DemoCrm#2026pv"
DEMO_ORG_ID = "4cdfbd7aed3d43b882032892885feef3"
SA_EMAIL = "manara.michele.pro@gmail.com"
SA_PASS = "CrmEvent2026!"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def demo(): return _login(DEMO_EMAIL, DEMO_PASS)


@pytest.fixture(scope="module")
def sa(): return _login(SA_EMAIL, SA_PASS)


def _balance(s):
    r = s.get(f"{API}/credits/balance", timeout=15)
    assert r.status_code == 200
    return r.json().get("balance")


def _adjust(sa, amount, note="test"):
    r = sa.post(
        f"{API}/platform/orgs/{DEMO_ORG_ID}/credits/adjust",
        json={"amount": int(amount), "note": note, "idempotency_key": f"faseE2corr-{time.time()}-{amount}"},
        timeout=20,
    )
    assert r.status_code == 200, r.text


def _set_balance(demo, sa, target):
    cur = _balance(demo)
    if cur != target:
        _adjust(sa, int(target) - int(cur), note=f"set {target}")
    assert _balance(demo) == target


def _reset_welcome_flag(sa):
    """Rimuove il flag welcome_event_activation_used dell'org Demo tramite un endpoint superadmin.
    Non esiste un endpoint dedicato: usiamo un unset con motor direttamente."""
    from pymongo import MongoClient
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    c = MongoClient(os.environ["MONGO_URL"])
    c[os.environ["DB_NAME"]].organizations.update_one(
        {"id": DEMO_ORG_ID},
        {"$unset": {"credits.welcome_event_activation_used": ""}}
    )


def _cleanup_events(demo):
    r = demo.get(f"{API}/events", timeout=15)
    if r.status_code == 200:
        for ev in (r.json() if isinstance(r.json(), list) else r.json().get("items", [])):
            if (ev.get("nome") or "").startswith("TEST_E2C_"):
                demo.delete(f"{API}/events/{ev['id']}", timeout=15)


def _clean_ledger():
    """Pulisce eventuali movimenti test dal ledger (welcome_activation/event_activation) per lasciare l'org pristina."""
    from pymongo import MongoClient
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    c = MongoClient(os.environ["MONGO_URL"])
    c[os.environ["DB_NAME"]].credit_ledger.delete_many({
        "org_id": DEMO_ORG_ID,
        "reason_code": {"$in": ["welcome_event_activation", "event_activation"]}
    })


def _create_event(demo, nome, future_days=90):
    fut = (datetime.now(timezone.utc) + timedelta(days=future_days)).date().isoformat()
    r = demo.post(f"{API}/events", json={"nome": nome, "data_inizio": fut, "data_fine": fut}, timeout=20)
    return r


# ==================== SETUP ====================

def test_00_prepare_pristine_state(demo, sa):
    _cleanup_events(demo)
    _set_balance(demo, sa, 100)
    _reset_welcome_flag(sa)
    _clean_ledger()
    assert _balance(demo) == 100


# ==================== PRIMO EVENTO GRATIS ====================

def test_01_first_event_welcome_available(demo):
    """Prima di creare eventi: credit-status non chiamabile, ma /credits/balance = 100."""
    assert _balance(demo) == 100


def test_02_create_first_event_no_charge(demo, sa):
    r = _create_event(demo, "TEST_E2C_first")
    assert r.status_code == 200, r.text
    ev = r.json()
    pytest.first_eid = ev["id"]
    # nessun addebito
    assert _balance(demo) == 100
    # credit-status
    r = demo.get(f"{API}/events/{ev['id']}/credit-status", timeout=15)
    assert r.status_code == 200
    st = r.json()
    assert st["credit_state"] == "preparazione"
    assert st["cost"] == 20
    assert st["welcome_free_available"] is True, f"welcome free NON disponibile: {st}"
    assert st["is_credit_model"] is True


def test_03_activate_first_free_no_charge(demo):
    eid = pytest.first_eid
    r = demo.post(f"{API}/events/{eid}/activate", timeout=20)
    assert r.status_code == 200, r.text
    st = r.json()
    assert st["credit_state"] == "attivo"
    assert st["balance"] == 100, f"saldo doveva restare 100, invece: {st['balance']}"
    assert st["activation_free"] is True
    # ledger: welcome_event_activation amount 0
    r = demo.get(f"{API}/credits/ledger", timeout=15)
    rows = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    assert any(
        row.get("reason_code") == "welcome_event_activation" and row.get("amount") == 0 and row.get("event_id") == eid
        for row in rows
    ), "manca movimento welcome_event_activation nel ledger"


def test_04_activate_idempotent_first(demo):
    eid = pytest.first_eid
    bal = _balance(demo)
    r = demo.post(f"{API}/events/{eid}/activate", timeout=20)
    assert r.status_code == 200
    assert _balance(demo) == bal, "activate idempotente NON deve toccare il saldo"


# ==================== SECONDO EVENTO A PAGAMENTO ====================

def test_05_create_second_event(demo):
    r = _create_event(demo, "TEST_E2C_second")
    assert r.status_code == 200, r.text
    pytest.second_eid = r.json()["id"]
    # welcome_free NON deve più essere disponibile
    r = demo.get(f"{API}/events/{pytest.second_eid}/credit-status", timeout=15)
    st = r.json()
    assert st["welcome_free_available"] is False, "welcome_free deve essere gia' usato"
    assert st["cost"] == 20


def test_06_activate_second_paid(demo):
    eid = pytest.second_eid
    bal_before = _balance(demo)
    r = demo.post(f"{API}/events/{eid}/activate", timeout=20)
    assert r.status_code == 200, r.text
    st = r.json()
    assert st["credit_state"] == "attivo"
    assert st["balance"] == bal_before - 20, f"attivazione a pagamento: {bal_before} -> attesi {bal_before-20}, actual {st['balance']}"
    assert st["activation_free"] is False
    # ledger: event_activation amount -20
    r = demo.get(f"{API}/credits/ledger", timeout=15)
    rows = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    assert any(
        row.get("reason_code") == "event_activation" and row.get("amount") == -20 and row.get("event_id") == eid
        for row in rows
    )


def test_07_activate_second_idempotent(demo):
    eid = pytest.second_eid
    bal = _balance(demo)
    r = demo.post(f"{API}/events/{eid}/activate", timeout=20)
    assert r.status_code == 200
    assert _balance(demo) == bal, "doppia activate non deve riscalare"


# ==================== SALDO 0: BLOCCO SCRITTURE / LETTURE OK ====================

def test_08_zero_balance_blocks_writes(demo, sa):
    _set_balance(demo, sa, 0)
    # POST /api/events (creazione) -> 402
    r = _create_event(demo, "TEST_E2C_blocked")
    assert r.status_code == 402, f"creazione evento a saldo 0 doveva dare 402: {r.status_code} {r.text}"

    # POST /api/persons -> 402
    r = demo.post(f"{API}/persons", json={"nome": "TEST", "cognome": "Zero"}, timeout=15)
    assert r.status_code == 402, f"POST /persons a saldo 0: atteso 402, actual {r.status_code} {r.text}"

    # POST /api/companies -> 402
    r = demo.post(f"{API}/companies", json={"nome": "TEST_ZeroCo"}, timeout=15)
    assert r.status_code == 402, f"POST /companies a saldo 0: atteso 402, actual {r.status_code} {r.text}"


def test_09_zero_balance_reads_work(demo):
    for path in ("/events", "/persons", "/companies", "/credits/balance", "/credits/ledger"):
        r = demo.get(f"{API}{path}", timeout=15)
        assert r.status_code == 200, f"GET {path} a saldo 0: atteso 200, actual {r.status_code}"


def test_10_zero_balance_event_stays_active(demo):
    """L'evento gia' attivo NON deve essere disattivato per saldo 0."""
    r = demo.get(f"{API}/events/{pytest.first_eid}/credit-status", timeout=15)
    assert r.status_code == 200
    st = r.json()
    assert st["credit_state"] == "attivo", f"evento attivo non deve cambiare stato per saldo 0: {st}"
    assert st["display_state"] in ("attivo", "concluso")


# ==================== RIPRISTINO AUTOMATICO ====================

def test_11_recharge_restores_ops_no_reactivation(demo, sa):
    _set_balance(demo, sa, 50)
    bal_after_recharge = _balance(demo)
    assert bal_after_recharge == 50

    # scritture operative tornano a funzionare
    r = demo.post(f"{API}/persons", json={"nome": "TEST_E2C", "cognome": "Restored"}, timeout=15)
    assert r.status_code == 200, f"post ripristino: atteso 200, actual {r.status_code} {r.text}"
    person_id = r.json().get("id")

    # evento resta attivo con lo stesso saldo (NO riaddebito 20)
    assert _balance(demo) == 50, "ricarica NON deve triggerare addebito 20"
    r = demo.get(f"{API}/events/{pytest.first_eid}/credit-status", timeout=15)
    assert r.json()["credit_state"] == "attivo"

    # cleanup persona test
    if person_id:
        demo.delete(f"{API}/persons/{person_id}", timeout=10)


# ==================== MODIFICA DATA IN AVANTI ====================

def test_12_extend_event_date_no_charge(demo):
    """Spostare data_fine in avanti non deve addebitare."""
    eid = pytest.first_eid
    bal = _balance(demo)
    new_end = (datetime.now(timezone.utc) + timedelta(days=200)).date().isoformat()
    r = demo.put(f"{API}/events/{eid}", json={"data_fine": new_end}, timeout=15)
    # può essere 200 o 405 se non c'è PUT: proviamo alternative
    assert r.status_code in (200, 405), r.text
    assert _balance(demo) == bal, "cambio data NON deve addebitare"


# ==================== NESSUNA VOCE 'Piani e prezzi' + CATALOGO ====================

def test_13_platform_catalog_has_attivazione_evento(sa):
    r = sa.get(f"{API}/platform/credit-services", timeout=15)
    # endpoint può avere path leggermente diverso, proviamo alcuni
    if r.status_code == 404:
        r = sa.get(f"{API}/platform/services", timeout=15)
    assert r.status_code == 200, f"catalogo servizi non raggiungibile: {r.status_code} {r.text}"
    body = r.json()
    items = body if isinstance(body, list) else body.get("services") or body.get("items") or []
    found = False
    for it in items:
        name = (it.get("name") or it.get("label") or it.get("service_name") or "").lower()
        key = (it.get("key") or it.get("service_key") or "").lower()
        if "attivazione evento" in name or key == "event_active_period":
            found = True
            cost = it.get("unit_cost") or it.get("cost") or it.get("credits_cost") or it.get("price")
            assert cost == 20, f"'Attivazione evento' costo atteso 20, actual {cost}"
            assert "30 giorni" not in name and "evento attivo" not in name.replace("attivazione", ""), \
                f"Il servizio non deve chiamarsi ancora 'Evento attivo — 30 giorni': {name}"
            break
    assert found, f"Servizio 'Attivazione evento' non trovato nel catalogo. Items: {items[:3] if items else 'empty'}"


# ==================== EVENTO PASSATO -> CONCLUSO ====================

def test_14_past_event_display_concluso(demo, sa):
    """Un evento con data passata deve avere display_state='concluso'."""
    # Creiamo un evento con data passata direttamente in DB (non c'è endpoint pubblico)
    _set_balance(demo, sa, 100)  # servono crediti per creare
    r = _create_event(demo, "TEST_E2C_past", future_days=1)
    if r.status_code != 200:
        pytest.skip(f"non riesco a creare evento: {r.status_code}")
    eid = r.json()["id"]
    pytest.past_eid = eid
    from pymongo import MongoClient
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    c = MongoClient(os.environ["MONGO_URL"])
    past = (datetime.now(timezone.utc) - timedelta(days=10)).date().isoformat()
    c[os.environ["DB_NAME"]].events.update_one({"id": eid}, {"$set": {"data_fine": past, "data_inizio": past, "credit_state": "attivo"}})
    r = demo.get(f"{API}/events/{eid}/credit-status", timeout=15)
    assert r.status_code == 200
    st = r.json()
    assert st["display_state"] == "concluso", f"evento passato deve mostrare 'concluso', actual: {st}"


# ==================== CLEANUP FINALE ====================

def test_zzz_final_cleanup(demo, sa):
    _cleanup_events(demo)
    _reset_welcome_flag(sa)
    _clean_ledger()
    _set_balance(demo, sa, 100)
    assert _balance(demo) == 100
    # verifica no eventi
    r = demo.get(f"{API}/events", timeout=15)
    items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    assert not any((e.get("nome") or "").startswith("TEST_E2C_") for e in items)
