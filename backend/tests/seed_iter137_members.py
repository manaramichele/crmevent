# Seed/cleanup TEST_ members (role user / collaboratore) in org_qa_eventi for menu + tickets tests (iteration 137)
import os, sys, asyncio, uuid, bcrypt
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv('/app/backend/.env')
db = AsyncIOMotorClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
PW = "TestPass2026!"
USERS = [("test_iter137_user@crmeventqa.it", "user", {}),
         ("test_iter137_collab@crmeventqa.it", "collaboratore",
          {"sections": {}, "events": "all", "send_invites": False})]


async def seed():
    now = datetime.now(timezone.utc).isoformat()
    h = bcrypt.hashpw(PW.encode(), bcrypt.gensalt()).decode()
    for email, role, perms in USERS:
        uid = "user_test137_" + role
        await db.users.delete_many({"email": email})
        await db.memberships.delete_many({"user_id": uid})
        await db.users.insert_one({"user_id": uid, "email": email, "name": f"TEST_ {role}", "password_hash": h, "role": "member",
                                   "auth_provider": "password", "org_id": "org_qa_eventi", "telefono": "+393330000000", "picture": "",
                                   "active": True, "created_at": now, "registered_at": now, "accepted_terms_at": now,
                                   "onboarding": {"seen": True, "skipped": {}, "card_hidden": True, "started": True, "later": False}})
        await db.memberships.insert_one({"id": "mem_test137_" + role, "user_id": uid, "org_id": "org_qa_eventi", "role": role,
                                         "active": True, "permissions": perms, "added_by": "user_qaeventi",
                                         "created_at": now, "updated_at": now, "last_login_at": None})
    print("seeded")


async def cleanup():
    uids = ["user_test137_user", "user_test137_collaboratore"]
    print("users", (await db.users.delete_many({"user_id": {"$in": uids}})).deleted_count)
    print("mem", (await db.memberships.delete_many({"user_id": {"$in": uids}})).deleted_count)
    tks = await db.tickets.find({"subject": {"$regex": "^TEST_"}}, {"_id": 0, "id": 1}).to_list(1000)
    ids = [t["id"] for t in tks]
    print("tickets", (await db.tickets.delete_many({"id": {"$in": ids}})).deleted_count)
    print("msgs", (await db.ticket_messages.delete_many({"ticket_id": {"$in": ids}})).deleted_count)
    print("files", (await db.ticket_files.delete_many({"ticket_id": {"$in": ids}})).deleted_count)
    print("sessions", (await db.user_sessions.delete_many({"user_id": {"$in": uids}})).deleted_count)


asyncio.run(cleanup() if "cleanup" in sys.argv else seed())
