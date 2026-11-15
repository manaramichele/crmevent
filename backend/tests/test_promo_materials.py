# Promo materials (Marketing → Email & Brevo → Materiali promozionali): public pages, SA CRUD, versions, status, RBAC, HTML, media
import os
import re
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
SA = {"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"}
SLUGS = ["event-planner", "event-map", "eventi", "staff-volontari", "sponsor-partner"]
NEW = ["eventi", "staff-volontari", "sponsor-partner"]
EDITABLE = ["name", "title", "subtitle", "description", "subject", "preheader", "headline", "body", "benefits", "button_label", "html_override"]


@pytest.fixture(scope="module")
def sa():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=SA)
    if r.status_code != 200:
        pytest.skip("SA login failed")
    return s


@pytest.fixture(scope="module")
def org_user(sa):
    s = requests.Session()
    email = f"test_promo_{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{BASE_URL}/api/auth/register-organization", json={"nome": "Test", "cognome": "Promo", "email": email, "password": "TestPass123!",
                                                                     "org_name": f"TEST_Promo_{uuid.uuid4().hex[:6]}", "telefono": "+393331234567", "accept_terms": True})
    assert r.status_code == 200, r.text
    me = s.get(f"{BASE_URL}/api/auth/me").json()
    yield s
    # cleanup: delete org then user
    org_id, uid = me.get("org_id"), me.get("user_id")
    if org_id:
        orgs = sa.get(f"{BASE_URL}/api/platform/organizations").json()
        orgs = orgs if isinstance(orgs, list) else orgs.get("items", orgs.get("organizations", []))
        name = next((o.get("nome") for o in orgs if o.get("id") == org_id), "")
        d = sa.delete(f"{BASE_URL}/api/platform/organizations/{org_id}", json={"confirm_name": name})
        print("org delete", d.status_code, d.text[:200])
    if uid:
        d = sa.delete(f"{BASE_URL}/api/platform/users/{uid}")
        print("user delete", d.status_code, d.text[:200])


class TestPromo:
    # Public list: only published
    def test_public_list_only_published(self):
        r = requests.get(f"{BASE_URL}/api/public/promo")
        assert r.status_code == 200
        slugs = [x["slug"] for x in r.json()]
        assert "event-planner" in slugs and "event-map" in slugs
        for s in NEW:
            assert s not in slugs
        assert all(x["status"] == "pubblicato" for x in r.json())
        assert "body" not in r.json()[0] and "html_override" not in r.json()[0]

    # Public single: draft hidden from anonymous, visible to SA
    def test_public_draft_404_anon_200_sa(self, sa):
        for s in NEW:
            assert requests.get(f"{BASE_URL}/api/public/promo/{s}").status_code == 404
            r = sa.get(f"{BASE_URL}/api/public/promo/{s}")
            assert r.status_code == 200 and r.json()["status"] == "bozza"
        assert requests.get(f"{BASE_URL}/api/public/promo/event-planner").status_code == 200
        assert requests.get(f"{BASE_URL}/api/public/promo/nonexistent").status_code == 404

    # SA list
    def test_admin_list(self, sa):
        r = sa.get(f"{BASE_URL}/api/promo-materials")
        assert r.status_code == 200
        d = r.json()
        assert [m["slug"] for m in d] == SLUGS
        assert all("_id" not in m for m in d)

    # HTML structure
    @pytest.mark.parametrize("slug", SLUGS)
    def test_html(self, sa, slug):
        r = sa.get(f"{BASE_URL}/api/promo-materials/{slug}/html")
        assert r.status_code == 200
        h, site = r.json()["html"], r.json()["site"]
        assert site.startswith("https://")
        assert "<table" in h and 'width="600"' in h
        assert "<script" not in h.lower()
        assert f'href="{site}/video/{slug}"' in h
        assert "GUARDA IL VIDEO" in h and "Scopri CRMEvent" in h and "www.crmevent.it" in h
        assert "{{ unsubscribe }}" in h
        assert "€" not in h and "&euro;" not in h
        for u in re.findall(r'(?:href|src)="([^"]+)"', h):
            assert u.startswith("https://") or u == "{{ unsubscribe }}", u
        assert f"{site}/media/brevo/{slug}-anteprima.jpg" in h

    def test_html_base_param(self, sa):
        r = sa.get(f"{BASE_URL}/api/promo-materials/eventi/html", params={"base": BASE_URL})
        assert r.json()["site"] == BASE_URL and f"{BASE_URL}/video/eventi" in r.json()["html"]
        r = sa.get(f"{BASE_URL}/api/promo-materials/eventi/html", params={"base": "javascript:alert(1)"})
        assert r.json()["site"].startswith("https://") and "javascript" not in r.json()["site"]

    # Edit -> versions -> restore
    def test_edit_version_restore(self, sa):
        orig = next(m for m in sa.get(f"{BASE_URL}/api/promo-materials").json() if m["slug"] == "eventi")
        payload = {k: orig.get(k) for k in EDITABLE}
        payload["subject"] = "TEST_Oggetto modificato"
        payload["benefits"] = ["TEST_a", " ", "TEST_b "]
        r = sa.put(f"{BASE_URL}/api/promo-materials/eventi", json=payload)
        assert r.status_code == 200, r.text
        assert r.json()["subject"] == "TEST_Oggetto modificato"
        assert r.json()["benefits"] == ["TEST_a", "TEST_b"]
        assert r.json()["version"] == orig["version"] + 1
        assert r.json()["status"] == "bozza"
        g = next(m for m in sa.get(f"{BASE_URL}/api/promo-materials").json() if m["slug"] == "eventi")
        assert g["subject"] == "TEST_Oggetto modificato"
        html = sa.get(f"{BASE_URL}/api/promo-materials/eventi/html").json()["html"]
        assert "TEST_a" in html
        vs = sa.get(f"{BASE_URL}/api/promo-materials/eventi/versions").json()
        assert vs and vs[0]["reason"] == "modifica" and vs[0]["data"]["subject"] == orig["subject"]
        rr = sa.post(f"{BASE_URL}/api/promo-materials/eventi/versions/{vs[0]['id']}/restore")
        assert rr.status_code == 200
        assert rr.json()["subject"] == orig["subject"] and rr.json()["benefits"] == orig["benefits"]
        assert rr.json()["version"] == orig["version"] + 2
        assert sa.post(f"{BASE_URL}/api/promo-materials/eventi/versions/badid/restore").status_code == 404

    def test_put_validation(self, sa):
        r = sa.put(f"{BASE_URL}/api/promo-materials/eventi", json={"name": "", "title": "x", "subject": "x"})
        assert r.status_code == 422
        r = sa.put(f"{BASE_URL}/api/promo-materials/nope", json={"name": "a", "title": "x", "subject": "x"})
        assert r.status_code == 404

    # Status toggle (restored to bozza at the end)
    def test_status_publish_unpublish(self, sa):
        r = sa.post(f"{BASE_URL}/api/promo-materials/staff-volontari/status", params={"status": "pubblicato"})
        try:
            assert r.status_code == 200 and r.json()["status"] == "pubblicato"
            assert requests.get(f"{BASE_URL}/api/public/promo/staff-volontari").status_code == 200
            assert "staff-volontari" in [x["slug"] for x in requests.get(f"{BASE_URL}/api/public/promo").json()]
        finally:
            r2 = sa.post(f"{BASE_URL}/api/promo-materials/staff-volontari/status", params={"status": "bozza"})
        assert r2.json()["status"] == "bozza"
        assert requests.get(f"{BASE_URL}/api/public/promo/staff-volontari").status_code == 404
        assert sa.post(f"{BASE_URL}/api/promo-materials/staff-volontari/status", params={"status": "foo"}).status_code == 422

    # RBAC
    def test_anonymous_denied(self):
        for m, u in [("get", "/api/promo-materials"), ("get", "/api/promo-materials/eventi/html"), ("get", "/api/promo-materials/eventi/versions"),
                     ("post", "/api/promo-materials/eventi/status?status=pubblicato"), ("put", "/api/promo-materials/eventi"),
                     ("post", "/api/promo-materials/eventi/versions/x/restore")]:
            r = getattr(requests, m)(f"{BASE_URL}{u}", json={"name": "a", "title": "b", "subject": "c"} if m == "put" else None)
            assert r.status_code in (401, 403), (u, r.status_code)

    def test_org_admin_denied(self, org_user):
        for m, u in [("get", "/api/promo-materials"), ("get", "/api/promo-materials/eventi/html"), ("get", "/api/promo-materials/eventi/versions"),
                     ("post", "/api/promo-materials/eventi/status?status=pubblicato"), ("put", "/api/promo-materials/eventi"),
                     ("post", "/api/promo-materials/eventi/versions/x/restore")]:
            r = getattr(org_user, m)(f"{BASE_URL}{u}", json={"name": "a", "title": "b", "subject": "c"} if m == "put" else None)
            assert r.status_code == 403, (u, r.status_code)
        assert org_user.get(f"{BASE_URL}/api/public/promo/eventi").status_code == 404

    # Media reachable
    @pytest.mark.parametrize("path", ["/media/eventi-demo.mp4", "/media/staff-volontari-demo.mp4", "/media/sponsor-partner-demo.mp4",
                                      "/media/eventi-demo-poster.jpg", "/media/staff-volontari-demo-poster.jpg", "/media/sponsor-partner-demo-poster.jpg",
                                      "/media/brevo/eventi-anteprima.jpg", "/media/brevo/staff-volontari-anteprima.jpg", "/media/brevo/sponsor-partner-anteprima.jpg",
                                      "/media/brevo/event-planner-anteprima.jpg", "/media/brevo/event-map-anteprima.jpg"])
    def test_media(self, path):
        r = requests.get(f"{BASE_URL}{path}", headers={"Range": "bytes=0-1023"})
        assert r.status_code in (200, 206)
        ct = r.headers.get("content-type", "")
        assert ("video/mp4" in ct) if path.endswith(".mp4") else ("image/jpeg" in ct), ct
