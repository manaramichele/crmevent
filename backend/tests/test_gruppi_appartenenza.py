# Gruppo di appartenenza: public link field, add-from-public, settings list (org_only, SA rename/delete+unlink), person edit
# Run serial: python -m pytest tests/test_gruppi_appartenenza.py -n 0 (public endpoints rate-limited: submit 6/min, groups 5/min)
import os
import time
import uuid
import pytest
import requests
from pymongo import MongoClient

RUN = uuid.uuid4().hex[:6]
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
SA = ("manara.michele.pro@gmail.com", "CrmEvent2026!")
QA = ("qa.eventi@crmeventqa.it", "QaEvents2026!")
DEMO_ORG = "b7f40862230441b9a0bedabefe8dab49"
QA_ORG = "nova_events_test_org"  # writable (internal plan) org; org_qa_eventi is plan_readonly
DEMO_LINK = "NlURMnPLdhOE3eIA3zcncZueASccC1ch"
QA_LINK = "GTsKCYLQZQb8U8AeOh_wO6Jp-BngpWW9"
DAY = "2026-12-19"
ADMIN_PW = "TestGr2026!"
ADMIN_UID = f"TEST_gr_admin_{RUN}"
ADMIN_EMAIL = f"test_gr_admin_{RUN}@example.com"
GRP = f"TEST_Gruppo {RUN}"
GRP2 = f"TEST_Rinominato {RUN}"

CREATED = {"persons": [], "groups": []}  # (org, value)


def _mongo():
    env = dict(l.strip().split("=", 1) for l in open("/app/backend/.env") if "=" in l and not l.startswith("#"))
    return MongoClient(env["MONGO_URL"].strip('"'))[env["DB_NAME"].strip('"')]


def _login(cred):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": cred[0], "password": cred[1]})
    if r.status_code != 200:
        pytest.skip(f"login failed {cred[0]}")
    tok = r.json().get("token") or r.json().get("session_token")
    if tok:
        s.headers["Authorization"] = f"Bearer {tok}"
    return s


@pytest.fixture(scope="module")
def sa():
    return _login(SA)


@pytest.fixture(scope="module")
def qa():
    import bcrypt
    db = _mongo()
    db.users.insert_one({"user_id": ADMIN_UID, "email": ADMIN_EMAIL, "name": "TEST_ Gr Admin", "role": "admin", "org_id": QA_ORG,
                         "auth_provider": "password", "active": True,
                         "password_hash": bcrypt.hashpw(ADMIN_PW.encode(), bcrypt.gensalt()).decode()})
    db.memberships.insert_one({"id": f"TEST_m_{ADMIN_UID}", "user_id": ADMIN_UID, "org_id": QA_ORG, "role": "admin_org", "active": True})
    return _login((ADMIN_EMAIL, ADMIN_PW))


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    db = _mongo()
    for pid, org in CREATED["persons"]:
        db.availabilities.delete_many({"org_id": org, "persona_id": pid})
        db.staff.delete_many({"org_id": org, "persona_id": pid})
        db.person_events.delete_many({"org_id": org, "persona_id": pid}) if "person_events" in db.list_collection_names() else None
        db.persons.delete_one({"org_id": org, "id": pid})
    if os.environ.get("KEEP_GR_ADMIN") != "1":
        db.memberships.delete_many({"user_id": ADMIN_UID})
        db.users.delete_many({"user_id": ADMIN_UID})
        for c in ("access_users", "access_logins", "access_sessions", "user_sessions"):
            db[c].delete_many({"user_id": ADMIN_UID})
    for org, v in CREATED["groups"]:
        db.settings.update_one({"id": org}, {"$pull": {"gruppi_appartenenza": v, "disattivati.gruppi_appartenenza": v}})


def _lists(s, org):
    r = s.get(f"{BASE_URL}/api/settings/lists", headers={"X-Org-Id": org} if org else {})
    assert r.status_code == 200, r.text
    return next(l for l in r.json()["lists"] if l["key"] == "gruppi_appartenenza")


def _submit(code, date, email, gruppo=None, extra=None):
    body = {"nome": f"TEST_Gr{RUN}", "cognome": "Tester", "cellulare": f"+39333{int(time.time()*1000) % 10000000:07d}",
            "email": email, "data_nascita": "1990-01-01", "days": [{"date": date, "disponibile": True}],
            "preferenza_attivita": "Accoglienza", "privacy": True}
    if gruppo is not None:
        body["gruppo_appartenenza"] = gruppo
    body.update(extra or {})
    for _ in range(3):
        r = requests.post(f"{BASE_URL}/api/public/availability/{code}", json=body)
        if r.status_code != 429:
            return r
        time.sleep(20)
    return r


def _person_by_email(email, org):
    return _mongo().persons.find_one({"org_id": org, "email": email}, {"_id": 0})


class TestPublic:
    def test_info_has_groups_and_separation(self):
        d = requests.get(f"{BASE_URL}/api/public/availability/{DEMO_LINK}").json()
        assert "TEST_Croce Rossa" in d["gruppi_options"]
        q = requests.get(f"{BASE_URL}/api/public/availability/{QA_LINK}").json()
        assert "TEST_Croce Rossa" not in q["gruppi_options"]

    def test_duplicate_ignores_case_spaces(self):
        r = requests.post(f"{BASE_URL}/api/public/availability/{DEMO_LINK}/groups", json={"nome": "  test_croce   ROSSA "})
        assert r.status_code == 200, r.text
        assert r.json() == {"value": "TEST_Croce Rossa", "created": False}

    def test_reserved_rejected(self):
        r = requests.post(f"{BASE_URL}/api/public/availability/{DEMO_LINK}/groups", json={"nome": " nessun   GRUPPO "})
        assert r.status_code == 400

    def test_group_lands_in_link_org_even_with_sa_session(self, sa):
        # SA session with X-Org-Id Demo posting to the QA link -> group must land in QA
        r = sa.post(f"{BASE_URL}/api/public/availability/{QA_LINK}/groups", json={"nome": f"  {GRP} "},
                    headers={"X-Org-Id": DEMO_ORG})
        assert r.status_code == 200, r.text
        assert r.json() == {"value": GRP, "created": True}
        CREATED["groups"].append((QA_ORG, GRP))
        assert GRP in requests.get(f"{BASE_URL}/api/public/availability/{QA_LINK}").json()["gruppi_options"]
        assert GRP not in requests.get(f"{BASE_URL}/api/public/availability/{DEMO_LINK}").json()["gruppi_options"]
        assert GRP not in [i["value"] for i in _lists(sa, DEMO_ORG)["items"]]
        assert GRP in [i["value"] for i in _lists(sa, QA_ORG)["items"]]

    def test_submit_without_group(self):
        email = f"test_gr_none_{RUN}@example.com"
        r = _submit(QA_LINK, DAY, email)
        assert r.status_code == 200, r.text
        p = _person_by_email(email, QA_ORG)
        assert p is not None
        CREATED["persons"].append((p["id"], QA_ORG))
        assert p.get("gruppo_appartenenza") is None

    def test_submit_invalid_group(self):
        r = _submit(QA_LINK, DAY, f"test_gr_bad_{RUN}@example.com", gruppo="TEST_Inesistente_xyz")
        assert r.status_code == 400

    def test_submit_with_group_saved_on_person_and_availability(self):
        email = f"test_gr_yes_{RUN}@example.com"
        r = _submit(QA_LINK, DAY, email, gruppo=GRP.lower())
        assert r.status_code == 200, r.text
        p = _person_by_email(email, QA_ORG)
        CREATED["persons"].append((p["id"], QA_ORG))
        assert p["gruppo_appartenenza"] == GRP
        av = _mongo().availabilities.find_one({"org_id": QA_ORG, "persona_id": p["id"]})
        assert av["gruppo_appartenenza"] == GRP

    def test_activity_required(self):
        r = _submit(QA_LINK, DAY, f"test_gr_noact_{RUN}@example.com", extra={"preferenza_attivita": ""})
        assert r.status_code == 400


class TestSettings:
    def test_org_admin_view_count_no_manage(self, qa):
        l = _lists(qa, None)
        assert l["group"] == "Staff e Volontari" and l["label"] == "Gruppi di appartenenza"
        assert l["org_only"] is True and l["can_manage"] is False
        it = next(i for i in l["items"] if i["value"] == GRP)
        assert it["usage"] == 1
        assert "TEST_Croce Rossa" not in [i["value"] for i in l["items"]]

    def test_org_admin_add_and_dup(self, qa):
        v = f"TEST_Admin {RUN}"
        r = qa.post(f"{BASE_URL}/api/settings/lists/gruppi_appartenenza/items", json={"value": v})
        assert r.status_code == 200 and r.json()["created"] is True, r.text
        CREATED["groups"].append((QA_ORG, v))
        r = qa.post(f"{BASE_URL}/api/settings/lists/gruppi_appartenenza/items", json={"value": f" test_admin   {RUN.upper()} "})
        assert r.json()["created"] is False and r.json()["value"] == v
        r = qa.post(f"{BASE_URL}/api/settings/lists/gruppi_appartenenza/items", json={"value": "Nessun gruppo"})
        assert r.status_code == 400

    def test_org_admin_forbidden_manage(self, qa):
        assert qa.post(f"{BASE_URL}/api/settings/lists/gruppi_appartenenza/rename", json={"old": GRP, "new": "TEST_x"}).status_code == 403
        assert qa.post(f"{BASE_URL}/api/settings/lists/gruppi_appartenenza/delete", json={"value": GRP}).status_code == 403
        assert qa.put(f"{BASE_URL}/api/settings/lists/gruppi_appartenenza", json={"items": []}).status_code == 403

    def test_org_admin_generic_settings_put_bypass(self, qa):
        # Generic PUT /api/settings must not allow wiping gruppi_appartenenza (bypass of SA-only delete)
        cur = qa.get(f"{BASE_URL}/api/settings").json()
        r = qa.put(f"{BASE_URL}/api/settings", json={"gruppi_appartenenza": [g for g in cur.get("gruppi_appartenenza", []) if g != f"TEST_Admin {RUN}"]})
        after = _lists(qa, None)
        assert f"TEST_Admin {RUN}" in [i["value"] for i in after["items"]], "org admin removed group via PUT /api/settings (bypass)"

    def test_sa_rename_updates_records(self, sa):
        r = sa.post(f"{BASE_URL}/api/settings/lists/gruppi_appartenenza/rename", json={"old": GRP, "new": GRP2}, headers={"X-Org-Id": QA_ORG})
        assert r.status_code == 200, r.text
        assert r.json()["records_updated"] == 1
        CREATED["groups"].append((QA_ORG, GRP2))
        p = _person_by_email(f"test_gr_yes_{RUN}@example.com", QA_ORG)
        assert p["gruppo_appartenenza"] == GRP2
        r = sa.post(f"{BASE_URL}/api/settings/lists/gruppi_appartenenza/rename", json={"old": GRP2, "new": "nessun gruppo"}, headers={"X-Org-Id": QA_ORG})
        assert r.status_code == 400

    def test_sa_delete_unlinks(self, sa):
        r = sa.post(f"{BASE_URL}/api/settings/lists/gruppi_appartenenza/delete", json={"value": GRP2}, headers={"X-Org-Id": QA_ORG})
        assert r.status_code == 200, r.text
        assert r.json()["records_unlinked"] == 1
        p = _person_by_email(f"test_gr_yes_{RUN}@example.com", QA_ORG)
        assert p is not None and p.get("gruppo_appartenenza") is None
        assert GRP2 not in [i["value"] for i in _lists(sa, QA_ORG)["items"]]


class TestPersonEdit:
    def test_person_edit_group(self, qa):
        p = _person_by_email(f"test_gr_none_{RUN}@example.com", QA_ORG)
        v = f"TEST_Admin {RUN}"
        r = qa.put(f"{BASE_URL}/api/persons/{p['id']}", json={"gruppo_appartenenza": v})
        assert r.status_code == 200, r.text
        g = qa.get(f"{BASE_URL}/api/persons/{p['id']}").json()
        assert g["gruppo_appartenenza"] == v
        assert g["nome"] == p["nome"]
        en = qa.get(f"{BASE_URL}/api/persons-enriched").json()
        row = next(x for x in en if x["id"] == p["id"])
        assert row.get("gruppo_appartenenza") == v
