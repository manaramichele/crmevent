"""Backend tests for iteration 17: Brevo Demo Funnel (draft-only in preview).

BREVO_API_KEY is intentionally EMPTY in preview → any Brevo-calling endpoint
must gracefully return a 400 (not 500).
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://manage-events-12.preview.emergentagent.com").rstrip("/")
SUPER_EMAIL = "manara.michele.pro@gmail.com"
SUPER_PWD = "CrmEvent2026!"

# Load cron secret + webhook token from backend/.env
_ENV = {}
with open("/app/backend/.env") as fh:
    for ln in fh:
        if "=" in ln and not ln.strip().startswith("#"):
            k, _, v = ln.strip().partition("=")
            _ENV[k] = v.strip().strip('"').strip("'")
CRON_SECRET = _ENV.get("WEBHOOK_CRON_SECRET", "")
WEBHOOK_TOKEN = _ENV.get("BREVO_WEBHOOK_TOKEN", "")


@pytest.fixture(scope="module")
def anon():
    return requests.Session()


@pytest.fixture(scope="module")
def sadmin():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": SUPER_EMAIL, "password": SUPER_PWD}, timeout=30)
    assert r.status_code == 200, f"Superadmin login failed: {r.status_code} {r.text}"
    return s


# --------- Auth guards ---------
def test_funnels_list_requires_auth(anon):
    r = anon.get(f"{BASE_URL}/api/platform/funnels", timeout=30)
    assert r.status_code == 401

def test_funnel_get_requires_auth(anon):
    r = anon.get(f"{BASE_URL}/api/platform/funnels/demo", timeout=30)
    assert r.status_code == 401

def test_funnels_list_authenticated(sadmin):
    r = sadmin.get(f"{BASE_URL}/api/platform/funnels", timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list) and len(data) >= 1
    f = next((x for x in data if x["key"] == "demo"), None)
    assert f, f"Expected 'demo' funnel: {data}"
    assert f["status"] == "draft"
    assert f["brevo_configured"] is False  # preview
    # never expose API key
    assert "BREVO_API_KEY" not in r.text
    assert "brevo_api_key" not in r.text.lower() or "api_key" not in r.text.lower()

def test_funnel_get_demo_structure(sadmin):
    r = sadmin.get(f"{BASE_URL}/api/platform/funnels/demo", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["key"] == "demo"
    assert d["status"] == "draft"
    assert isinstance(d.get("steps"), list) and len(d["steps"]) == 4
    # Timing check
    delays = [s.get("delay_days") for s in d["steps"]]
    assert delays == [0, 1, 3, 6], f"delays mismatch: {delays}"
    # Subjects present
    for s in d["steps"]:
        assert s.get("subject")
    assert d["brevo_configured"] is False


# --------- Draft-protection guard ---------
def test_activate_blocked_in_preview(sadmin):
    r = sadmin.post(f"{BASE_URL}/api/platform/funnels/demo/status",
                    json={"status": "active"}, timeout=30)
    assert r.status_code == 400
    # message about Brevo not configured
    assert "brevo" in r.text.lower() or "BREVO" in r.text
    assert "BREVO_API_KEY" not in r.text  # never leak

def test_status_paused_ok(sadmin):
    r = sadmin.post(f"{BASE_URL}/api/platform/funnels/demo/status",
                    json={"status": "paused"}, timeout=30)
    assert r.status_code == 200
    # revert to draft
    r2 = sadmin.post(f"{BASE_URL}/api/platform/funnels/demo/status",
                     json={"status": "draft"}, timeout=30)
    assert r2.status_code == 200

def test_status_invalid(sadmin):
    r = sadmin.post(f"{BASE_URL}/api/platform/funnels/demo/status",
                    json={"status": "bogus"}, timeout=30)
    assert r.status_code in (400, 422)


# --------- Sync templates / test funnel (Brevo-gated) ---------
def test_sync_templates_400_no_brevo(sadmin):
    r = sadmin.post(f"{BASE_URL}/api/platform/funnels/demo/sync-templates", timeout=30)
    assert r.status_code == 400
    assert "BREVO_API_KEY" in r.text or "non configurata" in r.text.lower()

def test_test_funnel_400_no_brevo(sadmin):
    r = sadmin.post(f"{BASE_URL}/api/platform/funnels/demo/test",
                    json={"email": "test@example.com"}, timeout=30)
    assert r.status_code == 400


# --------- Cron endpoint ---------
def test_cron_no_auth(anon):
    r = anon.post(f"{BASE_URL}/api/cron/brevo-funnel-tick", timeout=30)
    assert r.status_code == 401

def test_cron_wrong_bearer(anon):
    r = anon.post(f"{BASE_URL}/api/cron/brevo-funnel-tick",
                  headers={"Authorization": "Bearer wrong-token"}, timeout=30)
    assert r.status_code == 401

def test_cron_correct_bearer(anon):
    assert CRON_SECRET, "WEBHOOK_CRON_SECRET missing in .env"
    r = anon.post(f"{BASE_URL}/api/cron/brevo-funnel-tick",
                  headers={"Authorization": f"Bearer {CRON_SECRET}"}, timeout=30)
    assert r.status_code == 200
    assert r.json().get("accepted") is True


# --------- Brevo webhook ---------
def test_webhook_wrong_token(anon):
    r = anon.post(f"{BASE_URL}/api/brevo/webhook/wrong-token", json=[], timeout=30)
    assert r.status_code == 401

def test_webhook_correct_token_empty(anon):
    assert WEBHOOK_TOKEN
    r = anon.post(f"{BASE_URL}/api/brevo/webhook/{WEBHOOK_TOKEN}", json=[], timeout=30)
    assert r.status_code == 200
    assert "received" in r.json()


# --------- Unsubscribe (public HTML) ---------
def test_unsubscribe_invalid_token(anon):
    r = anon.get(f"{BASE_URL}/api/brevo/unsubscribe", params={"token": "invalid"}, timeout=30)
    assert r.status_code == 404
    assert "text/html" in r.headers.get("content-type", "").lower()
    assert "<html" in r.text.lower()


# --------- Full lead lifecycle in DRAFT ---------
_created_lead_email = f"test_iter17_{uuid.uuid4().hex[:8]}@example.com"
_created_lead_id = {"id": None}

def test_create_public_lead_no_enrollment(anon, sadmin):
    payload = {"nome": "Test", "cognome": "Iter17", "email": _created_lead_email,
               "telefono": "+390000000000", "source": "test-iter17", "privacy": True}
    r = anon.post(f"{BASE_URL}/api/leads", json=payload, timeout=30)
    assert r.status_code in (200, 201), f"{r.status_code} {r.text}"
    body = r.json()
    lead_id = body.get("id") or body.get("lead", {}).get("id")
    assert lead_id
    _created_lead_id["id"] = lead_id

    # Fetch as superadmin
    r2 = sadmin.get(f"{BASE_URL}/api/leads/{lead_id}", timeout=30)
    assert r2.status_code == 200
    d = r2.json()
    lead = d.get("lead", d)
    assert lead.get("funnel_status") == "demo_requested", lead
    assert d.get("funnel") is None, f"Expected funnel=null in DRAFT, got {d.get('funnel')}"


def test_unsubscribe_valid_token(anon, sadmin):
    """Fetch a valid unsub_token via DB-less route: create lead already done; get its token."""
    if not _created_lead_id["id"]:
        pytest.skip("prior test did not create a lead")
    r = sadmin.get(f"{BASE_URL}/api/leads/{_created_lead_id['id']}", timeout=30)
    d = r.json()
    lead = d.get("lead", d)
    token = lead.get("unsub_token")
    if not token:
        pytest.skip("lead has no unsub_token exposed")
    r2 = requests.get(f"{BASE_URL}/api/brevo/unsubscribe", params={"token": token}, timeout=30)
    assert r2.status_code == 200
    assert "disiscri" in r2.text.lower() or "unsubscri" in r2.text.lower()
    # verify persisted
    r3 = sadmin.get(f"{BASE_URL}/api/leads/{_created_lead_id['id']}", timeout=30)
    lead2 = r3.json().get("lead", r3.json())
    assert lead2.get("marketing_opt_out") is True


def test_cleanup_lead(sadmin):
    """Cleanup created lead if delete endpoint exists."""
    lid = _created_lead_id["id"]
    if not lid:
        return
    r = sadmin.delete(f"{BASE_URL}/api/leads/{lid}", timeout=30)
    # accept any (endpoint may not exist)
    assert r.status_code in (200, 204, 404, 405)


# --------- Non-superadmin authorization ---------
def test_leads_endpoint_rejects_anon(anon):
    r = anon.get(f"{BASE_URL}/api/leads/some-id", timeout=30)
    assert r.status_code in (401, 403, 404)  # must not be 200

def test_no_api_key_leak_anywhere(sadmin):
    for path in ["/api/platform/funnels", "/api/platform/funnels/demo"]:
        r = sadmin.get(f"{BASE_URL}{path}", timeout=30)
        assert "BREVO_API_KEY" not in r.text
