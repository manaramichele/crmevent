# Setup/cleanup for Control Room UI tests: TEST_ org admin with 2 events + billing, plus a staff user. Usage: python ui_controlroom_setup.py [cleanup]
import os, sys, uuid, json, requests, bcrypt
from dotenv import load_dotenv; load_dotenv('/app/backend/.env'); load_dotenv('/app/frontend/.env')
from pymongo import MongoClient
db = MongoClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
if len(sys.argv) > 1 and sys.argv[1] == "cleanup":
    d = json.load(open("/tmp/ui_cr.json"))
    sa = requests.Session(); sa.post(f"{API}/auth/login", json={"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"})
    print("purchases", db.controlroom_purchases.delete_many({"org_id": d["org_id"]}).deleted_count)
    db.users.delete_one({"user_id": d["staff_uid"]})
    n = db.organizations.find_one({"id": d["org_id"]})["nome"]
    print(sa.delete(f"{API}/platform/organizations/{d['org_id']}", json={"confirm_name": n}).text)
    print("users", db.users.delete_many({"email": {"$in": [d["email"], d["staff_email"]]}}).deleted_count)
    sys.exit()
s = requests.Session(); em = f"test_crui_{uuid.uuid4().hex[:6]}@example.com"
s.post(f"{API}/auth/register-organization", json={"nome": "TEST", "cognome": "UI", "email": em, "password": "TestCr2026!",
       "org_name": "TEST_CRUI Org", "telefono": "+393471234567", "accept_terms": True})
me = s.get(f"{API}/auth/me").json(); oid = me.get("org_id") or me["user"]["org_id"]
evs = [s.post(f"{API}/events", json={"nome": f"TEST_CRUI_Gara{i}", "data_inizio": f"2026-12-1{i}"}).json()["id"] for i in (1, 2)]
print(s.put(f"{API}/account/billing", json={"tipo": "azienda", "paese": "IT", "ragione_sociale": "TEST_Srl", "partita_iva": "01234567890", "indirizzo": "Via Roma 1",
      "cap": "20100", "citta": "Milano", "provincia": "MI", "codice_sdi": "0000000"}).status_code)
se = f"test_crui_staff_{uuid.uuid4().hex[:6]}@example.com"; su = "user_test_" + uuid.uuid4().hex[:10]
db.users.insert_one({"user_id": su, "email": se, "name": "TEST Staff", "role": "staff", "auth_provider": "password", "org_id": oid, "active": True,
                     "password_hash": bcrypt.hashpw(b"TestCr2026!", bcrypt.gensalt()).decode()})
out = {"email": em, "org_id": oid, "events": evs, "staff_email": se, "staff_uid": su}
json.dump(out, open("/tmp/ui_cr.json", "w")); print(out)
