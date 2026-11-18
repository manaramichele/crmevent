# Helper for UI retest of planner water fixes: `seed` links 3 buoys to the TEST_NUOTO route; `show` prints route coords + buoy links. Usage: python water_ui_helper.py seed|show <email> <eid>
import os, sys, json, requests
API = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/") + "/api"
cmd, email, eid = sys.argv[1:4]
s = requests.Session(); s.post(f"{API}/auth/login", json={"email": email, "password": "TestPlanner2026!"})
pid = next(p["id"] for p in s.get(f"{API}/planner/events/{eid}/projects").json()["projects"] if p["nome"] == "TEST_NUOTO")
pr = s.get(f"{API}/planner/projects/{pid}").json()
route = next(f for f in pr["features"] if f["properties"].get("disciplina"))
if cmd == "seed":
    lb = next(l["id"] for l in pr["layers"] if l["nome"].startswith("Boe"))
    feats = [f for f in pr["features"] if f["properties"].get("categoria") != "Boe"]
    for i in range(3):
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": route["geometry"]["coordinates"][i]},
                      "properties": {"id": f"TESTb{i}", "tipo": "point", "nome": "Boa di virata", "categoria": "Boe", "numero": i + 1, "layer_id": lb, "link_route": route["properties"]["id"], "link_idx": i}})
    r = s.put(f"{API}/planner/projects/{pid}/content", json={"version": pr["version"], "features": feats, "layers": pr["layers"]})
    print("seed", r.status_code)
print(json.dumps({"route": route["properties"]["id"], "coords": [[round(c[0], 6), round(c[1], 6)] for c in route["geometry"]["coordinates"]],
                  "buoys": [{"id": f["properties"]["id"], "c": [round(x, 6) for x in f["geometry"]["coordinates"]], "link_route": f["properties"].get("link_route"), "link_idx": f["properties"].get("link_idx"), "numero": f["properties"].get("numero")}
                            for f in pr["features"] if f["properties"].get("categoria") == "Boe"]}, indent=None))
