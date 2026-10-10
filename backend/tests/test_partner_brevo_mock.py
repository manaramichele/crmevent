"""Test simulato sincronizzazione Brevo partner (nessuna chiamata reale)."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("JWT_SECRET", "x")
import brevo_funnel  # noqa: E402
import partner_portal  # noqa: E402

calls = []


class FakeColl:
    def __init__(self, doc):
        self.doc = doc

    async def find_one(self, q, proj=None):
        return dict(self.doc)

    async def update_one(self, q, upd):
        self.doc.update(upd["$set"])


class FakeDB:
    def __init__(self, doc):
        self.partners = FakeColl(doc)


async def fake_request(method, path, json=None, params=None):
    calls.append((method, path, json))
    if path == "/v3/contacts/attributes":
        return 200, {"attributes": [{"name": "NOME"}, {"name": "COGNOME"}, {"name": "SMS"}]}, None
    if path.startswith("/v3/contacts/attributes/normal/"):
        return 201, None, None
    if path == "/v3/contacts" and "SMS" in json["attributes"] and SMS_DUP:
        return 400, {"message": "SMS is already associated with another Contact"}, "SMS is already associated with another Contact"
    return 204, None, None


SMS_DUP = False


def run(doc):
    calls.clear()
    brevo_funnel._request = fake_request
    brevo_funnel.is_configured = lambda: True
    deps = {"person_name": str, "hash_password": str, "verify_password": lambda a, b: True, "require_superadmin": lambda: None,
            "record_audit": None, "saas_config": None}
    sync = partner_portal.build(FakeDB(doc), deps)
    res = asyncio.run(_sync(sync, doc))
    return res


async def _sync(b, doc):
    # brevo_sync non è esportato: lo raggiungiamo tramite il router (closure) cercando l'endpoint sa_brevo_sync_one
    for r in b["router"].routes:
        if r.path == "/api/platform/partners/{pid}/brevo-sync":
            return await r.endpoint(pid=doc["id"], admin={})


def test_sync_pending():
    doc = {"id": "p1", "email": "a@b.it", "nome": "Mario", "cognome": "Rossi", "telefono": "+393331234567", "tipologia": "azienda",
           "ragione_sociale": "ACME Srl", "status": "pending", "code": None, "created_at": "2026-10-10T06:00:00+00:00"}
    res = run(doc)
    assert res["ok"], res
    created = [c[1].rsplit("/", 1)[1] for c in calls if c[1].startswith("/v3/contacts/attributes/normal/")]
    assert set(created) == set(partner_portal.BREVO_ATTRS), created
    up = [c for c in calls if c[1] == "/v3/contacts"][0][2]
    assert up["listIds"] == [18] and up["updateEnabled"] is True and up["email"] == "a@b.it"
    a = up["attributes"]
    assert a["PARTNER_STATO"] == "In attesa" and a["PARTNER_TIPOLOGIA"] == "Azienda" and a["SMS"] == "+393331234567"
    assert a["PARTNER_DATA_REGISTRAZIONE"] == "2026-10-10" and "PARTNER_CODICE" not in a
    assert "emailBlacklisted" not in up
    assert doc["brevo_sync"]["status"] == "ok"


def test_sync_approved_sms_dup():
    global SMS_DUP
    SMS_DUP = True
    doc = {"id": "p2", "email": "c@d.it", "nome": "Anna", "cognome": "Bianchi", "telefono": "+393339999999", "tipologia": "influencer",
           "status": "approved", "code": "ABCD2345", "created_at": "2026-10-10T06:00:00+00:00"}
    res = run(doc)
    SMS_DUP = False
    assert res["ok"], res
    ups = [c[2] for c in calls if c[1] == "/v3/contacts"]
    assert len(ups) == 2 and "SMS" not in ups[1]["attributes"] and ups[1]["attributes"]["PARTNER_CELLULARE"] == "+393339999999"
    assert ups[1]["attributes"]["PARTNER_CODICE"] == "ABCD2345" and ups[1]["attributes"]["PARTNER_STATO"] == "Approvato"


def test_phone():
    assert partner_portal.intl_phone("333 123 4567") == "+393331234567"
    assert partner_portal.intl_phone("0041 79 123 45 67") == "+41791234567"
    assert partner_portal.intl_phone("abc") is None
