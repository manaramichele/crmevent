"""Duplica evento: nuova edizione nella stessa organizzazione, solo configurazioni riutilizzabili (mai persone, pagamenti, video, attivazioni)."""
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

EVENT_SKIP = {"_id", "id", "created_at", "updated_at", "entitlement", "homepage_logo", "calendar_event_id", "gcal_event_id", "duplicated_from"}
DATE_FIELDS = ("data_inizio_allestimento", "data_inizio", "data_fine", "data_fine_disallestimento")


class DuplicateIn(BaseModel):
    nome: str = Field(min_length=2, max_length=200)
    edizione: Optional[str] = Field(None, max_length=40)
    data_inizio: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    copy_maps: bool = True
    copy_teams: bool = True
    copy_activities: bool = True
    copy_planner: bool = False


def _now():
    return datetime.now(timezone.utc).isoformat()


def _shift(v: Optional[str], days: int) -> Optional[str]:
    if not v or not days:
        return v
    try:
        return (date.fromisoformat(v[:10]) + timedelta(days=days)).isoformat() + v[10:]
    except ValueError:
        return v


def build(db, deps):
    r = APIRouter(prefix="/api")
    admin_dep, check_limit, ev_ids, audit = deps["require_admin"], deps["check_limit"], deps["ev_ids"], deps["record_audit"]

    async def _copy(coll: str, q: dict, new_eid: str, field: str, fix) -> int:
        n = 0
        for d in await db[coll].find(q, {"_id": 0}).to_list(5000):
            doc = fix({**d, "id": uuid.uuid4().hex, field: new_eid, "created_at": _now(), "updated_at": _now()})
            await db[coll].insert_one(doc)
            n += 1
        return n

    @r.post("/events/{event_id}/duplicate")
    async def duplicate(event_id: str, body: DuplicateIn, user: dict = Depends(admin_dep)):
        org = user["org_id"]
        if ev_ids(user) is not None:
            raise HTTPException(status_code=403, detail="Puoi operare solo sugli eventi assegnati: non puoi creare nuovi eventi")
        src = await db.events.find_one({"id": event_id, "org_id": org}, {"_id": 0})
        if not src:
            raise HTTPException(status_code=404, detail="Evento non trovato")
        await check_limit(org, "events")
        days = 0
        if body.data_inizio and src.get("data_inizio"):
            days = (date.fromisoformat(body.data_inizio) - date.fromisoformat(src["data_inizio"][:10])).days
        new = {k: v for k, v in src.items() if k not in EVENT_SKIP}
        for f in DATE_FIELDS:
            new[f] = _shift(src.get(f), days)
        if body.data_inizio:
            new["data_inizio"] = body.data_inizio
        if src.get("giorni_descrizioni"):
            new["giorni_descrizioni"] = {_shift(k, days): v for k, v in src["giorni_descrizioni"].items()}
        nid = uuid.uuid4().hex
        new |= {"id": nid, "org_id": org, "nome": body.nome.strip(), "edizione": (body.edizione or "").strip() or None, "stato": "pianificato",
                "duplicated_from": event_id, "created_at": _now(), "updated_at": _now()}
        await db.events.insert_one(new)
        counts = {}
        try:
            team_map = {}
            if body.copy_teams:
                for t in await db.teams.find({"org_id": org, "evento_id": event_id}, {"_id": 0}).to_list(1000):
                    tid = uuid.uuid4().hex
                    team_map[t["id"]] = tid
                    await db.teams.insert_one({**t, "id": tid, "evento_id": nid, "responsabile_id": None, "created_at": _now(), "updated_at": _now()})
                counts["teams"] = len(team_map)
            if body.copy_maps:
                counts["maps"] = await _copy("event_maps", {"org_id": org, "evento_id": event_id}, nid, "evento_id",
                                             lambda d: {**d, "team_id": team_map.get(d.get("team_id"))})
            if body.copy_activities:
                counts["activities"] = await _copy("activities", {"org_id": org, "evento_id": event_id}, nid, "evento_id",
                                                   lambda d: {**d, "stato": "da_fare", "data": _shift(d.get("data"), days), "persona_id": None, "responsabile_id": None,
                                                              "calendar_event_id": None, "gcal_event_id": None})
            if body.copy_planner:
                counts["planner"] = await _copy("planner_projects", {"org_id": org, "evento_id": event_id, "archiviato": {"$ne": True}}, nid, "evento_id",
                                                lambda d: {**d, "version": 1, "created_by": user.get("email"), "updated_by": user.get("email")})
        except Exception:
            for c in ("teams", "event_maps", "activities", "planner_projects"):
                await db[c].delete_many({"org_id": org, "evento_id": nid})
            await db.events.delete_one({"id": nid})
            raise HTTPException(status_code=500, detail="Duplicazione non riuscita: nessun dato è stato creato")
        await audit(user, "event_duplicated", org_id=org, detail=f"{src.get('nome')} → {new['nome']} · " + ", ".join(f"{k} {v}" for k, v in counts.items()))
        return {"id": nid, "nome": new["nome"], "counts": counts}

    return {"router": r}
