"""Iter100 - Dashboard To Do List + Note personali."""
import os
import time
import requests
import pytest

def _load_env():
    try:
        for line in open("/app/frontend/.env"):
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    return os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

BASE = _load_env()
assert BASE, "REACT_APP_BACKEND_URL not set"
API = f"{BASE}/api"

QA = {"email": "qa.eventi@crmeventqa.it", "password": "QaEvents2026!"}
SUPER = {"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, r.text
    return s, r.json()


@pytest.fixture(scope="module")
def qa():
    s, u = _login(QA)
    yield s, u
    s.post(f"{API}/auth/logout")


@pytest.fixture(scope="module")
def sup():
    s, u = _login(SUPER)
    yield s, u
    s.post(f"{API}/auth/logout")


# ---------- To Do List ----------
class TestTodo:
    def test_my_todo_shape(self, qa):
        s, _ = qa
        r = s.get(f"{API}/my/todo", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "items" in data and "types" in data
        assert set(data["types"]).issubset({"pipeline", "attivita", "followup"})
        # fields present
        for i in data["items"]:
            for k in ("tipo", "id", "titolo", "stato", "priorita", "scadenza", "bucket",
                      "responsabile", "evento", "evento_id", "can_edit"):
                assert k in i, f"missing {k} in {i}"
            assert i["tipo"] in ("pipeline", "attivita", "followup")
            assert i["bucket"] in ("ritardo", "scadenza", "da_fare")

    def test_todo_sorted_and_no_completed(self, qa):
        s, _ = qa
        items = s.get(f"{API}/my/todo").json()["items"]
        order = {"ritardo": 0, "scadenza": 1, "da_fare": 2}
        prev = -1
        for i in items:
            assert i["stato"] not in ("completata", "completato"), i
            assert order[i["bucket"]] >= prev
            prev = order[i["bucket"]]

    def test_complete_and_restore_pipeline_task(self, qa):
        s, _ = qa
        items = s.get(f"{API}/my/todo").json()["items"]
        pipe = next((i for i in items if i["tipo"] == "pipeline" and i["can_edit"]), None)
        if not pipe:
            pytest.skip("No pipeline task available in QA org")
        original_stato = pipe["stato"]
        event_id = pipe["evento_id"]
        tid = pipe["id"]
        # Complete
        r = s.post(f"{API}/my/todo/complete", json={"tipo": "pipeline", "id": tid}, timeout=15)
        assert r.status_code == 200, r.text
        # Gone from list
        items2 = s.get(f"{API}/my/todo").json()["items"]
        assert not any(x["id"] == tid for x in items2)
        # Pipeline endpoint shows it as completata
        tasks = s.get(f"{API}/events/{event_id}/pipeline/tasks").json()
        if isinstance(tasks, dict):
            tasks = tasks.get("tasks") or tasks.get("items") or []
        task = next((t for t in tasks if t["id"] == tid), None)
        assert task is not None
        assert task["stato"] == "completata"
        # Restore
        rr = s.put(f"{API}/pipeline/tasks/{tid}", json={"stato": original_stato})
        assert rr.status_code == 200, rr.text

    def test_complete_404_on_bad_id(self, qa):
        s, _ = qa
        r = s.post(f"{API}/my/todo/complete", json={"tipo": "pipeline", "id": "nonexistent_xyz"})
        assert r.status_code == 404


# ---------- Notes ----------
class TestNotes:
    def _cleanup(self, s, prefix="TEST_iter100"):
        for n in s.get(f"{API}/my/notes").json().get("items", []):
            if n["text"].startswith(prefix):
                s.delete(f"{API}/my/notes/{n['id']}")

    def test_notes_crud(self, qa):
        s, _ = qa
        self._cleanup(s)
        # Create
        r = s.post(f"{API}/my/notes", json={"text": "TEST_iter100 nota uno"})
        assert r.status_code == 200, r.text
        n = r.json()
        assert n["text"] == "TEST_iter100 nota uno"
        assert "id" in n and "created_at" in n
        nid = n["id"]
        # List - newest first
        lst = s.get(f"{API}/my/notes").json()["items"]
        assert lst[0]["id"] == nid
        # Update
        r = s.put(f"{API}/my/notes/{nid}", json={"text": "TEST_iter100 nota uno (edit)"})
        assert r.status_code == 200
        after = s.get(f"{API}/my/notes").json()["items"]
        assert next(x for x in after if x["id"] == nid)["text"] == "TEST_iter100 nota uno (edit)"
        # Empty rejected
        r = s.post(f"{API}/my/notes", json={"text": "   "})
        assert r.status_code == 400
        # Delete
        r = s.delete(f"{API}/my/notes/{nid}")
        assert r.status_code == 200
        assert s.delete(f"{API}/my/notes/{nid}").status_code == 404
        # Delete the main-agent-created leftover
        for leftover in s.get(f"{API}/my/notes").json().get("items", []):
            if leftover["text"] == "TEST_nota":
                s.delete(f"{API}/my/notes/{leftover['id']}")

    def test_notes_isolation_between_users(self, qa, sup):
        s_qa, _ = qa
        s_su, _ = sup
        # Create note as QA
        r = s_qa.post(f"{API}/my/notes", json={"text": "TEST_iter100 private QA"})
        nid = r.json()["id"]
        try:
            # Super admin shouldn't see it
            others = s_su.get(f"{API}/my/notes").json()["items"]
            assert not any(x["id"] == nid for x in others)
            # Super admin cannot edit/delete it
            r = s_su.put(f"{API}/my/notes/{nid}", json={"text": "hack"})
            assert r.status_code == 404
            r = s_su.delete(f"{API}/my/notes/{nid}")
            assert r.status_code == 404
        finally:
            s_qa.delete(f"{API}/my/notes/{nid}")

    def test_notes_persist_across_sessions(self):
        s1, _ = _login(QA)
        r = s1.post(f"{API}/my/notes", json={"text": "TEST_iter100 persist"})
        nid = r.json()["id"]
        s1.post(f"{API}/auth/logout")
        s2, _ = _login(QA)
        try:
            items = s2.get(f"{API}/my/notes").json()["items"]
            assert any(x["id"] == nid for x in items)
        finally:
            s2.delete(f"{API}/my/notes/{nid}")
            s2.post(f"{API}/auth/logout")
