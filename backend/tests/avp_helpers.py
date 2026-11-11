# Helpers for Preferenze volontari tests (iteration 152): TEST org setup via public API + scoped cleanup by org_id
import os, uuid, requests
from pymongo import MongoClient

def _base():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        for line in open("/app/frontend/.env"):
            if line.startswith("REACT_APP_BACKEND_URL="):
                url = line.split("=", 1)[1].strip()
    return url.rstrip("/")

BASE = _base()
SA = ("manara.michele.pro@gmail.com", "CrmEvent2026!")


def _db():
    env = dict(l.strip().split("=", 1) for l in open("/app/backend/.env") if "=" in l and not l.startswith("#"))
    return MongoClient(env["MONGO_URL"].strip('"'))[env["DB_NAME"].strip('"')]


def login(email, pw):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return s


def submit(code, nome, cognome, email, cell, pref, altro=None):
    body = {"nome": nome, "cognome": cognome, "cellulare": cell, "email": email, "data_nascita": "1990-01-01",
            "days": [{"date": "2026-12-20", "disponibile": True}], "preferenza_attivita": pref,
            "preferenza_altro": altro, "privacy": True}
    r = requests.post(f"{BASE}/api/public/availability/{code}", json=body)
    assert r.status_code == 200, r.text


def setup_org():
    tag = uuid.uuid4().hex[:6]
    email = f"test_avp_{tag}@example.com"
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/register-organization", json={"nome": "TEST_Admin", "cognome": "Avp", "email": email,
               "password": "TestPass123!", "org_name": f"TEST_AVP_{tag}", "telefono": "+39 333 123 4567", "accept_terms": True})
    assert r.status_code == 200, r.text
    org_id = r.json().get("org_id") or s.get(f"{BASE}/api/auth/me").json().get("org_id")
    ruoli = s.get(f"{BASE}/api/settings").json()["ruoli_staff"]
    ev = {}
    for k in ("A", "B"):
        e = s.post(f"{BASE}/api/events", json={"nome": f"TEST_EV_{k}_{tag}", "data_inizio": "2026-12-20", "data_fine": "2026-12-20"})
        assert e.status_code in (200, 201), e.text
        ev[k] = e.json()["id"]
    codes = {k: s.post(f"{BASE}/api/events/{ev[k]}/availability/link").json()["code"] for k in ev}
    # P1: Da classificare, pref ruoli[0] on A
    submit(codes["A"], "TEST_Uno", "Pref", f"test_p1_{tag}@example.com", "3331000001", ruoli[0])
    # P2: volunteer with staff link on A (pref ruoli[1]) and B (pref ruoli[0])
    submit(codes["A"], "TEST_Due", "Pref", f"test_p2_{tag}@example.com", "3331000002", ruoli[1])
    submit(codes["B"], "TEST_Due", "Pref", f"test_p2_{tag}@example.com", "3331000002", ruoli[0])
    # P3: Altro
    submit(codes["A"], "TEST_Tre", "Pref", f"test_p3_{tag}@example.com", "3331000003", "Altro", "TEST_custom")
    persons = {p["email"]: p for p in s.get(f"{BASE}/api/persons-enriched").json()}
    pid = {k: persons[f"test_{k}_{tag}@example.com"]["id"] for k in ("p1", "p2", "p3")}
    team = s.post(f"{BASE}/api/teams", json={"nome": "TEST_Team", "evento_id": ev["A"]}).json()
    staffA = s.post(f"{BASE}/api/staff", json={"persona_id": pid["p2"], "evento_id": ev["A"], "categoria": "volontario", "team_id": team["id"], "stato": "confermato"}).json()
    staffB = s.post(f"{BASE}/api/staff", json={"persona_id": pid["p2"], "evento_id": ev["B"], "categoria": "volontario"}).json()
    shift = s.post(f"{BASE}/api/shifts", json={"evento_id": ev["A"], "persona_id": pid["p2"], "data": "2026-12-20", "ora_inizio": "08:00", "ora_fine": "12:00", "team_id": team["id"]}).json()
    return {"s": s, "tag": tag, "email": email, "org_id": org_id, "ruoli": ruoli, "ev": ev, "codes": codes, "pid": pid,
            "team": team["id"], "staffA": staffA["id"], "staffB": staffB["id"], "shift": shift["id"]}


def cleanup(org_id, email):
    db = _db()
    org = db.organizations.find_one({"id": org_id})
    assert org and (org.get("nome") or "").startswith("TEST_"), "refuse to clean non-TEST org"
    for c in ["events", "companies", "persons", "deals", "staff", "teams", "shifts", "activities", "followups", "memberships",
              "availabilities", "avail_links", "backup_avail_prefs", "avail_prefs_runs", "audit_logs", "files", "person_companies"]:
        db[c].delete_many({"org_id": org_id})
    db.settings.delete_many({"id": org_id})
    db.users.delete_many({"email": email})
    db.organizations.delete_one({"id": org_id})
