"""Iter67: Verifica che il payload FIC per ricariche crediti NON applichi rivalsa/cassa/ritenute
(così FIC non modifica il totale e il pagamento Stripe 305€ corrisponde al totale documento).
Nessuna chiamata reale a FIC: httpx.AsyncClient mockato."""
import os
import sys
import asyncio
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402


# ---- _derive_amounts ----
def test_derive_amounts_credit_recharge_305():
    inv = {"imponibile": 250, "importo_iva": 55, "iva": 55, "totale": 305,
           "aliquota_iva": 22, "kind": "credit_recharge", "credits_total": 550}
    a = server._derive_amounts(inv)
    assert a["imponibile"] == 250.0
    assert a["importo_iva"] == 55.0
    assert a["totale"] == 305.0
    assert a["aliquota_iva"] == 22.0
    assert a["coerente"] is True


# ---- _fic_build_payload (simulazione TEST) ----
def _org():
    return {"id": "org_test", "nome": "Test Org", "ragione_sociale": "Test Org SRL",
            "partita_iva": "12345678901", "codice_fiscale": "12345678901",
            "indirizzo": "Via Test 1", "cap": "20100", "citta": "Milano",
            "provincia": "MI", "paese": "IT", "email": "t@t.it",
            "billing": {"ragione_sociale": "Test Org SRL", "partita_iva": "12345678901",
                        "codice_fiscale": "12345678901", "indirizzo": "Via Test 1",
                        "cap": "20100", "citta": "Milano", "provincia": "MI",
                        "paese": "IT", "sdi": "0000000"}}


def test_fic_build_payload_no_withholding():
    inv = {"imponibile": 250, "importo_iva": 55, "iva": 55, "totale": 305,
           "aliquota_iva": 22, "kind": "credit_recharge", "credits_total": 550}
    a = server._derive_amounts(inv)
    payload = server._fic_build_payload(_org(), a, server._invoice_line_name(inv, _org()))
    d = payload["data"]
    # Campi fiscali a zero / use_gross_prices False
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
    assert item["qty"] == 1
    assert item["vat"]["value"] == 22.0
    assert item["apply_withholding_taxes"] is False
    # Payments
    pay = d["payments_list"][0]
    assert pay["amount"] == 305.0
    assert pay["status"] == "paid"
    # Nessun campo "undocumented" (checklist: solo le chiavi previste)
    allowed_top = {"type", "e_invoice", "entity", "items_list", "currency", "language",
                   "rivalsa", "cassa", "cassa2", "withholding_tax", "withholding_tax_taxable",
                   "other_withholding_tax", "use_gross_prices",
                   "payment_method", "payments_list"}
    assert set(d.keys()).issubset(allowed_top), f"Chiavi extra: {set(d.keys()) - allowed_top}"


# ---- _fic_issue_document con httpx MOCKATO ----
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
    def __init__(self):
        self.last_update = None

    async def update_one(self, flt, upd):
        self.last_update = (flt, upd)

        class R: modified_count = 1
        return R()


class _FakeOrgColl:
    def __init__(self, org):
        self._org = org

    async def find_one(self, flt, proj=None):
        return self._org


def test_fic_issue_document_mocked(monkeypatch):
    inv = {"id": "inv_test_1", "org_id": "org_test", "imponibile": 250,
           "importo_iva": 55, "iva": 55, "totale": 305, "aliquota_iva": 22,
           "kind": "credit_recharge", "credits_total": 550, "is_test": False}

    org = _org()
    fake_inv = _FakeInvColl()
    fake_org = _FakeOrgColl(org)

    class FakeDB:
        invoices = fake_inv
        organizations = fake_org

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

    res = asyncio.run(server._fic_issue_document(inv, dry_run=False))
    body = _MockClient.captured["body"]["data"]

    # Verifica campi fiscali IDENTICI a quelli della simulazione
    assert body["rivalsa"] == 0
    assert body["cassa"] == 0
    assert body["cassa2"] == 0
    assert body["withholding_tax"] == 0
    assert body["withholding_tax_taxable"] == 0
    assert body["other_withholding_tax"] == 0
    assert body["use_gross_prices"] is False
    # Items
    item = body["items_list"][0]
    assert item["apply_withholding_taxes"] is False
    assert item["net_price"] == 250
    # Payments (dry_run=False => payments_list presente)
    assert body["payments_list"][0]["amount"] == 305.0
    assert body["payments_list"][0]["status"] == "paid"

    # Il return deve includere amounts coerente
    assert res["amounts"]["totale"] == 305


def test_payload_fiscal_fields_identical_real_vs_sim():
    """Stesso set di chiavi/valori per rivalsa/cassa/ritenute tra reale e simulazione."""
    fiscal_keys = {"rivalsa", "cassa", "cassa2", "withholding_tax",
                   "withholding_tax_taxable", "other_withholding_tax", "use_gross_prices"}
    sim_doc = server.FIC_NO_WITHHOLDING_DOC
    assert set(sim_doc.keys()) == fiscal_keys
    assert all(sim_doc[k] in (0, False) for k in sim_doc)
    assert server.FIC_NO_WITHHOLDING_ITEM == {"apply_withholding_taxes": False}


def test_math_250_plus_22pct_equals_305():
    assert round(250 * 0.22, 2) == 55.00
    assert round(250 + 55, 2) == 305.00
