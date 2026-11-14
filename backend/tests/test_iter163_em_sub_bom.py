# Iter 163: Event Map annual org subscription (marketplace price/checkout/stripe), video groups lifecycle
# (free regenerations, first-download confirm/final, SA unlock/restore), aid-pause timing, Event Planner BOM (API + exports + dup + cross-org).
# Creates TEST_ orgs and deletes them at the end (and expires Stripe test checkout sessions).
import io
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
import stripe
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
SA = ("manara.michele.pro@gmail.com", "CrmEvent2026!")
PW = "TestIter163!"
GPX = open(os.path.join(os.path.dirname(__file__), "fixtures", "hill_aid.gpx"), "rb").read()
mdb = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[os.environ.get("DB_NAME", "test_database")]
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
ST = {"sessions": []}
BILL = {"tipo": "azienda", "paese": "IT", "ragione_sociale": "TEST_Srl", "partita_iva": "01234567890", "indirizzo": "Via Roma 1", "cap": "20100",
        "citta": "Milano", "provincia": "MI", "codice_sdi": "0000000", "email_fatturazione": "test_bill@example.com"}


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return s


def _wait(s, vid, timeout=400):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = s.get(f"{API}/eventmap/videos/{vid}").json()
        if v["status"] in ("completed", "error"):
            return v
        time.sleep(4)
    raise AssertionError("video timeout")


def _mkorg(sa, plan, tag):
    s = requests.Session()
    em = f"test_i163_{tag}_{uuid.uuid4().hex[:6]}@example.com"
    name = f"TEST_I163 {tag} {uuid.uuid4().hex[:4]}"
    r = s.post(f"{API}/auth/register-organization", json={"nome": "TEST", "cognome": "I163", "email": em, "password": PW, "org_name": name,
                                                          "telefono": "+393471234567", "accept_terms": True})
    assert r.status_code in (200, 201), r.text
    oid = s.get(f"{API}/auth/me").json()["org_id"]
    evs = [s.post(f"{API}/events", json={"nome": f"TEST_I163 Ev {i}", "data_inizio": "2026-12-13"}).json()["id"] for i in range(2)]  # trial: before plan limits
    assert sa.put(f"{API}/platform/saas/orgs/{oid}/admin", json={"plan": plan, "status": "active"}).status_code == 200
    return s, oid, name, evs


@pytest.fixture(scope="module")
def sa():
    return _login(*SA)


@pytest.fixture(scope="module")
def orgs(sa):
    out = {"bronze": _mkorg(sa, "bronze", "br"), "silver": _mkorg(sa, "silver", "si")}
    json.dump({k: {"oid": v[1], "name": v[2]} for k, v in out.items()}, open("/tmp/i163_orgs.json", "w"))
    yield out
    for sid in ST["sessions"]:
        try:
            stripe.checkout.Session.expire(sid)
        except Exception as e:
            print("expire", sid, e)
    if os.environ.get("KEEP_ORG"):
        return
    for _, oid, name, _ in out.values():
        print("cleanup", oid, sa.delete(f"{API}/platform/organizations/{oid}", json={"confirm_name": name}).status_code)


# --- Marketplace / subscription ---
def test_summary_bronze(orgs):
    s = orgs["bronze"][0]
    d = s.get(f"{API}/addons/eventmap").json()
    print({k: d.get(k) for k in ("included", "included_free", "yearly_price", "videos_per_year", "sale_open", "packages")})
    assert d["yearly_price"] == 29.0 and d["sale_open"] and d["videos_per_year"] == 1 and d["packages"] == [] and d["included_free"] == 0


def test_summary_silver_included(orgs):
    d = orgs["silver"][0].get(f"{API}/addons/eventmap").json()
    assert d["included"] == 1 and d["included_free"] == 1, d


def test_checkout_subscription(orgs):
    s, oid, _, evs = orgs["bronze"]
    r = s.post(f"{API}/addons/eventmap/checkout", json={"origin_url": BASE_URL})
    if r.status_code == 400 and "fatturazione" in r.text:
        assert s.put(f"{API}/account/billing", json=BILL).status_code == 200
        r = s.post(f"{API}/addons/eventmap/checkout", json={"origin_url": BASE_URL})
    assert r.status_code == 200 and r.json()["checkout_url"].startswith("https://checkout.stripe.com"), r.text
    g = mdb.addon_grants.find_one({"org_id": oid, "product": "eventmap", "status": "pending"})
    sess = stripe.checkout.Session.retrieve(g["stripe_session_id"], expand=["line_items"])
    ST["sessions"].append(sess.id)
    li = sess.line_items.data[0].price
    print("mode", sess.mode, "price", li.id, li.unit_amount, li.recurring)
    assert sess.mode == "subscription" and li.unit_amount == 2900 and li.recurring.interval == "year" and li.recurring.interval_count == 1
    r2 = s.post(f"{API}/addons/eventmap/checkout", json={"origin_url": BASE_URL})
    assert r2.status_code == 200
    g2 = mdb.addon_grants.find_one({"org_id": oid, "product": "eventmap", "status": "pending"})
    ST["sessions"].append(g2["stripe_session_id"])
    assert g2["stripe_price_id"] == li.id
    svc = mdb.marketplace_services.find_one({"key": "event-map"})
    mode = next(iter(svc["eventmap_prices"]))
    assert svc["eventmap_prices"][mode]["yearly"]["price_id"] == li.id
    # pending -> no rights
    st = s.get(f"{API}/eventmap/events/{evs[0]}").json()
    assert st["rights"]["active"] is False


def test_activation_all_events(orgs):
    s, oid, _, evs = orgs["bronze"]
    mdb.addon_grants.insert_one({"id": uuid.uuid4().hex, "org_id": oid, "product": "eventmap", "scope": "org", "source": "purchase", "status": "active",
                                 "events_total": 0, "videos_total": 1, "videos_per_year": 1, "formats": [], "cycle": "yearly", "price": 29.0,
                                 "package_name": "Abbonamento annuale", "event_id": None, "activated_at": datetime.now(timezone.utc).isoformat(),
                                 "expires_at": (datetime.now(timezone.utc) + timedelta(days=365)).isoformat(), "created_at": datetime.now(timezone.utc).isoformat()})
    for e in evs:
        rg = s.get(f"{API}/eventmap/events/{e}").json()["rights"]
        assert rg["active"] is True and rg["videos_remaining"] == 1, rg
    r = s.post(f"{API}/addons/eventmap/checkout", json={"origin_url": BASE_URL})
    assert r.status_code == 400 and "già attivo" in r.text


# --- Video lifecycle ---
def test_race_and_timing(orgs):
    s, oid, _, evs = orgs["bronze"]
    r = s.post(f"{API}/eventmap/events/{evs[0]}/tracks", files={"file": ("hill_aid.gpx", io.BytesIO(GPX), "application/gpx+xml")})
    assert r.status_code in (200, 201), r.text
    tid = r.json().get("id") or r.json().get("track", {}).get("id")
    races = s.post(f"{API}/eventmap/events/{evs[0]}/races/from-tracks").json()["created"]
    rid = races[0]["id"]
    ST.update(tid=tid, rid=rid)
    aids = [{"name": "Ristoro A", "km": 0.5, "desc": "Acqua e sali"}, {"name": "Ristoro B", "km": 1.0, "desc": ""}, {"name": "Ristoro C", "km": 1.5, "desc": ""}]
    assert s.put(f"{API}/eventmap/tracks/{tid}/aid-stations", json={"items": aids}).status_code == 200
    t = s.put(f"{API}/eventmap/races/{rid}", json={"duration": 15, "aid_pause": 3, "format": "1:1"}).json()["timing"]
    print("timing 15s", t)
    assert t["ok"] is False and t["suggest"] == 30 and t["pause_s"] == 9.0
    t = s.put(f"{API}/eventmap/races/{rid}", json={"duration": 30}).json()["timing"]
    assert t["ok"] is True
    t = s.put(f"{API}/eventmap/races/{rid}", json={"aid_pause": 0, "duration": 15}).json()["timing"]
    assert t["ok"] is True and t["pause_s"] == 0
    assert s.put(f"{API}/eventmap/races/{rid}", json={"aid_pause": 11}).status_code == 422
    s.put(f"{API}/eventmap/races/{rid}", json={"aid_pause": 2, "aid_pause_auto": True})
    r = s.post(f"{API}/eventmap/races/{rid}/preview")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and r.content[:2] == b"\xff\xd8"


def test_video_group_lifecycle(orgs, sa):
    s, oid, _, evs = orgs["bronze"]
    rid = ST["rid"]
    v1 = s.post(f"{API}/eventmap/races/{rid}/videos").json()
    gid = v1["group_id"]
    ST.update(gid=gid, v1=v1["id"])
    g = mdb.eventmap_video_groups.find_one({"id": gid})
    assert g["status"] == "modificabile" and g["credit_consumed"] is False
    assert _wait(s, v1["id"])["status"] == "completed"
    u = mdb.addon_usage.find_one({"org_id": oid, "product": "eventmap"})
    assert u["videos_used"] == 1
    assert s.get(f"{API}/eventmap/events/{evs[0]}").json()["rights"]["videos_remaining"] == 0
    # v2 free
    s.put(f"{API}/eventmap/races/{rid}", json={"style": "streets"})
    r = s.post(f"{API}/eventmap/video-groups/{gid}/versions", json={"race_id": rid})
    assert r.status_code == 200, r.text
    v2 = r.json()
    assert v2["version"] == 2
    assert s.get(f"{API}/eventmap/events/{evs[0]}").json()["rights"]["videos_remaining"] == 0
    assert _wait(s, v2["id"])["status"] == "completed"
    assert mdb.addon_usage.find_one({"org_id": oid, "product": "eventmap"})["videos_used"] == 1
    ST["v2"] = v2["id"]
    # a new group requires a credit (none left)
    r = s.post(f"{API}/eventmap/races/{rid}/videos")
    assert r.status_code == 403, r.text
    # first download confirm
    r = s.get(f"{API}/eventmap/videos/{v2['id']}/file", params={"download": 1})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "confirm_first_download"
    assert s.get(f"{API}/eventmap/videos/{v2['id']}/file").status_code == 200  # inline playback does not finalize
    assert mdb.eventmap_video_groups.find_one({"id": gid})["status"] == "modificabile"
    r = s.get(f"{API}/eventmap/videos/{v2['id']}/file", params={"download": 1, "confirm": 1})
    assert r.status_code == 200 and len(r.content) > 10000
    g = mdb.eventmap_video_groups.find_one({"id": gid})
    assert g["status"] == "definitivo" and g["first_download"]["version_id"] == v2["id"] and g["first_download"]["version"] == 2 and g["first_download"]["by"]
    r = s.post(f"{API}/eventmap/video-groups/{gid}/versions", json={"race_id": rid})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "video_final"
    assert s.get(f"{API}/eventmap/videos/{v1['id']}/file", params={"download": 1}).status_code == 200  # re-download allowed
    assert s.post(f"{API}/eventmap/video-groups/{gid}/unlock").status_code == 403
    st = s.get(f"{API}/eventmap/events/{evs[0]}").json()
    assert any(x["id"] == gid and x["status"] == "definitivo" for x in st["groups"])


def test_sa_unlock_restore(orgs, sa):
    s, oid, _, evs = orgs["bronze"]
    h = {"X-Org-Id": oid}
    gid = ST["gid"]
    r = sa.post(f"{API}/eventmap/video-groups/{gid}/restore/{ST['v1']}", headers=h)
    assert r.status_code == 200 and r.json()["current_version_id"] == ST["v1"], r.text
    r = sa.post(f"{API}/eventmap/video-groups/{gid}/unlock", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "modificabile"
    r = sa.get(f"{API}/eventmap/videos/{ST['v1']}/file", params={"download": 1}, headers=h)
    assert r.status_code == 200
    assert mdb.eventmap_video_groups.find_one({"id": gid})["status"] == "modificabile"  # SA download does not finalize
    actions = [x["action"] for x in mdb.eventmap_video_groups.find_one({"id": gid})["history"]]
    print("history", actions)
    assert "ripristino" in actions and "sblocco" in actions and "primo download" in actions


def test_legacy_migration_and_cross_org(orgs):
    s2 = orgs["silver"][0]
    assert s2.get(f"{API}/eventmap/videos/{ST['v1']}/file").status_code == 404
    assert s2.post(f"{API}/eventmap/video-groups/{ST['gid']}/versions", json={"race_id": ST["rid"]}).status_code == 404
    assert mdb.eventmap_videos.count_documents({"group_id": {"$exists": False}}) == 0


# --- Event Planner BOM ---
LINE = [[10.4000, 43.7000], [10.4000, 43.700179]]  # ~19.9 m -> 10 pieces


def _features():
    gz = {"properties": {"id": "f1", "categoria": "Strutture", "nome": "Gazebo 3×3 m", "tipo": "box", "center": [10.4, 43.7], "larghezza": 3, "lunghezza": 3, "quantita": 2}}
    gz2 = {"properties": {"id": "f2", "categoria": "Strutture", "nome": "Gazebo 3×3 m", "tipo": "box", "center": [10.401, 43.7], "larghezza": 3, "lunghezza": 3, "quantita": 3}}
    tr = {"properties": {"id": "f3", "categoria": "Viabilità", "nome": "Transenne (2 m)", "tipo": "line", "passo": 2}, "geometry": {"type": "LineString", "coordinates": LINE}}
    return [gz, gz2, tr]


def test_bom_flow(orgs, sa):
    s, oid, _, evs = orgs["silver"]
    r = sa.post(f"{API}/platform/addons/orgs/{oid}/grants", json={"product": "planner", "source": "superadmin", "scope": "org", "events_total": 1})
    assert r.status_code in (200, 201), r.text
    eid = evs[0]
    p = s.post(f"{API}/planner/events/{eid}/projects", json={"nome": "TEST_Progetto A"}).json()
    pid = p["id"]
    ST.update(pid=pid, peid=eid)
    full = s.get(f"{API}/planner/projects/{pid}").json()
    assert s.put(f"{API}/planner/projects/{pid}/content", json={"version": full["version"], "features": _features(), "layers": full["layers"]}).status_code == 200
    b = s.get(f"{API}/planner/projects/{pid}/bom").json()
    rows = {x["key"]: x for x in b["rows"]}
    print({k: (v["map_qty"], v["total"]) for k, v in rows.items()})
    gk = "Strutture|Gazebo 3×3 m"
    assert rows[gk]["map_qty"] == 5 and rows["Viabilità|Transenne (2 m)"]["map_qty"] == 10
    # edit row
    r = s.put(f"{API}/planner/projects/{pid}/bom/rows/{gk}", json={"adjust": -7, "code": "GZ33", "supplier": "TEST_Forn", "notes": "A & B <x>", "status": "ordinato"})
    assert r.status_code == 200
    rows = {x["key"]: x for x in s.get(f"{API}/planner/projects/{pid}/bom").json()["rows"]}
    assert rows[gk]["total"] == 0 and rows[gk]["code"] == "GZ33" and rows[gk]["status"] == "ordinato" and len(rows) == 2
    assert s.put(f"{API}/planner/projects/{pid}/bom/rows/{gk}", json={"status": "boh"}).status_code == 400
    s.put(f"{API}/planner/projects/{pid}/bom/rows/{gk}", json={"adjust": 1})
    # manual
    b = s.post(f"{API}/planner/projects/{pid}/bom/manual", json={"categoria": "Altro", "description": "TEST_Nastro", "adjust": 4}).json()
    man = [x for x in b["rows"] if x["source"] == "manual"]
    assert len(man) == 1 and man[0]["total"] == 4
    mid = man[0]["key"][2:]
    b = s.post(f"{API}/planner/projects/{pid}/bom/manual", json={"description": "TEST_Del"}).json()
    did = [x for x in b["rows"] if x["description"] == "TEST_Del"][0]["key"][2:]
    b = s.delete(f"{API}/planner/projects/{pid}/bom/manual/{did}").json()
    assert not any(x["description"] == "TEST_Del" for x in b["rows"])
    # components
    comps = {"items": [{"description": "Struttura", "qty": 1}, {"description": "Zavorra", "qty": 4}, {"description": "Copertura", "qty": 1}]}
    b = s.put(f"{API}/planner/projects/{pid}/bom/components/{gk}", json=comps).json()
    cr = [x for x in b["rows"] if x.get("parent") == gk]
    assert sorted(x["map_qty"] for x in cr) == [5, 5, 20] and not any(x["key"] == gk for x in b["rows"])
    ST["mid"] = mid


def test_bom_event_summary_exports_dup(orgs):
    s, oid, _, evs = orgs["silver"]
    pid, eid = ST["pid"], ST["peid"]
    d = s.post(f"{API}/planner/events/{eid}/projects", json={"nome": "TEST_Progetto B", "duplica_da": pid}).json()
    b1, b2 = s.get(f"{API}/planner/projects/{pid}/bom").json()["rows"], s.get(f"{API}/planner/projects/{d['id']}/bom").json()["rows"]
    assert len(b1) == len(b2)
    s.put(f"{API}/planner/projects/{d['id']}/bom/rows/m:{ST['mid']}", json={"adjust": 10})
    assert [x for x in s.get(f"{API}/planner/projects/{pid}/bom").json()["rows"] if x["key"] == f"m:{ST['mid']}"][0]["total"] == 4
    ev = s.get(f"{API}/planner/events/{eid}/bom").json()
    assert len(ev["projects"]) == 2
    nastro = [x for x in ev["rows"] if x["description"] == "TEST_Nastro"][0]
    assert nastro["total"] == 14 and nastro["by_project"][pid] == 4 and nastro["by_project"][d["id"]] == 10
    from openpyxl import load_workbook
    for url in (f"{API}/planner/projects/{pid}/bom/export.xlsx", f"{API}/planner/events/{eid}/bom/export.xlsx"):
        r = s.get(url)
        assert r.status_code == 200, (url, r.text[:200])
        ws = load_workbook(io.BytesIO(r.content)).active
        print(url[-30:], [c.value for c in ws[2]], [c.value for c in ws[3]])
    ws = load_workbook(io.BytesIO(s.get(f"{API}/planner/projects/{pid}/bom/export.xlsx").content)).active
    assert ws["G3"].value == "=MAX(0,E3+F3)"
    for url in (f"{API}/planner/projects/{pid}/bom/export.pdf", f"{API}/planner/events/{eid}/bom/export.pdf?inline=1"):
        r = s.get(url)
        print(url[-35:], r.status_code, r.headers.get("content-disposition"), r.text[:150] if r.status_code != 200 else "")
        assert r.status_code == 200 and r.content[:4] == b"%PDF"
    open("/tmp/i163_bom.pdf", "wb").write(s.get(f"{API}/planner/projects/{pid}/bom/export.pdf").content)


def test_bom_cross_org(orgs):
    s = orgs["bronze"][0]
    pid, eid = ST["pid"], ST["peid"]
    for u in (f"/planner/projects/{pid}/bom", f"/planner/events/{eid}/bom", f"/planner/projects/{pid}/bom/export.xlsx"):
        assert s.get(f"{API}{u}").status_code in (403, 404), u
    assert s.put(f"{API}/planner/projects/{pid}/bom/rows/x", json={"adjust": 1}).status_code in (403, 404)
    assert s.post(f"{API}/planner/projects/{pid}/bom/manual", json={}).status_code in (403, 404)
