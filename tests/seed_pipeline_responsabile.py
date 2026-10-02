"""Seed test data for Pipeline Responsabile filtering test."""
import uuid, time
from pymongo import MongoClient
from datetime import datetime, timezone

c = MongoClient('mongodb://localhost:27017')
db = c['test_database']

ORG_ID = db.users.find_one({'email': 'demo.crmevent@gmail.com'})['org_id']
NOW = datetime.now(timezone.utc).isoformat()

def nid(): return uuid.uuid4().hex

# 1 azienda for the referente-only person
AZ_ID = nid()
db.companies.insert_one({
    "id": AZ_ID, "org_id": ORG_ID, "ragione_sociale": "TEST_Azienda_SRL",
    "created_at": NOW, "updated_at": NOW,
})

# 1 event, operational (no credit_state)
EV_ID = nid()
db.events.insert_one({
    "id": EV_ID, "org_id": ORG_ID, "nome": "TEST_Evento_Pipeline",
    "data_inizio": "2026-06-15", "data_fine": "2026-06-15",
    "stato": "pianificato",
    "created_at": NOW, "updated_at": NOW,
})

# 5 persons (sorting-sensitive cognomi: Alberti, Bianchi, Colombo, Dalla, Esposito)
persons_data = [
    ("TEST_Mario", "Alberti", "staff"),       # should appear (staff)
    ("TEST_Luigi", "Bianchi", "collaboratore"),  # should appear (collaboratore)
    ("TEST_Peach", "Colombo", "volontario"),   # NOT appear
    ("TEST_Toad",  "Dalla",   "team"),         # NOT appear (da classificare)
    ("TEST_Bowser","Esposito", None),          # referente-only, no staff link
]
PERSON_IDS = {}
for nome, cognome, categoria in persons_data:
    pid = nid()
    PERSON_IDS[cognome] = pid
    doc = {
        "id": pid, "org_id": ORG_ID,
        "nome": nome, "cognome": cognome,
        "created_at": NOW, "updated_at": NOW,
    }
    if categoria is None:
        doc["azienda_id"] = AZ_ID  # referente only
    db.persons.insert_one(doc)
    if categoria:
        db.staff.insert_one({
            "id": nid(), "org_id": ORG_ID,
            "persona_id": pid, "evento_id": EV_ID,
            "categoria": categoria,
            "created_at": NOW, "updated_at": NOW,
        })

# Activate pipeline doc
db.event_pipelines.insert_one({
    "id": nid(), "org_id": ORG_ID, "event_id": EV_ID,
    "active": True, "activated_at": NOW, "activation_cost": 0,
    "template_key": "trail", "created_at": NOW, "updated_at": NOW,
})

# Seed one category
CAT_ID = nid()
db.pipeline_categories.insert_one({
    "id": CAT_ID, "org_id": ORG_ID, "event_id": EV_ID,
    "name": "Logistica", "order": 0,
    "created_at": NOW, "updated_at": NOW,
})

# Seed 2 pipeline tasks:
#   T1: no responsabile
#   T2: responsabile = Peach Colombo (NOT staff) -> stale test
T1 = nid(); T2 = nid()
db.pipeline_tasks.insert_many([
    {"id": T1, "org_id": ORG_ID, "event_id": EV_ID, "categoria_id": CAT_ID,
     "titolo": "TEST_Task_NoResp", "stato": "da_fare", "priorita": "normale",
     "created_at": NOW, "updated_at": NOW},
    {"id": T2, "org_id": ORG_ID, "event_id": EV_ID, "categoria_id": CAT_ID,
     "titolo": "TEST_Task_StaleResp", "stato": "da_fare", "priorita": "normale",
     "responsabile_id": PERSON_IDS["Colombo"],  # volontario -> non staff
     "created_at": NOW, "updated_at": NOW},
])

print("ORG_ID:", ORG_ID)
print("EV_ID:", EV_ID)
print("T1:", T1, "T2 (stale):", T2)
print("Persons:", PERSON_IDS)
