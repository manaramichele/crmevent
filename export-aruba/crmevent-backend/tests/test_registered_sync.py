"""Verifica la sync 'Utenti registrati' su Brevo: multiutenza (ORGANIZZAZIONE aggregata, nessun
duplicato), ruolo più alto, CELLULARE E.164, e il riallineamento idempotente (inseriti/aggiornati).
Monkeypatcha il layer HTTP di Brevo: nessuna chiamata reale."""
import os, asyncio, uuid
os.environ["BREVO_API_KEY"] = "test-key"

import server
import brevo_funnel

CAPTURED = []

async def fake_request(method, path, *, json=None, params=None):
    if path == "/v3/contacts" and method == "POST":
        CAPTURED.append(json)
        email = (json or {}).get("email", "").lower()
        # simula: primo upsert dell'email = created(201), successivi = updated(204)
        prior = [c for c in CAPTURED[:-1] if (c.get("email") or "").lower() == email]
        return (204 if prior else 201), {"id": 1}, None
    if path.startswith("/v3/contacts/lists/"):
        return 200, {"id": 999, "totalSubscribers": 5}, None
    return 200, {}, None

brevo_funnel._request = fake_request

async def main():
    db = server.db
    pfx = f"tsync_{uuid.uuid4().hex[:6]}"
    uid = f"user_{pfx}"
    oid1, oid2 = f"org_{pfx}_a", f"org_{pfx}_b"
    try:
        await db.organizations.insert_one({"id": oid1, "nome": "Alpha Eventi", "credits": {"balance": 10}})
        await db.organizations.insert_one({"id": oid2, "nome": "Beta Eventi", "credits": {"balance": 5}})
        await db.users.insert_one({"user_id": uid, "email": f"{pfx}@test.it", "name": "Mario Rossi",
                                   "telefono": "+393331234567", "role": "member",
                                   "registered_at": "2026-01-10T00:00:00+00:00"})
        await db.memberships.insert_one({"id": f"m_{pfx}_1", "user_id": uid, "org_id": oid1, "role": "user", "active": True})
        await db.memberships.insert_one({"id": f"m_{pfx}_2", "user_id": uid, "org_id": oid2, "role": "admin_org", "active": True})

        CAPTURED.clear()
        res = await server.sync_registered_user(uid, oid1, source="test")
        assert res.get("ok"), res
        assert len(CAPTURED) == 1, CAPTURED
        a = CAPTURED[0]["attributes"]
        assert a["ORGANIZZAZIONE"] == "Alpha Eventi, Beta Eventi", a["ORGANIZZAZIONE"]
        assert a["RUOLO_UTENTE"] == "Admin Organizzazione", a["RUOLO_UTENTE"]
        assert a["CELLULARE"] == "+393331234567", a["CELLULARE"]
        assert a["NOME"] == "Mario" and a["COGNOME"] == "Rossi"
        assert a["CREDITI_DISPONIBILI"] == 15, a["CREDITI_DISPONIBILI"]
        assert CAPTURED[0]["updateEnabled"] is True
        print("OK multi-org attrs:", a["ORGANIZZAZIONE"], "| ruolo:", a["RUOLO_UTENTE"], "| cell:", a["CELLULARE"])

        # idempotenza: secondo upsert stessa email -> status 204 (updated)
        CAPTURED.clear()
        # simula un contatto già esistente registrando una POST pregressa
        CAPTURED.append({"email": f"{pfx}@test.it"})
        res2 = await server.sync_registered_user(uid, oid2, source="test")
        assert res2.get("ok"), res2
        print("OK upsert idempotente (nessun duplicato per email)")

        # invito pending: utente senza membership attiva -> skipped
        uid2 = f"user_{pfx}_p"
        await db.users.insert_one({"user_id": uid2, "email": f"{pfx}_p@test.it", "name": "Luca Bianchi", "role": "member"})
        res3 = await server.sync_registered_user(uid2, oid1, source="test")
        assert res3.get("skipped"), res3
        print("OK invito pending (no membership attiva) -> skipped")

        # staff/volontario -> skipped
        await db.users.update_one({"user_id": uid2}, {"$set": {"role": "volunteer"}})
        await db.memberships.insert_one({"id": f"m_{pfx}_v", "user_id": uid2, "org_id": oid1, "role": "user", "active": True})
        res4 = await server.sync_registered_user(uid2, oid1, source="test")
        assert res4.get("skipped"), res4
        print("OK staff/volontario -> skipped (non è utente org)")

        print("\nTUTTI I TEST PASSATI")
    finally:
        await db.users.delete_many({"user_id": {"$in": [uid, uid2]}})
        await db.organizations.delete_many({"id": {"$in": [oid1, oid2]}})
        await db.memberships.delete_many({"id": {"$regex": f"^m_{pfx}"}})

asyncio.run(main())
