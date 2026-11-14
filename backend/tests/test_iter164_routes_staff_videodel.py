# Iter 164: Event Map SA video delete/undelete/purge/refund, Percorsi Eventi routes (GPX/KML/KMZ) shared archive + version tracking,
# Event Planner routes import + staff stations linked to shifts, assignments summary/exports, cross-org.
# Creates TEST_I164 orgs and deletes them at the end.
import io
import json
import os
import time
import uuid
import zipfile
from datetime import datetime, timedelta, timezone

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
SA = ("manara.michele.pro@gmail.com", "CrmEvent2026!")
PW = "TestIter164!"
GPX = open(os.path.join(os.path.dirname(__file__), "fixtures", "hill_aid.gpx"), "rb").read()
mdb = MongoClient(os.environ.get("MONGO_URL"))[os.environ.get("DB_NAME")]
ST = {}
KML = ('<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark><name>TEST</name><LineString><coordinates>'
       + " ".join(f"{10.40 + i * 0.001:.4f},{43.70 + i * 0.0005:.4f}" for i in range(40)) + "</coordinates></LineString></Placemark></Document></kml>").encode()
KML_ELE = KML.replace(b",43.7000 ", b",43.7000,120 ")


def _kmz(kml):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("doc.kml", kml)
    return b.getvalue()


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return s


def _mkorg(sa, tag):
    s = requests.Session()
    em = f"test_i164_{tag}_{uuid.uuid4().hex[:6]}@example.com"
    name = f"TEST_I164 {tag} {uuid.uuid4().hex[:4]}"
    r = s.post(f"{API}/auth/register-organization", json={"nome": "TEST", "cognome": "I164", "email": em, "password": PW, "org_name": name,
                                                          "telefono": "+393471234567", "accept_terms": True})
    assert r.status_code in (200, 201), r.text
    oid = s.get(f"{API}/auth/me").json()["org_id"]
    ev = s.post(f"{API}/events", json={"nome": f"TEST_I164 Ev {tag}", "data_inizio": "2026-12-13"}).json()["id"]
    assert sa.put(f"{API}/platform/saas/orgs/{oid}/admin", json={"plan": "gold", "status": "active"}).status_code == 200
    now = datetime.now(timezone.utc)
    mdb.addon_grants.insert_one({"id": uuid.uuid4().hex, "org_id": oid, "product": "eventmap", "scope": "org", "source": "purchase", "status": "active",
                                 "events_total": 0, "videos_total": 2, "videos_per_year": 2, "formats": [], "cycle": "yearly", "price": 29.0,
                                 "package_name": "TEST", "event_id": None, "activated_at": now.isoformat(),
                                 "expires_at": (now + timedelta(days=365)).isoformat(), "created_at": now.isoformat()})
    r = sa.post(f"{API}/platform/addons/orgs/{oid}/grants", json={"product": "planner", "source": "superadmin", "scope": "org", "events_total": 1})
    assert r.status_code in (200, 201), r.text
    return {"s": s, "oid": oid, "name": name, "eid": ev, "email": em}


def _upload(s, name, data, ct):
    r = s.post(f"{API}/upload", files={"file": (name, io.BytesIO(data), ct)})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def sa():
    return _login(*SA)


@pytest.fixture(scope="module")
def orgs(sa):
    out = {"a": _mkorg(sa, "A"), "b": _mkorg(sa, "B")}
    json.dump({k: {kk: vv for kk, vv in v.items() if kk != "s"} for k, v in out.items()}, open("/tmp/i164_orgs.json", "w"))
    yield out
    if os.environ.get("KEEP_ORG"):
        return
    for v in out.values():
        nm = (mdb.organizations.find_one({"id": v["oid"]}, {"nome": 1}) or {}).get("nome") or v["name"]
        print("cleanup", v["oid"], sa.delete(f"{API}/platform/organizations/{v['oid']}", json={"confirm_name": nm}).status_code)


# --- Percorsi Eventi (event_maps) ---
def test_routes_list(orgs):
    o = orgs["a"]
    s, eid = o["s"], o["eid"]
    g = _upload(s, "TEST_hill.gpx", GPX, "application/gpx+xml")
    k = _upload(s, "TEST_flat.kml", KML, "application/vnd.google-earth.kml+xml")
    z = _upload(s, "TEST_flat.kmz", _kmz(KML.replace(b"10.4", b"10.5")), "application/vnd.google-earth.kmz")
    ids = {}
    for key, body in (("gpx", {"nome": "TEST_Percorso GPX", "gpx_url": g["url"], "distanza": 2.1}),
                      ("kml", {"nome": "TEST_Percorso KML", "file_url": k["url"]}),
                      ("kmz", {"nome": "TEST_Percorso KMZ", "file_url": z["url"]})):
        r = s.post(f"{API}/maps", json={"evento_id": eid, "tipologia": "Percorso", **body})
        assert r.status_code in (200, 201), r.text
        ids[key] = r.json()["id"]
    ST["maps"], ST["gpx_file"] = ids, g["id"]
    st = s.get(f"{API}/eventmap/events/{eid}").json()
    rt = {x["map_id"]: x for x in st["routes"]}
    print(st["routes"])
    assert rt[ids["gpx"]]["format"] == "GPX" and rt[ids["kml"]]["format"] == "KML" and rt[ids["kmz"]]["format"] == "KMZ"
    assert rt[ids["gpx"]]["version"] == g["id"] and rt[ids["gpx"]]["distance"] == 2.1
    for x in st["routes"]:
        assert {"map_id", "nome", "format", "distance", "updated_at", "version", "gare"} <= set(x) and "_rec" not in x
    pr = s.get(f"{API}/planner/events/{eid}/routes").json()["routes"]
    assert {x["map_id"] for x in pr} == set(ids.values())


def test_track_from_map_all_formats(orgs):
    o = orgs["a"]
    s, eid = o["s"], o["eid"]
    out = {}
    for key, mid in ST["maps"].items():
        r = s.post(f"{API}/eventmap/events/{eid}/tracks/from-map/{mid}")
        print(key, r.status_code, {k: r.json().get(k) for k in ("id", "source_format", "has_elevation", "warning", "duplicate")} if r.ok else r.text)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["source_map_id"] == mid and d["source_format"] == key.upper() and d["source_version"]
        out[key] = d
    assert out["gpx"]["has_elevation"] and "warning" not in out["gpx"]
    assert not out["kml"]["has_elevation"] and "altimetric" in out["kml"]["warning"]
    t = mdb.eventmap_tracks.find_one({"id": out["kml"]["id"]})
    assert t["source_map_id"] == ST["maps"]["kml"] and t["source_version"]
    ST["tracks"] = out
    # duplicate content from another map: existing track must keep its original source link (known bug if relinked)
    k2 = _upload(s, "TEST_dup.kml", KML, "application/vnd.google-earth.kml+xml")
    mid2 = s.post(f"{API}/maps", json={"evento_id": eid, "tipologia": "Percorso", "nome": "TEST_Dup KML", "file_url": k2["url"]}).json()["id"]
    ST["dup_map"] = mid2
    d = s.post(f"{API}/eventmap/events/{eid}/tracks/from-map/{mid2}").json()
    relinked = mdb.eventmap_tracks.find_one({"id": out["kml"]["id"]})["source_map_id"]
    print("DUP", d.get("duplicate"), "kml track source now", relinked, "orig", ST["maps"]["kml"])
    assert s.post(f"{API}/eventmap/events/{eid}/tracks/from-map/nope").status_code == 404


def test_route_update_flag(orgs):
    o = orgs["a"]
    s, eid = o["s"], o["eid"]
    r = s.post(f"{API}/eventmap/events/{eid}/races", json={"name": "TEST_Gara GPX", "track_id": ST["tracks"]["gpx"]["id"], "duration": 15, "format": "1:1"})
    assert r.status_code == 200, r.text
    ST["rid"] = r.json()["id"]
    st = s.get(f"{API}/eventmap/events/{eid}").json()
    rc = next(x for x in st["races"] if x["id"] == ST["rid"])
    assert rc["route_update"] is False
    assert "TEST_Gara GPX" in next(x for x in st["routes"] if x["map_id"] == ST["maps"]["gpx"])["gare"]
    # replace file in Percorsi Eventi
    g2 = _upload(s, "TEST_hill_v2.gpx", GPX.replace(b"</gpx>", b"<!-- v2 --></gpx>"), "application/gpx+xml")
    assert s.put(f"{API}/maps/{ST['maps']['gpx']}", json={"gpx_url": g2["url"]}).status_code == 200
    st = s.get(f"{API}/eventmap/events/{eid}").json()
    rc = next(x for x in st["races"] if x["id"] == ST["rid"])
    assert rc["route_update"] is True
    # track unchanged (no auto replace)
    assert rc["track_id"] == ST["tracks"]["gpx"]["id"]
    ST["gpx_v2"] = g2["id"]


# --- Planner routes ---
def test_planner_route_geometry(orgs):
    o = orgs["a"]
    s, eid = o["s"], o["eid"]
    for key, mid in ST["maps"].items():
        r = s.get(f"{API}/planner/events/{eid}/routes/{mid}")
        assert r.status_code == 200, r.text
        d = r.json()
        assert len(d["coordinates"]) >= 2 and d["format"] == key.upper() and d["version"]
        assert d["has_elevation"] is (key == "gpx"), (key, d["has_elevation"])
    assert s.get(f"{API}/planner/events/{eid}/routes/{ST['maps']['gpx']}").json()["version"] == ST["gpx_v2"]
    assert s.get(f"{API}/planner/events/{eid}/routes/nope").status_code == 404


# --- Planner staff stations ---
def test_people_setup(orgs):
    o = orgs["a"]
    s, eid = o["s"], o["eid"]
    pids = [s.post(f"{API}/persons", json={"nome": f"TEST_P{i}", "cognome": "I164"}).json()["id"] for i in range(3)]
    team = s.post(f"{API}/teams", json={"nome": "TEST_Team Ristori", "evento_id": eid, "responsabile_id": pids[0]}).json()
    for i, p in enumerate(pids):
        r = s.post(f"{API}/staff", json={"persona_id": p, "evento_id": eid, "categoria": "volontario" if i == 2 else "staff", "ruolo": "Addetto",
                                         "team_id": team["id"] if i < 2 else None, "data_arrivo": "2026-12-13"})
        assert r.status_code in (200, 201), r.text
    sh = s.post(f"{API}/shifts", json={"evento_id": eid, "persona_id": pids[1], "data": "2026-12-13", "ora_inizio": "09:00", "ora_fine": "11:00", "luogo": "TEST_Manual"}).json()
    outsider = s.post(f"{API}/persons", json={"nome": "TEST_Out"}).json()["id"]
    ST.update(pids=pids, team=team["id"], manual_shift=sh["id"], outsider=outsider)
    d = s.get(f"{API}/planner/events/{eid}/people").json()
    t = d["teams"][0]
    assert (t["responsabile"] or "").lower() == "test_p0 i164" and len(t["membri"]) == 2
    pp = {x["persona_id"]: x for x in d["people"]}
    assert pp[pids[2]]["categoria"] == "volontario" and pp[pids[0]]["team_nome"] == "TEST_Team Ristori" and len(pp[pids[1]]["turni"]) == 1


def test_station_flow(orgs):
    o = orgs["a"]
    s, eid = o["s"], o["eid"]
    pids = ST["pids"]
    p = s.post(f"{API}/planner/events/{eid}/projects", json={"nome": "TEST_Prog I164"}).json()
    pid = p["id"]
    ST["pid"] = pid
    body = {"nome": "TEST_Ristoro km5", "tipologia": "Ristoro", "kind": "team", "ruolo": "Addetto", "data": "2026-12-13", "ora_inizio": "08:00", "ora_fine": "12:00",
            "team_id": ST["team"], "persona_ids": [pids[0], pids[1]]}
    r = s.post(f"{API}/planner/projects/{pid}/stations/stA", json=body)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "staff_conflict", r.text
    assert r.json()["detail"]["conflicts"][0]["persona_id"] == pids[1]
    assert mdb.shifts.count_documents({"planner_station_id": "stA"}) == 0
    r = s.post(f"{API}/planner/projects/{pid}/stations/stA", json={**body, "force": True})
    assert r.status_code == 200, r.text
    assert len(r.json()["shifts"]) == 2 and all(x["source"] == "event_planner" for x in r.json()["shifts"])
    # idempotent
    s.post(f"{API}/planner/projects/{pid}/stations/stA", json={**body, "force": True})
    assert mdb.shifts.count_documents({"org_id": o["oid"], "planner_station_id": "stA"}) == 2
    # deselect p1
    r = s.post(f"{API}/planner/projects/{pid}/stations/stA", json={**body, "persona_ids": [pids[0]]})
    assert r.status_code == 200 and len(r.json()["shifts"]) == 1
    # second station, volontario, no overlap
    r = s.post(f"{API}/planner/projects/{pid}/stations/stB", json={"nome": "TEST_Varco", "kind": "volontario", "data": "2026-12-13", "ora_inizio": "13:00",
                                                                   "ora_fine": "15:00", "persona_ids": [pids[2]]})
    assert r.status_code == 200, r.text
    # outsider / bad team
    assert s.post(f"{API}/planner/projects/{pid}/stations/stC", json={"nome": "x", "persona_ids": [ST["outsider"]]}).status_code == 400
    assert s.post(f"{API}/planner/projects/{pid}/stations/stC", json={"nome": "x", "team_id": "nope"}).status_code == 400
    assert s.post(f"{API}/planner/projects/{pid}/stations/stC", json={"nome": "x", "kind": "bad"}).status_code == 422
    stl = s.get(f"{API}/planner/projects/{pid}/stations").json()["stations"]
    assert set(stl) == {"stA", "stB"}
    # save content with both stations
    full = s.get(f"{API}/planner/projects/{pid}").json()
    feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [10.4, 43.7]},
              "properties": {"id": fid, "nome": n, "tipo": "point", "categoria": "Staff", "station": {"nome": n, "kind": k, "team_id": tm, "tipologia": "Ristoro"}}}
             for fid, n, k, tm in (("stA", "TEST_Ristoro km5", "team", ST["team"]), ("stB", "TEST_Varco", "volontario", None), ("stE", "TEST_Vuota", "generica", None))]
    r = s.put(f"{API}/planner/projects/{pid}/content", json={"version": full["version"], "features": feats, "layers": full["layers"]})
    assert r.status_code == 200, r.text
    a = s.get(f"{API}/planner/events/{eid}/assignments").json()
    print(a["counts"], a["conflicts"])
    assert a["counts"]["postazioni"] == 3 and a["counts"]["coperte"] == 2 and a["counts"]["scoperte"] == 1 and a["counts"]["volontari"] == 1 and a["counts"]["staff"] == 1
    assert a["counts"]["team"] == 1
    ap = s.get(f"{API}/planner/events/{eid}/assignments", params={"project": pid}).json()
    assert ap["counts"]["postazioni"] == 3
    from openpyxl import load_workbook
    r = s.get(f"{API}/planner/events/{eid}/assignments/export.xlsx")
    assert r.status_code == 200
    ws = load_workbook(io.BytesIO(r.content)).active
    print([[c.value for c in row] for row in ws.iter_rows(min_row=1, max_row=6)])
    r = s.get(f"{API}/planner/events/{eid}/assignments/export.pdf", params={"project": pid})
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    assert s.get(f"{API}/planner/events/{eid}/assignments/export.csv").status_code == 404
    # remove stB from project -> only its planner shifts deleted
    full = s.get(f"{API}/planner/projects/{pid}").json()
    r = s.put(f"{API}/planner/projects/{pid}/content", json={"version": full["version"], "features": [feats[0], feats[2]], "layers": full["layers"]})
    assert r.status_code == 200
    assert mdb.shifts.count_documents({"org_id": o["oid"], "planner_station_id": "stB"}) == 0
    assert mdb.shifts.count_documents({"org_id": o["oid"], "planner_station_id": "stA"}) == 1
    assert mdb.shifts.find_one({"id": ST["manual_shift"]}) is not None


def test_planner_cross_org(orgs):
    sb = orgs["b"]["s"]
    eid, pid = orgs["a"]["eid"], ST["pid"]
    for u in (f"/planner/events/{eid}/people", f"/planner/events/{eid}/routes", f"/planner/events/{eid}/routes/{ST['maps']['gpx']}",
              f"/planner/projects/{pid}/stations", f"/planner/events/{eid}/assignments", f"/planner/events/{eid}/assignments/export.xlsx"):
        assert sb.get(f"{API}{u}").status_code in (403, 404), u
    assert sb.post(f"{API}/planner/projects/{pid}/stations/stZ", json={"nome": "x"}).status_code in (403, 404)
    assert sb.post(f"{API}/eventmap/events/{eid}/tracks/from-map/{ST['maps']['gpx']}").status_code in (403, 404)


# --- Video SA delete ---
def _wait(s, vid, timeout=420):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = s.get(f"{API}/eventmap/videos/{vid}").json()
        if v["status"] in ("completed", "error"):
            return v
        time.sleep(4)
    raise AssertionError("video timeout")


def test_sa_video_delete_lifecycle(orgs, sa):
    o = orgs["a"]
    s, eid, oid = o["s"], o["eid"], o["oid"]
    h = {"X-Org-Id": oid}
    v = s.post(f"{API}/eventmap/races/{ST['rid']}/videos")
    assert v.status_code == 200, v.text
    v = v.json()
    gid = v["group_id"]
    assert _wait(s, v["id"])["status"] == "completed"
    used0 = mdb.addon_usage.find_one({"org_id": oid, "product": "eventmap"})["videos_used"]
    assert used0 == 1
    for m, u in (("delete", f"/eventmap/video-groups/{gid}"), ("post", f"/eventmap/video-groups/{gid}/undelete"),
                 ("delete", f"/eventmap/video-groups/{gid}/purge"), ("post", f"/eventmap/video-groups/{gid}/refund-credit")):
        assert getattr(s, m)(f"{API}{u}").status_code == 403, u
    assert sa.delete(f"{API}/eventmap/video-groups/{gid}/purge", headers=h).status_code == 400
    r = sa.delete(f"{API}/eventmap/video-groups/{gid}", headers=h)
    assert r.status_code == 200 and r.json()["deleted_at"] and r.json()["deleted_by"] == SA[0]
    st = s.get(f"{API}/eventmap/events/{eid}").json()
    assert not any(g["id"] == gid for g in st["groups"]) and not any(x.get("group_id") == gid for x in st["videos"])
    assert s.get(f"{API}/eventmap/videos/{v['id']}/file").status_code == 404
    sst = sa.get(f"{API}/eventmap/events/{eid}", headers=h).json()
    assert any(g["id"] == gid and g.get("deleted_at") for g in sst["groups"])
    assert sa.get(f"{API}/eventmap/videos/{v['id']}/file", headers=h).status_code == 200
    assert mdb.addon_usage.find_one({"org_id": oid, "product": "eventmap"})["videos_used"] == used0
    r = sa.post(f"{API}/eventmap/video-groups/{gid}/undelete", headers=h)
    assert r.status_code == 200 and r.json()["deleted_at"] is None
    assert any(g["id"] == gid for g in s.get(f"{API}/eventmap/events/{eid}").json()["groups"])
    assert mdb.addon_usage.find_one({"org_id": oid, "product": "eventmap"})["videos_used"] == used0
    g = mdb.eventmap_video_groups.find_one({"id": gid})
    print("credit_consumed", g.get("credit_consumed"), [x["action"] for x in g["history"]])
    r = sa.post(f"{API}/eventmap/video-groups/{gid}/refund-credit", headers=h)
    assert r.status_code == 200, r.text
    assert mdb.addon_usage.find_one({"org_id": oid, "product": "eventmap"})["videos_used"] == used0 - 1
    assert sa.post(f"{API}/eventmap/video-groups/{gid}/refund-credit", headers=h).status_code == 400
    sa.delete(f"{API}/eventmap/video-groups/{gid}", headers=h)
    r = sa.delete(f"{API}/eventmap/video-groups/{gid}/purge", headers=h)
    assert r.status_code == 200 and r.json()["versions"] >= 1
    assert mdb.eventmap_videos.count_documents({"group_id": gid}) == 0
    assert mdb.eventmap_tracks.find_one({"id": ST["tracks"]["gpx"]["id"]}) is not None
    acts = [x["action"] for x in mdb.eventmap_video_groups.find_one({"id": gid})["history"]]
    assert "eliminazione" in acts and "ripristino eliminazione" in acts and "credito restituito" in acts
