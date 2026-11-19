# Universal Excel/CSV import (/api/imports): upload/read/preview/run/history/undo/configs/templates, targets persone/soci/aziende/sponsor/pernottamenti/pasti/pipeline
import io
import os
import uuid

import openpyxl
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
SUPER = ("manara.michele.pro@gmail.com", "CrmEvent2026!")
PWD = "TestImp2026!"


def _env(key):
    for line in open("/app/backend/.env"):
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"')


MDB = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]
ORGS = []
CFG_IDS = []
U = uuid.uuid4().hex[:6]


def register(tag):
    s = requests.Session()
    email = f"test_imp_{tag.lower()}_{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{BASE_URL}/api/auth/register-organization", json={
        "nome": "TEST", "cognome": tag, "email": email, "password": PWD, "org_name": f"TEST_IMP_{tag}_{U}",
        "telefono": "+393331234567", "accept_terms": True})
    assert r.status_code == 200, r.text
    org = MDB.users.find_one({"email": email})["org_id"]
    ORGS.append((org, email))
    assert s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": PWD}).status_code == 200
    return {"s": s, "org": org, "email": email}


def mk_event(org, nome):
    eid = uuid.uuid4().hex
    MDB.events.insert_one({"id": eid, "org_id": org, "nome": nome, "data_inizio": "2026-09-01", "created_at": "2026-01-01T00:00:00+00:00"})
    return eid


@pytest.fixture(scope="module")
def A():
    a = register("A")
    a["ev"] = mk_event(a["org"], f"TEST_Gara {U}")
    a["ev2"] = mk_event(a["org"], f"TEST_Festa {U}")
    return a


@pytest.fixture(scope="module")
def B():
    return register("B")


@pytest.fixture(scope="module")
def SA(A):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": SUPER[0], "password": SUPER[1]})
    if r.status_code != 200:
        pytest.skip("superadmin login failed")
    s.headers.update({"X-Org-Id": A["org"]})
    return s


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    for org, email in ORGS:
        for c in ("persons", "asd_soci", "asd_tesseramenti", "asd_quote", "staff", "teams", "companies", "deals", "lodgings", "meals", "events",
                  "pipeline_tasks", "pipeline_categories", "event_pipelines", "import_jobs", "import_configs", "org_services", "memberships",
                  "subscriptions", "audit_logs", "settings"):
            MDB[c].delete_many({"org_id": org})
        MDB.settings.delete_one({"id": org})
        MDB.organizations.delete_one({"id": org})
        MDB.users.delete_many({"email": email})
    for cid in CFG_IDS:
        MDB.import_configs.delete_one({"id": cid})


def csv_bytes(rows, sep=";"):
    return ("\n".join(sep.join(r) for r in rows)).encode("utf-8")


def xlsx_bytes(sheets):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for r in rows:
            ws.append(r)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def upload(s, data, name="f.csv"):
    r = s.post(f"{BASE_URL}/api/imports/upload", files={"file": (name, data)})
    assert r.status_code == 200, r.text
    return r.json()


def read(s, jid, target, **body):
    r = s.post(f"{BASE_URL}/api/imports/jobs/{jid}/read", params={"target": target}, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def body(target, mapping, mode="both", options=None, **kw):
    return {"target": target, "mapping": mapping, "mode": mode, "options": options or {}, "header_row": 1, **kw}


def preview(s, jid, b, code=200):
    r = s.post(f"{BASE_URL}/api/imports/jobs/{jid}/preview", json=b)
    assert r.status_code == code, r.text
    return r.json()


def run(s, jid, b, code=200):
    r = s.post(f"{BASE_URL}/api/imports/jobs/{jid}/run", json=b)
    assert r.status_code == code, r.text
    return r.json()


def full(s, rows, target, mode="both", options=None, name="f.csv", sep=";"):
    j = upload(s, csv_bytes(rows, sep), name)
    rd = read(s, j["id"], target)
    b = body(target, rd["suggested"], mode, options)
    return j["id"], b, preview(s, j["id"], b)


# ---------- upload / read ----------
class TestUploadRead:
    def test_csv_semicolon_and_comma(self, A):
        for sep in (";", ","):
            j = upload(A["s"], csv_bytes([["Nome", "Cognome", "Mail", "Cell"], ["TEST_a", "X", "a@x.it", "3331112222"]], sep))
            assert j["sheets"][0]["rows"] == 2 and j["sheets"][0]["sep"] == sep
            rd = read(A["s"], j["id"], "persone")
            assert rd["columns"] == ["Nome", "Cognome", "Mail", "Cell"] and rd["total"] == 1
            assert rd["suggested"]["Mail"] == "email" and rd["suggested"]["Cell"] == "cellulare"

    def test_xlsx_multi_sheets_and_header_row(self, A):
        data = xlsx_bytes({"Uno": [["Titolo report"], ["Attività", "Scadenza", "Responsabile", "Fase"]] + [[f"T{i}", "2026-05-01", "Mario", "F"] for i in range(25)],
                           "Due": [["Attività"], ["x"]]})
        j = upload(A["s"], data, "p.xlsx")
        assert [(s["name"], s["rows"]) for s in j["sheets"]] == [("Uno", 27), ("Due", 2)]
        rd = read(A["s"], j["id"], "pipeline", sheet="Uno", header_row=2)
        assert rd["total"] == 25 and len(rd["preview"]) == 20
        sg = rd["suggested"]
        assert sg["Attività"] == "titolo" and sg["Scadenza"] == "scadenza" and sg["Responsabile"] == "responsabile" and sg["Fase"] == "fase"

    def test_bad_extension(self, A):
        r = A["s"].post(f"{BASE_URL}/api/imports/upload", files={"file": ("x.txt", b"a,b")})
        assert r.status_code == 400


# ---------- persone ----------
class TestPersone:
    def test_preview_writes_nothing_then_run(self, A):
        em = f"test_p1_{U}@example.com"
        rows = [["Nome", "Cognome", "Mail", "Cell", "Classificazione", "Team", "Mansione"],
                ["TEST_Anna", "Rossi", em, "3401234567", "Volontario", "TEST_Team Ristoro", "Cassa"],
                ["TEST_Anna", "Rossi", em, "3401234567", "Volontario", "TEST_Team Ristoro", "Cassa"],
                ["TEST_Bea", "Verdi", "", "3409999888", "Staff", "TEST_Team Ristoro", ""],
                ["", "NoName", "bad-email", "", "", "", ""]]
        jid, b, pv = full(A["s"], rows, "persone", options={"event_id": A["ev"]})
        b["options"] = {"event_id": A["ev"]}
        pv = preview(A["s"], jid, b)
        assert pv["counts"]["nuovo"] == 2 and pv["counts"]["duplicato_file"] == 1 and pv["counts"]["errore"] == 1, pv["counts"]
        assert pv["actions"]["crea"] == 2
        assert MDB.persons.count_documents({"org_id": A["org"], "email": em}) == 0
        res = run(A["s"], jid, b)
        assert res["creati"] == 2 and res["ignorati"] == 2
        p = MDB.persons.find_one({"org_id": A["org"], "email": em})
        assert p["provenienza"]["tipo"] == "importazione"
        st = MDB.staff.find_one({"org_id": A["org"], "persona_id": p["id"], "evento_id": A["ev"]})
        assert st["categoria"] == "volontario" and st["ruolo"] == "Cassa"
        b2 = MDB.persons.find_one({"org_id": A["org"], "nome": "TEST_Bea"})
        st2 = MDB.staff.find_one({"org_id": A["org"], "persona_id": b2["id"]})
        assert st2["categoria"] == "staff" and st2["team_id"] == st["team_id"]
        assert MDB.teams.count_documents({"org_id": A["org"], "evento_id": A["ev"]}) == 1
        run(A["s"], jid, b, code=409)
        h = A["s"].get(f"{BASE_URL}/api/imports/history").json()
        hj = next(x for x in h if x["id"] == jid)
        assert hj["result"]["creati"] == 2 and len(hj["result"]["errori"]) == 2
        r = A["s"].get(f"{BASE_URL}/api/imports/jobs/{jid}/errors.csv")
        assert r.status_code == 200 and "Riga" in r.text and "duplicato_file" in r.text
        A["p1"] = p["id"]
        A["p1_email"] = em

    def test_update_empty_cell_and_keys(self, A):
        em = A["p1_email"]
        # match by email, empty cell for cellulare must not clear it; new value for citta
        jid, b, pv = full(A["s"], [["Nome", "Cognome", "Mail", "Cell", "Città"], ["TEST_Anna", "Rossi", em.upper(), "", "Bergamo"]], "persone", mode="update")
        assert pv["counts"]["esistente"] == 1 and pv["actions"]["aggiorna"] == 1
        run(A["s"], jid, b)
        p = MDB.persons.find_one({"org_id": A["org"], "id": A["p1"]})
        assert p["cellulare"] and "3401234567" in p["cellulare"].replace(" ", "") and p["citta"] == "Bergamo"
        assert MDB.persons.count_documents({"org_id": A["org"], "nome": "TEST_Anna"}) == 1
        # match by cellulare with prefix
        _, _, pv = full(A["s"], [["Nome", "Cell"], ["TEST_Anna", "+39 340 123 4567"]], "persone")
        assert pv["counts"]["esistente"] == 1

    def test_possibile_duplicato_and_conflict(self, A):
        MDB.persons.insert_one({"id": uuid.uuid4().hex, "org_id": A["org"], "nome": "TEST_Dup", "cognome": "Uno", "data_nascita": "1990-03-04"})
        _, _, pv = full(A["s"], [["Nome", "Cognome", "Data di nascita"], ["TEST_Dup", "Uno", "04/03/1990"]], "persone")
        assert pv["counts"]["possibile_duplicato"] == 1 and pv["actions"]["crea"] == 0, pv
        # email of person1 + cell of Bea -> conflitto
        _, _, pv = full(A["s"], [["Nome", "Mail", "Cell"], ["TEST_X", A["p1_email"], "3409999888"]], "persone")
        assert pv["counts"]["conflitto"] == 1

    def test_undo(self, A):
        jid, b, pv = full(A["s"], [["Nome", "Cognome", "Mail"], ["TEST_Undo1", "A", f"u1_{U}@example.com"], ["TEST_Undo2", "B", f"u2_{U}@example.com"]], "persone")
        run(A["s"], jid, b)
        p2 = MDB.persons.find_one({"org_id": A["org"], "nome": "TEST_Undo2"})
        r = A["s"].put(f"{BASE_URL}/api/persons/{p2['id']}", json={"nome": "TEST_Undo2", "cognome": "Modificato"})
        if r.status_code >= 400:
            MDB.persons.update_one({"id": p2["id"]}, {"$set": {"updated_at": "2999-01-01"}})
        u = A["s"].post(f"{BASE_URL}/api/imports/jobs/{jid}/undo")
        assert u.status_code == 200, u.text
        assert u.json() == {"rimossi": 1, "mantenuti": 1}
        assert not MDB.persons.find_one({"org_id": A["org"], "nome": "TEST_Undo1"})
        assert MDB.persons.find_one({"id": p2["id"]})
        assert MDB.import_jobs.find_one({"id": jid})["status"] == "annullato"
        assert A["s"].post(f"{BASE_URL}/api/imports/jobs/{jid}/undo").status_code == 409


# ---------- soci (module inactive, super admin) ----------
class TestSoci:
    def test_org_admin_forbidden_and_hidden(self, A):
        t = A["s"].get(f"{BASE_URL}/api/imports/targets").json()
        assert "soci" not in [x["key"] for x in t["targets"]] and not t["superadmin"]
        j = upload(A["s"], csv_bytes([["Nome"], ["TEST_s"]]))
        preview(A["s"], j["id"], body("soci", {"Nome": "nome"}), code=403)
        run(A["s"], j["id"], body("soci", {"Nome": "nome"}), code=403)
        assert A["s"].get(f"{BASE_URL}/api/imports/templates/soci").status_code == 403

    def test_superadmin_imports_soci(self, A, SA):
        t = SA.get(f"{BASE_URL}/api/imports/targets").json()
        so = next(x for x in t["targets"] if x["key"] == "soci")
        assert t["superadmin"] and so["active"] is False
        rows = [["Nome", "Cognome", "Mail", "Federazione", "Stagione", "Numero tessera", "Quota: importo", "Quota: descrizione"],
                ["TEST_Socio", "Uno", f"socio1_{U}@example.com", "CSI", "2025/2026", "T123", "50,00", "Quota annuale"],
                ["TEST_Anna", "Rossi", A["p1_email"], "ENTE_FAKE", "2025/2026", "", "", ""]]
        jid, b, pv = full(SA, rows, "soci")
        assert pv["counts"]["nuovo"] == 1 and pv["counts"]["esistente"] == 1, pv["counts"]
        res = run(SA, jid, b)
        assert res["creati_per_collezione"].get("asd_soci") == 2 and res["creati_per_collezione"].get("asd_tesseramenti") == 1
        assert res["creati_per_collezione"].get("asd_quote") == 1 and res["creati_per_collezione"].get("persons") == 1
        assert any("ENTE_FAKE" in e["messaggio"] for e in res["errori"])
        assert not MDB.org_services.find_one({"org_id": A["org"], "service": "gestione-societa"})
        assert MDB.persons.count_documents({"org_id": A["org"], "email": A["p1_email"]}) == 1
        q = MDB.asd_quote.find_one({"org_id": A["org"]})
        assert q["importo"] == 50.0
        assert A["s"].get(f"{BASE_URL}/api/asd/soci").status_code == 403
        MDB.org_services.insert_one({"org_id": A["org"], "service": "gestione-societa", "active": True})
        r = A["s"].get(f"{BASE_URL}/api/asd/soci")
        assert r.status_code == 200, r.text
        rows = r.json() if isinstance(r.json(), list) else r.json().get("items", r.json().get("soci", []))
        assert len(rows) == 2
        MDB.org_services.delete_many({"org_id": A["org"]})


# ---------- pipeline ----------
def activate_pipes(A):
    # l'organizzatore importa solo nelle pipeline attive (il Super Admin anche in quelle non attive)
    for e in MDB.events.find({"org_id": A["org"]}, {"_id": 0, "id": 1}):
        MDB.event_pipelines.update_one({"org_id": A["org"], "event_id": e["id"]}, {"$set": {"active": True}, "$setOnInsert": {"id": uuid.uuid4().hex}}, upsert=True)


class TestPipeline:
    def test_format_a(self, A, SA):
        MDB.persons.insert_one({"id": uuid.uuid4().hex, "org_id": A["org"], "nome": "TEST_Mario", "cognome": "Bianchi"})
        credits_before = MDB.organizations.find_one({"id": A["org"]}, {"_id": 0})
        rows = [["Attività", "Fase", "Stato", "Responsabile", "Scadenza", "Priorità"],
                ["TEST_Permesso", "Da iniziare", "Da fare", "TEST_Mario Bianchi", "01/05/2026", "Alta"],
                ["TEST_Palco", "Logistica TEST", "Completato", "Nessuno Tizio", "", ""],
                ["TEST_Skip", "Scarta", "", "", "", ""]]
        opts = {"event_id": A["ev"], "fasi": {"Da iniziare": {"action": "use", "name": "Autorizzazioni"}, "Scarta": {"action": "skip"}}}
        jid, b, pv = full(SA, rows, "pipeline", options=opts)
        assert pv["actions"]["crea"] == 2, pv
        assert "Logistica TEST" in pv["pipeline"]["fasi_da_creare"] and "Scarta" not in pv["pipeline"]["fasi_da_creare"]
        assert pv["pipeline"]["responsabili_collegati"] == 1 and pv["pipeline"]["eventi_senza_pipeline_attiva"]
        assert MDB.pipeline_tasks.count_documents({"org_id": A["org"]}) == 0
        run(SA, jid, b)
        t1 = MDB.pipeline_tasks.find_one({"org_id": A["org"], "titolo": "TEST_Permesso"})
        t2 = MDB.pipeline_tasks.find_one({"org_id": A["org"], "titolo": "TEST_Palco"})
        assert t2["stato"] == "completata" and t1["stato"] == "da_fare" and t1["priorita"] == "importante" and t1["scadenza"] == "2026-05-01"
        assert t1["responsabile_id"] and "responsabile_id" not in t2
        c1 = MDB.pipeline_categories.find_one({"id": t1["categoria_id"]})
        assert c1["name"].lower() == "autorizzazioni"
        assert not MDB.pipeline_tasks.find_one({"org_id": A["org"], "titolo": "TEST_Skip"})
        assert not MDB.event_pipelines.find_one({"org_id": A["org"], "event_id": A["ev"]})
        assert MDB.organizations.find_one({"id": A["org"]}, {"_id": 0}) == credits_before
        # visibility
        r = A["s"].get(f"{BASE_URL}/api/events/{A['ev']}/pipeline/tasks").json()
        assert r["tasks"] == []
        assert A["s"].get(f"{BASE_URL}/api/events/{A['ev']}/pipeline/categories").json() == []
        assert len(SA.get(f"{BASE_URL}/api/events/{A['ev']}/pipeline/tasks").json()["tasks"]) == 2
        A["rows_a"], A["t1"] = rows, t1["id"]

    def test_reimport_and_conflict(self, A, SA):
        opts = {"event_id": A["ev"], "fasi": {"Da iniziare": {"action": "use", "name": "Autorizzazioni"}, "Scarta": {"action": "skip"}}}
        _, _, pv = full(SA, A["rows_a"], "pipeline", options=opts)
        assert pv["counts"]["esistente"] == 2 and pv["actions"]["aggiorna"] == 2, pv["counts"]
        r = SA.put(f"{BASE_URL}/api/pipeline/tasks/{A['t1']}", json={"descrizione": "modificata"})
        assert r.status_code == 200, r.text
        _, _, pv = full(SA, A["rows_a"], "pipeline", options=opts)
        assert pv["counts"]["conflitto"] == 1 and pv["counts"]["esistente"] == 1
        jid, b, pv = full(SA, A["rows_a"], "pipeline", options={**opts, "sovrascrivi_modificate": True})
        assert pv["counts"]["esistente"] == 2
        res = run(SA, jid, b)
        assert res["aggiornati"] == 2
        assert MDB.pipeline_tasks.count_documents({"org_id": A["org"], "event_id": A["ev"]}) == 2

    def test_activate_then_visible(self, A):
        MDB.event_pipelines.insert_one({"org_id": A["org"], "event_id": A["ev"], "active": True})
        r = A["s"].get(f"{BASE_URL}/api/events/{A['ev']}/pipeline/tasks").json()
        assert len(r["tasks"]) == 2
        MDB.event_pipelines.delete_many({"org_id": A["org"]})

    def test_format_b_columns(self, A):
        activate_pipes(A)
        rows = [["Da fare", "In corso", "Completato"], ["TEST_B1", "TEST_B2", ""], ["TEST_B3", "", "TEST_B4"]]
        j = upload(A["s"], csv_bytes(rows))
        rd = read(A["s"], j["id"], "pipeline", layout="columns")
        assert rd["columns"] == ["Attività", "Fase"] and rd["total"] == 4
        b = body("pipeline", {}, options={"event_id": A["ev2"]}, layout="columns")
        pv = preview(A["s"], j["id"], b)
        assert pv["actions"]["crea"] == 4
        run(A["s"], j["id"], b)
        tasks = list(MDB.pipeline_tasks.find({"org_id": A["org"], "event_id": A["ev2"]}))
        assert len(tasks) == 4
        cats = {c["id"]: c["name"] for c in MDB.pipeline_categories.find({"org_id": A["org"], "event_id": A["ev2"]})}
        m = {t["titolo"]: cats.get(t.get("categoria_id")) for t in tasks}
        assert m["TEST_B1"].lower() == "da fare" and m["TEST_B4"].lower() == "completato"

    def test_format_c_sheets(self, A):
        activate_pipes(A)
        data = xlsx_bytes({"S1": [["Attività", "Fase"], ["TEST_C1", "TEST_FaseC"]], "S2": [["Attività", "Fase"], ["TEST_C2", "TEST_FaseC"], ["TEST_C3", "TEST_FaseC"]]})
        j = upload(A["s"], data, "c.xlsx")
        rd = read(A["s"], j["id"], "pipeline", sheet="S1")
        b = body("pipeline", rd["suggested"], options={"sheets": [{"sheet": "S1", "event_id": A["ev"]}, {"sheet": "S2", "event_id": A["ev2"]}]})
        pv = preview(A["s"], j["id"], b)
        assert pv["actions"]["crea"] == 3, pv
        run(A["s"], j["id"], b)
        assert MDB.pipeline_tasks.find_one({"org_id": A["org"], "titolo": "TEST_C1"})["event_id"] == A["ev"]
        assert MDB.pipeline_tasks.find_one({"org_id": A["org"], "titolo": "TEST_C3"})["event_id"] == A["ev2"]

    def test_event_by_exact_name(self, A):
        activate_pipes(A)
        rows = [["Attività", "Pipeline"], ["TEST_E1", f"TEST_Gara {U}"], ["TEST_E2", "TEST_Gara"]]
        _, _, pv = full(A["s"], rows, "pipeline")
        assert pv["actions"]["crea"] == 1 and pv["counts"]["errore"] == 1, pv["counts"]


# ---------- aziende / sponsor / ospitalità ----------
class TestOthers:
    def test_aziende_dedupe(self, A):
        rows = [["Ragione sociale", "Partita IVA", "Città"], [f"TEST_Az {U}", "IT01234567890", "Milano"]]
        jid, b, pv = full(A["s"], rows, "aziende")
        assert pv["counts"]["nuovo"] == 1
        run(A["s"], jid, b)
        _, _, pv = full(A["s"], [["Ragione sociale", "Partita IVA"], ["Altro Nome", "IT01234567890"]], "aziende")
        assert pv["counts"]["esistente"] == 1
        _, _, pv = full(A["s"], [["Ragione sociale"], [f"test_az {U}".upper()]], "aziende")
        assert pv["counts"]["esistente"] == 1

    def test_sponsor_deal(self, A):
        rows = [["Azienda", "Valore", "Tipo"], [f"TEST_Az {U}", "1000", "sponsor"]]
        jid, b, pv = full(A["s"], rows, "sponsor", options={"event_id": A["ev"]})
        assert pv["counts"]["nuovo"] == 1
        run(A["s"], jid, b)
        d = MDB.deals.find_one({"org_id": A["org"], "evento_id": A["ev"]})
        assert d and d["valore"] == 1000.0
        assert MDB.companies.count_documents({"org_id": A["org"]}) == 1
        _, _, pv = full(A["s"], rows, "sponsor", options={"event_id": A["ev"]})
        assert pv["counts"]["esistente"] == 1
        _, _, pv = full(A["s"], rows, "sponsor")
        assert pv["counts"]["errore"] == 1

    def test_lodging_meals(self, A):
        rows = [["Persona", "Hotel", "Check-in", "Check-out"], ["TEST_Anna Rossi", "TEST_Hotel", "01/09/2026", "02/09/2026"], ["Sconosciuto Tizio", "H", "", ""]]
        jid, b, pv = full(A["s"], rows, "pernottamenti", options={"event_id": A["ev"]})
        assert pv["counts"]["nuovo"] == 1 and pv["counts"]["errore"] == 1, pv["counts"]
        run(A["s"], jid, b)
        assert MDB.lodgings.find_one({"org_id": A["org"], "persona_id": A["p1"]})["struttura_nome"] == "TEST_Hotel"
        rows = [["Persona", "Tipo pasto", "Data"], ["TEST_Anna Rossi", "pranzo", "01/09/2026"]]
        jid, b, pv = full(A["s"], rows, "pasti", options={"event_id": A["ev"]})
        assert pv["counts"]["nuovo"] == 1
        run(A["s"], jid, b)
        assert MDB.meals.find_one({"org_id": A["org"], "persona_id": A["p1"]})


# ---------- configs / templates / isolation ----------
class TestConfigsIsolation:
    def test_configs(self, A, B, SA):
        r = A["s"].post(f"{BASE_URL}/api/imports/configs", json={"name": "TEST_cfg", "target": "persone", "mapping": {"Mail": "email"}})
        assert r.status_code == 200
        cid = r.json()["id"]
        CFG_IDS.append(cid)
        assert A["s"].put(f"{BASE_URL}/api/imports/configs/{cid}", json={"name": "TEST_cfg2", "target": "persone", "mapping": {}}).status_code == 200
        assert any(c["name"] == "TEST_cfg2" for c in A["s"].get(f"{BASE_URL}/api/imports/configs").json())
        assert not any(c["id"] == cid for c in B["s"].get(f"{BASE_URL}/api/imports/configs").json())
        assert B["s"].delete(f"{BASE_URL}/api/imports/configs/{cid}").status_code == 404
        assert A["s"].delete(f"{BASE_URL}/api/imports/configs/{cid}").status_code == 200
        assert A["s"].post(f"{BASE_URL}/api/imports/configs", json={"name": "TEST_g", "target": "persone", "globale": True}).status_code == 403
        g = SA.post(f"{BASE_URL}/api/imports/configs", json={"name": f"TEST_global_{U}", "target": "persone", "globale": True})
        assert g.status_code == 200 and g.json()["org_id"] is None
        gid = g.json()["id"]
        CFG_IDS.append(gid)
        assert any(c["id"] == gid for c in B["s"].get(f"{BASE_URL}/api/imports/configs").json())
        assert B["s"].put(f"{BASE_URL}/api/imports/configs/{gid}", json={"name": "x", "target": "persone"}).status_code == 403
        assert B["s"].delete(f"{BASE_URL}/api/imports/configs/{gid}").status_code == 403
        assert SA.delete(f"{BASE_URL}/api/imports/configs/{gid}").status_code == 200

    def test_template_pipeline(self, A):
        r = A["s"].get(f"{BASE_URL}/api/imports/templates/pipeline")
        assert r.status_code == 200
        ws = openpyxl.load_workbook(io.BytesIO(r.content)).active
        hdr = [c.value for c in ws[1]]
        for h in ("Titolo attività", "Descrizione", "Fase / Categoria", "Responsabile", "Priorità", "Evento / Pipeline", "Data scadenza", "Note"):
            assert h in hdr

    def test_isolation(self, A, B):
        j = upload(A["s"], csv_bytes([["Nome"], ["TEST_iso"]]))
        assert B["s"].post(f"{BASE_URL}/api/imports/jobs/{j['id']}/read", json={}).status_code == 404
        assert B["s"].post(f"{BASE_URL}/api/imports/jobs/{j['id']}/preview", json=body("persone", {"Nome": "nome"})).status_code == 404
        assert B["s"].get(f"{BASE_URL}/api/imports/jobs/{j['id']}/errors.csv").status_code == 404
        # X-Org-Id ignored/rejected for non-superadmin
        r = B["s"].post(f"{BASE_URL}/api/imports/jobs/{j['id']}/read", json={}, headers={"X-Org-Id": A["org"]})
        assert r.status_code in (403, 404)
