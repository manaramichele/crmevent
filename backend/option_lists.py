"""Gestione centralizzata dei menu a tendina personalizzabili (un'unica fonte dati: documento settings dell'organizzazione)."""
import re
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

PLATFORM_DEFAULTS_ID = "__platform_defaults__"

# key -> (gruppo, etichetta, [(collection, campo, is_array, filtro_extra)], sezione permesso per aggiungere dalle maschere)
NO_STATION = {"planner_station_id": {"$in": [None, ""]}}
LISTS = {
    "tipologie_evento": ("Eventi", "Tipologie evento", [("events", "tipologia", False, None)], "eventi"),
    "taglie": ("Staff e Volontari", "Taglie", [("persons", "taglia", False, None)], "staff"),
    "ruoli_staff": ("Staff e Volontari", "Mansioni / Attività", [("staff", "ruolo", False, None), ("shifts", "ruolo", False, None)], "staff"),
    "aree_operative": ("Staff e Volontari", "Aree operative", [("teams", "area", False, None), ("shifts", "area", False, NO_STATION), ("staff", "area", False, None)], "staff"),
    "settori": ("Aziende, Sponsor e Partner", "Settori aziende", [("companies", "settore", False, None)], "aziende"),
    "tipi_azienda": ("Aziende, Sponsor e Partner", "Tipi di azienda", [("companies", "tipo", False, None)], "aziende"),
    "livelli_sponsorship": ("Aziende, Sponsor e Partner", "Livelli sponsorship", [("deals", "livello", False, None)], "sponsor"),
    "esigenze_alimentari": ("Ospitalità e Pasti", "Esigenze alimentari", [("persons", "esigenze_alimentari", True, None), ("staff", "esigenze_alimentari", True, None)], "ospitalita"),
    "tipologie_struttura": ("Ospitalità e Pasti", "Tipologie struttura", [("structures", "tipologia", False, None)], "ospitalita"),
    "tipi_postazione": ("Event Planner", "Tipologie postazione", [("shifts", "area", False, {"planner_station_id": {"$nin": [None, ""]}})], "*"),
    "tipi_risorsa_persona": ("Control Room", "Tipologie risorsa persona", [("cr_resources", "tipologia", False, {"kind": "persona"})], "eventi"),
}
DEFAULTS = {
    "taglie": ["XS", "S", "M", "L", "XL", "XXL", "XXXL"],
    "esigenze_alimentari": ["Vegetariano", "Vegano", "Senza glutine", "Senza lattosio", "Allergie", "Intolleranze", "Altro"],
    "tipologie_struttura": ["Hotel", "B&B", "Residence", "Agriturismo", "Ristorante", "Pizzeria", "Bar", "Catering", "Mensa", "Altro"],
    "tipi_postazione": ["Ristoro", "Incrocio", "Partenza", "Arrivo", "Deposito borse", "Expo", "Area sponsor", "Sicurezza percorso", "Altro"],
    "tipi_risorsa_persona": ["Volontario", "Staff", "Sanitario", "Forze dell'ordine", "Altro"],
}
# Sezioni senza elenchi liberi: usano stati tecnici o anagrafiche strutturate.
TECHNICAL = {"Attività e Scadenze": "Tipi e stati di attività e follow-up sono stati tecnici del flusso di lavoro.",
             "Briefing": "Destinatari e stati provengono da anagrafiche (Team, persone) e regole di invio.",
             "Percorsi": "Percorsi e tracciati provengono dai file GPX caricati.",
             "Event Map": "Livelli e oggetti provengono dalla libreria Event Planner."}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").strip())


class ItemIn(BaseModel):
    value: str = Field(min_length=1, max_length=80)


class ListIn(BaseModel):
    items: List[str]
    disattivati: List[str] = []


class RenameIn(BaseModel):
    old: str
    new: str = Field(min_length=1, max_length=80)


def build(db, deps: dict):
    r = APIRouter(prefix="/api")
    require_admin = deps["require_admin"]
    get_settings = deps["get_settings"]
    allows = deps["allows"]

    def _key(key):
        if key not in LISTS:
            raise HTTPException(status_code=404, detail="Elenco non trovato")
        return key

    def _is_manager(user):
        return user.get("platform_scope") or (user.get("perm") or {}).get("admin")

    def _sid(user):
        return PLATFORM_DEFAULTS_ID if user.get("platform_scope") else user["org_id"]

    async def _doc(user):
        if user.get("platform_scope"):
            doc = await db.settings.find_one({"id": PLATFORM_DEFAULTS_ID}, {"_id": 0}) or {}
            base = deps["default_settings"]()
            return {**{k: list(DEFAULTS.get(k) or base.get(k) or []) for k in LISTS}, **{k: v for k, v in doc.items() if v}}
        return await get_settings(user)

    async def usage(user, key, value) -> int:
        if user.get("platform_scope"):
            return 0
        n = 0
        for coll, field, _, extra in LISTS[key][2]:
            n += await db[coll].count_documents({"org_id": user["org_id"], field: value, **(extra or {})})
        return n

    async def _save(user, key, items, dis):
        await db.settings.update_one({"id": _sid(user)}, {"$set": {key: items, f"disattivati.{key}": dis, "updated_at": _now()}}, upsert=True)

    @r.get("/settings/lists")
    async def lists_overview(user: dict = Depends(require_admin)):
        doc = await _doc(user)
        dis = doc.get("disattivati") or {}
        out = []
        for k, (group, label, _, _) in LISTS.items():
            items = doc.get(k) or []
            out.append({"key": k, "group": group, "label": label,
                        "items": [{"value": v, "active": v not in (dis.get(k) or []), "usage": await usage(user, k, v)} for v in items]})
        return {"lists": out, "technical": TECHNICAL, "can_manage": bool(_is_manager(user)), "platform": bool(user.get("platform_scope"))}

    @r.post("/settings/lists/{key}/items")
    async def add_item(key: str, body: ItemIn, user: dict = Depends(require_admin)):
        _key(key)
        sec = LISTS[key][3]
        perm = user.get("perm") or {}
        if not _is_manager(user) and not (sec == "*" or allows(perm, (sec,), "create") or allows(perm, (sec,), "edit")):
            raise HTTPException(status_code=403, detail="Non hai i permessi per aggiungere voci a questo elenco")
        doc = await _doc(user)
        items = list(doc.get(key) or [])
        dis = list((doc.get("disattivati") or {}).get(key) or [])
        v = _norm(body.value)
        hit = next((x for x in items if x.lower() == v.lower()), None)
        if hit:
            if hit in dis:
                dis.remove(hit)
                await _save(user, key, items, dis)
            return {"value": hit, "created": False, "items": items}
        items.append(v)
        await _save(user, key, items, dis)
        return {"value": v, "created": True, "items": items}

    @r.put("/settings/lists/{key}")
    async def update_list(key: str, body: ListIn, user: dict = Depends(require_admin)):
        _key(key)
        if not _is_manager(user):
            raise HTTPException(status_code=403, detail="Solo l'Admin Organizzazione può gestire gli elenchi")
        doc = await _doc(user)
        cur = list(doc.get(key) or [])
        items, seen = [], set()
        for x in body.items:
            v = _norm(x)
            if v and v.lower() not in seen:
                seen.add(v.lower())
                items.append(v)
        for removed in [x for x in cur if x not in items]:
            if await usage(user, key, removed):
                raise HTTPException(status_code=409, detail=f"\"{removed}\" è già utilizzata: puoi solo disattivarla")
        await _save(user, key, items, [x for x in body.disattivati if x in items])
        return {"ok": True}

    @r.post("/settings/lists/{key}/rename")
    async def rename_item(key: str, body: RenameIn, user: dict = Depends(require_admin)):
        _key(key)
        if not _is_manager(user):
            raise HTTPException(status_code=403, detail="Solo l'Admin Organizzazione può gestire gli elenchi")
        doc = await _doc(user)
        items = list(doc.get(key) or [])
        dis = list((doc.get("disattivati") or {}).get(key) or [])
        new = _norm(body.new)
        if body.old not in items:
            raise HTTPException(status_code=404, detail="Voce non trovata")
        if any(x.lower() == new.lower() and x != body.old for x in items):
            raise HTTPException(status_code=409, detail="Esiste già una voce con questo nome")
        items[items.index(body.old)] = new
        dis = [new if x == body.old else x for x in dis]
        await _save(user, key, items, dis)
        n = 0
        if not user.get("platform_scope"):
            for coll, field, arr, extra in LISTS[key][2]:
                q = {"org_id": user["org_id"], field: body.old, **(extra or {})}
                res = await (db[coll].update_many(q, {"$set": {f"{field}.$": new}}) if arr else db[coll].update_many(q, {"$set": {field: new}}))
                n += res.modified_count
        return {"ok": True, "records_updated": n}

    return {"router": r}


def merge_defaults(base: dict, platform: Optional[dict]) -> dict:
    out = {**base, **DEFAULTS, "disattivati": {}}
    for k in LISTS:
        if platform and platform.get(k):
            out[k] = list(platform[k])
    return out
