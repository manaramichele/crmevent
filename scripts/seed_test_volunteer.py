"""Idempotent: create a test volunteer account linked to a demo event for role-based testing."""
import asyncio
import os
import uuid
from datetime import datetime, timezone

import bcrypt
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

EMAIL = "volontario.test@crmevent.it"
PASSWORD = "VolTest2026!"


def now_iso():
    return datetime.now(timezone.utc).isoformat()


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    existing = await db.users.find_one({"email": EMAIL})
    event = await db.events.find_one({}, {"_id": 0})
    if not event:
        print("Nessun evento demo presente: impossibile collegare la presenza.")
    person = await db.persons.find_one({"email": EMAIL})
    if not person:
        pid = uuid.uuid4().hex
        person = {"id": pid, "nome": "Valentina", "cognome": "Volontari", "email": EMAIL,
                  "cellulare": "+39 340 0000000", "invite_status": "account_attivato", "user_role": "volunteer",
                  "created_at": now_iso(), "updated_at": now_iso()}
        await db.persons.insert_one(dict(person))
        print("Persona creata:", pid)
    pid = person["id"]

    if event:
        pres = await db.staff.find_one({"persona_id": pid, "evento_id": event["id"]})
        if not pres:
            await db.staff.insert_one({"id": uuid.uuid4().hex, "org_id": "default", "persona_id": pid,
                                       "evento_id": event["id"], "categoria": "volontario", "ruolo": "Accoglienza",
                                       "area": "Ingresso", "stato": "confermato", "data_arrivo": event.get("data_inizio"),
                                       "created_at": now_iso(), "updated_at": now_iso()})
            print("Presenza volontario creata sull'evento", event["nome"])

    pw_hash = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode()
    if existing:
        await db.users.update_one({"email": EMAIL}, {"$set": {"password_hash": pw_hash, "role": "volunteer",
                                                              "person_id": pid, "active": True}})
        print("Utente volontario aggiornato:", EMAIL)
    else:
        await db.users.insert_one({"user_id": uuid.uuid4().hex, "email": EMAIL, "name": "Valentina Volontari",
                                   "password_hash": pw_hash, "role": "volunteer", "auth_provider": "password",
                                   "person_id": pid, "active": True, "created_at": now_iso()})
        print("Utente volontario creato:", EMAIL, "/", PASSWORD)

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
