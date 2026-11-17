# UI setup helper for iteration 172 (Phase 4): sector+post with phones/coords, persona resource + invite, alta intervention with coords assigned. Usage: python ui_cr172_setup.py setup|cleanup
import json, sys, os
import requests
sys.path.insert(0, os.path.dirname(__file__))
from cr_ids import login, ids, API  # noqa

I = ids()
A, _ = login("test_cr_a@crmevent-test.it")
OPS = f"{API}/controlroom/events/{I['ev_a']}/ops"
F = "/tmp/cr172.json"

if sys.argv[1] == "setup":
    out = {"ev": I["ev_a"], "made": []}
    def mk(kind, body):
        r = A.post(f"{OPS}/{kind}", json=body); assert r.status_code == 200, r.text
        out["made"].append([kind, r.json()["id"]]); return r.json()
    st = A.get(OPS).json()
    out["routes"] = len(st.get("routes") or [])
    sec = mk("sectors", {"nome": "TEST_UI172 Settore", "km_inizio": 0, "km_fine": 5, "responsabile": "TEST Capo Settore", "telefono": "+39 333 1110001"})
    post = mk("posts", {"nome": "TEST_UI172 Post", "previsti": 2, "km": 1, "sector_id": sec["id"], "lng": 12.4964, "lat": 41.9028, "responsabile": "TEST Capo Post", "telefono": "+39 333 1110002"})
    res = mk("resources", {"kind": "persona", "nome": "TEST_UI172 Op", "post_id": post["id"]})
    A.post(f"{OPS}/resources/{res['id']}/presence", json={"presente": True})
    inv = A.post(f"{OPS}/invites", json={"resource_id": res["id"], "days": 1}).json()
    it = A.post(f"{OPS}/interventions", json={"tipologia": "sanitario", "priorita": "alta", "descrizione": "TEST_UI172 alta", "lng": 12.4975, "lat": 41.9035}).json()
    A.post(f"{OPS}/interventions/{it['id']}/assign", json={"resource_ids": [res["id"]]})
    out.update(post=post["id"], res=res["id"], inv=inv["id"], tok=inv["token"], itv=[it["id"], it["codice"]])
    json.dump(out, open(F, "w")); print(json.dumps(out))
else:
    out = json.load(open(F))
    iid = out["itv"][0]
    it = next(i for i in A.get(OPS).json()["interventions"] if i["id"] == iid)
    if it["stato"] not in ("chiuso", "annullato"):
        print(A.post(f"{OPS}/interventions/{iid}/status", json={"to": "annullato", "motivo": "TEST cleanup", "force": True, "note": "cleanup", "version": it["version"]}).status_code)
    A.delete(f"{OPS}/invites/{out['inv']}")
    for kind, oid in reversed(out["made"]):
        print(kind, A.delete(f"{OPS}/{kind}/{oid}").status_code)
