# Iteration 207: Da classificare delete/restore + Copertura only confirmed Staff/Volontari (TEST_DcOrg)
import os, uuid, pytest, requests
from pymongo import MongoClient

B = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
EV1 = "59cced67e8d84c7caef5d0436d072ef8"
EV2 = "72bd01373a3441e2b78b69a92b127530"
ORG = "42744eae0ca84875b89d86a80e7bd985"
DAY = "2026-12-20"


def _env():
    d = {}
    for l in open("/app/backend/.env"):
        if "=" in l:
            k, v = l.strip().split("=", 1); d[k] = v.strip('"')
    return d


E = _env()
mdb = MongoClient(E["MONGO_URL"])[E["DB_NAME"]]


@pytest.fixture(scope="module")
def adm():
    s = requests.Session()
    r = s.post(f"{B}/api/auth/login", json={"email": "test_dc_3e68a3@example.com", "password": "TestPass123!"})
    if r.status_code != 200:
        pytest.skip("org admin login failed")
    return s


@pytest.fixture(scope="module")
def sa():
    s = requests.Session()
    r = s.post(f"{B}/api/auth/login", json={"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"})
    if r.status_code != 200:
        pytest.skip("superadmin login failed")
    s.headers["X-Org-Id"] = ORG
    return s


CREATED = {"persons": [], "staff": []}


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    # delete only what we created (by id), incl. any deleted_requests copies
    for pid in CREATED["persons"]:
        mdb.staff.delete_many({"org_id": ORG, "persona_id": pid})
        mdb.availabilities.delete_many({"org_id": ORG, "persona_id": pid})
        mdb.persons.delete_many({"org_id": ORG, "id": pid})
        mdb.deleted_requests.delete_many({"org_id": ORG, "persona_id": pid})


def mk_person(s, tag):
    r = s.post(f"{B}/api/persons", json={"nome": tag, "cognome": f"TEST_{tag}{uuid.uuid4().hex[:4]}", "email": f"test_{uuid.uuid4().hex[:8]}@example.com"})
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]; CREATED["persons"].append(pid)
    return r.json()


def mk_link(s, pid, ev, cat, stato="confermato"):
    r = s.post(f"{B}/api/staff", json={"persona_id": pid, "evento_id": ev, "categoria": cat, "stato": stato})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def set_avail(s, pid, ev, fasce):
    r = s.put(f"{B}/api/persons/{pid}/availability/{ev}", json={"days": [{"date": DAY, "fasce": fasce}]})
    assert r.status_code == 200, r.text


def fx(s, ev=EV1):
    r = s.get(f"{B}/api/staff-coverage/fasce", params={"evento_id": ev})
    assert r.status_code == 200, r.text
    return r.json()


def ids_in(rows, fascia, date=DAY):
    row = next(x for x in rows["rows"] if x["date"] == date and x["fascia"] == fascia)
    return {p["id"] for p in row["people"]}, row


# Coverage: lifecycle da_classificare -> volontario confermato -> rinunciato -> da_classificare
def test_coverage_only_confirmed(adm):
    p = mk_person(adm, "CovA")
    lid = mk_link(adm, p["id"], EV1, "da_classificare", "confermato")
    set_avail(adm, p["id"], EV1, ["mattina", "pomeriggio"])
    m, _ = ids_in(fx(adm), "mattina")
    assert p["id"] not in m
    r = adm.put(f"{B}/api/staff/{lid}", json={"categoria": "volontario", "stato": "confermato"}); assert r.status_code == 200, r.text
    d = fx(adm); m, row = ids_in(d, "mattina"); pm, _ = ids_in(d, "pomeriggio")
    assert p["id"] in m and p["id"] in pm
    r = adm.put(f"{B}/api/staff/{lid}", json={"stato": "rinunciato"}); assert r.status_code == 200
    m, _ = ids_in(fx(adm), "mattina"); assert p["id"] not in m
    r = adm.put(f"{B}/api/staff/{lid}", json={"categoria": "staff", "stato": "confermato"}); assert r.status_code == 200
    m, _ = ids_in(fx(adm), "mattina"); assert p["id"] in m
    r = adm.put(f"{B}/api/staff/{lid}", json={"categoria": "da_classificare"}); assert r.status_code == 200
    m, _ = ids_in(fx(adm), "mattina"); assert p["id"] not in m


# Seed people: Da classificare/unconfirmed never in coverage or legacy list
def test_seed_not_in_coverage(adm):
    d = fx(adm)
    all_ids = set().union(*[{p["id"] for p in r["people"]} for r in d["rows"]])
    leg = {x["id"] for x in d.get("legacy") or []}
    for pid in ("89be8a2ffe8e49a7a2c9d32e144e3247", "368c331177b7437ba7edd169cb05f390", "f9c0fed32d4b4a09b130b83ce95a3cb8"):
        assert pid not in all_ids and pid not in leg


# Delete: 404 when no Da classificare request
def test_delete_404(adm):
    r = adm.post(f"{B}/api/da-classificare/delete", json={"persona_id": "ab323fbf35ab451198ad0ff30d4209c0", "evento_id": EV1})
    assert r.status_code == 404
    r = adm.post(f"{B}/api/da-classificare/delete", json={"persona_id": "nope", "evento_id": EV1})
    assert r.status_code == 404


# Delete person also confirmed on EV2: person kept, EV2 coverage intact
def test_delete_keeps_other_event(adm):
    p = mk_person(adm, "Two")
    mk_link(adm, p["id"], EV1, "da_classificare")
    mk_link(adm, p["id"], EV2, "volontario", "confermato")
    d2 = fx(adm, EV2)
    days2 = [r["date"] for r in d2["rows"]]
    if days2:
        r = adm.put(f"{B}/api/persons/{p['id']}/availability/{EV2}", json={"days": [{"date": days2[0], "fasce": ["mattina", "pomeriggio"]}]})
        assert r.status_code == 200
    before = set().union(*[{x["id"] for x in r["people"]} for r in fx(adm, EV2)["rows"]]) if days2 else set()
    r = adm.post(f"{B}/api/da-classificare/delete", json={"persona_id": p["id"], "evento_id": EV1})
    assert r.status_code == 200 and r.json()["person_deleted"] is False
    pe = {x["id"]: x for x in adm.get(f"{B}/api/persons-enriched").json()}
    assert p["id"] in pe
    assert [a["evento_id"] for a in pe[p["id"]]["assegnazioni"]] == [EV2]
    after = set().union(*[{x["id"] for x in r["people"]} for r in fx(adm, EV2)["rows"]]) if days2 else set()
    assert before == after
    if days2:
        assert p["id"] in after


# Delete orphan person -> person removed; superadmin list + restore; audit
def test_delete_restore_superadmin(adm, sa):
    p = mk_person(adm, "Solo")
    mk_link(adm, p["id"], EV1, "da_classificare")
    set_avail(adm, p["id"], EV1, ["mattina"])
    r = adm.post(f"{B}/api/da-classificare/delete", json={"persona_id": p["id"], "evento_id": EV1})
    assert r.status_code == 200 and r.json()["person_deleted"] is True
    batch = r.json()["batch_id"]
    assert p["id"] not in {x["id"] for x in adm.get(f"{B}/api/persons-enriched").json()}
    assert adm.get(f"{B}/api/admin/deleted-requests").status_code == 403
    assert adm.post(f"{B}/api/admin/deleted-requests/{batch}/restore").status_code == 403
    lst = sa.get(f"{B}/api/admin/deleted-requests")
    assert lst.status_code == 200, lst.text
    b = next(x for x in lst.json() if x["batch_id"] == batch)
    assert set(b["items"]) >= {"staff", "persons", "availabilities"}
    assert b["evento_nome"] == "TEST_Ev Dc"
    r = sa.post(f"{B}/api/admin/deleted-requests/{batch}/restore"); assert r.status_code == 200
    pe = {x["id"]: x for x in adm.get(f"{B}/api/persons-enriched").json()}
    assert pe[p["id"]]["is_da_classificare"] is True
    assert mdb.availabilities.find_one({"org_id": ORG, "persona_id": p["id"]})
    assert sa.post(f"{B}/api/admin/deleted-requests/{batch}/restore").status_code == 404
    acts = {a["action"] for a in mdb.audit_logs.find({"org_id": ORG, "meta.batch_id": batch})} if "audit_logs" in mdb.list_collection_names() else set()
    if not acts:
        for c in mdb.list_collection_names():
            if "audit" in c:
                acts |= {a["action"] for a in mdb[c].find({"org_id": ORG, "meta.batch_id": batch})}
    assert {"da_classificare_deleted", "da_classificare_restored"} <= acts


# Org isolation: superadmin with another org cannot see TEST_DcOrg deletions
def test_isolation(adm):
    r = adm.post(f"{B}/api/da-classificare/delete", json={"persona_id": "89be8a2ffe8e49a7a2c9d32e144e3247", "evento_id": "doesnotexist"})
    assert r.status_code == 404
