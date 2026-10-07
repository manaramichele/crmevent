"""Iter64 — Ruoli & Permessi per organizzazione (backend)."""
import os
import time
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://manage-events-12.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"

ADMIN = ("qa.eventi@crmeventqa.it", "QaEvents2026!")
USER = ("test_perm_user@crmeventqa.it", "TestPerm2026!")
COLLAB = ("test_perm_collab@crmeventqa.it", "TestPerm2026!")
SUPER = ("manara.michele.pro@gmail.com", "CrmEvent2026!")

QA_ORG = "org_qa_eventi"
EV1 = "ev_qa_1"
EV2 = "ev_qa_2"

USER_ID = "user_TEST_perm_user"
COLLAB_ID = "user_TEST_perm_collab"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_s():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def super_s():
    s = _login(*SUPER)
    s.headers["X-Org-Id"] = QA_ORG
    return s


def _reset(admin_s, uid, role):
    r = admin_s.put(f"{API}/org/permissions/{uid}", json={"role": role, "reset": True}, timeout=20)
    assert r.status_code == 200, r.text


@pytest.fixture(scope="module", autouse=True)
def reset_all(admin_s):
    # inizio: reset entrambi utenti ai predefiniti
    _reset(admin_s, USER_ID, "user")
    _reset(admin_s, COLLAB_ID, "collaboratore")
    yield
    # fine: ripristina
    _reset(admin_s, USER_ID, "user")
    _reset(admin_s, COLLAB_ID, "collaboratore")


@pytest.fixture
def user_s():
    return _login(*USER)


@pytest.fixture
def collab_s():
    return _login(*COLLAB)


# ---------- Collaboratore predefinito ----------
class TestCollabDefaults:
    ALLOWED_GET = ["events", "staff", "teams", "shifts", "companies", "persons", "activities",
                   "followups", "lodgings", "meals", "dashboard", "settings"]

    def test_allowed_sections_200(self, collab_s):
        for p in self.ALLOWED_GET:
            r = collab_s.get(f"{API}/{p}", timeout=20)
            assert r.status_code == 200, f"GET /{p} -> {r.status_code} {r.text[:200]}"

    def test_deals_403(self, collab_s):
        r = collab_s.get(f"{API}/deals", timeout=20)
        assert r.status_code == 403, r.text

    def test_pipeline_403(self, collab_s):
        r = collab_s.get(f"{API}/events/{EV1}/pipeline/tasks", timeout=20)
        assert r.status_code == 403
        r2 = collab_s.get(f"{API}/pipeline/attention", timeout=20)
        assert r2.status_code == 403

    def test_write_blocked_403(self, collab_s):
        # POST attivita non consentito
        r = collab_s.post(f"{API}/activities", json={"evento_id": EV1, "titolo": "TEST_x"}, timeout=20)
        assert r.status_code == 403
        # DELETE followups (id fittizio) deve essere 403 prima del lookup
        r = collab_s.delete(f"{API}/followups/zzz_not_exists", timeout=20)
        assert r.status_code == 403

    def test_admin_only_endpoints_403(self, collab_s):
        for p in ["account/subscription", "account/billing", "credits/ledger",
                  "settings/usage", "org/permissions"]:
            r = collab_s.get(f"{API}/{p}", timeout=20)
            assert r.status_code == 403, f"GET /{p} -> {r.status_code}"
        r = collab_s.put(f"{API}/settings", json={}, timeout=20)
        assert r.status_code == 403
        r = collab_s.post(f"{API}/events/{EV1}/activate", json={}, timeout=20)
        assert r.status_code == 403

    def test_dashboard_no_sponsor_data(self, collab_s):
        r = collab_s.get(f"{API}/dashboard", timeout=20)
        assert r.status_code == 200
        data = r.json()
        comm = (data.get("commerciale") or {})
        assert comm.get("valore_pipeline", 0) in (0, None, 0.0), f"sponsor data leak: {comm}"


# ---------- Utente predefinito ----------
class TestUserDefaults:
    def test_crud_sections_200(self, user_s):
        for p in ["events", "staff", "deals", "activities", "followups", "companies", "persons", "dashboard"]:
            r = user_s.get(f"{API}/{p}", timeout=20)
            assert r.status_code == 200, f"GET /{p} -> {r.status_code}"

    def test_admin_endpoints_403(self, user_s):
        for p in ["org/permissions", "account/subscription", "account/billing"]:
            r = user_s.get(f"{API}/{p}", timeout=20)
            assert r.status_code == 403


# ---------- Restrizione per evento ----------
class TestEventRestriction:
    def test_user_restricted_to_ev1(self, admin_s, user_s):
        r = admin_s.put(f"{API}/org/permissions/{USER_ID}",
                        json={"role": "user", "events": [EV1]}, timeout=20)
        assert r.status_code == 200, r.text
        # user re-login per avere perm aggiornati non necessario (controllo per-request)
        us = _login(*USER)
        # Events list -> solo EV1
        r = us.get(f"{API}/events", timeout=20)
        assert r.status_code == 200
        ids = [e.get("id") for e in r.json()]
        assert ids == [EV1] or (EV1 in ids and all(x == EV1 for x in ids)), f"got events: {ids}"
        # EV2 -> 404
        r = us.get(f"{API}/events/{EV2}", timeout=20)
        assert r.status_code == 404, r.text
        r = us.get(f"{API}/events/{EV2}/briefing-live", timeout=20)
        assert r.status_code == 404
        r = us.get(f"{API}/staff", params={"evento_id": EV2}, timeout=20)
        assert r.status_code == 404
        # POST on EV2 -> 404
        r = us.post(f"{API}/activities", json={"evento_id": EV2, "titolo": "TEST_blocked"}, timeout=20)
        assert r.status_code == 404
        # POST /events -> 403
        r = us.post(f"{API}/events", json={"nome": "TEST_newevt"}, timeout=20)
        assert r.status_code == 403
        # dashboard events_count = 1
        r = us.get(f"{API}/dashboard", timeout=20)
        assert r.status_code == 200
        d = r.json()
        # ricerca field eventi_totale
        ev_count = (d.get("eventi") or {}).get("eventi_totali") or d.get("eventi_totali") or d.get("events_count")
        # non assertivo: solo verifichiamo che staff/record che vengono siano di EV1
        r = us.get(f"{API}/staff", timeout=20)
        assert r.status_code == 200
        for s in r.json():
            e = s.get("evento_id")
            assert e in (None, "", EV1), f"staff leak evento: {e}"
        # cleanup: ripristina
        r = admin_s.put(f"{API}/org/permissions/{USER_ID}", json={"role": "user", "reset": True}, timeout=20)
        assert r.status_code == 200


# ---------- Permessi granulari ----------
class TestGranular:
    def test_sponsor_view_only(self, admin_s, collab_s):
        r = admin_s.put(f"{API}/org/permissions/{COLLAB_ID}",
                        json={"role": "collaboratore", "sections": {"sponsor": ["view"]}}, timeout=20)
        assert r.status_code == 200, r.text
        cs = _login(*COLLAB)
        r = cs.get(f"{API}/deals", timeout=20)
        assert r.status_code == 200
        r = cs.post(f"{API}/deals", json={"evento_id": EV1, "titolo": "TEST_deal"}, timeout=20)
        assert r.status_code == 403

    def test_attivita_view_create(self, admin_s):
        r = admin_s.put(f"{API}/org/permissions/{COLLAB_ID}",
                        json={"role": "collaboratore",
                              "sections": {"attivita": ["view", "create"], "sponsor": ["view"]}}, timeout=20)
        assert r.status_code == 200
        cs = _login(*COLLAB)
        r = cs.post(f"{API}/activities",
                    json={"evento_id": EV1, "titolo": "TEST_act_perm", "tipo": "task"}, timeout=20)
        assert r.status_code in (200, 201), r.text
        aid = r.json().get("id")
        assert aid
        # DELETE dal collaboratore -> 403
        r2 = cs.delete(f"{API}/activities/{aid}", timeout=20)
        assert r2.status_code == 403
        # Admin elimina il record TEST_
        r3 = admin_s.delete(f"{API}/activities/{aid}", timeout=20)
        assert r3.status_code in (200, 204), r3.text
        # reset
        admin_s.put(f"{API}/org/permissions/{COLLAB_ID}",
                    json={"role": "collaboratore", "reset": True}, timeout=20)


# ---------- Gestione permessi ----------
class TestPermManagement:
    def test_self_edit_400(self, admin_s):
        admin_id = admin_s.get(f"{API}/auth/me", timeout=20).json().get("user_id")
        if not admin_id:
            pytest.skip("no admin id")
        r = admin_s.put(f"{API}/org/permissions/{admin_id}",
                        json={"role": "user", "reset": True}, timeout=20)
        assert r.status_code == 400

    def test_invalid_role_400(self, admin_s):
        r = admin_s.put(f"{API}/org/permissions/{COLLAB_ID}",
                        json={"role": "pippo"}, timeout=20)
        assert r.status_code == 400

    def test_non_member_404(self, admin_s):
        r = admin_s.put(f"{API}/org/permissions/user_does_not_exist_zzz",
                        json={"role": "user"}, timeout=20)
        assert r.status_code == 404

    def test_audit_log(self, admin_s):
        # trigger a change
        r = admin_s.put(f"{API}/org/permissions/{COLLAB_ID}",
                        json={"role": "collaboratore",
                              "sections": {"attivita": ["view"]}}, timeout=20)
        assert r.status_code == 200
        time.sleep(0.5)
        r = admin_s.get(f"{API}/org/permissions/audit", timeout=20)
        assert r.status_code == 200
        items = r.json().get("items") or []
        assert any(it.get("action") == "permissions_changed" for it in items), items[:3]
        # Prima/Dopo in detail
        pc = [it for it in items if it.get("action") == "permissions_changed"][0]
        assert "Prima" in (pc.get("detail") or "") and "Dopo" in (pc.get("detail") or "")
        # reset
        admin_s.put(f"{API}/org/permissions/{COLLAB_ID}",
                    json={"role": "collaboratore", "reset": True}, timeout=20)

    def test_superadmin_audit_includes_perm(self, super_s):
        r = super_s.get(f"{API}/platform/audit", timeout=20)
        assert r.status_code == 200, r.text
        items = r.json().get("items") or r.json() or []
        if isinstance(items, dict):
            items = items.get("items") or []
        actions = [it.get("action") for it in items]
        assert "permissions_changed" in actions, actions[:10]


# ---------- Revoca immediata ----------
class TestImmediateRevocation:
    def test_revoke_without_relogin(self, admin_s):
        # concedi attivita full
        admin_s.put(f"{API}/org/permissions/{COLLAB_ID}",
                    json={"role": "collaboratore",
                          "sections": {"attivita": ["view", "create", "edit", "delete"]}}, timeout=20)
        cs = _login(*COLLAB)
        r = cs.get(f"{API}/activities", timeout=20)
        assert r.status_code == 200
        # revoca attivita
        admin_s.put(f"{API}/org/permissions/{COLLAB_ID}",
                    json={"role": "collaboratore", "sections": {}}, timeout=20)
        r = cs.get(f"{API}/activities", timeout=20)
        assert r.status_code == 403, f"stale perms? got {r.status_code}"
        admin_s.put(f"{API}/org/permissions/{COLLAB_ID}",
                    json={"role": "collaboratore", "reset": True}, timeout=20)


# ---------- Isolamento multi-tenant ----------
class TestTenantIsolation:
    def test_other_org_member_404(self, admin_s):
        # super admin user id (non member of org_qa_eventi? ma a volte sì). Usa id garantito di altra org:
        r = admin_s.put(f"{API}/org/permissions/user_other_tenant_xyz",
                        json={"role": "user"}, timeout=20)
        assert r.status_code == 404

    def test_wrong_org_header_403(self):
        s = _login(*COLLAB)
        s.headers["X-Org-Id"] = "org_does_not_exist_zzz"
        r = s.get(f"{API}/events", timeout=20)
        assert r.status_code in (403, 404)


# ---------- Compatibilità ----------
class TestCompat:
    def test_admin_full_access(self, admin_s):
        for p in ["events", "staff", "deals", "activities", "followups",
                  "companies", "persons", "lodgings", "meals", "dashboard",
                  "settings", "org/permissions", "account/subscription"]:
            r = admin_s.get(f"{API}/{p}", timeout=20)
            assert r.status_code == 200, f"admin GET /{p} -> {r.status_code}"

    def test_super_admin_full_access(self, super_s):
        for p in ["events", "staff", "deals", "activities", "dashboard"]:
            r = super_s.get(f"{API}/{p}", timeout=20)
            assert r.status_code == 200, f"super GET /{p} -> {r.status_code}"

    def test_role_change_accepts_collaboratore(self, admin_s):
        r = admin_s.patch(f"{API}/platform/organizations/{QA_ORG}/members/{USER_ID}",
                          json={"role": "collaboratore"}, timeout=20)
        assert r.status_code == 200, r.text
        # verifica che permissions siano azzerate
        r = admin_s.get(f"{API}/org/permissions", timeout=20)
        row = next((m for m in r.json().get("members", []) if m["user_id"] == USER_ID), None)
        assert row and row["role"] == "collaboratore"
        assert row.get("custom") is False, f"permissions non azzerati: custom={row.get('custom')}"
        # ripristina user
        r = admin_s.patch(f"{API}/platform/organizations/{QA_ORG}/members/{USER_ID}",
                          json={"role": "user"}, timeout=20)
        assert r.status_code == 200
