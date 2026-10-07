"""Backend tests for Novità (news) feature.

Covers: superadmin endpoints (list/env/simulate/edit/publish/withdraw/delete),
user endpoints (list/unread/mark-read), audit entries, access control.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://manage-events-12.preview.emergentagent.com").rstrip("/")

SUPERADMIN = {"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"}
ORG_USER = {"email": "qa.eventi@crmeventqa.it", "password": "QaEvents2026!"}
RELEASE_ID = "2026-10-07-team-mobile"


def _login(creds):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"Login failed {creds['email']}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def sa():
    return _login(SUPERADMIN)


@pytest.fixture(scope="module")
def org():
    return _login(ORG_USER)


# tracked items to delete on teardown (only ones created by this test file)
_created_ids = []


@pytest.fixture(scope="module", autouse=True)
def _cleanup(sa):
    yield
    # Withdraw if published, then delete each created item
    for nid in _created_ids:
        try:
            sa.post(f"{BASE_URL}/api/platform/news/{nid}/withdraw", timeout=10)
        except Exception:
            pass
        try:
            sa.delete(f"{BASE_URL}/api/platform/news/{nid}", timeout=10)
        except Exception:
            pass


# ---------------- Access control ----------------
class TestAccess:
    def test_org_user_cannot_list_platform_news(self, org):
        r = org.get(f"{BASE_URL}/api/platform/news", timeout=15)
        assert r.status_code == 403

    def test_org_user_cannot_env(self, org):
        r = org.get(f"{BASE_URL}/api/platform/news/env", timeout=15)
        assert r.status_code == 403

    def test_org_user_cannot_simulate(self, org):
        r = org.post(f"{BASE_URL}/api/platform/news/simulate-release", json={"release_id": RELEASE_ID}, timeout=15)
        assert r.status_code == 403


# ---------------- Env & list ----------------
class TestEnv:
    def test_env_returns_releases(self, sa):
        r = sa.get(f"{BASE_URL}/api/platform/news/env", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "production" in data and isinstance(data["releases"], list)
        assert data["production"] is False  # preview env
        ids = [x["id"] for x in data["releases"]]
        assert RELEASE_ID in ids

    def test_admin_list_ok(self, sa):
        r = sa.get(f"{BASE_URL}/api/platform/news", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------------- Simulate (creates drafts) ----------------
class TestSimulateAndLifecycle:
    def test_simulate_unknown_release_404(self, sa):
        r = sa.post(f"{BASE_URL}/api/platform/news/simulate-release", json={"release_id": "nope-xxx"}, timeout=15)
        assert r.status_code == 404

    def test_simulate_creates_drafts(self, sa):
        r = sa.post(f"{BASE_URL}/api/platform/news/simulate-release", json={"release_id": RELEASE_ID}, timeout=60)
        assert r.status_code == 200
        created = r.json()["created"]
        assert created >= 1

        # find newest drafts for this release just created
        lst = sa.get(f"{BASE_URL}/api/platform/news", timeout=15).json()
        rel_drafts = [x for x in lst if x["release_id"] == RELEASE_ID and x["status"] == "bozza" and x.get("simulated")]
        assert len(rel_drafts) >= created
        # sort by created_at desc, take newest `created` as ours
        rel_drafts.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        ours = rel_drafts[:created]
        for d in ours:
            _created_ids.append(d["id"])
            assert d["status"] == "bozza"
            assert d["simulated"] is True
            assert d["generator"] in ("ai", "fallback")
            assert d["titolo"] and d["descrizione"]
            assert d["edited"] is False

    def test_edit_draft(self, sa):
        assert _created_ids, "need created draft"
        nid = _created_ids[0]
        payload = {"titolo": "QA Test Titolo", "descrizione": "QA Test descrizione aggiornata dal test backend."}
        r = sa.put(f"{BASE_URL}/api/platform/news/{nid}", json=payload, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["titolo"] == payload["titolo"]
        assert data["descrizione"] == payload["descrizione"]
        assert data["edited"] is True
        # generated_* must be preserved
        assert data["generated_titolo"] and data["generated_descrizione"]
        assert data["generated_titolo"] != payload["titolo"] or data["generated_descrizione"] != payload["descrizione"]

    def test_publish_draft(self, sa):
        nid = _created_ids[0]
        r = sa.post(f"{BASE_URL}/api/platform/news/{nid}/publish", timeout=15)
        assert r.status_code == 200
        # verify via list
        lst = sa.get(f"{BASE_URL}/api/platform/news", timeout=15).json()
        doc = next(x for x in lst if x["id"] == nid)
        assert doc["status"] == "pubblicata"
        assert doc["approved_by"] and doc["approved_by"].get("email") == SUPERADMIN["email"]
        assert doc["published_at"]

    def test_edit_published_rejected(self, sa):
        nid = _created_ids[0]
        r = sa.put(f"{BASE_URL}/api/platform/news/{nid}", json={"titolo": "x", "descrizione": "y"}, timeout=15)
        assert r.status_code == 400

    def test_delete_published_rejected(self, sa):
        nid = _created_ids[0]
        r = sa.delete(f"{BASE_URL}/api/platform/news/{nid}", timeout=15)
        assert r.status_code == 400

    def test_withdraw_published(self, sa):
        nid = _created_ids[0]
        r = sa.post(f"{BASE_URL}/api/platform/news/{nid}/withdraw", timeout=15)
        assert r.status_code == 200
        lst = sa.get(f"{BASE_URL}/api/platform/news", timeout=15).json()
        doc = next(x for x in lst if x["id"] == nid)
        assert doc["status"] == "ritirata"

    def test_republish_withdrawn(self, sa):
        nid = _created_ids[0]
        r = sa.post(f"{BASE_URL}/api/platform/news/{nid}/publish", timeout=15)
        assert r.status_code == 200


# ---------------- User endpoints ----------------
class TestUserEndpoints:
    def test_user_news_list_only_published(self, org):
        r = org.get(f"{BASE_URL}/api/news", timeout=15)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        # must contain the republished one
        pub_id = _created_ids[0]
        found = next((x for x in items if x["id"] == pub_id), None)
        assert found is not None, "published item not visible to user"
        # fields: no admin leaks
        allowed = {"id", "titolo", "descrizione", "area", "published_at"}
        for k in ("release_id", "generated_titolo", "generated_descrizione", "approved_by", "simulated", "source_notes", "status"):
            assert k not in found, f"field {k} leaked to user"

    def test_unread_count_and_mark_read(self, org):
        # mark read first
        r0 = org.post(f"{BASE_URL}/api/news/mark-read", timeout=15)
        assert r0.status_code == 200
        time.sleep(1)
        r1 = org.get(f"{BASE_URL}/api/news/unread-count", timeout=15)
        assert r1.status_code == 200
        assert r1.json()["count"] == 0

    def test_publishing_increments_unread(self, sa, org):
        # need a second draft; use second item from simulate, or simulate again
        if len(_created_ids) < 2:
            r = sa.post(f"{BASE_URL}/api/platform/news/simulate-release", json={"release_id": RELEASE_ID}, timeout=60)
            assert r.status_code == 200
            lst = sa.get(f"{BASE_URL}/api/platform/news", timeout=15).json()
            new_drafts = [x for x in lst if x["status"] == "bozza" and x.get("simulated") and x["id"] not in _created_ids]
            new_drafts.sort(key=lambda x: x.get("created_at") or "", reverse=True)
            for d in new_drafts[: r.json()["created"]]:
                _created_ids.append(d["id"])

        nid = _created_ids[1]
        r = sa.post(f"{BASE_URL}/api/platform/news/{nid}/publish", timeout=15)
        assert r.status_code == 200
        time.sleep(1)
        rc = org.get(f"{BASE_URL}/api/news/unread-count", timeout=15)
        assert rc.status_code == 200
        assert rc.json()["count"] >= 1

    def test_withdrawn_not_visible_to_user(self, sa, org):
        nid = _created_ids[1]
        rw = sa.post(f"{BASE_URL}/api/platform/news/{nid}/withdraw", timeout=15)
        assert rw.status_code == 200
        time.sleep(1)
        items = org.get(f"{BASE_URL}/api/news", timeout=15).json()
        assert not any(x["id"] == nid for x in items), "withdrawn item still visible to user"


# ---------------- Audit ----------------
class TestAudit:
    def test_audit_news_published(self, sa):
        r = sa.get(f"{BASE_URL}/api/platform/audit", params={"action": "news_published"}, timeout=15)
        assert r.status_code == 200
        data = r.json()
        # response may be list or dict with items
        rows = data if isinstance(data, list) else data.get("items", [])
        assert len(rows) >= 1
