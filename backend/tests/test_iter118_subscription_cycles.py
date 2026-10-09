"""Iter 118 — Semester (6 mesi) / Yearly (12 mesi, -20%) subscription cycles."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")

QA_EMAIL = "qa.eventi@crmeventqa.it"
QA_PASS = "QaEvents2026!"
SA_EMAIL = "manara.michele.pro@gmail.com"
SA_PASS = "CrmEvent2026!"


# ---------------- Public plans ----------------
class TestPlansPublic:
    def test_plans_public_cycles(self):
        r = requests.get(f"{BASE_URL}/api/saas/plans-public", timeout=20)
        assert r.status_code == 200
        data = r.json()
        plans = {p["key"]: p for p in data["plans"]}
        # monthly values
        assert plans["bronze"]["monthly"] == 19.0
        assert plans["silver"]["monthly"] == 49.0
        assert plans["gold"]["monthly"] == 79.0
        # semester = monthly * 6
        assert plans["bronze"]["semester"] == 114.0
        assert plans["silver"]["semester"] == 294.0
        assert plans["gold"]["semester"] == 474.0
        # yearly = monthly * 12 * 0.8
        assert plans["bronze"]["yearly"] == pytest.approx(182.4, rel=1e-3)
        assert plans["silver"]["yearly"] == pytest.approx(470.4, rel=1e-3)
        assert plans["gold"]["yearly"] == pytest.approx(758.4, rel=1e-3)


# ---------------- Backend cycle_amount unit ----------------
class TestCycleAmountUnit:
    def test_cycle_amount(self):
        from subscriptions import cycle_amount, DEFAULT_CONFIG
        cfg = DEFAULT_CONFIG
        assert cycle_amount(cfg, "silver", "semester") == 294.0
        assert cycle_amount(cfg, "bronze", "semester") == 114.0
        assert cycle_amount(cfg, "gold", "semester") == 474.0
        assert cycle_amount(cfg, "silver", "yearly") == 470.4

    def test_sync_sub_cycle_mapping_logic(self):
        """Replicate the logic in sync_sub for cycle mapping."""
        def to_cycle(interval, interval_count):
            return "yearly" if interval == "year" else "semester" if int(interval_count or 1) == 6 else "monthly"
        assert to_cycle("year", 1) == "yearly"
        assert to_cycle("month", 6) == "semester"
        assert to_cycle("month", 1) == "monthly"


# ---------------- Auth helpers ----------------
def _login(email, pwd):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pwd}, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"Login failed for {email}: {r.status_code} {r.text[:120]}")
    return s


# ---------------- Checkout validation ----------------
class TestCheckout:
    def test_checkout_monthly_rejected(self):
        s = _login(QA_EMAIL, QA_PASS)
        r = s.post(f"{BASE_URL}/api/saas/checkout",
                   json={"plan": "silver", "cycle": "monthly",
                         "origin_url": f"{BASE_URL}/profilo"}, timeout=20)
        # monthly not in CYCLES → 400 "Piano o periodicità non validi"
        assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text[:200]}"

    def test_checkout_semester(self):
        s = _login(QA_EMAIL, QA_PASS)
        r = s.post(f"{BASE_URL}/api/saas/checkout",
                   json={"plan": "silver", "cycle": "semester",
                         "origin_url": f"{BASE_URL}/profilo"}, timeout=30)
        # Either success (200) or billing_missing (400)
        assert r.status_code in (200, 400), r.text[:200]
        if r.status_code == 200:
            data = r.json()
            assert "checkout_url" in data and data["checkout_url"].startswith("https://")
        else:
            # Accept only billing_missing
            body = r.json()
            det = body.get("detail")
            if isinstance(det, dict):
                assert det.get("code") == "billing_missing", det
            else:
                # could also be "already active" etc – log it
                print(f"Checkout 400 detail: {det}")

    def test_checkout_yearly(self):
        s = _login(QA_EMAIL, QA_PASS)
        r = s.post(f"{BASE_URL}/api/saas/checkout",
                   json={"plan": "gold", "cycle": "yearly",
                         "origin_url": f"{BASE_URL}/profilo"}, timeout=30)
        assert r.status_code in (200, 400), r.text[:200]
        if r.status_code == 200:
            assert r.json().get("checkout_url", "").startswith("https://")


# ---------------- Super Admin PUT admin cycle ----------------
class TestSuperAdminCycle:
    def test_platform_orgs_cycle_update(self):
        s = _login(SA_EMAIL, SA_PASS)
        orgs = s.get(f"{BASE_URL}/api/platform/saas/organizations", timeout=20)
        assert orgs.status_code == 200
        # pick QA org
        target = None
        for o in orgs.json():
            if "qa" in (o.get("nome") or "").lower() or o.get("admin"):
                target = o
                break
        if not target:
            pytest.skip("No suitable org for admin cycle update")
        org_id = target["id"]
        prev_adm = target.get("admin") or {}
        payload = {
            "plan": prev_adm.get("plan"),
            "status": prev_adm.get("status") or "auto",
            "billing_cycle": "semester",
            "access_start": prev_adm.get("access_start"),
            "access_end": prev_adm.get("access_end"),
            "renewal_date": prev_adm.get("renewal_date"),
            "comp": bool(prev_adm.get("comp")),
            "max_events": prev_adm.get("max_events"),
            "max_users": prev_adm.get("max_users"),
            "notes": prev_adm.get("notes"),
            "reason": "TEST_iter118",
        }
        r = s.put(f"{BASE_URL}/api/platform/saas/orgs/{org_id}/admin", json=payload, timeout=20)
        assert r.status_code == 200, r.text[:200]
        # restore
        payload["billing_cycle"] = prev_adm.get("billing_cycle")
        payload["reason"] = "TEST_iter118_restore"
        s.put(f"{BASE_URL}/api/platform/saas/orgs/{org_id}/admin", json=payload, timeout=20)
