# Event "Fase evento" controlled list incl. "In corso" (stored key 'attivo'): create/edit/validate/defaults/dashboard/duplicate
import os
import uuid
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
SA = {"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"}
SUFFIX = uuid.uuid4().hex[:8]
ORG_NAME = f"TEST_FaseOrg_{SUFFIX}"
EMAIL = f"test_fase_{SUFFIX}@example.com"
PW = "TestPass2026!"
STATE = {}


@pytest.fixture(scope="module")
def org():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/register-organization", json={
        "nome": "Test", "cognome": "Fase", "email": EMAIL, "password": PW,
        "org_name": ORG_NAME, "telefono": "+393331112233", "accept_terms": True})
    assert r.status_code == 200, r.text
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PW})
    assert r.status_code == 200, r.text
    me = s.get(f"{BASE_URL}/api/auth/me").json()
    STATE["org_id"] = me.get("org_id") or (me.get("user") or {}).get("org_id")
    yield s
    sa = requests.Session()
    sa.post(f"{BASE_URL}/api/auth/login", json=SA)
    if STATE.get("org_id"):
        d = sa.delete(f"{BASE_URL}/api/platform/organizations/{STATE['org_id']}", json={"confirm_name": ORG_NAME})
        print("cleanup org", d.status_code, d.text[:200])


def _create(s, **kw):
    body = {"nome": f"TEST_Evento_{uuid.uuid4().hex[:6]}", **kw}
    return s.post(f"{BASE_URL}/api/events", json=body)


class TestFase:
    def test_create_each_state(self, org):
        for st in ("pianificato", "attivo", "concluso", "annullato"):
            r = _create(org, stato=st)
            assert r.status_code == 200, r.text
            ev = r.json()
            assert ev["stato"] == st
            g = org.get(f"{BASE_URL}/api/events/{ev['id']}")
            assert g.status_code == 200 and g.json()["stato"] == st
            STATE.setdefault("ids", {})[st] = ev["id"]

    def test_default_pianificato(self, org):
        r = _create(org)
        assert r.status_code == 200, r.text
        assert r.json()["stato"] == "pianificato"
        STATE["default_id"] = r.json()["id"]

    def test_invalid_create_422(self, org):
        r = _create(org, stato="xyz")
        assert r.status_code == 422
        assert "Fase evento non valida" in r.text

    def test_update_transitions(self, org):
        eid = STATE["default_id"]
        for st in ("attivo", "concluso", "annullato", "pianificato", "attivo"):
            r = org.put(f"{BASE_URL}/api/events/{eid}", json={"stato": st})
            assert r.status_code == 200, r.text
            assert r.json()["stato"] == st
            assert org.get(f"{BASE_URL}/api/events/{eid}").json()["stato"] == st

    def test_update_invalid_422(self, org):
        eid = STATE["default_id"]
        r = org.put(f"{BASE_URL}/api/events/{eid}", json={"stato": "in_corso"})
        assert r.status_code == 422, r.text
        assert org.get(f"{BASE_URL}/api/events/{eid}").json()["stato"] == "attivo"

    def test_update_other_field_keeps_stato(self, org):
        eid = STATE["default_id"]
        r = org.put(f"{BASE_URL}/api/events/{eid}", json={"note": "x"})
        assert r.status_code == 200, r.text
        assert org.get(f"{BASE_URL}/api/events/{eid}").json()["stato"] == "attivo"

    def test_list_contains_states(self, org):
        r = org.get(f"{BASE_URL}/api/events")
        assert r.status_code == 200
        st = {e["stato"] for e in r.json()}
        assert {"pianificato", "attivo", "concluso", "annullato"} <= st

    def test_dashboard_kpi_attivi(self, org):
        r = org.get(f"{BASE_URL}/api/dashboard")
        assert r.status_code == 200, r.text
        d = r.json()
        evs = org.get(f"{BASE_URL}/api/events").json()
        expected = len([e for e in evs if e.get("stato") == "attivo"])
        assert expected == 2
        assert d["eventi"]["attivi"] == expected

    def test_duplicate_attivo_event(self, org):
        src = STATE["ids"]["attivo"]
        r = org.post(f"{BASE_URL}/api/events/{src}/duplicate", json={"nome": "TEST_Dup Fase"})
        assert r.status_code == 200, r.text
        new = r.json()
        nid = new.get("id") or (new.get("event") or {}).get("id")
        assert nid
        assert org.get(f"{BASE_URL}/api/events/{nid}").json()["stato"] == "pianificato"
        assert org.get(f"{BASE_URL}/api/events/{src}").json()["stato"] == "attivo"
