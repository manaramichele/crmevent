"""Seed TEST_ org for Team card + Team-scoped permissions. Run with --clean to remove."""
import os, sys, asyncio, bcrypt
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
ORG, EV = "org_TEST_tl", "ev_TEST_tl"
USERS = [("user_TEST_tl_admin", "test_tl_admin@crmeventqa.it", "admin_org"),
         ("user_TEST_tl_leader", "test_tl_leader@crmeventqa.it", "collaboratore"),
         ("user_TEST_tl_resp", "test_tl_resp@crmeventqa.it", "collaboratore")]
NOW = datetime.now(timezone.utc).isoformat()


async def clean():
    uids = [u[0] for u in USERS]
    for c in await db.list_collection_names():
        await db[c].delete_many({"$or": [{"org_id": ORG}, {"user_id": {"$in": uids}}, {"id": ORG}]})


async def seed():
    await clean()
    qa = await db.organizations.find_one({"id": "org_qa_eventi"}, {"_id": 0})
    await db.organizations.insert_one({**qa, "id": ORG, "nome": "TEST_TeamLeader Org", "owner_user_id": USERS[0][0], "created_at": NOW,
                                       "subscription": {**qa["subscription"], "stripe_customer_id": None}})
    h = bcrypt.hashpw(b"TestTl2026!", bcrypt.gensalt()).decode()
    for uid, email, role in USERS:
        await db.users.insert_one({"user_id": uid, "email": email, "name": uid.replace("user_", ""), "role": "admin" if role == "admin_org" else "member",
                                   "auth_provider": "password", "password_hash": h, "org_id": ORG, "active": True, "telefono": "+393331234567",
                                   "accepted_terms_at": NOW, "created_at": NOW, "registered_at": NOW, "onboarding": {"seen": True}})
        perms = {}
        if uid.endswith("resp"):  # Responsabile Volontari: tutti i Team, sola lettura
            perms = {"sections": {"staff": ["view"], "dashboard": ["view"], "anagrafiche": ["view"]}, "events": "all", "teams": {"scope": "all", "ids": []}}
        await db.memberships.insert_one({"id": f"mem_{uid}", "user_id": uid, "org_id": ORG, "role": role, "active": True,
                                         "permissions": perms, "created_at": NOW})
    await db.events.insert_one({"id": EV, "org_id": ORG, "nome": "TEST_Maratona", "data_inizio": "2026-12-19", "data_fine": "2026-12-20",
                                "stato": "pianificazione", "credit_state": "attivo", "created_at": NOW})
    # persona Team Leader con la stessa email dell'utente collaboratore
    await db.persons.insert_one({"id": "pe_TEST_leader", "org_id": ORG, "nome": "Michele", "cognome": "Leader", "email": "Test_TL_Leader@crmeventqa.it", "created_at": NOW})
    await db.staff.insert_one({"id": "sl_TEST_leader", "org_id": ORG, "evento_id": EV, "persona_id": "pe_TEST_leader", "categoria": "staff",
                               "team_id": "tm_TEST_start", "stato": "confermato", "created_at": NOW})
    teams = [("tm_TEST_start", "Start Line", "pe_TEST_leader", 20, 4, 18), ("tm_TEST_ristori", "Ristori", None, 10, 2, 7), ("tm_TEST_expo", "Expo", None, None, 1, 0)]
    i = 0
    for tid, nome, leader, req, n_staff, n_vol in teams:
        await db.teams.insert_one({"id": tid, "org_id": ORG, "evento_id": EV, "nome": nome, "responsabile_id": leader, "area": f"Area {nome}",
                                   "luogo_operativo": f"Luogo {nome}", "punto_ritrovo": "Gazebo", "volontari_richiesti": req, "created_at": NOW})
        for cat, n in [("staff", n_staff), ("volontario", n_vol)]:
            for _ in range(n):
                pid = f"pe_TEST_tl{i}"
                await db.persons.insert_one({"id": pid, "org_id": ORG, "nome": f"{cat.capitalize()}{i}", "cognome": "TEST", "created_at": NOW})
                await db.staff.insert_one({"id": f"sl_TEST_tl{i}", "org_id": ORG, "evento_id": EV, "persona_id": pid, "categoria": cat,
                                           "team_id": tid, "stato": "confermato", "created_at": NOW})
                await db.shifts.insert_one({"id": f"sh_TEST_tl{i}", "org_id": ORG, "evento_id": EV, "persona_id": pid, "team_id": tid,
                                            "data": "2026-12-19", "ora_inizio": "07:00", "ora_fine": "12:00", "created_at": NOW})
                i += 1
    print("seeded")


asyncio.run(clean() if "--clean" in sys.argv else seed())
