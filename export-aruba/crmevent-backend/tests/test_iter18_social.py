"""Iteration 18: Marketing · Social (Phase A+B) — end-to-end backend tests.
Covers: settings, dashboard, AI generation, post lifecycle, plan, calendar,
media library, accounts scaffold, logs, and multi-tenant isolation.
"""
import io
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://manage-events-12.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


def _register(session, tag):
    ts = int(time.time() * 1000)
    email = f"soc_{tag}_{ts}_{uuid.uuid4().hex[:6]}@example.com"
    pwd = "Password123"
    r = session.post(f"{API}/auth/register-organization", json={
        "nome": "Test", "cognome": tag.title(), "email": email, "password": pwd,
        "org_name": f"Org Social {tag} {ts}", "telefono": "+390000000000",
        "accept_terms": True,
    }, timeout=30)
    assert r.status_code in (200, 201), f"register failed {r.status_code}: {r.text}"
    return email, pwd


def _login(session, email, pwd):
    r = session.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=30)
    assert r.status_code == 200, r.text
    return r


@pytest.fixture(scope="module")
def org_a():
    s = requests.Session()
    email, pwd = _register(s, "a")
    _login(s, email, pwd)
    return s


@pytest.fixture(scope="module")
def org_b():
    s = requests.Session()
    email, pwd = _register(s, "b")
    _login(s, email, pwd)
    return s


# ---------------- Settings ----------------
class TestSettings:
    def test_get_defaults(self, org_a):
        r = org_a.get(f"{API}/social/settings")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["autopilot"] == "OFF"
        assert "brand_name" in d

    def test_put_settings(self, org_a):
        payload = {
            "brand_name": "TEST_Brand A",
            "target": "runners 25-45",
            "tone_of_voice": "energico",
            "default_cta": "Iscriviti ora",
            "main_hashtags": ["#run", "#event"],
            "preferred_days": ["mon", "wed", "fri"],
            "preferred_times": ["09:00", "18:00"],
        }
        r = org_a.put(f"{API}/social/settings", json=payload)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["brand_name"] == "TEST_Brand A"
        assert d["autopilot"] == "OFF"
        assert d["main_hashtags"] == ["#run", "#event"]
        # persistence
        r2 = org_a.get(f"{API}/social/settings")
        assert r2.json()["brand_name"] == "TEST_Brand A"


# ---------------- Dashboard & Meta ----------------
class TestDashboard:
    def test_dashboard(self, org_a):
        r = org_a.get(f"{API}/social/dashboard")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["autopilot"] == "OFF"
        assert "counts" in d and isinstance(d["counts"], dict)
        for s in ("draft", "pending_approval", "approved", "scheduled", "published", "error"):
            assert s in d["counts"]
        assert "upcoming" in d and "total" in d

    def test_meta(self, org_a):
        r = org_a.get(f"{API}/social/meta")
        assert r.status_code == 200
        d = r.json()
        assert "statuses" in d and "categories" in d and "formats" in d


# ---------------- AI Generation + Lifecycle ----------------
class TestPostLifecycle:
    def test_generate_and_lifecycle(self, org_a):
        # Generate via AI (live LLM)
        r = org_a.post(f"{API}/social/generate", json={
            "topic": "TEST_AI post lancio evento", "category": "Anteprima evento",
        }, timeout=180)
        assert r.status_code == 200, r.text
        post = r.json()
        assert post["source"] == "ai"
        assert post["status"] == "draft"
        assert post.get("body") or post.get("caption"), "AI content must not be empty"
        pid = post["id"]

        # Edit
        r = org_a.put(f"{API}/social/posts/{pid}", json={"title": "TEST_edited title"})
        assert r.status_code == 200
        assert r.json()["title"] == "TEST_edited title"

        # Approve (org_admin)
        r = org_a.post(f"{API}/social/posts/{pid}/approve")
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "approved"

        # Schedule
        r = org_a.post(f"{API}/social/posts/{pid}/schedule", json={"scheduled_at": "2030-01-15T10:00:00+00:00"})
        assert r.status_code == 200
        j = r.json()
        assert j["status"] == "scheduled"
        assert j["scheduled_at"].startswith("2030-01-15")

        # Regenerate (goes back to draft)
        r = org_a.post(f"{API}/social/posts/{pid}/regenerate", json={"topic": "TEST_regen"}, timeout=180)
        assert r.status_code == 200
        assert r.json()["status"] == "draft"

        # Delete
        r = org_a.delete(f"{API}/social/posts/{pid}")
        assert r.status_code == 200
        r = org_a.get(f"{API}/social/posts/{pid}")
        assert r.status_code == 404


# ---------------- Editorial Plan ----------------
class TestPlan:
    def test_plan_generation(self, org_a):
        r = org_a.post(f"{API}/social/plan/generate", json={
            "date_from": "2030-02-01", "date_to": "2030-02-21",
            "posts_per_week": 3, "goal": "TEST_awareness",
        }, timeout=240)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["count"] >= 3
        assert len(d["posts"]) == d["count"]
        dates = [p.get("scheduled_at") for p in d["posts"] if p.get("scheduled_at")]
        assert len(dates) >= 3
        # spread: at least 2 distinct days
        distinct_days = {x[:10] for x in dates}
        assert len(distinct_days) >= 2
        # Calendar returns posts
        rc = org_a.get(f"{API}/social/calendar")
        assert rc.status_code == 200
        cd = rc.json()
        assert isinstance(cd.get("posts"), list) and isinstance(cd.get("plans"), list)
        assert any(p.get("plan_id") == d["plan_id"] for p in cd["posts"])


# ---------------- Media Library ----------------
class TestMedia:
    def test_media_crud(self, org_a):
        # tiny fake png
        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\x00\x01"
            b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        files = {"file": ("test.png", io.BytesIO(png), "image/png")}
        data = {"name": "TEST_media", "category": "photo", "tags": "hero,launch"}
        r = org_a.post(f"{API}/social/media", files=files, data=data)
        assert r.status_code == 200, r.text
        m = r.json()
        assert m["url"].startswith("/api/files/")
        assert "hero" in m["tags"]
        mid = m["id"]

        # list
        r = org_a.get(f"{API}/social/media")
        assert r.status_code == 200
        assert any(x["id"] == mid for x in r.json())

        # update
        r = org_a.put(f"{API}/social/media/{mid}", json={"name": "TEST_media2", "tags": ["a"]})
        assert r.status_code == 200
        assert r.json()["name"] == "TEST_media2"

        # delete
        r = org_a.delete(f"{API}/social/media/{mid}")
        assert r.status_code == 200


# ---------------- Accounts scaffold ----------------
class TestAccounts:
    def test_upsert_and_delete(self, org_a):
        r = org_a.post(f"{API}/social/accounts", json={"platform": "instagram", "handle": "@test_brand"})
        assert r.status_code == 200, r.text
        a = r.json()
        assert a["status"] == "pending_connection"
        assert a["connected"] is False
        aid = a["id"]

        r = org_a.get(f"{API}/social/accounts")
        assert r.status_code == 200
        assert any(x["id"] == aid for x in r.json())

        r = org_a.delete(f"{API}/social/accounts/{aid}")
        assert r.status_code == 200


# ---------------- Logs ----------------
class TestLogs:
    def test_logs_present(self, org_a):
        r = org_a.get(f"{API}/social/logs")
        assert r.status_code == 200
        logs = r.json()
        actions = {l.get("action") for l in logs}
        # at minimum settings_updated and generated should exist by now
        assert "settings_updated" in actions or "generated" in actions


# ---------------- Multi-tenant isolation ----------------
class TestIsolation:
    def test_orgs_do_not_see_each_other(self, org_a, org_b):
        # A creates a manual post + settings brand tag; B must not see it
        r = org_a.post(f"{API}/social/posts", json={"title": "TEST_ISO_A", "body": "A body"})
        assert r.status_code == 200
        pid_a = r.json()["id"]

        r = org_b.post(f"{API}/social/posts", json={"title": "TEST_ISO_B", "body": "B body"})
        assert r.status_code == 200
        pid_b = r.json()["id"]

        # B list must not contain A's post
        r = org_b.get(f"{API}/social/posts")
        assert r.status_code == 200
        ids_b = {p["id"] for p in r.json()}
        assert pid_a not in ids_b
        assert pid_b in ids_b

        # B cannot fetch A's post directly
        r = org_b.get(f"{API}/social/posts/{pid_a}")
        assert r.status_code == 404
        # B cannot approve/schedule/delete A's post
        assert org_b.post(f"{API}/social/posts/{pid_a}/approve").status_code == 404
        assert org_b.post(f"{API}/social/posts/{pid_a}/schedule", json={"scheduled_at": "2030-05-01T10:00:00+00:00"}).status_code == 404
        assert org_b.delete(f"{API}/social/posts/{pid_a}").status_code == 200  # delete_one silently: returns ok
        # verify A still sees its post
        r = org_a.get(f"{API}/social/posts/{pid_a}")
        assert r.status_code == 200, "Isolation broken: org B was able to delete org A's post"

    def test_settings_isolation(self, org_a, org_b):
        # A already has "TEST_Brand A"; B should get its own defaults
        rb = org_b.get(f"{API}/social/settings")
        assert rb.status_code == 200
        db_data = rb.json()
        assert db_data.get("brand_name") != "TEST_Brand A"
