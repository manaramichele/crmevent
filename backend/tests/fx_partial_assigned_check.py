# Ad-hoc check (iter 206): does a PARTIAL person with a mansione count in 'assegnati' of the fascia?
import os, requests
from pymongo import MongoClient
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
B = "https://manage-events-12.preview.emergentagent.com"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
EV, LP = "5e09ce16ec304f4e8b332870b59d1a1e", "6d9ed5cbe39647f9b24c31bbffd2d459"
s = requests.Session()
s.post(f"{B}/api/auth/login", json={"email": "test_fx_f73982@example.com", "password": "TestPass123!"})
link = db.staff.find_one({"persona_id": LP, "evento_id": EV})
try:
    db.staff.update_one({"id": link["id"]}, {"$set": {"ruolo": "Hostess"}})
    rows = {(r["date"], r["fascia"]): r for r in s.get(f"{B}/api/staff-coverage/fasce", params={"evento_id": EV}).json()["rows"]}
    for k in [("2026-12-19", "mattina"), ("2026-12-19", "pomeriggio")]:
        r = rows[k]
        print(k, "available", r["available"], "partial", r["partial"], "assigned", r["assigned"])
finally:
    db.staff.update_one({"id": link["id"]}, {"$unset": {"ruolo": ""}} if "ruolo" not in link else {"$set": {"ruolo": link.get("ruolo")}})
    print("restored", db.staff.find_one({"id": link["id"]}, {"_id": 0, "ruolo": 1}))
