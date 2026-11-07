# Seed/cleanup of TEST_ data for the Calendario Italia Phase 3 (Brevo) UI test. Usage: python cal_brevo_ui_seed.py seed|cleanup
import json, os, sys
from datetime import date, timedelta
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env"); load_dotenv("/app/backend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api/platform/cal"
F = "/tmp/cal_brevo_ui_ids.json"
REG = "TEST_RegUI"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

if sys.argv[1] == "seed":
    s = requests.Session()
    s.post(f"{BASE}/api/auth/login", json={"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"}).raise_for_status()
    ids = {"orgs": [], "events": [], "tpl_before": [t["id"] for t in db.cal_templates.find({}, {"id": 1})],
           "settings": db.cal_settings.find_one({"id": "main"}, {"_id": 0})}
    d8 = (date.today() - timedelta(days=8)).isoformat()
    for nome, email, idoneo in [("TEST_UI3 Org Idoneo", "test_ui3_ok@example.com", True), ("TEST_UI3 Org DaVerificare", "test_ui3_dv@example.com", False)]:
        o = s.post(f"{API}/organizers", json={"nome": nome, "email_organizzativa": email, "regione": REG}).json()
        ids["orgs"].append(o["id"])
        if idoneo:
            s.put(f"{API}/organizers/{o['id']}/privacy", json={"status": "idoneo", "fonte": "sito", "finalita": "B2B", "base_giuridica": "legittimo interesse"}).raise_for_status()
        e = s.post(f"{API}/events", json={"nome": nome.replace("Org", "Gara"), "data_inizio": d8, "stato": "conclusa", "regione": REG, "organizer_id": o["id"], "comune": "Testopoli"}).json()
        ids["events"].append(e.get("id") or e["event"]["id"])
    json.dump(ids, open(F, "w"))
    print(ids["orgs"], ids["events"])
else:
    ids = json.load(open(F))
    allids = ids["orgs"] + ids["events"]
    camps = [c["campaign_id"] for c in db.cal_comms.find({"org_id": {"$in": ids["orgs"]}}, {"campaign_id": 1})]
    print("hist", db.cal_history.delete_many({"entity_id": {"$in": allids}}).deleted_count)
    print("comms", db.cal_comms.delete_many({"org_id": {"$in": ids["orgs"]}}).deleted_count)
    print("camps", db.cal_campaigns.delete_many({"id": {"$in": camps}}).deleted_count)
    print("ev", db.cal_events.delete_many({"id": {"$in": ids["events"]}}).deleted_count)
    print("org", db.cal_organizers.delete_many({"id": {"$in": ids["orgs"]}}).deleted_count)
    print("tpl", db.cal_templates.delete_many({"id": {"$nin": ids["tpl_before"]}}).deleted_count)
    if ids["settings"]:
        db.cal_settings.replace_one({"id": "main"}, ids["settings"])
