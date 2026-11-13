# Public Event Planner demo on homepage: public config, tracking whitelist/rate-limit, super admin settings & stats
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
SA_EMAIL = "manara.michele.pro@gmail.com"
SA_PASS = "CrmEvent2026!"


@pytest.fixture(scope="module")
def sa():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": SA_EMAIL, "password": SA_PASS})
    if r.status_code != 200:
        pytest.skip("superadmin login failed")
    return s


@pytest.fixture(scope="module")
def org_admin(sa):
    s = requests.Session()
    tag = uuid.uuid4().hex[:6]
    name = f"TEST_PDemo Org {tag}"
    r = s.post(f"{BASE_URL}/api/auth/register-organization", json={
        "nome": "Test", "cognome": "Pdemo", "email": f"test_pdemo_{tag}@example.com", "password": "TestPass123!",
        "org_name": name, "telefono": "+393331234567", "accept_terms": True})
    assert r.status_code == 200, r.text
    org_id = r.json().get("org_id") or (r.json().get("org") or {}).get("id")
    yield s
    if org_id:
        d = sa.delete(f"{BASE_URL}/api/platform/organizations/{org_id}", json={"confirm_name": name})
        print("cleanup org", d.status_code)


VALID = {"abilitata": True, "scenario_default": "running", "titolo": "TEST_ Titolo demo", "sottotitolo": "Sottotitolo test",
         "cta_demo": "Prova", "cta_funzioni": "Funzioni", "cta_funzioni_link": "#funzionalita", "nudge_titolo": "Nudge titolo",
         "nudge_testo": "Nudge testo", "nudge_cta": "Registrati", "soglia_interazioni": 4}


class TestPublicConfig:
    def test_public_config(self):
        r = requests.get(f"{BASE_URL}/api/public/planner-demo")
        assert r.status_code == 200
        d = r.json()
        assert d["abilitata"] is True
        assert d["scenario_default"] == "running"
        assert len(d["library"]) == 38
        assert d.get("maptiler_key")
        assert d["titolo"] and d["nudge_titolo"] == "Hai iniziato a progettare il tuo evento!"
        assert "_id" not in d


class TestTrack:
    H = {"X-Forwarded-For": f"10.250.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"}

    @pytest.mark.parametrize("ev", ["view", "start", "scenario", "tool", "place", "nudge", "cta_register",
                                    "cta_features", "fullscreen", "signup", "import"])
    def test_whitelisted(self, ev):
        r = requests.post(f"{BASE_URL}/api/public/planner-demo/track", json={"evento": ev, "valore": "TEST_v"}, headers=self.H)
        assert r.status_code == 200 and r.json()["ok"] is True

    def test_invalid_event(self):
        r = requests.post(f"{BASE_URL}/api/public/planner-demo/track", json={"evento": "hack"})
        assert r.status_code == 400

    def test_rate_limit(self):
        h = {"X-Forwarded-For": f"10.251.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"}
        oks = [requests.post(f"{BASE_URL}/api/public/planner-demo/track", json={"evento": "tool", "valore": "TEST_rl"}, headers=h).json()["ok"]
               for _ in range(122)]
        print("ok count", oks.count(True))
        assert oks.count(True) == 120 and oks[-1] is False


class TestAdminAuth:
    def test_noauth(self):
        assert requests.get(f"{BASE_URL}/api/planner-demo/settings").status_code == 401
        assert requests.get(f"{BASE_URL}/api/planner-demo/stats?giorni=30").status_code == 401
        assert requests.put(f"{BASE_URL}/api/planner-demo/settings", json=VALID).status_code == 401

    def test_org_admin_forbidden(self, org_admin):
        assert org_admin.get(f"{BASE_URL}/api/planner-demo/settings").status_code == 403
        assert org_admin.get(f"{BASE_URL}/api/planner-demo/stats?giorni=30").status_code == 403
        assert org_admin.put(f"{BASE_URL}/api/planner-demo/settings", json=VALID).status_code == 403


class TestAdminSettings:
    def test_get_and_stats(self, sa):
        r = sa.get(f"{BASE_URL}/api/planner-demo/settings")
        assert r.status_code == 200 and "running" in r.json()["scenari"]
        s = sa.get(f"{BASE_URL}/api/planner-demo/stats?giorni=30")
        assert s.status_code == 200
        d = s.json()
        assert d["totali"].get("signup", 0) >= 1 and "tool" in d["dettaglio"]

    def test_validation(self, sa):
        assert sa.put(f"{BASE_URL}/api/planner-demo/settings", json={**VALID, "scenario_default": "triathlon"}).status_code == 400
        assert sa.put(f"{BASE_URL}/api/planner-demo/settings", json={**VALID, "titolo": "x" * 141}).status_code == 422
        assert sa.put(f"{BASE_URL}/api/planner-demo/settings", json={**VALID, "soglia_interazioni": 0}).status_code == 422

    def test_update_disable_restore(self, sa):
        try:
            r = sa.put(f"{BASE_URL}/api/planner-demo/settings", json=VALID)
            assert r.status_code == 200
            assert requests.get(f"{BASE_URL}/api/public/planner-demo").json()["titolo"] == "TEST_ Titolo demo"
            r = sa.put(f"{BASE_URL}/api/planner-demo/settings", json={**VALID, "abilitata": False})
            assert r.status_code == 200
            assert requests.get(f"{BASE_URL}/api/public/planner-demo").json() == {"abilitata": False}
        finally:
            import subprocess  # restore defaults by deleting doc
            subprocess.run(["python3", "-c", "import os,pymongo;from dotenv import load_dotenv;load_dotenv('/app/backend/.env');"
                            "c=pymongo.MongoClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']];c.planner_demo_settings.delete_one({'_id':'main'})"])
        d = requests.get(f"{BASE_URL}/api/public/planner-demo").json()
        assert d["abilitata"] is True and d["titolo"] == "Progetta il tuo evento direttamente sulla mappa"
