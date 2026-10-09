"""Dashboard: To Do List (attività esistenti: Pipeline, CRM, Follow-up) e Note personali dell'utente."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import permissions as P

DONE = {"pipeline": "completata", "attivita": "completata", "followup": "completato"}
COLL = {"pipeline": "pipeline_tasks", "attivita": "activities", "followup": "followups"}
EV_FIELD = {"pipeline": "event_id", "attivita": "evento_id", "followup": "evento_id"}
DATE_FIELD = {"pipeline": "scadenza", "attivita": "data", "followup": "scadenza"}


class CompleteIn(BaseModel):
    tipo: Literal["pipeline", "attivita", "followup"]
    id: str


class AssignIn(CompleteIn):
    responsabile_id: Optional[str] = None


class NoteIn(BaseModel):
    text: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_router(db, require_admin, get_current_user, saas: dict) -> APIRouter:
    r = APIRouter()

    async def _scope(user: dict) -> dict:
        """Tipi visibili (permessi + piano), filtro eventi e persona collegata per i non Admin."""
        perm = user.get("perm") or {"admin": True}
        st = await saas["state_for"](user["org_id"]) if saas.get("state_for") else {}
        feats = set(st.get("features") or []) if st.get("enabled") else None
        types = [t for t in COLL if P.allows(perm, (t,), "view") and (feats is None or t in feats)]
        persona = None
        if not perm.get("admin"):
            m = await db.memberships.find_one({"user_id": user["user_id"], "org_id": user["org_id"]}, {"_id": 0, "persona_id": 1})
            persona = (m or {}).get("persona_id")
        return {"perm": perm, "types": types, "ev_ids": perm.get("event_ids"), "persona": persona}

    def _query(sc: dict, tipo: str, org_id: str) -> dict:
        q = {"org_id": org_id, "stato": {"$ne": DONE[tipo]}}
        if sc["ev_ids"] is not None:
            q[EV_FIELD[tipo]] = {"$in": sc["ev_ids"] + ([None, ""] if tipo != "pipeline" else [])}
        if not sc["perm"].get("admin"):
            q["responsabile_id"] = {"$in": ([sc["persona"]] if sc["persona"] else []) + [None, ""]}
        return q

    @r.get("/my/todo")
    async def todo(user: dict = Depends(require_admin)):
        sc = await _scope(user)
        today = datetime.now(timezone.utc).date()
        soon = (today + timedelta(days=7)).isoformat()
        rows = []
        for tipo in sc["types"]:
            for d in await db[COLL[tipo]].find(_query(sc, tipo, user["org_id"]), {"_id": 0}).to_list(1000):
                rows.append((tipo, d))
        pids = {d.get("responsabile_id") for _, d in rows if d.get("responsabile_id")}
        eids = {d.get(EV_FIELD[t]) for t, d in rows if d.get(EV_FIELD[t])}
        persons = {p["id"]: f"{p.get('nome') or ''} {p.get('cognome') or ''}".strip()
                   for p in await db.persons.find({"org_id": user["org_id"], "id": {"$in": list(pids)}}, {"_id": 0, "id": 1, "nome": 1, "cognome": 1}).to_list(1000)}
        events = {e["id"]: e.get("nome") for e in await db.events.find({"org_id": user["org_id"], "id": {"$in": list(eids)}}, {"_id": 0, "id": 1, "nome": 1}).to_list(1000)}
        items = []
        for tipo, d in rows:
            due = (d.get(DATE_FIELD[tipo]) or "")[:10] or None
            bucket = "ritardo" if due and due < today.isoformat() else "scadenza" if due and due <= soon else "da_fare"
            ev = d.get(EV_FIELD[tipo])
            items.append({"tipo": tipo, "id": d["id"], "titolo": d.get("titolo"), "stato": d.get("stato"), "priorita": d.get("priorita"),
                          "scadenza": due, "bucket": bucket, "responsabile": persons.get(d.get("responsabile_id")), "responsabile_id": d.get("responsabile_id") or None,
                          "evento": events.get(ev), "evento_id": ev,
                          "can_edit": P.allows(sc["perm"], (tipo,), "edit")})
        order = {"ritardo": 0, "scadenza": 1, "da_fare": 2}
        items.sort(key=lambda i: (order[i["bucket"]], i["scadenza"] or "9999", (i["titolo"] or "").lower()))
        return {"items": items, "types": sc["types"]}

    @r.get("/my/todo/assignees")
    async def assignees(user: dict = Depends(require_admin)):
        rows = await db.persons.find({"org_id": user["org_id"]}, {"_id": 0, "id": 1, "nome": 1, "cognome": 1}).to_list(5000)
        rows.sort(key=lambda p: ((p.get("cognome") or "").lower(), (p.get("nome") or "").lower()))
        return {"items": rows}

    @r.post("/my/todo/assign")
    async def assign(body: AssignIn, user: dict = Depends(require_admin)):
        sc = await _scope(user)
        if body.tipo not in sc["types"] or not P.allows(sc["perm"], (body.tipo,), "edit"):
            raise HTTPException(status_code=403, detail="Non hai i permessi per assegnare questa attività")
        if body.responsabile_id and not await db.persons.find_one({"org_id": user["org_id"], "id": body.responsabile_id}, {"_id": 1}):
            raise HTTPException(status_code=400, detail="Persona non valida")
        q = {**_query(sc, body.tipo, user["org_id"]), "id": body.id}
        q.pop("stato")
        res = await db[COLL[body.tipo]].update_one(q, {"$set": {"responsabile_id": body.responsabile_id or None, "updated_at": _now()}})
        if not res.matched_count:
            raise HTTPException(status_code=404, detail="Attività non trovata")
        p = await db.persons.find_one({"id": body.responsabile_id}, {"_id": 0, "nome": 1, "cognome": 1}) if body.responsabile_id else None
        return {"ok": True, "responsabile": f"{p.get('nome') or ''} {p.get('cognome') or ''}".strip() if p else None}

    @r.post("/my/todo/complete")
    async def complete(body: CompleteIn, user: dict = Depends(require_admin)):
        sc = await _scope(user)
        if body.tipo not in sc["types"] or not P.allows(sc["perm"], (body.tipo,), "edit"):
            raise HTTPException(status_code=403, detail="Non hai i permessi per completare questa attività")
        q = {**_query(sc, body.tipo, user["org_id"]), "id": body.id}
        q.pop("stato")
        res = await db[COLL[body.tipo]].update_one(q, {"$set": {"stato": DONE[body.tipo], "updated_at": _now()}})
        if not res.matched_count:
            raise HTTPException(status_code=404, detail="Attività non trovata")
        return {"ok": True}

    @r.get("/my/notes")
    async def notes(user: dict = Depends(get_current_user)):
        return {"items": await db.user_notes.find({"user_id": user["user_id"]}, {"_id": 0, "user_id": 0}).sort("created_at", -1).to_list(500)}

    @r.post("/my/notes")
    async def add_note(body: NoteIn, user: dict = Depends(get_current_user)):
        text = body.text.strip()[:5000]
        if not text:
            raise HTTPException(status_code=400, detail="La nota è vuota")
        doc = {"id": uuid.uuid4().hex, "user_id": user["user_id"], "text": text, "created_at": _now(), "updated_at": _now()}
        await db.user_notes.insert_one(dict(doc))
        doc.pop("user_id")
        return doc

    @r.put("/my/notes/{nid}")
    async def edit_note(nid: str, body: NoteIn, user: dict = Depends(get_current_user)):
        text = body.text.strip()[:5000]
        if not text:
            raise HTTPException(status_code=400, detail="La nota è vuota")
        res = await db.user_notes.update_one({"id": nid, "user_id": user["user_id"]}, {"$set": {"text": text, "updated_at": _now()}})
        if not res.matched_count:
            raise HTTPException(status_code=404, detail="Nota non trovata")
        return {"ok": True}

    @r.delete("/my/notes/{nid}")
    async def del_note(nid: str, user: dict = Depends(get_current_user)):
        res = await db.user_notes.delete_one({"id": nid, "user_id": user["user_id"]})
        if not res.deleted_count:
            raise HTTPException(status_code=404, detail="Nota non trovata")
        return {"ok": True}

    return r
