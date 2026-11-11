# Iteration 153 UI seed: iter152 TEST org + P4 (volunteer linked to A and B, single pref ruoli[0] only on A). `cleanup` arg removes it
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
from avp_helpers import setup_org, cleanup, submit, BASE

F = "/tmp/avp_ui.json"
if len(sys.argv) > 1 and sys.argv[1] == "cleanup":
    d = json.load(open(F)); cleanup(d["org_id"], d["email"]); print("cleaned", d["org_id"])
else:
    c = setup_org(); s = c.pop("s"); t = c["tag"]
    submit(c["codes"]["A"], "TEST_Quattro", "Pref", f"test_p4_{t}@example.com", "3331000004", c["ruoli"][0])
    p4 = next(p for p in s.get(f"{BASE}/api/persons-enriched").json() if p["email"] == f"test_p4_{t}@example.com")["id"]
    c["pid"]["p4"] = p4
    c["staff4A"] = s.post(f"{BASE}/api/staff", json={"persona_id": p4, "evento_id": c["ev"]["A"], "categoria": "volontario"}).json()["id"]
    c["staff4B"] = s.post(f"{BASE}/api/staff", json={"persona_id": p4, "evento_id": c["ev"]["B"], "categoria": "volontario"}).json()["id"]
    json.dump(c, open(F, "w")); print(json.dumps(c))
