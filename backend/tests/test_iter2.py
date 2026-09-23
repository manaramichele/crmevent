"""Iteration 2 tests: dynamic settings/tipologia, teams/shifts/maps, presence, dashboard KPIs,
password change/forgot/reset, invite, permissions, calendar, volunteer endpoints."""
import os
import uuid
import io
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "https://manage-events-12.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "manara.michele.pro@gmail.com"
ADMIN_PASSWORD = "CrmEvent2026!"
VOL_EMAIL = "mario.rossi@mail.it"
VOL_PASSWORD = "Volontario2026!"


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def volunteer():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": VOL_EMAIL, "password": VOL_PASSWORD})
    assert r.status_code == 200, r.text
    return s


# ---------- BUG#1: dynamic Tipologia ----------
class TestDynamicSettings:
    def test_add_tipologia_and_usage(self, admin):
        s = admin
        current = s.get(f"{API}/settings").json()
        current.pop("_id", None)
        new_val = f"TEST_Tip_{uuid.uuid4().hex[:6]}"
        payload = {**current, "tipologie_evento": list(current.get("tipologie_evento", [])) + [new_val]}
        r = s.put(f"{API}/settings", json=payload)
        assert r.status_code == 200
        assert new_val in r.json()["tipologie_evento"]

        # create event with new tipologia
        r = s.post(f"{API}/events", json={"nome": "TEST_EvTip", "tipologia": new_val, "citta": "Roma"})
        assert r.status_code == 200
        eid = r.json()["id"]
        r = s.get(f"{API}/events/{eid}")
        assert r.json()["tipologia"] == new_val

        # usage
        r = s.get(f"{API}/settings/usage", params={"list": "tipologie_evento", "value": new_val})
        assert r.status_code == 200
        assert r.json().get("count", 0) >= 1

        # cleanup
        s.delete(f"{API}/events/{eid}")
        payload["tipologie_evento"] = [t for t in payload["tipologie_evento"] if t != new_val]
        s.put(f"{API}/settings", json=payload)

    def test_usage_congresso(self, admin):
        # Verify usage returns count for a common seed value
        r = admin.get(f"{API}/settings/usage", params={"list": "tipologie_evento", "value": "Congresso"})
        assert r.status_code == 200
        assert "count" in r.json()


# ---------- Event partial update ----------
class TestPartialUpdate:
    def test_partial_update_preserves_fields(self, admin):
        r = admin.post(f"{API}/events", json={"nome": "TEST_Partial", "citta": "Torino", "tipologia": "Congresso"})
        eid = r.json()["id"]
        r = admin.put(f"{API}/events/{eid}", json={"tipologia": "Workshop", "ora_inizio": "10:00"})
        assert r.status_code == 200
        d = r.json()
        assert d["tipologia"] == "Workshop"
        assert d.get("ora_inizio") == "10:00"
        assert d["nome"] == "TEST_Partial"
        assert d["citta"] == "Torino"
        admin.delete(f"{API}/events/{eid}")


# ---------- Presence / Teams / Shifts CRUD ----------
class TestPresenceTeamShift:
    def test_full_cycle(self, admin):
        ev = admin.get(f"{API}/events").json()[0]["id"]
        pp = admin.get(f"{API}/persons").json()[0]["id"]

        # Team
        r = admin.post(f"{API}/teams", json={"nome": "TEST_Team", "evento_id": ev, "area": "Logistica",
                                             "responsabile_id": pp, "luogo_operativo": "Sala A", "punto_ritrovo": "Ingresso"})
        assert r.status_code == 200, r.text
        tid = r.json()["id"]

        # Presence
        r = admin.post(f"{API}/staff", json={"persona_id": pp, "evento_id": ev, "categoria": "volunteer",
                                             "area": "Logistica", "ruolo": "Runner", "team_id": tid, "stato": "confermato",
                                             "data_arrivo": "2026-05-01", "ora_arrivo": "08:00",
                                             "data_partenza": "2026-05-01", "ora_partenza": "18:00",
                                             "punto_ritrovo": "Ingresso", "luogo_operativo": "Sala A",
                                             "note_operative": "TEST"})
        assert r.status_code == 200, r.text
        sid = r.json()["id"]

        # Shift covered
        r = admin.post(f"{API}/shifts", json={"evento_id": ev, "persona_id": pp, "data": "2026-05-01",
                                              "ora_inizio": "09:00", "ora_fine": "13:00", "area": "Logistica",
                                              "ruolo": "Runner", "team_id": tid})
        assert r.status_code == 200
        sh1 = r.json()["id"]

        # Shift uncovered
        r = admin.post(f"{API}/shifts", json={"evento_id": ev, "data": "2026-05-01",
                                              "ora_inizio": "14:00", "ora_fine": "18:00", "area": "Logistica",
                                              "ruolo": "Runner"})
        assert r.status_code == 200
        sh2_body = r.json()
        assert sh2_body.get("persona_id") in (None, "")
        sh2 = sh2_body["id"]

        # cleanup
        admin.delete(f"{API}/shifts/{sh1}")
        admin.delete(f"{API}/shifts/{sh2}")
        admin.delete(f"{API}/staff/{sid}")
        admin.delete(f"{API}/teams/{tid}")


# ---------- Maps + Upload ----------
class TestMapsUpload:
    def test_upload_and_map(self, admin):
        ev = admin.get(f"{API}/events").json()[0]["id"]
        files = {"file": ("test.txt", io.BytesIO(b"hello test"), "text/plain")}
        r = admin.post(f"{API}/upload", files=files)
        assert r.status_code == 200, r.text
        fid = r.json()["id"]
        assert r.json()["url"].endswith(f"/api/files/{fid}")

        # download
        r = admin.get(f"{API}/files/{fid}")
        assert r.status_code == 200
        assert r.content == b"hello test"

        # Create map linked
        r = admin.post(f"{API}/maps", json={"nome": "TEST_Map", "evento_id": ev, "file_id": fid})
        assert r.status_code == 200
        mid = r.json()["id"]
        admin.delete(f"{API}/maps/{mid}")


# ---------- Dashboard KPIs ----------
class TestDashboardKPIs:
    def test_staff_kpis(self, admin):
        d = admin.get(f"{API}/dashboard").json()
        assert "staff" in d
        st = d["staff"]
        for k in ["staff_totale", "volontari_totali", "confermati", "da_confermare", "rinunce",
                  "team_creati", "team_senza_responsabile", "turni_totali", "turni_scoperti",
                  "persone_senza_ruolo", "persone_senza_team"]:
            assert k in st, f"missing KPI {k}"


# ---------- Password change / forgot / reset ----------
class TestPassword:
    def test_change_password_flow(self):
        s = requests.Session()
        email = f"tmp_{uuid.uuid4().hex[:8]}@testcrm.it"
        r = s.post(f"{API}/auth/register", json={"email": email, "password": "OldPass123!", "name": "Tmp"})
        assert r.status_code == 200
        # wrong current
        r = s.post(f"{API}/auth/change-password", json={"current_password": "wrong", "new_password": "NewPass123!"})
        assert r.status_code == 400
        # short new
        r = s.post(f"{API}/auth/change-password", json={"current_password": "OldPass123!", "new_password": "short"})
        assert r.status_code == 400
        # correct
        r = s.post(f"{API}/auth/change-password", json={"current_password": "OldPass123!", "new_password": "NewPass123!"})
        assert r.status_code == 200
        # login with new
        s2 = requests.Session()
        r = s2.post(f"{API}/auth/login", json={"email": email, "password": "NewPass123!"})
        assert r.status_code == 200

    def test_forgot_password_ok(self):
        r = requests.post(f"{API}/auth/forgot-password", json={"email": "unknown_xyz@example.com"})
        assert r.status_code == 200
        # even for unknown email should be ok (no user enumeration)
        assert r.json().get("ok") is True or r.status_code == 200

    def test_reset_invalid_token(self):
        r = requests.post(f"{API}/auth/reset-password", json={"token": "invalid_xxx", "new_password": "NewPass123!"})
        assert r.status_code == 400


# ---------- Invite ----------
class TestInvite:
    def test_invite_and_access_toggle(self, admin):
        # create person with email
        email = f"inv_{uuid.uuid4().hex[:6]}@testcrm.it"
        r = admin.post(f"{API}/persons", json={"nome": "TEST_Inv", "cognome": "X", "email": email})
        pid = r.json()["id"]
        r = admin.post(f"{API}/persons/{pid}/invite", json={"role": "volunteer"})
        assert r.status_code == 200
        assert r.json().get("ok") is True
        p = admin.get(f"{API}/persons/{pid}").json()
        assert p.get("invite_status") == "invito_inviato"
        # disable access
        r = admin.put(f"{API}/persons/{pid}/access", json={"enabled": False})
        assert r.status_code == 200
        p = admin.get(f"{API}/persons/{pid}").json()
        assert p.get("invite_status") == "accesso_disabilitato"
        admin.delete(f"{API}/persons/{pid}")


# ---------- Permissions ----------
class TestPermissions:
    @pytest.mark.parametrize("path", ["/events", "/dashboard", "/persons", "/settings", "/companies", "/deals"])
    def test_volunteer_denied(self, volunteer, path):
        r = volunteer.get(f"{API}{path}")
        assert r.status_code == 403, f"{path}: expected 403 got {r.status_code}"

    def test_volunteer_me_events(self, volunteer):
        r = volunteer.get(f"{API}/me/events")
        assert r.status_code == 200
        d = r.json()
        items = d["events"] if isinstance(d, dict) and "events" in d else d
        assert isinstance(items, list)
        assert len(items) >= 1

    def test_volunteer_me_event_detail(self, volunteer):
        d = volunteer.get(f"{API}/me/events").json()
        items = d["events"] if isinstance(d, dict) and "events" in d else d
        eid = items[0]["event"]["id"] if "event" in items[0] else items[0]["id"]
        r = volunteer.get(f"{API}/me/events/{eid}")
        assert r.status_code == 200
        d = r.json()
        for k in ["presence", "shifts", "team", "colleagues", "maps"]:
            assert k in d, f"missing key {k}"

    def test_volunteer_isolation(self, volunteer, admin):
        # create a fresh event volunteer is NOT part of
        ev = admin.post(f"{API}/events", json={"nome": "TEST_Isolation", "citta": "X"}).json()
        eid = ev["id"]
        try:
            r = volunteer.get(f"{API}/me/events/{eid}")
            assert r.status_code == 404
        finally:
            admin.delete(f"{API}/events/{eid}")

    def test_volunteer_shifts(self, volunteer):
        r = volunteer.get(f"{API}/me/shifts")
        assert r.status_code == 200
        d = r.json()
        items = d["shifts"] if isinstance(d, dict) and "shifts" in d else d
        assert isinstance(items, list)


# ---------- Calendar (not configured) ----------
class TestCalendar:
    def test_status_not_configured(self, admin):
        r = admin.get(f"{API}/calendar/status")
        assert r.status_code == 200
        assert r.json().get("configured") is False

    def test_connect_400(self, admin):
        r = admin.get(f"{API}/calendar/connect", allow_redirects=False)
        assert r.status_code == 400
