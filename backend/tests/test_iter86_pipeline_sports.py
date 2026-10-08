"""Iter 86 — Modelli Pipeline Sport (Triathlon, Nuoto, Ciclismo, MTB, Trail Running).

Test coverage:
- SA list: 7 templates A-Z with correct counts, idempotent re-seed
- Task structure: standard categories, valid priorities, order sorted by offset, auth/safety notes
- Triathlon-specific tasks (Sprint/Olimpico/Medio/Lungo)
- Task CRUD (edit, add TEST_, deactivate, restore)
- Delete model: 409 if used, OK if TEST_
- Event suggested=triathlon for Triathlon tipologia
- Pipeline generate -> 92 tasks, scadenze = event_date + offset
- Multi-tenant isolation
- Non-regression: other events' pipelines untouched
"""
import os
import json
import datetime
import requests
import pytest

def _read_base():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        v = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass
    assert v, "REACT_APP_BACKEND_URL missing"
    return v.rstrip("/")


BASE = _read_base()
SA = {"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"}
QA = {"email": "qa.eventi@crmeventqa.it", "password": "QaEvents2026!"}

STANDARD = {"Autorizzazioni", "Percorso", "Allestimenti", "Staff e volontari", "Sicurezza",
            "Iscrizioni", "Materiali", "Comunicazione", "Sponsor e partner", "Merchandising",
            "Logistica", "Post evento"}
PRIORITIES = {"normale", "importante", "critica"}

EXPECTED_COUNTS = {"running": 114, "generico": 32, "triathlon": 92, "nuoto_acque_libere": 77,
                   "ciclismo_strada": 77, "mountain_bike": 76, "trail_running": 93}
EXPECTED_NAMES_SORTED = ["Ciclismo su strada", "Evento generico", "Mountain Bike",
                        "Nuoto in acque libere", "Running", "Trail Running", "Triathlon"]


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def sa():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json=SA)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def qa():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json=QA)
    assert r.status_code == 200, r.text
    return s


# ---------- SA listing ----------
class TestPlatformList:
    def test_list_seven_templates_az_and_counts(self, sa):
        r = sa.get(f"{BASE}/api/platform/pipeline-templates")
        assert r.status_code == 200
        rows = r.json()["templates"]
        assert len(rows) == 7, [t["key"] for t in rows]
        names = [t["name"] for t in rows]
        assert names == EXPECTED_NAMES_SORTED, names
        for t in rows:
            assert t["task_count"] == EXPECTED_COUNTS[t["key"]], (t["key"], t["task_count"])
            assert "in_use" in t

    def test_idempotent_reseed(self, sa):
        # call twice: counts must not change (per key)
        r1 = sa.get(f"{BASE}/api/platform/pipeline-templates").json()["templates"]
        r2 = sa.get(f"{BASE}/api/platform/pipeline-templates").json()["templates"]
        c1 = {t["key"]: t["task_count"] for t in r1}
        c2 = {t["key"]: t["task_count"] for t in r2}
        assert c1 == c2


# ---------- Task structure ----------
NEW_KEYS = ["triathlon", "nuoto_acque_libere", "ciclismo_strada", "mountain_bike", "trail_running"]


class TestTaskStructure:
    @pytest.mark.parametrize("key", NEW_KEYS)
    def test_tasks_valid_and_ordered(self, sa, key):
        r = sa.get(f"{BASE}/api/platform/pipeline-templates/{key}/tasks")
        assert r.status_code == 200
        tasks = r.json()["tasks"]
        assert len(tasks) == EXPECTED_COUNTS[key]
        for t in tasks:
            assert t["categoria"] in STANDARD, (key, t["titolo"], t["categoria"])
            assert t["priorita"] in PRIORITIES, (key, t["priorita"])
        # order crescente per giorni_offset
        offsets = [t["giorni_offset"] for t in tasks]
        assert offsets == sorted(offsets), (key, "offsets not sorted")

    def test_triathlon_has_distances(self, sa):
        r = sa.get(f"{BASE}/api/platform/pipeline-templates/triathlon/tasks")
        titles = " || ".join(t["titolo"] for t in r.json()["tasks"])
        for word in ("Sprint", "Olimpico", "Medio", "Lungo"):
            assert word in titles, f"missing {word}"

    def test_authorizations_and_safety_have_verification_note(self, sa):
        V_SUB = "Verificare i requisiti"
        missing = []
        for key in NEW_KEYS:
            tasks = sa.get(f"{BASE}/api/platform/pipeline-templates/{key}/tasks").json()["tasks"]
            # at least one Autorizzazioni and one Sicurezza task must contain V note
            auth = [t for t in tasks if t["categoria"] == "Autorizzazioni"]
            safe = [t for t in tasks if t["categoria"] == "Sicurezza"]
            assert auth and safe, key
            if not any(V_SUB in (t.get("descrizione") or "") for t in auth):
                missing.append(f"{key}:Autorizzazioni")
            if not any(V_SUB in (t.get("descrizione") or "") for t in safe):
                missing.append(f"{key}:Sicurezza")
        assert not missing, missing


# ---------- Task CRUD on new model ----------
class TestTaskCRUD:
    def test_edit_add_deactivate_restore(self, sa):
        key = "mountain_bike"
        tasks = sa.get(f"{BASE}/api/platform/pipeline-templates/{key}/tasks").json()["tasks"]
        base_count = len(tasks)
        victim = tasks[5]
        original = {"titolo": victim["titolo"], "giorni_offset": victim["giorni_offset"],
                    "priorita": victim["priorita"], "active": victim.get("active", True)}
        tid = victim["id"]
        # edit title+offset+priority
        r = sa.put(f"{BASE}/api/platform/pipeline-template-tasks/{tid}",
                   json={"titolo": "TEST_edited_title", "giorni_offset": -999, "priorita": "critica"})
        assert r.status_code == 200, r.text
        got = r.json()
        assert got["titolo"] == "TEST_edited_title"
        assert got["giorni_offset"] == -999
        assert got["priorita"] == "critica"
        # add new task
        r = sa.post(f"{BASE}/api/platform/pipeline-templates/{key}/tasks",
                    json={"titolo": "TEST_new_task", "categoria": "Logistica",
                          "giorni_offset": -10, "priorita": "normale",
                          "descrizione": "test", "active": True})
        assert r.status_code == 200, r.text
        new_id = r.json()["id"]
        after = sa.get(f"{BASE}/api/platform/pipeline-templates/{key}/tasks").json()["tasks"]
        assert len(after) == base_count + 1
        # deactivate
        r = sa.put(f"{BASE}/api/platform/pipeline-template-tasks/{tid}", json={"active": False})
        assert r.status_code == 200
        assert r.json()["active"] is False
        # restore victim
        r = sa.put(f"{BASE}/api/platform/pipeline-template-tasks/{tid}", json=original)
        assert r.status_code == 200
        # delete the TEST_ added task
        r = sa.delete(f"{BASE}/api/platform/pipeline-template-tasks/{new_id}")
        assert r.status_code == 200
        final = sa.get(f"{BASE}/api/platform/pipeline-templates/{key}/tasks").json()["tasks"]
        assert len(final) == base_count


# ---------- Delete model ----------
class TestDeleteModel:
    def test_delete_test_template(self, sa):
        # create TEST_ template, then delete OK
        r = sa.post(f"{BASE}/api/platform/pipeline-templates",
                    json={"key": "test_delete_me", "name": "TEST_Delete Me",
                          "description": "x", "active": True, "order": 999})
        assert r.status_code == 200, r.text
        r = sa.delete(f"{BASE}/api/platform/pipeline-templates/test_delete_me")
        assert r.status_code == 200

    def test_delete_in_use_returns_409(self, sa, qa_event_with_triathlon_pipeline):
        # by the time this runs the generico+generated pipelines may be in use.
        # We rely on fixture to ensure triathlon is in use.
        _event_id, _ = qa_event_with_triathlon_pipeline
        r = sa.delete(f"{BASE}/api/platform/pipeline-templates/triathlon")
        assert r.status_code == 409, r.text


# ---------- QA event: templates for event + generate + isolation ----------
@pytest.fixture(scope="module")
def qa_event_with_triathlon_pipeline(qa, sa, other_pipelines_before):
    """Create a TEST_ event (Triathlon tipologia), activate pipeline, generate triathlon. Cleanup after."""
    # Record starting credit balance
    me = qa.get(f"{BASE}/api/auth/me").json()
    org_id = me.get("org_id")
    start_bal = qa.get(f"{BASE}/api/credits/summary").json().get("balance", 0)
    # Create event
    event_date = (datetime.date.today() + datetime.timedelta(days=120)).isoformat()
    r = qa.post(f"{BASE}/api/events", json={"nome": "TEST_iter86_tri", "tipologia": "Triathlon",
                                             "data_inizio": event_date, "data_fine": event_date})
    assert r.status_code in (200, 201), r.text
    event_id = r.json()["id"]
    # GET templates for event -> suggested = triathlon
    r = qa.get(f"{BASE}/api/events/{event_id}/pipeline/templates")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["suggested"] == "triathlon", data
    assert any(t["key"] == "triathlon" and t["task_count"] == 92 for t in data["templates"])
    # Activate pipeline (may cost credits)
    r = qa.post(f"{BASE}/api/events/{event_id}/pipeline/activate", json={"template_key": "triathlon"})
    assert r.status_code in (200,), r.text
    # Generate from triathlon
    r = qa.post(f"{BASE}/api/events/{event_id}/pipeline/generate",
                json={"template_key": "triathlon", "confirm": True})
    assert r.status_code == 200, r.text
    yield event_id, event_date
    # Cleanup: delete event (also removes pipeline docs via existing flow if present)
    try:
        qa.delete(f"{BASE}/api/events/{event_id}")
    except Exception:
        pass


class TestOrganizerFlow:
    def test_suggested_triathlon(self, qa_event_with_triathlon_pipeline, qa):
        event_id, _ = qa_event_with_triathlon_pipeline
        r = qa.get(f"{BASE}/api/events/{event_id}/pipeline/templates")
        assert r.json()["suggested"] == "triathlon"

    def test_generated_92_tasks_with_offset_dates(self, qa_event_with_triathlon_pipeline, qa):
        event_id, event_date = qa_event_with_triathlon_pipeline
        r = qa.get(f"{BASE}/api/events/{event_id}/pipeline/tasks")
        assert r.status_code == 200, r.text
        payload = r.json()
        tasks = payload.get("tasks") if isinstance(payload, dict) else payload
        assert isinstance(tasks, list)
        assert len(tasks) == 92, len(tasks)
        ref = datetime.date.fromisoformat(event_date)
        bad = []
        for t in tasks[:20]:
            exp = (ref + datetime.timedelta(days=int(t.get("giorni_offset") or 0))).isoformat()
            if t.get("scadenza") != exp:
                bad.append((t.get("titolo"), t.get("scadenza"), exp))
        assert not bad, bad

    def test_isolation_other_org_cannot_see(self, qa_event_with_triathlon_pipeline, sa):
        event_id, _ = qa_event_with_triathlon_pipeline
        # SA has no org_id, should 404/403 on org-scoped endpoint
        r = sa.get(f"{BASE}/api/events/{event_id}/pipeline/tasks")
        assert r.status_code in (401, 403, 404, 428), r.status_code


# ---------- Non-regression: counts of other events' pipeline_tasks preserved ----------
@pytest.fixture(scope="module")
def other_pipelines_before(qa):
    """Record pipeline task count for all QA events BEFORE test event is created."""
    r = qa.get(f"{BASE}/api/events")
    events = r.json() if r.status_code == 200 else []
    if isinstance(events, dict):
        events = events.get("events") or events.get("items") or []
    counts = {}
    for ev in events:
        eid = ev.get("id")
        if not eid:
            continue
        rr = qa.get(f"{BASE}/api/events/{eid}/pipeline/tasks")
        if rr.status_code == 200:
            p = rr.json()
            tasks = p.get("tasks") if isinstance(p, dict) else p
            counts[eid] = len(tasks) if isinstance(tasks, list) else 0
    return counts


class TestNonRegression:
    def test_other_events_pipelines_unchanged(self, qa, other_pipelines_before, qa_event_with_triathlon_pipeline):
        for eid, before_n in other_pipelines_before.items():
            rr = qa.get(f"{BASE}/api/events/{eid}/pipeline/tasks")
            if rr.status_code != 200:
                continue
            p = rr.json()
            tasks = p.get("tasks") if isinstance(p, dict) else p
            after = len(tasks) if isinstance(tasks, list) else 0
            assert after == before_n, (eid, before_n, after)


# ---------- suggest_template coverage for all tipologie ----------
class TestSuggestedCoverage:
    @pytest.mark.parametrize("tipologia,expected", [
        ("Triathlon", "triathlon"),
        ("Nuoto in acque libere", "nuoto_acque_libere"),
        ("Ciclismo su strada", "ciclismo_strada"),
        ("Mountain Bike", "mountain_bike"),
        ("Trail Running", "trail_running"),
        ("Running", "running"),
    ])
    def test_suggested_for_tipologia(self, qa, tipologia, expected):
        event_date = (datetime.date.today() + datetime.timedelta(days=60)).isoformat()
        r = qa.post(f"{BASE}/api/events", json={"nome": f"TEST_sugg_{expected}",
                                                 "tipologia": tipologia,
                                                 "data_inizio": event_date, "data_fine": event_date})
        assert r.status_code in (200, 201), r.text
        eid = r.json()["id"]
        try:
            d = qa.get(f"{BASE}/api/events/{eid}/pipeline/templates").json()
            assert d["suggested"] == expected, (tipologia, d.get("suggested"))
        finally:
            qa.delete(f"{BASE}/api/events/{eid}")
