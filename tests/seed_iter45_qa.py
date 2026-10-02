"""Seed data for QA org to test iteration 45 features (sort + pipeline quick-staff)."""
import uuid, sys
from pymongo import MongoClient
from datetime import datetime, timezone

c = MongoClient('mongodb://localhost:27017')
db = c['test_database']

user = db.users.find_one({'email': 'qa.eventi@crmeventqa.it'})
if not user:
    sys.exit("QA user not found")
ORG_ID = user['org_id']
NOW = datetime.now(timezone.utc).isoformat()

def nid(): return uuid.uuid4().hex

# Clean previous TEST_ data in QA org
db.events.delete_many({"org_id": ORG_ID, "nome": {"$regex": "^TEST_QA_"}})
db.persons.delete_many({"org_id": ORG_ID, "nome": {"$regex": "^TEST_QA_"}})

# Event (operational: no credit_state issue → set to preparazione)
EV_ID = nid()
db.events.insert_one({
    "id": EV_ID, "org_id": ORG_ID, "nome": "TEST_QA_Iter45_Event",
    "data_inizio": "2026-07-20", "data_fine": "2026-07-22",
    "stato": "pianificato", "credit_state": "preparazione",
    "created_at": NOW, "updated_at": NOW,
})

# Staff persons on the event
staff_data = [
    ("TEST_QA_Zara", "Ancona", "staff"),
    ("TEST_QA_Marco", "Bellini", "staff"),
    ("TEST_QA_Davide", "Delmonte", "staff"),
]
PIDS = {}
for n, co, cat in staff_data:
    pid = nid(); PIDS[co] = pid
    db.persons.insert_one({"id": pid, "org_id": ORG_ID, "nome": n, "cognome": co,
                           "created_at": NOW, "updated_at": NOW})
    db.staff.insert_one({"id": nid(), "org_id": ORG_ID, "persona_id": pid,
                         "evento_id": EV_ID, "categoria": cat, "created_at": NOW})

# Add some volontari too so staff-volontari page has rows with vuoti values
vol = [("TEST_QA_Luca", "Rossi", "volontario", "+393334444001"),
       ("TEST_QA_Elena", "Verdi", "volontario", None),
       ("TEST_QA_Paolo", "Alfieri", "staff", None)]
for n, co, cat, cel in vol:
    pid = nid()
    doc = {"id": pid, "org_id": ORG_ID, "nome": n, "cognome": co,
           "created_at": NOW, "updated_at": NOW}
    if cel: doc["cellulare"] = cel
    db.persons.insert_one(doc)
    db.staff.insert_one({"id": nid(), "org_id": ORG_ID, "persona_id": pid,
                         "evento_id": EV_ID, "categoria": cat, "created_at": NOW})

# Active pipeline for the event
db.event_pipelines.insert_one({"id": nid(), "org_id": ORG_ID, "event_id": EV_ID,
                               "active": True, "activated_at": NOW, "activation_cost": 0,
                               "template_key": "trail", "created_at": NOW})

# A few aziende so EntityManager /aziende has rows
db.companies.delete_many({"org_id": ORG_ID, "ragione_sociale": {"$regex": "^TEST_QA_"}})
for rs in ["TEST_QA_Zeta Srl", "TEST_QA_Alpha SpA", "TEST_QA_Mike Co"]:
    db.companies.insert_one({"id": nid(), "org_id": ORG_ID,
                             "ragione_sociale": rs, "created_at": NOW})

print("ORG_ID:", ORG_ID)
print("EV_ID:", EV_ID)
