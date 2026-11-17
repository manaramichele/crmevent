"""Seed dimostrativo Control Room su evento Demo (Bologna City Run, org Demo). Nessun dato personale reale."""
import json
import sys
import urllib.request

API = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0] + "/api"
ORG, EV = "b7f40862230441b9a0bedabefe8dab49", "demo_evt_bcr"
TOKEN = sys.argv[1]


def call(method, path, body=None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {TOKEN}", "X-Org-Id": ORG, "Content-Type": "application/json", "User-Agent": "Mozilla/5.0 crmevent-seed"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read() or b"{}")


B = f"/controlroom/events/{EV}/ops"
st = call("GET", f"/controlroom/events/{EV}/status")
if not st.get("active"):
    print(call("POST", f"/platform/orgs/{ORG}/modules/controlroom/grant", {"event_ids": [EV], "note": "Video dimostrativo Control Room"}))
rt = call("GET", B + "/route")["route"]
import math
route = rt["coordinates"] if rt else [[11.3426 + 0.028 * math.sin(2 * math.pi * k / 200) * (1 + 0.3 * math.cos(6 * math.pi * k / 200)), 44.4938 + 0.018 * (1 - math.cos(2 * math.pi * k / 200))] for k in range(201)]
n = len(route)
pt = lambda f: route[min(n - 1, int(n * f))]
sectors = [call("POST", B + "/sectors", {"nome": nome, "codice": c, "km_inizio": a, "km_fine": b, "colore": col})["id"]
           for nome, c, a, b, col in [("Partenza e centro storico", "S1", 0, 7, "#0ABAB5"), ("Colli e Giardini", "S2", 7, 14, "#F59E0B"), ("Rientro e arrivo", "S3", 14, 21.1, "#6366F1")]]
posts = []
for i, (nome, cat, f) in enumerate([("Partenza · Piazza Maggiore", "partenza", 0.0), ("Ristoro km 5", "ristoro", 0.24), ("Postazione volontari km 8", "volontari", 0.38),
                                    ("Presidio sanitario km 10", "sanitario", 0.48), ("Ristoro km 15", "ristoro", 0.71), ("Arrivo · Piazza Maggiore", "arrivo", 0.99)]):
    lng, lat = pt(f)
    try:
        posts.append(call("POST", B + "/posts", {"nome": nome, "categoria": cat, "lng": lng, "lat": lat, "km": round(21.1 * f, 1), "sector_id": sectors[min(2, int(f * 3))]})["id"])
    except Exception:
        posts.append(call("POST", B + "/posts", {"nome": nome, "categoria": "volontari", "lng": lng, "lat": lat, "km": round(21.1 * f, 1), "sector_id": sectors[min(2, int(f * 3))]})["id"])
for kind, nome, tip, pi in [("squadra", "Squadra Ristoro A", "volontari", 1), ("squadra", "Squadra Ristoro B", "volontari", 4), ("persona", "Volontario Demo 1", "volontario", 2),
                            ("persona", "Volontario Demo 2", "volontario", 2), ("mezzo", "Ambulanza Demo 1", "ambulanza", 3), ("mezzo", "Moto staffetta Demo", "moto_org", 0),
                            ("persona", "Responsabile Demo Arrivo", "staff", 5), ("squadra", "Team Accoglienza Demo", "staff", 0)]:
    call("POST", B + "/resources", {"kind": kind, "nome": nome, "tipologia": tip, "post_id": posts[pi]})
lng, lat = pt(0.5)
print(call("POST", B + "/interventions", {"titolo": "Simulazione · richiesta acqua al km 10", "priorita": "normale", "descrizione": "Intervento dimostrativo per il video", "lng": lng, "lat": lat, "km": 10.5}).get("codice"))
print("ok", len(posts))
