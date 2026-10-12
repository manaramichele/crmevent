"""Partner materials — Super Admin create (file/text/legacy), partner portal view with placeholder replacement."""
import os
import time
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else "https://manage-events-12.preview.emergentagent.com"
SA_EMAIL = "manara.michele.pro@gmail.com"
SA_PASS = "CrmEvent2026!"
PH = "[LINK PERSONALE DEL PARTNER]"

created_material_ids = []
test_partner_id = None


def _sa_session():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": SA_EMAIL, "password": SA_PASS})
    assert r.status_code == 200, r.text
    return s


def test_sa_create_text_material_ok():
    s = _sa_session()
    text = f"Ciao 🎉\n\nProva CRMEvent gratis!\n\nIl mio link: {PH}\n\nA presto 👋"
    r = s.post(f"{BASE}/api/platform/partner-materials",
               data={"title": "TEST_text_whatsapp", "kind": "text", "category": "whatsapp", "text": text})
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["kind"] == "text"
    assert m["category"] == "whatsapp"
    assert m["text"] == text
    assert m["title"] == "TEST_text_whatsapp"
    assert m.get("url") in (None, "")
    created_material_ids.append(m["id"])
    # Verify persistence via list
    r2 = s.get(f"{BASE}/api/platform/partner-materials")
    assert r2.status_code == 200
    found = [x for x in r2.json() if x["id"] == m["id"]]
    assert found and found[0]["text"] == text


def test_sa_create_text_empty_text_400():
    s = _sa_session()
    r = s.post(f"{BASE}/api/platform/partner-materials",
               data={"title": "TEST_empty", "kind": "text", "category": "generale", "text": "   "})
    assert r.status_code == 400, r.text
    assert "testo" in r.json().get("detail", "").lower()


def test_sa_create_file_kind_without_url_or_file_400():
    s = _sa_session()
    r = s.post(f"{BASE}/api/platform/partner-materials",
               data={"title": "TEST_file_missing", "kind": "file", "category": "generale"})
    assert r.status_code == 400, r.text


def test_sa_create_file_kind_with_url_legacy_200():
    s = _sa_session()
    r = s.post(f"{BASE}/api/platform/partner-materials",
               data={"title": "TEST_file_link", "kind": "file", "category": "instagram",
                     "url": "https://example.com/banner.png"})
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["kind"] == "file"
    assert m["category"] == "instagram"
    assert m["url"] == "https://example.com/banner.png"
    assert m.get("text") in (None, "")
    created_material_ids.append(m["id"])


def test_sa_create_invalid_category_422():
    s = _sa_session()
    r = s.post(f"{BASE}/api/platform/partner-materials",
               data={"title": "TEST_badcat", "kind": "text", "category": "xxxx", "text": "hello"})
    assert r.status_code == 422, r.text


def test_partner_portal_sees_materials_with_placeholder_replaced():
    """Create TEST partner, approve, login, fetch materials; placeholder replacement is done client-side so we just verify text comes with placeholder."""
    global test_partner_id
    sa = _sa_session()
    ts = int(time.time())
    email = f"test_partner_{ts}@example.com"
    reg = requests.post(f"{BASE}/api/partner/register", json={
        "nome": "Test", "cognome": "Partner", "email": email, "telefono": "+393331234567",
        "tipologia": "persona_fisica", "password": "Partner2026!", "password_confirm": "Partner2026!",
        "accept_terms": True, "accept_privacy": True,
    })
    assert reg.status_code == 200, reg.text
    # Find partner id
    plist = sa.get(f"{BASE}/api/platform/partners", params={"q": email}).json()
    assert plist, "partner not found"
    test_partner_id = plist[0]["id"]
    # Approve
    appr = sa.post(f"{BASE}/api/platform/partners/{test_partner_id}/status",
                   json={"status": "approved", "note": "test"})
    assert appr.status_code == 200
    # Partner login (separate session)
    p = requests.Session()
    lr = p.post(f"{BASE}/api/partner/login", json={"email": email, "password": "Partner2026!"})
    assert lr.status_code == 200, lr.text
    partner_me = lr.json()
    referral_link = partner_me.get("referral_link")
    assert referral_link and "ref=" in referral_link
    # Fetch materials
    mr = p.get(f"{BASE}/api/partner/materials")
    assert mr.status_code == 200, mr.text
    materials = mr.json()
    text_mats = [m for m in materials if m.get("kind") == "text"]
    assert text_mats, "text material not returned to partner"
    tm = text_mats[0]
    assert PH in tm["text"], "placeholder should still be in server response (replaced client-side)"
    assert tm["category"] == "whatsapp"
    # Verify client-side replacement would work
    replaced = tm["text"].replace(PH, referral_link)
    assert referral_link in replaced and PH not in replaced


def test_cleanup():
    """Cleanup created materials and TEST partner."""
    sa = _sa_session()
    for mid in created_material_ids:
        sa.delete(f"{BASE}/api/platform/partner-materials/{mid}")
    # Delete the TEST partner directly via Mongo via SA? No direct endpoint. Leave status as rejected and note.
    # Attempt to find any additional created text materials (from text test) and clean
    r = sa.get(f"{BASE}/api/platform/partner-materials").json()
    for m in r:
        if (m.get("title") or "").startswith("TEST_"):
            sa.delete(f"{BASE}/api/platform/partner-materials/{m['id']}")
    # Try removing the TEST partner from Mongo directly
    try:
        from pymongo import MongoClient
        mc = MongoClient(os.environ.get("MONGO_URL") or "mongodb://localhost:27017")
        db = mc[os.environ.get("DB_NAME") or "test_database"]
        if test_partner_id:
            db.partners.delete_one({"id": test_partner_id})
            db.partner_referrals.delete_many({"partner_id": test_partner_id})
    except Exception as e:
        print(f"cleanup partner skip: {e}")
