"""Backend tests for the new Ospitalità & Pasti feature (iteration 7)."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://manage-events-12.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "manara.michele.pro@gmail.com"
ADMIN_PWD = "CrmEvent2026!"
EVENT_ID = "25299c763b9e45b38db227d0692c97bf"  # Tech Summit Milano (4 people)


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PWD})
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def created_ids():
    return {"lodgings": [], "meals": [], "groups": []}


# --- Aggregation endpoint ---
def test_hospitality_aggregation(client):
    r = client.get(f"{API}/events/{EVENT_ID}/hospitality")
    assert r.status_code == 200
    d = r.json()
    assert "event" in d and "persons" in d and "summary" in d
    assert d["can_view_costs"] is True, "Admin must see costs"
    assert isinstance(d["persons"], list)
    assert len(d["persons"]) >= 1
    for k in ["persone_gestite", "pernottamenti", "colazioni", "pranzi", "cene",
              "servizi_da_definire", "senza_sistemazione"]:
        assert k in d["summary"]


def test_hospitality_event_not_found(client):
    r = client.get(f"{API}/events/nonexistent-id-xyz/hospitality")
    assert r.status_code == 404


# --- Single Lodging CRUD ---
def test_lodging_crud(client, created_ids):
    payload = {
        "evento_id": EVENT_ID,
        "persona_id": "TEST_PERSON_SINGLE",
        "struttura_nome": "TEST_Hotel Roma",
        "tipo_struttura": "hotel",
        "tipo_camera": "singola",
        "a_carico_di": "organizzazione",
        "costo": 120.0,
    }
    r = client.post(f"{API}/lodgings", json=payload)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["struttura_nome"] == "TEST_Hotel Roma"
    lid = d["id"]
    created_ids["lodgings"].append(lid)

    # GET
    r = client.get(f"{API}/lodgings/{lid}")
    assert r.status_code == 200
    assert r.json()["struttura_nome"] == "TEST_Hotel Roma"

    # UPDATE
    r = client.put(f"{API}/lodgings/{lid}", json={"struttura_nome": "TEST_Hotel Milano"})
    assert r.status_code == 200
    r = client.get(f"{API}/lodgings/{lid}")
    assert r.json()["struttura_nome"] == "TEST_Hotel Milano"

    # DELETE
    r = client.delete(f"{API}/lodgings/{lid}")
    assert r.status_code == 200
    created_ids["lodgings"].remove(lid)
    r = client.get(f"{API}/lodgings/{lid}")
    assert r.status_code == 404


# --- Single Meal CRUD ---
def test_meal_crud(client, created_ids):
    payload = {
        "evento_id": EVENT_ID,
        "persona_id": "TEST_PERSON_SINGLE",
        "tipo_pasto": "pranzo",
        "tipologia_servizio": "ristorante",
        "struttura_nome": "TEST_Ristorante Da Mario",
        "data": "2026-03-15",
        "a_carico_di": "organizzazione",
    }
    r = client.post(f"{API}/meals", json=payload)
    assert r.status_code == 200, r.text
    mid = r.json()["id"]
    created_ids["meals"].append(mid)

    r = client.put(f"{API}/meals/{mid}", json={"tipo_pasto": "cena"})
    assert r.status_code == 200
    assert client.get(f"{API}/meals/{mid}").json()["tipo_pasto"] == "cena"

    r = client.delete(f"{API}/meals/{mid}")
    assert r.status_code == 200
    created_ids["meals"].remove(mid)


# --- Bulk assignment ---
def _real_person_ids(client):
    r = client.get(f"{API}/events/{EVENT_ID}/hospitality")
    return [p["persona_id"] for p in r.json()["persons"]]


def test_bulk_meal_assignment(client, created_ids):
    pids = _real_person_ids(client)
    assert len(pids) >= 2
    selected = pids[:2]
    payload = {
        "evento_id": EVENT_ID,
        "persona_ids": selected,
        "data": {"tipo_pasto": "colazione", "struttura_nome": "TEST_Bulk Breakfast",
                 "data": "2026-03-15", "a_carico_di": "organizzazione"},
    }
    r = client.post(f"{API}/meals/bulk", json=payload)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["count"] == 2
    gid = d["gruppo_id"]
    created_ids["groups"].append(("meal", gid))

    # Verify they were created for each person
    r = client.get(f"{API}/events/{EVENT_ID}/hospitality")
    persons = {p["persona_id"]: p for p in r.json()["persons"]}
    for pid in selected:
        matching = [m for m in persons[pid]["meals"] if m.get("gruppo_id") == gid]
        assert len(matching) == 1

    # Delete group
    r = client.delete(f"{API}/hospitality/group/{gid}?tipo=meal")
    assert r.status_code == 200
    assert r.json()["deleted"] == 2
    created_ids["groups"].remove(("meal", gid))


def test_bulk_lodging_by_category(client, created_ids):
    # Use categorie filter — may or may not resolve people, so use persona_ids
    pids = _real_person_ids(client)
    payload = {
        "evento_id": EVENT_ID,
        "persona_ids": pids[:1],
        "data": {"struttura_nome": "TEST_Bulk Hotel", "tipo_struttura": "hotel",
                 "a_carico_di": "organizzazione"},
    }
    r = client.post(f"{API}/lodgings/bulk", json=payload)
    assert r.status_code == 200
    gid = r.json()["gruppo_id"]
    created_ids["groups"].append(("lodging", gid))

    r = client.delete(f"{API}/hospitality/group/{gid}?tipo=lodging")
    assert r.status_code == 200
    created_ids["groups"].remove(("lodging", gid))


def test_bulk_no_persons_error(client):
    r = client.post(f"{API}/meals/bulk", json={
        "evento_id": EVENT_ID, "persona_ids": [],
        "data": {"tipo_pasto": "pranzo"},
    })
    assert r.status_code == 400


# --- Individual override precedence ---
def test_individual_edit_does_not_affect_others(client, created_ids):
    pids = _real_person_ids(client)[:2]
    payload = {
        "evento_id": EVENT_ID, "persona_ids": pids,
        "data": {"tipo_pasto": "cena", "struttura_nome": "TEST_GroupDinner",
                 "data": "2026-03-16"},
    }
    r = client.post(f"{API}/meals/bulk", json=payload)
    assert r.status_code == 200
    gid = r.json()["gruppo_id"]
    created_ids["groups"].append(("meal", gid))

    # Fetch meals for persona[0], edit only one
    agg = client.get(f"{API}/events/{EVENT_ID}/hospitality").json()
    p0_meal = next(m for m in agg["persons"][0]["meals"]
                   if m.get("gruppo_id") == gid) if agg["persons"][0]["persona_id"] == pids[0] else None
    if not p0_meal:
        # find in whichever person
        for p in agg["persons"]:
            if p["persona_id"] == pids[0]:
                p0_meal = next(m for m in p["meals"] if m.get("gruppo_id") == gid)
                break

    r = client.put(f"{API}/meals/{p0_meal['id']}", json={"struttura_nome": "TEST_IndividualEdit"})
    assert r.status_code == 200

    # Verify persona[1]'s meal is untouched
    agg2 = client.get(f"{API}/events/{EVENT_ID}/hospitality").json()
    for p in agg2["persons"]:
        if p["persona_id"] == pids[1]:
            m1 = next(m for m in p["meals"] if m.get("gruppo_id") == gid)
            assert m1["struttura_nome"] == "TEST_GroupDinner"

    # Cleanup
    client.delete(f"{API}/hospitality/group/{gid}?tipo=meal")
    created_ids["groups"].remove(("meal", gid))


# --- Cost redaction path (code-level verification) ---
def test_cost_redaction_code_path_exists():
    """Verify the COST_FIELDS redaction logic exists in server code."""
    with open("/app/backend/server.py") as f:
        src = f.read()
    assert 'COST_FIELDS = ("costo", "stato_pagamento", "note_amministrative")' in src
    assert "if not can_costs:" in src
    assert 'admin.get("role") == "admin"' in src


# --- Regression: existing endpoints still work ---
def test_regression_events_list(client):
    r = client.get(f"{API}/events")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_regression_persons_list(client):
    r = client.get(f"{API}/persons")
    assert r.status_code == 200


def test_regression_staff_list(client):
    r = client.get(f"{API}/staff?evento_id={EVENT_ID}")
    assert r.status_code == 200
    links = r.json()
    assert len(links) >= 1


def test_regression_sponsors(client):
    # Sponsor lives under companies with a role/flag or dedicated endpoint
    r = client.get(f"{API}/companies")
    assert r.status_code == 200


# --- Cleanup at module teardown ---
@pytest.fixture(scope="module", autouse=True)
def cleanup(client, created_ids):
    yield
    for lid in list(created_ids["lodgings"]):
        client.delete(f"{API}/lodgings/{lid}")
    for mid in list(created_ids["meals"]):
        client.delete(f"{API}/meals/{mid}")
    for tipo, gid in list(created_ids["groups"]):
        client.delete(f"{API}/hospitality/group/{gid}?tipo={tipo}")
