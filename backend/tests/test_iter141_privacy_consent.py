# Privacy & Cookie consent manager: public config, consent registry, Super Admin settings/stats/registry/publish
import os
import uuid
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
SA_EMAIL = "manara.michele.pro@gmail.com"
SA_PASS = "CrmEvent2026!"
TEST_EMAIL = f"test_privacy_{uuid.uuid4().hex[:6]}@example.com"


def _db():
    env = {}
    for line in open("/app/backend/.env"):
        if "=" in line:
            k, v = line.strip().split("=", 1)
            env[k] = v.strip('"')
    return MongoClient(env["MONGO_URL"])[env["DB_NAME"]]


@pytest.fixture(scope="module")
def sa():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": SA_EMAIL, "password": SA_PASS})
    if r.status_code != 200:
        pytest.skip(f"SA login failed {r.status_code}")
    return s


@pytest.fixture(scope="module")
def org_user():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/register-organization", json={
        "nome": "TEST_Priv", "cognome": "User", "email": TEST_EMAIL, "password": "TestPass123!",
        "org_name": "TEST_PrivacyOrg", "telefono": "+393331234567", "accept_terms": True})
    assert r.status_code == 200, r.text
    data = r.json()
    yield s, data
    db = _db()
    u = db.users.find_one({"email": TEST_EMAIL})
    if u:
        db.organizations.delete_many({"id": u.get("org_id")})
        db.memberships.delete_many({"user_id": u["user_id"]})
        db.consent_records.delete_many({"user_id": u["user_id"]})
        db.users.delete_one({"user_id": u["user_id"]})


def _consent(cid, a, m, action, versions, source="banner"):
    return {"consent_id": cid, "analytics": a, "marketing": m, "action": action, "source": source, "lang": "it", "versions": versions}


# Public config
class TestPublic:
    def test_config_public(self):
        r = requests.get(f"{BASE_URL}/api/privacy/config")
        assert r.status_code == 200
        d = r.json()
        assert set(d["versions"]) == {"privacy", "cookie", "banner"}
        ids = [s["id"] for s in d["services"]]
        for sid in ("ga4", "posthog", "brevo", "crmevent_core"):
            assert sid in ids
        assert d["reask_days"] == 180
        assert "it" in d["banner"] and "en" in d["banner"]
        assert "_id" not in d

    def test_consent_bad_id(self):
        v = requests.get(f"{BASE_URL}/api/privacy/config").json()["versions"]
        r = requests.post(f"{BASE_URL}/api/privacy/consents", json=_consent("not-a-uuid", True, True, "accept_all", v))
        assert r.status_code == 400
        assert r.json()["detail"] == "ID consenso non valido"

    def test_consent_dash_only_id_accepted(self):
        # regex ^[a-f0-9-]{36}$ accepts 36 dashes (weak validation) - informational
        v = requests.get(f"{BASE_URL}/api/privacy/config").json()["versions"]
        r = requests.post(f"{BASE_URL}/api/privacy/consents", json=_consent("-" * 36, False, False, "reject_all", v))
        print("dash-only id status:", r.status_code)
        _db().consent_records.delete_many({"consent_id": "-" * 36})

    def test_consent_invalid_action(self):
        r = requests.post(f"{BASE_URL}/api/privacy/consents", json=_consent(str(uuid.uuid4()), True, True, "bogus", {}))
        assert r.status_code == 422

    def test_consent_first_then_revoke(self):
        v = requests.get(f"{BASE_URL}/api/privacy/config").json()["versions"]
        cid = str(uuid.uuid4())
        r = requests.post(f"{BASE_URL}/api/privacy/consents", json=_consent(cid, True, True, "accept_all", v))
        assert r.status_code == 200 and r.json()["ok"] is True
        r = requests.post(f"{BASE_URL}/api/privacy/consents", json=_consent(cid, False, True, "custom", v, "footer"))
        assert r.status_code == 200
        recs = list(_db().consent_records.find({"consent_id": cid}, {"_id": 0}).sort("created_at", 1))
        assert [x["event"] for x in recs] == ["first", "revoke"]
        assert recs[1]["revoked"] == ["analytics"]
        assert recs[0]["user_id"] is None
        _db().consent_records.delete_many({"consent_id": cid})


# Consent with logged-in user stores user_id; org user cannot access SA endpoints
class TestOrgUser:
    def test_consent_stores_user_id(self, org_user):
        s, data = org_user
        v = requests.get(f"{BASE_URL}/api/privacy/config").json()["versions"]
        cid = str(uuid.uuid4())
        r = s.post(f"{BASE_URL}/api/privacy/consents", json=_consent(cid, True, False, "custom", v))
        assert r.status_code == 200
        rec = _db().consent_records.find_one({"consent_id": cid})
        assert rec["user_id"] == data["user_id"]

    @pytest.mark.parametrize("method,path", [("get", "settings"), ("get", "stats"), ("get", "consents"), ("post", "publish"), ("put", "settings")])
    def test_sa_endpoints_forbidden_for_org(self, org_user, method, path):
        s, _ = org_user
        r = getattr(s, method)(f"{BASE_URL}/api/platform/privacy/{path}", json={})
        assert r.status_code in (401, 403, 422), r.status_code
        print(method, path, r.status_code)

    @pytest.mark.parametrize("path", ["settings", "stats", "consents"])
    def test_sa_endpoints_anon(self, path):
        r = requests.get(f"{BASE_URL}/api/platform/privacy/{path}")
        assert r.status_code == 401


# Super Admin
class TestSuperAdmin:
    def test_get_settings(self, sa):
        r = sa.get(f"{BASE_URL}/api/platform/privacy/settings")
        assert r.status_code == 200
        d = r.json()
        assert d["locked_services"]["brevo"] == "marketing"
        assert d["retention_days"] == 730

    def test_stats(self, sa):
        r = sa.get(f"{BASE_URL}/api/platform/privacy/stats?days=30")
        assert r.status_code == 200
        d = r.json()
        for k in ("records", "actions", "revocations", "devices", "analytics_granted", "marketing_granted"):
            assert k in d

    def test_registry_and_audit(self, sa):
        r = sa.get(f"{BASE_URL}/api/platform/privacy/consents?limit=5")
        assert r.status_code == 200
        d = r.json()
        assert "items" in d and "total" in d
        for it in d["items"]:
            assert "_id" not in it and "created_at_dt" not in it
        a = _db().audit_logs.find_one({"action": "privacy_consents_viewed"}) or _db().audit_log.find_one({"action": "privacy_consents_viewed"})
        print("audit found:", bool(a))

    def _payload(self, sa):
        s = sa.get(f"{BASE_URL}/api/platform/privacy/settings").json()
        return {"banner": s["banner"], "categories": s["categories"], "services": s["services"]}

    def test_put_reject_brevo_removal(self, sa):
        p = self._payload(sa)
        p["services"] = [x for x in p["services"] if x["id"] != "brevo"]
        r = sa.put(f"{BASE_URL}/api/platform/privacy/settings", json=p)
        assert r.status_code == 400
        assert "brevo" in r.json()["detail"]

    def test_put_reject_ga4_necessary(self, sa):
        p = self._payload(sa)
        for x in p["services"]:
            if x["id"] == "ga4":
                x["category"] = "necessary"
        r = sa.put(f"{BASE_URL}/api/platform/privacy/settings", json=p)
        assert r.status_code == 400

    def test_put_short_banner_text_rejected(self, sa):
        p = self._payload(sa)
        p["banner"]["it"]["text"] = "short"
        r = sa.put(f"{BASE_URL}/api/platform/privacy/settings", json=p)
        print("short text status:", r.status_code, r.text[:200])
        assert r.status_code in (400, 422)

    def test_put_same_settings_ok(self, sa):
        p = self._payload(sa)
        r = sa.put(f"{BASE_URL}/api/platform/privacy/settings", json=p)
        assert r.status_code == 200
        assert r.json()["services"] == p["services"]

    def test_publish_increments(self, sa):
        before = requests.get(f"{BASE_URL}/api/privacy/config").json()["versions"]["cookie"]
        r = sa.post(f"{BASE_URL}/api/platform/privacy/publish", json={"doc": "cookie", "note": "TEST_ publish by testing agent"})
        assert r.status_code == 200
        e = r.json()
        assert e["previous"] == before
        after = requests.get(f"{BASE_URL}/api/privacy/config").json()["versions"]["cookie"]
        assert after == e["version"]
        print("publish", before, "->", after)
        if before.startswith("2026.10."):
            assert after == f"2026.10.{int(before.split('.')[-1]) + 1}"

    def test_publish_note_validation(self, sa):
        r = sa.post(f"{BASE_URL}/api/platform/privacy/publish", json={"doc": "cookie", "note": "x"})
        assert r.status_code == 422
