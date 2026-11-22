# DB helper for iteration 206 fasce coverage tests: snapshot/restore TEST_Fasce availabilities
import asyncio, json, os, sys
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
EV = "5e09ce16ec304f4e8b332870b59d1a1e"
SNAP = "/tmp/fx_snapshot.json"


async def main(cmd):
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    ev = await db.events.find_one({"id": EV}, {"_id": 0})
    org = ev["org_id"]
    if cmd == "show":
        print("event", ev.get("nome"), ev.get("data_inizio"), ev.get("data_fine"), json.dumps(ev.get("avail_fasce") or ev.get("fasce_giorni") or {}, default=str)[:600])
        async for a in db.availabilities.find({"org_id": org}, {"_id": 0}):
            p = await db.persons.find_one({"id": a.get("persona_id")}, {"_id": 0, "cognome": 1, "nome": 1, "gruppo_appartenenza": 1})
            print(a["id"], a["evento_id"][:8], p, json.dumps(a.get("days"), default=str), "HIST:", json.dumps(a.get("days_history"), default=str))
        print("staff", await db.staff.find({"org_id": org}, {"_id": 0, "persona_id": 1, "ruolo": 1, "team_id": 1, "evento_id": 1}).to_list(100))
        print("teams", await db.teams.find({"org_id": org}, {"_id": 0}).to_list(100))
        print("needs", await db.coverage_fascia_needs.find({"org_id": org}, {"_id": 0}).to_list(100))
        print("links", await db.avail_links.find({"org_id": org}, {"_id": 0, "code": 1, "evento_id": 1, "active": 1}).to_list(10))
        print("persons", await db.persons.find({"org_id": org}, {"_id": 0, "id": 1, "cognome": 1}).to_list(100))
    elif cmd == "snap":
        avs = await db.availabilities.find({"org_id": org}, {"_id": 0}).to_list(1000)
        json.dump(avs, open(SNAP, "w"), default=str)
        print("snap", len(avs))
    elif cmd == "restore":
        avs = json.load(open(SNAP))
        ids = [a["id"] for a in avs]
        for a in avs:
            await db.availabilities.replace_one({"id": a["id"], "org_id": org}, a, upsert=True)
        print("restored", len(avs))


asyncio.run(main(sys.argv[1]))
