# Iteration 208: restore no-duplicate (public form re-registration), bulk-fascia only confirmed Staff/Volontari, stato via PUT
import os, uuid, pytest, requests
from pymongo import MongoClient

B = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
EV1 = "59cced67e8d84c7caef5d0436d072ef8"
EV2 = "72bd01373a3441e2b78b69a92b127530"
ORG = "42744eae0ca84875b89d86a80e7bd985"
DAY = "2026-12-20"
E = {k: v.strip('"') for k, v in (l.strip().split("=", 1) for l in open("/app/backend/.env") if "=" in l)}
mdb = MongoClient(E["MONGO_URL"])[E["DB_NAME"]]
CREATED = []


@pytest.fixture(scope="module")
def adm():
    s = requests.Session()
    if s.post(f"{B}/api/auth/login", json={"email": "test_dc_3e68a3@example.com", "password": "TestPass123!"}).status_code != 200:
        pytest.skip("org admin login failed")
    return s


@pytest.fixture(scope="module")
def sa():
    s = requests.Session()
    if s.post(f"{B}/api/auth/login", json={"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"}).status_code != 200:
        pytest.skip("SA login failed")
    s.headers["X-Org-Id"] = ORG
    return s


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    for pid in CREATED:
        for c in ("staff", "availabilities", "deleted_requests"):
            mdb[c].delete_many({"org_id": ORG, "persona_id": pid})
        mdb.persons.delete_many({"org_id": ORG, "id": pid})


def mk_person(s, tag, email=None):
    r = s.post(f"{B}/api/persons", json={"nome": tag, "cognome": f"TEST_{tag}", "email": email or f"test_{uuid.uuid4().hex[:8]}@example.com"})
    assert r.status_code in (200, 201), r.text
    CREATED.append(r.json()["id"]); return r.json()


def mk_link(s, pid, ev, cat, stato="confermato", ruolo=""):
    r = s.post(f"{B}/api/staff", json={"persona_id": pid, "evento_id": ev, "categoria": cat, "stato": stato, "ruolo": ruolo})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def links(pid, ev):
    return list(mdb.staff.find({"org_id": ORG, "persona_id": pid, "evento_id": ev}, {"_id": 0}))


def public_submit(email, nome="Pub", cognome="TEST_Pub"):
    code = mdb.avail_links.find_one({"evento_id": EV1, "active": True})["code"]
    info = requests.get(f"{B}/api/public/availability/{code}").json()
    body = {"nome": nome, "cognome": cognome, "email": email, "cellulare": "+39 333 000" + uuid.uuid4().hex[:4].translate(str.maketrans("abcdef", "123456")),
            "data_nascita": "1990-01-01", "privacy": True, "preferenza_attivita": info["attivita_options"][0],
            "days": [{"date": DAY, "disponibile": True, "fasce": ["mattina"]}]}
    return requests.post(f"{B}/api/public/availability/{code}", json=body)


# Restore after re-registration via public form (same person kept because confirmed on EV2) -> exactly one link + one availability
def test_restore_no_duplicate_after_public_form(adm, sa):
    email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    p = mk_person(adm, "Rst", email)
    mk_link(adm, p["id"], EV1, "da_classificare", "da_contattare")
    mk_link(adm, p["id"], EV2, "volontario", "confermato")
    r = adm.put(f"{B}/api/persons/{p['id']}/availability/{EV1}", json={"days": [{"date": DAY, "fasce": ["mattina", "pomeriggio"]}]}); assert r.status_code == 200
    r = adm.post(f"{B}/api/da-classificare/delete", json={"persona_id": p["id"], "evento_id": EV1})
    assert r.status_code == 200 and r.json()["person_deleted"] is False
    batch = r.json()["batch_id"]
    assert links(p["id"], EV1) == []
    r = public_submit(email)
    assert r.status_code in (200, 201), r.text
    assert len(links(p["id"], EV1)) == 1, "public form should re-link same person by email"
    r = sa.post(f"{B}/api/admin/deleted-requests/{batch}/restore"); assert r.status_code == 200, r.text
    assert len(links(p["id"], EV1)) == 1
    assert mdb.availabilities.count_documents({"org_id": ORG, "persona_id": p["id"], "evento_id": EV1}) == 1
    assert mdb.deleted_requests.count_documents({"org_id": ORG, "batch_id": batch}) == 0


# Restore after re-linking via API (person kept) -> one link
def test_restore_no_duplicate_after_manual_link(adm, sa):
    p = mk_person(adm, "Rst2")
    mk_link(adm, p["id"], EV1, "da_classificare", "da_contattare")
    mk_link(adm, p["id"], EV2, "staff", "confermato")
    batch = adm.post(f"{B}/api/da-classificare/delete", json={"persona_id": p["id"], "evento_id": EV1}).json()["batch_id"]
    mk_link(adm, p["id"], EV1, "volontario", "confermato")
    assert sa.post(f"{B}/api/admin/deleted-requests/{batch}/restore").status_code == 200
    ls = links(p["id"], EV1)
    assert len(ls) == 1 and ls[0]["categoria"] == "volontario"


# Orphan delete + public form re-registration + restore: report how many persons share the email
def test_restore_orphan_after_public_form(adm, sa):
    email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    p = mk_person(adm, "Orph", email)
    mk_link(adm, p["id"], EV1, "da_classificare", "da_contattare")
    batch = adm.post(f"{B}/api/da-classificare/delete", json={"persona_id": p["id"], "evento_id": EV1}).json()["batch_id"]
    r = public_submit(email, "Orph", "TEST_Orph"); assert r.status_code in (200, 201), r.text
    newp = [x["id"] for x in mdb.persons.find({"org_id": ORG, "email": email})]
    CREATED.extend(newp)
    assert sa.post(f"{B}/api/admin/deleted-requests/{batch}/restore").status_code == 200
    persons = list(mdb.persons.find({"org_id": ORG, "email": email}, {"_id": 0, "id": 1}))
    ev1_links = mdb.staff.count_documents({"org_id": ORG, "persona_id": {"$in": [x["id"] for x in persons]}, "evento_id": EV1})
    print(f"ORPHAN_CASE persons_with_email={len(persons)} ev1_links={ev1_links}")
    assert len(persons) == 1, f"duplicate anagrafica after restore: {len(persons)} persons with same email, {ev1_links} EV1 links"


# Bulk fascia preview: only confirmed staff/volontari with chosen mansione
def test_bulk_preview_filter(adm):
    mans = "TEST_Mans208"
    ids = {}
    for tag, cat, st in (("BkOk", "volontario", "confermato"), ("BkSt", "staff", "confermato"), ("BkDc", "da_classificare", "confermato"),
                         ("BkUn", "volontario", "da_contattare"), ("BkRi", "staff", "rinunciato")):
        p = mk_person(adm, tag); ids[tag] = p["id"]
        mk_link(adm, p["id"], EV1, cat, st, mans)
    r = adm.post(f"{B}/api/staff-coverage/bulk-fascia/preview", json={"evento_id": EV1, "date": DAY, "fascia": "mattina", "mansioni": [mans]})
    assert r.status_code == 200, r.text
    got = {x["id"] for x in r.json()["people"]}
    assert ids["BkOk"] in got and ids["BkSt"] in got
    assert not ({ids["BkDc"], ids["BkUn"], ids["BkRi"]} & got)


# PUT /staff stato persists for every mask option value
@pytest.mark.parametrize("st", ["da_contattare", "disponibilita_richiesta", "disponibile", "da_riconfermare", "confermato", "non_disponibile", "rinunciato"])
def test_stato_values_accepted(adm, st):
    if not hasattr(test_stato_values_accepted, "pid"):
        p = mk_person(adm, "StV"); test_stato_values_accepted.pid = p["id"]
        test_stato_values_accepted.lid = mk_link(adm, p["id"], EV1, "volontario", "da_contattare")
    r = adm.put(f"{B}/api/staff/{test_stato_values_accepted.lid}", json={"categoria": "volontario", "stato": st})
    assert r.status_code == 200, r.text
    assert mdb.staff.find_one({"id": test_stato_values_accepted.lid})["stato"] == st
