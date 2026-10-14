"""Mock Brevo + LLM: lista per org, sync contatti, rimozione solo dalla lista, opposizione, invio idempotente, automazione post-evento
senza duplicati, sospensione se non approvato, statistiche. Nessuna chiamata reale."""
import asyncio
import os
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
import brevo_funnel  # noqa: E402
import press  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

calls = []


async def fake(method, path, *, json=None, params=None):
    calls.append((method, path, json))
    if path == "/v3/contacts/folders" and method == "GET":
        return 200, {"folders": []}, None
    if path == "/v3/contacts/folders":
        return 201, {"id": 7}, None
    if path.endswith("/lists") and method == "GET":
        return 200, {"lists": []}, None
    if path == "/v3/contacts/lists":
        return 201, {"id": 99}, None
    if path == "/v3/smtp/email":
        return 201, {"messageId": "m1"}, None
    if "aggregatedReport" in path:
        return 200, {"requests": 2, "delivered": 2, "uniqueOpens": 1}, None
    return 204, None, None


async def main():
    brevo_funnel._request = fake
    brevo_funnel.is_configured = lambda: True
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    O = "TEST_press_org"

    async def dep():
        return {}

    async def audit(*a, **k):
        pass

    P = press.build_router(db, dep, dep, audit, "https://example.com", "x")
    await P["ensure_indexes"]()
    ep = {(list(x.methods)[0], x.path): x.endpoint for x in P["router"].routes}
    u = {"org_id": O, "user_id": "TEST_u", "name": "Tester", "org_role": "admin_org", "email": "t@example.com"}
    try:
        await db.organizations.insert_one({"id": O, "nome": "TEST Press Org"})
        await db.events.insert_one({"id": "TEST_ev", "org_id": O, "nome": "TEST Gara", "data_inizio": "2020-01-01", "data_fine": "2020-01-02", "citta": "Roma"})
        await db.org_services.insert_one({"org_id": O, "service": "comunicati-stampa", "active": True})
        c1 = await ep[("POST", "/api/press/contacts")](body=press.ContactIn(email="A@Example.com", nome="A"), user=u)
        await ep[("POST", "/api/press/contacts")](body=press.ContactIn(email="b@example.com", base_giuridica="consenso"), user=u)
        try:
            await ep[("POST", "/api/press/contacts")](body=press.ContactIn(email="a@example.com"), user=u)
            raise AssertionError("duplicate allowed")
        except Exception as e:
            assert "già presente" in str(getattr(e, "detail", e))
        await asyncio.sleep(0.5)
        lst = await db.press_brevo_lists.find_one({"org_id": O})
        assert lst["list_id"] == 99 and lst["list_name"].startswith("CRMEvent_STAMPA_TEST_Press_Org_"), lst
        adds = [c for c in calls if c[1] == "/v3/contacts"]
        assert adds and adds[0][2]["listIds"] == [99] and "emailBlacklisted" not in adds[0][2]
        assert sum(1 for c in calls if c[1] == "/v3/contacts/lists") == 1  # lista creata una sola volta
        imp = await ep[("POST", "/api/press/contacts/import")](body=press.build_router.__globals__["BaseModel"].__subclasses__()[-1](csv_text="email;nome\nc@example.com;C\nb@example.com;B\nbad;X", base_giuridica="legittimo_interesse"), user=u) if False else None
        # disiscrizione per organizzazione: non riattivabile
        tok = (await db.press_contacts.find_one({"id": c1["id"]}))["unsub_token"]
        await ep[("GET", "/api/public/press/unsubscribe/{token}")](token=tok)
        await asyncio.sleep(0.3)
        assert (await db.press_contacts.find_one({"id": c1["id"]}))["stato"] == "opposto"
        assert any(c[1] == "/v3/contacts/lists/99/contacts/remove" for c in calls)
        await ep[("PUT", "/api/press/contacts/{cid}")](cid=c1["id"], body=press.ContactIn(email="a@example.com", stato="attivo"), user=u)
        assert (await db.press_contacts.find_one({"id": c1["id"]}))["stato"] == "opposto"
        # invio: solo idonei, idempotente
        await db.press_settings.insert_one({"org_id": O, "sender_name": "Org", "sender_email": "press@org.it", "sender_verified": True})
        await db.press_releases.insert_one({"id": "TEST_rel", "org_id": O, "event_id": "TEST_ev", "tipo": "presentazione", "titolo": "T", "testo": "Corpo",
                                            "status": "programmato", "send_at": "2000-01-01T00:00:00+00:00", "approved_at": "x", "filters": {}})
        await P["tick"]()
        await P["tick"]()
        sends = [c for c in calls if c[1] == "/v3/smtp/email"]
        assert len(sends) == 1 and sends[0][2]["to"][0]["email"] == "b@example.com" and sends[0][2]["sender"]["email"] == "press@org.it", sends
        assert "unsubscribe" in sends[0][2]["htmlContent"]
        rel = await db.press_releases.find_one({"id": "TEST_rel"})
        assert rel["status"] == "inviato" and rel["sent_count"] == 1
        rep = await ep[("GET", "/api/press/releases/{rid}/report")](rid="TEST_rel", user=u)
        assert rep["stats"]["delivered"] == 2
        # automazione post-evento: una sola bozza, da approvare, mai inviata senza approvazione
        await db.press_automations.insert_one({"org_id": O, "event_id": "TEST_ev", "enabled": True, "delay_days": 1, "send_time": "10:00"})

        async def fake_ai(*a, **k):
            return {"titolo": "Resoconto", "sottotitolo": "", "testo": "x", "dati_mancanti": ["Risultati"]}
        P["tick"].__globals__  # noqa
        press_ai = None  # AI reale non chiamata: _ai lancia senza chiave -> fallback testo vuoto
        os.environ.pop("EMERGENT_LLM_KEY", None)
        await P["tick"]()
        await P["tick"]()
        autos = await db.press_releases.find({"org_id": O, "automation": True}).to_list(5)
        assert len(autos) == 1 and autos[0]["status"] == "da_approvare", autos
        assert autos[0].get("approval_expired") is True  # orario passato senza approvazione: sospeso
        assert len([c for c in calls if c[1] == "/v3/smtp/email"]) == 1
        assert await db.press_notifications.count_documents({"org_id": O}) == 1
        print("OK press mock")
    finally:
        for col in ("press_contacts", "press_brevo_lists", "press_releases", "press_sends", "press_settings", "press_automations", "press_notifications", "press_versions", "org_services"):
            await db[col].delete_many({"org_id": O})
        await db.events.delete_one({"id": "TEST_ev"})
        await db.organizations.delete_one({"id": O})


asyncio.run(main())
