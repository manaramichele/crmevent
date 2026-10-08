"""Seed TEST_iter82_ui_ data for frontend UI testing of Team Leader perms."""
import os, uuid
from datetime import datetime, timezone
from pymongo import MongoClient
import bcrypt

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
ORG = "org_qa_eventi"
TAG = "TEST_iter82_ui"
EMAIL = f"test_tl_{TAG}@example.com".lower()
PWD = "TlPwdUi2026!"

client = MongoClient(MONGO_URL)
d = client[DB_NAME]
now = datetime.now(timezone.utc).isoformat()

# Clean prior if any
d.users.delete_many({"email": EMAIL})
d.memberships.delete_many({"user_id": {"$regex": f"^user_{TAG}"}})
d.teams.delete_many({"id": {"$regex": f"^{TAG}"}})
d.staff.delete_many({"id": {"$regex": f"^{TAG}"}})
d.persons.delete_many({"id": {"$regex": f"^{TAG}"}})
d.events.delete_many({"id": {"$regex": f"^{TAG}"}})
d.shifts.delete_many({"id": {"$regex": f"^{TAG}"}})

uid = f"user_{TAG}"
d.users.insert_one({"user_id": uid, "email": EMAIL, "name": "TL UI",
                    "role": "user", "auth_provider": "password",
                    "password_hash": bcrypt.hashpw(PWD.encode(), bcrypt.gensalt()).decode(),
                    "org_id": ORG, "active": True, "created_at": now,
                    "telefono": "+393490000001"})

ev = {"id": f"{TAG}_ev", "org_id": ORG, "nome": f"{TAG} Event",
      "data_inizio": "2026-09-01", "data_fine": "2026-09-02",
      "credit_state": "attivo", "created_at": now}
d.events.insert_one(ev)

leader_p = {"id": f"{TAG}_leader", "org_id": ORG, "nome": "Leader", "cognome": "UI",
            "email": EMAIL, "created_at": now}
p_m1 = {"id": f"{TAG}_m1", "org_id": ORG, "nome": "Membro1", "cognome": "UI",
        "email": f"test_m1_{TAG}@example.com", "invite_status": "non_invitato", "created_at": now}
p_m2 = {"id": f"{TAG}_m2", "org_id": ORG, "nome": "Membro2", "cognome": "UI",
        "email": f"test_m2_{TAG}@example.com", "invite_status": "invito_inviato", "created_at": now}
d.persons.insert_many([leader_p, p_m1, p_m2])

t = {"id": f"{TAG}_tA", "org_id": ORG, "nome": f"{TAG} TeamUI", "evento_id": ev["id"],
     "responsabile_id": leader_p["id"], "volontari_richiesti": 3, "created_at": now}
d.teams.insert_one(t)

d.staff.insert_many([
    {"id": f"{TAG}_s1", "org_id": ORG, "persona_id": p_m1["id"], "evento_id": ev["id"],
     "team_id": t["id"], "categoria": "staff", "stato": "da_contattare", "created_at": now},
    {"id": f"{TAG}_s2", "org_id": ORG, "persona_id": p_m2["id"], "evento_id": ev["id"],
     "team_id": t["id"], "categoria": "volontario", "stato": "da_contattare", "created_at": now},
])

perm = {"sections": {k: [] for k in [
    "dashboard", "eventi", "staff", "aziende", "anagrafiche", "ospitalita",
    "sponsor", "attivita", "followup", "briefing", "mappe", "pipeline"]},
    "events": "all",
    "teams": {"scope": "leader", "ids": [], "manage_staff": True, "manage_volunteers": True},
    "send_invites": False,
    "team_leader": {"edit_members": False, "manage_shifts": False}}
perm["sections"]["dashboard"] = ["view"]
d.memberships.insert_one({"id": f"mem_{TAG}", "org_id": ORG, "user_id": uid,
                          "role": "collaboratore", "active": True, "created_at": now,
                          "permissions": perm})
print(f"SEEDED user={EMAIL} pwd={PWD} team={t['id']} uid={uid}")
client.close()
