"""Demo CRMEvent post-registrazione: disponibilità Super Admin → Demo, prenotazione 30 min con Google Meet (separata dall'Assistenza)."""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

import demo_booking
import gcal_utils
import video_support

logger = logging.getLogger("demo_slots")
ROME = ZoneInfo("Europe/Rome")
DURATION_MIN = 30


class Window(BaseModel):
    weekday: int
    start: str
    end: str


class ConfigIn(BaseModel):
    weekly: list[Window] = []
    closed_dates: list[str] = []
    min_notice_hours: int = 12
    horizon_days: int = 30


class BookIn(BaseModel):
    slot_key: str
    nome: str
    cognome: Optional[str] = None
    telefono: Optional[str] = None
    organizzazione: Optional[str] = None


def _now():
    return datetime.now(timezone.utc)


def _iso(d):
    return d.astimezone(timezone.utc).isoformat()


def build_router(db, require_admin, require_superadmin, record_audit, app_url: str) -> APIRouter:
    r = APIRouter(prefix="/api")
    st = {"idx": False}

    async def _idx():
        if not st["idx"]:
            await db.demo_slot_locks.create_index("slot", unique=True)
            st["idx"] = True

    async def _cfg() -> dict:
        return await db.demo_slot_config.find_one({"id": "config"}, {"_id": 0}) or {
            "id": "config", "weekly": [], "closed_dates": [], "min_notice_hours": 12, "horizon_days": 30}

    async def _busy(tmin, tmax) -> list:
        if video_support.simulation():
            return []
        vcfg = await db.video_support_config.find_one({"id": "config"}, {"_id": 0}) or {}
        conn = await db.calendar_connections.find_one({"user_id": vcfg.get("calendar_user_id")}, {"_id": 0}) if vcfg.get("calendar_user_id") else None
        if not (conn and gcal_utils.is_configured()):
            return []
        try:
            return gcal_utils.freebusy(conn["tokens"], conn.get("calendar_id") or "primary", _iso(tmin), _iso(tmax))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"demo freebusy failed: {type(e).__name__}")
            return []

    async def slots() -> list:
        cfg, now = await _cfg(), _now()
        start_min, horizon = now + timedelta(hours=cfg.get("min_notice_hours", 12)), now + timedelta(days=cfg.get("horizon_days", 30))
        taken = set(await db.demo_slot_locks.distinct("slot")) | set(await db.video_support_bookings.distinct("slot_lock", {"slot_lock": {"$type": "string"}}))
        busy = [(datetime.fromisoformat(s.replace("Z", "+00:00")), datetime.fromisoformat(e.replace("Z", "+00:00"))) for s, e in await _busy(now, horizon)]
        closed, out, day = set(cfg.get("closed_dates") or []), [], now.astimezone(ROME).date()
        while datetime.combine(day, datetime.min.time(), ROME) <= horizon:
            if day.isoformat() not in closed:
                for w in cfg.get("weekly") or []:
                    if w["weekday"] != day.weekday():
                        continue
                    cur = datetime.strptime(f"{day.isoformat()}T{w['start']}", "%Y-%m-%dT%H:%M").replace(tzinfo=ROME)
                    end = datetime.strptime(f"{day.isoformat()}T{w['end']}", "%Y-%m-%dT%H:%M").replace(tzinfo=ROME)
                    while cur + timedelta(minutes=DURATION_MIN) <= end:
                        fin, key = cur + timedelta(minutes=DURATION_MIN), cur.strftime("%Y-%m-%dT%H:%M")
                        if start_min <= cur <= horizon and key not in taken and not any(b0 < fin and b1 > cur for b0, b1 in busy):
                            out.append({"slot_key": key, "start": _iso(cur), "end": _iso(fin)})
                        cur = fin
            day += timedelta(days=1)
        return sorted({s["slot_key"]: s for s in out}.values(), key=lambda s: s["slot_key"])

    @r.get("/demo/welcome")
    async def welcome_info(user: dict = Depends(require_admin)):
        u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "welcome_demo": 1})
        lead = await db.leads.find_one({"user_id": user["user_id"], "demo_status": {"$in": ["confermata", "riprogrammata"]}}, {"_id": 0, "demo_slot": 1, "demo_meet_link": 1})
        org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0, "nome": 1})
        return {"state": (u or {}).get("welcome_demo"), "booking": lead, "duration_min": DURATION_MIN,
                "prefill": {"nome": user.get("nome") or (user.get("name") or "").split(" ")[0], "cognome": user.get("cognome") or "",
                            "email": user.get("email"), "telefono": user.get("telefono") or "", "organizzazione": (org or {}).get("nome") or ""}}

    @r.get("/demo/slots")
    async def get_slots(user: dict = Depends(require_admin)):
        return {"slots": await slots()}

    @r.post("/demo/welcome/dismiss")
    async def dismiss(user: dict = Depends(require_admin)):
        await db.users.update_one({"user_id": user["user_id"], "welcome_demo": "pending"}, {"$set": {"welcome_demo": "dismissed"}})
        return {"ok": True}

    @r.post("/demo/welcome/book")
    async def book(body: BookIn, user: dict = Depends(require_admin)):
        await _idx()
        if not (user.get("perm") or {}).get("admin"):
            raise HTTPException(status_code=403, detail="Prenotazione riservata all'organizzatore")
        if body.slot_key not in {s["slot_key"] for s in await slots()}:
            raise HTTPException(status_code=409, detail="L'orario selezionato non è più disponibile")
        email = (user.get("email") or "").lower()
        if await db.leads.find_one({"email": email, "demo_status": {"$in": ["confermata", "riprogrammata"]}, "demo_slot": {"$gt": datetime.now(ROME).strftime("%Y-%m-%dT%H:%M")}}):
            raise HTTPException(status_code=400, detail="Hai già una demo prenotata")
        lid = (await db.leads.find_one({"email": email}, {"_id": 0, "id": 1}) or {}).get("id") or uuid.uuid4().hex
        try:
            await db.demo_slot_locks.insert_one({"slot": body.slot_key, "lead_id": lid, "created_at": _iso(_now())})
        except DuplicateKeyError:
            raise HTTPException(status_code=409, detail="L'orario selezionato è appena stato prenotato")
        prev = await db.leads.find_one({"id": lid}, {"_id": 0})
        fields = {"nome": body.nome.strip(), "cognome": (body.cognome or "").strip(), "telefono": (body.telefono or "").strip(),
                  "organizzazione": (body.organizzazione or "").strip(), "email": email, "user_id": user["user_id"], "org_id": user["org_id"],
                  "demo_slot": body.slot_key, "demo_status": "confermata", "demo_source": "benvenuto_registrazione", "updated_at": _iso(_now())}
        lead = {**(prev or {"id": lid, "created_at": _iso(_now()), "source": "benvenuto_registrazione", "funnel_status": "trial_started"}), **fields,
                "demo_event_id": None, "demo_meet_link": None}
        meet = await demo_booking.meet_for_demo(db, lead, "create")
        if not meet.get("demo_meet_link"):
            await db.demo_slot_locks.delete_one({"slot": body.slot_key, "lead_id": lid})
            raise HTTPException(status_code=502, detail="Non è stato possibile creare l'appuntamento Google Meet. Riprova più tardi o scegli un altro orario.")
        lead.update(meet)
        await db.leads.update_one({"id": lid}, {"$set": lead}, upsert=True)
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"welcome_demo": "booked"}})
        try:
            await demo_booking.send_operational(lead, "confermata", app_url)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"demo email failed: {type(e).__name__}")
        await record_audit(user, "demo_welcome_booked", org_id=user["org_id"], detail=demo_booking.fmt_slot(body.slot_key), meta={"lead_id": lid})
        return {"ok": True, "slot_key": body.slot_key, "meet_link": lead["demo_meet_link"], "simulated": bool(lead.get("demo_meet_simulated"))}

    @r.get("/platform/demo/config")
    async def get_cfg(admin: dict = Depends(require_superadmin)):
        vcfg = await db.video_support_config.find_one({"id": "config"}, {"_id": 0}) or {}
        conn = await db.calendar_connections.find_one({"user_id": vcfg.get("calendar_user_id")}, {"_id": 0, "google_email": 1}) if vcfg.get("calendar_user_id") else None
        return {**(await _cfg()), "calendar_connected": bool(conn), "calendar_email": (conn or {}).get("google_email"),
                "gcal_configured": gcal_utils.is_configured(), "simulation": video_support.simulation()}

    @r.put("/platform/demo/config")
    async def put_cfg(body: ConfigIn, admin: dict = Depends(require_superadmin)):
        for w in body.weekly:
            if not (0 <= w.weekday <= 6) or w.start >= w.end:
                raise HTTPException(status_code=400, detail="Fascia oraria non valida")
            for t in (w.start, w.end):
                datetime.strptime(t, "%H:%M")
        doc = {"id": "config", "weekly": [w.model_dump() for w in body.weekly], "closed_dates": sorted(set(body.closed_dates)),
               "min_notice_hours": max(0, body.min_notice_hours), "horizon_days": min(max(1, body.horizon_days), 120), "updated_at": _iso(_now())}
        await db.demo_slot_config.update_one({"id": "config"}, {"$set": doc}, upsert=True)
        await record_audit(admin, "demo_config", meta={"windows": len(doc["weekly"])})
        return await get_cfg(admin)

    return r
