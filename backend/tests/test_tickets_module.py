# Segnalazioni e richieste (tickets org <-> Super Admin) – regression tests
import io
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ORG = ("qa.eventi@crmeventqa.it", "QaEvents2026!")
SA = ("manara.michele.pro@gmail.com", "CrmEvent2026!")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF = b"%PDF-1.4\n%test\n"
STATE = {}


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw})
    if r.status_code != 200:
        pytest.skip(f"login failed {email}: {r.status_code} {r.text[:200]}")
    return s


@pytest.fixture(scope="module")
def org():
    return _login(*ORG)


@pytest.fixture(scope="module")
def sa():
    return _login(*SA)


@pytest.fixture(scope="module")
def org2():
    email = f"test_tk_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{BASE_URL}/api/auth/register-organization", json={
        "nome": "TEST", "cognome": "Ticket", "email": email, "password": "TestPass2026!",
        "org_name": f"TEST_TicketOrg_{uuid.uuid4().hex[:6]}", "telefono": "+393331234567", "accept_terms": True})
    assert r.status_code == 200, r.text
    STATE["org2_email"] = email
    return _login(email, "TestPass2026!")


def _count(sa):
    r = sa.get(f"{BASE_URL}/api/platform/tickets/count")
    assert r.status_code == 200
    return r.json()["pending"]


# --- create + SA visibility + badge
def test_create_ticket_with_png(org, sa):
    before = _count(sa)
    r = org.post(f"{BASE_URL}/api/tickets", data={"category": "problema_tecnico", "subject": "TEST_ticket flow", "description": "desc test"},
                 files=[("files", ("shot.png", PNG, "image/png"))])
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["number"] > 1000 and t["status"] == "aperta" and len(t["attachments"]) == 1
    assert "_id" not in t
    STATE["t"] = t
    assert _count(sa) == before + 1
    lst = sa.get(f"{BASE_URL}/api/platform/tickets").json()
    assert any(x["id"] == t["id"] for x in lst["tickets"])
    assert org.get(f"{BASE_URL}/api/tickets/files/{t['attachments'][0]['id']}").content == PNG
    assert sa.get(f"{BASE_URL}/api/platform/tickets/files/{t['attachments'][0]['id']}").status_code == 200
    assert any(x["id"] == t["id"] for x in org.get(f"{BASE_URL}/api/tickets").json())


# --- SA reply/internal note/status changes; org visibility
def test_sa_reply_internal_status(org, sa):
    tid = STATE["t"]["id"]
    r = sa.post(f"{BASE_URL}/api/platform/tickets/{tid}/messages", data={"text": "TEST public reply", "internal": "false"})
    assert r.status_code == 200 and r.json()["internal"] is False
    r = sa.post(f"{BASE_URL}/api/platform/tickets/{tid}/messages", data={"text": "TEST secret note", "internal": "true"},
                files=[("files", ("int.pdf", PDF, "application/pdf"))])
    assert r.status_code == 200 and r.json()["internal"] is True
    STATE["int_fid"] = r.json()["attachments"][0]["id"]
    for s in ("in_lavorazione", "in_attesa"):
        r = sa.post(f"{BASE_URL}/api/platform/tickets/{tid}/status", json={"status": s})
        assert r.status_code == 200 and r.json()["status"] == s
    assert sa.post(f"{BASE_URL}/api/platform/tickets/{tid}/status", json={"status": "in_attesa"}).status_code == 400
    assert sa.post(f"{BASE_URL}/api/platform/tickets/{tid}/status", json={"status": "bogus"}).status_code in (400, 422)
    d = org.get(f"{BASE_URL}/api/tickets/{tid}").json()
    assert d["status"] == "in_attesa"
    texts = [m["text"] for m in d["messages"]]
    assert "TEST public reply" in texts and "TEST secret note" not in texts
    assert not any(m.get("internal") for m in d["messages"])
    assert org.get(f"{BASE_URL}/api/tickets/files/{STATE['int_fid']}").status_code == 404
    assert sa.get(f"{BASE_URL}/api/platform/tickets/files/{STATE['int_fid']}").status_code == 200
    sd = sa.get(f"{BASE_URL}/api/platform/tickets/{tid}").json()
    assert "TEST secret note" in [m["text"] for m in sd["messages"]]


def test_org_reply_with_attachment(org, sa):
    tid = STATE["t"]["id"]
    r = org.post(f"{BASE_URL}/api/tickets/{tid}/messages", data={"text": "TEST org reply"}, files=[("files", ("a.png", PNG, "image/png"))])
    assert r.status_code == 200, r.text
    fid = r.json()["attachments"][0]["id"]
    assert org.get(f"{BASE_URL}/api/tickets/files/{fid}").status_code == 200
    assert sa.get(f"{BASE_URL}/api/platform/tickets/files/{fid}").status_code == 200
    assert org.post(f"{BASE_URL}/api/tickets/{tid}/messages", data={"text": "  "}).status_code == 400


def test_close_and_reopen_flow(org, sa):
    tid = STATE["t"]["id"]
    before = _count(sa)
    r = sa.post(f"{BASE_URL}/api/platform/tickets/{tid}/status", json={"status": "chiusa", "message": "TEST final message"})
    assert r.status_code == 200 and r.json()["closed_at"] and r.json()["closed_by"]
    assert _count(sa) == before - 1
    d = org.get(f"{BASE_URL}/api/tickets/{tid}").json()
    assert d["status"] == "chiusa" and d["closed_at"]
    texts = [m["text"] for m in d["messages"]]
    assert "TEST final message" in texts and "TEST org reply" in texts and "TEST public reply" in texts
    assert org.post(f"{BASE_URL}/api/tickets/{tid}/messages", data={"text": "x"}).status_code == 400
    assert org.post(f"{BASE_URL}/api/tickets/{tid}/reopen-request", data={"text": "TEST please reopen"}).status_code == 200
    assert org.post(f"{BASE_URL}/api/tickets/{tid}/reopen-request", data={"text": "again"}).status_code == 400
    d = org.get(f"{BASE_URL}/api/tickets/{tid}").json()
    assert d["status"] == "chiusa" and d["reopen_requested"] is True
    assert _count(sa) == before
    rr = sa.get(f"{BASE_URL}/api/platform/tickets", params={"status": "riapertura"}).json()["tickets"]
    assert any(x["id"] == tid for x in rr)
    r = sa.post(f"{BASE_URL}/api/platform/tickets/{tid}/status", json={"status": "in_lavorazione"})
    assert r.status_code == 200
    d = org.get(f"{BASE_URL}/api/tickets/{tid}").json()
    assert d["status"] == "in_lavorazione" and d["reopen_requested"] is False and d["closed_at"] is None
    assert org.post(f"{BASE_URL}/api/tickets/{tid}/reopen-request", data={"text": "x"}).status_code == 400


# --- cross-org isolation
def test_cross_org(org2, sa):
    t = STATE["t"]
    assert org2.get(f"{BASE_URL}/api/tickets").json() == []
    assert org2.get(f"{BASE_URL}/api/tickets/{t['id']}").status_code == 404
    assert org2.post(f"{BASE_URL}/api/tickets/{t['id']}/messages", data={"text": "hack"}).status_code == 404
    assert org2.post(f"{BASE_URL}/api/tickets/{t['id']}/reopen-request", data={"text": "hack"}).status_code == 404
    assert org2.get(f"{BASE_URL}/api/tickets/files/{t['attachments'][0]['id']}").status_code == 404
    for path in ("/api/platform/tickets", "/api/platform/tickets/count", f"/api/platform/tickets/{t['id']}",
                 f"/api/platform/tickets/files/{t['attachments'][0]['id']}"):
        assert org2.get(f"{BASE_URL}{path}").status_code == 403, path
    assert org2.post(f"{BASE_URL}/api/platform/tickets/{t['id']}/status", json={"status": "chiusa"}).status_code == 403
    assert org2.post(f"{BASE_URL}/api/platform/tickets/{t['id']}/messages", data={"text": "x"}).status_code == 403
    # org2 creates own ticket -> SA org filter
    r = org2.post(f"{BASE_URL}/api/tickets", data={"category": "altro", "subject": "TEST_org2 ticket", "description": "d"})
    assert r.status_code == 200
    STATE["t2"] = r.json()
    rows = sa.get(f"{BASE_URL}/api/platform/tickets", params={"org_id": STATE["t2"]["org_id"]}).json()["tickets"]
    assert [x["id"] for x in rows] == [STATE["t2"]["id"]]


# --- validation
@pytest.mark.parametrize("data,files", [
    ({"category": "bogus", "subject": "TEST_v", "description": "d"}, None),
    ({"category": "altro", "subject": "  ", "description": "d"}, None),
    ({"category": "altro", "subject": "TEST_v", "description": "  "}, None),
    ({"category": "altro", "subject": "TEST_v", "description": "d"}, [("files", ("fake.png", b"GIF89a....", "image/png"))]),
    ({"category": "altro", "subject": "TEST_v", "description": "d"}, [("files", (f"f{i}.png", PNG, "image/png")) for i in range(6)]),
    ({"category": "altro", "subject": "TEST_v", "description": "d"}, [("files", ("big.png", PNG + b"\x00" * (10 * 1024 * 1024 + 10), "image/png"))]),
    ({"category": "altro", "subject": "TEST_v", "description": "d"}, [("files", ("x.exe", b"MZ..", "application/octet-stream"))]),
])
def test_validation(org, data, files):
    r = org.post(f"{BASE_URL}/api/tickets", data=data, files=files)
    assert r.status_code == 400, f"{r.status_code} {r.text[:200]}"


def test_missing_fields_422_or_400(org):
    r = org.post(f"{BASE_URL}/api/tickets", data={"category": "altro"})
    assert r.status_code in (400, 422), r.status_code
    STATE["missing_code"] = r.status_code


# --- SA filters
def test_sa_filters(sa):
    t = STATE["t"]
    g = lambda **p: [x["id"] for x in sa.get(f"{BASE_URL}/api/platform/tickets", params=p).json()["tickets"]]
    assert t["id"] in g(q=str(t["number"]))
    assert t["id"] in g(q=f"#{t['number']}")
    assert t["id"] in g(q="ticket flow")
    assert t["id"] in g(category="problema_tecnico") and t["id"] not in g(category="altro")
    assert t["id"] in g(status="in_lavorazione") and t["id"] not in g(status="chiusa")
    day = t["created_at"][:10]
    assert t["id"] in g(**{"from": day, "to": day})
    assert t["id"] not in g(**{"from": "2099-01-01"})
    assert t["id"] not in g(**{"to": "2000-01-01"})
    d = sa.get(f"{BASE_URL}/api/platform/tickets").json()
    assert set(d["counts"]) == {"aperta", "in_lavorazione", "in_attesa", "chiusa"}


def test_unauth():
    assert requests.get(f"{BASE_URL}/api/tickets").status_code == 401
    assert requests.get(f"{BASE_URL}/api/platform/tickets").status_code == 401
