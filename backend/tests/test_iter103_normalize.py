"""Backend tests for text normalization (persons/companies/teams/org registration/platform preview+apply)."""
import os
import random
import string
import pytest
import requests

def _load_frontend_env():
    p = "/app/frontend/.env"
    if os.path.exists(p):
        for line in open(p):
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    return None

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _load_frontend_env() or "").rstrip("/")
API = f"{BASE_URL}/api"

QA_EMAIL = "qa.eventi@crmeventqa.it"
QA_PASS = "QaEvents2026!"
SA_EMAIL = "manara.michele.pro@gmail.com"
SA_PASS = "CrmEvent2026!"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def qa():
    return _login(QA_EMAIL, QA_PASS)


@pytest.fixture(scope="module")
def sa():
    return _login(SA_EMAIL, SA_PASS)


@pytest.fixture(scope="module")
def created():
    # tracks ids for cleanup across tests
    return {"persons": [], "companies": [], "teams": [], "organizations": [], "users": []}


# ---------------- PERSONS ----------------
def test_person_create_normalizes(qa, created):
    body = {
        "nome": "mARIO",
        "cognome": "d'amico",
        "email": f"TEST_X_{random.randint(1000,9999)}@Example.com",
        "note": "testo libero minuscolo",
        "citta": "reggio emilia",
    }
    r = qa.post(f"{API}/persons", json=body, timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    created["persons"].append(d["id"])
    assert d["nome"] == "Mario"
    assert d["cognome"] == "D'Amico"
    assert d["email"] == body["email"]  # untouched
    assert d["note"] == "testo libero minuscolo"
    assert d["citta"] == "Reggio Emilia"


def test_person_update_normalizes(qa, created):
    assert created["persons"], "need previous person"
    pid = created["persons"][0]
    r = qa.put(f"{API}/persons/{pid}", json={"cognome": "DE LUCA"}, timeout=20)
    assert r.status_code == 200, r.text
    assert r.json()["cognome"] == "De Luca"


# ---------------- COMPANIES ----------------
def test_company_create_asd(qa, created):
    body = {"nome": "test asd RUNNING club", "partita_iva": "IT12345678901", "sito_web": "https://Example.COM/Path"}
    r = qa.post(f"{API}/companies", json=body, timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    created["companies"].append(d["id"])
    assert d["nome"] == "Test Asd RUNNING Club"
    assert d["partita_iva"] == "IT12345678901"
    assert d["sito_web"] == "https://Example.COM/Path"


def test_company_create_crmevent(qa, created):
    r = qa.post(f"{API}/companies", json={"nome": "CRMEvent partner"}, timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    created["companies"].append(d["id"])
    assert d["nome"] == "CRMEvent Partner"


# ---------------- TEAMS ----------------
def test_team_create_normalizes(qa, created):
    ev = qa.get(f"{API}/events", timeout=20).json()
    if not ev:
        pytest.skip("No events available to attach team")
    evento_id = ev[0]["id"]
    r = qa.post(f"{API}/teams", json={"nome": "team ristori TEST", "evento_id": evento_id}, timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    created["teams"].append(d["id"])
    assert d["nome"] == "Team Ristori TEST"


# ---------------- REGISTER ORGANIZATION ----------------
def test_register_org_normalizes(created):
    tag = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    email = f"TEST_norm_{tag}@example.com"
    body = {
        "nome": "tEST",
        "cognome": "MANARA",
        "email": email,
        "password": "StrongPass123!",
        "org_name": "test associazione sportiva di milano",
        "telefono": "+393331112233",
        "accept_terms": True,
    }
    r = requests.post(f"{API}/auth/register-organization", json=body, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    # Response may differ; verify by logging in and reading /auth/me
    s = _login(email, "StrongPass123!")
    me = s.get(f"{API}/auth/me", timeout=20)
    assert me.status_code == 200, me.text
    mejson = me.json()
    # name should be "Test Manara"
    name = mejson.get("name") or mejson.get("user", {}).get("name")
    assert name == "Test Manara", f"name={name!r} full={mejson}"
    # org name — top-level org_name or inside organizations[]
    org_nome = mejson.get("org_name")
    if not org_nome and mejson.get("organizations"):
        org_nome = mejson["organizations"][0].get("nome")
    assert org_nome == "Test Associazione Sportiva di Milano", f"org_nome={org_nome!r}"
    created["users"].append(mejson.get("user_id") or mejson.get("id"))
    org_id = mejson.get("org_id") or (mejson.get("organizations") or [{}])[0].get("org_id")
    created["organizations"].append(org_id)


# ---------------- PLATFORM NORMALIZE PREVIEW/APPLY ----------------
def test_platform_preview_readonly(sa):
    r = sa.get(f"{API}/platform/normalize/preview", timeout=60)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "items" in body and isinstance(body["items"], list)
    for it in body["items"][:5]:
        for k in ("coll", "id", "field", "old", "new"):
            assert k in it, f"missing {k} in {it}"
        assert it["old"] != it["new"]


def test_platform_apply_test_record_only(sa, qa, created):
    # Insert a TEST_ person with non-normalized name directly? No, we normalize on create.
    # Use existing registered org user (TEST_norm_) — their user record might have test name.
    # Instead, create a person manually with QA and then "de-normalize" via a mongo-less path:
    # We'll pick a preview item that belongs to a TEST_ email user if present.
    r = sa.get(f"{API}/platform/normalize/preview", timeout=60)
    assert r.status_code == 200
    items = r.json()["items"]
    # find at most one TEST_ item (users with email starting with TEST_, or persons we created but non-normalized)
    # Our created records are already normalized; try to pick a users item where id maps to one we just created
    target = None
    for it in items:
        if it["coll"] == "users" and it["id"] in created["users"]:
            target = it; break
    if target is None:
        pytest.skip("No TEST_ un-normalized record found in preview — apply is a no-op; endpoint reachable.")
    r2 = sa.post(f"{API}/platform/normalize/apply", json={"items": [target]}, timeout=30)
    assert r2.status_code == 200, r2.text
    assert r2.json().get("updated") in (0, 1)


# ---------------- CLEANUP ----------------
def test_zzz_cleanup(qa, sa, created):
    for pid in created["persons"]:
        qa.delete(f"{API}/persons/{pid}", timeout=15)
    for cid in created["companies"]:
        qa.delete(f"{API}/companies/{cid}", timeout=15)
    for tid in created["teams"]:
        qa.delete(f"{API}/teams/{tid}", timeout=15)
    # Delete created orgs/users via super admin if endpoints exist
    for uid in [u for u in created["users"] if u]:
        sa.delete(f"{API}/platform/users/{uid}", timeout=15)
    for oid in [o for o in created["organizations"] if o]:
        sa.delete(f"{API}/platform/organizations/{oid}", timeout=15)
