"""Assistenza in videochiamata (Google Meet) a crediti: disponibilità Super Admin, prenotazioni, annulli e riprogrammazioni."""
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

import gcal_utils
from email_utils import link_email, send_email

logger = logging.getLogger("video_support")
ROME = ZoneInfo("Europe/Rome")
SERVICE_KEY = "video_support"
DURATION_MIN = 30
POLICY_HOURS = 24
ACTIVE = ("in_creazione", "confermata")


def simulation() -> bool:
    """Meet simulato solo fuori produzione e con flag esplicito (mai addebiti/appuntamenti reali nei test)."""
    if os.environ.get("CRMEVENT_ENV", "").strip().lower() == "production":
        return False
    return os.environ.get("VIDEO_SUPPORT_MEET_SIMULATION", "").strip() == "1"


def _now():
    return datetime.now(timezone.utc)


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).isoformat()


def _slot_dt(slot_key: str) -> datetime:
    try:
        return datetime.strptime(slot_key, "%Y-%m-%dT%H:%M").replace(tzinfo=ROME)
    except ValueError:
        raise HTTPException(status_code=400, detail="Orario non valido")


def _fmt(slot_key: str) -> str:
    return _slot_dt(slot_key).strftime("%d/%m/%Y alle %H:%M")


class WeeklyWindow(BaseModel):
    weekday: int  # 0 = lunedì
    start: str
    end: str


class ConfigIn(BaseModel):
    weekly: list[WeeklyWindow] = []
    closed_dates: list[str] = []
    min_notice_hours: int = 24
    horizon_days: int = 30


class BookIn(BaseModel):
    slot_key: str
    confirm_cost: int
    note: Optional[str] = None


class SlotIn(BaseModel):
    slot_key: str


class CancelIn(BaseModel):
    reason: Optional[str] = None


class NoteIn(BaseModel):
    admin_note: str = ""


def build_router(db, require_admin, require_superadmin, record_audit, credits, plan=None) -> APIRouter:
    """credits: funzioni del sistema crediti esistente; plan: modulo abbonamenti (quote videochiamate per piano)."""
    r = APIRouter(prefix="/api")
    state = {"idx": False}

    async def _indexes():
        if not state["idx"]:
            await db.video_support_bookings.create_index("slot_lock", unique=True, partialFilterExpression={"slot_lock": {"$type": "string"}})
            state["idx"] = True

    async def _config() -> dict:
        return await db.video_support_config.find_one({"id": "config"}, {"_id": 0}) or {
            "id": "config", "weekly": [], "closed_dates": [], "min_notice_hours": 24, "horizon_days": 30}

    async def _service() -> dict:
        await credits["ensure_setup"]()
        return await db.credit_services.find_one({"key": SERVICE_KEY}, {"_id": 0}) or {}

    def _bookable(svc: dict) -> bool:
        return bool(svc.get("active") and svc.get("consumo_active") and svc.get("unit_cost") is not None)

    async def _calendar(cfg: dict) -> Optional[dict]:
        uid = cfg.get("calendar_user_id")
        return await db.calendar_connections.find_one({"user_id": uid}, {"_id": 0}) if uid else None

    async def _ready(cfg: dict) -> bool:
        return simulation() or (gcal_utils.is_configured() and bool(await _calendar(cfg)))

    async def _busy(cfg: dict, tmin: datetime, tmax: datetime) -> list:
        """Solo intervalli occupati (free/busy): mai titoli o dettagli degli appuntamenti."""
        conn = None if simulation() else await _calendar(cfg)
        if not conn:
            return []
        try:
            return gcal_utils.freebusy(conn["tokens"], conn.get("calendar_id") or "primary", _iso(tmin), _iso(tmax))
        except Exception as e:
            logger.warning(f"video_support freebusy failed: {type(e).__name__}")
            return []

    async def _policy(org_id: str) -> dict:
        return await plan["video_policy"](org_id) if plan else {"mode": "credits"}

    async def _slots(cfg: dict, enforce_notice: bool = True, exclude_booking: Optional[str] = None, priority: bool = False) -> list:
        now = _now()
        notice = cfg.get("min_notice_hours", 24)
        if priority:
            notice = min(notice, plan["gold_notice_hours"])  # GOLD: disponibilità prioritaria (preavviso ridotto)
        start_min = now + timedelta(hours=notice if enforce_notice else 0)
        horizon = now + timedelta(days=cfg.get("horizon_days", 30))
        q = {"slot_lock": {"$type": "string"}}
        if exclude_booking:
            q["id"] = {"$ne": exclude_booking}
        taken = set(await db.video_support_bookings.distinct("slot_lock", q))
        busy = [(datetime.fromisoformat(s.replace("Z", "+00:00")), datetime.fromisoformat(e.replace("Z", "+00:00")))
                for s, e in await _busy(cfg, now, horizon)]
        closed = set(cfg.get("closed_dates") or [])
        out, day = [], now.astimezone(ROME).date()
        while datetime.combine(day, datetime.min.time(), ROME) <= horizon:
            if day.isoformat() not in closed:
                for w in cfg.get("weekly") or []:
                    if w["weekday"] != day.weekday():
                        continue
                    cur = datetime.strptime(f"{day.isoformat()}T{w['start']}", "%Y-%m-%dT%H:%M").replace(tzinfo=ROME)
                    end = datetime.strptime(f"{day.isoformat()}T{w['end']}", "%Y-%m-%dT%H:%M").replace(tzinfo=ROME)
                    while cur + timedelta(minutes=DURATION_MIN) <= end:
                        fin = cur + timedelta(minutes=DURATION_MIN)
                        key = cur.strftime("%Y-%m-%dT%H:%M")
                        if cur >= start_min and cur <= horizon and key not in taken and not any(b0 < fin and b1 > cur for b0, b1 in busy):
                            out.append({"slot_key": key, "start": _iso(cur), "end": _iso(fin)})
                        cur = fin
            day += timedelta(days=1)
        return sorted({s["slot_key"]: s for s in out}.values(), key=lambda s: s["slot_key"])

    async def _assert_free_slot(cfg, slot_key, enforce_notice=True, exclude_booking=None, priority=False):
        if slot_key not in {s["slot_key"] for s in await _slots(cfg, enforce_notice, exclude_booking, priority)}:
            raise HTTPException(status_code=409, detail="L'orario selezionato non è più disponibile")

    def _event_body(b: dict, start: datetime) -> dict:
        end = start + timedelta(minutes=DURATION_MIN)
        body = {"summary": f"Assistenza CRMEvent · {b['org_name']}",
                "description": f"Assistenza in videochiamata CRMEvent\nOrganizzazione: {b['org_name']}\nRichiedente: {b['user_name']} ({b['user_email']})"
                               + (f"\nNote: {b['note']}" if b.get("note") else ""),
                "start": {"dateTime": start.strftime("%Y-%m-%dT%H:%M:00"), "timeZone": "Europe/Rome"},
                "end": {"dateTime": end.strftime("%Y-%m-%dT%H:%M:00"), "timeZone": "Europe/Rome"}}
        if b.get("user_email"):
            body["attendees"] = [{"email": b["user_email"]}]
        return body

    async def _create_meet(cfg: dict, b: dict) -> dict:
        if simulation():
            return {"id": f"sim-{b['id'][:12]}", "meet_link": f"https://meet.google.com/sim-{b['id'][:3]}-{b['id'][3:7]}-{b['id'][7:10]}", "simulated": True}
        conn = await _calendar(cfg)
        if not (gcal_utils.is_configured() and conn):
            raise RuntimeError("calendario assistenza non collegato")
        ev = gcal_utils.create_meet_event(conn["tokens"], conn.get("calendar_id") or "primary", _event_body(b, _slot_dt(b["slot_key"])), b["id"])
        link = ev.get("hangoutLink") or next((e.get("uri") for e in (ev.get("conferenceData") or {}).get("entryPoints", []) if e.get("entryPointType") == "video"), None)
        if not link:
            raise RuntimeError("link Meet non generato")
        return {"id": ev["id"], "meet_link": link, "simulated": False}

    async def _gcal_call(cfg, b, fn):
        if simulation() or not b.get("google_event_id") or b.get("simulated"):
            return
        conn = await _calendar(cfg)
        if conn:
            try:
                fn(conn["tokens"], conn.get("calendar_id") or "primary")
            except Exception as e:
                logger.warning(f"video_support gcal update failed: {type(e).__name__}")

    async def _email(b: dict, intro: str, subject: str):
        if simulation() or not b.get("user_email"):
            logger.info(f"video_support email (simulata) booking={b['id']} subject={subject}")
            return
        try:
            await send_email(to=b["user_email"], subject=subject, html=link_email(
                name=b.get("user_name") or "", intro=intro, cta_label="Apri Google Meet", url=b["meet_link"],
                footer_note="Trovi il link anche in CRMEvent → Assistenza → Le mie prenotazioni."))
        except Exception as e:
            logger.warning(f"video_support email failed: {type(e).__name__}")

    async def _refund(b: dict, by: dict, reason: str) -> int:
        amt = int(b.get("credits_charged") or 0)
        if amt <= 0:
            return 0
        key = f"video_support_refund:{b['id']}"
        doc = {"id": uuid.uuid4().hex, "org_id": b["org_id"], "type": "credit", "status": "committed", "amount": amt,
               "reason_code": "video_support_refund", "service_key": SERVICE_KEY, "quantity": 1, "user_id": by.get("user_id"),
               "idempotency_key": key, "note": f"Riaccredito assistenza annullata ({reason})", "created_at": _iso(_now()), "settled_at": _iso(_now())}
        try:
            await db.credit_ledger.insert_one(doc)
        except DuplicateKeyError:
            return 0
        await db.organizations.update_one({"id": b["org_id"]}, {"$inc": {"credits.balance": amt, "credits.lifetime_spent": -amt},
                                                                "$set": {"credits.updated_at": _iso(_now())}})
        org = await db.organizations.find_one({"id": b["org_id"]}, {"_id": 0, "credits": 1})
        await db.credit_ledger.update_one({"id": doc["id"]}, {"$set": {"balance_after": (org.get("credits") or {}).get("balance", 0)}})
        return amt

    def _public(b: dict) -> dict:
        return {k: b.get(k) for k in ("id", "org_id", "org_name", "user_id", "user_name", "user_email", "slot_key", "start", "end",
                                      "status", "meet_link", "credits_charged", "refunded", "note", "reschedule_count",
                                      "cancelled_by", "cancel_reason", "simulated", "created_at", "charge_mode", "quota_period",
                                      "quota_consumed", "quota_refunded")}

    def _hours_left(b: dict) -> float:
        return (_slot_dt(b["slot_key"]) - _now()).total_seconds() / 3600

    async def _audit(actor, action, b, detail=None):
        await record_audit(actor, action, org_id=b["org_id"], org_name=b.get("org_name"), target_email=b.get("user_email"),
                           target_name=b.get("user_name"), detail=detail or _fmt(b["slot_key"]), meta={"booking_id": b["id"]})

    async def _cancel(b: dict, actor: dict, by_admin: bool, reason: Optional[str]) -> dict:
        if b["status"] != "confermata":
            raise HTTPException(status_code=400, detail="La prenotazione non è attiva")
        refund = by_admin or _hours_left(b) >= POLICY_HOURS
        res = await db.video_support_bookings.update_one({"id": b["id"], "status": "confermata"}, {
            "$set": {"status": "annullata", "cancelled_by": "superadmin" if by_admin else "organizzatore",
                     "cancel_reason": reason, "cancelled_at": _iso(_now())}, "$unset": {"slot_lock": ""}})
        if not res.modified_count:
            raise HTTPException(status_code=409, detail="Prenotazione già aggiornata")
        amt = 0
        if b.get("charge_mode") == "plan":
            if refund and b.get("quota_consumed") and not b.get("quota_refunded"):
                await _quota_back(b)
        else:
            amt = await _refund(b, actor, "Super Admin" if by_admin else "organizzatore") if refund else 0
        await db.video_support_bookings.update_one({"id": b["id"]}, {"$set": {"refunded": amt}})
        await _gcal_call(await _config(), b, lambda t, c: gcal_utils.delete_event(t, c, b["google_event_id"]))
        await _audit(actor, "video_support_cancelled", b, f"{_fmt(b['slot_key'])} · riaccredito {amt} crediti")
        return {"ok": True, "refunded": amt}

    async def _quota_back(b: dict) -> bool:
        res = await db.video_support_bookings.update_one({"id": b["id"], "quota_refunded": {"$ne": True}}, {"$set": {"quota_refunded": True}})
        if res.modified_count:
            await plan["video_release"](b["org_id"], b["quota_period"])
        return bool(res.modified_count)

    async def _reschedule(b: dict, slot_key: str, actor: dict, by_admin: bool) -> dict:
        if b["status"] != "confermata":
            raise HTTPException(status_code=400, detail="La prenotazione non è attiva")
        cfg = await _config()
        pr = b.get("charge_mode") == "plan" and bool((await _policy(b["org_id"])).get("priority"))
        await _assert_free_slot(cfg, slot_key, enforce_notice=not by_admin, exclude_booking=b["id"], priority=pr)
        start = _slot_dt(slot_key)
        upd = {"slot_key": slot_key, "slot_lock": slot_key, "start": _iso(start), "end": _iso(start + timedelta(minutes=DURATION_MIN))}
        try:
            res = await db.video_support_bookings.update_one({"id": b["id"], "status": "confermata", "slot_key": b["slot_key"]},
                                                             {"$set": upd, "$inc": {"reschedule_count": 0 if by_admin else 1}})
        except DuplicateKeyError:
            raise HTTPException(status_code=409, detail="L'orario selezionato non è più disponibile")
        if not res.modified_count:
            raise HTTPException(status_code=409, detail="Prenotazione già aggiornata")
        nb = {**b, **upd}
        await _gcal_call(cfg, b, lambda t, c: gcal_utils.patch_event(t, c, b["google_event_id"], {k: v for k, v in _event_body(nb, start).items() if k in ("start", "end")}))
        await _email(nb, f"La tua assistenza CRMEvent in videochiamata è stata spostata al {_fmt(slot_key)} (durata 30 minuti).", "Assistenza CRMEvent riprogrammata")
        await _audit(actor, "video_support_rescheduled", nb, f"{_fmt(b['slot_key'])} → {_fmt(slot_key)}")
        return {"ok": True, "slot_key": slot_key}

    async def _own(bid: str, user: dict) -> dict:
        b = await db.video_support_bookings.find_one({"id": bid, "org_id": user["org_id"]}, {"_id": 0})
        if not b or not ((user.get("perm") or {}).get("admin") or b["user_id"] == user["user_id"]):
            raise HTTPException(status_code=404, detail="Prenotazione non trovata")
        return b

    # ---------------- Organizzatore ----------------
    @r.get("/video-support/info")
    async def info(user: dict = Depends(require_admin)):
        svc, cfg = await _service(), await _config()
        pol = await _policy(user["org_id"])
        if pol["mode"] == "plan":
            return {"service": {"name": "Assistenza in videochiamata", "description": "Sessione di 30 minuti su Google Meet con un esperto CRMEvent, inclusa nel tuo piano.", "unit_cost": 0},
                    "available": pol["allowed"], "ready": pol["allowed"] and await _ready(cfg), "duration_min": DURATION_MIN,
                    "balance": 0, "policy_hours": POLICY_HOURS, "simulation": simulation(), "plan": pol}
        c = await credits["ensure_org"](user["org_id"])
        available = _bookable(svc)
        return {"service": {"name": svc.get("name"), "description": svc.get("description"), "unit_cost": svc.get("unit_cost")},
                "available": available, "ready": available and await _ready(cfg), "duration_min": DURATION_MIN,
                "balance": c.get("balance", 0), "policy_hours": POLICY_HOURS, "simulation": simulation(), "plan": pol}

    @r.get("/video-support/slots")
    async def slots(user: dict = Depends(require_admin)):
        svc, cfg = await _service(), await _config()
        pol = await _policy(user["org_id"])
        ok = pol["allowed"] if pol["mode"] == "plan" else _bookable(svc)
        if not ok or not await _ready(cfg):
            return {"slots": []}
        return {"slots": await _slots(cfg, priority=bool(pol.get("priority")))}

    @r.get("/video-support/bookings")
    async def my_bookings(user: dict = Depends(require_admin)):
        q = {"org_id": user["org_id"], "status": {"$in": ["confermata", "annullata"]}}
        if not (user.get("perm") or {}).get("admin"):
            q["user_id"] = user["user_id"]
        rows = await db.video_support_bookings.find(q, {"_id": 0}).sort("slot_key", -1).to_list(500)
        return {"bookings": [{**_public(b), "can_cancel_refund": b["status"] == "confermata" and _hours_left(b) >= POLICY_HOURS,
                              "can_reschedule": b["status"] == "confermata" and _hours_left(b) >= POLICY_HOURS and not b.get("reschedule_count")}
                             for b in rows]}

    @r.post("/video-support/bookings")
    async def book(body: BookIn, user: dict = Depends(require_admin)):
        await _indexes()
        svc, cfg = await _service(), await _config()
        pol = await _policy(user["org_id"])
        if pol["mode"] == "plan":
            return await _book_plan(body, user, cfg, pol)
        if not _bookable(svc):
            raise HTTPException(status_code=403, detail="Il servizio di assistenza in videochiamata non è ancora disponibile")
        if not await _ready(cfg):
            raise HTTPException(status_code=503, detail="Le prenotazioni non sono al momento disponibili")
        if int(svc["unit_cost"]) != body.confirm_cost:
            raise HTTPException(status_code=409, detail={"code": "cost_changed", "unit_cost": svc["unit_cost"], "message": "Il costo del servizio è cambiato: conferma di nuovo"})
        await _assert_free_slot(cfg, body.slot_key)
        c = await credits["ensure_org"](user["org_id"])
        if c.get("balance", 0) < svc["unit_cost"]:
            raise HTTPException(status_code=402, detail=f"Crediti insufficienti (saldo {c.get('balance', 0)}, richiesti {int(svc['unit_cost'])})")
        org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0, "nome": 1}) or {}
        start = _slot_dt(body.slot_key)
        nome = f"{user.get('cognome') or ''} {user.get('nome') or ''}".strip() or user.get("name") or user.get("email")
        b = {"id": uuid.uuid4().hex, "org_id": user["org_id"], "org_name": org.get("nome"), "user_id": user["user_id"],
             "user_name": nome, "user_email": user.get("email"), "slot_key": body.slot_key, "slot_lock": body.slot_key,
             "start": _iso(start), "end": _iso(start + timedelta(minutes=DURATION_MIN)), "status": "in_creazione",
             "note": (body.note or "").strip()[:1000] or None, "reschedule_count": 0, "credits_charged": 0, "created_at": _iso(_now())}
        try:
            await db.video_support_bookings.insert_one({**b})
        except DuplicateKeyError:
            raise HTTPException(status_code=409, detail="L'orario selezionato è appena stato prenotato")
        try:
            res = await credits["reserve"](user["org_id"], SERVICE_KEY, 1, user_id=user["user_id"],
                                           idempotency_key=f"video_support:{b['id']}", note=f"Assistenza videochiamata {_fmt(body.slot_key)}")
        except Exception:
            await db.video_support_bookings.update_one({"id": b["id"]}, {"$set": {"status": "errore", "error": "crediti"}, "$unset": {"slot_lock": ""}})
            raise
        try:
            ev = await _create_meet(cfg, b)
        except Exception as e:
            logger.error(f"video_support meet creation failed booking={b['id']}: {type(e).__name__}: {e}")
            await credits["release"](res["id"])
            await db.video_support_bookings.update_one({"id": b["id"]}, {"$set": {"status": "errore", "error": "appuntamento"}, "$unset": {"slot_lock": ""}})
            raise HTTPException(status_code=502, detail="Non è stato possibile creare l'appuntamento Google Meet. Nessun credito è stato addebitato: riprova più tardi.")
        settled = await credits["settle"](res["id"])
        upd = {"status": "confermata", "meet_link": ev["meet_link"], "google_event_id": ev["id"], "simulated": ev["simulated"],
               "reservation_id": res["id"], "credits_charged": -int(settled.get("amount") or 0)}
        await db.video_support_bookings.update_one({"id": b["id"]}, {"$set": upd})
        b.update(upd)
        await _email(b, f"La tua assistenza CRMEvent in videochiamata è confermata per il {_fmt(body.slot_key)} (durata 30 minuti). "
                        "Al momento dell'appuntamento apri il link Google Meet: potrai condividere lo schermo.", "Assistenza CRMEvent confermata")
        await _audit(user, "video_support_booked", b, f"{_fmt(body.slot_key)} · {b['credits_charged']} crediti")
        return _public(b)

    async def _book_plan(body: BookIn, user: dict, cfg: dict, pol: dict) -> dict:
        """Prenotazione inclusa nel piano: quota controllata e consumata in modo atomico sul backend, nessun credito."""
        if not pol["allowed"]:
            raise HTTPException(status_code=403, detail={"code": "video_quota", "message": pol.get("reason") or "Videochiamate non disponibili con il tuo piano"})
        if not await _ready(cfg):
            raise HTTPException(status_code=503, detail="Le prenotazioni non sono al momento disponibili")
        await _assert_free_slot(cfg, body.slot_key, priority=bool(pol.get("priority")))
        org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0, "nome": 1}) or {}
        start = _slot_dt(body.slot_key)
        nome = f"{user.get('cognome') or ''} {user.get('nome') or ''}".strip() or user.get("name") or user.get("email")
        b = {"id": uuid.uuid4().hex, "org_id": user["org_id"], "org_name": org.get("nome"), "user_id": user["user_id"],
             "user_name": nome, "user_email": user.get("email"), "slot_key": body.slot_key, "slot_lock": body.slot_key,
             "start": _iso(start), "end": _iso(start + timedelta(minutes=DURATION_MIN)), "status": "in_creazione",
             "note": (body.note or "").strip()[:1000] or None, "reschedule_count": 0, "credits_charged": 0,
             "charge_mode": "plan", "plan": pol.get("plan"), "priority": bool(pol.get("priority")), "quota_period": pol["period"],
             "quota_consumed": False, "created_at": _iso(_now())}
        try:
            await db.video_support_bookings.insert_one({**b})
        except DuplicateKeyError:
            raise HTTPException(status_code=409, detail="L'orario selezionato è appena stato prenotato")
        if not await plan["video_consume"](user["org_id"], pol["period"], pol.get("quota")):
            await db.video_support_bookings.update_one({"id": b["id"]}, {"$set": {"status": "errore", "error": "quota"}, "$unset": {"slot_lock": ""}})
            raise HTTPException(status_code=403, detail={"code": "video_quota", "message": "Hai già utilizzato tutte le videochiamate incluse nel periodo."})
        try:
            ev = await _create_meet(cfg, b)
        except Exception as e:
            logger.error(f"video_support meet creation failed booking={b['id']}: {type(e).__name__}: {e}")
            await plan["video_release"](user["org_id"], pol["period"])
            await db.video_support_bookings.update_one({"id": b["id"]}, {"$set": {"status": "errore", "error": "appuntamento"}, "$unset": {"slot_lock": ""}})
            raise HTTPException(status_code=502, detail="Non è stato possibile creare l'appuntamento Google Meet. Nessuna videochiamata è stata conteggiata: riprova più tardi.")
        upd = {"status": "confermata", "meet_link": ev["meet_link"], "google_event_id": ev["id"], "simulated": ev["simulated"], "quota_consumed": True}
        await db.video_support_bookings.update_one({"id": b["id"]}, {"$set": upd})
        b.update(upd)
        await _email(b, f"La tua assistenza CRMEvent in videochiamata è confermata per il {_fmt(body.slot_key)} (durata 30 minuti). "
                        "Al momento dell'appuntamento apri il link Google Meet: potrai condividere lo schermo.", "Assistenza CRMEvent confermata")
        await _audit(user, "video_support_booked", b, f"{_fmt(body.slot_key)} · incluso nel piano {pol.get('plan_label') or ''}")
        return _public(b)

    @r.post("/video-support/bookings/{bid}/cancel")
    async def cancel(bid: str, body: CancelIn, user: dict = Depends(require_admin)):
        return await _cancel(await _own(bid, user), user, False, body.reason)

    @r.post("/video-support/bookings/{bid}/reschedule")
    async def reschedule(bid: str, body: SlotIn, user: dict = Depends(require_admin)):
        b = await _own(bid, user)
        if b.get("reschedule_count"):
            raise HTTPException(status_code=400, detail="La prenotazione è già stata riprogrammata una volta")
        if _hours_left(b) < POLICY_HOURS:
            raise HTTPException(status_code=400, detail="La riprogrammazione è possibile fino a 24 ore prima dell'appuntamento")
        return await _reschedule(b, body.slot_key, user, False)

    # ---------------- Super Admin ----------------
    @r.get("/platform/video-support/config")
    async def get_config(admin: dict = Depends(require_superadmin)):
        cfg = await _config()
        conn = await _calendar(cfg)
        return {**cfg, "calendar_connected": bool(conn), "calendar_email": (conn or {}).get("google_email"),
                "gcal_configured": gcal_utils.is_configured(), "simulation": simulation()}

    @r.put("/platform/video-support/config")
    async def put_config(body: ConfigIn, admin: dict = Depends(require_superadmin)):
        for w in body.weekly:
            if not (0 <= w.weekday <= 6) or w.start >= w.end:
                raise HTTPException(status_code=400, detail="Fascia oraria non valida")
            for t in (w.start, w.end):
                datetime.strptime(t, "%H:%M")
        doc = {"id": "config", "weekly": [w.model_dump() for w in body.weekly], "closed_dates": sorted(set(body.closed_dates)),
               "min_notice_hours": max(0, body.min_notice_hours), "horizon_days": min(max(1, body.horizon_days), 120),
               "calendar_user_id": admin["user_id"], "updated_at": _iso(_now())}
        await db.video_support_config.update_one({"id": "config"}, {"$set": doc}, upsert=True)
        await record_audit(admin, "video_support_config", meta={"windows": len(doc["weekly"]), "closed": len(doc["closed_dates"])})
        return await get_config(admin)

    @r.get("/platform/video-support/bookings")
    async def all_bookings(admin: dict = Depends(require_superadmin)):
        rows = await db.video_support_bookings.find({"status": {"$in": ["confermata", "annullata", "errore"]}}, {"_id": 0}).sort("slot_key", -1).to_list(2000)
        return {"bookings": [{**_public(b), "admin_note": b.get("admin_note"), "error": b.get("error")} for b in rows]}

    @r.get("/platform/video-support/slots")
    async def admin_slots(admin: dict = Depends(require_superadmin)):
        return {"slots": await _slots(await _config(), enforce_notice=False)}

    @r.post("/platform/video-support/bookings/{bid}/cancel")
    async def admin_cancel(bid: str, body: CancelIn, admin: dict = Depends(require_superadmin)):
        b = await db.video_support_bookings.find_one({"id": bid}, {"_id": 0})
        if not b:
            raise HTTPException(status_code=404, detail="Prenotazione non trovata")
        out = await _cancel(b, admin, True, body.reason)
        await _email({**b, "meet_link": f"{os.environ.get('APP_URL', '')}/assistenza"},
                     f"La tua assistenza CRMEvent del {_fmt(b['slot_key'])} è stata annullata da CRMEvent. "
                     + ("La videochiamata non viene conteggiata nel tuo piano." if b.get("charge_mode") == "plan" else f"I {out['refunded']} crediti sono stati riaccreditati."),
                     "Assistenza CRMEvent annullata")
        return out

    @r.post("/platform/video-support/bookings/{bid}/reschedule")
    async def admin_reschedule(bid: str, body: SlotIn, admin: dict = Depends(require_superadmin)):
        b = await db.video_support_bookings.find_one({"id": bid}, {"_id": 0})
        if not b:
            raise HTTPException(status_code=404, detail="Prenotazione non trovata")
        return await _reschedule(b, body.slot_key, admin, True)

    @r.post("/platform/video-support/bookings/{bid}/restore-quota")
    async def admin_restore_quota(bid: str, admin: dict = Depends(require_superadmin)):
        """Rettifica Super Admin: restituisce la videochiamata (annullo tardivo / mancata partecipazione)."""
        b = await db.video_support_bookings.find_one({"id": bid}, {"_id": 0})
        if not b or b.get("charge_mode") != "plan" or not b.get("quota_consumed"):
            raise HTTPException(status_code=400, detail="Rettifica non applicabile")
        if not await _quota_back(b):
            raise HTTPException(status_code=400, detail="Videochiamata già restituita")
        await _audit(admin, "video_support_quota_restored", b)
        return {"ok": True}

    @r.put("/platform/video-support/bookings/{bid}/note")
    async def admin_note(bid: str, body: NoteIn, admin: dict = Depends(require_superadmin)):
        res = await db.video_support_bookings.update_one({"id": bid}, {"$set": {"admin_note": body.admin_note.strip()[:2000]}})
        if not res.matched_count:
            raise HTTPException(status_code=404, detail="Prenotazione non trovata")
        return {"ok": True}

    return r
