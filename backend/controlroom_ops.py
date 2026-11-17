"""Control Room (Fase 2): stato operativo evento, settori, postazioni, risorse (persone/mezzi/squadre), presenze, interventi base, revisioni per aggiornamenti live."""
import uuid
from datetime import datetime, timezone
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from fastapi import Body, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError

import event_routes as EVR
import permissions as P

ROME = ZoneInfo("Europe/Rome")
EVENT_STATES = ("preparazione", "in_corso", "sospeso", "terminato")
RES_STATES = ("disponibile", "impegnato", "fuori_servizio", "non_raggiungibile")
POST_CATEGORIES = [("volontari", "Volontari", "Users", "#0ABAB5"), ("ristoro", "Ristoro", "CupSoda", "#F59E0B"), ("spugnaggio", "Spugnaggio", "Droplets", "#0EA5E9"),
                   ("ambulanza", "Ambulanza", "Ambulance", "#DC2626"), ("sanitario", "Soccorso sanitario", "Cross", "#E11D48"), ("polizia", "Polizia", "Shield", "#1D4ED8"),
                   ("polizia_locale", "Polizia Locale", "BadgeCheck", "#2563EB"), ("protezione_civile", "Protezione Civile", "LifeBuoy", "#EA580C"),
                   ("viabilita", "Viabilità", "TrafficCone", "#CA8A04"), ("controllo", "Controllo percorso", "Flag", "#16A34A"), ("critico", "Punto critico", "TriangleAlert", "#B91C1C"),
                   ("vigili_fuoco", "Vigili del Fuoco", "Flame", "#C2410C"), ("chiusura", "Chiusura stradale", "Ban", "#475569"), ("altro", "Altro", "MapPin", "#64748B")]
VEHICLES = [("ambulanza", "Ambulanza"), ("automedica", "Automedica"), ("moto_soccorso", "Moto soccorso"), ("auto_org", "Auto organizzativa"), ("moto_org", "Moto organizzativa"),
            ("protezione_civile", "Mezzo Protezione Civile"), ("polizia", "Mezzo Polizia"), ("polizia_locale", "Mezzo Polizia Locale"), ("altro", "Altro")]
EXTERNAL_VEHICLES = {"protezione_civile", "polizia", "polizia_locale"}
Txt = Optional[str]


class SectorIn(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    codice: Txt = None
    km_inizio: Optional[float] = Field(None, ge=0, le=1000)
    km_fine: Optional[float] = Field(None, ge=0, le=1000)
    responsabile: Txt = None
    telefono: Txt = None
    colore: Txt = None
    note: Txt = None


class PostIn(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    codice: Txt = None
    categoria: str = "volontari"
    sector_id: Txt = None
    km: Optional[float] = Field(None, ge=0, le=1000)
    lng: Optional[float] = Field(None, ge=-180, le=180)
    lat: Optional[float] = Field(None, ge=-90, le=90)
    responsabile: Txt = None
    telefono: Txt = None
    apertura: Txt = None
    chiusura: Txt = None
    previsti: int = Field(0, ge=0, le=10000)
    presenti_manuali: int = Field(0, ge=0, le=10000)
    attiva: bool = True
    note: Txt = None


class ResourceIn(BaseModel):
    kind: Literal["persona", "mezzo", "squadra"] = "persona"
    codice: Txt = None
    nome: Txt = None
    tipologia: Txt = None
    responsabile: Txt = None
    telefono: Txt = None
    post_id: Txt = None
    sector_id: Txt = None
    turno: Txt = None
    shift_id: Txt = None
    stato: Literal[RES_STATES] = "disponibile"
    persona_id: Txt = None
    caposquadra: bool = False
    targa: Txt = None
    equipaggio: Txt = None
    autorizzazione_ente: bool = False
    gps_device_id: Txt = None
    gps_device_type: Optional[Literal["tracker", "smartphone"]] = None
    lng: Optional[float] = Field(None, ge=-180, le=180)
    lat: Optional[float] = Field(None, ge=-90, le=90)
    note: Txt = None


class InterventionIn(BaseModel):
    titolo: str = Field(min_length=1, max_length=160)
    priorita: Literal["normale", "urgente"] = "normale"
    descrizione: Txt = None
    post_id: Txt = None
    km: Optional[float] = Field(None, ge=0, le=1000)
    lng: Optional[float] = Field(None, ge=-180, le=180)
    lat: Optional[float] = Field(None, ge=-90, le=90)
    stato: Literal["aperto", "chiuso"] = "aperto"


class CategoryIn(BaseModel):
    key: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=60)
    icon: str = "MapPin"
    color: str = "#64748B"


class SettingsIn(BaseModel):
    status: Optional[Literal[EVENT_STATES]] = None
    responsabile: Txt = None
    responsabile_tel: Txt = None
    route_map_id: Txt = None
    categories: Optional[list[CategoryIn]] = None
    version: int


class PresenceIn(BaseModel):
    presente: bool


class PositionIn(BaseModel):
    lng: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    version: int


class StatusIn(BaseModel):
    stato: Literal[RES_STATES]
    version: int


class FromStaffIn(BaseModel):
    staff_ids: list[str] = Field(min_length=1, max_length=500)
    post_id: Txt = None
    sector_id: Txt = None
    shift_id: Txt = None
    caposquadra_staff_id: Txt = None


KINDS = {"sectors": ("cr_sectors", SectorIn, "settore"), "posts": ("cr_posts", PostIn, "postazione"),
         "resources": ("cr_resources", ResourceIn, "risorsa"), "interventions": ("cr_interventions", InterventionIn, "intervento")}
PHONE_FIELDS = ("telefono", "responsabile_tel")


def _now():
    return datetime.now(timezone.utc).isoformat()


def toform(cur):
    g = cur.get("gps") or {}
    return {**cur, "gps_device_id": g.get("device_id"), "gps_device_type": g.get("device_type")}


def _clean(d):
    return {k: v for k, v in d.items() if k not in ("_id", "org_id")}


def attach(r, db, deps, require_active):
    ops_dep = deps["require_admin"]
    base = "/controlroom/events/{event_id}/ops"

    def perms(u):
        p = u.get("perm") or {"admin": True}
        return {"view": P.allows(p, ("eventi", "staff"), "view"), "edit": P.allows(p, ("staff",), "edit"),
                "contacts": P.allows(p, ("staff", "anagrafiche"), "view")}

    async def ctx(u, eid, write=False):
        pm = perms(u)
        if not pm["view"] or (write and not pm["edit"]):
            raise HTTPException(status_code=403, detail="Non hai i permessi per modificare la Control Room" if write else "Non hai accesso alla Control Room")
        ev = await db.events.find_one({"org_id": u["org_id"], "id": eid}, {"_id": 0, "id": 1, "nome": 1, "data_inizio": 1, "data_fine": 1, "ora_inizio": 1, "citta": 1})
        if not ev:
            raise HTTPException(status_code=404, detail="Evento non trovato")
        await require_active(u["org_id"], eid)
        return ev, pm

    def q(u, eid, **x):
        return {"org_id": u["org_id"], "event_id": eid, **x}

    async def settings(u, eid):
        s = await db.cr_settings.find_one(q(u, eid), {"_id": 0})
        if not s:
            s = {"org_id": u["org_id"], "event_id": eid, "status": "preparazione", "responsabile": None, "responsabile_tel": None, "route_map_id": None,
                 "categories": [{"key": k, "label": lbl, "icon": i, "color": c} for k, lbl, i, c in POST_CATEGORIES], "version": 1, "rev": 1, "created_at": _now()}
            await db.cr_settings.update_one(q(u, eid), {"$setOnInsert": s}, upsert=True)
            s = await db.cr_settings.find_one(q(u, eid), {"_id": 0})
        return s

    async def touch(u, eid, action, entity, eid_obj=None, label=""):
        await db.cr_settings.update_one(q(u, eid), {"$inc": {"rev": 1}})
        await db.cr_log.insert_one({"id": uuid.uuid4().hex, "org_id": u["org_id"], "event_id": eid, "at": _now(), "by": u.get("name") or u.get("email"),
                                    "action": action, "entity": entity, "entity_id": eid_obj, "label": label})

    def conflict():
        return HTTPException(status_code=409, detail="Dato modificato nel frattempo da un altro operatore: ricarico la versione più recente")

    async def check_refs(u, eid, data):
        for fld, coll in (("sector_id", "cr_sectors"), ("post_id", "cr_posts")):
            if data.get(fld) and not await db[coll].find_one(q(u, eid, id=data[fld]), {"_id": 1}):
                raise HTTPException(status_code=400, detail="Settore o postazione non validi")
        if data.get("shift_id") and not await db.shifts.find_one({"org_id": u["org_id"], "evento_id": eid, "id": data["shift_id"]}, {"_id": 1}):
            raise HTTPException(status_code=400, detail="Turno non valido")

    async def validate(u, eid, kind, data, cur=None):
        if kind == "sectors" and data.get("km_inizio") is not None and data.get("km_fine") is not None and data["km_fine"] < data["km_inizio"]:
            raise HTTPException(status_code=400, detail="Il chilometro finale deve essere successivo a quello iniziale")
        if kind == "posts":
            s = await settings(u, eid)
            if data["categoria"] not in {c["key"] for c in s["categories"]}:
                raise HTTPException(status_code=400, detail="Categoria non valida")
        if kind == "resources":
            if data["kind"] == "mezzo":
                if data.get("tipologia") not in {k for k, _ in VEHICLES}:
                    raise HTTPException(status_code=400, detail="Categoria mezzo non valida")
                if data["tipologia"] in EXTERNAL_VEHICLES and not data.get("autorizzazione_ente"):
                    raise HTTPException(status_code=400, detail="Conferma l'autorizzazione dell'ente per registrare un mezzo esterno")
            if data.get("persona_id"):
                if not await db.staff.find_one({"org_id": u["org_id"], "evento_id": eid, "persona_id": data["persona_id"]}, {"_id": 1}):
                    raise HTTPException(status_code=400, detail="La persona non è registrata in Staff / Volontari per questo evento")
                dup = await db.cr_resources.find_one(q(u, eid, persona_id=data["persona_id"], id={"$ne": (cur or {}).get("id")}), {"_id": 1})
                if dup:
                    raise HTTPException(status_code=409, detail="Questa persona è già una risorsa della Control Room")
            elif data["kind"] == "persona" and not (data.get("nome") or "").strip():
                raise HTTPException(status_code=400, detail="Indica il nome della risorsa")
            if data["kind"] == "mezzo" and not (data.get("codice") or data.get("nome")):
                raise HTTPException(status_code=400, detail="Indica l'identificativo del mezzo")
        await check_refs(u, eid, data)

    def gps_of(data, prev=None):
        g = (prev or {}).get("gps") or {}
        dev = data.pop("gps_device_id", None)
        typ = data.pop("gps_device_type", None)
        if not dev:
            return None
        # Fase 2: solo associazione; posizione/ultimo aggiornamento arriveranno da dispositivi reali (mai simulati)
        same = g.get("device_id") == dev
        return {"device_id": dev, "device_type": typ, "status": g.get("status") if same else "non_collegato",
                "last_lng": g.get("last_lng") if same else None, "last_lat": g.get("last_lat") if same else None, "last_at": g.get("last_at") if same else None}

    def presidio(p, presenti, ev_status, now_hm):
        prev = p.get("previsti") or 0
        if not p.get("attiva", True):
            return "non_attiva"
        if presenti and presenti >= prev:
            return "presidiata"
        if presenti:
            return "parziale"
        if ev_status == "preparazione" or (p.get("apertura") and now_hm < p["apertura"]):
            return "in_attesa"
        return "non_presidiata"

    @r.get(base)
    async def state(event_id: str, u: dict = Depends(ops_dep)):
        ev, pm = await ctx(u, event_id)
        s = await settings(u, event_id)
        sectors = await db.cr_sectors.find(q(u, event_id), {"_id": 0, "org_id": 0}).sort("km_inizio", 1).to_list(500)
        posts = await db.cr_posts.find(q(u, event_id), {"_id": 0, "org_id": 0}).sort("km", 1).to_list(2000)
        res = await db.cr_resources.find(q(u, event_id), {"_id": 0, "org_id": 0}).sort("created_at", 1).to_list(5000)
        itv = await db.cr_interventions.find(q(u, event_id), {"_id": 0, "org_id": 0}).sort("created_at", -1).to_list(1000)
        log = await db.cr_log.find(q(u, event_id), {"_id": 0, "org_id": 0}).sort("at", -1).to_list(40)
        pids = [x["persona_id"] for x in res if x.get("persona_id")]
        pers = {p["id"]: p for p in await db.persons.find({"org_id": u["org_id"], "id": {"$in": pids}}, {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "cellulare": 1, "telefono": 1}).to_list(5000)}
        shifts = {x["id"]: x for x in await db.shifts.find({"org_id": u["org_id"], "evento_id": event_id}, {"_id": 0, "id": 1, "data": 1, "ora_inizio": 1, "ora_fine": 1}).to_list(5000)}
        for x in res:
            p = pers.get(x.get("persona_id"))
            if p:
                x["nome"] = f"{p.get('nome') or ''} {p.get('cognome') or ''}".strip()
                x["telefono"] = p.get("cellulare") or p.get("telefono")
            sh = shifts.get(x.get("shift_id"))
            x["turno_label"] = " ".join(v for v in ((sh or {}).get("data"), "-".join(v for v in ((sh or {}).get("ora_inizio"), (sh or {}).get("ora_fine")) if v)) if v) if sh else x.get("turno")
        now_hm = datetime.now(ROME).strftime("%H:%M")
        for p in posts:
            ppl = [x for x in res if x.get("post_id") == p["id"] and x["kind"] == "persona"]
            p["presenti"] = sum(1 for x in ppl if x.get("presente")) + (p.get("presenti_manuali") or 0)
            p["assegnati"] = len(ppl)
            p["mancanti"] = max((p.get("previsti") or 0) - p["presenti"], 0)
            p["presidio"] = presidio(p, p["presenti"], s["status"], now_hm)
        for sc in sectors:
            sp = [p for p in posts if p.get("sector_id") == sc["id"]]
            spids = {p["id"] for p in sp}
            inside = [x for x in res if x.get("sector_id") == sc["id"] or x.get("post_id") in spids]
            sc["summary"] = {"postazioni": len(sp), "volontari": sum(1 for x in inside if x["kind"] == "persona"),
                             "presenti": sum(p["presenti"] for p in sp), "mezzi": sum(1 for x in inside if x["kind"] == "mezzo"),
                             "mezzi_disponibili": sum(1 for x in inside if x["kind"] == "mezzo" and x["stato"] == "disponibile")}
        open_itv = [i for i in itv if i["stato"] != "chiuso"]
        mezzi = [x for x in res if x["kind"] == "mezzo"]
        kpi = {"volontari_presenti": sum(1 for x in res if x["kind"] == "persona" and x.get("presente")) + sum(p.get("presenti_manuali") or 0 for p in posts),
               "postazioni_presidiate": sum(1 for p in posts if p["presidio"] == "presidiata"), "postazioni_attive": sum(1 for p in posts if p["presidio"] != "non_attiva"),
               "ambulanze_disponibili": sum(1 for x in mezzi if x.get("tipologia") == "ambulanza" and x["stato"] == "disponibile"),
               "mezzi_operativi": sum(1 for x in mezzi if x["stato"] in ("disponibile", "impegnato")), "risorse_impegnate": sum(1 for x in res if x["stato"] == "impegnato"),
               "non_raggiungibili": sum(1 for x in res if x["stato"] == "non_raggiungibile"), "interventi_aperti": len(open_itv),
               "interventi_urgenti": sum(1 for i in open_itv if i["priorita"] == "urgente")}
        alerts = ([{"level": "high", "text": f"Intervento urgente: {i['titolo']}", "ref": ["interventions", i["id"]]} for i in open_itv if i["priorita"] == "urgente"]
                  + [{"level": "high", "text": f"{p['nome']}: postazione non presidiata", "ref": ["posts", p["id"]]} for p in posts if p["presidio"] == "non_presidiata"]
                  + [{"level": "mid", "text": f"{p['nome']}: mancano {p['mancanti']} operatori", "ref": ["posts", p["id"]]} for p in posts if p["presidio"] == "parziale"]
                  + [{"level": "mid", "text": f"{x.get('nome') or x.get('codice')}: non raggiungibile", "ref": ["resources", x["id"]]} for x in res if x["stato"] == "non_raggiungibile"])
        if not pm["contacts"]:
            for row in [s, *sectors, *posts, *res]:
                for f in PHONE_FIELDS:
                    if row.get(f):
                        row[f] = None
                        row["contatti_nascosti"] = True
        routes = EVR.public(await EVR.list_routes(db, u["org_id"], event_id, deps["resolve_attachment"]))
        return {"event": ev, "settings": _clean(s), "sectors": sectors, "posts": posts, "resources": res, "interventions": itv, "log": log, "kpi": kpi, "alerts": alerts,
                "routes": routes, "vehicles": [{"key": k, "label": lbl} for k, lbl in VEHICLES], "external_vehicles": sorted(EXTERNAL_VEHICLES),
                "perms": {"edit": pm["edit"], "contacts": pm["contacts"]}, "rev": s.get("rev", 1), "server_time": _now()}

    @r.get(base + "/rev")
    async def rev(event_id: str, u: dict = Depends(ops_dep)):
        await ctx(u, event_id)
        return {"rev": (await settings(u, event_id)).get("rev", 1)}

    @r.get(base + "/route")
    async def route(event_id: str, map_id: Optional[str] = None, u: dict = Depends(ops_dep)):
        await ctx(u, event_id)
        routes = await EVR.list_routes(db, u["org_id"], event_id, deps["resolve_attachment"])
        rt = next((x for x in routes if x["map_id"] == map_id), None) if map_id else next((x for x in routes if x["format"] == "GPX"), None) or (routes[0] if routes else None)
        if not rt:
            return {"route": None}
        data, _ = await deps["read_file_rec"](rt["_rec"])
        try:
            c = EVR.coords(data, rt["filename"])
        except Exception:
            raise HTTPException(status_code=400, detail=f"Percorso {rt['format']} non leggibile")
        return {"route": {"map_id": rt["map_id"], "nome": rt["nome"], "coordinates": [[p[0], p[1]] for p in c]}}

    @r.put(base + "/settings")
    async def put_settings(event_id: str, body: SettingsIn, u: dict = Depends(ops_dep)):
        await ctx(u, event_id, write=True)
        cur = await settings(u, event_id)
        upd = {k: v for k, v in body.model_dump(exclude={"version"}, exclude_unset=True).items()}
        if "categories" in upd:
            keys = [c["key"] for c in upd["categories"]]
            used = set(await db.cr_posts.distinct("categoria", q(u, event_id)))
            if len(set(keys)) != len(keys) or not keys or used - set(keys):
                raise HTTPException(status_code=400, detail="Categorie non valide: chiavi duplicate o categoria ancora usata da una postazione")
        if body.responsabile_tel is None and "responsabile_tel" in upd and not perms(u)["contacts"]:
            upd.pop("responsabile_tel")
        res = await db.cr_settings.update_one(q(u, event_id, version=body.version), {"$set": {**upd, "updated_at": _now(), "updated_by": u.get("email")}, "$inc": {"version": 1}})
        if not res.matched_count:
            raise conflict()
        if "status" in upd and upd["status"] != cur["status"]:
            await deps["audit"](u, "controlroom_status", detail=f"{event_id} · {upd['status']}")
        await touch(u, event_id, "update", "impostazioni", None, ", ".join(upd))
        return {"ok": True}

    @r.get(base + "/staff")
    async def staff(event_id: str, u: dict = Depends(ops_dep)):
        await ctx(u, event_id, write=True)
        tids = (u.get("perm") or {}).get("team_ids")
        sq = {"org_id": u["org_id"], "evento_id": event_id}
        if tids is not None:
            sq["team_id"] = {"$in": list(tids) + [None, ""]}
        rows = await db.staff.find(sq, {"_id": 0, "id": 1, "persona_id": 1, "categoria": 1, "ruolo": 1, "team_id": 1, "stato": 1}).to_list(5000)
        pers = {p["id"]: p for p in await db.persons.find({"org_id": u["org_id"], "id": {"$in": [x["persona_id"] for x in rows]}},
                                                          {"_id": 0, "id": 1, "nome": 1, "cognome": 1}).to_list(5000)}
        teams = {t["id"]: t["nome"] for t in await db.teams.find({"org_id": u["org_id"], "evento_id": event_id}, {"_id": 0, "id": 1, "nome": 1}).to_list(1000)}
        used = set(await db.cr_resources.distinct("persona_id", q(u, event_id)))
        shifts = await db.shifts.find({"org_id": u["org_id"], "evento_id": event_id}, {"_id": 0, "id": 1, "persona_id": 1, "data": 1, "ora_inizio": 1, "ora_fine": 1, "luogo": 1}).to_list(5000)
        out = [{"staff_id": x["id"], "persona_id": x["persona_id"], "nome": f"{(pers.get(x['persona_id']) or {}).get('nome') or ''} {(pers.get(x['persona_id']) or {}).get('cognome') or ''}".strip(),
                "categoria": x.get("categoria"), "ruolo": x.get("ruolo"), "team": teams.get(x.get("team_id")), "stato": x.get("stato"), "in_control_room": x["persona_id"] in used}
               for x in rows if x.get("persona_id") in pers]
        return {"staff": sorted(out, key=lambda x: x["nome"].lower()), "shifts": shifts}

    @r.post(base + "/resources/from-staff")
    async def from_staff(event_id: str, body: FromStaffIn, u: dict = Depends(ops_dep)):
        await ctx(u, event_id, write=True)
        await check_refs(u, event_id, body.model_dump())
        tids = (u.get("perm") or {}).get("team_ids")
        rows = await db.staff.find({"org_id": u["org_id"], "evento_id": event_id, "id": {"$in": body.staff_ids}}, {"_id": 0}).to_list(500)
        if tids is not None:
            rows = [x for x in rows if not x.get("team_id") or x["team_id"] in tids]
        used = set(await db.cr_resources.distinct("persona_id", q(u, event_id)))
        added = 0
        for x in rows:
            if not x.get("persona_id") or x["persona_id"] in used:
                continue
            used.add(x["persona_id"])
            await db.cr_resources.insert_one({"id": uuid.uuid4().hex, "org_id": u["org_id"], "event_id": event_id, "kind": "persona", "persona_id": x["persona_id"], "staff_id": x["id"],
                                              "tipologia": "Volontario" if x.get("categoria") == "volontario" else "Staff", "post_id": body.post_id, "sector_id": body.sector_id,
                                              "shift_id": body.shift_id, "caposquadra": x["id"] == body.caposquadra_staff_id, "stato": "disponibile", "presente": False, "gps": None,
                                              "version": 1, "created_at": _now(), "created_by": u.get("email"), "updated_at": _now(), "updated_by": u.get("email")})
            added += 1
        if added:
            await touch(u, event_id, "create", "risorsa", None, f"{added} da Staff / Volontari")
        return {"added": added}

    @r.post(base + "/resources/{oid}/presence")
    async def presence(event_id: str, oid: str, body: PresenceIn, u: dict = Depends(ops_dep)):
        await ctx(u, event_id, write=True)
        res = await db.cr_resources.update_one(q(u, event_id, id=oid, kind="persona"), {"$set": {"presente": body.presente, "presente_at": _now() if body.presente else None, "presente_by": u.get("email")},
                                                                         "$inc": {"version": 1}})
        if not res.matched_count:
            raise HTTPException(status_code=404, detail="Risorsa non trovata")
        await touch(u, event_id, "presence", "risorsa", oid, "presente" if body.presente else "assente")
        return {"ok": True}

    @r.patch(base + "/resources/{oid}/status")
    async def set_status(event_id: str, oid: str, body: StatusIn, u: dict = Depends(ops_dep)):
        await ctx(u, event_id, write=True)
        res = await db.cr_resources.update_one(q(u, event_id, id=oid, version=body.version), {"$set": {"stato": body.stato, "updated_at": _now(), "updated_by": u.get("email")}, "$inc": {"version": 1}})
        if not res.matched_count:
            raise conflict() if await db.cr_resources.find_one(q(u, event_id, id=oid), {"_id": 1}) else HTTPException(status_code=404, detail="Risorsa non trovata")
        await touch(u, event_id, "status", "risorsa", oid, body.stato)
        return {"ok": True}

    @r.patch(base + "/posts/{oid}/position")
    async def move_post(event_id: str, oid: str, body: PositionIn, u: dict = Depends(ops_dep)):
        await ctx(u, event_id, write=True)
        res = await db.cr_posts.update_one(q(u, event_id, id=oid, version=body.version), {"$set": {"lng": body.lng, "lat": body.lat, "updated_at": _now(), "updated_by": u.get("email")}, "$inc": {"version": 1}})
        if not res.matched_count:
            raise conflict() if await db.cr_posts.find_one(q(u, event_id, id=oid), {"_id": 1}) else HTTPException(status_code=404, detail="Postazione non trovata")
        await touch(u, event_id, "move", "postazione", oid, f"{body.lat:.5f}, {body.lng:.5f}")
        return {"ok": True}

    @r.post(base + "/posts/{oid}/duplicate")
    async def duplicate_post(event_id: str, oid: str, u: dict = Depends(ops_dep)):
        await ctx(u, event_id, write=True)
        p = await db.cr_posts.find_one(q(u, event_id, id=oid), {"_id": 0})
        if not p:
            raise HTTPException(status_code=404, detail="Postazione non trovata")
        doc = {**p, "id": uuid.uuid4().hex, "nome": f"{p['nome']} (copia)"[:120], "codice": f"{p['codice']}-2" if p.get("codice") else None, "presenti_manuali": 0,
               "version": 1, "created_at": _now(), "created_by": u.get("email"), "updated_at": _now(), "updated_by": u.get("email")}
        if p.get("lng") is not None:
            doc["lng"] = p["lng"] + 0.0003
        await db.cr_posts.insert_one({**doc})
        await touch(u, event_id, "create", "postazione", doc["id"], doc["nome"])
        return _clean(doc)

    def kind_of(kind):
        if kind not in KINDS:
            raise HTTPException(status_code=404, detail="Elemento non trovato")
        return KINDS[kind]

    def parse(model, body):
        try:
            return model(**(body or {})).model_dump()
        except ValidationError as e:
            raise HTTPException(status_code=422, detail="Dati non validi: " + "; ".join(f"{'.'.join(map(str, x['loc']))} {x['msg']}" for x in e.errors()))

    @r.post(base + "/{kind}")
    async def create(event_id: str, kind: str, body: dict = Body(...), u: dict = Depends(ops_dep)):
        coll, model, label = kind_of(kind)
        await ctx(u, event_id, write=True)
        data = parse(model, body)
        await validate(u, event_id, kind, data)
        if kind == "resources":
            data["gps"] = gps_of(data)
            data["presente"] = False
        doc = {**data, "id": uuid.uuid4().hex, "org_id": u["org_id"], "event_id": event_id, "version": 1, "created_at": _now(), "created_by": u.get("email"),
               "updated_at": _now(), "updated_by": u.get("email")}
        await db[coll].insert_one({**doc})
        await touch(u, event_id, "create", label, doc["id"], data.get("nome") or data.get("titolo") or data.get("codice") or "")
        return _clean(doc)

    @r.put(base + "/{kind}/{oid}")
    async def update(event_id: str, kind: str, oid: str, body: dict = Body(...), u: dict = Depends(ops_dep)):
        coll, model, label = kind_of(kind)
        _, pm = await ctx(u, event_id, write=True)
        cur = await db[coll].find_one(q(u, event_id, id=oid), {"_id": 0})
        if not cur:
            raise HTTPException(status_code=404, detail="Elemento non trovato")
        version = body.get("version")
        data = parse(model, {k: v for k, v in {**toform(cur), **body}.items() if k in model.model_fields})
        if not pm["contacts"]:
            for f in PHONE_FIELDS:
                if f in data and not data[f]:
                    data[f] = cur.get(f)
        await validate(u, event_id, kind, data, cur)
        if kind == "resources":
            data["gps"] = gps_of(data, cur)
            if cur.get("persona_id"):
                data["persona_id"], data["nome"], data["telefono"] = cur["persona_id"], None, None
        if kind == "interventions" and data["stato"] == "chiuso" and cur["stato"] != "chiuso":
            data["chiuso_at"], data["chiuso_by"] = _now(), u.get("email")
        res = await db[coll].update_one(q(u, event_id, id=oid, version=version), {"$set": {**data, "updated_at": _now(), "updated_by": u.get("email")}, "$inc": {"version": 1}})
        if not res.matched_count:
            raise conflict()
        await touch(u, event_id, "update", label, oid, data.get("nome") or data.get("titolo") or data.get("codice") or cur.get("nome") or "")
        return {"ok": True}

    @r.delete(base + "/{kind}/{oid}")
    async def delete(event_id: str, kind: str, oid: str, u: dict = Depends(ops_dep)):
        coll, _, label = kind_of(kind)
        await ctx(u, event_id, write=True)
        cur = await db[coll].find_one_and_delete(q(u, event_id, id=oid), {"_id": 0})
        if not cur:
            raise HTTPException(status_code=404, detail="Elemento non trovato")
        if kind == "posts":
            await db.cr_resources.update_many(q(u, event_id, post_id=oid), {"$set": {"post_id": None}, "$inc": {"version": 1}})
        if kind == "sectors":
            for c in ("cr_posts", "cr_resources"):
                await db[c].update_many(q(u, event_id, sector_id=oid), {"$set": {"sector_id": None}, "$inc": {"version": 1}})
        await touch(u, event_id, "delete", label, oid, cur.get("nome") or cur.get("titolo") or cur.get("codice") or "")
        return {"ok": True}
