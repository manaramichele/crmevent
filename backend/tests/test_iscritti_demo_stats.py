# Elenco Iscritti – Demo seed (idempotent) + /api/iscritti/stats (KPI/charts/filters) + Brevo exclusion of demo records
import os
from collections import Counter

import pytest
import requests
from pymongo import MongoClient

BASE_URL = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0].rstrip("/")
API = f"{BASE_URL}/api"
OID = "b7f40862230441b9a0bedabefe8dab49"
SA = {"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"}
_env = dict(l.strip().split("=", 1) for l in open("/app/backend/.env") if "=" in l)
DB = MongoClient(_env["MONGO_URL"].strip('"'))[_env["DB_NAME"].strip('"')]


@pytest.fixture(scope="module")
def sa():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=SA)
    if r.status_code != 200:
        pytest.skip(f"SA login failed {r.status_code}")
    return s


@pytest.fixture(scope="module")
def org(sa):
    s = requests.Session()
    s.cookies.update(sa.cookies)
    s.headers["X-Org-Id"] = OID
    return s


def eds():
    return {e["anno"]: e for e in DB.iscritti_edizioni.find({"org_id": OID}, {"_id": 0})}


# --- Demo seed idempotency ---
class TestDemoSeed:
    def test_seed_requires_sa(self):
        assert requests.post(f"{API}/platform/iscritti/demo-seed").status_code in (401, 403)

    @pytest.mark.parametrize("run", [1, 2])
    def test_seed_idempotent(self, sa, run):
        r = sa.post(f"{API}/platform/iscritti/demo-seed", timeout=180)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["org_id"] == OID
        assert d["iscritti"] == 6220
        assert d["partecipazioni"] == {"2024": 1850, "2025": 2640, "2026": 3420}
        assert d["totale_partecipazioni"] == 7910
        assert DB.iscritti_edizioni.count_documents({"org_id": OID}) == 3
        assert DB.events.count_documents({"org_id": OID, "nome": "Maratona Demo"}) == 1

    def test_demo_data_markers(self):
        assert DB.iscritti.count_documents({"org_id": OID, "demo": True, "brevo_status": "demo_escluso"}) == 6220
        assert DB.iscritti.count_documents({"org_id": OID, "email": {"$not": {"$regex": "@example\\.com$"}}}) == 0
        assert set(DB.iscritti_partecipazioni.distinct("gara", {"org_id": OID})) == {"Maratona 42K", "Mezza Maratona 21K", "10K"}
        svc = DB.org_services.find_one({"org_id": OID, "service": "archivio-iscritti"})
        assert svc and svc["active"] is True


# --- Stats endpoint ---
class TestStats:
    def test_stats_all(self, org):
        r = org.get(f"{API}/iscritti/stats")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["demo"] is True and d["org_nome"] == "Demo"
        k = d["kpi"]
        assert k["totale"] == 7910 and k["unici"] == 6220
        assert k["ricorrenti"] == 6220 - (7910 - 610 - 1080) or k["ricorrenti"] > 0
        assert [e["n"] for e in d["evolution"]] == [1850, 2640, 3420]
        assert k["variazione"] == round((3420 - 2640) * 100 / 2640, 1)
        assert round(k["uomini_pct"] + k["donne_pct"]) == 100
        for key in ("evolution", "distance", "gender", "ages", "nationalities", "new_recurring", "trend"):
            assert d[key], key
        assert [a["fascia"] for a in d["ages"]] == ["Under 25", "25–34", "35–44", "45–54", "55–64", "Over 65"]
        nr = d["new_recurring"]
        assert nr[0]["Ricorrenti"] == 0 and nr[1]["Ricorrenti"] == 610 and nr[2]["Ricorrenti"] >= 1080
        # distance per edition matches DB
        for row, (anno, e) in zip(d["distance"], sorted(eds().items())):
            c = Counter(p["gara"] for p in DB.iscritti_partecipazioni.find({"edizione_id": e["id"]}, {"gara": 1}))
            assert {g: row[g] for g in d["gare"]} == dict(c)
        # distanza top matches DB
        c = Counter(p["gara"] for p in DB.iscritti_partecipazioni.find({"org_id": OID}, {"gara": 1}))
        assert k["distanza_top"] == c.most_common(1)[0][0]
        # nationality count matches DB
        ids = DB.iscritti.distinct("nazionalita", {"org_id": OID})
        assert k["nazionalita"] == len([n for n in ids if n])
        # trend last row (Evento) equals total per edition
        last = d["trend"][-1]
        assert [last[l] for l in d["labels"]] == [1850, 2640, 3420]

    def test_stats_anni_filter(self, org):
        d = org.get(f"{API}/iscritti/stats", params={"anni": "2025,2026"}).json()
        assert d["kpi"]["totale"] == 2640 + 3420
        assert [e["anno"] for e in d["evolution"]] == [2025, 2026]
        assert d["new_recurring"][0]["Ricorrenti"] == 610  # recurrence uses full history

    def test_stats_edizione_filter(self, org):
        e = eds()[2025]
        d = org.get(f"{API}/iscritti/stats", params={"edizione_id": e["id"]}).json()
        assert d["kpi"]["totale"] == 2640 and d["kpi"]["variazione"] is None
        assert len(d["evolution"]) == 1

    def test_stats_gara_filter(self, org):
        d = org.get(f"{API}/iscritti/stats", params={"gara": "10K"}).json()
        exp = DB.iscritti_partecipazioni.count_documents({"org_id": OID, "gara": "10K"})
        assert d["kpi"]["totale"] == exp and d["kpi"]["distanza_top"] == "10K"
        d2 = org.get(f"{API}/iscritti/stats", params={"gara": "10K", "anni": "2025,2026"}).json()
        assert d2["kpi"]["totale"] == DB.iscritti_partecipazioni.count_documents({"org_id": OID, "gara": "10K", "anno": {"$in": [2025, 2026]}})

    def test_stats_mode_months(self, org):
        dd = org.get(f"{API}/iscritti/stats").json()
        dm = org.get(f"{API}/iscritti/stats", params={"mode": "months"}).json()
        assert dm["trend_mode"] == "months" and dd["trend_mode"] == "days"
        assert dm["trend"][-1]["x"] == "Mese evento" and dd["trend"][-1]["x"] == "Evento"
        assert len(dm["trend"]) < len(dd["trend"])
        assert dm["trend"][-1] | {"x": 0} == dd["trend"][-1] | {"x": 0}
        # cumulative is monotonic
        for l in dm["labels"]:
            vals = [r[l] for r in dm["trend"]]
            assert vals == sorted(vals)

    def test_stats_empty_filter(self, org):
        d = org.get(f"{API}/iscritti/stats", params={"gara": "TEST_nonexistent"}).json()
        assert d["kpi"]["totale"] == 0

    def test_stats_no_org(self, sa):
        assert sa.get(f"{API}/iscritti/stats").status_code in (400, 401, 403, 428)


# --- Brevo exclusion ---
class TestBrevoExclusion:
    def test_sync_does_not_touch_demo(self, org):
        r = org.post(f"{API}/iscritti/brevo/sync")
        assert r.status_code == 200, r.text
        assert DB.iscritti.count_documents({"org_id": OID, "demo": True, "brevo_status": {"$ne": "demo_escluso"}}) == 0

    def test_list_and_export(self, org):
        r = org.get(f"{API}/iscritti", params={"limit": 20})
        assert r.status_code == 200
        assert r.json()["total"] == 6220
        x = org.get(f"{API}/iscritti/export", params={"format": "xlsx", "anno": "2026"})
        assert x.status_code == 200 and len(x.content) > 1000
