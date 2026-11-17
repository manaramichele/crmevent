"""Control Room (Fase 3): interventi, assegnazioni, comunicazioni, notifiche, diario operativo, ruoli e accesso mobile operatori."""
import asyncio
import csv
import hashlib
import io
import math
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

import storage_utils

PRIORITIES = ("bassa", "media", "alta", "critica")
STATES = ("segnalato", "preso_in_carico", "squadra_inviata", "sul_posto", "risolto", "chiuso", "in_attesa", "annullato")
FLOW = {"segnalato": {"preso_in_carico", "in_attesa", "annullato"}, "preso_in_carico": {"squadra_inviata", "in_attesa", "annullato"},
        "in_attesa": {"preso_in_carico", "squadra_inviata", "annullato"}, "squadra_inviata": {"sul_posto", "in_attesa", "annullato"},
        "sul_posto": {"risolto", "in_attesa"}, "risolto": {"chiuso", "sul_posto"}, "chiuso": set(), "annullato": set()}
CLOSED = {"chiuso", "annullato"}
TIMES = {"preso_in_carico": "t_presa", "squadra_inviata": "t_invio", "sul_posto": "t_arrivo", "risolto": "t_risoluzione", "chiuso": "t_chiusura"}
ACTIVE_ASG = {"non_confermata", "confermata"}
LINEAR = ["preso_in_carico", "squadra_inviata", "sul_posto", "risolto"]
ITV_TYPES = [("sanitario", "Soccorso sanitario", "Cross", "#DC2626", "alta", "Sanitario"), ("infortunio", "Infortunio atleta", "HeartPulse", "#E11D48", "alta", "Sanitario"),
             ("ostacolo", "Ostacolo sul percorso", "TriangleAlert", "#EA580C", "media", "Percorso"), ("viabilita", "Problema di viabilità", "TrafficCone", "#CA8A04", "media", "Viabilità"),
             ("sicurezza", "Sicurezza", "Shield", "#1D4ED8", "alta", "Sicurezza"), ("disperso", "Persona dispersa", "Users", "#7C3AED", "alta", "Sicurezza"),
             ("logistico", "Problema logistico", "Truck", "#0F766E", "bassa", "Logistica"), ("tecnico", "Problema tecnico", "Flame", "#475569", "bassa", "Tecnico"),
             ("ristoro", "Problema al ristoro", "CupSoda", "#F59E0B", "bassa", "Logistica"), ("volontario", "Segnalazione volontario", "Flag", "#0ABAB5", "bassa", None),
             ("altro", "Altro", "MapPin", "#64748B", "media", None)]
DEFAULT_ITV_TYPES = [{"key": k, "label": lbl, "icon": i, "color": c, "priorita": p, "gruppo": g} for k, lbl, i, c, p, g in ITV_TYPES]
CR_ROLES = ("responsabile", "coordinatore", "operatore", "visualizzatore")
IMG = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/heic": "heic", "image/heif": "heic"}
MAX_IMG = 8 * 1024 * 1024
Txt = Optional[str]


class PosIn(BaseModel):
    lng: Optional[float] = Field(None, ge=-180, le=180)
    lat: Optional[float] = Field(None, ge=-90, le=90)
    post_id: Txt = None
    sector_id: Txt = None
    km: Optional[float] = Field(None, ge=0, le=1000)
    riferimento: Optional[str] = Field(None, max_length=300)


class ItvIn(PosIn):
    tipologia: str = Field(min_length=1, max_length=40)
    priorita: Literal[PRIORITIES]
    descrizione: str = Field(min_length=1, max_length=1000)
    origine: Literal["centrale", "telefono", "radio", "mappa", "campo"] = "centrale"
    responsabile_incaricato: Optional[str] = Field(None, max_length=120)
    note: Optional[str] = Field(None, max_length=4000)


class ItvEdit(ItvIn):
    version: int


class StatusIn(BaseModel):
    to: Literal[STATES]
    note: Optional[str] = Field(None, max_length=1000)
    motivo: Optional[str] = Field(None, max_length=500)
    force: bool = False
    version: int


class AssignIn(BaseModel):
    resource_ids: list[str] = Field(min_length=1, max_length=50)
    conferma_esterni: bool = False
    note: Optional[str] = Field(None, max_length=500)


class ConfirmIn(BaseModel):
    via: Literal["radio", "telefono", "di persona"] = "radio"


class MessageIn(BaseModel):
    to_type: Literal["operatore", "squadra", "settore", "coordinatori", "tutti"]
    to_id: Txt = None
    text: str = Field(min_length=1, max_length=1000)
    intervention_id: Txt = None


class RoleIn(BaseModel):
    user_id: str
    role: Optional[Literal[CR_ROLES]] = None
    sector_ids: list[str] = []


class InviteIn(BaseModel):
    resource_id: str
    role: Literal["operatore", "coordinatore"] = "operatore"
    can_set_priority: bool = False
    days: int = Field(3, ge=1, le=30)


class HealthIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class MobileReportIn(PosIn):
    client_id: str = Field(min_length=8, max_length=64)
    tipologia: str = Field(min_length=1, max_length=40)
    descrizione: str = Field(min_length=1, max_length=1000)
    priorita: Optional[Literal[PRIORITIES]] = None
    pos_mode: Literal["postazione", "gps", "mappa", "manuale"] = "postazione"


class MobileActionIn(BaseModel):
    action: Literal["conferma", "rifiuta", "partito", "arrivato", "aggiorna", "risolto"]
    note: Optional[str] = Field(None, max_length=1000)


class MobileMsgIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _hash(t):
    return hashlib.sha256(t.encode()).hexdigest()


def _dist(a, b):
    r = math.radians
    dlat, dlng = r(b[1] - a[1]), r(b[0] - a[0])
    h = math.sin(dlat / 2) ** 2 + math.cos(r(a[1])) * math.cos(r(b[1])) * math.sin(dlng / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(h))


def _sniff(data):
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1", b"ftyphevc"):
        return "image/heic"
    return None


def attach(r, db, deps, require_active, H):
    ops_dep = deps["require_admin"]
    base = "/controlroom/events/{event_id}/ops"
    mb = "/cr-mobile/{token}"
    ctx, q, settings, touch, external = H["ctx"], H["q"], H["settings"], H["touch"], H["external"]

    async def ensure():
        await db.cr_interventions.create_index([("org_id", 1), ("event_id", 1), ("numero", 1)], unique=True, partialFilterExpression={"numero": {"$type": "number"}})
        await db.cr_interventions.create_index([("org_id", 1), ("event_id", 1), ("client_id", 1)], unique=True, partialFilterExpression={"client_id": {"$type": "string"}})
        await db.cr_invites.create_index("token_hash", unique=True)
        for c in ("cr_diary", "cr_messages", "cr_notifications", "cr_roles", "cr_attachments", "cr_itv_health", "cr_counters"):
            await db[c].create_index([("org_id", 1), ("event_id", 1)])
    H["ensure_tasks"].append(ensure)

    def can_itv(pm, itv=None, sector=None):
        if pm["role"] == "responsabile":
            return True
        if pm["role"] != "coordinatore":
            return False
        s = sector if sector is not None else (itv or {}).get("sector_id")
        return bool(s) and s in pm["sectors"]

    async def diary(org, eid, by, by_name, typ, text, itv=None, **x):
        await db.cr_diary.insert_one({"id": uuid.uuid4().hex, "org_id": org, "event_id": eid, "at": _now(), "by": by, "by_name": by_name, "type": typ, "text": text,
                                      "intervention_id": (itv or {}).get("id"), "codice": (itv or {}).get("codice"), **x})

    async def notify(org, eid, typ, text, level="info", itv=None, audience="centrale"):
        await db.cr_notifications.insert_one({"id": uuid.uuid4().hex, "org_id": org, "event_id": eid, "at": _now(), "type": typ, "text": text, "level": level,
                                              "intervention_id": (itv or {}).get("id"), "audience": audience})
    H["notify"] = notify

    async def bump(org, eid):
        await db.cr_settings.update_one({"org_id": org, "event_id": eid}, {"$inc": {"rev": 1}})

    def who(u):
        return u.get("email"), u.get("name") or u.get("email")

    async def resolve_pos(org, eid, d):
        pos = {k: d.get(k) for k in ("lng", "lat", "post_id", "sector_id", "km", "riferimento")}
        posts = await db.cr_posts.find({"org_id": org, "event_id": eid}, {"_id": 0, "id": 1, "lng": 1, "lat": 1, "sector_id": 1, "km": 1}).to_list(2000)
        byid = {p["id"]: p for p in posts}
        if pos["post_id"]:
            p = byid.get(pos["post_id"])
            if not p:
                raise HTTPException(status_code=400, detail="Postazione non valida")
            if pos["lng"] is None and p.get("lng") is not None:
                pos["lng"], pos["lat"] = p["lng"], p["lat"]
            pos["sector_id"] = pos["sector_id"] or p.get("sector_id")
            pos["km"] = pos["km"] if pos["km"] is not None else p.get("km")
        if (pos["lng"] is None) != (pos["lat"] is None):
            raise HTTPException(status_code=400, detail="Coordinate incomplete")
        if pos["sector_id"] and not await db.cr_sectors.find_one({"org_id": org, "event_id": eid, "id": pos["sector_id"]}, {"_id": 1}):
            raise HTTPException(status_code=400, detail="Settore non valido")
        if not pos["sector_id"] and pos["km"] is not None:
            s = await db.cr_sectors.find_one({"org_id": org, "event_id": eid, "km_inizio": {"$lte": pos["km"]}, "km_fine": {"$gte": pos["km"]}}, {"_id": 0, "id": 1})
            pos["sector_id"] = (s or {}).get("id")
        if not any(pos[k] not in (None, "") for k in pos):
            raise HTTPException(status_code=400, detail="Indica la posizione o un riferimento operativo")
        near = None
        if pos["lng"] is not None:
            cand = sorted(((_dist((pos["lng"], pos["lat"]), (p["lng"], p["lat"])), p["id"]) for p in posts if p.get("lng") is not None), key=lambda x: x[0])
            near = cand[0][1] if cand and cand[0][0] <= 1500 else None
        pos["post_vicina_id"] = pos["post_id"] or near
        pos["da_confermare"] = pos["lng"] is None
        return pos

    async def types_of(org, eid):
        s = await db.cr_settings.find_one({"org_id": org, "event_id": eid}, {"_id": 0, "itv_types": 1})
        return (s or {}).get("itv_types") or DEFAULT_ITV_TYPES

    async def create_itv(org, eid, data, by, by_name, extra):
        types = {t["key"]: t for t in await types_of(org, eid)}
        if data["tipologia"] not in types:
            raise HTTPException(status_code=400, detail="Tipologia non valida")
        pos = await resolve_pos(org, eid, data)
        seq = await db.cr_counters.find_one_and_update({"org_id": org, "event_id": eid, "key": "itv"}, {"$inc": {"seq": 1}}, upsert=True, return_document=ReturnDocument.AFTER)
        n = seq["seq"]
        doc = {"id": uuid.uuid4().hex, "org_id": org, "event_id": eid, "numero": n, "codice": f"INT-{n:03d}", "created_at": _now(), "created_by": by, "created_by_name": by_name,
               "origine": data.get("origine", "campo"), "tipologia": data["tipologia"], "priorita": data["priorita"], "descrizione": data["descrizione"],
               "note": data.get("note"), "responsabile_incaricato": data.get("responsabile_incaricato"), **pos, "stato": "segnalato", "assignments": [],
               "version": 1, "updated_at": _now(), **extra}
        await db.cr_interventions.insert_one({**doc})
        await diary(org, eid, by, by_name, "segnalazione" if doc["origine"] == "campo" else "apertura", f"{doc['codice']} · {types[doc['tipologia']]['label']} · {doc['priorita'].upper()} · {doc['descrizione'][:120]}", doc)
        await notify(org, eid, "nuova_segnalazione", f"{doc['codice']} {types[doc['tipologia']]['label']}{' (dal campo)' if doc['origine'] == 'campo' else ''}", "critical" if doc["priorita"] == "critica" else "info", doc)
        await bump(org, eid)
        doc.pop("_id", None)
        return doc

    async def get_itv(org, eid, iid):
        it = await db.cr_interventions.find_one({"org_id": org, "event_id": eid, "id": iid}, {"_id": 0})
        if not it:
            raise HTTPException(status_code=404, detail="Intervento non trovato")
        return it

    async def save_itv(it, upd, version=None, extra_ops=None, array_filters=None):
        flt = {"org_id": it["org_id"], "event_id": it["event_id"], "id": it["id"], "version": it["version"] if version is None else version}
        res = await db.cr_interventions.update_one(flt, {"$set": {**upd, "updated_at": _now()}, "$inc": {"version": 1}, **(extra_ops or {})}, array_filters=array_filters)
        if not res.matched_count:
            raise HTTPException(status_code=409, detail="Intervento modificato nel frattempo da un altro operatore: ricarico la versione più recente")

    async def transition(it, to, by, by_name, note=None, motivo=None, force=False, reopen_ok=False, version=None):
        frm = it["stato"]
        if to == frm:
            raise HTTPException(status_code=400, detail="L'intervento è già in questo stato")
        reopen = frm in CLOSED
        if reopen and not (reopen_ok and motivo):
            raise HTTPException(status_code=403 if not reopen_ok else 400, detail="Per riaprire servono il permesso del responsabile e una motivazione")
        if not reopen and to not in FLOW[frm] and not force:
            raise HTTPException(status_code=409, detail="Cambio di stato non coerente con il flusso operativo")
        if to == "annullato" and not motivo:
            raise HTTPException(status_code=400, detail="Indica la motivazione dell'annullamento")
        upd = {"stato": to}
        if TIMES.get(to) and not it.get(TIMES[to]):
            upd[TIMES[to]] = _now()
        af = None
        if to in CLOSED and any(a["stato"] in ACTIVE_ASG for a in it.get("assignments") or []):
            upd["assignments.$[a].stato"] = "completata"
            af = [{"a.stato": {"$in": list(ACTIVE_ASG)}}]
        await save_itv(it, upd, version, {"$push": {"history": {"at": _now(), "from": frm, "to": to, "by": by, "by_name": by_name, "note": note, "motivo": motivo, "forzato": force}}}, af)
        if to in CLOSED:
            await release(it)
        typ = {"chiuso": "chiusura", "annullato": "annullamento", "risolto": "risoluzione", "sul_posto": "arrivo", "squadra_inviata": "partenza",
               "preso_in_carico": "presa_in_carico"}.get(to, "stato")
        await diary(it["org_id"], it["event_id"], by, by_name, "riapertura" if reopen else typ, f"{it['codice']}: {frm} → {to}{' (forzato)' if force else ''}{f' · {motivo}' if motivo else ''}{f' · {note}' if note else ''}",
                    it, **{"from": frm, "to": to})
        if to in ("risolto", "chiuso", "annullato") or reopen:
            await notify(it["org_id"], it["event_id"], "stato", f"{it['codice']}: {to.replace('_', ' ')}", "info", it)
        await bump(it["org_id"], it["event_id"])

    async def release(it):
        for a in it.get("assignments") or []:
            if a["stato"] in ACTIVE_ASG:
                busy = await db.cr_interventions.count_documents({"org_id": it["org_id"], "event_id": it["event_id"], "id": {"$ne": it["id"]}, "stato": {"$nin": list(CLOSED)},
                                                                  "assignments": {"$elemMatch": {"resource_id": a["resource_id"], "stato": {"$in": list(ACTIVE_ASG)}}}})
                if not busy:
                    await db.cr_resources.update_one({"org_id": it["org_id"], "event_id": it["event_id"], "id": a["resource_id"], "stato": "impegnato"},
                                                     {"$set": {"stato": "disponibile"}, "$inc": {"version": 1}})

    async def op_audience(org, eid, resource_id):
        return [f"op:{i['id']}" for i in await db.cr_invites.find({"org_id": org, "event_id": eid, "resource_id": resource_id, "revoked_at": None}, {"_id": 0, "id": 1}).to_list(20)]

    # ---------- centrale ----------
    async def cctx(u, eid, need=None, itv=None, sector=None):
        ev, pm = await ctx(u, eid)
        if need == "manage" and not can_itv(pm, itv, sector):
            raise HTTPException(status_code=403, detail="Non hai i permessi per gestire questo intervento")
        if need == "resp" and pm["role"] != "responsabile":
            raise HTTPException(status_code=403, detail="Operazione riservata al Responsabile Control Room")
        return ev, pm

    @r.post(base + "/interventions")
    async def new_itv(event_id: str, body: ItvIn, u: dict = Depends(ops_dep)):
        _, pm = await cctx(u, event_id)
        if pm["role"] not in ("responsabile", "coordinatore"):
            raise HTTPException(status_code=403, detail="Non hai i permessi per aprire interventi")
        data = body.model_dump()
        if pm["role"] == "coordinatore":
            pos = await resolve_pos(u["org_id"], event_id, data)
            if pos["sector_id"] not in pm["sectors"]:
                raise HTTPException(status_code=403, detail="Puoi aprire interventi solo nel tuo settore")
        return await create_itv(u["org_id"], event_id, data, *who(u), {})

    @r.put(base + "/interventions/{iid}")
    async def edit_itv(event_id: str, iid: str, body: ItvEdit, u: dict = Depends(ops_dep)):
        it = await get_itv(u["org_id"], event_id, iid)
        _, pm = await cctx(u, event_id, "manage", it)
        data = body.model_dump(exclude={"version", "origine"})
        if data["tipologia"] not in {t["key"] for t in await types_of(u["org_id"], event_id)}:
            raise HTTPException(status_code=400, detail="Tipologia non valida")
        pos = await resolve_pos(u["org_id"], event_id, data)
        if pm["role"] == "coordinatore" and pos["sector_id"] not in pm["sectors"]:
            raise HTTPException(status_code=403, detail="Puoi spostare l'intervento solo nel tuo settore")
        await save_itv(it, {**data, **pos}, body.version)
        by, name = who(u)
        if data["priorita"] != it["priorita"]:
            await diary(u["org_id"], event_id, by, name, "cambio_priorita", f"{it['codice']}: priorità {it['priorita']} → {data['priorita']}", it)
            if data["priorita"] == "critica":
                await notify(u["org_id"], event_id, "critico", f"{it['codice']} ora CRITICO", "critical", it)
        else:
            await diary(u["org_id"], event_id, by, name, "aggiornamento", f"{it['codice']}: dati aggiornati", it)
        await bump(u["org_id"], event_id)
        return {"ok": True}

    @r.post(base + "/interventions/{iid}/status")
    async def set_itv_status(event_id: str, iid: str, body: StatusIn, u: dict = Depends(ops_dep)):
        it = await get_itv(u["org_id"], event_id, iid)
        _, pm = await cctx(u, event_id, "manage", it)
        resp = pm["role"] == "responsabile"
        if body.to == "chiuso" and not resp:
            raise HTTPException(status_code=403, detail="La chiusura definitiva è riservata al Responsabile Control Room")
        if body.force and (not resp or not body.note):
            raise HTTPException(status_code=403, detail="Il cambio fuori flusso richiede il Responsabile e una nota")
        await transition(it, body.to, *who(u), body.note, body.motivo, body.force, resp, body.version)
        return {"ok": True}

    @r.post(base + "/interventions/{iid}/assign")
    async def assign(event_id: str, iid: str, body: AssignIn, u: dict = Depends(ops_dep)):
        it = await get_itv(u["org_id"], event_id, iid)
        _, pm = await cctx(u, event_id, "manage", it)
        if it["stato"] in CLOSED:
            raise HTTPException(status_code=400, detail="Intervento chiuso o annullato")
        s = await settings(u, event_id)
        res = {x["id"]: x for x in await db.cr_resources.find(q(u, event_id, id={"$in": body.resource_ids}), {"_id": 0}).to_list(50)}
        have = {a["resource_id"] for a in it.get("assignments") or [] if a["stato"] in ACTIVE_ASG}
        new = []
        for rid in body.resource_ids:
            x = res.get(rid)
            if not x:
                raise HTTPException(status_code=400, detail="Risorsa non valida")
            if rid in have:
                continue
            if x["kind"] == "mezzo" and x.get("tipologia") in external:
                if not x.get("autorizzazione_ente") or not body.conferma_esterni:
                    raise HTTPException(status_code=400, detail=f"{x.get('codice') or x.get('nome')}: mezzo di ente esterno, serve l'autorizzazione dell'ente e la conferma esplicita dell'accordo operativo")
            if pm["role"] == "coordinatore" and x.get("sector_id") not in pm["sectors"]:
                post = await db.cr_posts.find_one(q(u, event_id, id=x.get("post_id")), {"_id": 0, "sector_id": 1}) if x.get("post_id") else None
                if (post or {}).get("sector_id") not in pm["sectors"]:
                    raise HTTPException(status_code=403, detail="Puoi assegnare solo risorse del tuo settore")
            new.append({"resource_id": rid, "label": x.get("nome") or x.get("codice"), "stato": "non_confermata", "assigned_at": _now(), "assigned_by": u.get("email"),
                        "note": body.note})
        if not new:
            raise HTTPException(status_code=400, detail="Le risorse selezionate sono già assegnate")
        await save_itv(it, {}, None, {"$push": {"assignments": {"$each": new}}})
        by, name = who(u)
        for a in new:
            if s.get("assign_sets_busy", True):
                await db.cr_resources.update_one(q(u, event_id, id=a["resource_id"], stato="disponibile"), {"$set": {"stato": "impegnato"}, "$inc": {"version": 1}})
            await diary(u["org_id"], event_id, by, name, "assegnazione", f"{it['codice']} assegnato a {a['label']} (in attesa di conferma)", it, resource_id=a["resource_id"])
            for aud in await op_audience(u["org_id"], event_id, a["resource_id"]):
                await notify(u["org_id"], event_id, "nuova_assegnazione", f"Nuovo incarico {it['codice']}: {it['descrizione'][:80]}", "critical" if it["priorita"] == "critica" else "info", it, aud)
        await bump(u["org_id"], event_id)
        return {"assigned": len(new)}

    async def set_asg(it, rid, upd, expect=None):
        a = next((a for a in it.get("assignments") or [] if a["resource_id"] == rid and a["stato"] in ACTIVE_ASG), None)
        if not a or (expect and a["stato"] not in expect):
            raise HTTPException(status_code=409, detail="Assegnazione non attiva o già aggiornata")
        res = await db.cr_interventions.update_one({"org_id": it["org_id"], "event_id": it["event_id"], "id": it["id"], "assignments": {"$elemMatch": {"resource_id": rid, "stato": a["stato"]}}},
                                                   {"$set": {**{f"assignments.$.{k}": v for k, v in upd.items()}, "updated_at": _now()}, "$inc": {"version": 1}})
        if not res.matched_count:
            raise HTTPException(status_code=409, detail="Assegnazione aggiornata nel frattempo")
        return a

    @r.post(base + "/interventions/{iid}/assignments/{rid}/confirm")
    async def confirm_central(event_id: str, iid: str, rid: str, body: ConfirmIn, u: dict = Depends(ops_dep)):
        it = await get_itv(u["org_id"], event_id, iid)
        await cctx(u, event_id, "manage", it)
        a = await set_asg(it, rid, {"stato": "confermata", "confirmed_at": _now(), "confirmed_via": body.via, "confirmed_by": u.get("email")}, {"non_confermata"})
        await diary(u["org_id"], event_id, *who(u), "conferma", f"{it['codice']}: presa in carico di {a['label']} confermata via {body.via}", it, resource_id=rid)
        await bump(u["org_id"], event_id)
        return {"ok": True}

    @r.delete(base + "/interventions/{iid}/assignments/{rid}")
    async def unassign(event_id: str, iid: str, rid: str, u: dict = Depends(ops_dep)):
        it = await get_itv(u["org_id"], event_id, iid)
        await cctx(u, event_id, "manage", it)
        a = await set_asg(it, rid, {"stato": "revocata", "revoked_at": _now(), "revoked_by": u.get("email")})
        await release({**it, "assignments": [a]})
        await diary(u["org_id"], event_id, *who(u), "assegnazione", f"{it['codice']}: assegnazione a {a['label']} revocata", it, resource_id=rid)
        await bump(u["org_id"], event_id)
        return {"ok": True}

    async def read_upload(file):
        data = await file.read(MAX_IMG + 1)
        if len(data) > MAX_IMG:
            raise HTTPException(status_code=413, detail="Fotografia troppo grande (massimo 8 MB)")
        mime = _sniff(data)
        if not mime or (file.content_type or "").lower() not in IMG:
            raise HTTPException(status_code=415, detail="Formato non supportato: usa JPG, PNG, WEBP o HEIC")
        return data, mime

    async def store_att(it, data, mime, by, by_name, fname):
        aid = uuid.uuid4().hex
        res = await asyncio.to_thread(storage_utils.save, f"controlroom/{it['org_id']}/{it['event_id']}/{aid}.{IMG[mime]}", data, mime)
        doc = {"id": aid, "org_id": it["org_id"], "event_id": it["event_id"], "intervention_id": it["id"], "storage_path": res["path"], "storage_backend": res.get("backend"),
               "mime": mime, "size": len(data), "filename": (fname or "foto")[:120], "by": by, "by_name": by_name, "at": _now()}
        await db.cr_attachments.insert_one({**doc})
        await diary(it["org_id"], it["event_id"], by, by_name, "allegato", f"{it['codice']}: fotografia allegata", it)
        await bump(it["org_id"], it["event_id"])
        return {k: doc[k] for k in ("id", "mime", "size", "filename", "by_name", "at")}

    async def send_att(it, aid):
        a = await db.cr_attachments.find_one({"org_id": it["org_id"], "event_id": it["event_id"], "intervention_id": it["id"], "id": aid}, {"_id": 0})
        if not a:
            raise HTTPException(status_code=404, detail="Allegato non trovato")
        data, _ = await asyncio.to_thread(storage_utils.read, a["storage_path"], a.get("storage_backend"), a["mime"])
        return Response(content=data, media_type=a["mime"], headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})

    @r.post(base + "/interventions/{iid}/attachments")
    async def upload_att(event_id: str, iid: str, file: UploadFile = File(...), u: dict = Depends(ops_dep)):
        it = await get_itv(u["org_id"], event_id, iid)
        await cctx(u, event_id, "manage", it)
        data, mime = await read_upload(file)
        return await store_att(it, data, mime, *who(u), file.filename)

    @r.get(base + "/interventions/{iid}/attachments/{aid}")
    async def get_att(event_id: str, iid: str, aid: str, u: dict = Depends(ops_dep)):
        await ctx(u, event_id)
        return await send_att(await get_itv(u["org_id"], event_id, iid), aid)

    @r.get(base + "/interventions/{iid}/health")
    async def get_health(event_id: str, iid: str, u: dict = Depends(ops_dep)):
        await cctx(u, event_id, "resp")
        await get_itv(u["org_id"], event_id, iid)
        return {"notes": await db.cr_itv_health.find(q(u, event_id, intervention_id=iid), {"_id": 0, "org_id": 0}).sort("at", 1).to_list(200)}

    @r.post(base + "/interventions/{iid}/health")
    async def add_health(event_id: str, iid: str, body: HealthIn, u: dict = Depends(ops_dep)):
        await cctx(u, event_id, "resp")
        it = await get_itv(u["org_id"], event_id, iid)
        await db.cr_itv_health.insert_one({"id": uuid.uuid4().hex, "org_id": u["org_id"], "event_id": event_id, "intervention_id": iid, "text": body.text, "at": _now(), "by": u.get("email")})
        await diary(u["org_id"], event_id, *who(u), "aggiornamento", f"{it['codice']}: nota sanitaria riservata aggiunta", it)
        return {"ok": True}

    @r.post(base + "/messages")
    async def send_msg(event_id: str, body: MessageIn, u: dict = Depends(ops_dep)):
        _, pm = await cctx(u, event_id)
        if pm["role"] not in ("responsabile", "coordinatore"):
            raise HTTPException(status_code=403, detail="Non hai i permessi per inviare comunicazioni")
        if body.to_type in ("operatore", "squadra", "settore") and not body.to_id:
            raise HTTPException(status_code=400, detail="Seleziona il destinatario")
        invs = await db.cr_invites.find(q(u, event_id, revoked_at=None, expires_at={"$gt": _now()}), {"_id": 0}).to_list(2000)
        label = {"coordinatori": "Tutti i coordinatori", "tutti": "Tutti gli operatori"}.get(body.to_type)
        if body.to_type in ("operatore", "squadra"):
            x = await db.cr_resources.find_one(q(u, event_id, id=body.to_id), {"_id": 0})
            if not x:
                raise HTTPException(status_code=400, detail="Destinatario non valido")
            label, rec = x.get("nome") or x.get("codice"), [i for i in invs if i["resource_id"] == body.to_id]
            if not label and x.get("persona_id"):
                p = await db.persons.find_one({"org_id": u["org_id"], "id": x["persona_id"]}, {"_id": 0, "nome": 1, "cognome": 1})
                label = f"{(p or {}).get('nome', '')} {(p or {}).get('cognome', '')}".strip()
        elif body.to_type == "settore":
            sc = await db.cr_sectors.find_one(q(u, event_id, id=body.to_id), {"_id": 0, "nome": 1})
            if not sc:
                raise HTTPException(status_code=400, detail="Settore non valido")
            posts = {p["id"] for p in await db.cr_posts.find(q(u, event_id, sector_id=body.to_id), {"_id": 0, "id": 1}).to_list(2000)}
            rs = {x["id"] for x in await db.cr_resources.find(q(u, event_id, **{"$or": [{"sector_id": body.to_id}, {"post_id": {"$in": list(posts)}}]}), {"_id": 0, "id": 1}).to_list(5000)}
            label, rec = f"Settore {sc['nome']}", [i for i in invs if i["resource_id"] in rs]
        elif body.to_type == "coordinatori":
            rec = [i for i in invs if i["role"] == "coordinatore"]
        else:
            rec = invs
        by, name = who(u)
        doc = {"id": uuid.uuid4().hex, "org_id": u["org_id"], "event_id": event_id, "at": _now(), "from_type": "centrale", "from_id": by, "from_name": name,
               "to_type": body.to_type, "to_id": body.to_id, "to_label": label, "text": body.text, "intervention_id": body.intervention_id,
               "recipients": [i["id"] for i in rec], "delivered": {}, "read": {}}
        await db.cr_messages.insert_one({**doc})
        for i in rec:
            await notify(u["org_id"], event_id, "messaggio", f"Messaggio dalla Control Room: {body.text[:80]}", "info", None, f"op:{i['id']}")
        if body.to_type == "coordinatori":
            await notify(u["org_id"], event_id, "messaggio", f"Ai coordinatori: {body.text[:80]}", "info")
        await diary(u["org_id"], event_id, by, name, "comunicazione", f"Messaggio a {label}: {body.text[:120]}", {"id": body.intervention_id} if body.intervention_id else None)
        await bump(u["org_id"], event_id)
        return {"id": doc["id"], "recipients": len(rec)}

    @r.post(base + "/messages/read")
    async def read_inbound(event_id: str, u: dict = Depends(ops_dep)):
        await ctx(u, event_id)
        await db.cr_messages.update_many(q(u, event_id, to_type="centrale", read_at=None), {"$set": {"read_at": _now(), "read_by": u.get("email")}})
        await bump(u["org_id"], event_id)
        return {"ok": True}

    @r.post(base + "/notifications/read")
    async def read_notifs(event_id: str, u: dict = Depends(ops_dep)):
        await ctx(u, event_id)
        await db.cr_reads.update_one(q(u, event_id, user_id=u["user_id"]), {"$set": {"last_at": _now()}}, upsert=True)
        return {"ok": True}

    @r.get(base + "/diary")
    async def get_diary(event_id: str, type: Optional[str] = None, intervention_id: Optional[str] = None, limit: int = 500, u: dict = Depends(ops_dep)):
        await ctx(u, event_id)
        f = q(u, event_id)
        if type:
            f["type"] = type
        if intervention_id:
            f["intervention_id"] = intervention_id
        return {"rows": await db.cr_diary.find(f, {"_id": 0, "org_id": 0}).sort("at", 1).to_list(min(max(limit, 1), 5000))}

    @r.get(base + "/diary/export")
    async def export_diary(event_id: str, u: dict = Depends(ops_dep)):
        ev, _ = await cctx(u, event_id, "resp")
        rows = await db.cr_diary.find(q(u, event_id), {"_id": 0}).sort("at", 1).to_list(50000)
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(["data_ora_utc", "tipo", "intervento", "utente", "descrizione"])
        for x in rows:
            w.writerow([x["at"], x["type"], x.get("codice") or "", x.get("by_name") or "", x["text"]])
        return Response(content="\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="diario-{event_id[:8]}.csv"'})

    @r.get(base + "/members")
    async def members(event_id: str, u: dict = Depends(ops_dep)):
        await cctx(u, event_id, "resp")
        ms = await db.memberships.find({"org_id": u["org_id"], "active": {"$ne": False}}, {"_id": 0, "user_id": 1, "role": 1}).to_list(500)
        users = {x["user_id"]: x for x in await db.users.find({"user_id": {"$in": [m["user_id"] for m in ms]}}, {"_id": 0, "user_id": 1, "name": 1, "email": 1}).to_list(500)}
        roles = {x["user_id"]: x for x in await db.cr_roles.find(q(u, event_id), {"_id": 0}).to_list(500)}
        return {"members": [{"user_id": m["user_id"], "name": (users.get(m["user_id"]) or {}).get("name"), "email": (users.get(m["user_id"]) or {}).get("email"), "org_role": m["role"],
                             "cr_role": (roles.get(m["user_id"]) or {}).get("role"), "sector_ids": (roles.get(m["user_id"]) or {}).get("sector_ids", [])} for m in ms if m["user_id"] in users]}

    @r.put(base + "/roles")
    async def set_role(event_id: str, body: RoleIn, u: dict = Depends(ops_dep)):
        await cctx(u, event_id, "resp")
        if not await db.memberships.find_one({"org_id": u["org_id"], "user_id": body.user_id}, {"_id": 1}):
            raise HTTPException(status_code=404, detail="Utente non trovato nell'organizzazione")
        if body.role is None:
            await db.cr_roles.delete_one(q(u, event_id, user_id=body.user_id))
        else:
            await db.cr_roles.update_one(q(u, event_id, user_id=body.user_id), {"$set": {"role": body.role, "sector_ids": body.sector_ids, "by": u.get("email"), "at": _now()}}, upsert=True)
        await deps["audit"](u, "controlroom_role", detail=f"{event_id} · {body.user_id} · {body.role}")
        await bump(u["org_id"], event_id)
        return {"ok": True}

    def new_token():
        t = secrets.token_urlsafe(32)
        return t, _hash(t)

    @r.post(base + "/invites")
    async def create_invite(event_id: str, body: InviteIn, u: dict = Depends(ops_dep)):
        await cctx(u, event_id, "resp")
        x = await db.cr_resources.find_one(q(u, event_id, id=body.resource_id), {"_id": 0, "id": 1})
        if not x:
            raise HTTPException(status_code=400, detail="Risorsa non valida")
        t, h = new_token()
        doc = {"id": uuid.uuid4().hex, "org_id": u["org_id"], "event_id": event_id, "resource_id": body.resource_id, "role": body.role, "can_set_priority": body.can_set_priority,
               "token_hash": h, "expires_at": (datetime.now(timezone.utc) + timedelta(days=body.days)).isoformat(), "revoked_at": None, "created_by": u.get("email"), "created_at": _now()}
        await db.cr_invites.update_many(q(u, event_id, resource_id=body.resource_id, revoked_at=None), {"$set": {"revoked_at": _now(), "revoked_by": u.get("email")}})
        await db.cr_invites.insert_one({**doc})
        await deps["audit"](u, "controlroom_invite", detail=f"{event_id} · {body.resource_id} · {body.role}")
        await bump(u["org_id"], event_id)
        return {"id": doc["id"], "token": t, "expires_at": doc["expires_at"]}

    @r.delete(base + "/invites/{inv_id}")
    async def revoke_invite(event_id: str, inv_id: str, u: dict = Depends(ops_dep)):
        await cctx(u, event_id, "resp")
        res = await db.cr_invites.update_one(q(u, event_id, id=inv_id, revoked_at=None), {"$set": {"revoked_at": _now(), "revoked_by": u.get("email")}})
        if not res.matched_count:
            raise HTTPException(status_code=404, detail="Invito non trovato")
        await bump(u["org_id"], event_id)
        return {"ok": True}

    async def extra(u, eid, pm, s, res, posts):
        itv = await db.cr_interventions.find(q(u, eid), {"_id": 0, "org_id": 0}).sort("numero", -1).to_list(2000)
        opened = [i for i in itv if i["stato"] not in CLOSED]
        timeout = (datetime.now(timezone.utc) - timedelta(minutes=s.get("confirm_timeout_min") or 3)).isoformat()
        busy = {}
        for i in opened:
            for a in i.get("assignments") or []:
                if a["stato"] in ACTIVE_ASG:
                    busy.setdefault(a["resource_id"], []).append(i["codice"])
                if a["stato"] == "non_confermata" and a["assigned_at"] < timeout and not a.get("late_notified"):
                    a["late_notified"] = True
                    await db.cr_interventions.update_one({"org_id": u["org_id"], "event_id": eid, "id": i["id"], "assignments": {"$elemMatch": {"resource_id": a["resource_id"], "stato": "non_confermata"}}},
                                                         {"$set": {"assignments.$.late_notified": True}})
                    await notify(u["org_id"], eid, "non_confermato", f"{i['codice']}: {a['label']} non ha confermato l'incarico", "warn", i)
        overlaps = {k: v for k, v in busy.items() if len(v) > 1}
        att = {}
        for a in await db.cr_attachments.find(q(u, eid), {"_id": 0, "id": 1, "intervention_id": 1, "filename": 1, "by_name": 1, "at": 1, "size": 1}).to_list(5000):
            att.setdefault(a["intervention_id"], []).append(a)
        for i in itv:
            i["attachments"] = att.get(i["id"], [])
            act = [a for a in i.get("assignments") or [] if a["stato"] in ACTIVE_ASG]
            i["senza_squadra"] = not act
            i["attesa_conferma"] = any(a["stato"] == "non_confermata" for a in act)
            i["can_manage"] = can_itv(pm, i)
        kpi = {"interventi_aperti": len(opened), "interventi_critici": sum(1 for i in opened if i["priorita"] == "critica"),
               "interventi_senza_squadra": sum(1 for i in opened if i["senza_squadra"]), "interventi_attesa_conferma": sum(1 for i in opened if i["attesa_conferma"]),
               "interventi_in_corso": sum(1 for i in opened if i["stato"] in ("squadra_inviata", "sul_posto")), "interventi_risolti": sum(1 for i in itv if i["stato"] in ("risolto", "chiuso"))}
        alerts = ([{"level": "high", "text": f"{i['codice']} CRITICO: {i['descrizione'][:60]}", "ref": ["interventions", i["id"]]} for i in opened if i["priorita"] == "critica"]
                  + [{"level": "mid", "text": f"{i['codice']}: assegnazione NON CONFERMATA", "ref": ["interventions", i["id"]]} for i in opened if i["attesa_conferma"]]
                  + [{"level": "mid", "text": f"Risorsa assegnata a più interventi: {', '.join(v)}", "ref": ["resources", k]} for k, v in overlaps.items()])
        msgs = await db.cr_messages.find(q(u, eid), {"_id": 0, "org_id": 0}).sort("at", -1).to_list(200)
        for m in msgs:
            m["n_recipients"], m["n_delivered"], m["n_read"] = len(m.get("recipients") or []), len(m.get("delivered") or {}), len(m.get("read") or {})
            m.pop("delivered", None)
        last = (await db.cr_reads.find_one(q(u, eid, user_id=u["user_id"]), {"_id": 0}) or {}).get("last_at") or ""
        notifs = await db.cr_notifications.find(q(u, eid, audience="centrale"), {"_id": 0, "org_id": 0}).sort("at", -1).to_list(60)
        out = {"interventions": itv, "itv_kpi": kpi, "itv_alerts": alerts, "overlaps": overlaps, "messages": msgs, "notifications": notifs,
               "unread": sum(1 for n in notifs if n["at"] > last), "unread_inbound": sum(1 for m in msgs if m["to_type"] == "centrale" and not m.get("read_at")),
               "itv_types": s.get("itv_types") or DEFAULT_ITV_TYPES, "diary": await db.cr_diary.find(q(u, eid), {"_id": 0, "org_id": 0}).sort("at", -1).to_list(80)}
        if pm["role"] == "responsabile":
            out["invites"] = [{k: v for k, v in i.items() if k not in ("token_hash", "_id", "org_id")} for i in await db.cr_invites.find(q(u, eid), {"_id": 0}).sort("created_at", -1).to_list(500)]
        return out
    H["extra"] = extra

    # ---------- accesso mobile operatori (invito personale) ----------
    async def mctx(token):
        inv = await db.cr_invites.find_one({"token_hash": _hash(token)}, {"_id": 0})
        if not inv or inv.get("revoked_at") or inv["expires_at"] < _now():
            raise HTTPException(status_code=401, detail="Invito non valido, scaduto o revocato: chiedi un nuovo link alla Control Room")
        await require_active(inv["org_id"], inv["event_id"])
        x = await db.cr_resources.find_one({"org_id": inv["org_id"], "event_id": inv["event_id"], "id": inv["resource_id"]}, {"_id": 0})
        if not x:
            raise HTTPException(status_code=401, detail="Risorsa non più presente nella Control Room")
        if x.get("persona_id"):
            p = await db.persons.find_one({"org_id": inv["org_id"], "id": x["persona_id"]}, {"_id": 0, "nome": 1, "cognome": 1})
            x["nome"] = f"{(p or {}).get('nome') or ''} {(p or {}).get('cognome') or ''}".strip()
        await db.cr_invites.update_one({"id": inv["id"]}, {"$set": {"last_seen_at": _now()}})
        return inv, x, (f"op:{inv['id']}", x.get("nome") or x.get("codice") or "Operatore")

    async def op_sector(inv, x):
        if x.get("sector_id"):
            return x["sector_id"]
        p = await db.cr_posts.find_one({"org_id": inv["org_id"], "event_id": inv["event_id"], "id": x.get("post_id")}, {"_id": 0, "sector_id": 1}) if x.get("post_id") else None
        return (p or {}).get("sector_id")

    def mine(inv, x, sector):
        f = [{"created_by": f"op:{inv['id']}"}, {"assignments": {"$elemMatch": {"resource_id": x["id"]}}}]
        if inv["role"] == "coordinatore" and sector:
            f.append({"sector_id": sector})
        return {"org_id": inv["org_id"], "event_id": inv["event_id"], "$or": f}

    @r.get(mb)
    async def m_home(token: str):
        inv, x, (oid, name) = await mctx(token)
        org, eid = inv["org_id"], inv["event_id"]
        ev = await db.events.find_one({"org_id": org, "id": eid}, {"_id": 0, "nome": 1, "data_inizio": 1})
        s = await db.cr_settings.find_one({"org_id": org, "event_id": eid}, {"_id": 0}) or {}
        post = await db.cr_posts.find_one({"org_id": org, "event_id": eid, "id": x.get("post_id")}, {"_id": 0, "id": 1, "nome": 1, "codice": 1, "responsabile": 1, "telefono": 1, "lng": 1, "lat": 1, "km": 1}) if x.get("post_id") else None
        sector = await op_sector(inv, x)
        sc = await db.cr_sectors.find_one({"org_id": org, "event_id": eid, "id": sector}, {"_id": 0, "nome": 1, "responsabile": 1, "telefono": 1}) if sector else None
        shift = await db.shifts.find_one({"org_id": org, "evento_id": eid, "id": x.get("shift_id")}, {"_id": 0, "data": 1, "ora_inizio": 1, "ora_fine": 1}) if x.get("shift_id") else None
        itv = await db.cr_interventions.find(mine(inv, x, sector), {"_id": 0, "org_id": 0, "history": 0, "created_by": 0}).sort("numero", -1).to_list(200)
        for i in itv:
            a = next((a for a in i.get("assignments") or [] if a["resource_id"] == x["id"] and a["stato"] != "revocata"), None)
            i["my_assignment"] = {k: a.get(k) for k in ("stato", "assigned_at", "confirmed_at", "motivo")} if a else None
            i["mine_report"] = i.get("reporter_invite") == inv["id"]
            i["assignments"] = [{"label": b["label"], "stato": b["stato"]} for b in i.get("assignments") or []]
        msgs = await db.cr_messages.find({"org_id": org, "event_id": eid, "$or": [{"recipients": inv["id"]}, {"from_id": oid}]}, {"_id": 0, "org_id": 0}).sort("at", -1).to_list(100)
        undelivered = [m["id"] for m in msgs if m.get("recipients") and inv["id"] in m["recipients"] and inv["id"] not in (m.get("delivered") or {})]
        if undelivered:
            await db.cr_messages.update_many({"id": {"$in": undelivered}}, {"$set": {f"delivered.{inv['id']}": _now()}})
        out_msgs = [{"id": m["id"], "at": m["at"], "from_name": m["from_name"], "text": m["text"], "mine": m["from_id"] == oid,
                     "read": inv["id"] in (m.get("read") or {}) if m["from_id"] != oid else bool(m.get("read_at"))} for m in msgs]
        notifs = await db.cr_notifications.find({"org_id": org, "event_id": eid, "audience": oid}, {"_id": 0, "org_id": 0}).sort("at", -1).to_list(30)
        return {"event": ev, "operator": {"nome": name, "codice": x.get("codice"), "kind": x["kind"], "stato": x["stato"], "presente": bool(x.get("presente")), "role": inv["role"],
                                         "can_set_priority": inv["can_set_priority"] or inv["role"] == "coordinatore"},
                "post": post, "sector": sc, "shift": shift, "centrale_tel": s.get("centrale_tel") or s.get("responsabile_tel"), "responsabile": s.get("responsabile"),
                "status": s.get("status", "preparazione"), "itv_types": [{k: t.get(k) for k in ("key", "label", "icon", "color", "priorita")} for t in (s.get("itv_types") or DEFAULT_ITV_TYPES)],
                "interventions": itv, "messages": out_msgs, "notifications": notifs, "unread": sum(1 for n in notifs if n["at"] > (inv.get("last_notif_at") or "")),
                "expires_at": inv["expires_at"], "server_time": _now()}

    @r.post(mb + "/checkin")
    async def m_checkin(token: str, body: dict):
        inv, x, (oid, name) = await mctx(token)
        on = bool(body.get("presente", True))
        await db.cr_resources.update_one({"org_id": inv["org_id"], "event_id": inv["event_id"], "id": x["id"]}, {"$set": {"presente": on, "presente_at": _now() if on else None, "presente_by": oid}, "$inc": {"version": 1}})
        await diary(inv["org_id"], inv["event_id"], oid, name, "presenza", f"{name}: {'in postazione' if on else 'ha lasciato la postazione'} (da smartphone)")
        await touch({"org_id": inv["org_id"], "name": name, "email": oid}, inv["event_id"], "presence", "risorsa", x["id"], "check-in mobile" if on else "check-out mobile")
        return {"presente": on, "at": _now()}

    @r.post(mb + "/reports")
    async def m_report(token: str, body: MobileReportIn):
        inv, x, (oid, name) = await mctx(token)
        dup = await db.cr_interventions.find_one({"org_id": inv["org_id"], "event_id": inv["event_id"], "client_id": body.client_id}, {"_id": 0, "codice": 1, "stato": 1, "created_at": 1, "id": 1})
        if dup:
            return {**dup, "duplicate": True}
        data = body.model_dump()
        types = {t["key"]: t for t in await types_of(inv["org_id"], inv["event_id"])}
        if data["tipologia"] not in types:
            raise HTTPException(status_code=400, detail="Tipologia non valida")
        allowed = inv["can_set_priority"] or inv["role"] == "coordinatore"
        data["priorita"] = data["priorita"] if allowed and data["priorita"] else types[data["tipologia"]].get("priorita") or "media"
        if body.pos_mode == "postazione":
            if not x.get("post_id"):
                raise HTTPException(status_code=400, detail="Non hai una postazione assegnata: indica la posizione in altro modo")
            data.update({"post_id": x["post_id"], "lng": None, "lat": None})
        data["origine"] = "campo"
        try:
            doc = await create_itv(inv["org_id"], inv["event_id"], data, oid, name, {"client_id": body.client_id, "reporter_invite": inv["id"], "pos_mode": body.pos_mode,
                                                                                   "priorita_indicativa": True})
        except DuplicateKeyError:
            doc = await db.cr_interventions.find_one({"org_id": inv["org_id"], "event_id": inv["event_id"], "client_id": body.client_id}, {"_id": 0})
        return {"id": doc["id"], "codice": doc["codice"], "stato": doc["stato"], "created_at": doc["created_at"]}

    @r.post(mb + "/interventions/{iid}/action")
    async def m_action(token: str, iid: str, body: MobileActionIn):
        inv, x, (oid, name) = await mctx(token)
        it = await get_itv(inv["org_id"], inv["event_id"], iid)
        a = next((a for a in it.get("assignments") or [] if a["resource_id"] == x["id"] and a["stato"] in ACTIVE_ASG), None)
        if not a:
            raise HTTPException(status_code=403, detail="Questo intervento non ti è assegnato")
        if it["stato"] in CLOSED:
            raise HTTPException(status_code=409, detail="Intervento già chiuso o annullato dalla Control Room")
        if body.action == "rifiuta":
            if not body.note:
                raise HTTPException(status_code=400, detail="Indica la motivazione del rifiuto")
            await set_asg(it, x["id"], {"stato": "rifiutata", "motivo": body.note, "refused_at": _now()})
            await release({**it, "assignments": [a]})
            await diary(inv["org_id"], inv["event_id"], oid, name, "rifiuto", f"{it['codice']}: incarico rifiutato da {name} · {body.note}", it, resource_id=x["id"])
            await notify(inv["org_id"], inv["event_id"], "rifiuto", f"{it['codice']}: {name} ha rifiutato l'incarico", "warn", it)
        elif body.action == "aggiorna":
            if not body.note:
                raise HTTPException(status_code=400, detail="Scrivi l'aggiornamento")
            await diary(inv["org_id"], inv["event_id"], oid, name, "aggiornamento", f"{it['codice']}: {body.note}", it)
            await notify(inv["org_id"], inv["event_id"], "aggiornamento", f"{it['codice']}: aggiornamento da {name}", "info", it)
        else:
            target = {"conferma": "preso_in_carico", "partito": "squadra_inviata", "arrivato": "sul_posto", "risolto": "risolto"}[body.action]
            cur = LINEAR.index(it["stato"]) if it["stato"] in LINEAR else -1
            steps = LINEAR[cur + 1:LINEAR.index(target) + 1]
            if not steps and body.action != "conferma":
                raise HTTPException(status_code=409, detail=f"Azione non coerente con lo stato attuale ({it['stato'].replace('_', ' ')})")
            if a["stato"] == "non_confermata":
                await set_asg(it, x["id"], {"stato": "confermata", "confirmed_at": _now(), "confirmed_via": "app"})
                await diary(inv["org_id"], inv["event_id"], oid, name, "conferma", f"{it['codice']}: presa in carico confermata da {name}", it, resource_id=x["id"])
            for stp in steps:
                it = await get_itv(inv["org_id"], inv["event_id"], iid)
                await transition(it, stp, oid, name, body.note if stp == target else None)
            if steps:
                await notify(inv["org_id"], inv["event_id"], "stato", f"{it['codice']}: {name} → {target.replace('_', ' ')}", "info", it)
        await bump(inv["org_id"], inv["event_id"])
        return {"ok": True, "at": _now()}

    @r.post(mb + "/interventions/{iid}/photo")
    async def m_photo(token: str, iid: str, file: UploadFile = File(...)):
        inv, x, (oid, name) = await mctx(token)
        it = await get_itv(inv["org_id"], inv["event_id"], iid)
        if it.get("reporter_invite") != inv["id"] and not any(a["resource_id"] == x["id"] and a["stato"] in ACTIVE_ASG for a in it.get("assignments") or []):
            raise HTTPException(status_code=403, detail="Puoi allegare foto solo alle tue segnalazioni o ai tuoi incarichi")
        data, mime = await read_upload(file)
        return await store_att(it, data, mime, oid, name, file.filename)

    @r.post(mb + "/messages")
    async def m_msg(token: str, body: MobileMsgIn):
        inv, x, (oid, name) = await mctx(token)
        await db.cr_messages.insert_one({"id": uuid.uuid4().hex, "org_id": inv["org_id"], "event_id": inv["event_id"], "at": _now(), "from_type": "op", "from_id": oid, "from_name": name,
                                         "to_type": "centrale", "to_label": "Control Room", "text": body.text, "recipients": [], "delivered": {}, "read": {}, "read_at": None})
        await notify(inv["org_id"], inv["event_id"], "messaggio", f"Messaggio da {name}: {body.text[:80]}", "info")
        await diary(inv["org_id"], inv["event_id"], oid, name, "comunicazione", f"Messaggio di {name} alla Control Room: {body.text[:120]}")
        await bump(inv["org_id"], inv["event_id"])
        return {"ok": True, "at": _now()}

    @r.post(mb + "/messages/read")
    async def m_read(token: str):
        inv, _, _ = await mctx(token)
        await db.cr_messages.update_many({"org_id": inv["org_id"], "event_id": inv["event_id"], "recipients": inv["id"], f"delivered.{inv['id']}": {"$exists": False}}, {"$set": {f"delivered.{inv['id']}": _now()}})
        await db.cr_messages.update_many({"org_id": inv["org_id"], "event_id": inv["event_id"], "recipients": inv["id"], f"read.{inv['id']}": {"$exists": False}}, {"$set": {f"read.{inv['id']}": _now()}})
        await db.cr_invites.update_one({"id": inv["id"]}, {"$set": {"last_notif_at": _now()}})
        await bump(inv["org_id"], inv["event_id"])
        return {"ok": True}

    @r.get(mb + "/interventions/{iid}/attachments/{aid}")
    async def m_att(token: str, iid: str, aid: str):
        inv, x, _ = await mctx(token)
        it = await get_itv(inv["org_id"], inv["event_id"], iid)
        if it.get("reporter_invite") != inv["id"] and not any(a["resource_id"] == x["id"] for a in it.get("assignments") or []):
            raise HTTPException(status_code=403, detail="Allegato non disponibile")
        return await send_att(it, aid)
