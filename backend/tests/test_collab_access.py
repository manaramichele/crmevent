# Collaboratori per evento + gestione accessi Super Admin (iteration 211)
import os, uuid, pytest, requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") + "/api"
SA = ("manara.michele.pro@gmail.com", "CrmEvent2026!")
ADM = ("test_collab_admin@example.com", "TestCollab2026!")
COL = ("test_collab_user@example.com", "TestCollab2026!")
CARLA = "user_23ab8651c50d"
ORG = "5a80bfbe69a74355a2ec3f0ae81df5f6"
UNO, DUE, TRE = "fba084fcbe3f41f29a81e4e38cf1ff31", "8c92c85753f34afa84c9c03f453e2fc7", "c2f01d0c203947edafbcc55e988b2e85"


def login(cred):
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": cred[0], "password": cred[1]})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def sa():
    return login(SA)


@pytest.fixture(scope="module")
def adm():
    return login(ADM)


def rows(s, eid):
    r = s.get(f"{BASE}/events/{eid}/collaborators")
    assert r.status_code == 200, r.text
    return r.json()["rows"]


def carla_row(s, eid):
    return next((x for x in rows(s, eid) if x.get("user_id") == CARLA), None)


# --- Scoping collaboratore: 404 eventi non autorizzati, 403 sezioni/flag
class TestCollabScope:
    def test_events_list_only_authorized(self):
        c = login(COL)
        ids = {e["id"] for e in c.get(f"{BASE}/events").json()}
        assert TRE not in ids and UNO in ids

    def test_unauthorized_event_404(self):
        c = login(COL)
        assert c.get(f"{BASE}/events/{TRE}").status_code == 404
        assert c.get(f"{BASE}/events/{TRE}/collaborators").status_code == 404

    def test_section_403(self):
        c = login(COL)
        assert c.get(f"{BASE}/companies").status_code == 403
        assert c.get(f"{BASE}/shifts").status_code == 403

    def test_flag_export_403(self):
        c = login(COL)
        r = c.get(f"{BASE}/iscritti/export", params={"evento_id": UNO})
        assert r.status_code == 403, r.text

    def test_manage_grant_capped(self):
        c = login(COL)
        email = f"test_cap_{uuid.uuid4().hex[:6]}@example.com"
        r = c.post(f"{BASE}/events/{UNO}/collaborators", json={"nome": "TEST_Cap", "cognome": "X", "email": email,
                   "sections": {"aziende": ["view", "edit"], "eventi": ["view"]}, "flags": {"export_personal": True}})
        assert r.status_code == 200, r.text
        row = next(x for x in rows(c, UNO) if x["email"] == email)
        assert row["sections"]["aziende"] == [] and row["sections"]["eventi"] == ["view"]
        assert row["flags"]["export_personal"] is False
        c.post(f"{BASE}/events/{UNO}/collaborators/{row['invite_id']}/revoke?kind=invite")


# --- Scheda evento: invito / reinvio / modifica / revoca
class TestEventCollaborators:
    def test_invite_resend_edit_revoke(self, adm):
        email = f"test_inv_{uuid.uuid4().hex[:6]}@example.com"
        r = adm.post(f"{BASE}/events/{TRE}/collaborators", json={"nome": "TEST_Nuovo", "cognome": "Collab", "email": email,
                     "sections": {"eventi": ["view"], "staff": ["view", "edit"]}, "flags": {"bulk_delete": True}})
        assert r.status_code == 200 and r.json()["mode"] == "invited", r.text
        iid = r.json()["invite_id"]
        row = next(x for x in rows(adm, TRE) if x.get("invite_id") == iid)
        assert row["invite_status"] == "pending" and row["access_label"] == "Invito in attesa"
        assert row["flags"]["bulk_delete"] is True and row["flags"]["export_personal"] is False
        assert adm.post(f"{BASE}/events/{TRE}/collaborators/{iid}/resend").status_code == 200
        assert adm.put(f"{BASE}/events/{TRE}/collaborators/{iid}?kind=invite", json={"sections": {"eventi": ["view"]}}).status_code == 200
        row = next(x for x in rows(adm, TRE) if x.get("invite_id") == iid)
        assert row["sections"]["staff"] == []
        assert adm.post(f"{BASE}/events/{TRE}/collaborators/{iid}/revoke?kind=invite").status_code == 200
        row = next(x for x in rows(adm, TRE) if x.get("invite_id") == iid)
        assert row["invite_status"] == "revoked"

    def test_existing_collab_added_no_duplicate_then_revoked(self, adm):
        r = adm.post(f"{BASE}/events/{TRE}/collaborators", json={"nome": "Carla", "cognome": "Test", "email": COL[0],
                     "sections": {"eventi": ["view"], "staff": ["view"]}})
        assert r.status_code == 200 and r.json()["mode"] == "added", r.text
        assert carla_row(adm, TRE)["access_status"] == "active"
        persons = adm.get(f"{BASE}/persons", params={"q": COL[0]}).json()
        items = persons if isinstance(persons, list) else persons.get("items", [])
        assert len([p for p in items if (p.get("email") or "").lower() == COL[0]]) <= 1
        c = login(COL)
        assert c.get(f"{BASE}/events/{TRE}").status_code == 200
        assert adm.post(f"{BASE}/events/{TRE}/collaborators/{CARLA}/revoke").status_code == 200
        assert c.get(f"{BASE}/events/{TRE}").status_code == 404
        row = carla_row(adm, TRE)
        assert row is None or row["access_status"] == "revoked"
        assert carla_row(adm, UNO)["access_status"] == "active"


# --- Super Admin: stato per evento, account, organizzazione
class TestSuperAdmin:
    def ev(self, sa, eid, action, **kw):
        return sa.post(f"{BASE}/platform/users/{CARLA}/memberships/{ORG}/events/{eid}", json={"action": action, **kw})

    def test_access_view(self, sa):
        r = sa.get(f"{BASE}/platform/users/{CARLA}/access")
        assert r.status_code == 200
        m = next(x for x in r.json()["memberships"] if x["org_id"] == ORG)
        assert m["role"] == "collaboratore"

    def test_event_cycle_revoked_needs_explicit_assign(self, sa):
        c = login(COL)
        assert self.ev(sa, TRE, "restore").status_code == 400  # revocato non si ripristina
        assert self.ev(sa, TRE, "assign").status_code == 400  # serve scelta permessi
        r = self.ev(sa, TRE, "assign", sections={"eventi": ["view"], "staff": ["view", "edit"], "copertura": ["view"]})
        assert r.status_code == 200 and r.json()["status"] == "active", r.text
        assert c.get(f"{BASE}/events/{TRE}").status_code == 200
        assert self.ev(sa, TRE, "disable", reason="TEST").json()["status"] == "disabled"
        assert c.get(f"{BASE}/events/{TRE}").status_code == 404
        assert c.get(f"{BASE}/events/{UNO}").status_code == 200
        assert self.ev(sa, TRE, "restore").json()["status"] == "active"
        assert c.get(f"{BASE}/events/{TRE}").status_code == 200
        assert self.ev(sa, TRE, "revoke").json()["status"] == "revoked"
        assert c.get(f"{BASE}/events/{TRE}").status_code == 404

    def test_account_disable_enable(self, sa):
        c = login(COL)
        r = sa.post(f"{BASE}/platform/users/{CARLA}/state", json={"active": False, "reason": "TEST_motivo"})
        assert r.status_code == 200 and r.json()["changed"], r.text
        try:
            assert c.get(f"{BASE}/auth/me").status_code in (401, 403)
            assert requests.post(f"{BASE}/auth/login", json={"email": COL[0], "password": COL[1]}).status_code in (401, 403)
            acc = sa.get(f"{BASE}/platform/users/{CARLA}/access").json()
            assert acc["active"] is False and acc["deactivation_reason"] == "TEST_motivo"
        finally:
            assert sa.post(f"{BASE}/platform/users/{CARLA}/state", json={"active": True}).status_code == 200
        c2 = login(COL)
        ids = {e["id"] for e in c2.get(f"{BASE}/events").json()}
        assert UNO in ids

    def test_org_membership_disable_enable(self, sa):
        r = sa.post(f"{BASE}/platform/users/{CARLA}/memberships/{ORG}/state", json={"active": False, "reason": "TEST"})
        assert r.status_code == 200, r.text
        try:
            s = requests.Session()
            lr = s.post(f"{BASE}/auth/login", json={"email": COL[0], "password": COL[1]})
            if lr.status_code == 200:
                me = s.get(f"{BASE}/auth/me").json()
                assert s.get(f"{BASE}/events/{UNO}").status_code in (401, 403, 404), me.get("organizations")
                assert s.get(f"{BASE}/staff").status_code in (401, 403, 404)
        finally:
            assert sa.post(f"{BASE}/platform/users/{CARLA}/memberships/{ORG}/state", json={"active": True}).status_code == 200
        assert login(COL).get(f"{BASE}/events/{UNO}").status_code == 200

    def test_cannot_disable_superadmin(self, sa):
        me = sa.get(f"{BASE}/auth/me").json()
        r = sa.post(f"{BASE}/platform/users/{me['user_id']}/state", json={"active": False})
        assert r.status_code == 400

    def test_non_sa_forbidden(self, adm):
        assert adm.post(f"{BASE}/platform/users/{CARLA}/state", json={"active": False}).status_code == 403

    def test_audit_entries(self, sa):
        r = sa.get(f"{BASE}/platform/audit", params={"q": COL[0]})
        assert r.status_code == 200
        txt = r.text
        assert "account_disabled" in txt or "collab_event" in txt
