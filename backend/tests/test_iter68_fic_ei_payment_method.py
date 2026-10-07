"""Iter68: Verifica che il payload FIC includa ei_data.payment_method='MP08' (FatturaPA ModalitaPagamento
'carta di pagamento') sia nella simulazione sia nell'emissione reale, mantenendo rivalsa/cassa/ritenute
a zero e il resto del payload invariato. Nessuna chiamata reale a FIC: httpx.AsyncClient mockato."""
import os
import sys
import asyncio
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402


def _org():
    return {"id": "org_test", "nome": "Test Org", "ragione_sociale": "Test Org SRL",
            "partita_iva": "12345678901", "codice_fiscale": "12345678901",
            "indirizzo": "Via Test 1", "cap": "20100", "citta": "Milano",
            "provincia": "MI", "paese": "IT", "email": "t@t.it",
            "billing": {"ragione_sociale": "Test Org SRL", "partita_iva": "12345678901",
                        "codice_fiscale": "12345678901", "indirizzo": "Via Test 1",
                        "cap": "20100", "citta": "Milano", "provincia": "MI",
                        "paese": "IT", "sdi": "0000000"}}


def _inv():
    return {"id": "inv_test_68", "org_id": "org_test", "imponibile": 250,
            "importo_iva": 55, "iva": 55, "totale": 305, "aliquota_iva": 22,
            "kind": "credit_recharge", "credits_total": 550, "is_test": False}


# ---------------- 1. Costante configurabile ----------------
def test_fic_ei_payment_method_constant_default():
    assert hasattr(server, "FIC_EI_PAYMENT_METHOD")
    # Default MP08 (carta di pagamento) salvo override via env
    assert server.FIC_EI_PAYMENT_METHOD == (os.environ.get("FIC_EI_PAYMENT_METHOD") or "MP08").strip()


# ---------------- 2. _fic_build_payload (simulazione) ----------------
def test_build_payload_contains_ei_data_mp08_and_fields():
    a = server._derive_amounts(_inv())
    payload = server._fic_build_payload(_org(), a, server._invoice_line_name(_inv(), _org()))
    d = payload["data"]

    # ei_data obbligatorio e corretto
    assert d["ei_data"] == {"payment_method": "MP08"}
    # e_invoice True
    assert d["e_invoice"] is True
    # Fiscal fields a zero
    assert d["rivalsa"] == 0
    assert d["cassa"] == 0
    assert d["cassa2"] == 0
    assert d["withholding_tax"] == 0
    assert d["withholding_tax_taxable"] == 0
    assert d["other_withholding_tax"] == 0
    assert d["use_gross_prices"] is False
    # Items
    item = d["items_list"][0]
    assert item["net_price"] == 250
    assert item["apply_withholding_taxes"] is False
    # Payments
    pay = d["payments_list"][0]
    assert pay["amount"] == 305.0
    # payment_method name coerente con costante
    assert d["payment_method"]["name"] == server.FIC_PAYMENT_METHOD_NAME == "Carta di credito (Stripe)"


# ---------------- 3. _fic_issue_document (emissione reale) ----------------
class _MockResponse:
    def __init__(self, status=200, data=None):
        self.status_code = status
        self._data = data or {"data": {"id": 9999, "number": "1/2026",
                                       "date": "2026-01-15", "amount_net": 250,
                                       "amount_vat": 55, "amount_gross": 305,
                                       "url": "https://fic.test/pdf"}}
        self.content = b"{}"

    def json(self):
        return self._data


class _MockClient:
    captured = {}

    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None):
        _MockClient.captured["url"] = url
        _MockClient.captured["body"] = json
        _MockClient.captured["headers"] = headers
        return _MockResponse()


class _FakeInvColl:
    async def update_one(self, flt, upd):
        class R: modified_count = 1
        return R()


class _FakeOrgColl:
    def __init__(self, org):
        self._org = org

    async def find_one(self, flt, proj=None):
        return self._org


def _patch_common(monkeypatch, org):
    class FakeDB:
        invoices = _FakeInvColl()
        organizations = _FakeOrgColl(org)

    monkeypatch.setattr(server, "db", FakeDB)
    monkeypatch.setattr(server, "httpx", type("H", (), {"AsyncClient": _MockClient}))

    async def _tok():
        return "fake_token"

    async def _cid():
        return "123456"

    async def _vat(cid, token):
        return 42

    monkeypatch.setattr(server, "_fic_token", _tok)
    monkeypatch.setattr(server, "_fic_company_id", _cid)
    monkeypatch.setattr(server, "_fic_vat_id", _vat)


def test_issue_document_live_includes_ei_data_mp08(monkeypatch):
    _MockClient.captured = {}
    _patch_common(monkeypatch, _org())
    # Imposta payment_account_id numerico
    monkeypatch.setattr(server, "FIC_PAYMENT_ACCOUNT_ID", "123")

    asyncio.run(server._fic_issue_document(_inv(), dry_run=False))
    body = _MockClient.captured["body"]["data"]

    # ei_data presente e corretto
    assert body["ei_data"] == {"payment_method": "MP08"}
    assert body["e_invoice"] is True
    # Fiscal fields a zero (invariato)
    assert body["rivalsa"] == 0
    assert body["cassa"] == 0
    assert body["cassa2"] == 0
    assert body["withholding_tax"] == 0
    assert body["withholding_tax_taxable"] == 0
    assert body["other_withholding_tax"] == 0
    assert body["use_gross_prices"] is False
    assert body["items_list"][0]["apply_withholding_taxes"] is False
    # payments_list con amount 305 e payment_account
    pay = body["payments_list"][0]
    assert pay["amount"] == 305.0
    assert pay["status"] == "paid"
    assert pay["payment_account"] == {"id": 123}
    # payment_method name
    assert body["payment_method"]["name"] == "Carta di credito (Stripe)"


def test_issue_document_without_payment_account(monkeypatch):
    """Se FIC_PAYMENT_ACCOUNT_ID non è numerico, payment_account NON deve essere incluso."""
    _MockClient.captured = {}
    _patch_common(monkeypatch, _org())
    monkeypatch.setattr(server, "FIC_PAYMENT_ACCOUNT_ID", "")

    asyncio.run(server._fic_issue_document(_inv(), dry_run=False))
    body = _MockClient.captured["body"]["data"]

    assert body["ei_data"] == {"payment_method": "MP08"}
    assert "payment_account" not in body["payments_list"][0]


# ---------------- 4. ei_data identico tra reale e simulazione ----------------
def test_ei_data_identical_real_vs_sim(monkeypatch):
    _MockClient.captured = {}
    _patch_common(monkeypatch, _org())
    monkeypatch.setattr(server, "FIC_PAYMENT_ACCOUNT_ID", "123")

    # Reale
    asyncio.run(server._fic_issue_document(_inv(), dry_run=False))
    real_body = _MockClient.captured["body"]["data"]

    # Simulazione
    a = server._derive_amounts(_inv())
    sim_payload = server._fic_build_payload(_org(), a, server._invoice_line_name(_inv(), _org()))
    sim_body = sim_payload["data"]

    assert real_body["ei_data"] == sim_body["ei_data"] == {"payment_method": "MP08"}


# ---------------- 5. Env override ----------------
def test_ei_payment_method_env_override_shape():
    """Verifica che la costante sia costruita a partire da env; il valore attuale
    deve matchare la variabile d'ambiente se impostata o default MP08."""
    expected = (os.environ.get("FIC_EI_PAYMENT_METHOD") or "MP08").strip()
    assert server.FIC_EI_PAYMENT_METHOD == expected
