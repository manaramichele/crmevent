# Control Room Phase 4: KPI dashboard, diary (filters + post/resource/sector rows, not deletable), final report PDF/XLSX (permissions, tenant, 402, logo), regression smoke
import io, os
from datetime import datetime, timedelta, timezone
import pytest, requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
API = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/") + "/api"
PWD = "TestCR2026!"
PNG_1x1 = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                        "1f15c4890000000d49444154789c6360f8cfc0f01f0005000201a5f5e6d40000000049454e44ae426082")


def _login(email, org=None):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": PWD})
    if r.status_code != 200:
        pytest.skip(f"login failed {email}: {r.status_code}")
    s.headers["Authorization"] = f"Bearer {s.cookies.get('access_token')}"
    if org:
        s.headers["X-Org-Id"] = org
    return s


_A = _login("test_cr_a@crmevent-test.it")
_EVS = _A.get(f"{API}/controlroom/events").json()["events"]
EV_A = next(e["id"] for e in _EVS if e["nome"] == "TEST_CR Gara A")
EV_INA = next(e["id"] for e in _EVS if "Non attivo" in e["nome"])
OPS = f"{API}/controlroom/events/{EV_A}/ops"
ORG_A = None


def state(s):
    r = s.get(OPS)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def A():
    return _A


@pytest.fixture(scope="module")
def org_a(A):
    me = A.get(f"{API}/auth/me").json()
    return me.get("org_id") or (me.get("user") or {}).get("org_id")


@pytest.fixture(scope="module")
def B():
    return _login("test_cr_b@crmevent-test.it")


@pytest.fixture(scope="module")
def C(org_a):
    return _login("test_cr_c@crmevent-test.it", org_a)


@pytest.fixture(scope="module")
def W(A):
    made, itvs = [], []
    def mk(kind, body):
        r = A.post(f"{OPS}/{kind}", json=body)
        assert r.status_code == 200, r.text
        made.append((kind, r.json()["id"]))
        return r.json()
    yield {"mk": mk, "itvs": itvs}
    for iid in itvs:
        it = next((i for i in state(A)["interventions"] if i["id"] == iid), None)
        if it and it["stato"] not in ("chiuso", "annullato"):
            A.post(f"{OPS}/interventions/{iid}/status", json={"to": "annullato", "motivo": "TEST cleanup", "force": True, "note": "cleanup", "version": it["version"]})
    for kind, oid in reversed(made):
        A.delete(f"{OPS}/{kind}/{oid}")


KPI_KEYS = ["postazioni_attive", "postazioni_presidiate", "postazioni_non_presidiate", "volontari_presenti", "squadre_disponibili", "squadre_impegnate",
            "segnalazioni_aperte", "interventi_in_corso", "interventi_risolti", "criticita_rosse"]


class TestKpi:
    def test_keys(self, A):
        k = state(A)["kpi"]
        for key in KPI_KEYS:
            assert key in k and isinstance(k[key], int), key

    def test_values_change(self, A, W):
        k0 = state(A)["kpi"]
        sec = W["mk"]("sectors", {"nome": "TEST_P4 Sett", "km_inizio": 50, "km_fine": 60, "responsabile": "TEST Resp Sett", "telefono": "+39 333 0000001"})
        p_full = W["mk"]("posts", {"nome": "TEST_P4 Full", "previsti": 1, "km": 51, "sector_id": sec["id"], "lng": 12.5, "lat": 41.9, "responsabile": "TEST Resp Post", "telefono": "+39 333 0000002"})
        p_part = W["mk"]("posts", {"nome": "TEST_P4 Part", "previsti": 2, "km": 52})
        r1 = W["mk"]("resources", {"kind": "persona", "nome": "TEST_P4 Op1", "post_id": p_full["id"]})
        r2 = W["mk"]("resources", {"kind": "persona", "nome": "TEST_P4 Op2", "post_id": p_part["id"]})
        sq = W["mk"]("resources", {"kind": "squadra", "nome": "TEST_P4 Squadra"})
        W.update(sec=sec, p_full=p_full, p_part=p_part, r1=r1, r2=r2, sq=sq)
        for rid in (r1["id"], r2["id"]):
            assert A.post(f"{OPS}/resources/{rid}/presence", json={"presente": True}).status_code == 200
        k1 = state(A)["kpi"]
        assert k1["postazioni_attive"] == k0["postazioni_attive"] + 2
        assert k1["postazioni_presidiate"] == k0["postazioni_presidiate"] + 1
        assert k1["postazioni_non_presidiate"] == k0["postazioni_non_presidiate"] + 1  # parziale counted as non presidiata
        assert k1["volontari_presenti"] == k0["volontari_presenti"] + 2
        assert k1["squadre_disponibili"] == k0["squadre_disponibili"] + 1
        sqv = next(x for x in state(A)["resources"] if x["id"] == sq["id"])["version"]
        assert A.patch(f"{OPS}/resources/{sq['id']}/status", json={"stato": "impegnato", "version": sqv}).status_code == 200
        r = A.post(f"{OPS}/interventions", json={"tipologia": "sanitario", "priorita": "alta", "descrizione": "TEST_P4 alta", "riferimento": "TEST km 51"})
        assert r.status_code == 200, r.text
        it = r.json(); W["itvs"].append(it["id"]); W["it_alta"] = it
        r = A.post(f"{OPS}/interventions", json={"tipologia": "sanitario", "priorita": "bassa", "descrizione": "TEST_P4 bassa", "riferimento": "TEST km 52"})
        it2 = r.json(); W["itvs"].append(it2["id"]); W["it_bassa"] = it2
        k2 = state(A)["kpi"]
        assert k2["squadre_impegnate"] == k1["squadre_impegnate"] + 1
        assert k2["squadre_disponibili"] == k1["squadre_disponibili"] - 1
        assert k2["segnalazioni_aperte"] == k1["segnalazioni_aperte"] + 2
        assert k2["criticita_rosse"] == k1["criticita_rosse"] + 1  # bassa not counted
        for to in ("preso_in_carico", "squadra_inviata"):
            v = next(i for i in state(A)["interventions"] if i["id"] == it["id"])["version"]
            assert A.post(f"{OPS}/interventions/{it['id']}/status", json={"to": to, "version": v}).status_code == 200
        k3 = state(A)["kpi"]
        assert k3["interventi_in_corso"] == k2["interventi_in_corso"] + 1
        assert k3["segnalazioni_aperte"] == k2["segnalazioni_aperte"] - 1
        for to in ("sul_posto", "risolto"):
            v = next(i for i in state(A)["interventions"] if i["id"] == it["id"])["version"]
            assert A.post(f"{OPS}/interventions/{it['id']}/status", json={"to": to, "version": v}).status_code == 200
        k4 = state(A)["kpi"]
        assert k4["interventi_risolti"] == k3["interventi_risolti"] + 1
        assert k4["interventi_in_corso"] == k3["interventi_in_corso"] - 1
        assert k4["criticita_rosse"] == k3["criticita_rosse"]  # risolto is still open (not chiuso) -> still red
        print("KPI k0..k4", k0, k4)


class TestDiary:
    def test_entity_rows(self, A, W):
        rows = A.get(f"{OPS}/diary").json()["rows"]
        texts = [(x["type"], x["text"]) for x in rows]
        assert any(t == "postazione" and "TEST_P4 Full" in tx for t, tx in texts), texts[-10:]
        assert any(t == "settore" and "TEST_P4 Sett" in tx for t, tx in texts)
        assert any(t == "risorsa" and "TEST_P4 Squadra" in tx for t, tx in texts)
        assert any(t == "risorsa" and "presence" in tx for t, tx in texts)

    def test_filter_type(self, A):
        rows = A.get(f"{OPS}/diary", params={"type": "postazione"}).json()["rows"]
        assert rows and all(x["type"] == "postazione" for x in rows)

    def test_filter_priority(self, A, W):
        rows = A.get(f"{OPS}/diary", params={"priorita": "alta"}).json()["rows"]
        assert rows and any(x.get("intervention_id") == W["it_alta"]["id"] for x in rows)
        assert not any(x.get("intervention_id") == W["it_bassa"]["id"] for x in rows)
        assert all(x.get("intervention_id") for x in rows)

    def test_filter_dates(self, A):
        now = datetime.now(timezone.utc)
        recent = A.get(f"{OPS}/diary", params={"dal": (now - timedelta(minutes=10)).isoformat()}).json()["rows"]
        assert recent and all(x["at"] >= (now - timedelta(minutes=10)).isoformat() for x in recent)
        # JS toISOString() format (Z suffix, ms) as sent by the UI
        z = (now - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        recent_z = A.get(f"{OPS}/diary", params={"dal": z}).json()["rows"]
        assert len(recent_z) == len(recent), (len(recent_z), len(recent))
        future = A.get(f"{OPS}/diary", params={"dal": (now + timedelta(hours=1)).isoformat()}).json()["rows"]
        assert future == []
        old = A.get(f"{OPS}/diary", params={"al": "2000-01-01T00:00:00+00:00"}).json()["rows"]
        assert old == []

    def test_filter_operator(self, A):
        all_rows = A.get(f"{OPS}/diary").json()["rows"]
        name = next(x["by_name"] for x in reversed(all_rows) if x.get("by_name"))
        rows = A.get(f"{OPS}/diary", params={"operatore": name[:4].lower()}).json()["rows"]
        assert rows and all(name[:4].lower() in (x["by_name"] or "").lower() for x in rows)
        assert A.get(f"{OPS}/diary", params={"operatore": "zz_nobody_zz"}).json()["rows"] == []

    def test_not_deletable(self, A):
        rows = A.get(f"{OPS}/diary").json()["rows"]
        n = len(rows)
        assert A.delete(f"{OPS}/diary").status_code in (404, 405)
        assert A.delete(f"{OPS}/diary/{rows[0]['id']}").status_code in (404, 405)
        assert len(A.get(f"{OPS}/diary").json()["rows"]) >= n


class TestReport:
    def test_pdf_ok(self, A, W):
        import fitz
        r = A.get(f"{OPS}/report.pdf")
        assert r.status_code == 200, r.text[:300]
        assert r.headers["content-type"].startswith("application/pdf") and r.content[:4] == b"%PDF"
        assert "attachment" in r.headers.get("content-disposition", "")
        doc = fitz.open(stream=r.content, filetype="pdf")
        text = "\n".join(p.get_text() for p in doc)
        for sec in ("Report Control Room", "TEST_CR Gara A", "Riepilogo", "Segnalazioni per categoria", "Postazioni", "Personale e mezzi", "Criticità principali",
                    "Interventi effettuati", "Interventi rimasti aperti", "Cronologia delle attività", "TEST_P4 Full", W["it_alta"]["codice"]):
            assert sec in text, sec
        W["pdf_text"] = text
        print("PDF pages", len(doc), "images p1:", len(doc[0].get_images()))
        if "alta (alta" in text:
            print("WARN: criticità priorità rendered doubled e.g. 'alta (alta (Rosso))'")

    def test_xlsx_ok(self, A):
        from openpyxl import load_workbook
        r = A.get(f"{OPS}/report.xlsx")
        assert r.status_code == 200, r.text[:300]
        wb = load_workbook(io.BytesIO(r.content))
        assert wb.sheetnames == ["Riepilogo", "Postazioni", "Personale", "Interventi", "Cronologia"], wb.sheetnames
        rie = {row[0].value: row[1].value for row in wb["Riepilogo"].iter_rows(min_row=2)}
        assert rie["Evento"] == "TEST_CR Gara A"
        heads = [c.value for c in wb["Interventi"][1]]
        assert "Presa in carico (min)" in heads and "Risoluzione (min)" in heads
        assert wb["Cronologia"].max_row > 1

    def test_collab_403(self, C):
        for ext in ("pdf", "xlsx"):
            r = C.get(f"{OPS}/report.{ext}")
            assert r.status_code == 403, (ext, r.status_code, r.text[:200])

    def test_org_b_404(self, B):
        for ext in ("pdf", "xlsx"):
            assert B.get(f"{OPS}/report.{ext}").status_code == 404

    def test_inactive_402(self, A):
        for ext in ("pdf", "xlsx"):
            assert A.get(f"{API}/controlroom/events/{EV_INA}/ops/report.{ext}").status_code == 402

    def test_unauth_401(self):
        assert requests.get(f"{OPS}/report.pdf").status_code in (401, 403)

    def test_logo_in_header(self, A):
        """Upload a PNG, set it as the TEST event logo_url directly in DB (no UI for this here), check that the PDF embeds an image; restore."""
        import fitz
        from pymongo import MongoClient
        up = A.post(f"{API}/upload", files={"file": ("test_logo.png", PNG_1x1, "image/png")})
        assert up.status_code == 200, up.text
        url = up.json()["url"]
        db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        prev = db.events.find_one({"id": EV_A}, {"_id": 0, "logo_url": 1}).get("logo_url")
        try:
            db.events.update_one({"id": EV_A}, {"$set": {"logo_url": url}})
            r = A.get(f"{OPS}/report.pdf")
            assert r.status_code == 200
            doc = fitz.open(stream=r.content, filetype="pdf")
            assert len(doc[0].get_images()) >= 1, "logo not embedded in PDF header"
        finally:
            db.events.update_one({"id": EV_A}, {"$set": {"logo_url": prev}})


class TestMobileContacts:
    def test_m_home_contacts(self, A, W):
        inv = A.post(f"{OPS}/invites", json={"resource_id": W["r1"]["id"], "days": 1})
        assert inv.status_code == 200, inv.text
        tok = inv.json()["token"]
        W["inv"] = inv.json()["id"]
        d = requests.get(f"{API}/cr-mobile/{tok}").json()
        assert d["post"]["telefono"] == "+39 333 0000002" and d["post"]["lng"] == 12.5
        assert d["sector"]["telefono"] == "+39 333 0000001" and d["sector"]["responsabile"] == "TEST Resp Sett"
        assert A.delete(f"{OPS}/invites/{W['inv']}").status_code == 200
