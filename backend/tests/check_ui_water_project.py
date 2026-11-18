# Inspect the UI-created TEST_NUOTO project: persisted props + exports (manual check helper, not a pytest module).
import io, os, requests
from openpyxl import load_workbook
API = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/") + "/api"
s = requests.Session(); s.post(f"{API}/auth/login", json={"email": "test_nuoto_ui_90c17b@example.com", "password": "TestPlanner2026!"})
eid = "4dd9f4d11acb47a59a82642bc757fdab"
ps = s.get(f"{API}/planner/events/{eid}/projects").json()["projects"]
pid = next(p["id"] for p in ps if p["nome"] == "TEST_NUOTO")
pr = s.get(f"{API}/planner/projects/{pid}").json()
for f in pr["features"]:
    p = f["properties"]
    keys = {k: p.get(k) for k in ["nome", "categoria", "numero", "dimensione", "colore", "responsabile", "cellulare", "funzione", "area_competenza", "gps_device", "link_route", "link_idx", "riservato", "disciplina", "giri", "frecce"] if p.get(k) not in (None, "")}
    print(keys)
for pub in ["false", "true"]:
    r = s.get(f"{API}/planner/projects/{pid}/export/boe.xlsx", params={"pubblico": pub})
    rows = list(load_workbook(io.BytesIO(r.content)).active.iter_rows(values_only=True))
    print("XLSX pubblico", pub, r.status_code); [print("  ", x) for x in rows]
    g = s.get(f"{API}/planner/projects/{pid}/export/gpx", params={"pubblico": pub})
    print("GPX", pub, g.status_code, g.text.count("<trk>"), "trk", g.text.count("<wpt"), "wpt")
    k = s.get(f"{API}/planner/projects/{pid}/export/kml", params={"pubblico": pub})
    print("KML", pub, k.status_code, k.text.count("<Placemark>"), "placemarks; Gommone" , "Gommone" in k.text, "Rotta", "Rotta" in k.text)
    pdf = s.get(f"{API}/planner/projects/{pid}/export/boe.pdf", params={"pubblico": pub})
    print("PDF", pub, pdf.status_code, pdf.content[:4])
cr = s.get(f"{API}/controlroom/events/{eid}/ops/planner")
print("CR", cr.status_code, cr.text[:200])
