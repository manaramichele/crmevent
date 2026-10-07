"""Seed TEST_ org for briefing Pasti/Ospitalità scenario. Run with --clean to remove."""
import os, sys, asyncio, bcrypt
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
ORG, UID, EV = "org_TEST_brf", "user_TEST_brf", "ev_TEST_brf"
NOW = datetime.now(timezone.utc).isoformat()


async def clean():
    for c in await db.list_collection_names():
        await db[c].delete_many({"$or": [{"org_id": ORG}, {"user_id": UID}, {"id": ORG}]})


async def seed():
    await clean()
    qa = await db.organizations.find_one({"id": "org_qa_eventi"}, {"_id": 0})
    await db.organizations.insert_one({**qa, "id": ORG, "nome": "TEST_Briefing Org", "owner_user_id": UID, "created_at": NOW,
                                       "subscription": {**qa["subscription"], "stripe_customer_id": None}})
    await db.users.insert_one({"user_id": UID, "email": "test_brf@crmeventqa.it", "name": "TEST_Brf", "role": "admin",
                               "auth_provider": "password", "password_hash": bcrypt.hashpw(b"TestBrf2026!", bcrypt.gensalt()).decode(),
                               "org_id": ORG, "active": True, "telefono": "+393331234567", "accepted_terms_at": NOW,
                               "created_at": NOW, "registered_at": NOW, "onboarding": {"seen": True}})
    await db.memberships.insert_one({"id": "mem_TEST_brf", "user_id": UID, "org_id": ORG, "role": "admin_org", "active": True,
                                     "permissions": {}, "created_at": NOW})
    await db.events.insert_one({"id": EV, "org_id": ORG, "nome": "TEST_Gara Dicembre", "data_inizio": "2026-12-19",
                                "data_fine": "2026-12-20", "citta": "Pisa", "stato": "pianificazione", "credit_state": "attivo", "created_at": NOW})
    await db.structures.insert_many([
        {"id": "st_TEST_bo", "org_id": ORG, "nome": "Hotel Bologna", "indirizzo": "Via Indipendenza 5", "citta": "Bologna",
         "telefono": "+39051111111", "referente": "Giulia Neri", "telefono_referente": "+39333000111", "note": "Parcheggio interno", "created_at": NOW},
        {"id": "st_TEST_pi", "org_id": ORG, "nome": "Hotel Pisa", "indirizzo": "Lungarno 3", "citta": "Pisa", "telefono": "+39050222222", "created_at": NOW},
        {"id": "st_TEST_rist", "org_id": ORG, "nome": "Ristorante XYZ", "indirizzo": "Via Roma 10", "citta": "Pisa", "created_at": NOW},
    ])
    people = [("p1", "Mario", "Rossi"), ("p2", "Luca", "Bianchi"), ("p3", "Andrea", "Verdi"), ("p4", "Paolo", "Gialli"), ("p5", "Anna", "Blu"), ("p6", "Sara", "Senzahotel")]
    for pid, n, c in people:
        await db.persons.insert_one({"id": f"pe_TEST_{pid}", "org_id": ORG, "nome": n, "cognome": c, "created_at": NOW})
        await db.staff.insert_one({"id": f"sl_TEST_{pid}", "org_id": ORG, "evento_id": EV, "persona_id": f"pe_TEST_{pid}",
                                   "categoria": "staff", "esigenze_alimentari": ["Vegetariano"] if pid in ("p2", "p5") else [], "created_at": NOW})
    lods = [  # (persona, struttura, camera, tipo, in, out)
        ("p1", "st_TEST_bo", "101", "doppia", "2026-12-18", "2026-12-21"),
        ("p2", "st_TEST_bo", "101", "doppia", "2026-12-18", "2026-12-20"),
        ("p3", "st_TEST_bo", "102", "singola", "2026-12-19", "2026-12-21"),
        ("p4", "st_TEST_pi", "204", "tripla", "2026-12-18", "2026-12-21"),
        ("p5", "st_TEST_pi", "204", "tripla", "2026-12-19", "2026-12-20"),
    ]
    for i, (pid, st, cam, tipo, ci, co) in enumerate(lods):
        await db.lodgings.insert_one({"id": f"lo_TEST_{i}", "org_id": ORG, "evento_id": EV, "persona_id": f"pe_TEST_{pid}",
                                      "struttura_id": st, "numero_camera": cam, "tipo_camera": tipo, "check_in": ci, "check_out": co, "created_at": NOW})
    # pasto senza camera assegnata per Sara non c'è: Sara ha solo pasti
    i = 0
    for pid in ["p1", "p2", "p3", "p4", "p5", "p6"]:
        meals = [("2026-12-19", "2026-12-19", "cena", "st_TEST_rist", "20:00", "Tavolo riservato CRMEvent"),
                 ("2026-12-20", "2026-12-20", "colazione", "st_TEST_pi", "05:30-07:00", None),
                 ("2026-12-20", "2026-12-20", "pranzo", "st_TEST_rist", "14:30", None)]
        for di, df, tipo, st, ora, note in meals:
            await db.meals.insert_one({"id": f"me_TEST_{i}", "org_id": ORG, "evento_id": EV, "persona_id": f"pe_TEST_{pid}",
                                       "data": di, "data_inizio": di, "data_fine": df, "tipo_pasto": tipo, "struttura_id": st,
                                       "orario": ora, "note": note, "referente": "Mario Rossi" if tipo == "cena" else None,
                                       "telefono": "+39333999888" if tipo == "cena" else None, "created_at": NOW})
            i += 1
    print("seeded")


asyncio.run(clean() if "--clean" in sys.argv else seed())
