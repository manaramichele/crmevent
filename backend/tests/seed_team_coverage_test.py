"""Seed TEST_ org for team volunteer coverage. Run with --clean to remove."""
import os, sys, asyncio, bcrypt
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
ORG, UID, EV = "org_TEST_team", "user_TEST_team", "ev_TEST_team"
NOW = datetime.now(timezone.utc).isoformat()


async def clean():
    for c in await db.list_collection_names():
        await db[c].delete_many({"$or": [{"org_id": ORG}, {"user_id": UID}, {"id": ORG}]})


async def seed():
    await clean()
    qa = await db.organizations.find_one({"id": "org_qa_eventi"}, {"_id": 0})
    await db.organizations.insert_one({**qa, "id": ORG, "nome": "TEST_Team Org", "owner_user_id": UID, "created_at": NOW,
                                       "subscription": {**qa["subscription"], "stripe_customer_id": None}})
    await db.users.insert_one({"user_id": UID, "email": "test_team@crmeventqa.it", "name": "TEST_Team", "role": "admin",
                               "auth_provider": "password", "password_hash": bcrypt.hashpw(b"TestTeam2026!", bcrypt.gensalt()).decode(),
                               "org_id": ORG, "active": True, "telefono": "+393331234567", "accepted_terms_at": NOW,
                               "created_at": NOW, "registered_at": NOW, "onboarding": {"seen": True}})
    await db.memberships.insert_one({"id": "mem_TEST_team", "user_id": UID, "org_id": ORG, "role": "admin_org", "active": True,
                                     "permissions": {}, "created_at": NOW})
    for eid, nome in [(EV, "TEST_Gara Team"), (EV + "_2", "TEST_Altro Evento")]:
        await db.events.insert_one({"id": eid, "org_id": ORG, "nome": nome, "data_inizio": "2026-12-19", "data_fine": "2026-12-20",
                                    "stato": "pianificazione", "credit_state": "attivo", "created_at": NOW})
    teams = [("tm_TEST_ristori", "Ristori", 20, 14), ("tm_TEST_percorso", "Percorso", 5, 5), ("tm_TEST_expo", "Expo", 3, 5), ("tm_TEST_nofab", "Senza fabbisogno", None, 1)]
    i = 0
    for tid, nome, req, n in teams:
        await db.teams.insert_one({"id": tid, "org_id": ORG, "evento_id": EV, "nome": nome, "volontari_richiesti": req, "created_at": NOW})
        for _ in range(n):
            pid = f"pe_TEST_t{i}"
            await db.persons.insert_one({"id": pid, "org_id": ORG, "nome": f"Vol{i}", "cognome": "TEST", "created_at": NOW})
            await db.staff.insert_one({"id": f"sl_TEST_t{i}", "org_id": ORG, "evento_id": EV, "persona_id": pid, "categoria": "volontario",
                                       "team_id": tid, "stato": "confermato", "created_at": NOW})
            i += 1
    # Non contano: staff (non volontario) e volontario con rinuncia nel team Ristori
    for k, cat, st in [("s", "staff", "confermato"), ("r", "volontario", "rinunciato")]:
        await db.persons.insert_one({"id": f"pe_TEST_x{k}", "org_id": ORG, "nome": f"Extra{k}", "cognome": "TEST", "created_at": NOW})
        await db.staff.insert_one({"id": f"sl_TEST_x{k}", "org_id": ORG, "evento_id": EV, "persona_id": f"pe_TEST_x{k}", "categoria": cat,
                                   "team_id": "tm_TEST_ristori", "stato": st, "created_at": NOW})
    # Volontario libero (senza team) per test assegnazione
    await db.persons.insert_one({"id": "pe_TEST_free", "org_id": ORG, "nome": "Libero", "cognome": "TEST", "created_at": NOW})
    await db.staff.insert_one({"id": "sl_TEST_free", "org_id": ORG, "evento_id": EV, "persona_id": "pe_TEST_free", "categoria": "volontario",
                               "team_id": "", "stato": "confermato", "created_at": NOW})
    print("seeded")


asyncio.run(clean() if "--clean" in sys.argv else seed())
