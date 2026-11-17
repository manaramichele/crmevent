# Helper: look up current Control Room test IDs (org A, event 'TEST_CR Gara A') by name after a reseed
import os, requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
API = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/") + "/api"
PWD = "TestCR2026!"


def login(email, org=None):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": PWD})
    assert r.status_code == 200, r.text
    s.headers["Authorization"] = f"Bearer {s.cookies.get('access_token')}"
    if org:
        s.headers["X-Org-Id"] = org
    return s, r.json()


def ids():
    s, me = login("test_cr_a@crmevent-test.it")
    evs = s.get(f"{API}/controlroom/events").json()["events"]
    ev = next(e for e in evs if e.get("nome") == "TEST_CR Gara A")
    ina = next((e for e in evs if "Non attivo" in (e.get("nome") or "")), None)
    org = s.get(f"{API}/auth/me").json()
    org_id = org.get("org_id") or (org.get("user") or {}).get("org_id")
    return {"org_a": org_id, "ev_a": ev["id"], "ev_inactive": ina and ina["id"], "events": [(e["nome"], e["id"], e.get("active")) for e in evs]}


if __name__ == "__main__":
    print(ids())
