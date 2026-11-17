# Staff/Volontari reorganization: PersonMask backend contract (provenienza, assegnazioni, preferenza on staff link, org isolation)
import os
import uuid
import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL")).rstrip("/")
ORG = "b7f40862230441b9a0bedabefe8dab49"
OTHER_ORG = "org_qa_eventi"
CREDS = {"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"}
EV1, EV2 = "demo_evt_bcr", "demo_evt_maratona"

CREATED = {"persons": [], "staff": [], "events": [], "avail_codes": [], "availabilities": []}


def _sess(org=ORG):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=CREDS, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"login failed {r.status_code}")
    s.headers.update({"X-Org-Id": org})
    return s


@pytest.fixture(scope="module")
def s():
    sess = _sess()
    yield sess
    # cleanup only what we created
    for sid in CREATED["staff"]:
        sess.delete(f"{BASE_URL}/api/staff/{sid}")
    for pid in CREATED["persons"]:
        sess.delete(f"{BASE_URL}/api/persons/{pid}")
    env = dotenv_values("/app/backend/.env")
    db = MongoClient(env["MONGO_URL"])[env["DB_NAME"]]
    if CREATED["persons"]:
        db.staff.delete_many({"org_id": ORG, "persona_id": {"$in": CREATED["persons"]}})
    for aid in CREATED["availabilities"]:
        db.availabilities.delete_one({"org_id": ORG, "id": aid})
    for code in CREATED["avail_codes"]:
        db.avail_links.delete_one({"org_id": ORG, "code": code})
    for eid in CREATED["events"]:
        sess.delete(f"{BASE_URL}/api/events/{eid}")


def _enriched(s, pid):
    r = s.get(f"{BASE_URL}/api/persons-enriched", timeout=60)
    assert r.status_code == 200
    return next((p for p in r.json() if p["id"] == pid), None)


def _teams(s, ev):
    r = s.get(f"{BASE_URL}/api/teams", params={"evento_id": ev})
    return [t for t in r.json() if t.get("evento_id") == ev]


class TestProvenienza:
    def test_post_person_sets_manuale_and_ignores_body(self, s):
        r = s.post(f"{BASE_URL}/api/persons", json={"nome": "TEST_Mask", "cognome": f"TEST_Prov{uuid.uuid4().hex[:5]}",
                                                   "provenienza": {"tipo": "link_disponibilita"}})
        assert r.status_code in (200, 201), r.text
        p = r.json(); CREATED["persons"].append(p["id"])
        assert p["provenienza"]["tipo"] == "manuale"
        e = _enriched(s, p["id"])
        assert e["provenienza_tipo"] == "manuale"
        # PUT with provenienza ignored; cognome updated
        r = s.put(f"{BASE_URL}/api/persons/{p['id']}", json={"cognome": "TEST_ProvEdited", "provenienza": {"tipo": "link_disponibilita"},
                                                           "provenienza_tipo": "link_disponibilita"})
        assert r.status_code == 200, r.text
        e = _enriched(s, p["id"])
        assert e["cognome"].lower() == "test_provedited"
        assert e["provenienza_tipo"] == "manuale"

    def test_quick_add_sets_manuale(self, s):
        r = s.post(f"{BASE_URL}/api/staff/quick-add", json={"evento_id": EV1, "nome": "TEST_Quick", "cognome": f"TEST_QA{uuid.uuid4().hex[:5]}", "categoria": "volontario"})
        assert r.status_code == 200, r.text
        d = r.json()
        pid = (d.get("person") or {}).get("id") or d.get("persona_id")
        assert pid, d
        CREATED["persons"].append(pid)
        e = _enriched(s, pid)
        assert e["provenienza_tipo"] == "manuale"
        assert e["is_volontario"] is True
        for a in e["assegnazioni"]:
            CREATED["staff"].append(a["id"])

    def test_historic_persons_non_determinata(self, s):
        r = s.get(f"{BASE_URL}/api/persons-enriched", timeout=60)
        rows = r.json()
        nd = [p for p in rows if not p.get("provenienza")]
        assert all(p["provenienza_tipo"] == "non_determinata" for p in nd)
        assert len(nd) > 0

    def test_public_availability_sets_link_disponibilita(self, s):
        ev = s.post(f"{BASE_URL}/api/events", json={"nome": f"TEST_MaskEv_{uuid.uuid4().hex[:5]}", "data_inizio": "2026-10-10", "data_fine": "2026-10-10", "stato": "pianificato"})
        if ev.status_code not in (200, 201):
            pytest.skip(f"cannot create TEST event: {ev.status_code} {ev.text[:200]}")
        eid = ev.json()["id"]; CREATED["events"].append(eid)
        lk = s.post(f"{BASE_URL}/api/events/{eid}/availability/link")
        assert lk.status_code == 200, lk.text
        code = lk.json()["code"]; CREATED["avail_codes"].append(code)
        info = requests.get(f"{BASE_URL}/api/public/availability/{code}").json()
        day = next(d for d in info["days"] if d["fase"] == "evento")["date"]
        uniq = uuid.uuid4().hex[:6]
        r = requests.post(f"{BASE_URL}/api/public/availability/{code}", json={
            "nome": "TEST_Pub", "cognome": f"TEST_Link{uniq}", "cellulare": f"+39333{int(uniq, 16) % 10**7:07d}",
            "email": f"test_pub_{uniq}@example.com", "data_nascita": "1990-01-01", "privacy": True, "preferenza_attivita": "Altro", "preferenza_altro": "TEST_pref",
            "days": [{"date": day, "disponibile": True}]})
        assert r.status_code == 200, r.text
        rows = s.get(f"{BASE_URL}/api/persons-enriched", timeout=60).json()
        p = next((x for x in rows if (x.get("email") or "").lower() == f"test_pub_{uniq}@example.com"), None)
        assert p, "public submission person not found"
        CREATED["persons"].append(p["id"])
        env = dotenv_values("/app/backend/.env")
        db = MongoClient(env["MONGO_URL"])[env["DB_NAME"]]
        CREATED["availabilities"] += [a["id"] for a in db.availabilities.find({"org_id": ORG, "persona_id": p["id"]}, {"id": 1})]
        assert p["provenienza_tipo"] == "link_disponibilita"


class TestAssegnazioni:
    def test_two_events_different_team_mansione_and_preferenza(self, s):
        r = s.post(f"{BASE_URL}/api/persons", json={"nome": "TEST_Multi", "cognome": f"TEST_Multi{uuid.uuid4().hex[:5]}"})
        pid = r.json()["id"]; CREATED["persons"].append(pid)
        t1 = _teams(s, EV1); t2 = _teams(s, EV2)
        l1 = s.post(f"{BASE_URL}/api/staff", json={"persona_id": pid, "evento_id": EV1, "categoria": "staff", "ruolo": "TEST_MansA",
                                                   "team_id": t1[0]["id"] if t1 else None, "preferenza": "TEST_PrefA", "stato": "da_contattare"})
        assert l1.status_code in (200, 201), l1.text
        CREATED["staff"].append(l1.json()["id"])
        assert l1.json()["preferenza"] == "TEST_PrefA"
        l2 = s.post(f"{BASE_URL}/api/staff", json={"persona_id": pid, "evento_id": EV2, "categoria": "volontario", "ruolo": "TEST_MansB",
                                                   "team_id": t2[0]["id"] if t2 else None, "stato": "da_contattare"})
        assert l2.status_code in (200, 201), l2.text
        CREATED["staff"].append(l2.json()["id"])
        e = _enriched(s, pid)
        assert e["is_staff"] and e["is_volontario"]
        asg = {a["evento_id"]: a for a in e["assegnazioni"]}
        assert asg[EV1]["ruolo"] == "TEST_MansA" and asg[EV1]["preferenza"] == "TEST_PrefA" and asg[EV1]["categoria"] == "staff"
        assert asg[EV2]["ruolo"] == "TEST_MansB" and asg[EV2]["categoria"] == "volontario"
        # remove one association -> person remains, only that link removed
        d = s.delete(f"{BASE_URL}/api/staff/{l2.json()['id']}")
        assert d.status_code == 200
        e = _enriched(s, pid)
        assert e is not None
        assert [a["evento_id"] for a in e["assegnazioni"]] == [EV1]
        assert e["is_volontario"] is False

    def test_put_staff_preferenza(self, s):
        sid = CREATED["staff"][-2] if len(CREATED["staff"]) >= 2 else None
        if not sid:
            pytest.skip("no staff link")
        r = s.put(f"{BASE_URL}/api/staff/{sid}", json={"preferenza": "TEST_PrefZ", "ruolo": "TEST_MansZ"})
        assert r.status_code == 200, r.text
        g = s.get(f"{BASE_URL}/api/staff/{sid}").json()
        assert g["preferenza"] == "TEST_PrefZ" and g["ruolo"] == "TEST_MansZ"

    def test_duplicate_event_role_backend(self, s):
        """Mask blocks duplicates client-side; check whether backend also blocks (informational)."""
        r = s.post(f"{BASE_URL}/api/persons", json={"nome": "TEST_Dup", "cognome": f"TEST_Dup{uuid.uuid4().hex[:5]}"})
        pid = r.json()["id"]; CREATED["persons"].append(pid)
        a = s.post(f"{BASE_URL}/api/staff", json={"persona_id": pid, "evento_id": EV1, "categoria": "staff"})
        CREATED["staff"].append(a.json()["id"])
        b = s.post(f"{BASE_URL}/api/staff", json={"persona_id": pid, "evento_id": EV1, "categoria": "staff"})
        if b.status_code in (200, 201):
            CREATED["staff"].append(b.json()["id"])
        print(f"backend duplicate staff link status: {b.status_code}")
        assert b.status_code >= 400, "Backend accepts duplicate persona+evento+categoria staff link (only client-side guard)"


class TestOrgIsolation:
    def test_staff_link_foreign_event_rejected(self, s):
        other = _sess(OTHER_ORG)
        evs = other.get(f"{BASE_URL}/api/events").json()
        if not evs:
            pytest.skip("other org has no events")
        foreign = evs[0]["id"]
        r = s.post(f"{BASE_URL}/api/persons", json={"nome": "TEST_Iso", "cognome": f"TEST_Iso{uuid.uuid4().hex[:5]}"})
        pid = r.json()["id"]; CREATED["persons"].append(pid)
        x = s.post(f"{BASE_URL}/api/staff", json={"persona_id": pid, "evento_id": foreign, "categoria": "staff"})
        if x.status_code in (200, 201):
            CREATED["staff"].append(x.json()["id"])
        assert x.status_code in (400, 403, 404), f"foreign event accepted: {x.status_code} {x.text[:200]}"

    def test_staff_link_foreign_person_rejected(self, s):
        other = _sess(OTHER_ORG)
        ps = other.get(f"{BASE_URL}/api/persons").json()
        if not ps:
            pytest.skip("other org has no persons")
        x = s.post(f"{BASE_URL}/api/staff", json={"persona_id": ps[0]["id"], "evento_id": EV1, "categoria": "staff"})
        if x.status_code in (200, 201):
            CREATED["staff"].append(x.json()["id"])
        assert x.status_code in (400, 403, 404), f"foreign person accepted: {x.status_code}"

# iteration_177: retest fixes (PUT org isolation, 409 duplicate, clear team)
class TestIter177Fixes:
    def _person_link(self, s, ev=EV1, cat="staff", **kw):
        r = s.post(f"{BASE_URL}/api/persons", json={"nome": "TEST_R177", "cognome": f"TEST_R177{uuid.uuid4().hex[:5]}"})
        pid = r.json()["id"]; CREATED["persons"].append(pid)
        l = s.post(f"{BASE_URL}/api/staff", json={"persona_id": pid, "evento_id": ev, "categoria": cat, **kw})
        assert l.status_code in (200, 201), l.text
        CREATED["staff"].append(l.json()["id"])
        return pid, l.json()

    def test_duplicate_is_409_with_message(self, s):
        pid, l = self._person_link(s)
        b = s.post(f"{BASE_URL}/api/staff", json={"persona_id": pid, "evento_id": EV1, "categoria": "staff"})
        if b.status_code in (200, 201):
            CREATED["staff"].append(b.json()["id"])
        assert b.status_code == 409, b.text
        # same person+event but different categoria allowed
        c = s.post(f"{BASE_URL}/api/staff", json={"persona_id": pid, "evento_id": EV1, "categoria": "volontario"})
        assert c.status_code in (200, 201), c.text
        CREATED["staff"].append(c.json()["id"])

    def test_foreign_refs_message(self, s):
        other = _sess(OTHER_ORG)
        foreign_ev = other.get(f"{BASE_URL}/api/events").json()[0]["id"]
        r = s.post(f"{BASE_URL}/api/persons", json={"nome": "TEST_R177", "cognome": f"TEST_R177{uuid.uuid4().hex[:5]}"})
        pid = r.json()["id"]; CREATED["persons"].append(pid)
        x = s.post(f"{BASE_URL}/api/staff", json={"persona_id": pid, "evento_id": foreign_ev, "categoria": "staff"})
        if x.status_code in (200, 201): CREATED["staff"].append(x.json()["id"])
        assert x.status_code == 404 and "non trovato in questa organizzazione" in x.text, x.text

    def test_foreign_team_post_rejected(self, s):
        other = _sess(OTHER_ORG)
        tms = other.get(f"{BASE_URL}/api/teams").json()
        if not tms: pytest.skip("other org no teams")
        r = s.post(f"{BASE_URL}/api/persons", json={"nome": "TEST_R177", "cognome": f"TEST_R177{uuid.uuid4().hex[:5]}"})
        pid = r.json()["id"]; CREATED["persons"].append(pid)
        x = s.post(f"{BASE_URL}/api/staff", json={"persona_id": pid, "evento_id": EV1, "categoria": "staff", "team_id": tms[0]["id"]})
        if x.status_code in (200, 201): CREATED["staff"].append(x.json()["id"])
        assert x.status_code == 404, x.text

    def test_put_foreign_event_and_team_rejected(self, s):
        other = _sess(OTHER_ORG)
        foreign_ev = other.get(f"{BASE_URL}/api/events").json()[0]["id"]
        tms = other.get(f"{BASE_URL}/api/teams").json()
        pid, l = self._person_link(s)
        x = s.put(f"{BASE_URL}/api/staff/{l['id']}", json={"evento_id": foreign_ev})
        assert x.status_code == 404, x.text
        if tms:
            y = s.put(f"{BASE_URL}/api/staff/{l['id']}", json={"team_id": tms[0]["id"]})
            assert y.status_code == 404, y.text
        g = s.get(f"{BASE_URL}/api/staff/{l['id']}").json()
        assert g["evento_id"] == EV1

    def test_clear_team_persists_empty(self, s):
        t1 = _teams(s, EV1)
        if not t1: pytest.skip("no team")
        pid, l = self._person_link(s, team_id=t1[0]["id"])
        assert l["team_id"] == t1[0]["id"]
        u = s.put(f"{BASE_URL}/api/staff/{l['id']}", json={"team_id": ""})
        assert u.status_code == 200, u.text
        g = s.get(f"{BASE_URL}/api/staff/{l['id']}").json()
        assert not g.get("team_id"), g
        e = _enriched(s, pid)
        assert not e["assegnazioni"][0].get("team_id")

    def test_put_into_duplicate(self, s):
        """Informational: PUT changing categoria to collide with existing link."""
        pid, a = self._person_link(s)
        b = s.post(f"{BASE_URL}/api/staff", json={"persona_id": pid, "evento_id": EV1, "categoria": "volontario"})
        CREATED["staff"].append(b.json()["id"])
        x = s.put(f"{BASE_URL}/api/staff/{b.json()['id']}", json={"categoria": "staff"})
        print("PUT into duplicate status:", x.status_code)
        if x.status_code == 200:
            s.put(f"{BASE_URL}/api/staff/{b.json()['id']}", json={"categoria": "volontario"})
        assert x.status_code == 409, f"PUT allows duplicate: {x.status_code}"
