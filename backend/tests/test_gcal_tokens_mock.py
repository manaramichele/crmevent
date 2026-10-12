"""Test simulati Google Calendar multiutente: cifratura, refresh persistente, revoca, separazione, migrazione (nessun token reale)."""
import asyncio
import base64
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

import gcal_tokens as T  # noqa: E402

KEY = "k1:" + base64.b64encode(os.urandom(32)).decode()


class Resp:
    def __init__(self, status, data):
        self.status_code, self._d = status, data

    def json(self):
        return self._d


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("GOOGLE_TOKEN_ENCRYPTION_KEY", KEY)


def test_encrypt_roundtrip_and_rotation(monkeypatch):
    t = {"access_token": "FAKE_A", "refresh_token": "FAKE_R"}
    e = T.encrypt(t)
    assert "FAKE" not in str(e) and e["kid"] == "k1" and T.decrypt(e) == t
    monkeypatch.setenv("GOOGLE_TOKEN_ENCRYPTION_KEY", "k2:" + base64.b64encode(os.urandom(32)).decode() + "," + KEY)
    assert T.decrypt(e) == t and T.encrypt(t)["kid"] == "k2"
    monkeypatch.setenv("GOOGLE_TOKEN_ENCRYPTION_KEY", "k1:" + base64.b64encode(os.urandom(32)).decode())
    with pytest.raises(T.GCalError) as x:
        T.decrypt(e)
    assert x.value.code == "key_missing"
    monkeypatch.delenv("GOOGLE_TOKEN_ENCRYPTION_KEY")
    with pytest.raises(T.GCalError):
        T.store_fields(t)


async def _seed(db, uid, exp_delta, refresh="FAKE_R", plain=False):
    toks = {"access_token": f"FAKE_A_{uid}", "refresh_token": refresh}
    doc = {"user_id": uid, "org_id": f"TEST_org_{uid}", "google_email": f"{uid}@gmail.test", "google_sub": uid, "calendar_id": "primary",
           "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=exp_delta)).isoformat(), "token_rev": 1}
    doc.update({"tokens": toks} if plain else {"tokens_enc": T.encrypt(toks)})
    await db.calendar_connections.insert_one(doc)


def test_refresh_persist_revoke_separation(monkeypatch):
    db = _db()
    a, b = f"TEST_gA_{uuid.uuid4().hex[:6]}", f"TEST_gB_{uuid.uuid4().hex[:6]}"
    calls = []

    def fake_post(url, data=None, timeout=None, **k):
        calls.append(data["refresh_token"])
        if data["refresh_token"] == "REVOKED":
            return Resp(400, {"error": "invalid_grant"})
        if data["refresh_token"] == "DOWN":
            return Resp(503, {})
        return Resp(200, {"access_token": "FAKE_NEW", "expires_in": 3599})

    monkeypatch.setattr(T.requests, "post", fake_post)

    async def go():
        try:
            await _seed(db, a, 3000)
            await _seed(db, b, -10)
            ca = await T.load(db, a)
            assert ca["tokens"]["access_token"] == f"FAKE_A_{a}" and not calls  # valido: nessun refresh
            cb = await T.load(db, b)
            assert cb["tokens"]["access_token"] == "FAKE_NEW" and cb["tokens"]["refresh_token"] == "FAKE_R"
            raw = await db.calendar_connections.find_one({"user_id": b})
            assert "tokens" not in raw and T.decrypt(raw["tokens_enc"])["access_token"] == "FAKE_NEW" and raw["token_rev"] == 2
            assert (await db.calendar_connections.find_one({"user_id": a}))["token_rev"] == 1  # A intatto
            calls.clear()
            again = await T.load(db, b)  # nuovo accesso dopo il rinnovo: nessun nuovo refresh
            assert again["tokens"]["access_token"] == "FAKE_NEW" and not calls
            # due rinnovi simultanei: un solo salvataggio vince, l'altro usa il più recente
            await db.calendar_connections.update_one({"user_id": b}, {"$set": {"expires_at": datetime.now(timezone.utc).isoformat()}})
            r1, r2 = await asyncio.gather(T.load(db, b), T.load(db, b))
            assert r1["tokens"]["access_token"] == r2["tokens"]["access_token"] == "FAKE_NEW"
            # revoca
            await db.calendar_connections.update_one({"user_id": a}, {"$set": {"tokens_enc": T.encrypt({"access_token": "x", "refresh_token": "REVOKED"}), "expires_at": datetime.now(timezone.utc).isoformat()}})
            with pytest.raises(T.GCalError) as x:
                await T.load(db, a)
            assert x.value.code == "reauthorization_required"
            ra = await db.calendar_connections.find_one({"user_id": a})
            assert ra["status"] == "reauthorization_required" and ra.get("tokens_enc")  # dati non cancellati
            # Google non disponibile
            await db.calendar_connections.update_one({"user_id": b}, {"$set": {"tokens_enc": T.encrypt({"access_token": "x", "refresh_token": "DOWN"}), "expires_at": datetime.now(timezone.utc).isoformat()}})
            with pytest.raises(T.GCalError) as y:
                await T.load(db, b)
            assert y.value.code == "temporary"
            assert (await db.calendar_connections.find_one({"user_id": b}))["status"] == "temporary_error"
        finally:
            await db.calendar_connections.delete_many({"user_id": {"$in": [a, b]}})

    asyncio.run(go())


def test_migration_dry_run_and_apply(tmp_path):
    from scripts import migrate_gcal_tokens as M
    db = _db()
    u = f"TEST_gM_{uuid.uuid4().hex[:6]}"

    async def go():
        try:
            await _seed(db, u, 3000, plain=True)
            r = await M.main(False, None, db)
            assert r["plain"] >= 1 and r["migrated"] == 0 and "tokens" in await db.calendar_connections.find_one({"user_id": u})
            assert (await M.main(True, None, db)).get("error") == "backup_required"
            bk = tmp_path / "b.json"
            r2 = await M.main(True, str(bk), db)
            assert r2["migrated"] >= 1 and oct(os.stat(bk).st_mode)[-3:] == "600"
            doc = await db.calendar_connections.find_one({"user_id": u})
            assert "tokens" not in doc and T.decrypt(doc["tokens_enc"])["access_token"] == f"FAKE_A_{u}"
            assert (await M.main(True, str(bk), db))["plain"] == 0  # idempotente
        finally:
            await db.calendar_connections.delete_many({"user_id": u})

    asyncio.run(go())
