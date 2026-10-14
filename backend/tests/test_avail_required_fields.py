# Iteration 138: public availability form - REQUIRED event day + REQUIRED activity preference (backend rules)
import os, time, random
import pytest, requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
C1 = os.environ["AV138_C1"]   # event with allestimento 2026-11-08..09, evento 10..11, disallestimento 12..13
C2 = os.environ["AV138_C2"]   # event without setup/teardown, evento 2026-12-01..03
E1 = os.environ["AV138_E1"]
E2 = os.environ["AV138_E2"]
ERR_DAY = "Seleziona almeno un giorno dell'evento."
ERR_PREF = "Seleziona almeno un'attività che preferiresti svolgere."


def post(code, **over):
    body = {"nome": "Test", "cognome": "Avail", "cellulare": "+393331230000", "email": "test_avail138_x@example.com",
            "codice_fiscale": None, "data_nascita": "1990-05-05", "days": [], "privacy": True, "lang": "it"}
    body.update(over)
    ip = f"10.138.{random.randint(0, 250)}.{random.randint(1, 250)}"
    for _ in range(3):
        r = requests.post(f"{BASE_URL}/api/public/availability/{code}", json=body, headers={"X-Forwarded-For": ip})
        if r.status_code != 429:
            return r
        time.sleep(61)
    return r


def d(date):
    return {"date": date, "disponibile": True}


# Public info endpoint: days phases + attivita options
class TestInfo:
    def test_info_setup_event(self):
        r = requests.get(f"{BASE_URL}/api/public/availability/{C1}")
        assert r.status_code == 200
        j = r.json()
        fasi = {x["date"]: x["fase"] for x in j["days"]}
        assert fasi["2026-11-08"] == "allestimento" and fasi["2026-11-10"] == "evento" and fasi["2026-11-13"] == "disallestimento"
        assert "Nessuna preferenza" not in j["attivita_options"]
        assert "Hostess" in j["attivita_options"]

    def test_info_plain_event(self):
        j = requests.get(f"{BASE_URL}/api/public/availability/{C2}").json()
        assert all(x["fase"] == "evento" for x in j["days"]) and len(j["days"]) == 3


# Days validation
class TestDays:
    def test_no_days(self):
        r = post(C1, preferenza_attivita="Hostess")
        assert r.status_code == 400
        assert r.json()["detail"] == ERR_DAY, r.json()

    def test_only_allestimento(self):
        r = post(C1, days=[d("2026-11-08"), d("2026-11-09")], preferenza_attivita="Hostess")
        assert r.status_code == 400 and r.json()["detail"] == ERR_DAY

    def test_only_disallestimento(self):
        r = post(C1, days=[d("2026-11-12")], preferenza_attivita="Hostess")
        assert r.status_code == 400 and r.json()["detail"] == ERR_DAY

    def test_days_not_disponibile(self):
        r = post(C1, days=[{"date": "2026-11-10", "disponibile": False}], preferenza_attivita="Hostess")
        assert r.status_code == 400 and r.json()["detail"] == ERR_DAY


# Activity preference validation
class TestPref:
    @pytest.mark.parametrize("pref", [None, "", "   ", "Nessuna preferenza", "__none__", "RandomRole", "hostess"])
    def test_invalid_pref(self, pref):
        r = post(C1, days=[d("2026-11-10")], preferenza_attivita=pref)
        assert r.status_code == 400 and r.json()["detail"] == ERR_PREF, (pref, r.text)

    def test_altro_without_text(self):
        r = post(C1, days=[d("2026-11-10")], preferenza_attivita="Altro", preferenza_altro="  ")
        assert r.status_code == 400
        assert "Descrivi brevemente" in r.json()["detail"]


# Valid submissions + organizer visibility
class TestValid:
    def test_valid_event_day_only(self, admin):
        r = post(C1, email="test_avail138_a@example.com", cellulare="+393331238801", days=[d("2026-11-10")], preferenza_attivita="Hostess")
        assert r.status_code == 200 and r.json()["ok"] is True
        rows = admin.get(f"{BASE_URL}/api/events/{E1}/availabilities").json()["availabilities"]
        row = next(x for x in rows if x["email"] == "test_avail138_a@example.com")
        assert row["preferenza_attivita"] == "Hostess"
        assert [x["date"] for x in row["days"]] == ["2026-11-10"] and row["days"][0]["fase"] == "evento"
        assert row["persona_id"] and row["persona"]["nome"] == "Test"
        p = admin.get(f"{BASE_URL}/api/persons/{row['persona_id']}")
        assert p.status_code == 200 and p.json()["email"] == "test_avail138_a@example.com"

    def test_valid_mixed_days(self, admin):
        r = post(C1, email="test_avail138_c@example.com", cellulare="+393331238803",
                 days=[d("2026-11-08"), d("2026-11-11"), d("2026-11-13")], preferenza_attivita="Tecnico")
        assert r.status_code == 200
        rows = admin.get(f"{BASE_URL}/api/events/{E1}/availabilities").json()["availabilities"]
        row = next(x for x in rows if x["email"] == "test_avail138_c@example.com")
        assert {x["date"]: x["fase"] for x in row["days"]} == {"2026-11-08": "allestimento", "2026-11-11": "evento", "2026-11-13": "disallestimento"}

    def test_valid_altro(self, admin):
        r = post(C2, email="test_avail138_b@example.com", cellulare="+393331238802", days=[d("2026-12-02")],
                 preferenza_attivita="Altro", preferenza_altro="Fotografo", lang="en")
        assert r.status_code == 200
        rows = admin.get(f"{BASE_URL}/api/events/{E2}/availabilities").json()["availabilities"]
        row = next(x for x in rows if x["email"] == "test_avail138_b@example.com")
        assert row["preferenza_attivita"] == "Altro" and row["preferenza_altro"] == "Fotografo"
        assert row["compilation_lang"] == "en"


@pytest.fixture(scope="session")
def admin():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": "qa.eventi@crmeventqa.it", "password": "QaEvents2026!"})
    if r.status_code != 200:
        pytest.skip("login failed")
    s.headers.update({"X-Org-Id": "org_qa_eventi"})
    return s
