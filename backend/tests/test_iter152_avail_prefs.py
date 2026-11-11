# Iteration 152: Preferenze volontari (per-event preference, mansione-bulk, Super Admin retro recovery)
import sys, os, requests, pytest
sys.path.insert(0, os.path.dirname(__file__))
from avp_helpers import BASE, SA, setup_org, cleanup, login, _db


@pytest.fixture(scope="module")
def ctx():
    c = setup_org()
    yield c
    cleanup(c["org_id"], c["email"])


def enriched(c, pid):
    return next(p for p in c["s"].get(f"{BASE}/api/persons-enriched").json() if p["id"] == pid)


class TestAvailPrefs:
    # persons-enriched exposes preferenze per event
    def test_enriched_prefs(self, ctx):
        p1 = enriched(ctx, ctx["pid"]["p1"])
        assert [x["preferenza"] for x in p1["preferenze"]] == [ctx["ruoli"][0]]
        assert p1["preferenze"][0]["evento_id"] == ctx["ev"]["A"]
        p2 = enriched(ctx, ctx["pid"]["p2"])
        m = {x["evento_id"]: x["preferenza"] for x in p2["preferenze"]}
        assert m == {ctx["ev"]["A"]: ctx["ruoli"][1], ctx["ev"]["B"]: ctx["ruoli"][0]}
        p3 = enriched(ctx, ctx["pid"]["p3"])
        assert p3["preferenze"][0]["preferenza"] == "Altro: TEST_custom"

    # confirming availability keeps preference
    def test_confirm_availability(self, ctx):
        s = ctx["s"]
        avs = s.get(f"{BASE}/api/events/{ctx['ev']['A']}/availabilities").json()
        avs = avs["availabilities"]
        a1 = next(a for a in avs if a["persona_id"] == ctx["pid"]["p1"])
        r = s.put(f"{BASE}/api/availabilities/{a1['id']}", json={"stato": "confermata"})
        assert r.status_code == 200, r.text
        p1 = enriched(ctx, ctx["pid"]["p1"])
        assert p1["preferenze"][0]["preferenza"] == ctx["ruoli"][0]
        assert p1["preferenze"][0]["stato"] == "confermata"

    # person detail exposes preferenze
    def test_person_detail(self, ctx):
        d = ctx["s"].get(f"{BASE}/api/persons/{ctx['pid']['p2']}/detail").json()
        assert {x["evento_id"] for x in d["preferenze"]} == {ctx["ev"]["A"], ctx["ev"]["B"]}

    # mansione-bulk on Da classificare (no staff link) -> person.ruolo
    def test_mansione_person_no_link(self, ctx):
        s = ctx["s"]
        r = s.post(f"{BASE}/api/persons/mansione-bulk", json={"person_ids": [ctx["pid"]["p1"]], "mansione": ctx["ruoli"][0], "evento_id": ctx["ev"]["A"]})
        assert r.status_code == 200 and r.json()["anagrafiche"] == 1 and r.json()["partecipazioni"] == 0
        p1 = enriched(ctx, ctx["pid"]["p1"])
        assert p1["ruolo"] == ctx["ruoli"][0]
        assert p1["preferenze"][0]["preferenza"] == ctx["ruoli"][0]
        assert not p1["is_volontario"] and not p1["is_staff"]

    # mansione-bulk with event A filter only touches staff A; categoria/team/shift unchanged
    def test_mansione_staff_event_scope(self, ctx):
        s = ctx["s"]
        r = s.post(f"{BASE}/api/persons/mansione-bulk", json={"person_ids": [ctx["pid"]["p2"]], "mansione": ctx["ruoli"][1], "evento_id": ctx["ev"]["A"]})
        assert r.status_code == 200 and r.json()["partecipazioni"] == 1
        db = _db()
        a = db.staff.find_one({"id": ctx["staffA"]}); b = db.staff.find_one({"id": ctx["staffB"]})
        assert a["ruolo"] == ctx["ruoli"][1] and a["categoria"] == "volontario" and a["team_id"] == ctx["team"] and a.get("stato") == "confermato"
        assert b.get("ruolo") in (None, "") and b["categoria"] == "volontario"
        sh = db.shifts.find_one({"id": ctx["shift"]})
        assert sh["persona_id"] == ctx["pid"]["p2"] and sh["team_id"] == ctx["team"] and sh["ora_inizio"] == "08:00"
        p2 = enriched(ctx, ctx["pid"]["p2"])
        m = {x["evento_id"]: x["preferenza"] for x in p2["preferenze"]}
        assert m == {ctx["ev"]["A"]: ctx["ruoli"][1], ctx["ev"]["B"]: ctx["ruoli"][0]}

    # UI mansione column reads persons.ruolo -> does it reflect staff.ruolo after assignment?
    def test_enriched_reflects_staff_mansione(self, ctx):
        p2 = enriched(ctx, ctx["pid"]["p2"])
        m = {x["evento_id"]: x["ruolo"] for x in p2["mansioni"]}  # iter153: per-event mansioni from staff links
        assert m.get(ctx["ev"]["A"]) == ctx["ruoli"][1] and m.get(ctx["ev"]["B"]) in (None, "")

    # invalid mansione -> 400, nothing created
    def test_invalid_mansione(self, ctx):
        r = ctx["s"].post(f"{BASE}/api/persons/mansione-bulk", json={"person_ids": [ctx["pid"]["p3"]], "mansione": "TEST_NonEsiste"})
        assert r.status_code == 400
        r = ctx["s"].post(f"{BASE}/api/persons/mansione-bulk", json={"person_ids": [ctx["pid"]["p3"]], "mansione": "Altro: TEST_custom"})
        assert r.status_code == 400

    # non-superadmin gets 403 on platform endpoints
    def test_platform_403(self, ctx):
        s = ctx["s"]
        assert s.get(f"{BASE}/api/platform/avail-prefs/orgs").status_code == 403
        assert s.post(f"{BASE}/api/platform/avail-prefs/preview", json={"org_id": ctx["org_id"]}).status_code == 403
        assert s.post(f"{BASE}/api/platform/avail-prefs/apply", json={"org_id": ctx["org_id"]}).status_code == 403
        assert requests.get(f"{BASE}/api/platform/avail-prefs/orgs").status_code in (401, 403)

    # Super Admin preview (no write), apply, idempotent re-apply
    def test_superadmin_preview_apply(self, ctx):
        sa = login(*SA)
        db = _db(); oid = ctx["org_id"]
        orgs = sa.get(f"{BASE}/api/platform/avail-prefs/orgs").json()["orgs"]
        assert any(o["id"] == oid and o["disponibilita"] == 4 for o in orgs)
        before = {c: db[c].count_documents({"org_id": oid}) for c in ("persons", "staff", "availabilities", "shifts", "teams")}
        snap = {s["id"]: {k: s.get(k) for k in ("categoria", "ruolo", "team_id", "stato")} for s in db.staff.find({"org_id": oid})}
        r = sa.post(f"{BASE}/api/platform/avail-prefs/preview", json={"org_id": oid})
        assert r.status_code == 200
        rep = r.json()["reports"][0]
        assert rep["simulazione"] is True and rep["disponibilita_esaminate"] == 4 and rep["preferenze_recuperate"] == 4
        assert db.backup_avail_prefs.count_documents({"org_id": oid}) == 0
        assert db.staff.count_documents({"org_id": oid, "preferenza_volontario": {"$exists": True}}) == 0
        r = sa.post(f"{BASE}/api/platform/avail-prefs/apply", json={"org_id": oid})
        assert r.status_code == 200
        rep = r.json()["reports"][0]
        assert rep["simulazione"] is False and rep["run_id"] and rep["partecipazioni_gia_corrette"] == 0
        assert rep["con_team_o_turni_aggiornati"] >= 1 and rep["da_classificare_con_preferenza"] == 2
        sA = db.staff.find_one({"id": ctx["staffA"]}); sB = db.staff.find_one({"id": ctx["staffB"]})
        assert sA["preferenza_volontario"] == ctx["ruoli"][1] and sB["preferenza_volontario"] == ctx["ruoli"][0]
        assert db.backup_avail_prefs.count_documents({"org_id": oid}) == 2
        r2 = sa.post(f"{BASE}/api/platform/avail-prefs/apply", json={"org_id": oid}).json()["reports"][0]
        assert r2["partecipazioni_gia_corrette"] == 2 and db.backup_avail_prefs.count_documents({"org_id": oid}) == 2
        after = {c: db[c].count_documents({"org_id": oid}) for c in ("persons", "staff", "availabilities", "shifts", "teams")}
        assert before == after
        snap2 = {s["id"]: {k: s.get(k) for k in ("categoria", "ruolo", "team_id", "stato")} for s in db.staff.find({"org_id": oid})}
        assert snap == snap2

    # superadmin preview with unknown org -> 404
    def test_preview_unknown_org(self, ctx):
        sa = login(*SA)
        assert sa.post(f"{BASE}/api/platform/avail-prefs/preview", json={"org_id": "nonexistent_TEST"}).status_code == 404
