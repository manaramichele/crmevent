# UI setup helper for retest 171: creates TEST resource+invite and interventions in several states. Usage: python ui_cr171_setup.py setup|cleanup
import json, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from test_controlroom_phase3_itv import _login, OPS, itv  # noqa

A = _login("test_cr_a@crmevent-test.it")
F = "/tmp/cr171.json"


def st(iid, to, **kw):
    r = A.post(f"{OPS}/interventions/{iid}/status", json={"to": to, "version": itv(A, iid)["version"], **kw})
    assert r.status_code == 200, r.text


if sys.argv[1] == "setup":
    rid = A.post(f"{OPS}/resources", json={"kind": "persona", "nome": "TEST_UI171 Op"}).json()["id"]
    inv = A.post(f"{OPS}/invites", json={"resource_id": rid, "days": 1}).json()
    out = {"rid": rid, "inv": inv["id"], "tok": inv["token"], "itvs": {}}
    for name in ("seg_radio", "seg_nc", "sul_posto", "closed", "presa"):
        r = A.post(f"{OPS}/interventions", json={"tipologia": "sanitario", "priorita": "alta", "descrizione": f"TEST_UI171 {name}", "riferimento": "TEST bivio"}).json()
        iid = r["id"]
        out["itvs"][name] = [iid, r["codice"]]
        A.post(f"{OPS}/interventions/{iid}/assign", json={"resource_ids": [rid]})
    A.post(f"{OPS}/interventions/{out['itvs']['seg_radio'][0]}/assignments/{rid}/confirm", json={"via": "radio"})
    for to in ("preso_in_carico", "squadra_inviata", "sul_posto"):
        st(out["itvs"]["sul_posto"][0], to)
    st(out["itvs"]["presa"][0], "preso_in_carico")
    for to in ("preso_in_carico", "squadra_inviata", "sul_posto", "risolto", "chiuso"):
        st(out["itvs"]["closed"][0], to)
    json.dump(out, open(F, "w"))
    print(json.dumps(out))
else:
    out = json.load(open(F))
    for iid, _ in out["itvs"].values():
        it = itv(A, iid)
        if it["stato"] not in ("chiuso", "annullato"):
            A.post(f"{OPS}/interventions/{iid}/status", json={"to": "annullato", "motivo": "TEST cleanup", "force": True, "note": "cleanup", "version": it["version"]})
    A.delete(f"{OPS}/invites/{out['inv']}")
    print(A.delete(f"{OPS}/resources/{out['rid']}").status_code)
