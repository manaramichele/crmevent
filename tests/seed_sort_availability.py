"""Seed test data for sort (pipeline) + availabilities responsiveness tests."""
import uuid, random
from pymongo import MongoClient
from datetime import datetime, timezone

c = MongoClient('mongodb://localhost:27017')
db = c['test_database']

user = db.users.find_one({'email': 'demo.crmevent@gmail.com'})
ORG_ID = user['org_id']
NOW = datetime.now(timezone.utc).isoformat()

def nid(): return uuid.uuid4().hex

# Event (operational: no credit_state)
EV_ID = nid()
db.events.insert_one({
    "id": EV_ID, "org_id": ORG_ID, "nome": "TEST_SortEvent",
    "data_inizio": "2026-06-15", "data_fine": "2026-06-17",
    "data_inizio_allestimento": "2026-06-14",
    "data_fine_disallestimento": "2026-06-18",
    "stato": "pianificato",
    "created_at": NOW, "updated_at": NOW,
})

# Persons as responsabili (staff + collaboratore) with varied cognomi
staff_data = [
    ("Zara", "Ancona", "staff"),
    ("Marco", "Bellini", "staff"),
    ("Giulia", "Carrara", "collaboratore"),
    ("Davide", "Del Monte", "staff"),
]
PERSON_IDS = {}
for nome, cognome, cat in staff_data:
    pid = nid()
    PERSON_IDS[cognome] = pid
    db.persons.insert_one({
        "id": pid, "org_id": ORG_ID, "nome": nome, "cognome": cognome,
        "created_at": NOW, "updated_at": NOW,
    })
    db.staff.insert_one({
        "id": nid(), "org_id": ORG_ID, "persona_id": pid, "evento_id": EV_ID,
        "categoria": cat, "created_at": NOW, "updated_at": NOW,
    })

# Active pipeline
db.event_pipelines.insert_one({
    "id": nid(), "org_id": ORG_ID, "event_id": EV_ID,
    "active": True, "activated_at": NOW, "activation_cost": 0,
    "template_key": "trail", "created_at": NOW, "updated_at": NOW,
})

# 3 categories (so Categoria sort has A/B/C)
cats = []
for name in ["Alfa", "Beta", "Gamma"]:
    cid = nid()
    cats.append((cid, name))
    db.pipeline_categories.insert_one({
        "id": cid, "org_id": ORG_ID, "event_id": EV_ID,
        "name": name, "order": len(cats) - 1,
        "created_at": NOW, "updated_at": NOW,
    })

# Tasks with varied titolo, categoria, scadenza (some empty), stato, priorita, responsabile
tasks = [
    ("TEST_Alfa_Task", cats[0][0], "2026-05-01", "da_fare",     "critica",    "Ancona"),
    ("TEST_Zeta_Task", cats[2][0], "2026-04-10", "in_corso",    "normale",    "Bellini"),
    ("TEST_Delta_Task", cats[1][0], None,         "completata", "importante", "Del Monte"),
    ("TEST_Mike_Task", cats[0][0], "2026-07-20", "da_fare",     "normale",    None),
    ("TEST_Bravo_Task", cats[2][0], None,         "in_corso",   "critica",    "Carrara"),
    ("TEST_Yankee_Task", cats[1][0], "2026-03-05","da_fare",    "importante", None),
]
for titolo, cid, scad, stato, prio, resp in tasks:
    doc = {
        "id": nid(), "org_id": ORG_ID, "event_id": EV_ID, "categoria_id": cid,
        "titolo": titolo, "stato": stato, "priorita": prio,
        "created_at": NOW, "updated_at": NOW,
    }
    if scad: doc["scadenza"] = scad
    if resp: doc["responsabile_id"] = PERSON_IDS[resp]
    db.pipeline_tasks.insert_one(doc)

# ~45 availabilities for the event
first_names = ["Luca","Marta","Giovanni","Elena","Paolo","Chiara","Andrea","Sara","Matteo","Alessia",
               "Federico","Valentina","Francesco","Martina","Lorenzo","Giorgia","Alberto","Serena","Simone","Noemi",
               "Davide","Camilla","Riccardo","Beatrice","Enrico","Silvia","Edoardo","Alice","Nicola","Ilaria",
               "Fabio","Monica","Stefano","Erica","Pietro","Veronica","Gabriele","Roberta","Daniele","Laura",
               "Michele","Barbara","Antonio","Rachele","Marco"]
last_names = ["Rossi","Bianchi","Russo","Ferrari","Esposito","Romano","Colombo","Ricci","Marino","Greco",
              "Bruno","Gallo","Conti","De Luca","Mancini","Costa","Giordano","Rizzo","Lombardi","Moretti",
              "Barbieri","Fontana","Santoro","Mariani","Rinaldi","Caruso","Ferrara","Galli","Martini","Leone",
              "Longo","Gentile","Martinelli","Vitale","Lombardo","Serra","Coppola","De Santis","D'Angelo","Marchetti",
              "Parisi","Villa","Conte","Ferretti","Bianco"]

random.seed(42)
for i in range(45):
    pid_p = nid()
    nome = first_names[i]
    cog = last_names[i]
    db.persons.insert_one({
        "id": pid_p, "org_id": ORG_ID, "nome": f"TEST_{nome}", "cognome": cog,
        "email": f"test_{i}@example.com", "cellulare": f"+39333{1000000+i}",
        "data_nascita": f"199{i%10}-01-15",
        "created_at": NOW, "updated_at": NOW,
    })
    ruolo = random.choice(["da_definire","staff","volontario"])
    stato = random.choice(["nuova","confermata","non_utilizzata"])
    db.availabilities.insert_one({
        "id": nid(), "org_id": ORG_ID, "evento_id": EV_ID, "persona_id": pid_p,
        "nome": f"TEST_{nome}", "cognome": cog, "email": f"test_{i}@example.com",
        "cellulare": f"+39333{1000000+i}", "data_nascita": f"199{i%10}-01-15",
        "ruolo_evento": ruolo, "stato": stato,
        "preferenza_attivita": random.choice(["Allestimento","Accoglienza","Logistica","Altro"]),
        "preferenza_altro": None,
        "days": [{"date":"2026-06-15","dalle":"09:00","alle":"18:00","fase":"evento"}],
        "has_mismatch": False, "privacy_accepted": True,
        "privacy_ts": NOW, "code": f"TC{i:03d}",
        "brevo_status":"skipped",
        "created_at": NOW, "updated_at": NOW,
    })

print("ORG_ID:", ORG_ID)
print("EV_ID:", EV_ID)
print("Persons staff:", PERSON_IDS)
