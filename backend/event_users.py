"""Ruolo UTENTE: accesso tramite link personale alla sola visualizzazione degli eventi assegnati (nessun back-end).
Account tecnico separato (users.role = "event_user"), senza membership: le API gestionali restano bloccate."""
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, EmailStr

ROLE = "event_user"
INFO = {"orari": "Date e orari", "luogo": "Luogo e indirizzo", "descrizione": "Descrizione evento", "contatti": "Contatti organizzazione"}
LINK_DAYS, CODE_MIN, SESSION_DAYS = 30, 10, 7


def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _mask(email: str) -> str:
    n, _, d = email.partition("@")
    return f"{n[:2]}{'•' * max(1, len(n) - 2)}@{d}"


class AssignIn(BaseModel):
    nome: str
    cognome: str
    email: EmailStr
    event_id: str
    incarico: Optional[str] = None
    note: Optional[str] = None
    info: List[str] = []


class AssignEditIn(BaseModel):
    incarico: Optional[str] = None
    note: Optional[str] = None
    info: Optional[List[str]] = None


class CodeIn(BaseModel):
    code: str


def build(db, deps: dict):
    r = APIRouter(prefix="/api")
    require_admin, get_user, audit, now_iso, new_id = deps["require_admin"], deps["get_current_user"], deps["record_audit"], deps["now_iso"], deps["new_id"]
    email_utils = deps["email_utils"]

    def _now():
        return datetime.now(timezone.utc)

    async def _send_link(u: dict, org_name: str, actor: dict) -> bool:
        token = secrets.token_urlsafe(32)
        await db.event_user_links.update_many({"user_id": u["user_id"], "status": "active"}, {"$set": {"status": "replaced"}})
        await db.event_user_links.insert_one({"id": new_id(), "user_id": u["user_id"], "token_hash": _h(token), "status": "active",
                                              "expires_at": (_now() + timedelta(days=LINK_DAYS)).isoformat(), "created_at": now_iso(), "by": actor.get("email")})
        await db.users.update_one({"user_id": u["user_id"]}, {"$set": {"link_sent_at": now_iso()}})
        try:
            await email_utils.send_email(to=u["email"], subject=f"I tuoi eventi con {org_name} su CRMEvent", html=email_utils.link_email(
                name=(u.get("name") or "").split(" ")[0], cta_label="Apri i miei eventi", url=f"{deps['app_url']}/accesso-evento/{token}",
                intro=f"«{org_name}» ti ha assegnato a uno o più eventi. Apri il link per vedere l'evento e il tuo incarico: per sicurezza ti invieremo un codice di verifica a questo indirizzo.",
                footer_note=f"Il link è personale, non inoltrarlo. Scade tra {LINK_DAYS} giorni."))
            return True
        except Exception:
            return False

    async def _event(org_id: str, eid: str) -> dict:
        ev = await db.events.find_one({"org_id": org_id, "id": eid}, {"_id": 0, "id": 1, "nome": 1})
        if not ev:
            raise HTTPException(status_code=404, detail="Evento non trovato")
        return ev

    def _info(v):
        return [k for k in INFO if k in (v or [])]

    # ---------------- Gestione (Organizzatore / Amministratore) ----------------
    @r.get("/event-users")
    async def list_assign(event_id: str, user: dict = Depends(require_admin)):
        await _event(user["org_id"], event_id)
        rows = await db.event_user_assignments.find({"org_id": user["org_id"], "event_id": event_id}, {"_id": 0}).to_list(2000)
        us = {u["user_id"]: u for u in await db.users.find({"user_id": {"$in": [x["user_id"] for x in rows]}}, {"_id": 0, "password_hash": 0}).to_list(2000)}
        out = [{**a, "name": (us.get(a["user_id"]) or {}).get("name"), "email": (us.get(a["user_id"]) or {}).get("email"),
                "account_active": (us.get(a["user_id"]) or {}).get("active", True), "last_login_at": (us.get(a["user_id"]) or {}).get("last_login_at"),
                "link_sent_at": (us.get(a["user_id"]) or {}).get("link_sent_at")} for a in rows]
        out.sort(key=lambda x: (x["status"] != "active", (x["name"] or "").lower()))
        return {"rows": out, "info": INFO}

    @r.post("/event-users")
    async def assign(body: AssignIn, user: dict = Depends(require_admin)):
        org_id = user["org_id"]
        ev = await _event(org_id, body.event_id)
        email = body.email.lower()
        u = await db.users.find_one({"email": email}, {"_id": 0, "password_hash": 0})
        if u and u.get("role") != ROLE:
            raise HTTPException(status_code=409, detail="Questa email appartiene già a un account con credenziali (gestionale o Staff/Volontari): per l'accesso tramite link usa un altro indirizzo")
        if u and u.get("org_id") != org_id:
            raise HTTPException(status_code=409, detail="Questa email è già un Utente di un'altra organizzazione")
        if not u:
            u = {"user_id": f"user_{secrets.token_hex(6)}", "email": email, "name": f"{body.nome.strip()} {body.cognome.strip()}".strip(),
                 "role": ROLE, "org_id": org_id, "active": True, "auth_provider": "link", "created_at": now_iso(), "created_by": user.get("email")}
            await db.users.insert_one({**u})
        cur = await db.event_user_assignments.find_one({"user_id": u["user_id"], "event_id": body.event_id}, {"_id": 0})
        doc = {"incarico": (body.incarico or "").strip() or None, "note": (body.note or "").strip() or None, "info": _info(body.info),
               "status": "active", "updated_at": now_iso(), "assigned_by": user.get("email")}
        if cur:
            await db.event_user_assignments.update_one({"id": cur["id"]}, {"$set": doc, "$unset": {"revoked_at": "", "revoked_by": ""}})
        else:
            await db.event_user_assignments.insert_one({"id": new_id(), "org_id": org_id, "user_id": u["user_id"], "event_id": body.event_id, "created_at": now_iso(), **doc})
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "nome": 1}) or {}
        sent = await _send_link(u, org.get("nome") or "CRMEvent", user)
        await audit(user, "event_user_assigned", org_id=org_id, target_email=email, target_name=u.get("name"),
                    detail=f"Utente assegnato all'evento «{ev['nome']}»" + (f" · incarico: {doc['incarico']}" if doc["incarico"] else "") + f" · info: {', '.join(INFO[k] for k in doc['info']) or 'solo evento e incarico'}",
                    meta={"event_id": body.event_id, "before": cur, "after": doc})
        return {"ok": True, "email_sent": sent, "user_id": u["user_id"]}

    async def _assignment(org_id: str, aid: str) -> dict:
        a = await db.event_user_assignments.find_one({"org_id": org_id, "id": aid}, {"_id": 0})
        if not a:
            raise HTTPException(status_code=404, detail="Assegnazione non trovata")
        return a

    @r.put("/event-users/assignments/{aid}")
    async def edit(aid: str, body: AssignEditIn, user: dict = Depends(require_admin)):
        a = await _assignment(user["org_id"], aid)
        upd = {k: v for k, v in {"incarico": body.incarico, "note": body.note}.items() if v is not None}
        if body.info is not None:
            upd["info"] = _info(body.info)
        await db.event_user_assignments.update_one({"id": aid}, {"$set": {**upd, "updated_at": now_iso()}})
        tu = await db.users.find_one({"user_id": a["user_id"]}, {"_id": 0, "email": 1, "name": 1}) or {}
        await audit(user, "event_user_changed", org_id=user["org_id"], target_email=tu.get("email"), target_name=tu.get("name"),
                    detail="Incarico o informazioni visibili modificati", meta={"event_id": a["event_id"], "before": {k: a.get(k) for k in upd}, "after": upd})
        return {"ok": True}

    @r.post("/event-users/assignments/{aid}/revoke")
    async def revoke(aid: str, user: dict = Depends(require_admin)):
        a = await _assignment(user["org_id"], aid)
        await db.event_user_assignments.update_one({"id": aid}, {"$set": {"status": "revoked", "revoked_at": now_iso(), "revoked_by": user.get("email")}})
        tu = await db.users.find_one({"user_id": a["user_id"]}, {"_id": 0, "email": 1, "name": 1}) or {}
        ev = await db.events.find_one({"id": a["event_id"]}, {"_id": 0, "nome": 1}) or {}
        await audit(user, "event_user_revoked", org_id=user["org_id"], target_email=tu.get("email"), target_name=tu.get("name"),
                    detail=f"Accesso all'evento «{ev.get('nome')}» revocato", meta={"event_id": a["event_id"]})
        return {"ok": True}

    @r.post("/event-users/assignments/{aid}/send-link")
    async def resend(aid: str, user: dict = Depends(require_admin)):
        a = await _assignment(user["org_id"], aid)
        u = await db.users.find_one({"user_id": a["user_id"], "role": ROLE}, {"_id": 0, "password_hash": 0})
        if not u:
            raise HTTPException(status_code=404, detail="Utente non trovato")
        org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0, "nome": 1}) or {}
        sent = await _send_link(u, org.get("nome") or "CRMEvent", user)
        await audit(user, "event_user_link_sent", org_id=user["org_id"], target_email=u["email"], target_name=u.get("name"), detail="Link di accesso agli eventi reinviato")
        return {"ok": True, "email_sent": sent}

    # ---------------- Accesso tramite link (pubblico) + codice di verifica ----------------
    async def _link(token: str) -> tuple:
        lk = await db.event_user_links.find_one({"token_hash": _h(token), "status": "active"}, {"_id": 0})
        if not lk or datetime.fromisoformat(lk["expires_at"]) < _now():
            raise HTTPException(status_code=410, detail="Link non valido o scaduto: chiedi all'organizzatore di inviartene uno nuovo")
        u = await db.users.find_one({"user_id": lk["user_id"], "role": ROLE}, {"_id": 0, "password_hash": 0})
        if not u or u.get("active") is False:
            raise HTTPException(status_code=403, detail="Accesso disattivato: contatta l'organizzatore")
        return lk, u

    @r.get("/public/event-access/{token}")
    async def link_info(token: str):
        _, u = await _link(token)
        org = await db.organizations.find_one({"id": u.get("org_id")}, {"_id": 0, "nome": 1}) or {}
        return {"email": _mask(u["email"]), "name": u.get("name"), "org_name": org.get("nome")}

    @r.post("/public/event-access/{token}/code")
    async def send_code(token: str):
        lk, u = await _link(token)
        since = (_now() - timedelta(hours=1)).isoformat()
        if await db.event_user_codes.count_documents({"link_id": lk["id"], "created_at": {"$gte": since}}) >= 5:
            raise HTTPException(status_code=429, detail="Troppi codici richiesti: riprova tra un'ora")
        code = f"{secrets.randbelow(1000000):06d}"
        await db.event_user_codes.insert_one({"id": new_id(), "link_id": lk["id"], "user_id": u["user_id"], "code_hash": _h(code), "attempts": 0,
                                              "used": False, "expires_at": (_now() + timedelta(minutes=CODE_MIN)).isoformat(), "created_at": now_iso()})
        try:
            await email_utils.send_email(to=u["email"], subject="Il tuo codice di accesso CRMEvent", html=email_utils.link_email(
                name=(u.get("name") or "").split(" ")[0], intro=f"Il tuo codice di verifica è {code}. Inseriscilo nella pagina che hai aperto dal link personale. Vale {CODE_MIN} minuti.",
                cta_label="Torna alla pagina", url=f"{deps['app_url']}/accesso-evento/{token}", footer_note="Se non hai richiesto tu il codice, ignora questa email."))
        except Exception:
            raise HTTPException(status_code=502, detail="Impossibile inviare il codice in questo momento")
        return {"ok": True, "email": _mask(u["email"])}

    @r.post("/public/event-access/{token}/verify")
    async def verify(token: str, body: CodeIn, response: Response):
        lk, u = await _link(token)
        c = await db.event_user_codes.find_one({"link_id": lk["id"], "used": False}, {"_id": 0}, sort=[("created_at", -1)])
        if not c or datetime.fromisoformat(c["expires_at"]) < _now() or c["attempts"] >= 5:
            raise HTTPException(status_code=400, detail="Codice scaduto: richiedine uno nuovo")
        if not secrets.compare_digest(c["code_hash"], _h(body.code.strip())):
            await db.event_user_codes.update_one({"id": c["id"]}, {"$inc": {"attempts": 1}})
            raise HTTPException(status_code=400, detail="Codice non corretto")
        await db.event_user_codes.update_one({"id": c["id"]}, {"$set": {"used": True}})
        st = secrets.token_urlsafe(32)
        await db.user_sessions.insert_one({"user_id": u["user_id"], "session_token": st, "kind": "event_link",
                                           "expires_at": (_now() + timedelta(days=SESSION_DAYS)).isoformat(), "created_at": now_iso()})
        deps["set_auth_cookie"](response, "session_token", st, SESSION_DAYS * 24 * 3600)
        await db.users.update_one({"user_id": u["user_id"]}, {"$set": {"last_login_at": now_iso()}})
        return {"ok": True}

    # ---------------- Area Utente: solo eventi assegnati, solo informazioni autorizzate ----------------
    @r.get("/my-event-access")
    async def my_events(user: dict = Depends(get_user)):
        if user.get("role") != ROLE:
            raise HTTPException(status_code=403, detail="Area riservata agli Utenti invitati tramite link")
        rows = await db.event_user_assignments.find({"user_id": user["user_id"], "org_id": user.get("org_id"), "status": "active"}, {"_id": 0}).to_list(200)
        evs = {e["id"]: e for e in await db.events.find({"org_id": user.get("org_id"), "id": {"$in": [a["event_id"] for a in rows]}}, {"_id": 0}).to_list(200)}
        org = await db.organizations.find_one({"id": user.get("org_id")}, {"_id": 0, "nome": 1}) or {}
        out = []
        for a in rows:
            e = evs.get(a["event_id"])
            if not e:
                continue
            info = set(a.get("info") or [])
            ev = {"nome": e.get("nome"), "edizione": e.get("edizione"), "logo_url": e.get("logo_url")}
            if "orari" in info:
                ev.update({k: e.get(k) for k in ("data_inizio", "data_fine", "ora_inizio", "ora_fine")})
            if "luogo" in info:
                ev.update({k: e.get(k) for k in ("localita", "indirizzo", "citta", "provincia")})
            if "descrizione" in info:
                ev["descrizione"] = e.get("descrizione")
            if "contatti" in info:
                ev.update({"responsabile": e.get("responsabile"), "email": e.get("email"), "telefono": e.get("telefono"), "sito_web": e.get("sito_web")})
            out.append({"assignment_id": a["id"], "event": ev, "incarico": a.get("incarico"), "note": a.get("note"), "info": [k for k in INFO if k in info]})
        out.sort(key=lambda x: x["event"].get("data_inizio") or "9999")
        return {"org_name": org.get("nome"), "events": out, "info_labels": INFO}

    return {"router": r}
