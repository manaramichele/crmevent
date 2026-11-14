# Event Map download via authenticated API (X-Org-Id), free ("omaggio") orgs same rights as paid ones, SA org list.
# PREVIEW DB only: creates TEST_ orgs and removes them at the end.
import os
import uuid

import pytest
import requests
from pymongo import MongoClient

API = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/") + "/api"
mdb = MongoClient("mongodb://localhost:27017")["test_database"]
SA = ("manara.michele.pro@gmail.com", "CrmEvent2026!")
DEMO = ("test_em_1794651032@example.com", "TestEventMap2026!")
CREATED = []


def _login(email, pw):
    s = requests.Session()
    assert s.post(f"{API}/auth/login", json={"email": email, "password": pw}).status_code == 200
    return s


def _register(label):
    s = requests.Session()
    r = s.post(f"{API}/auth/register-organization", json={"nome": "TEST", "cognome": "FREE", "email": f"test_free_{uuid.uuid4().hex[:8]}@example.com",
                                                          "password": "TestFree2026!", "org_name": f"TEST_FREE {label} {uuid.uuid4().hex[:4]}",
                                                          "telefono": "+393471234567", "accept_terms": True})
    assert r.status_code in (200, 201), r.text
    oid = s.get(f"{API}/auth/me").json()["org_id"]
    CREATED.append(oid)
    return s, oid


@pytest.fixture(scope="module")
def sa():
    s = _login(*SA)
    yield s
    for oid in CREATED:
        real = (mdb.organizations.find_one({"id": oid}) or {}).get("nome")
        if real:
            s.delete(f"{API}/platform/organizations/{oid}", json={"confirm_name": real})


@pytest.fixture(scope="module")
def demo():
    s = _login(*DEMO)
    oid = s.get(f"{API}/auth/me").json()["org_id"]
    vids = list(mdb.eventmap_videos.find({"org_id": oid, "status": "completed"}, {"_id": 0, "id": 1, "format": 1, "duration": 1, "track_name": 1}))
    by_fmt = {}
    for v in vids:
        by_fmt.setdefault(v["format"], v)
    assert set(by_fmt) >= {"9:16", "1:1", "16:9"}, by_fmt
    return s, oid, by_fmt


def _is_mp4(b):
    return len(b) > 100_000 and b[4:8] == b"ftyp"


@pytest.mark.parametrize("fmt", ["9:16", "1:1", "16:9"])
def test_download_superadmin_with_x_org_id(sa, demo, fmt):
    _, oid, by_fmt = demo
    v = by_fmt[fmt]
    r = sa.get(f"{API}/eventmap/videos/{v['id']}/file", params={"download": 1})
    assert r.status_code == 428  # senza organizzazione attiva: errore chiaro, non il file
    r = sa.get(f"{API}/eventmap/videos/{v['id']}/file", params={"download": 1}, headers={"X-Org-Id": oid})
    assert r.status_code == 200, r.text[:200]
    assert r.headers["content-type"] == "video/mp4" and _is_mp4(r.content)
    cd = r.headers["content-disposition"]
    assert cd.startswith("attachment;") and f"-{fmt.replace(':', 'x')}-{v['duration']}s.mp4" in cd


@pytest.mark.parametrize("fmt", ["9:16", "1:1", "16:9"])
def test_download_organizer(demo, fmt):
    s, _, by_fmt = demo
    r = s.get(f"{API}/eventmap/videos/{by_fmt[fmt]['id']}/file", params={"download": 1})
    assert r.status_code == 200 and _is_mp4(r.content)


def test_download_isolation(sa, demo):
    _, oid, by_fmt = demo
    other, other_oid = _register("Other")
    vid = by_fmt["9:16"]["id"]
    assert other.get(f"{API}/eventmap/videos/{vid}/file", params={"download": 1}).status_code == 404
    assert other.get(f"{API}/eventmap/videos/{vid}/file", headers={"X-Org-Id": oid}).status_code == 403
    assert sa.get(f"{API}/eventmap/videos/{vid}/file", headers={"X-Org-Id": other_oid}).status_code == 404
    assert requests.get(f"{API}/eventmap/videos/{vid}/file").status_code == 401


def _rights(s, headers=None):
    p = s.get(f"{API}/addons/planner", headers=headers).json()
    m = s.get(f"{API}/addons/eventmap", headers=headers).json()
    return p, m


def test_free_orgs_same_rights_as_paid(sa):
    paid, paid_id = _register("Paid")
    mdb.organizations.update_one({"id": paid_id}, {"$set": {"saas.plan": "gold", "saas.stripe_status": "active", "saas.billing_cycle": "yearly",
                                                           "saas.trial_end": "2020-01-01T00:00:00+00:00"}})
    comp, comp_id = _register("Comp")
    mdb.organizations.update_one({"id": comp_id}, {"$set": {"saas.trial_end": "2020-01-01T00:00:00+00:00"}})
    assert sa.put(f"{API}/platform/saas/orgs/{comp_id}/admin", json={"plan": "gold", "status": "active", "comp": True}).status_code == 200
    r = sa.post(f"{API}/platform/organizations", json={"nome": f"TEST_FREE Interna {uuid.uuid4().hex[:4]}", "type": "interna"})
    assert r.status_code == 200, r.text
    int_id = r.json()["id"]
    CREATED.append(int_id)
    assert sa.patch(f"{API}/platform/organizations/{int_id}", json={"formula": "gold"}).status_code == 200

    results = {}
    for name, s, oid, h in (("paid", paid, paid_id, None), ("comp", comp, comp_id, None), ("interna", sa, int_id, {"X-Org-Id": int_id})):
        p, m = _rights(s, h)
        assert p["plan"] == "gold" and m["plan"] == "gold", (name, p.get("mode"), p.get("plan"))
        eid = s.post(f"{API}/events", json={"nome": f"TEST_FREE {name} evento", "data_inizio": "2026-12-13"}, headers=h).json()["id"]
        assert s.post(f"{API}/addons/eventmap/events/{eid}/activate", headers=h).status_code == 200
        assert s.post(f"{API}/addons/planner/events/{eid}/activate", headers=h).status_code == 200
        p, m = _rights(s, h)
        st = s.get(f"{API}/eventmap/events/{eid}", headers=h).json()
        assert st["rights"]["active"] and st["rights"]["videos_remaining"] == m["videos_available"]
        assert s.get(f"{API}/planner/events/{eid}/projects", headers=h).status_code == 200
        pr = s.post(f"{API}/planner/events/{eid}/projects", json={"nome": "TEST_FREE progetto"}, headers=h)
        assert pr.status_code == 200, (name, pr.text)
        results[name] = (p["included"], p["included_used"], m["included"], m["included_used"], m["videos_total"], m["videos_available"])
    per_event = max(1, int((mdb.addon_config.find_one({"id": "config"}) or {}).get("eventmap", {}).get("included_videos") or 0))
    assert results["paid"] == results["comp"] == results["interna"] == (1, 1, 3, 1, per_event, per_event), results

    rows = {r["id"]: r for r in sa.get(f"{API}/platform/addons/orgs").json()}
    for oid in (paid_id, comp_id, int_id):
        assert oid in rows, "organizzazione assente dall'elenco Super Admin Event Planner / Event Map"
        assert rows[oid]["plan_label"] == "GOLD" and rows[oid]["eventmap"]["videos_total"] == per_event
    assert rows[int_id]["type"] == "interna"
