"""Verifica gcal_availability con Google simulato. Uso: python tests/check_gcal_availability.py"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import dotenv_values  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

import gcal_availability as GA  # noqa: E402
import gcal_tokens  # noqa: E402
import gcal_utils  # noqa: E402

e = dotenv_values(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
db = AsyncIOMotorClient(e["MONGO_URL"])[e["DB_NAME"]]
UID = "TEST_gcal_avail_user"
CALLS = []


async def fake_load(_db, uid):
    return await db.calendar_connections.find_one({"user_id": uid}, {"_id": 0}) | {"tokens": {}}


def fake_fb(tokens, ids, tmin, tmax):
    CALLS.append(ids)
    if MODE["fail"]:
        raise RuntimeError("down")
    data = {"personale": [("2026-11-02T09:00:00Z", "2026-11-02T10:00:00Z")], "lavoro": [("2026-11-02T13:00:00Z", "2026-11-02T13:30:00Z")]}
    busy = [b for i in ids for b in data.get(i, [])]
    return busy, ({"rotto": "notFound"} if "rotto" in ids else {})


MODE = {"fail": False}


async def main():
    gcal_tokens.load = fake_load
    gcal_utils.freebusy_multi = fake_fb
    await db.calendar_connections.delete_many({"user_id": UID})
    await db.calendar_connections.insert_one({"user_id": UID, "calendar_id": "crmevent"})
    t0 = datetime(2026, 11, 2, 0, 0, tzinfo=timezone.utc)
    await GA.busy(db, UID, t0, t0 + timedelta(days=1))
    assert CALLS[-1] == ["crmevent"], "default = calendario di destinazione"
    await db.calendar_connections.update_one({"user_id": UID}, {"$set": {"availability_calendar_ids": ["personale", "lavoro", "crmevent", "rotto"]}})
    b = await GA.busy(db, UID, t0, t0 + timedelta(days=1))
    assert len(b) == 2, b
    conn = await db.calendar_connections.find_one({"user_id": UID})
    assert conn["availability"]["status"] == "partial" and conn["availability"]["monitored"] == 4
    s = datetime(2026, 11, 2, 13, 15, tzinfo=timezone.utc)
    assert await GA.assert_free(db, UID, s, s + timedelta(minutes=30)) is False, "conflitto su 'lavoro'"
    s = datetime(2026, 11, 2, 11, 0, tzinfo=timezone.utc)
    assert await GA.assert_free(db, UID, s, s + timedelta(minutes=30)) is True
    MODE["fail"] = True
    assert await GA.busy(db, UID, t0, t0 + timedelta(days=1)) == [], "non strict: orari mostrati"
    try:
        await GA.assert_free(db, UID, s, s + timedelta(minutes=30))
        raise AssertionError("strict doveva fallire")
    except GA.CheckFailed:
        pass
    conn = await db.calendar_connections.find_one({"user_id": UID})
    assert conn["availability"]["status"] == "error" and conn["availability"]["last_ok_at"]
    await db.calendar_connections.delete_many({"user_id": UID})
    print("OK", conn["availability"])


asyncio.run(main())
