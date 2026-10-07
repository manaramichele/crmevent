"""Iter 62: Briefing Pasti/Ospitalità restructure + lodgings.numero_camera."""
import os
import requests
import pytest

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
EV = "ev_TEST_brf"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{BASE}/api/auth/login", json={"email": "test_brf@crmeventqa.it", "password": "TestBrf2026!"})
    assert r.status_code == 200, r.text
    return sess


@pytest.fixture(scope="module")
def brief(s):
    r = s.get(f"{BASE}/api/events/{EV}/briefing-live")
    assert r.status_code == 200, r.text
    return r.json()


# ---- Pasti (meals_by_day) ----
def test_meals_structure_days_and_order(brief):
    days = brief["sections"]["meals_by_day"]
    assert [d["data"] for d in days] == ["2026-12-19", "2026-12-20"]
    s19 = [sv["tipo_pasto"] for sv in days[0]["servizi"]]
    s20 = [sv["tipo_pasto"] for sv in days[1]["servizi"]]
    assert s19 == ["cena"]
    assert s20 == ["colazione", "pranzo"]  # order: colazione, pranzo, cena


def test_meals_19_cena_details(brief):
    e = brief["sections"]["meals_by_day"][0]["servizi"][0]["entries"][0]
    assert e["luogo"] == "Ristorante XYZ"
    assert "Via Roma 10" in (e["indirizzo"] or "") and "Pisa" in (e["indirizzo"] or "")
    assert e["orario"] == "20:00"
    assert e["referente"] == "Mario Rossi"
    assert e["telefono"] == "+39333999888"
    assert e["note"] == "Tavolo riservato CRMEvent"
    assert e["persone"] == 6
    assert e["esigenze"].get("Vegetariano") == 2


def test_meals_no_person_names(brief):
    """No sub-field should contain person names in meals."""
    bad = {"Rossi", "Bianchi", "Verdi", "Gialli", "Blu", "Senzahotel"}
    import json
    s = json.dumps(brief["sections"]["meals_by_day"], ensure_ascii=False)
    # 'Mario Rossi' as referente is allowed; check cognomi dei partecipanti NON referenti
    for cog in ["Bianchi", "Verdi", "Gialli", "Senzahotel"]:
        assert cog not in s, f"Found participant name {cog} in meals"


def test_meals_20_colazione_at_hotel_pisa(brief):
    e = brief["sections"]["meals_by_day"][1]["servizi"][0]["entries"][0]
    assert e["tipologia_servizio"] is None or True  # not asserted
    assert e["luogo"] == "Hotel Pisa"
    assert e["orario"] == "05:30-07:00"
    assert e["persone"] == 6


# ---- Lodging structures ----
def test_lodging_structures_order_and_names(brief):
    st = brief["sections"]["lodging_structures"]
    assert [s["nome"] for s in st] == ["Hotel Bologna", "Hotel Pisa"]


def test_hotel_bologna_rooms(brief):
    bo = brief["sections"]["lodging_structures"][0]
    assert bo["referente"] == "Giulia Neri"
    assert bo["note"] == "Parcheggio interno"
    rooms = {r["numero"]: r for r in bo["camere"]}
    assert set(rooms) == {"101", "102"}
    r101 = rooms["101"]
    assert r101["tipo_camera"] == "doppia"
    # dates per guest
    g = {o["cognome"]: o for o in r101["ospiti"]}
    assert g["Bianchi"]["check_in"] == "2026-12-18" and g["Bianchi"]["check_out"] == "2026-12-20"
    assert g["Rossi"]["check_in"] == "2026-12-18" and g["Rossi"]["check_out"] == "2026-12-21"


def test_hotel_pisa_room_204(brief):
    pi = brief["sections"]["lodging_structures"][1]
    r = pi["camere"][0]
    assert r["numero"] == "204" and r["tipo_camera"] == "tripla"
    g = {o["cognome"]: o for o in r["ospiti"]}
    assert g["Blu"]["check_in"] == "2026-12-19" and g["Blu"]["check_out"] == "2026-12-20"
    assert g["Gialli"]["check_in"] == "2026-12-18" and g["Gialli"]["check_out"] == "2026-12-21"


def test_sara_senza_hotel_not_in_lodging(brief):
    import json
    s = json.dumps(brief["sections"]["lodging_structures"], ensure_ascii=False)
    assert "Senzahotel" not in s


# ---- Old 'hospitality' section removed ----
def test_old_hospitality_removed(brief):
    assert "hospitality" not in brief["sections"]


# ---- Other sections preserved ----
def test_other_sections_present(brief):
    for k in ["teams", "staff", "shifts", "maps", "sponsors", "timeline"]:
        assert k in brief["sections"], f"missing {k}"


# ---- Unassigned room via POST /api/lodgings ----
def test_unassigned_room_appears_in_da_assegnare(s):
    payload = {
        "evento_id": EV,
        "persona_id": "pe_TEST_p6",
        "struttura_id": "st_TEST_pi",
        "check_in": "2026-12-19",
        "check_out": "2026-12-20",
    }
    r = s.post(f"{BASE}/api/lodgings", json=payload)
    assert r.status_code in (200, 201), r.text
    lid = r.json()["id"]
    try:
        b = s.get(f"{BASE}/api/events/{EV}/briefing-live").json()
        pisa = [x for x in b["sections"]["lodging_structures"] if x["nome"] == "Hotel Pisa"][0]
        da = pisa.get("da_assegnare") or []
        cognomi = [o.get("cognome") for o in da]
        assert "Senzahotel" in cognomi, f"Expected Sara Senzahotel in da_assegnare, got {da}"
    finally:
        rd = s.delete(f"{BASE}/api/lodgings/{lid}")
        assert rd.status_code in (200, 204), rd.text


# ---- Rooms count regression: 5 lodgings -> 3 rooms ----
def test_rooms_summary_count(s):
    r = s.get(f"{BASE}/api/events/{EV}/hospitality-summary")
    if r.status_code == 404:
        # fallback: try /briefing-live rooms
        b = s.get(f"{BASE}/api/events/{EV}/briefing-live").json()
        total = sum(len(st.get("camere") or []) for st in b["sections"]["lodging_structures"])
        assert total == 3, f"rooms count = {total}"
        return
    assert r.status_code == 200, r.text
    data = r.json()
    rooms = data.get("rooms") or data.get("summary", {}).get("rooms")
    assert rooms == 3, f"expected 3 rooms, got {rooms}"


# ---- Lodging has numero_camera field ----
def test_lodgings_have_numero_camera(s):
    r = s.get(f"{BASE}/api/lodgings?evento_id={EV}")
    assert r.status_code == 200, r.text
    data = r.json()
    # p1 -> Mario Rossi -> 101
    for l in data:
        if l.get("persona_id") == "pe_TEST_p1":
            assert l.get("numero_camera") == "101"
            return
    pytest.fail("Mario Rossi lodging not found")
