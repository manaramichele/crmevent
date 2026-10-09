"""Iter 112: Super Admin acting_org_id behaviour; /my/todo and /my/notes org scoping."""
import os
import pytest
import requests

def _read_env(key):
    for p in ("/app/frontend/.env", "/app/backend/.env"):
        try:
            for line in open(p):
                if line.startswith(key + "="):
                    return line.split("=", 1)[1].strip()
        except Exception:
            pass
    return None

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or _read_env("REACT_APP_BACKEND_URL") or "").rstrip("/")
assert BASE, "REACT_APP_BACKEND_URL not set"
API = f"{BASE}/api"

SUPER = {"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"}
QA = {"email": "qa.eventi@crmeventqa.it", "password": "QaEvents2026!"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def super_sess():
    return _login(SUPER)


@pytest.fixture(scope="module")
def qa_sess():
    return _login(QA)


@pytest.fixture(scope="module")
def orgs(super_sess):
    r = super_sess.get(f"{API}/platform/organizations", timeout=30)
    assert r.status_code == 200
    return r.json()


# --- /my/todo for Super Admin ---

def test_super_todo_no_header_returns_428(super_sess):
    r = super_sess.get(f"{API}/my/todo", timeout=30)
    assert r.status_code == 428


def test_super_todo_invalid_org_returns_404(super_sess):
    r = super_sess.get(f"{API}/my/todo", headers={"X-Org-Id": "nonexistent123"}, timeout=30)
    assert r.status_code == 404


def test_super_todo_qa_eventi_has_items(super_sess, orgs):
    # Try org_qa_eventi, b7f40862..., else any org with items
    preferred = ["org_qa_eventi", "b7f40862230441b9a0bedabefe8dab49"]
    tried = []
    for oid in preferred + [o["id"] for o in orgs if o["id"] not in preferred]:
        r = super_sess.get(f"{API}/my/todo", headers={"X-Org-Id": oid}, timeout=30)
        if r.status_code != 200:
            continue
        n = len(r.json().get("items", []))
        tried.append((oid, n))
        if n > 0:
            return
    pytest.fail(f"No org had todo items. Tried: {tried[:10]}")


# --- /my/notes org scoping ---

TEST_PREFIX = "TEST_iter112_"


@pytest.fixture
def two_orgs(orgs):
    assert len(orgs) >= 2, "need >= 2 orgs"
    return orgs[0]["id"], orgs[1]["id"]


def test_super_notes_scoped_per_org(super_sess, two_orgs):
    a, b = two_orgs
    hA = {"X-Org-Id": a}
    hB = {"X-Org-Id": b}
    # Create note in A
    r = super_sess.post(f"{API}/my/notes", json={"text": TEST_PREFIX + "A"}, headers=hA, timeout=30)
    assert r.status_code == 200, r.text
    nid_a = r.json()["id"]
    # Not visible in B
    rb = super_sess.get(f"{API}/my/notes", headers=hB, timeout=30)
    assert rb.status_code == 200
    ids_b = [n["id"] for n in rb.json()["items"]]
    assert nid_a not in ids_b
    # Visible in A
    ra = super_sess.get(f"{API}/my/notes", headers=hA, timeout=30)
    assert nid_a in [n["id"] for n in ra.json()["items"]]
    # Deleting note of A while acting in B -> 404
    rdel_wrong = super_sess.delete(f"{API}/my/notes/{nid_a}", headers=hB, timeout=30)
    assert rdel_wrong.status_code == 404
    # Delete properly in A
    rdel = super_sess.delete(f"{API}/my/notes/{nid_a}", headers=hA, timeout=30)
    assert rdel.status_code == 200


def test_super_notes_legacy_without_org_visible(super_sess, two_orgs):
    """Legacy notes (no org_id) must remain visible to their owner in any org context."""
    from pymongo import MongoClient
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        pytest.skip("no mongo access")
    cli = MongoClient(mongo_url)
    db = cli[db_name]
    me = super_sess.get(f"{API}/auth/me", timeout=30).json()
    import uuid
    from datetime import datetime, timezone
    legacy_id = uuid.uuid4().hex
    db.user_notes.insert_one({
        "id": legacy_id, "user_id": me["user_id"], "text": TEST_PREFIX + "legacy",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    try:
        a, b = two_orgs
        for org in (a, b):
            r = super_sess.get(f"{API}/my/notes", headers={"X-Org-Id": org}, timeout=30)
            ids = [n["id"] for n in r.json()["items"]]
            assert legacy_id in ids, f"legacy not visible in {org}"
    finally:
        db.user_notes.delete_one({"id": legacy_id})
        cli.close()


# --- Org admin: no X-Org-Id needed ---

def test_qa_admin_todo_without_header(qa_sess):
    r = qa_sess.get(f"{API}/my/todo", timeout=30)
    assert r.status_code == 200, r.text
    assert "items" in r.json()


def test_qa_admin_notes_without_header(qa_sess):
    r = qa_sess.get(f"{API}/my/notes", timeout=30)
    assert r.status_code == 200
    assert "items" in r.json()
