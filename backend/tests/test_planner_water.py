# Event Planner · nuoto/triathlon: library categories+tags, default layers, export GPX/KML/boe.pdf/boe.xlsx (pubblico filter), Control Room planner list.
# Creates a TEST_ org (gold) with an event + planner add-on and deletes it at the end.
import io
import math
import os
import uuid

import pytest
import requests
from pymongo import MongoClient

mdb = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[os.environ.get("DB_NAME", "test_database")]
API = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/") + "/api"
SA_EMAIL, SA_PW = "manara.michele.pro@gmail.com", "CrmEvent2026!"
PW = "TestPlanner2026!"


def _login(email, pw):
    s = requests.Session()
    assert s.post(f"{API}/auth/login", json={"email": email, "password": pw}).status_code == 200
    return s


@pytest.fixture(scope="module")
def ctx():
    sa = _login(SA_EMAIL, SA_PW)
    s = requests.Session()
    name = f"TEST_NUOTO Org {uuid.uuid4().hex[:4]}"
    email = f"test_nuoto_{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{API}/auth/register-organization", json={"nome": "TEST", "cognome": "NUOTO", "email": email, "password": PW, "org_name": name,
                                                          "telefono": "+393471234567", "accept_terms": True})
    assert r.status_code in (200, 201), r.text
    me = s.get(f"{API}/auth/me").json()
    oid = me["org_id"]
    assert sa.put(f"{API}/platform/saas/orgs/{oid}/admin", json={"plan": "gold", "status": "active"}).status_code == 200
    eid = s.post(f"{API}/events", json={"nome": f"{name} Triathlon", "data_inizio": "2026-12-13"}).json()["id"]
    assert s.post(f"{API}/addons/planner/events/{eid}/activate").status_code == 200
    mdb.controlroom_purchases.insert_one({"id": "TEST_" + uuid.uuid4().hex, "org_id": oid, "event_id": eid, "status": "active", "test": True})
    yield {"sa": sa, "s": s, "oid": oid, "eid": eid, "email": email, "pw": PW}
    mdb.controlroom_purchases.delete_many({"org_id": oid, "event_id": eid, "test": True})
    sa.delete(f"{API}/platform/organizations/{oid}", json={"confirm_name": name})
    u = mdb.users.find_one({"email": email})
    if u:
        sa.delete(f"{API}/platform/users/{u.get('user_id') or u.get('id')}")


def d(a, b):
    R = 6371008.8
    la1, la2 = math.radians(a[1]), math.radians(b[1])
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(math.radians(b[0] - a[0]) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def test_library_has_water_categories(ctx):
    r = ctx["s"].get(f"{API}/planner/config")
    assert r.status_code == 200, r.text
    items = r.json()["library"]
    cats = {}
    for it in items:
        cats.setdefault(it.get("categoria"), []).append(it)
    assert len(cats.get("Boe", [])) == 12
    assert len(cats.get("Mezzi nautici", [])) == 15
    names = {i.get("nome") for i in items}
    for n in ["Bagnino", "Defibrillatore", "Zona pericolosa", "Corrente", "Scogli", "Acque basse", "Ostacolo", "Zona interdetta", "Rotta di navigazione",
              "Via di evacuazione", "Zona cambio T1", "Zona cambio T2", "Bike In", "Bike Out", "Run In", "Run Out", "Gazebo 3×3 m", "Ambulanza", "Transenne (2 m)"]:
        assert n in names, n
    ctx["lib"] = items


def test_project_create_has_nautical_layers(ctx):
    s = ctx["s"]
    r = s.post(f"{API}/planner/events/{ctx['eid']}/projects", json={"nome": "TEST_NUOTO"})
    assert r.status_code in (200, 201), r.text
    p = r.json()
    ctx["pid"] = p["id"]
    full = s.get(f"{API}/planner/projects/{p['id']}").json()
    names = [l["nome"] for l in full["layers"]]
    for n in ["Boe e segnaletica nautica", "Mezzi nautici", "Transizioni"]:
        assert n in names
    ctx["proj"] = full


def _save(ctx, features):
    s, pid = ctx["s"], ctx["pid"]
    cur = s.get(f"{API}/planner/projects/{pid}").json()
    r = s.put(f"{API}/planner/projects/{pid}/content", json={"version": cur["version"], "features": features, "layers": cur["layers"]})
    assert r.status_code == 200, r.text
    return cur["layers"]


def test_gpx_without_routes_400(ctx):
    r = ctx["s"].get(f"{API}/planner/projects/{ctx['pid']}/export/gpx")
    assert r.status_code == 400
    assert "disciplina" in r.json()["detail"].lower()


def test_exports_with_data(ctx):
    layers = ctx["proj"]["layers"]
    lb = next(l["id"] for l in layers if l["nome"].startswith("Boe"))
    lm = next(l["id"] for l in layers if l["nome"] == "Mezzi nautici")
    lp = next(l["id"] for l in layers if l["nome"] == "Percorsi")
    c0 = [12.0, 44.0]
    pts = [[12.0, 44.0], [12.003, 44.0], [12.0015, 44.002], [12.0, 44.0]]
    feats = [
        {"type": "Feature", "geometry": {"type": "LineString", "coordinates": pts}, "properties": {"id": "r1", "tipo": "line", "nome": "Nuoto 750", "layer_id": lp, "disciplina": "nuoto", "giri": 2}},
        {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[12.01, 44.0], [12.05, 44.0]]}, "properties": {"id": "r2", "tipo": "line", "nome": "Bici", "layer_id": lp, "disciplina": "ciclismo"}},
    ]
    for i in range(3):
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": pts[i]}, "properties": {"id": f"b{i}", "tipo": "point", "nome": "Boa di virata", "categoria": "Boe",
                      "numero": i + 1, "layer_id": lb, "link_route": "r1", "link_idx": i, "colore": "#F97316", "responsabile": "Mario"}})
    feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [12.002, 44.001]}, "properties": {"id": "b9", "tipo": "point", "nome": "Boa segreta", "categoria": "Boe",
                  "numero": 9, "layer_id": lb, "riservato": True}})
    feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [12.004, 44.003]}, "properties": {"id": "bi", "tipo": "point", "nome": "Boa indipendente", "categoria": "Boe",
                  "numero": 20, "layer_id": lb}})
    feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [12.0012, 44.0012]}, "properties": {"id": "bag", "tipo": "point", "nome": "Bagnino", "categoria": "Mezzi nautici", "layer_id": lm}})
    feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [12.0013, 44.0013]}, "properties": {"id": "def", "tipo": "point", "nome": "Defibrillatore", "categoria": "Sicurezza", "layer_id": lm}})
    feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [12.0014, 44.0014]}, "properties": {"id": "sup", "tipo": "point", "nome": "SUP", "categoria": "Mezzi nautici", "layer_id": lm}})
    feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [12.001, 44.001]}, "properties": {"id": "m1", "tipo": "point", "nome": "Gommone di soccorso", "categoria": "Mezzi nautici",
                  "layer_id": lm, "responsabile": "Luca", "gps_device": "X1"}})
    _save(ctx, feats)
    s, pid = ctx["s"], ctx["pid"]
    # GPX
    r = s.get(f"{API}/planner/projects/{pid}/export/gpx")
    assert r.status_code == 200 and "<trk>" in r.text and "Boa segreta" in r.text
    assert "Bici" not in r.text  # only nuoto routes when present
    r = s.get(f"{API}/planner/projects/{pid}/export/gpx", params={"pubblico": "true"})
    assert r.status_code == 200 and "Boa segreta" not in r.text
    # KML
    r = s.get(f"{API}/planner/projects/{pid}/export/kml")
    assert r.status_code == 200 and "<kml" in r.text and "Bici" in r.text and "Nuoto 750" in r.text
    # XLSX rows
    r = s.get(f"{API}/planner/projects/{pid}/export/boe.xlsx")
    assert r.status_code == 200
    from openpyxl import load_workbook
    ws = load_workbook(io.BytesIO(r.content)).active
    rows = list(ws.iter_rows(values_only=True))
    assert rows[0][0] == "N."
    body = rows[1:]
    print(body)
    assert len(body) == 5
    nums = [x[0] for x in body]
    # independent buoys: own count (first has empty da_precedente, progressive 0)
    ind = [x for x in body if x[1] in ("Boa indipendente", "Boa segreta")]
    assert ind[0][6] in (None, "") and ind[0][7] == 0, ind
    assert ind[1][7] == ind[1][6] and ind[1][6] > 0, ind
    assert nums[:3] == [1, 2, 3]
    assert body[1][6] == round(d(pts[0], pts[1]))
    assert body[2][7] == round(d(pts[0], pts[1]) + d(pts[1], pts[2]))
    r = s.get(f"{API}/planner/projects/{pid}/export/boe.xlsx", params={"pubblico": "true"})
    rows = list(load_workbook(io.BytesIO(r.content)).active.iter_rows(values_only=True))
    assert len(rows) == 5 and all(x[1] != "Boa segreta" for x in rows)
    # PDF
    r = s.get(f"{API}/planner/projects/{pid}/export/boe.pdf", params={"pubblico": "false"})
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    r = s.get(f"{API}/planner/projects/{pid}/export/xyz")
    assert r.status_code == 400
    ctx["exported"] = True


def test_controlroom_planner_list(ctx):
    r = ctx["s"].get(f"{API}/controlroom/events/{ctx['eid']}/ops/planner")
    assert r.status_code == 200, r.text
    projs = r.json()["projects"]
    pr = next(p for p in projs if p["id"] == ctx["pid"])
    m = next(f for f in pr["features"] if f["id"] == "m1")
    print(m)
    assert m.get("posizione") == "pianificata"
    assert "gps_reale" in m and m["gps_reale"] is None
    b = next(f for f in pr["features"] if f["id"] == "b0")
    assert b.get("posizione") == "pianificata"
    for f in pr["features"]:
        assert f["posizione"] == "pianificata" and f["gps_reale"] is None and f["gps_ultimo_aggiornamento"] is None and "gps_device" in f
    assert m["gps_device"] == "X1"
    sug = {f["id"]: f["suggested"] for f in pr["features"]}
    print(sug)
    for k in ("m1", "bag", "def"):
        assert sug[k] == "sanitario", (k, sug)
    assert sug["b0"] == "controllo" and sug["sup"] == "controllo", sug


def test_export_cross_org_forbidden(ctx):
    sa = ctx["sa"]
    r = requests.get(f"{API}/planner/projects/{ctx['pid']}/export/kml")
    assert r.status_code in (401, 403)
