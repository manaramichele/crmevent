"""Iter 76 — Brevo lists per Organization (Staff/Collaboratori/Utenti_invitati/Volontari/Referenti_Aziendali).
Covers:
  - GET  /api/platform/brevo/org-lists/settings  (superadmin only; defaults; configured flag; folder; unchanged_lists)
  - PUT  /api/platform/brevo/org-lists/settings  (toggle on/off; audit 'brevo_org_lists_toggle')
  - GET  /api/platform/brevo/org-lists/preview?org_id=  (5 categories, counts, naming)
  - POST /api/platform/brevo/org-lists/sync/{org_id}  (400 when disabled; 400 'Brevo non configurato')
  - Unit test (mocked BrevoClient): brevo_org_lists.sync_org folder/list lazy creation, idempotency, unsubscribed path.
  - Unit test: server.sync_registered_user skips 'invited' for non-self_registered when source!='registration'.
Does NOT call api.brevo.com. Toggle restored to False at end.
"""
import asyncio
import importlib
import os
import re
import sys
import uuid
import pytest
import requests
from pymongo import MongoClient

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or
            open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]
            ).rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

SUPER = {"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"}
ADMIN = {"email": "qa.eventi@crmeventqa.it", "password": "QaEvents2026!"}

sys.path.insert(0, "/app/backend")


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def sa():
    return _login(SUPER)


@pytest.fixture(scope="module")
def admin_sess():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def qa_org_id(sa):
    r = sa.get(f"{API}/platform/organizations", timeout=20)
    assert r.status_code == 200, r.text
    orgs = r.json()
    # QA organization associated to qa.eventi@crmeventqa.it; fall back to anything with "qa" in nome
    for o in orgs:
        if "qa" in (o.get("nome") or "").lower() or o.get("id") == "org_qa_eventi":
            return o["id"]
    return orgs[0]["id"]


@pytest.fixture(scope="module", autouse=True)
def _restore_toggle(sa):
    """Guarantee the toggle is OFF at module teardown (requirement)."""
    yield
    try:
        sa.put(f"{API}/platform/brevo/org-lists/settings", json={"enabled": False}, timeout=20)
    except Exception:
        pass


# ----- Settings endpoint -----

class TestSettings:
    def test_settings_requires_superadmin(self, admin_sess):
        r = admin_sess.get(f"{API}/platform/brevo/org-lists/settings", timeout=20)
        assert r.status_code == 403, r.status_code

    def test_settings_defaults_and_shape(self, sa):
        # Ensure OFF for a clean baseline
        sa.put(f"{API}/platform/brevo/org-lists/settings", json={"enabled": False}, timeout=20)
        r = sa.get(f"{API}/platform/brevo/org-lists/settings", timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert data["enabled"] is False
        assert "configured" in data and isinstance(data["configured"], bool)
        assert data["folder"] == "CRMEvent · Organizzazioni"
        unchanged = data.get("unchanged_lists") or []
        for name in ["CRMEvent · Lead", "CRMEvent · Utenti registrati",
                     "CRMEvent · Disponibilità eventi", "CRMEvent – Prospect"]:
            assert name in unchanged, f"missing unchanged list {name}"

    def test_settings_toggle_writes_audit(self, sa):
        # Toggle ON
        r = sa.put(f"{API}/platform/brevo/org-lists/settings", json={"enabled": True}, timeout=20)
        assert r.status_code == 200 and r.json()["enabled"] is True
        # Verify in GET
        assert sa.get(f"{API}/platform/brevo/org-lists/settings").json()["enabled"] is True
        # Verify audit entry (via Mongo)
        client = MongoClient(MONGO_URL)
        try:
            db = client[DB_NAME]
            audit = db.audit_logs.find_one(
                {"action": "brevo_org_lists_toggle"}, sort=[("created_at", -1)])
            assert audit is not None
        finally:
            client.close()
        # Toggle OFF (back to clean)
        r = sa.put(f"{API}/platform/brevo/org-lists/settings", json={"enabled": False}, timeout=20)
        assert r.status_code == 200 and r.json()["enabled"] is False


# ----- Preview endpoint -----

class TestPreview:
    def test_preview_requires_superadmin(self, admin_sess, qa_org_id):
        r = admin_sess.get(f"{API}/platform/brevo/org-lists/preview",
                           params={"org_id": qa_org_id}, timeout=20)
        assert r.status_code == 403

    def test_preview_shape_and_counts(self, sa, qa_org_id):
        r = sa.get(f"{API}/platform/brevo/org-lists/preview",
                   params={"org_id": qa_org_id}, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["org"]["id"] == qa_org_id
        lists = data["lists"]
        cats = [l["category"] for l in lists]
        assert cats == ["staff", "collaboratori", "utenti_invitati", "volontari", "referenti_aziendali"]
        # Verify naming pattern slug_Label
        suffixes = {"staff": "Staff", "collaboratori": "Collaboratori",
                    "utenti_invitati": "Utenti_invitati",
                    "volontari": "Volontari", "referenti_aziendali": "Referenti_Aziendali"}
        for l in lists:
            assert l["list_name"].endswith("_" + suffixes[l["category"]]), l["list_name"]
            assert isinstance(l["contacts"], int) and l["contacts"] >= 0

        # Validate counts vs DB
        client = MongoClient(MONGO_URL)
        try:
            db = client[DB_NAME]
            EMAIL_RX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
            # staff/collaboratori/volontari from staff presences
            cat_by = {"staff": "staff", "collaboratore": "collaboratori", "volontario": "volontari"}
            counts = {"staff": set(), "collaboratori": set(), "volontari": set()}
            links = list(db.staff.find({"org_id": qa_org_id}, {"persona_id": 1, "categoria": 1}))
            pids = list({l["persona_id"] for l in links if l.get("persona_id")})
            persons = {p["id"]: p for p in db.persons.find(
                {"org_id": qa_org_id, "id": {"$in": pids}}, {"id": 1, "email": 1})}
            for l in links:
                c = cat_by.get(l.get("categoria"))
                if not c:
                    continue
                p = persons.get(l.get("persona_id"))
                em = (p or {}).get("email") or ""
                em = em.strip().lower()
                if EMAIL_RX.match(em):
                    counts[c].add(em)
            # referenti
            rel_pids = {r["person_id"] for r in db.person_companies.find(
                {"org_id": qa_org_id}, {"person_id": 1})}
            ref = set()
            for p in db.persons.find({"org_id": qa_org_id,
                                      "$or": [{"id": {"$in": list(rel_pids)}},
                                              {"azienda_id": {"$nin": [None, ""]}}]},
                                     {"email": 1}):
                em = (p.get("email") or "").strip().lower()
                if EMAIL_RX.match(em):
                    ref.add(em)
            # utenti invitati
            org = db.organizations.find_one({"id": qa_org_id}, {"owner_user_id": 1}) or {}
            mems = list(db.memberships.find(
                {"org_id": qa_org_id, "active": True,
                 "user_id": {"$ne": org.get("owner_user_id")}}, {"user_id": 1}))
            inv = set()
            for u in db.users.find(
                {"user_id": {"$in": [m["user_id"] for m in mems]},
                 "role": {"$ne": "superadmin"}}, {"email": 1}):
                em = (u.get("email") or "").strip().lower()
                if EMAIL_RX.match(em):
                    inv.add(em)
        finally:
            client.close()

        api_counts = {l["category"]: l["contacts"] for l in lists}
        assert api_counts["staff"] == len(counts["staff"])
        assert api_counts["collaboratori"] == len(counts["collaboratori"])
        assert api_counts["volontari"] == len(counts["volontari"])
        assert api_counts["referenti_aziendali"] == len(ref)
        assert api_counts["utenti_invitati"] == len(inv)


# ----- Sync endpoint gating -----

class TestSyncGating:
    def test_sync_400_when_disabled(self, sa, qa_org_id):
        sa.put(f"{API}/platform/brevo/org-lists/settings", json={"enabled": False}, timeout=20)
        r = sa.post(f"{API}/platform/brevo/org-lists/sync/{qa_org_id}", timeout=20)
        assert r.status_code == 400
        assert "Attiva" in (r.json().get("detail") or "")

    def test_sync_400_when_enabled_but_brevo_not_configured(self, sa, qa_org_id):
        # Only runs when the environment has no Brevo key (expected per the test note)
        cfg = sa.get(f"{API}/platform/brevo/org-lists/settings").json()
        if cfg.get("configured"):
            pytest.skip("Brevo is configured in this env; cannot assert 'not configured' path.")
        sa.put(f"{API}/platform/brevo/org-lists/settings", json={"enabled": True}, timeout=20)
        try:
            r = sa.post(f"{API}/platform/brevo/org-lists/sync/{qa_org_id}", timeout=20)
            assert r.status_code == 400
            assert "Brevo non configurato" in (r.json().get("detail") or "")
        finally:
            sa.put(f"{API}/platform/brevo/org-lists/settings", json={"enabled": False}, timeout=20)


# ----- Unit tests with mocked BrevoClient (NO network) -----

class _FakeBrevoClient:
    """Fully in-memory Brevo client. Mimics only what brevo_org_lists uses."""
    def __init__(self):
        self.folders_store = []
        self.lists_store = {}  # list_id -> {name, folderId}
        self.contacts = {}      # email -> {email, listIds, listUnsubscribed, attributes}
        self.next_folder_id = 1
        self.next_list_id = 100
        self.create_folder_calls = 0
        self.create_list_calls = 0
        self.create_contact_calls = 0
        self.add_existing_calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return None

    async def folders(self, limit=50):
        return list(self.folders_store)

    async def create_folder(self, name):
        self.create_folder_calls += 1
        f = {"id": self.next_folder_id, "name": name}
        self.next_folder_id += 1
        self.folders_store.append(f)
        return f

    async def create_list(self, name, folder_id):
        self.create_list_calls += 1
        lid = self.next_list_id
        self.next_list_id += 1
        self.lists_store[lid] = {"name": name, "folderId": folder_id}
        return {"id": lid, "name": name, "folderId": folder_id}

    async def get_contact(self, email):
        return self.contacts.get(email.lower())

    async def create_contact(self, email, list_id, attributes=None):
        self.create_contact_calls += 1
        self.contacts[email.lower()] = {
            "email": email.lower(), "listIds": [list_id], "listUnsubscribed": [],
            "attributes": attributes or {},
        }
        return {"id": len(self.contacts)}

    async def add_existing_to_list(self, email, list_id):
        self.add_existing_calls += 1
        c = self.contacts[email.lower()]
        if list_id not in c["listIds"]:
            c["listIds"].append(list_id)
        return {"ok": True}


@pytest.fixture
def fake_client_module():
    """Patch brevo_client.BrevoClient and is_configured; yield (module, fake)."""
    import brevo_client
    import brevo_org_lists
    importlib.reload(brevo_org_lists)  # ensure fresh binding
    fake = _FakeBrevoClient()
    orig_cls = brevo_client.BrevoClient
    orig_cfg = brevo_client.is_configured

    def _factory(*a, **kw):
        return fake

    brevo_client.BrevoClient = _factory
    brevo_client.is_configured = lambda: True
    try:
        yield brevo_org_lists, fake
    finally:
        brevo_client.BrevoClient = orig_cls
        brevo_client.is_configured = orig_cfg


@pytest.fixture
def temp_motor_db():
    """Isolated motor DB; dropped after test."""
    from motor.motor_asyncio import AsyncIOMotorClient
    name = f"brevo_orglists_selftest_{uuid.uuid4().hex[:8]}"
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[name]
    yield db
    async def _drop():
        await client.drop_database(name)
        client.close()
    asyncio.get_event_loop().run_until_complete(_drop())


class TestSyncOrgUnit:
    def test_sync_org_lazy_create_and_idempotent(self, fake_client_module):
        mod, fake = fake_client_module
        from motor.motor_asyncio import AsyncIOMotorClient
        name = f"brevo_orglists_selftest_{uuid.uuid4().hex[:8]}"
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[name]

        async def run():
            org = {"id": "org_x", "nome": "Acme SRL"}
            # Seed: staff has 1 staff person + 1 collaboratore; no volontari; 1 referente; no invited
            await db.staff.insert_many([
                {"org_id": "org_x", "persona_id": "p1", "categoria": "staff"},
                {"org_id": "org_x", "persona_id": "p2", "categoria": "collaboratore"},
            ])
            await db.persons.insert_many([
                {"id": "p1", "org_id": "org_x", "email": "s1@test.io", "nome": "Mario", "cognome": "Rossi"},
                {"id": "p2", "org_id": "org_x", "email": "c1@test.io", "nome": "Lucia", "cognome": "Verdi"},
                {"id": "p3", "org_id": "org_x", "email": "ref@test.io", "nome": "Giulia", "cognome": "Bianchi",
                 "azienda_id": "a1"},
            ])
            await db.organizations.insert_one({"id": "org_x", "nome": "Acme SRL", "owner_user_id": "u_owner"})

            stats1 = await mod.sync_org(db, org)
            # staff + collaboratori + referenti_aziendali = 3 categories, no volontari / utenti_invitati
            assert set(stats1.keys()) == {"staff", "collaboratori", "referenti_aziendali"}
            assert fake.create_folder_calls == 1
            assert fake.create_list_calls == 3
            # list naming slug_Label
            names = {l["name"] for l in fake.lists_store.values()}
            assert "Acme_SRL_Staff" in names
            assert "Acme_SRL_Collaboratori" in names
            assert "Acme_SRL_Referenti_Aziendali" in names
            # contacts created
            assert fake.create_contact_calls == 3

            # Second run — must reuse list_ids (no new list), existing contacts -> gia_presente (no add)
            stats2 = await mod.sync_org(db, org)
            assert fake.create_list_calls == 3  # unchanged
            for cat, s in stats2.items():
                assert s["gia_presente"] >= 1
                assert s["creato"] == 0

            # Simulate a new contact in staff category → create_contact; existing untouched
            await db.staff.insert_one({"org_id": "org_x", "persona_id": "p4", "categoria": "staff"})
            await db.persons.insert_one(
                {"id": "p4", "org_id": "org_x", "email": "s2@test.io", "nome": "X", "cognome": "Y"})
            before_create = fake.create_contact_calls
            stats3 = await mod.sync_org(db, org)
            assert fake.create_contact_calls == before_create + 1
            assert stats3["staff"]["creato"] == 1

            # Simulate an unsubscribed contact: not re-added, counted "disiscritto"
            # Grab the staff list id and mark s1 unsubscribed
            staff_lid = (await db.brevo_org_lists.find_one({"org_id": "org_x", "category": "staff"}))["list_id"]
            fake.contacts["s1@test.io"]["listUnsubscribed"] = [staff_lid]
            before_add = fake.add_existing_calls
            stats4 = await mod.sync_org(db, org)
            assert stats4["staff"]["disiscritto"] >= 1
            # No "aggiunto" and no add_existing_to_list for s1
            assert fake.add_existing_calls == before_add  # all were already in list

        try:
            asyncio.get_event_loop().run_until_complete(run())
        finally:
            asyncio.get_event_loop().run_until_complete(client.drop_database(name))
            client.close()

    def test_sync_invited_user_only_adds_to_utenti_invitati(self, fake_client_module):
        mod, fake = fake_client_module
        from motor.motor_asyncio import AsyncIOMotorClient
        name = f"brevo_orglists_selftest_{uuid.uuid4().hex[:8]}"
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[name]

        async def run():
            # Enable toggle in this temp DB
            await db.settings.update_one({"key": mod.SETTING_KEY},
                                         {"$set": {"key": mod.SETTING_KEY, "value": True}}, upsert=True)
            await db.organizations.insert_one({"id": "org_y", "nome": "Beta", "owner_user_id": "u_owner"})
            await db.memberships.insert_one({"org_id": "org_y", "user_id": "u1", "active": True})
            await db.users.insert_one({"user_id": "u1", "email": "inv@test.io", "role": "admin",
                                       "nome": "I", "cognome": "N"})
            # Also seed a staff person; must NOT appear in sync_invited_user call
            await db.staff.insert_one({"org_id": "org_y", "persona_id": "p1", "categoria": "staff"})
            await db.persons.insert_one(
                {"id": "p1", "org_id": "org_y", "email": "staff@test.io", "nome": "S", "cognome": "T"})

            res = await mod.sync_invited_user(db, "u1", "org_y")
            assert res is not None
            assert set(res.keys()) == {"utenti_invitati"}
            # Only one list created
            assert fake.create_list_calls == 1
            # Only one contact created (inv@test.io)
            assert "inv@test.io" in fake.contacts
            assert "staff@test.io" not in fake.contacts

        try:
            asyncio.get_event_loop().run_until_complete(run())
        finally:
            asyncio.get_event_loop().run_until_complete(client.drop_database(name))
            client.close()


# ----- Unit: sync_registered_user gating 'invited' -----

class TestSyncRegisteredGating:
    def test_skips_invited_for_non_registration_source(self):
        """Non self_registered, non owner_user_id, source != 'registration' → skipped reason=invited.
        For source == 'registration' it should NOT skip (will proceed, but we mock brevo_funnel to no-op)."""
        import server
        from motor.motor_asyncio import AsyncIOMotorClient

        name = f"brevo_regsync_selftest_{uuid.uuid4().hex[:8]}"
        client = AsyncIOMotorClient(MONGO_URL)
        tmp_db = client[name]

        # Mock brevo_funnel bits + swap server.db
        orig_db = server.db
        orig_is_cfg = server.brevo_funnel.is_configured
        orig_upsert = getattr(server.brevo_funnel, "upsert_registered_contact", None)
        orig_ensure = getattr(server.brevo_funnel, "ensure_user_attributes", None)
        orig_regid = getattr(server, "_registered_list_id", None)
        server.db = tmp_db
        server.brevo_funnel.is_configured = lambda: True

        async def _noop_upsert(**kw):
            return {"ok": True}

        async def _noop_ensure():
            return None

        async def _noop_regid(create=True):
            return 999

        server.brevo_funnel.upsert_registered_contact = _noop_upsert
        server.brevo_funnel.ensure_user_attributes = _noop_ensure
        server._registered_list_id = _noop_regid

        async def run():
            # user is NOT self_registered, NOT owner of any org, has active membership
            await tmp_db.users.insert_one(
                {"user_id": "u_invited", "email": "inv@test.io", "role": "admin",
                 "nome": "A", "cognome": "B"})
            await tmp_db.memberships.insert_one(
                {"user_id": "u_invited", "org_id": "org_z", "active": True})

            r1 = await server.sync_registered_user("u_invited", "org_z", source="invite_accepted")
            assert r1.get("skipped") is True and r1.get("reason") == "invited", r1

            r2 = await server.sync_registered_user("u_invited", "org_z", source="profile_edit")
            assert r2.get("skipped") is True and r2.get("reason") == "invited", r2

            # Now source='registration' — must NOT skip for 'invited' reason
            r3 = await server.sync_registered_user("u_invited", "org_z", source="registration")
            # Either ok True (mocked) or skipped for a *different* reason (not 'invited').
            assert r3.get("reason") != "invited", r3

        try:
            asyncio.get_event_loop().run_until_complete(run())
        finally:
            server.db = orig_db
            server.brevo_funnel.is_configured = orig_is_cfg
            if orig_upsert is not None:
                server.brevo_funnel.upsert_registered_contact = orig_upsert
            if orig_ensure is not None:
                server.brevo_funnel.ensure_user_attributes = orig_ensure
            if orig_regid is not None:
                server._registered_list_id = orig_regid
            asyncio.get_event_loop().run_until_complete(client.drop_database(name))
            client.close()
