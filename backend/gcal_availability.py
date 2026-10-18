"""Disponibilità Google Calendar su più calendari (solo free/busy, in tempo reale, nessun appuntamento salvato)."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

import gcal_tokens
import gcal_utils

logger = logging.getLogger("gcal_availability")
MAX_CALENDARS = 25


class CheckFailed(Exception):
    pass


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def monitored(conn: dict) -> list:
    ids = conn.get("availability_calendar_ids")
    return ids if ids else [conn.get("calendar_id") or "primary"]


async def _record(db, user_id: str, ids: list, errors: dict, failed: str = None):
    now = datetime.now(timezone.utc).isoformat()
    st = "error" if failed else ("partial" if errors else "ok")
    upd = {"availability.status": st, "availability.last_check_at": now, "availability.monitored": len(ids),
           "availability.errors": ([{"calendar_id": "*", "reason": failed}] if failed else [{"calendar_id": k, "reason": v} for k, v in errors.items()])}
    if not failed:
        upd["availability.last_ok_at"] = now
        upd["last_sync_at"] = now
    await db.calendar_connections.update_one({"user_id": user_id}, {"$set": upd})


async def busy(db, user_id: str, tmin: datetime, tmax: datetime, strict: bool = False) -> list:
    """Intervalli occupati (datetime UTC) uniti da tutti i calendari monitorati. strict: solleva CheckFailed se Google non risponde."""
    try:
        conn = await gcal_tokens.load(db, user_id)
    except gcal_tokens.GCalError as e:
        await _record(db, user_id, [], {}, e.code)
        if strict:
            raise CheckFailed(e.message)
        return []
    ids = monitored(conn)
    try:
        raw, errors = await asyncio.to_thread(gcal_utils.freebusy_multi, conn["tokens"], ids, _iso(tmin), _iso(tmax))
    except Exception as e:  # noqa: BLE001
        logger.warning("freebusy failed: %s", type(e).__name__)
        await _record(db, user_id, ids, {}, "google_unavailable")
        if strict:
            raise CheckFailed("Google Calendar non risponde")
        return []
    await _record(db, user_id, ids, errors)
    if strict and errors and len(errors) == len(ids):
        raise CheckFailed("Nessun calendario leggibile")
    return [(datetime.fromisoformat(s.replace("Z", "+00:00")), datetime.fromisoformat(e.replace("Z", "+00:00"))) for s, e in raw]


async def assert_free(db, user_id: str, start: datetime, end: datetime):
    """Alla conferma: blocca se uno dei calendari è occupato o se il controllo non riesce."""
    for b0, b1 in await busy(db, user_id, start, end, strict=True):
        if b0 < end and b1 > start:
            return False
    return True


async def check_now(db, user_id: str) -> dict:
    now = datetime.now(timezone.utc)
    try:
        await busy(db, user_id, now, now + timedelta(days=30), strict=True)
    except CheckFailed:
        pass
    conn = await db.calendar_connections.find_one({"user_id": user_id}, {"_id": 0, "availability": 1})
    return (conn or {}).get("availability") or {}
