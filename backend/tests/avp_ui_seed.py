# Iteration 152 UI seed: creates a TEST org for UI checks; `python avp_ui_seed.py cleanup` removes it
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
from avp_helpers import setup_org, cleanup

F = "/tmp/avp_ui.json"
if len(sys.argv) > 1 and sys.argv[1] == "cleanup":
    d = json.load(open(F)); cleanup(d["org_id"], d["email"]); print("cleaned", d["org_id"])
else:
    c = setup_org(); c.pop("s"); json.dump(c, open(F, "w")); print(json.dumps(c))
