# UI seed: GOLD TEST_ org with 1 activated Event Map event (1 video available). Saves to /tmp/em_rights_orgs.json for cleanup.
import json
import sys
sys.path.insert(0, "/app/backend/tests")
import test_eventmap_rights_iter as T

sa = T._login(T.SA_EMAIL, T.SA_PW)
s, oid, evs = T._org("uigold", "gold", sa, 2)
assert s.post(f"{T.API}/addons/eventmap/events/{evs[0]}/activate").status_code == 200
print(json.dumps(T.ORGS["uigold"]))
print(T._hub(s)["videos_available"], T._rights(s, evs[0]))
