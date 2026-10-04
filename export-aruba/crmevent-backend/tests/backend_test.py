"""Backend API tests for CRMEvent."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://manage-events-12.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "manara.michele.pro@gmail.com"
ADMIN_PASSWORD = "CrmEvent2026!"


@pytest.fixture(scope="session")
def auth_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    data = r.json()
    assert data["email"] == ADMIN_EMAIL
    assert data.get("role") == "admin"
    return s


# ----- Auth -----
class TestAuth:
    def test_login_invalid(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"})
        assert r.status_code == 401

    def test_me_no_auth_returns_401(self):
        r = requests.get(f"{API}/auth/me")
        assert r.status_code == 401

    def test_me_with_auth(self, auth_session):
        r = auth_session.get(f"{API}/auth/me")
        assert r.status_code == 200
        assert r.json()["email"] == ADMIN_EMAIL

    def test_register_and_login(self):
        import uuid
        email = f"test_{uuid.uuid4().hex[:8]}@testcrm.it"
        s = requests.Session()
        r = s.post(f"{API}/auth/register", json={"email": email, "password": "Test1234!", "name": "TEST User"})
        assert r.status_code == 200, r.text
        assert r.json()["email"] == email
        # Verify /me works with cookie
        r2 = s.get(f"{API}/auth/me")
        assert r2.status_code == 200
        # duplicate registration should fail
        r3 = requests.post(f"{API}/auth/register", json={"email": email, "password": "x", "name": "y"})
        assert r3.status_code == 400


# ----- Protected endpoints without auth -----
class TestProtected:
    @pytest.mark.parametrize("path", [
        "/events", "/companies", "/persons", "/deals",
        "/staff", "/activities", "/followups", "/dashboard",
        "/notifications", "/settings", "/search?q=test",
    ])
    def test_requires_auth(self, path):
        r = requests.get(f"{API}{path}")
        assert r.status_code == 401, f"{path} returned {r.status_code}"


# ----- Dashboard -----
class TestDashboard:
    def test_dashboard(self, auth_session):
        r = auth_session.get(f"{API}/dashboard")
        assert r.status_code == 200
        d = r.json()
        for k in ["eventi", "crm", "commerciale", "attivita", "staff", "pipeline_chart", "tipo_chart"]:
            assert k in d
        assert d["eventi"]["totali"] >= 3  # seed created 3 events
        assert d["commerciale"]["valore_pipeline"] > 0

    def test_dashboard_filter(self, auth_session):
        events = auth_session.get(f"{API}/events").json()
        assert len(events) > 0
        eid = events[0]["id"]
        r = auth_session.get(f"{API}/dashboard", params={"evento_id": eid})
        assert r.status_code == 200
        assert r.json()["eventi"]["totali"] == 1


# ----- CRUD generic helper -----
def _crud(session, path, create_body, update_body, key_field="nome"):
    # Create
    r = session.post(f"{API}/{path}", json=create_body)
    assert r.status_code == 200, f"CREATE {path}: {r.status_code} {r.text}"
    obj = r.json()
    assert "id" in obj
    _id = obj["id"]
    # Read list
    r = session.get(f"{API}/{path}")
    assert r.status_code == 200
    assert any(x["id"] == _id for x in r.json())
    # Read one
    r = session.get(f"{API}/{path}/{_id}")
    assert r.status_code == 200
    # Update
    r = session.put(f"{API}/{path}/{_id}", json=update_body)
    assert r.status_code == 200, f"UPDATE {path}: {r.status_code} {r.text}"
    for k, v in update_body.items():
        assert r.json().get(k) == v
    # Verify GET after update
    r = session.get(f"{API}/{path}/{_id}")
    for k, v in update_body.items():
        assert r.json().get(k) == v
    # Delete
    r = session.delete(f"{API}/{path}/{_id}")
    assert r.status_code == 200
    r = session.get(f"{API}/{path}/{_id}")
    assert r.status_code == 404


class TestCRUD:
    def test_events(self, auth_session):
        _crud(auth_session, "events",
              {"nome": "TEST_Event", "citta": "Roma", "stato": "pianificato"},
              {"nome": "TEST_Event_Updated", "citta": "Milano"})

    def test_companies(self, auth_session):
        _crud(auth_session, "companies",
              {"nome": "TEST_Company", "settore": "Tecnologia", "tipo": "azienda"},
              {"nome": "TEST_Company_U", "settore": "Media"})

    def test_persons(self, auth_session):
        _crud(auth_session, "persons",
              {"nome": "TEST_Nome", "cognome": "Cognome", "email": "test@test.it"},
              {"nome": "TEST_Nome_U", "ruolo": "Manager"})

    def test_activities(self, auth_session):
        _crud(auth_session, "activities",
              {"titolo": "TEST_Activity", "tipo": "chiamata"},
              {"titolo": "TEST_Activity_U", "stato": "completata"})

    def test_followups(self, auth_session):
        _crud(auth_session, "followups",
              {"titolo": "TEST_Followup", "priorita": "alta"},
              {"titolo": "TEST_Followup_U", "stato": "completato"})

    def test_deals(self, auth_session):
        # need azienda + evento
        ev = auth_session.get(f"{API}/events").json()[0]["id"]
        cp = auth_session.get(f"{API}/companies").json()[0]["id"]
        _crud(auth_session, "deals",
              {"azienda_id": cp, "evento_id": ev, "tipo": "sponsor", "fase": "prospect", "valore": 1000},
              {"fase": "confermato", "valore_confermato": 1500})

    def test_staff(self, auth_session):
        ev = auth_session.get(f"{API}/events").json()[0]["id"]
        pp = auth_session.get(f"{API}/persons").json()[0]["id"]
        _crud(auth_session, "staff",
              {"persona_id": pp, "evento_id": ev, "categoria": "staff", "ruolo": "Tecnico", "stato": "invitato"},
              {"stato": "confermato", "area": "Logistica"})


# ----- Search / Notifications / Settings -----
class TestMisc:
    def test_search(self, auth_session):
        r = auth_session.get(f"{API}/search", params={"q": "Tech"})
        assert r.status_code == 200
        assert "results" in r.json()
        assert len(r.json()["results"]) > 0

    def test_search_short_query(self, auth_session):
        r = auth_session.get(f"{API}/search", params={"q": "a"})
        assert r.status_code == 200
        assert r.json()["results"] == []

    def test_notifications(self, auth_session):
        r = auth_session.get(f"{API}/notifications")
        assert r.status_code == 200
        assert "count" in r.json()
        assert "items" in r.json()

    def test_settings_get(self, auth_session):
        r = auth_session.get(f"{API}/settings")
        assert r.status_code == 200
        d = r.json()
        assert "tipologie_evento" in d
        assert "settori" in d
        assert "ruoli_staff" in d

    def test_settings_update(self, auth_session):
        current = auth_session.get(f"{API}/settings").json()
        new_tip = list(current.get("tipologie_evento", [])) + ["TEST_Tipologia"]
        payload = {**current, "tipologie_evento": new_tip}
        payload.pop("_id", None)
        r = auth_session.put(f"{API}/settings", json=payload)
        assert r.status_code == 200
        assert "TEST_Tipologia" in r.json()["tipologie_evento"]
        # remove
        payload["tipologie_evento"] = [t for t in new_tip if t != "TEST_Tipologia"]
        r = auth_session.put(f"{API}/settings", json=payload)
        assert "TEST_Tipologia" not in r.json()["tipologie_evento"]
