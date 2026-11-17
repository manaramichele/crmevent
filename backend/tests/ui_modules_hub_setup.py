# Setup/cleanup TEST_ org admin for modules hub UI checks + probe planner activate while disabled. Usage: setup|cleanup
import sys, json, uuid
sys.path.insert(0, "/app/backend/tests")
from test_modules_hub import _register, _login, API, SA_EMAIL, SA_PWD, mdb
F = "/tmp/mh173.json"
if sys.argv[1] == "setup":
    email, uid, oid = _register("ui")
    a = _login(email, "TestMH2026!")
    ev = a.post(f"{API}/events", json={"nome": "TEST_MH Evento", "data_inizio": "2026-06-01", "data_fine": "2026-06-01", "citta": "Milano"})
    print("event", ev.status_code, ev.text[:200])
    eid = ev.json().get("id")
    sa = _login(SA_EMAIL, SA_PWD, oid)
    print("disable planner", sa.post(f"{API}/platform/orgs/{oid}/modules/planner/state", json={"enabled": False}).status_code)
    print("org GET addons planner events", [(e["nome"], e.get("module_disabled")) for e in a.get(f"{API}/addons/planner").json().get("events", [])])
    r = a.post(f"{API}/addons/planner/events/{eid}/activate")
    print("ACTIVATE while disabled ->", r.status_code, r.text[:200])
    print("access", a.get(f"{API}/org/modules/access").json())
    print("enable planner", sa.post(f"{API}/platform/orgs/{oid}/modules/planner/state", json={"enabled": True}).status_code)
    json.dump({"email": email, "uid": uid, "oid": oid, "eid": eid}, open(F, "w")); print(json.load(open(F)))
else:
    d = json.load(open(F))
    for c, q in (("addon_activations", {"org_id": d["oid"]}), ("events", {"org_id": d["oid"]}), ("memberships", {"user_id": d["uid"]}), ("subscriptions", {"org_id": d["oid"]})):
        print(c, mdb[c].delete_many(q).deleted_count)
    print(mdb.users.delete_one({"user_id": d["uid"]}).deleted_count, mdb.organizations.delete_one({"id": d["oid"]}).deleted_count)
