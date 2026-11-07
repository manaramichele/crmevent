# UI seed/cleanup for Ricerca da Brevo tab: python tests/cal_reverse_ui_seed.py seed|cleanup
import json
import os
import sys
import uuid
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
F = "/tmp/cal_reverse_ui_ids.json"

if sys.argv[1] == "seed":
    t = uuid.uuid4().hex[:5]
    ids = {"contacts": [uuid.uuid4().hex, uuid.uuid4().hex], "findings": [uuid.uuid4().hex, uuid.uuid4().hex],
           "jobs_before": [j["id"] for j in db.cal_rv_jobs.find({}, {"id": 1})],
           "orgs_before": [o["id"] for o in db.cal_organizers.find({}, {"id": 1})],
           "events_before": [e["id"] for e in db.cal_events.find({}, {"id": 1})],
           "rv": (db.cal_settings.find_one({"id": "main"}, {"rv": 1}) or {}).get("rv")}
    db.cal_rv_contacts.insert_one({"id": ids["contacts"][0], "email": f"test_ui{t}@test-asd-ui{t}.it", "societa": f"TEST_ASD UI {t}",
                                   "dominio": f"test-asd-ui{t}.it", "stato_ricerca": "da_analizzare", "eventi": [], "fonti": []})
    db.cal_rv_contacts.insert_one({"id": ids["contacts"][1], "email": f"test_ui{t}@gmail.com", "societa": None, "dominio": None,
                                   "stato_ricerca": "dati_insufficienti", "eventi": [], "fonti": [], "nota": "TEST nota"})
    for i, fid in enumerate(ids["findings"]):
        db.cal_rv_findings.insert_one({"id": fid, "key": f"testui:{fid}", "contact_id": ids["contacts"][0], "email": f"test_ui{t}@test-asd-ui{t}.it",
                                       "nome": f"TEST_Gara UI{i} {t}", "disciplina": "running", "data_inizio": None, "data_fine": None, "anno": None,
                                       "stato": "data_da_confermare", "stato_evento": "confermata", "attendibilita": 50, "organizzatore": f"TEST_Org UI {t}",
                                       "organizer_id": None, "fonte_url": "https://example.org/gara", "estratto": "TEST estratto",
                                       "verificato_il": "2026-01-01T00:00:00+00:00"})
    json.dump(ids, open(F, "w"))
    print(json.dumps({"contacts": ids["contacts"], "findings": ids["findings"]}))
else:
    ids = json.load(open(F))
    db.cal_rv_jobs.delete_many({"id": {"$nin": ids["jobs_before"]}})
    db.cal_rv_contacts.delete_many({"id": {"$in": ids["contacts"]}})
    db.cal_rv_findings.delete_many({"id": {"$in": ids["findings"]}})
    ev = [e["id"] for e in db.cal_events.find({"id": {"$nin": ids["events_before"]}, "nome": {"$regex": "^TEST_"}}, {"id": 1})]
    org = [o["id"] for o in db.cal_organizers.find({"id": {"$nin": ids["orgs_before"]}, "nome": {"$regex": "^TEST_"}}, {"id": 1})]
    db.cal_history.delete_many({"entity_id": {"$in": ev + org}})
    db.cal_duplicates.delete_many({"$or": [{"a": {"$in": ev}}, {"b": {"$in": ev}}]})
    db.cal_events.delete_many({"id": {"$in": ev}})
    db.cal_organizers.delete_many({"id": {"$in": org}})
    if ids["rv"] is None:
        db.cal_settings.update_one({"id": "main"}, {"$unset": {"rv": ""}})
    else:
        db.cal_settings.update_one({"id": "main"}, {"$set": {"rv": ids["rv"]}})
    print("cleaned", len(ev), "events", len(org), "orgs")
