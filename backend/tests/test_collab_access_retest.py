# Retest iteration_212: HIGH-1 (events=all non riapre revocati/disattivati), HIGH-2 (persone limitate agli eventi autorizzati),
# aggiunta collaboratore esistente mantiene permessi, inviti revocati nascosti
import os, uuid, pytest, requests

BASE = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/") + "/api"
SA = ("manara.michele.pro@gmail.com", "CrmEvent2026!")
ADM = ("test_collab_admin@example.com", "TestCollab2026!")
COL = ("test_collab_user@example.com", "TestCollab2026!")
UID = "user_fbcc64642896"
ORG = "b840476cb2b045368918165143d99a04"


def login(cred):
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": cred[0], "password": cred[1]})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def adm():
    return login(ADM)


@pytest.fixture(scope="module")
def sa():
    return login(SA)


@pytest.fixture(scope="module")
def ev(adm):
    m = {e["nome"]: e["id"] for e in adm.get(f"{BASE}/events").json()}
    return m["TEST_Evento Uno"], m["TEST_Evento Due"], m["TEST_Evento Tre"]


@pytest.fixture(scope="module")
def created(adm):
    ids = {"persons": [], "staff": []}
    yield ids
    for sid in ids["staff"]:
        adm.delete(f"{BASE}/staff/{sid}")
    for pid in ids["persons"]:
        adm.delete(f"{BASE}/persons/{pid}")


def perms(adm):
    r = adm.get(f"{BASE}/org/permissions")
    assert r.status_code == 200, r.text
    d = r.json()
    rows = d if isinstance(d, list) else (d.get("users") or d.get("rows") or d.get("members") or [])
    return next(x for x in rows if x.get("user_id") == UID)


def get_ev(eid):
    return login(COL).get(f"{BASE}/events/{eid}").status_code


class TestHigh1:
    def test_baseline(self, ev):
        e1, e2, e3 = ev
        c = login(COL)
        ids = {e["id"] for e in c.get(f"{BASE}/events").json()}
        assert e1 in ids and e3 in ids and e2 not in ids, ids
        assert c.get(f"{BASE}/events/{e2}").status_code == 404

    def test_events_all_keeps_revoked_closed(self, adm, ev):
        e1, e2, e3 = ev
        r = adm.put(f"{BASE}/org/permissions/{UID}", json={"events": "all"})
        assert r.status_code == 200, r.text
        assert get_ev(e2) == 404 and get_ev(e1) == 200 and get_ev(e3) == 200

    def test_events_all_keeps_disabled_closed_restore_works(self, adm, sa, ev):
        e1, e2, e3 = ev
        r = sa.post(f"{BASE}/platform/users/{UID}/memberships/{ORG}/events/{e3}", json={"action": "disable", "reason": "TEST"})
        assert r.status_code == 200, r.text
        try:
            assert get_ev(e3) == 404
            assert adm.put(f"{BASE}/org/permissions/{UID}", json={"events": "all"}).status_code == 200
            assert get_ev(e3) == 404, "events=all reopened a disabled event"
        finally:
            r = sa.post(f"{BASE}/platform/users/{UID}/memberships/{ORG}/events/{e3}", json={"action": "restore"})
        assert r.status_code == 200, r.text
        assert get_ev(e3) == 200

    def test_explicit_tick_reopens_revoked(self, adm, ev):
        e1, e2, e3 = ev
        r = adm.put(f"{BASE}/org/permissions/{UID}", json={"events": [e1, e2, e3]})
        assert r.status_code == 200, r.text
        assert get_ev(e2) == 200
        # revoca di nuovo da scheda evento -> chiuso, e "tutti" non lo riapre
        assert adm.post(f"{BASE}/events/{e2}/collaborators/{UID}/revoke").status_code == 200
        assert get_ev(e2) == 404
        assert adm.put(f"{BASE}/org/permissions/{UID}", json={"events": "all"}).status_code == 200
        assert get_ev(e2) == 404 and get_ev(e1) == 200 and get_ev(e3) == 200


class TestHigh2:
    def test_persons_limited_to_authorized_events(self, adm, ev, created):
        e1, e2, e3 = ev
        tag = uuid.uuid4().hex[:6]
        pa = adm.post(f"{BASE}/persons", json={"nome": "TEST_SoloDue", "cognome": tag, "email": f"test_solodue_{tag}@example.com"}).json()["id"]
        pb = adm.post(f"{BASE}/persons", json={"nome": "TEST_UnoDue", "cognome": tag, "email": f"test_unodue_{tag}@example.com"}).json()["id"]
        created["persons"] += [pa, pb]
        for pid, eid in ((pa, e2), (pb, e1), (pb, e2)):
            r = adm.post(f"{BASE}/staff", json={"persona_id": pid, "evento_id": eid, "categoria": "volontario"})
            assert r.status_code == 200, r.text
            created["staff"].append(r.json()["id"])
        c = login(COL)
        p_ids = {p["id"] for p in c.get(f"{BASE}/persons").json()}
        assert pa not in p_ids and pb in p_ids
        enr = {p["id"]: p for p in c.get(f"{BASE}/persons-enriched").json()}
        assert pa not in enr and pb in enr
        assert enr[pb]["eventi_ids"] == [e1], enr[pb]["eventi_ids"]
        assert "TEST_Evento Due" not in enr[pb]["eventi_nomi"]
        assert c.get(f"{BASE}/persons/{pa}/detail").status_code == 404
        d = c.get(f"{BASE}/persons/{pb}/detail")
        assert d.status_code == 200
        evs = {x["presence"]["evento_id"] for x in d.json()["events"]}
        assert e2 not in evs, f"detail leaks unauthorized event presences: {evs}"

    def test_own_row_only_authorized(self, ev):
        e1, e2, e3 = ev
        c = login(COL)
        me = next(p for p in c.get(f"{BASE}/persons-enriched").json() if (p.get("email") or "").lower() == COL[0])
        assert e2 not in me["eventi_ids"] and "TEST_Evento Due" not in me["eventi_nomi"]


class TestEventCard:
    def test_add_existing_keeps_permissions(self, adm, ev):
        e1, e2, e3 = ev
        before = perms(adm)
        r = adm.post(f"{BASE}/events/{e2}/collaborators", json={"nome": "Carla", "cognome": "Test", "email": COL[0],
                     "sections": {"eventi": ["view"]}, "flags": {"bulk_delete": True}})
        assert r.status_code == 200 and r.json()["mode"] == "added", r.text
        after = perms(adm)
        sb = (before.get("permissions") or before).get("sections")
        sa_ = (after.get("permissions") or after).get("sections")
        assert sb == sa_, (sb, sa_)
        assert get_ev(e2) == 200
        # ripristina stato seed: e2 revocato
        assert adm.post(f"{BASE}/events/{e2}/collaborators/{UID}/revoke").status_code == 200
        assert get_ev(e2) == 404

    def test_revoked_invites_hidden(self, adm, ev):
        e1, _, _ = ev
        email = f"test_hid_{uuid.uuid4().hex[:6]}@example.com"
        r = adm.post(f"{BASE}/events/{e1}/collaborators", json={"nome": "TEST_Hid", "cognome": "X", "email": email, "sections": {"eventi": ["view"]}})
        assert r.status_code == 200, r.text
        iid = r.json()["invite_id"]
        assert any(x.get("invite_id") == iid for x in adm.get(f"{BASE}/events/{e1}/collaborators").json()["rows"])
        assert adm.post(f"{BASE}/events/{e1}/collaborators/{iid}/revoke?kind=invite").status_code == 200
        rows = adm.get(f"{BASE}/events/{e1}/collaborators").json()["rows"]
        assert not any(x.get("invite_id") == iid or x.get("email") == email for x in rows)
