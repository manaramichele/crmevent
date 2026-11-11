# Iteration 153: retest Preferenze volontari fixes (event-aware mansioni, per-event mansione-bulk, apply backup of persona_id rewrites, no-op runs)
import sys, os, requests, pytest
sys.path.insert(0, os.path.dirname(__file__))
from avp_helpers import BASE, SA, setup_org, cleanup, login, _db


@pytest.fixture(scope="module")
def ctx():
    c = setup_org()
    yield c
    cleanup(c["org_id"], c["email"])
    db = _db()
    left = sum(db[k].count_documents({"org_id": c["org_id"]}) for k in ("events", "persons", "staff", "shifts", "teams", "availabilities",
                                                                       "avail_links", "backup_avail_prefs", "avail_prefs_runs"))
    assert left == 0 and db.organizations.count_documents({"id": c["org_id"]}) == 0 and db.users.count_documents({"email": c["email"]}) == 0


def enriched(c, pid):
    return next(p for p in c["s"].get(f"{BASE}/api/persons-enriched").json() if p["id"] == pid)


class TestFixes:
    # persons-enriched exposes mansioni per event from staff links
    def test_enriched_mansioni_shape(self, ctx):
        p2 = enriched(ctx, ctx["pid"]["p2"])
        assert isinstance(p2["mansioni"], list) and {m["evento_id"] for m in p2["mansioni"]} == {ctx["ev"]["A"], ctx["ev"]["B"]}
        assert all(m["ruolo"] in (None, "") for m in p2["mansioni"])
        assert enriched(ctx, ctx["pid"]["p1"])["mansioni"] == []

    # mansione-bulk event A -> mansioni A updated, B unchanged
    def test_mansione_reflected_per_event(self, ctx):
        r = ctx["s"].post(f"{BASE}/api/persons/mansione-bulk", json={"person_ids": [ctx["pid"]["p2"]], "mansione": ctx["ruoli"][1], "evento_id": ctx["ev"]["A"]})
        assert r.status_code == 200 and r.json()["partecipazioni"] == 1 and r.json()["anagrafiche"] == 0
        m = {x["evento_id"]: x["ruolo"] for x in enriched(ctx, ctx["pid"]["p2"])["mansioni"]}
        assert m[ctx["ev"]["A"]] == ctx["ruoli"][1] and m[ctx["ev"]["B"]] in (None, "")
        r = ctx["s"].post(f"{BASE}/api/persons/mansione-bulk", json={"person_ids": [ctx["pid"]["p2"]], "mansione": ctx["ruoli"][0], "evento_id": ctx["ev"]["B"]})
        m = {x["evento_id"]: x["ruolo"] for x in enriched(ctx, ctx["pid"]["p2"])["mansioni"]}
        assert m == {ctx["ev"]["A"]: ctx["ruoli"][1], ctx["ev"]["B"]: ctx["ruoli"][0]}
        assert enriched(ctx, ctx["pid"]["p2"]).get("ruolo") in (None, "")  # persons.ruolo untouched

    # Da classificare person: persons.ruolo set, prefs unchanged
    def test_da_classificare_person_ruolo(self, ctx):
        r = ctx["s"].post(f"{BASE}/api/persons/mansione-bulk", json={"person_ids": [ctx["pid"]["p1"]], "mansione": ctx["ruoli"][0], "evento_id": ctx["ev"]["A"]})
        assert r.json()["anagrafiche"] == 1
        p1 = enriched(ctx, ctx["pid"]["p1"])
        assert p1["ruolo"] == ctx["ruoli"][0] and p1["preferenze"][0]["preferenza"] == ctx["ruoli"][0]

    # apply: no-op on fresh org without staff links needing change -> run, then second run no row
    def test_apply_backup_and_noop(self, ctx):
        db = _db(); oid = ctx["org_id"]; sa = login(*SA)
        # break link of P3's availability (TEST data) so apply must rebuild it from email
        av = db.availabilities.find_one({"org_id": oid, "persona_id": ctx["pid"]["p3"]})
        db.availabilities.update_one({"id": av["id"], "org_id": oid}, {"$set": {"persona_id": "TEST_broken_pid"}})
        pv = sa.post(f"{BASE}/api/platform/avail-prefs/preview", json={"org_id": oid}).json()["reports"][0]
        assert any(a["tipo"] == "collegamento persona ricostruito" for a in pv["anomalie"])
        assert db.availabilities.find_one({"id": av["id"]})["persona_id"] == "TEST_broken_pid"
        assert db.backup_avail_prefs.count_documents({"org_id": oid}) == 0 and db.avail_prefs_runs.count_documents({"org_id": oid}) == 0
        rep = sa.post(f"{BASE}/api/platform/avail-prefs/apply", json={"org_id": oid}).json()["reports"][0]
        assert rep.get("run_id") and rep["modifiche"] >= 3
        a2 = db.availabilities.find_one({"id": av["id"]})
        assert a2["persona_id"] == ctx["pid"]["p3"] and a2["persona_id_originale"] == "TEST_broken_pid"
        bk = db.backup_avail_prefs.find_one({"org_id": oid, "availability_id": av["id"]})
        assert bk and bk["prev"]["persona_id"] == "TEST_broken_pid" and bk["run_id"] == rep["run_id"]
        assert db.avail_prefs_runs.count_documents({"org_id": oid}) == 1
        nb = db.backup_avail_prefs.count_documents({"org_id": oid})
        rep2 = sa.post(f"{BASE}/api/platform/avail-prefs/apply", json={"org_id": oid}).json()["reports"][0]
        assert "run_id" not in rep2 and rep2["partecipazioni_gia_corrette"] == 2 and rep2["anomalie"] == []
        assert db.avail_prefs_runs.count_documents({"org_id": oid}) == 1 and db.backup_avail_prefs.count_documents({"org_id": oid}) == nb
