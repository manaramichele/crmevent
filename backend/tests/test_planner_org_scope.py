# Event Planner: org resolution on read endpoints (no KeyError 500), CRUD/save/revisions, cross-org isolation, Super Admin X-Org-Id.
# Creates TEST_ orgs in the PREVIEW DB and deletes them at the end.
import os
import uuid

import pytest
import requests
from pymongo import MongoClient

mdb = MongoClient("mongodb://localhost:27017")["test_database"]  # preview DB only, used for cleanup
API = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/") + "/api"
SA_EMAIL, SA_PW = "manara.michele.pro@gmail.com", "CrmEvent2026!"
PW = "TestPlanner2026!"
CREATED = []


def _login(email, pw):
    s = requests.Session()
    assert s.post(f"{API}/auth/login", json={"email": email, "password": pw}).status_code == 200
    return s


def _org(sa, label):
    s = requests.Session()
    name = f"TEST_PLN {label} {uuid.uuid4().hex[:4]}"
    r = s.post(f"{API}/auth/register-organization", json={"nome": "TEST", "cognome": "PLN", "email": f"test_pln_{uuid.uuid4().hex[:8]}@example.com",
                                                          "password": PW, "org_name": name, "telefono": "+393471234567", "accept_terms": True})
    assert r.status_code in (200, 201), r.text
    oid = s.get(f"{API}/auth/me").json()["org_id"]
    CREATED.append((oid, name))
    assert sa.put(f"{API}/platform/saas/orgs/{oid}/admin", json={"plan": "gold", "status": "active"}).status_code == 200
    eid = s.post(f"{API}/events", json={"nome": f"{name} Maratona", "data_inizio": "2026-12-13"}).json()["id"]
    r = s.post(f"{API}/addons/planner/events/{eid}/activate")
    assert r.status_code == 200, r.text
    return s, oid, eid


@pytest.fixture(scope="module")
def ctx():
    sa = _login(SA_EMAIL, SA_PW)
    a, oid_a, eid_a = _org(sa, "A")
    b, oid_b, eid_b = _org(sa, "B")
    yield {"sa": sa, "a": a, "oid_a": oid_a, "eid_a": eid_a, "b": b, "oid_b": oid_b, "eid_b": eid_b}
    for oid, _ in CREATED:
        real = (mdb.organizations.find_one({"id": oid}) or {}).get("nome")
        if real:
            sa.delete(f"{API}/platform/organizations/{oid}", json={"confirm_name": real})


def test_flow_create_load_edit_save_revisions(ctx):
    a, eid = ctx["a"], ctx["eid_a"]
    r = a.get(f"{API}/planner/events/{eid}/projects")
    assert r.status_code == 200, r.text
    assert r.json()["projects"] == []
    p = a.post(f"{API}/planner/events/{eid}/projects", json={"nome": "TEST_Planimetria"}).json()
    ctx["pid"] = p["id"]
    assert [x["id"] for x in a.get(f"{API}/planner/events/{eid}/projects").json()["projects"]] == [p["id"]]
    assert a.patch(f"{API}/planner/projects/{p['id']}", json={"nome": "TEST_Planimetria 2"}).status_code == 200
    full = a.get(f"{API}/planner/projects/{p['id']}").json()
    assert full["nome"] == "TEST_Planimetria 2"
    feat = [{"type": "Feature", "id": "f1", "geometry": {"type": "Point", "coordinates": [10.4, 43.7]}, "properties": {"nome": "Arrivo"}}]
    r = a.put(f"{API}/planner/projects/{p['id']}/content", json={"version": full["version"], "features": feat, "layers": full["layers"]})
    assert r.status_code == 200, r.text
    assert a.put(f"{API}/planner/projects/{p['id']}/content", json={"version": full["version"], "features": [], "layers": full["layers"]}).status_code == 409
    revs = a.get(f"{API}/planner/projects/{p['id']}/revisions").json()["revisions"]
    assert len(revs) == 1
    r = a.post(f"{API}/planner/projects/{p['id']}/revisions/{revs[0]['id']}/restore")
    assert r.status_code == 200, r.text


def test_other_org_cannot_access(ctx):
    b, pid, eid = ctx["b"], ctx["pid"], ctx["eid_a"]
    assert b.get(f"{API}/planner/events/{eid}/projects").status_code == 404
    assert b.get(f"{API}/planner/projects/{pid}").status_code == 404
    assert b.get(f"{API}/planner/projects/{pid}/revisions").status_code == 404
    assert b.patch(f"{API}/planner/projects/{pid}", json={"nome": "TEST_intrusione"}).status_code == 404
    assert b.post(f"{API}/planner/events/{eid}/projects", json={"nome": "TEST_intrusione"}).status_code == 404
    assert b.put(f"{API}/planner/projects/{pid}/content", json={"version": 1, "features": [], "layers": []}).status_code == 404
    # X-Org-Id of another org is rejected for an ordinary user
    assert b.get(f"{API}/planner/events/{eid}/projects", headers={"X-Org-Id": ctx["oid_a"]}).status_code == 403
    assert b.get(f"{API}/planner/events/{ctx['eid_b']}/projects").json()["projects"] == []


def test_superadmin_acting_as_org(ctx):
    sa, eid, pid = ctx["sa"], ctx["eid_a"], ctx["pid"]
    assert sa.get(f"{API}/planner/events/{eid}/projects").status_code == 428  # no org selected: clear error, not 500
    h = {"X-Org-Id": ctx["oid_a"]}
    r = sa.get(f"{API}/planner/events/{eid}/projects", headers=h)
    assert r.status_code == 200, r.text
    assert [x["id"] for x in r.json()["projects"]] == [pid]
    assert sa.get(f"{API}/planner/projects/{pid}/revisions", headers=h).status_code == 200
    assert sa.get(f"{API}/planner/projects/{pid}", headers={"X-Org-Id": ctx["oid_b"]}).status_code == 404


def test_unauthenticated():
    assert requests.get(f"{API}/planner/events/x/projects").status_code == 401
