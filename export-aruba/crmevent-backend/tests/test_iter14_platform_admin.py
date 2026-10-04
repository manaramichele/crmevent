"""Iteration 14 - SuperAdmin: global user list, account guards, org hard delete, seed demo."""
import os
import time
import pytest
import requests

def _load_backend_url():
    if os.environ.get("REACT_APP_BACKEND_URL"):
        return os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
    try:
        with open("/app/frontend/.env") as fh:
            for line in fh:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except FileNotFoundError:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


BASE = _load_backend_url()
SA_EMAIL = "manara.michele.pro@gmail.com"
SA_PASS = "CrmEvent2026!"


@pytest.fixture(scope="module")
def sa():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": SA_EMAIL, "password": SA_PASS}, timeout=30)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def throwaway(sa):
    name = f"QA Throwaway Test {int(time.time())}"
    r = sa.post(f"{BASE}/api/platform/organizations",
                json={"nome": name, "type": "test", "status": "active"}, timeout=30)
    assert r.status_code in (200, 201), r.text
    d = r.json()
    return {"id": d.get("id"), "nome": name}


# --------- global users list ---------
def test_users_list(sa):
    r = sa.get(f"{BASE}/api/platform/users", timeout=30)
    assert r.status_code == 200
    users = r.json()
    assert isinstance(users, list) and len(users) >= 2
    emails = {u["email"] for u in users}
    assert SA_EMAIL in emails
    for u in users:
        assert "user_id" in u and "role_label" in u
        assert "active" in u and "created_at" in u


# --------- account guards ---------
def test_cannot_delete_superadmin(sa):
    r = sa.get(f"{BASE}/api/platform/users", timeout=30)
    sa_uid = next(u["user_id"] for u in r.json() if u["email"] == SA_EMAIL)
    d = sa.delete(f"{BASE}/api/platform/users/{sa_uid}", timeout=30)
    assert d.status_code == 400
    assert "Super Admin" in d.text


def test_cannot_delete_sole_admin(sa):
    """organizer.test@crmevent.it is sole admin_org of Eventi Milano SRL (cliente)."""
    r = sa.get(f"{BASE}/api/platform/users", timeout=30)
    org_uid = next((u["user_id"] for u in r.json() if u["email"] == "organizer.test@crmevent.it"), None)
    if not org_uid:
        pytest.skip("organizer.test not present")
    d = sa.delete(f"{BASE}/api/platform/users/{org_uid}", timeout=30)
    assert d.status_code == 400
    # sanity: still there
    r2 = sa.get(f"{BASE}/api/platform/users", timeout=30)
    assert any(u["user_id"] == org_uid for u in r2.json())


# --------- org delete guards ---------
def test_org_delete_wrong_name(sa, throwaway):
    r = sa.request("DELETE", f"{BASE}/api/platform/organizations/{throwaway['id']}",
                   json={"confirm_name": "wrong-name"}, timeout=30)
    assert r.status_code == 400


# --------- seed demo ---------
def test_seed_demo_type_cliente_blocked(sa):
    orgs = sa.get(f"{BASE}/api/platform/organizations", timeout=30).json()
    cliente = next((o for o in orgs if o.get("type") == "cliente"), None)
    if not cliente:
        pytest.skip("no cliente org")
    r = sa.post(f"{BASE}/api/platform/organizations/{cliente['id']}/seed-demo",
                json={"wipe": False}, timeout=30)
    assert r.status_code == 400


def test_seed_demo_idempotent(sa, throwaway):
    r1 = sa.post(f"{BASE}/api/platform/organizations/{throwaway['id']}/seed-demo",
                 json={"wipe": False}, timeout=120)
    assert r1.status_code == 200, r1.text
    counts1 = r1.json().get("counts", {})
    total1 = sum(counts1.values())
    assert total1 > 0

    r2 = sa.post(f"{BASE}/api/platform/organizations/{throwaway['id']}/seed-demo",
                 json={"wipe": False}, timeout=120)
    assert r2.status_code == 200
    counts2 = r2.json().get("counts", {})
    # idempotent: same counts
    assert sum(counts2.values()) == total1, f"not idempotent {counts1} vs {counts2}"


# --------- final: org hard delete with correct name (cleanup) ---------
def test_org_delete_correct_name(sa, throwaway):
    r = sa.request("DELETE", f"{BASE}/api/platform/organizations/{throwaway['id']}",
                   json={"confirm_name": throwaway["nome"]}, timeout=60)
    assert r.status_code == 200, r.text
    # verify gone
    orgs = sa.get(f"{BASE}/api/platform/organizations", timeout=30).json()
    assert not any(o["id"] == throwaway["id"] for o in orgs)


# --------- Demobot isolation on Demo org ---------
def test_demobot_bologna_volunteers(sa):
    demo_org_id = "b7f40862230441b9a0bedabefe8dab49"
    sa.headers.update({"X-Org-Id": demo_org_id})
    r = sa.post(f"{BASE}/api/support/chat",
                json={"question": "Quanti volontari abbiamo per Bologna City Run?"},
                timeout=90)
    sa.headers.pop("X-Org-Id", None)
    assert r.status_code == 200, r.text
    ans = (r.json().get("answer") or "").lower()
    # expected 18 volunteers
    assert "18" in ans, f"expected 18 in answer, got: {ans[:400]}"
