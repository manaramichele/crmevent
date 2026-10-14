"""Segnalazioni e richieste: ticket interni org ↔ Super Admin. Nessuna email: solo aggiornamenti in piattaforma."""
import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from pymongo import ReturnDocument

import storage_utils

logger = logging.getLogger("tickets")

CATEGORIES = {
    "problema_tecnico": "Problema tecnico",
    "nuova_funzionalita": "Richiesta nuova funzionalità",
    "miglioramento": "Miglioramento piattaforma",
    "domanda_utilizzo": "Domanda sull'utilizzo",
    "abbonamento": "Abbonamento e fatturazione",
    "altro": "Altro",
}
STATUSES = {"aperta": "Aperta", "in_lavorazione": "In lavorazione", "in_attesa": "In attesa di risposta", "chiusa": "Chiusa"}
OPEN_STATUSES = ("aperta", "in_lavorazione", "in_attesa")
MAX_FILES = 5
MAX_BYTES = 10 * 1024 * 1024
ALLOWED = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp", "pdf": "application/pdf"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


ROME = ZoneInfo("Europe/Rome")


def _day_bound(day: str, end: bool) -> str:
    try:
        d = datetime.strptime(day, "%Y-%m-%d").replace(hour=23 if end else 0, minute=59 if end else 0,
                                                        second=59 if end else 0, microsecond=999999 if end else 0, tzinfo=ROME)
    except ValueError:
        raise HTTPException(status_code=400, detail="Data non valida")
    return d.astimezone(timezone.utc).isoformat()


def _magic_ok(ext: str, data: bytes) -> bool:
    if ext in ("jpg", "jpeg"):
        return data[:3] == b"\xff\xd8\xff"
    if ext == "png":
        return data[:8] == b"\x89PNG\r\n\x1a\n"
    if ext == "webp":
        return data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return data[:5] == b"%PDF-"


def _person(u: dict) -> dict:
    return {"user_id": u.get("user_id"), "name": u.get("name") or u.get("email"), "email": u.get("email")}


class StatusIn(BaseModel):
    status: str
    message: Optional[str] = None


def build_router(db, require_org_member, require_superadmin, record_audit):
    r = APIRouter(prefix="/api")

    async def _next_number() -> int:
        c = await db.counters.find_one_and_update({"id": "tickets"}, {"$inc": {"seq": 1}}, upsert=True,
                                                  return_document=ReturnDocument.AFTER)
        return 1000 + c["seq"]

    async def _store_files(files: List[UploadFile], ticket: dict, internal: bool) -> list:
        files = [f for f in (files or []) if f and f.filename]
        if len(files) > MAX_FILES:
            raise HTTPException(status_code=400, detail=f"Massimo {MAX_FILES} allegati per messaggio")
        prepared = []
        for f in files:
            data = await f.read()
            ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
            if ext not in ALLOWED or not _magic_ok(ext, data):
                raise HTTPException(status_code=400, detail=f"«{f.filename}»: formato non consentito (JPG, PNG, WEBP o PDF)")
            if len(data) > MAX_BYTES:
                raise HTTPException(status_code=400, detail=f"«{f.filename}»: dimensione massima 10 MB")
            prepared.append((f.filename[:200], ext, data))
        out = []
        for name, ext, data in prepared:
            fid = uuid.uuid4().hex
            res = await asyncio.to_thread(storage_utils.save, f"tickets/{ticket['org_id']}/{ticket['id']}/{fid}.{ext}", data, ALLOWED[ext])
            doc = {"id": fid, "ticket_id": ticket["id"], "org_id": ticket["org_id"], "internal": internal,
                   "storage_path": res["path"], "storage_backend": res.get("backend"), "filename": name,
                   "content_type": ALLOWED[ext], "size": len(data), "created_at": _now()}
            await db.ticket_files.insert_one(doc)
            out.append({k: doc[k] for k in ("id", "filename", "content_type", "size")})
        return out

    async def _add_msg(ticket: dict, author: dict, side: str, text: str = "", attachments=None, internal=False, kind="message", meta=None):
        m = {"id": uuid.uuid4().hex, "ticket_id": ticket["id"], "org_id": ticket["org_id"], "author": author, "side": side,
             "text": (text or "").strip()[:10000], "attachments": attachments or [], "internal": internal, "kind": kind,
             "meta": meta or {}, "created_at": _now()}
        await db.ticket_messages.insert_one(m)
        m.pop("_id", None)
        return m

    def _pub(t: dict) -> dict:
        return {k: v for k, v in t.items() if k != "_id"}

    async def _org_ticket(tid: str, user: dict) -> dict:
        t = await db.tickets.find_one({"id": tid, "org_id": user["org_id"]}, {"_id": 0})
        if not t:
            raise HTTPException(status_code=404, detail="Richiesta non trovata")
        return t

    async def _send_file(rec: Optional[dict]):
        if not rec:
            raise HTTPException(status_code=404, detail="Allegato non trovato")
        try:
            data, _ = await asyncio.to_thread(storage_utils.read, rec["storage_path"], rec.get("storage_backend"), rec["content_type"])
        except Exception:  # noqa: BLE001
            raise HTTPException(status_code=404, detail="Allegato non disponibile")
        safe = re.sub(r"[^\w.\- ]", "_", rec["filename"])
        return Response(content=data, media_type=rec["content_type"], headers={
            "Content-Disposition": f'inline; filename="{safe}"', "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store", "Content-Security-Policy": "sandbox"})

    # ---------------- Organizzazione ----------------
    @r.get("/tickets/meta")
    async def meta(user: dict = Depends(require_org_member)):
        return {"categories": CATEGORIES, "statuses": STATUSES, "max_files": MAX_FILES, "max_mb": MAX_BYTES // (1024 * 1024)}

    @r.get("/tickets")
    async def org_list(user: dict = Depends(require_org_member)):
        rows = await db.tickets.find({"org_id": user["org_id"]}, {"_id": 0, "description": 0}).sort("number", -1).to_list(1000)
        for t in rows:
            t["unread"] = bool(t.pop("creator_unread", False)) and (t.get("created_by") or {}).get("user_id") == user["user_id"]
        rows.sort(key=lambda t: not t["unread"])
        return rows

    def _unread_q(user: dict) -> dict:
        return {"org_id": user["org_id"], "created_by.user_id": user["user_id"], "creator_unread": True}

    @r.get("/tickets/unread-count")
    async def org_unread_count(user: dict = Depends(require_org_member)):
        return {"unread": await db.tickets.count_documents(_unread_q(user))}

    @r.post("/tickets")
    async def org_create(category: str = Form(""), subject: str = Form(""), description: str = Form(""),
                         files: List[UploadFile] = File(default=[]), user: dict = Depends(require_org_member)):
        subject, description = subject.strip(), description.strip()
        if category not in CATEGORIES:
            raise HTTPException(status_code=400, detail="Categoria non valida")
        if not subject or len(subject) > 200:
            raise HTTPException(status_code=400, detail="Inserisci un oggetto (max 200 caratteri)")
        if not description:
            raise HTTPException(status_code=400, detail="Inserisci una descrizione")
        org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0, "nome": 1}) or {}
        now = _now()
        t = {"id": uuid.uuid4().hex, "org_id": user["org_id"], "org_name": org.get("nome"), "created_by": _person(user),
             "category": category, "subject": subject, "description": description[:10000], "attachments": [],
             "status": "aperta", "reopen_requested": False, "created_at": now, "updated_at": now,
             "closed_at": None, "closed_by": None}
        t["attachments"] = await _store_files(files, t, False)
        t["number"] = await _next_number()
        await db.tickets.insert_one(t)
        await _add_msg(t, _person(user), "org", kind="status", meta={"from": None, "to": "aperta"})
        return _pub(t)

    @r.get("/tickets/{tid}")
    async def org_get(tid: str, user: dict = Depends(require_org_member)):
        t = await _org_ticket(tid, user)
        msgs = await db.ticket_messages.find({"ticket_id": tid, "org_id": user["org_id"], "internal": False}, {"_id": 0}).sort("created_at", 1).to_list(2000)
        mine = (t.get("created_by") or {}).get("user_id") == user["user_id"]
        t["unread"] = bool(t.pop("creator_unread", False)) and mine
        t["is_creator"] = mine
        return {**t, "messages": msgs}

    @r.post("/tickets/{tid}/read")
    async def org_mark_read(tid: str, user: dict = Depends(require_org_member)):
        """Lettura effettiva: solo il richiedente (mai il Super Admin o altri membri)."""
        res = await db.tickets.update_one({"id": tid, **_unread_q(user)}, {"$set": {"creator_unread": False, "creator_read_at": _now()}})
        return {"marked": bool(res.modified_count)}

    @r.post("/tickets/{tid}/messages")
    async def org_reply(tid: str, text: str = Form(""), files: List[UploadFile] = File(default=[]), user: dict = Depends(require_org_member)):
        t = await _org_ticket(tid, user)
        if t["status"] == "chiusa":
            raise HTTPException(status_code=400, detail="La richiesta è chiusa: chiedi la riapertura per aggiungere informazioni")
        if not text.strip() and not [f for f in files if f and f.filename]:
            raise HTTPException(status_code=400, detail="Scrivi un messaggio o allega un file")
        m = await _add_msg(t, _person(user), "org", text, await _store_files(files, t, False))
        await db.tickets.update_one({"id": tid}, {"$set": {"updated_at": m["created_at"], "last_side": "org"}})
        return m

    @r.post("/tickets/{tid}/reopen-request")
    async def org_reopen_request(tid: str, text: str = Form(""), user: dict = Depends(require_org_member)):
        t = await _org_ticket(tid, user)
        if t["status"] != "chiusa":
            raise HTTPException(status_code=400, detail="La richiesta non è chiusa")
        if t.get("reopen_requested"):
            raise HTTPException(status_code=400, detail="Riapertura già richiesta")
        m = await _add_msg(t, _person(user), "org", text, kind="reopen_request")
        await db.tickets.update_one({"id": tid}, {"$set": {"reopen_requested": True, "reopen_requested_at": m["created_at"],
                                                           "updated_at": m["created_at"], "last_side": "org"}})
        return {"ok": True}

    @r.get("/tickets/files/{fid}")
    async def org_file(fid: str, user: dict = Depends(require_org_member)):
        return await _send_file(await db.ticket_files.find_one({"id": fid, "org_id": user["org_id"], "internal": False}, {"_id": 0}))

    # ---------------- Super Admin ----------------
    def _pending_q():
        return {"$or": [{"status": {"$in": list(OPEN_STATUSES)}}, {"reopen_requested": True}]}

    @r.get("/platform/tickets/count")
    async def sa_count(admin: dict = Depends(require_superadmin)):
        return {"pending": await db.tickets.count_documents(_pending_q())}

    @r.get("/platform/tickets")
    async def sa_list(q: Optional[str] = None, org_id: Optional[str] = None, category: Optional[str] = None,
                      status: Optional[str] = None, date_from: Optional[str] = Query(None, alias="from"),
                      date_to: Optional[str] = Query(None, alias="to"), admin: dict = Depends(require_superadmin)):
        f: dict = {}
        if org_id:
            f["org_id"] = org_id
        if category in CATEGORIES:
            f["category"] = category
        if status == "riapertura":
            f["reopen_requested"] = True
        elif status in STATUSES:
            f["status"] = status
        if date_from or date_to:
            f["created_at"] = {**({"$gte": _day_bound(date_from, False)} if date_from else {}), **({"$lte": _day_bound(date_to, True)} if date_to else {})}
        if q and q.strip():
            rx = {"$regex": re.escape(q.strip()), "$options": "i"}
            ors = [{"subject": rx}, {"org_name": rx}, {"created_by.name": rx}, {"created_by.email": rx}]
            if q.strip().lstrip("#").isdigit():
                ors.append({"number": int(q.strip().lstrip("#"))})
            f["$or"] = ors
        rows = await db.tickets.find(f, {"_id": 0, "description": 0}).sort("number", -1).to_list(2000)
        counts = {s: 0 for s in STATUSES}
        for c in await db.tickets.aggregate([{"$group": {"_id": "$status", "n": {"$sum": 1}}}]).to_list(10):
            if c["_id"] in counts:
                counts[c["_id"]] = c["n"]
        orgs = await db.tickets.aggregate([{"$group": {"_id": "$org_id", "name": {"$first": "$org_name"}}}, {"$sort": {"name": 1}}]).to_list(1000)
        return {"tickets": rows, "counts": counts, "reopen_requests": await db.tickets.count_documents({"reopen_requested": True}),
                "orgs": [{"id": o["_id"], "name": o.get("name")} for o in orgs], "categories": CATEGORIES, "statuses": STATUSES}

    async def _sa_ticket(tid: str) -> dict:
        t = await db.tickets.find_one({"id": tid}, {"_id": 0})
        if not t:
            raise HTTPException(status_code=404, detail="Richiesta non trovata")
        return t

    @r.get("/platform/tickets/{tid}")
    async def sa_get(tid: str, admin: dict = Depends(require_superadmin)):
        t = await _sa_ticket(tid)
        msgs = await db.ticket_messages.find({"ticket_id": tid}, {"_id": 0}).sort("created_at", 1).to_list(5000)
        return {**t, "messages": msgs}

    @r.post("/platform/tickets/{tid}/messages")
    async def sa_reply(tid: str, text: str = Form(""), internal: bool = Form(False), files: List[UploadFile] = File(default=[]),
                       admin: dict = Depends(require_superadmin)):
        t = await _sa_ticket(tid)
        if not text.strip() and not [f for f in files if f and f.filename]:
            raise HTTPException(status_code=400, detail="Scrivi un messaggio o allega un file")
        m = await _add_msg(t, _person(admin), "admin", text, await _store_files(files, t, internal), internal=internal)
        if not internal:
            await db.tickets.update_one({"id": tid}, {"$set": {"updated_at": m["created_at"], "last_side": "admin",
                                                               "creator_unread": True, "creator_unread_since": m["created_at"]}})
        return m

    @r.post("/platform/tickets/{tid}/status")
    async def sa_status(tid: str, body: StatusIn, admin: dict = Depends(require_superadmin)):
        if body.status not in STATUSES:
            raise HTTPException(status_code=400, detail="Stato non valido")
        t = await _sa_ticket(tid)
        if t["status"] == body.status:
            raise HTTPException(status_code=400, detail="La richiesta è già in questo stato")
        now = _now()
        upd = {"status": body.status, "updated_at": now, "last_side": "admin", "creator_unread": True, "creator_unread_since": now}
        if body.status == "chiusa":
            upd.update({"closed_at": now, "closed_by": _person(admin), "reopen_requested": False})
        elif t["status"] == "chiusa":
            upd.update({"closed_at": None, "closed_by": None, "reopen_requested": False, "reopened_at": now})
        if body.message and body.message.strip():
            await _add_msg(t, _person(admin), "admin", body.message)
        await _add_msg(t, _person(admin), "admin", kind="status", meta={"from": t["status"], "to": body.status})
        await db.tickets.update_one({"id": tid}, {"$set": upd})
        await record_audit(admin, "ticket_status", org_id=t["org_id"], org_name=t.get("org_name"),
                           detail=f"#{t['number']} {STATUSES[t['status']]} → {STATUSES[body.status]}")
        return {**t, **upd}

    @r.get("/platform/tickets/files/{fid}")
    async def sa_file(fid: str, admin: dict = Depends(require_superadmin)):
        return await _send_file(await db.ticket_files.find_one({"id": fid}, {"_id": 0}))

    async def ensure_indexes():
        await db.tickets.create_index("id", unique=True)
        await db.tickets.create_index([("org_id", 1), ("number", -1)])
        await db.ticket_messages.create_index([("ticket_id", 1), ("created_at", 1)])
        await db.tickets.create_index([("org_id", 1), ("created_by.user_id", 1), ("creator_unread", 1)])
        await db.ticket_files.create_index("id", unique=True)

    return {"router": r, "ensure_indexes": ensure_indexes}
