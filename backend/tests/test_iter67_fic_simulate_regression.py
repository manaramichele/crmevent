"""Iter67: Regressione endpoint Super Admin simulate - crea una TEST invoice, simula, verifica, pulisce."""
import os
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:3000"
# Legge .env del frontend
if "localhost" in BASE:
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL"):
                    BASE = line.split("=", 1)[1].strip()
    except Exception:
        pass
BASE = BASE.rstrip("/")

EMAIL = "manara.michele.pro@gmail.com"
PASSWORD = "CrmEvent2026!"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=20)
    if r.status_code != 200:
        pytest.skip(f"Login superadmin fallito: {r.status_code} {r.text[:200]}")
    tok = r.json().get("token") or r.json().get("access_token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


def test_create_simulate_and_delete_test_invoice(session):
    # 1. Crea una ricarica di test
    r = session.post(f"{BASE}/api/platform/credit-invoices/test",
                     json={"amount_net": 250, "credits_total": 550}, timeout=20)
    assert r.status_code == 200, f"Create TEST failed: {r.status_code} {r.text[:300]}"
    data = r.json()
    purchase_id = data["purchase_id"]
    invoice_id = data["invoice_id"]

    try:
        # 2. Simula
        s = session.post(f"{BASE}/api/platform/invoices/{invoice_id}/simulate", timeout=20)
        assert s.status_code == 200, f"Simulate failed: {s.status_code} {s.text[:300]}"
        sim = s.json()
        assert sim["simulated"] is True
        assert sim["imponibile"] == 250.0
        assert sim["importo_iva"] == 55.0
        assert sim["totale"] == 305.0
        assert sim["coerente"] is True

        # 3. fic_payload_preview deve contenere i nuovi campi
        preview = sim["fic_payload_preview"]["data"]
        assert preview["rivalsa"] == 0
        assert preview["cassa"] == 0
        assert preview["cassa2"] == 0
        assert preview["withholding_tax"] == 0
        assert preview["withholding_tax_taxable"] == 0
        assert preview["other_withholding_tax"] == 0
        assert preview["use_gross_prices"] is False
        assert preview["items_list"][0]["apply_withholding_taxes"] is False
        assert preview["items_list"][0]["net_price"] == 250.0
        assert preview["payments_list"][0]["amount"] == 305.0
    finally:
        # 4. Pulizia
        d = session.delete(f"{BASE}/api/platform/credit-invoices/test/{purchase_id}", timeout=20)
        assert d.status_code == 200, f"Delete TEST failed: {d.status_code} {d.text[:300]}"
