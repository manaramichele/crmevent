# UI fixture for Marketing → Home Page carousel tests: `python ui_homepage_setup.py setup N|cleanup`
import io, json, os, sys, uuid
import requests
from PIL import Image
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env"); load_dotenv("/app/backend/.env")
API = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/") + "/api"
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
STATE = "/tmp/ui_homepage_state.json"
COLORS = ["red", "blue", "green", "orange", "purple", "teal", "navy", "olive", "maroon", "gold", "pink", "gray", "brown", "black"]
SIZES = [(400, 400), (1600, 400), (300, 900)]


def login(email, pwd):
    s = requests.Session(); r = s.post(f"{API}/auth/login", json={"email": email, "password": pwd}); assert r.status_code == 200, r.text
    s.headers["Authorization"] = f"Bearer {s.cookies.get('access_token')}"; return s


def setup(n):
    tag = uuid.uuid4().hex[:5]; email = f"test_hpui_{tag}@crmevent-test.it"
    r = requests.post(f"{API}/auth/register-organization", json={"nome": "TEST", "cognome": "HPUI", "email": email, "password": "TestHP2026!",
                                                                 "org_name": f"TEST_HPUI Org {tag}", "telefono": "+393331234567", "accept_terms": True})
    assert r.status_code == 200, r.text
    u = mdb.users.find_one({"email": email}, {"_id": 0, "user_id": 1, "org_id": 1})
    adm = login(email, "TestHP2026!"); sa = login("manara.michele.pro@gmail.com", "CrmEvent2026!")
    st = {"email": email, "uid": u["user_id"], "oid": u["org_id"], "events": [], "files": [], "tag": tag}
    for i in range(n):
        w, h = SIZES[i % 3]; b = io.BytesIO(); Image.new("RGB", (w, h), COLORS[i % len(COLORS)]).save(b, "PNG")
        f = adm.post(f"{API}/upload", files={"file": (f"l{i}.png", b.getvalue(), "image/png")}).json(); st["files"].append(f["id"])
        nome = f"{'abcdefghijklmn'[i]}{'' if i % 2 else 'X'} TEST_{tag}"
        e = adm.post(f"{API}/events", json={"nome": nome.capitalize() if i % 2 else nome, "logo_url": f["url"]}).json(); st["events"].append(e["id"])
        if i < n - 1:
            sa.post(f"{API}/homepage/logos/{e['id']}", json={"status": "approved"})
    json.dump(st, open(STATE, "w")); print(json.dumps(st))


def cleanup():
    st = json.load(open(STATE)); adm = login(st["email"], "TestHP2026!")
    for eid in st["events"]:
        adm.delete(f"{API}/events/{eid}"); mdb.homepage_logo_cache.delete_one({"_id": eid})
    for fid in st["files"]:
        mdb.files.delete_one({"id": fid})
    mdb.users.delete_one({"user_id": st["uid"]}); mdb.organizations.delete_one({"id": st["oid"]})
    mdb.subscriptions.delete_many({"org_id": st["oid"]}); mdb.memberships.delete_many({"user_id": st["uid"]})
    sa = login("manara.michele.pro@gmail.com", "CrmEvent2026!")
    print(sa.put(f"{API}/homepage/settings", json={"carousel_enabled": True, "carousel_title": "Scelto dai migliori organizzatori di eventi", "auto_new": False}).json())


if __name__ == "__main__":
    setup(int(sys.argv[2])) if sys.argv[1] == "setup" else cleanup()
