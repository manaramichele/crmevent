"""
Backend regression tests for the CRMEvent "GUIDA INFORMATIVA" tutorial feature.
Covers T22-T28 (no-mutation / shape / tenant isolation / superadmin no-op).
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ACCOUNTS = {
    "qa":      ("qa.eventi@crmeventqa.it",       "QaEvents2026!"),
    "zero":    ("test_tut_zero@crmeventqa.it",   "TestTut2026!"),
    "one":     ("test_tut_one@crmeventqa.it",    "TestTut2026!"),
    "super":   ("manara.michele.pro@gmail.com",  "CrmEvent2026!"),
}


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="session")
def qa():       return _login(*ACCOUNTS["qa"])
@pytest.fixture(scope="session")
def zero():     return _login(*ACCOUNTS["zero"])
@pytest.fixture(scope="session")
def one():      return _login(*ACCOUNTS["one"])
@pytest.fixture(scope="session")
def superadm(): return _login(*ACCOUNTS["super"])


# ---------- T25: shape of /onboarding/status for admin ----------
class TestStatusShape:
    def test_shape_no_counters(self, qa):
        r = qa.get(f"{API}/onboarding/status", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("superadmin") is False
        assert d.get("show") is True
        assert isinstance(d.get("events"), list)
        state = d.get("state") or {}
        assert set(state.keys()).issubset({"seen", "later"}), f"unexpected state keys: {state.keys()}"
        for forbidden in ("steps", "next_step", "main_done", "main_total", "returning_user"):
            assert forbidden not in d, f"legacy field '{forbidden}' still present"
        for e in d["events"]:
            assert set(e.keys()) == {"id", "nome"}, f"unexpected event keys: {e.keys()}"


# ---------- T26: superadmin is a no-op ----------
class TestSuperadmin:
    def test_super_status(self, superadm):
        r = superadm.get(f"{API}/onboarding/status", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["superadmin"] is True
        assert d["events"] == []

    def test_super_state_noop(self, superadm):
        r = superadm.post(f"{API}/onboarding/state",
                          json={"seen": True, "later": True, "completed": True},
                          timeout=15)
        assert r.status_code == 200
        assert r.json().get("superadmin") is True
        # second status still superadmin, no onboarding leaked
        r2 = superadm.get(f"{API}/onboarding/status", timeout=15).json()
        assert "state" in r2 and r2["state"] == {}


# ---------- T28: tenant isolation ----------
class TestTenantIsolation:
    def test_zero_sees_no_events(self, zero):
        d = zero.get(f"{API}/onboarding/status", timeout=15).json()
        assert d["events"] == [], f"expected 0 events, got {d['events']}"

    def test_one_sees_only_own(self, one):
        d = one.get(f"{API}/onboarding/status", timeout=15).json()
        ids = [e["id"] for e in d["events"]]
        assert ids == ["ev_TEST_tut_one"], f"got {ids}"
        assert d["events"][0]["nome"] == "TEST_Evento Unico"

    def test_qa_multi_events(self, qa):
        d = qa.get(f"{API}/onboarding/status", timeout=15).json()
        assert len(d["events"]) >= 2, f"QA should have multiple events, got {len(d['events'])}"
        # no event from other orgs
        for e in d["events"]:
            assert "TEST_" not in (e.get("nome") or ""), e


# ---------- T22/T23: full QA baseline unchanged after reading status/state many times ----------
class TestNoMutations:
    COLLECTIONS_ENDPOINTS = [
        ("/events", None),
        ("/activities", None),
        ("/deals", None),
    ]

    def _snapshot(self, s):
        snap = {}
        for path, _ in self.COLLECTIONS_ENDPOINTS:
            r = s.get(f"{API}{path}", timeout=20)
            if r.status_code == 200:
                data = r.json()
                items = data if isinstance(data, list) else (data.get("items") or data.get("data") or [])
                snap[path] = len(items)
        # credits
        r = s.get(f"{API}/credits/balance", timeout=15)
        if r.status_code == 200:
            snap["credits.balance"] = r.json().get("balance")
        return snap

    def test_tutorial_reads_do_not_mutate(self, qa):
        before = self._snapshot(qa)
        # simulate a full tutorial walk: hit status many times + idempotent state writes
        for _ in range(5):
            qa.get(f"{API}/onboarding/status", timeout=15)
        qa.post(f"{API}/onboarding/state", json={"seen": True}, timeout=15)
        qa.post(f"{API}/onboarding/state", json={"later": False}, timeout=15)
        after = self._snapshot(qa)
        assert before == after, f"state drift: before={before} after={after}"


# ---------- T02/T36: seen flag persistence for zero account ----------
class TestSeenPersistence:
    def test_seen_flag_sticks(self, zero):
        # emulate what the welcome dialog does on first mount
        zero.post(f"{API}/onboarding/state", json={"seen": True}, timeout=15)
        d = zero.get(f"{API}/onboarding/status", timeout=15).json()
        assert d["state"]["seen"] is True
        # second status call still true (persisted)
        d2 = zero.get(f"{API}/onboarding/status", timeout=15).json()
        assert d2["state"]["seen"] is True
