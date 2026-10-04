"""Backend tests for role-aware CRMEvent AI support assistant (iteration 5)."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

ADMIN_EMAIL = "manara.michele.pro@gmail.com"
ADMIN_PASSWORD = "CrmEvent2026!"
VOL_EMAIL = "volontario.test@crmevent.it"
VOL_PASSWORD = "VolTest2026!"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def vol_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": VOL_EMAIL, "password": VOL_PASSWORD})
    assert r.status_code == 200, f"volunteer login failed: {r.status_code} {r.text}"
    return s


# ---------- ROLE-AWARE CHAT ----------
def test_vol_modifica_turno_readonly(vol_session):
    r = vol_session.post(f"{BASE_URL}/api/support/chat",
                         json={"question": "Come modifico il mio turno?"})
    assert r.status_code == 200, r.text
    data = r.json()
    ans = (data.get("answer") or "").lower()
    print("VOL modifica turno:", ans[:300])
    # Must NOT be admin procedure; should mention read-only / organizer
    assert "persone" not in ans or "sola lettura" in ans or "organizzat" in ans or "read" in ans or "non puoi" in ans or "assegnat" in ans
    # No admin path 'Persone -> Turni -> Modifica'
    assert not ("persone" in ans and "turni" in ans and "modifica" in ans and "clicca" in ans)


def test_vol_crea_evento_answered_false(vol_session):
    r = vol_session.post(f"{BASE_URL}/api/support/chat",
                         json={"question": "Come creo un nuovo evento?"})
    assert r.status_code == 200, r.text
    data = r.json()
    print("VOL crea evento:", data.get("answered"), (data.get("answer") or "")[:200])
    assert data.get("answered") is False


def test_vol_vedo_miei_turni_answered(vol_session):
    r = vol_session.post(f"{BASE_URL}/api/support/chat",
                         json={"question": "Come vedo i miei turni?"})
    assert r.status_code == 200, r.text
    data = r.json()
    print("VOL miei turni:", data.get("answered"), (data.get("answer") or "")[:200])
    assert data.get("answered") is True
    ans = (data.get("answer") or "").lower()
    assert "turn" in ans


def test_admin_modifica_turno_full(admin_session):
    r = admin_session.post(f"{BASE_URL}/api/support/chat",
                           json={"question": "Come modifico il mio turno?"})
    assert r.status_code == 200, r.text
    data = r.json()
    print("ADMIN modifica turno:", data.get("answered"), (data.get("answer") or "")[:200])
    assert data.get("answered") is True


def test_admin_crea_evento_full(admin_session):
    r = admin_session.post(f"{BASE_URL}/api/support/chat",
                           json={"question": "Come creo un nuovo evento?"})
    assert r.status_code == 200, r.text
    data = r.json()
    print("ADMIN crea evento:", data.get("answered"), (data.get("answer") or "")[:200])
    assert data.get("answered") is True


# ---------- KB personal-area entries ----------
def test_kb_has_personal_area_entries(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/support-kb")
    assert r.status_code == 200
    kb = r.json()
    with_vol = [k for k in kb if "volontario" in (k.get("ruoli") or "")]
    print(f"KB total={len(kb)} with volontario role={len(with_vol)}")
    assert len(with_vol) >= 3
    # All published
    for k in with_vol:
        assert k.get("stato") == "pubblicato", f"KB {k.get('titolo')} not published"


# ---------- Feature-gap requests ----------
def test_feature_requests_gap_entries(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/support-feature-requests")
    assert r.status_code == 200
    frs = r.json()
    da_val = [f for f in frs if f.get("stato") == "da_valutare"]
    print(f"feature-requests total={len(frs)} da_valutare={len(da_val)}")
    assert len(da_val) >= 4


# ---------- Data isolation ----------
def test_vol_blocked_conversations(vol_session):
    r = vol_session.get(f"{BASE_URL}/api/support/conversations")
    assert r.status_code == 403, r.status_code


def test_vol_blocked_insights(vol_session):
    r = vol_session.get(f"{BASE_URL}/api/support/insights")
    assert r.status_code == 403, r.status_code


def test_vol_my_conversations_ok(vol_session):
    # trigger one
    vol_session.post(f"{BASE_URL}/api/support/chat", json={"question": "Come vedo i miei turni?"})
    r = vol_session.get(f"{BASE_URL}/api/support/my-conversations")
    assert r.status_code == 200
    convs = r.json()
    assert isinstance(convs, list)
