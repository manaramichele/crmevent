"""Demo CRMEvent post-registrazione: disponibilità Super Admin → Demo, prenotazione 30 min con Google Meet (separata dall'Assistenza)."""
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import demo_booking
import email_utils
import text_normalize as TN
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


class RequestIn(BaseModel):
    slot_key: str
    nome: str
    telefono: Optional[str] = None
    organizzazione: Optional[str] = None
    note: Optional[str] = None


class StatusIn(BaseModel):
    status: str


class BookingActionIn(BaseModel):
    action: str
    slot_key: Optional[str] = None


class NoteIn(BaseModel):
    admin_note: str = ""


BOOKING_FIELDS = {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "organizzazione": 1, "email": 1, "telefono": 1, "demo_slot": 1, "demo_status": 1,
                  "demo_meet_link": 1, "demo_meet_status": 1, "demo_meet_error": 1, "demo_meet_simulated": 1, "demo_admin_note": 1,
                  "demo_source": 1, "demo_request_id": 1, "updated_at": 1}


REQ_STATUS = {"nuova", "da_confermare", "confermata", "completata", "annullata"}


def _now():
    return datetime.now(timezone.utc)


def _iso(d):
    return d.astimezone(timezone.utc).isoformat()


def build_router(db, require_member, require_superadmin, record_audit, app_url: str) -> APIRouter:
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

    async def slots(enforce_notice: bool = True, exclude_lead: Optional[str] = None) -> list:
        cfg, now = await _cfg(), _now()
        start_min, horizon = now + timedelta(hours=cfg.get("min_notice_hours", 12) if enforce_notice else 0), now + timedelta(days=cfg.get("horizon_days", 30))
        taken = set(await db.demo_slot_locks.distinct("slot", {"lead_id": {"$ne": exclude_lead}} if exclude_lead else {})) | set(await db.video_support_bookings.distinct("slot_lock", {"slot_lock": {"$type": "string"}}))
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
    async def welcome_info(user: dict = Depends(require_member)):
        u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "welcome_demo": 1})
        org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0, "nome": 1})
        full = user.get("name") or " ".join(x for x in (user.get("nome"), user.get("cognome")) if x)
        return {"state": (u or {}).get("welcome_demo"), "duration_min": DURATION_MIN,
                "prefill": {"nome": full or "", "email": user.get("email"), "telefono": user.get("telefono") or "",
                            "organizzazione": (org or {}).get("nome") or "", "note": ""}}

    @r.get("/demo/slots")
    async def get_slots(user: dict = Depends(require_member)):
        return {"slots": await slots()}

    @r.post("/demo/welcome/dismiss")
    async def dismiss(user: dict = Depends(require_member)):
        await db.users.update_one({"user_id": user["user_id"], "welcome_demo": "pending"},
                                  {"$set": {"welcome_demo": "dismissed", "welcome_demo_seen_at": _iso(_now())}})
        return {"ok": True}

    @r.post("/demo/requests")
    async def create_request(body: RequestIn, user: dict = Depends(require_member)):
        if not body.nome.strip():
            raise HTTPException(status_code=400, detail="Inserisci nome e cognome")
        body.nome = TN.person_name(body.nome)
        body.organizzazione = TN.business_name(body.organizzazione)
        if body.slot_key not in {s["slot_key"] for s in await slots()}:
            raise HTTPException(status_code=409, detail="L'orario selezionato non è più disponibile, scegline un altro")
        now, email = _iso(_now()), (user.get("email") or "").lower()
        nome, _, cognome = body.nome.strip().partition(" ")
        req = {"id": uuid.uuid4().hex, "user_id": user["user_id"], "org_id": user["org_id"], "nome": body.nome.strip(), "email": email,
               "telefono": (body.telefono or "").strip(), "organizzazione": (body.organizzazione or "").strip(),
               "preferred_slot": body.slot_key, "note": (body.note or "").strip()[:2000], "status": "nuova",
               "created_at": now, "updated_at": now}
        await db.demo_requests.insert_one(dict(req))
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"welcome_demo": "requested", "welcome_demo_seen_at": now}})
        prev = await db.leads.find_one({"email": email}, {"_id": 0})
        lead = {**(prev or {"id": uuid.uuid4().hex, "created_at": now, "source": "richiesta_demo_app", "stato": "nuovo", "note": "",
                            "funnel_status": "demo_requested", "requested_at": now}),
                "nome": nome, "cognome": cognome, "email": email, "telefono": req["telefono"], "organizzazione": req["organizzazione"],
                "user_id": user["user_id"], "org_id": user["org_id"], "demo_slot": body.slot_key, "demo_status": "da_confermare",
                "demo_source": "richiesta_demo_app", "demo_request_id": req["id"], "updated_at": now}
        await db.leads.update_one({"id": lead["id"]}, {"$set": lead}, upsert=True)
        try:
            await demo_booking.sync_lead(db, lead)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"demo request brevo sync failed: {type(e).__name__}")
        await demo_booking.send_operational(lead, "ricevuta", app_url)
        try:
            await email_utils.send_email(to=os.environ["ADMIN_EMAIL"], subject="Nuova richiesta demo CRMEvent", html=email_utils.link_email(
                name="Michele", intro=f"Nuova richiesta demo da {req['nome']} ({req['organizzazione'] or '-'}) — email {email}, tel {req['telefono'] or '-'}. "
                f"Preferenza: {demo_booking.fmt_slot(body.slot_key)}. Note: {req['note'] or '-'}.",
                cta_label="Apri Richieste demo", url=f"{app_url}/piattaforma/richieste-demo", footer_note="Gestisci la richiesta nell'area Super Admin."))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"demo request admin notify failed: {type(e).__name__}")
        await record_audit(user, "demo_request_created", org_id=user["org_id"], detail=demo_booking.fmt_slot(body.slot_key), meta={"request_id": req["id"]})
        return {"ok": True, "id": req["id"], "preferred_slot": body.slot_key}

    @r.get("/platform/demo/requests")
    async def list_requests(status: Optional[str] = None, admin: dict = Depends(require_superadmin)):
        q = {"status": status} if status in REQ_STATUS else {}
        items = await db.demo_requests.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
        leads = {x["demo_request_id"]: x for x in await db.leads.find({"demo_request_id": {"$in": [i["id"] for i in items]}}, BOOKING_FIELDS).to_list(1000)}
        return {"items": [{**i, "booking": leads.get(i["id"])} for i in items]}

    async def _lead_for_request(req: dict) -> dict:
        lead = await db.leads.find_one({"demo_request_id": req["id"]}, {"_id": 0}) or await db.leads.find_one({"email": req["email"]}, {"_id": 0})
        now = _iso(_now())
        nome, _, cognome = (req.get("nome") or "").partition(" ")
        base = {"user_id": req.get("user_id"), "org_id": req.get("org_id"), "demo_request_id": req["id"], "demo_source": "richiesta_demo_app",
                "telefono": (lead or {}).get("telefono") or req.get("telefono"), "organizzazione": (lead or {}).get("organizzazione") or req.get("organizzazione")}
        if not lead:
            lead = {"id": uuid.uuid4().hex, "created_at": now, "source": "richiesta_demo_app", "stato": "nuovo", "note": "", "funnel_status": "demo_requested",
                    "requested_at": req.get("created_at") or now, "nome": nome, "cognome": cognome, "email": req["email"],
                    "demo_slot": req.get("preferred_slot"), "demo_status": "da_confermare"}
        if not lead.get("demo_slot") or lead.get("demo_status") in (None, "annullata"):
            base.update({"demo_slot": req.get("preferred_slot"), "demo_status": "da_confermare"})
        lead = {**lead, **base, "updated_at": now}
        await db.leads.update_one({"id": lead["id"]}, {"$set": lead}, upsert=True)
        return lead

    async def _do(lead: dict, action: str, slot=None) -> dict:
        try:
            return (await demo_booking.apply_action(db, lead, action, app_url, slot))["lead"]
        except demo_booking.SlotTaken:
            raise HTTPException(status_code=409, detail="Orario già occupato da un'altra demo o assistenza: riprogramma la demo")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    async def _sync_request(req: dict, admin: dict):
        """Conferma/annullo della richiesta → crea/aggiorna l'unica prenotazione (Lead) collegata, idempotente."""
        if req["status"] not in ("confermata", "annullata"):
            return None
        lead = await _lead_for_request(req)
        if req["status"] == "annullata":
            return await _do(lead, "cancel") if lead.get("demo_status") in demo_booking.ACTIVE else lead
        if lead.get("demo_status") in ("confermata", "riprogrammata"):
            lead = await _do(lead, "meet") if lead.get("demo_meet_status") != "ok" else lead
        else:
            lead = await _do(lead, "confirm")
        await record_audit(admin, "demo_booking_from_request", target_email=lead.get("email"), detail=demo_booking.fmt_slot(lead.get("demo_slot")), meta={"request_id": req["id"]})
        return lead

    @r.patch("/platform/demo/requests/{rid}")
    async def set_status(rid: str, body: StatusIn, admin: dict = Depends(require_superadmin)):
        if body.status not in REQ_STATUS:
            raise HTTPException(status_code=400, detail="Stato non valido")
        res = await db.demo_requests.update_one({"id": rid}, {"$set": {"status": body.status, "updated_at": _iso(_now())}})
        if not res.matched_count:
            raise HTTPException(status_code=404, detail="Richiesta non trovata")
        await record_audit(admin, "demo_request_status", detail=body.status, meta={"request_id": rid})
        req = await db.demo_requests.find_one({"id": rid}, {"_id": 0})
        lead = await _sync_request(req, admin)
        return {**req, "booking": {k: lead.get(k) for k in BOOKING_FIELDS if k != "_id"} if lead else None}

    @r.post("/platform/demo/requests/{rid}/booking")
    async def sync_request_booking(rid: str, admin: dict = Depends(require_superadmin)):
        req = await db.demo_requests.find_one({"id": rid}, {"_id": 0})
        if not req:
            raise HTTPException(status_code=404, detail="Richiesta non trovata")
        if req["status"] != "confermata":
            raise HTTPException(status_code=400, detail="La richiesta non è confermata")
        lead = await _sync_request(req, admin)
        return {**req, "booking": {k: lead.get(k) for k in BOOKING_FIELDS if k != "_id"}}

    def _now_key() -> str:
        return _now().astimezone(ROME).strftime("%Y-%m-%dT%H:%M")

    @r.get("/platform/demo/bookings")
    async def list_bookings(status: Optional[str] = None, when: str = "future", admin: dict = Depends(require_superadmin)):
        q = {"demo_slot": {"$nin": [None, ""]}}
        if status in demo_booking.STATUS_LABEL:
            q["demo_status"] = status
        if when == "future":
            q["demo_slot"] = {"$gte": _now_key()}
        elif when == "past":
            q["demo_slot"] = {"$lt": _now_key(), "$nin": [None, ""]}
        rows = await db.leads.find(q, BOOKING_FIELDS).sort("demo_slot", -1 if when == "past" else 1).to_list(2000)
        return {"bookings": rows}

    @r.post("/platform/demo/bookings/{lead_id}/action")
    async def booking_action(lead_id: str, body: BookingActionIn, admin: dict = Depends(require_superadmin)):
        lead = await db.leads.find_one({"id": lead_id}, {"_id": 0})
        if not lead:
            raise HTTPException(status_code=404, detail="Prenotazione non trovata")
        if body.action == "reschedule" and body.slot_key not in {s["slot_key"] for s in await slots(enforce_notice=False, exclude_lead=lead_id)}:
            raise HTTPException(status_code=409, detail="L'orario selezionato non è più disponibile")
        lead = await _do(lead, body.action, body.slot_key if body.action == "reschedule" else None)
        await record_audit(admin, "demo_booking_" + body.action, target_email=lead.get("email"), detail=demo_booking.fmt_slot(lead.get("demo_slot")))
        return {k: lead.get(k) for k in BOOKING_FIELDS if k != "_id"}

    @r.put("/platform/demo/bookings/{lead_id}/note")
    async def booking_note(lead_id: str, body: NoteIn, admin: dict = Depends(require_superadmin)):
        res = await db.leads.update_one({"id": lead_id}, {"$set": {"demo_admin_note": body.admin_note.strip()[:2000]}})
        if not res.matched_count:
            raise HTTPException(status_code=404, detail="Prenotazione non trovata")
        return {"ok": True}

    @r.get("/platform/demo/slots")
    async def admin_demo_slots(exclude: Optional[str] = None, admin: dict = Depends(require_superadmin)):
        return {"slots": await slots(enforce_notice=False, exclude_lead=exclude)}

    @r.get("/platform/booking-counts")
    async def booking_counts(admin: dict = Depends(require_superadmin)):
        nk = _now_key()
        demo = await db.leads.count_documents({"demo_status": {"$in": list(demo_booking.ACTIVE)}, "demo_slot": {"$gte": nk}})
        assist = await db.video_support_bookings.count_documents({"status": "confermata", "slot_key": {"$gte": nk}})
        return {"demo": demo, "assistenza": assist}

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
