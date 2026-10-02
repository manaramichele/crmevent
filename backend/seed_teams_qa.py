import asyncio, uuid
from datetime import datetime, timezone
from dotenv import load_dotenv; load_dotenv('/app/backend/.env')
import os
from motor.motor_asyncio import AsyncIOMotorClient

ORG = "org_qa_eventi"
EV = "ev_qa_1"  # Maratona QA
now = datetime.now(timezone.utc).isoformat()

def nid(pfx): return f"{pfx}_{uuid.uuid4().hex[:10]}"

PEOPLE = [
    ("Anna", "Bianchi", "anna.bianchi.qa@example.com", "+393401110001", "staff", "ristori", "Caposquadra", True),
    ("Marco", "Rossi", "marco.rossi.qa@example.com", "+393401110002", "staff", "ristori", "Addetto", False),
    ("Luca", "Verdi", "luca.verdi.qa@example.com", "+393401110003", "volontario", "ristori", "Volontario ristoro", False),
    ("Sara", "Neri", "sara.neri.qa@example.com", "+393401110004", "staff", "pacer", "Pace leader", True),
    ("Paolo", "Gialli", "paolo.gialli.qa@example.com", "+393401110005", "volontario", "pacer", "Pacer", False),
    ("Elena", "Blu", "elena.blu.qa@example.com", "+393401110006", "staff", "run", "Coordinatore", True),
    ("Giulia", "Viola", "giulia.viola.qa@example.com", "+393401110007", "volontario", None, None, False),
    ("Davide", "Mora", "davide.mora.qa@example.com", "+393401110008", "staff", None, None, False),
]
TEAMS = {"ristori": "Team Ristori", "pacer": "Team Pacer", "run": "Team Run"}


async def main():
    c = AsyncIOMotorClient(os.environ['MONGO_URL']); db = c[os.environ['DB_NAME']]
    # teams
    team_ids = {}
    for key, nome in TEAMS.items():
        t = await db.teams.find_one({"org_id": ORG, "evento_id": EV, "nome": nome}, {"_id": 0})
        if t:
            team_ids[key] = t["id"]
        else:
            tid = nid("team")
            await db.teams.insert_one({"id": tid, "org_id": ORG, "nome": nome, "evento_id": EV, "area": nome.split()[-1], "responsabile_id": None, "created_at": now})
            team_ids[key] = tid
    # persons + staff links
    leader_by_team = {}
    for nome, cognome, email, cell, cat, tkey, ruolo, leader in PEOPLE:
        p = await db.persons.find_one({"org_id": ORG, "email": email}, {"_id": 0})
        if not p:
            pid = nid("person")
            await db.persons.insert_one({"id": pid, "org_id": ORG, "nome": nome, "cognome": cognome, "email": email, "cellulare": cell, "created_at": now})
        else:
            pid = p["id"]
            await db.persons.update_one({"id": pid}, {"$set": {"cellulare": cell}})
        tid = team_ids.get(tkey) if tkey else None
        link = await db.staff.find_one({"org_id": ORG, "persona_id": pid, "evento_id": EV}, {"_id": 0})
        data = {"persona_id": pid, "evento_id": EV, "categoria": cat, "team_id": tid, "ruolo": ruolo, "stato": "confermato"}
        if link:
            await db.staff.update_one({"id": link["id"]}, {"$set": data})
        else:
            await db.staff.insert_one({"id": nid("staff"), "org_id": ORG, "created_at": now, **data})
        if leader and tid:
            leader_by_team[tid] = pid
    for tid, pid in leader_by_team.items():
        await db.teams.update_one({"id": tid}, {"$set": {"responsabile_id": pid}})
    # a couple shifts
    for email, tkey in [("anna.bianchi.qa@example.com", "ristori"), ("sara.neri.qa@example.com", "pacer")]:
        p = await db.persons.find_one({"org_id": ORG, "email": email}, {"_id": 0})
        tid = team_ids[tkey]
        sh = await db.shifts.find_one({"org_id": ORG, "evento_id": EV, "persona_id": p["id"]}, {"_id": 0})
        sdata = {"persona_id": p["id"], "evento_id": EV, "team_id": tid, "data": "2026-04-19", "ora_inizio": "07:00", "ora_fine": "13:00", "luogo": "Partenza"}
        if sh:
            await db.shifts.update_one({"id": sh["id"]}, {"$set": sdata})
        else:
            await db.shifts.insert_one({"id": nid("shift"), "org_id": ORG, "created_at": now, **sdata})
    # report
    for key, nome in TEAMS.items():
        tid = team_ids[key]
        n = len({l["persona_id"] for l in await db.staff.find({"org_id": ORG, "team_id": tid}, {"_id": 0, "persona_id": 1}).to_list(100)})
        print(f"{nome} ({tid[:10]}): {n} componenti, leader={leader_by_team.get(tid)}")
    print("Candidates (no team):", [p for p in ["Giulia Viola", "Davide Mora"]])

asyncio.run(main())
