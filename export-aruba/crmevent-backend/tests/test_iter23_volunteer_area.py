"""
Iteration 23 - Staff/Volunteer personal area 'La mia partecipazione'.

Verifies:
- GET /api/me/events/{event_id} scoping (lodgings/meals only for the caller)
- Admin/economic fields stripped for staff
- No leakage of other person's data (OTHER-LODGING, OTHER-MEAL, SECRETO-*)
- Event dashboard hides 'da_contattare' (op_stato) and shows 'confermato'
- GPX file endpoint returns 200
"""
import os
import re
import requests
import pytest

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].splitlines()[0]).rstrip("/")
MEMBER_EMAIL = "staffmember@tabtest.crmevent.it"
MEMBER_PW = "MemberTest2026!"
EVENT_ID = "trail-del-lago-test"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": MEMBER_EMAIL, "password": MEMBER_PW},
               timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


def test_me_events_list(session):
    r = session.get(f"{BASE_URL}/api/me/events", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    events = data if isinstance(data, list) else data.get("events") or data.get("items") or []
    ids = [(e.get("event") or {}).get("id") or e.get("id") or e.get("evento_id") for e in events]
    assert EVENT_ID in ids, f"expected event {EVENT_ID} in {ids}"


def test_me_event_detail_scoped(session):
    r = session.get(f"{BASE_URL}/api/me/events/{EVENT_ID}", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()

    # basic event info
    ev = data.get("event") or data.get("evento") or data
    assert (ev.get("nome") or "").lower().startswith("trail"), ev

    # incarico state should be confermato, never da_contattare
    incarico = data.get("presence") or data.get("incarico") or data.get("staff") or {}
    stato = (incarico.get("stato") or "").lower()
    assert stato == "confermato", f"unexpected stato: {stato}"
    # blob-check: op_stato / da_contattare must NOT be present as user-facing state anywhere
    body_str = str(data)
    assert "da_contattare" not in body_str, "'da_contattare' leaked into member payload"

    # lodgings scoping
    lodgings = data.get("lodgings") or data.get("ospitalita") or []
    assert isinstance(lodgings, list)
    assert len(lodgings) == 1, f"expected exactly 1 lodging for member, got {len(lodgings)}"
    l = lodgings[0]
    # forbidden admin/economic fields
    for f in ["costo", "stato_pagamento", "note_amministrative", "a_carico_di", "codice_prenotazione"]:
        assert f not in l, f"lodging leaked admin field: {f}"
    # forbidden markers
    lstr = str(l)
    assert "SECRETO" not in lstr and "OTHER-LODGING" not in lstr

    # meals scoping
    meals = data.get("meals") or data.get("pasti") or []
    assert isinstance(meals, list)
    assert len(meals) == 1, f"expected exactly 1 meal for member, got {len(meals)}"
    m = meals[0]
    for f in ["costo", "note_amministrative"]:
        assert f not in m, f"meal leaked admin field: {f}"
    mstr = str(m)
    assert "SECRETO" not in mstr and "OTHER-MEAL" not in mstr


def test_gpx_file_served(session):
    # find gpx via event maps
    r = session.get(f"{BASE_URL}/api/me/events/{EVENT_ID}", timeout=15)
    data = r.json()
    maps = data.get("maps") or data.get("mappe") or data.get("event_maps") or []
    assert maps, "no event maps returned"
    gpx_url = maps[0].get("gpx_url") or ""
    m = re.search(r"/api/files/([a-f0-9]+)", gpx_url)
    assert m, f"unexpected gpx_url {gpx_url}"
    rf = session.get(f"{BASE_URL}{gpx_url}", timeout=15)
    assert rf.status_code == 200, rf.status_code
    assert b"<gpx" in rf.content
