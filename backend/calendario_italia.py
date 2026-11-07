"""Calendario Eventi Italia (Super Admin) — Fase 1: eventi, organizzatori, deduplicazione, import/export, dashboard.
Archivio separato (collezioni cal_*): nessun legame con eventi/anagrafiche delle organizzazioni clienti. Nessun invio email."""
import asyncio
import csv
import difflib
import io
import json
import re
import uuid
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import cal_feeds
from iscritti import _norm, read_rows

DISCIPLINE = {"running": ["10 km", "Mezza maratona", "Maratona", "Altro"], "trail": ["Trail", "Ultra trail", "Skyrunning"],
              "triathlon": ["Sprint", "Olimpico", "Medio", "Lungo", "Ironman", "70.3"]}
STATI_EVENTO = ["confermata", "da_verificare", "rinviata", "annullata", "conclusa"]
STATI_COMM = ["da_qualificare", "contatto_da_verificare", "pronto_campagna", "invio_programmato", "inviato", "contattato", "interessato",
              "demo_richiesta", "cliente_acquisito", "escluso"]
PRIVACY = ["da_verificare", "idoneo", "non_idoneo", "disiscritto", "opposizione"]
TIPI_ORG = ["ASD", "SSD", "societa", "ente", "agenzia", "altro"]
SOURCES = [
    ("fidal", "FIDAL", "running", "https://www.fidal.it"), ("raceup", "RaceUp", "running", "https://www.raceup.org"),
    ("wedosport", "Wedosport", "trail", "https://www.wedosport.net"), ("runningaround", "Running Around", "trail", "https://www.runningaround.it"),
    ("fitri", "FITRI", "triathlon", "https://www.fitri.it"), ("myfitri", "MyFITRI", "triathlon", "https://www.myfitri.it"),
    ("ironman", "Ironman (calendario ufficiale)", "triathlon", "https://www.ironman.com/races"), ("manuale", "Importazione manuale", "*", ""),
]
EVENT_FIELDS = ["nome", "disciplina", "specialita", "distanza", "edizione", "anno", "data_inizio", "data_fine", "regione", "provincia", "comune",
                "indirizzo", "lat", "lng", "sito_web", "pagina_iscrizioni", "email", "telefono", "partecipanti", "note", "organizzatore"]
LABELS = {"nome": ["nome", "manifestazione", "evento", "gara", "titolo"], "disciplina": ["disciplina", "sport"], "specialita": ["specialita", "tipo"],
          "distanza": ["distanza", "km"], "edizione": ["edizione"], "anno": ["anno"], "data_inizio": ["data", "data inizio", "inizio", "data evento"],
          "data_fine": ["data fine", "fine"], "regione": ["regione"], "provincia": ["provincia", "prov"], "comune": ["comune", "citta", "localita", "luogo"],
          "indirizzo": ["indirizzo"], "sito_web": ["sito", "sito web", "web", "url"], "pagina_iscrizioni": ["iscrizioni", "pagina iscrizioni"],
          "email": ["email", "e mail", "mail"], "telefono": ["telefono", "tel"], "partecipanti": ["partecipanti", "iscritti"], "note": ["note"],
          "organizzatore": ["organizzatore", "societa", "organizzazione", "asd"], "ext_id": ["id", "codice", "id fonte"]}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _d(v) -> Optional[str]:
    s = str(v or "").strip()[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _domain(u) -> str:
    u = str(u or "").strip().lower()
    if not u:
        return ""
    return urlparse(u if "://" in u else f"http://{u}").netloc.removeprefix("www.")


def _name_key(n) -> str:
    return re.sub(r"\b(19|20)\d{2}\b|\b\d+(a|ª|°)?\s*edizione\b", " ", _norm(n)).strip()


def _disc(v) -> str:
    s = _norm(v)
    if "tri" in s or "ironman" in s or "70 3" in s:
        return "triathlon"
    if "trail" in s or "sky" in s:
        return "trail"
    return "running" if s else ""


def score(a: dict, b: dict) -> float:
    """Somiglianza 0..1 tra due eventi. Anni diversi => 0 (mai confondere edizioni)."""
    if a.get("anno") and b.get("anno") and int(a["anno"]) != int(b["anno"]):
        return 0.0
    s = difflib.SequenceMatcher(None, _name_key(a.get("nome")), _name_key(b.get("nome"))).ratio() * 0.45
    if a.get("data_inizio") and a.get("data_inizio") == b.get("data_inizio"):
        s += 0.25
    if _norm(a.get("comune")) and _norm(a.get("comune")) == _norm(b.get("comune")):
        s += 0.12
    elif _norm(a.get("provincia")) and _norm(a.get("provincia")) == _norm(b.get("provincia")):
        s += 0.05
    if a.get("disciplina") and a.get("disciplina") == b.get("disciplina"):
        s += 0.06
    if _norm(a.get("distanza")) and _norm(a.get("distanza")) == _norm(b.get("distanza")):
        s += 0.04
    if _domain(a.get("sito_web")) and _domain(a.get("sito_web")) == _domain(b.get("sito_web")):
        s += 0.08
    return round(min(s, 1.0), 3)


def comm_date(ev: dict, days: int) -> Optional[str]:
    """Data prevista comunicazione: solo per eventi confermati/conclusi senza date in conflitto."""
    end = ev.get("data_fine") or ev.get("data_inizio")
    if not end or ev.get("stato") not in ("confermata", "conclusa") or ev.get("data_da_verificare"):
        return None
    return (date.fromisoformat(end) + timedelta(days=int(days))).isoformat()


class EventIn(BaseModel):
    nome: str = Field(min_length=2, max_length=200)
    disciplina: str = "running"
    specialita: Optional[str] = None
    distanza: Optional[str] = None
    edizione: Optional[str] = None
    anno: Optional[int] = None
    data_inizio: Optional[str] = None
    data_fine: Optional[str] = None
    regione: Optional[str] = None
    provincia: Optional[str] = None
    comune: Optional[str] = None
    indirizzo: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    sito_web: Optional[str] = None
    pagina_iscrizioni: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    partecipanti: Optional[int] = None
    note: Optional[str] = None
    stato: str = "da_verificare"
    stato_commerciale: str = "da_qualificare"
    organizer_id: Optional[str] = None


class OrganizerIn(BaseModel):
    nome: str = Field(min_length=2, max_length=200)
    ragione_sociale: Optional[str] = None
    tipologia: str = "altro"
    regione: Optional[str] = None
    provincia: Optional[str] = None
    comune: Optional[str] = None
    sito_web: Optional[str] = None
    email_generale: Optional[str] = None
    email_organizzativa: Optional[str] = None
    telefono: Optional[str] = None
    cellulare: Optional[str] = None
    referente: Optional[str] = None
    note_commerciali: Optional[str] = None
    stato_commerciale: str = "da_qualificare"
    escluso_campagne: bool = False


class PrivacyIn(BaseModel):
    status: str
    fonte: Optional[str] = None
    data_acquisizione: Optional[str] = None
    tipo_indirizzo: Optional[str] = None
    finalita: Optional[str] = None
    base_giuridica: Optional[str] = None
    consenso: Optional[bool] = None
    consenso_data: Optional[str] = None
    consenso_prova: Optional[str] = None
    note: Optional[str] = None


class MergeIn(BaseModel):
    keep_id: str
    merge_ids: list[str]


class ResolveIn(BaseModel):
    action: str


class VerificaIn(BaseModel):
    esito: str
    metodo: Optional[str] = None
    prova: Optional[str] = None
    note: Optional[str] = None


class ConnIn(BaseModel):
    feed_url: str = Field(min_length=8, max_length=1000)
    formato: str = "csv"
    attiva: bool = True


class FonteIn(BaseModel):
    nome: str = Field(min_length=2, max_length=120)
    disciplina: str = "running"
    url: Optional[str] = None
    feed_url: str = Field(min_length=8, max_length=1000)
    formato: str = "csv"
    metodo: str = Field(min_length=3, max_length=300)
    prova: str = Field(min_length=3, max_length=1000)
    note: Optional[str] = None


class SettingsIn(BaseModel):
    giorni_post_evento: int = Field(7, ge=1, le=90)
    intervallo_min_giorni: int = Field(60, ge=1, le=365)
    modalita_invio: str = "manuale"
    raccolta_automatica: bool = False
    orario_sync: str = "03:00"


def build(db, deps: dict):
    r = APIRouter(prefix="/api/platform/cal")
    sa = deps["require_superadmin"]
    audit = deps["record_audit"]

    async def ensure_indexes():
        await db.cal_events.create_index("id", unique=True)
        await db.cal_events.create_index([("anno", 1), ("data_inizio", 1)])
        await db.cal_events.create_index([("sources.source", 1), ("sources.ext_id", 1)])
        await db.cal_organizers.create_index("id", unique=True)
        await db.cal_organizers.create_index("nome_key")
        await db.cal_duplicates.create_index([("a", 1), ("b", 1)], unique=True)
        await db.cal_history.create_index([("entity_id", 1), ("at", -1)])

    async def settings() -> dict:
        s = await db.cal_settings.find_one({"id": "main"}, {"_id": 0}) or {}
        return {**SettingsIn().model_dump(), **s}

    async def history(eid, field, old, new, source, mode, by):
        await db.cal_history.insert_one({"id": uuid.uuid4().hex, "entity_id": eid, "field": field, "old": old, "new": new,
                                         "source": source, "mode": mode, "by": by, "at": _now()})

    async def org_by_name(nome: str, extra: dict, by: str) -> Optional[str]:
        """Organizzatore unico: riusa quello con lo stesso nome normalizzato (o stesso sito), altrimenti lo crea."""
        key = _norm(nome)
        if not key:
            return None
        dom = _domain(extra.get("sito_web"))
        o = await db.cal_organizers.find_one({"$or": [{"nome_key": key}, *([{"dominio": dom}] if dom else [])], "merged_into": None}, {"_id": 0, "id": 1})
        if o:
            return o["id"]
        oid = uuid.uuid4().hex
        await db.cal_organizers.insert_one({**OrganizerIn(nome=nome[:200]).model_dump(), "id": oid, "nome_key": key, "dominio": dom or None,
                                            "email_generale": extra.get("email") or None, "telefono": extra.get("telefono") or None,
                                            "sito_web": extra.get("sito_web") or None, "comune": extra.get("comune"), "provincia": extra.get("provincia"),
                                            "regione": extra.get("regione"), "merged_into": None, "created_at": _now(), "created_by": by,
                                            "privacy": {"status": "da_verificare", "fonte": extra.get("_source"), "data_acquisizione": _now()[:10],
                                                        "tipo_indirizzo": "pubblico" if extra.get("email") else None}})
        return oid

    def clean_event(d: dict) -> dict:
        d["data_inizio"], d["data_fine"] = _d(d.get("data_inizio")), _d(d.get("data_fine"))
        if d.get("data_fine") and d.get("data_inizio") and d["data_fine"] < d["data_inizio"]:
            raise HTTPException(status_code=400, detail="La data di fine precede la data di inizio")
        if not d.get("anno") and d.get("data_inizio"):
            d["anno"] = int(d["data_inizio"][:4])
        if d.get("disciplina") not in DISCIPLINE:
            d["disciplina"] = _disc(d.get("disciplina")) or "running"
        if d.get("stato") not in STATI_EVENTO:
            d["stato"] = "da_verificare"
        if d.get("stato_commerciale") not in STATI_COMM:
            d["stato_commerciale"] = "da_qualificare"
        d["nome_key"] = _name_key(d["nome"])
        return d

    async def with_comm(ev: dict, days: int) -> dict:
        return {**ev, "data_comunicazione": comm_date(ev, days)}

    def event_query(f: dict) -> dict:
        q = {"merged_into": None}
        if f.get("anno"):
            q["anno"] = int(f["anno"])
        if f.get("mese"):
            q["data_inizio"] = {"$regex": f"^\\d{{4}}-{int(f['mese']):02d}-"}
        for k in ("regione", "provincia", "disciplina", "distanza", "organizer_id", "stato", "stato_commerciale"):
            if f.get(k):
                q[k] = f[k]
        if f.get("has_email") == "1":
            q["email"] = {"$nin": [None, ""]}
        elif f.get("has_email") == "0":
            q["email"] = {"$in": [None, ""]}
        if f.get("dal") or f.get("al"):
            q["data_inizio"] = {**({"$gte": f["dal"]} if f.get("dal") else {}), **({"$lte": f["al"]} if f.get("al") else {})}
        if f.get("q"):
            q["$or"] = [{k: {"$regex": re.escape(f["q"]), "$options": "i"}} for k in ("nome", "comune", "organizzatore_nome", "provincia")]
        return q

    # ---------- eventi ----------
    @r.get("/meta")
    async def meta(admin: dict = Depends(sa)):
        return {"discipline": DISCIPLINE, "stati_evento": STATI_EVENTO, "stati_commerciali": STATI_COMM, "privacy": PRIVACY, "tipi_org": TIPI_ORG,
                "fields": EVENT_FIELDS, "settings": await settings()}

    @r.get("/events")
    async def list_events(admin: dict = Depends(sa), anno: str = "", mese: str = "", regione: str = "", provincia: str = "", disciplina: str = "",
                          distanza: str = "", organizer_id: str = "", stato: str = "", stato_commerciale: str = "", has_email: str = "", q: str = "",
                          dal: str = "", al: str = "", sort: str = "asc", page: int = 1, limit: int = 50):
        f = dict(anno=anno, mese=mese, regione=regione, provincia=provincia, disciplina=disciplina, distanza=distanza, organizer_id=organizer_id,
                 stato=stato, stato_commerciale=stato_commerciale, has_email=has_email, q=q, dal=dal, al=al)
        qq, days = event_query(f), (await settings())["giorni_post_evento"]
        tot = await db.cal_events.count_documents(qq)
        limit = max(1, min(limit, 1000))
        rows = await db.cal_events.find(qq, {"_id": 0, "sources.data": 0}).sort("data_inizio", -1 if sort == "desc" else 1).skip((max(page, 1) - 1) * limit).limit(limit).to_list(limit)
        return {"total": tot, "rows": [await with_comm(e, days) for e in rows]}

    @r.get("/events/{eid}")
    async def get_event(eid: str, admin: dict = Depends(sa)):
        ev = await db.cal_events.find_one({"id": eid}, {"_id": 0})
        if not ev:
            raise HTTPException(status_code=404, detail="Evento non trovato")
        org = await db.cal_organizers.find_one({"id": ev.get("organizer_id")}, {"_id": 0}) if ev.get("organizer_id") else None
        hist = await db.cal_history.find({"entity_id": eid}, {"_id": 0}).sort("at", -1).to_list(200)
        conf = await db.cal_duplicates.find({"$or": [{"a": eid}, {"b": eid}], "status": "open"}, {"_id": 0}).to_list(20)
        return {**await with_comm(ev, (await settings())["giorni_post_evento"]), "organizer": org, "history": hist, "duplicates": conf}

    @r.post("/events")
    async def create_event(body: EventIn, admin: dict = Depends(sa)):
        d = clean_event(body.model_dump())
        res = await upsert_event(d, "manuale", None, None, admin.get("email"), manual=True)
        await audit(admin, "cal_event_create", detail=d["nome"])
        return res

    @r.put("/events/{eid}")
    async def update_event(eid: str, body: EventIn, admin: dict = Depends(sa)):
        cur = await db.cal_events.find_one({"id": eid}, {"_id": 0})
        if not cur:
            raise HTTPException(status_code=404, detail="Evento non trovato")
        d = clean_event(body.model_dump())
        upd, manual = {}, set(cur.get("manual_fields") or [])
        for k, v in d.items():
            if cur.get(k) != v and k != "nome_key":
                upd[k] = v
                manual.add(k)
                await history(eid, k, cur.get(k), v, "manuale", "manuale", admin.get("email"))
        if d.get("organizer_id"):
            o = await db.cal_organizers.find_one({"id": d["organizer_id"]}, {"_id": 0, "nome": 1})
            upd["organizzatore_nome"] = (o or {}).get("nome")
        if {"data_inizio", "data_fine"} & set(upd):
            upd["data_da_verificare"] = False
            upd["data_confermata_manuale"] = True
        upd.update(manual_fields=sorted(manual), updated_at=_now(), nome_key=d["nome_key"])
        await db.cal_events.update_one({"id": eid}, {"$set": upd})
        await audit(admin, "cal_event_update", detail=f"{d['nome']} · {', '.join(k for k in upd if k not in ('manual_fields', 'updated_at', 'nome_key'))}")
        return await get_event(eid, admin)

    async def upsert_event(d: dict, source: str, url: Optional[str], ext_id: Optional[str], by: str, manual: bool = False) -> dict:
        """Collega la fonte a un evento esistente (stesso ID fonte o corrispondenza certa), segnala i dubbi, altrimenti crea."""
        src = {"source": source, "url": url, "ext_id": ext_id, "seen_at": _now(),
               "data": {k: d.get(k) for k in ("nome", "data_inizio", "data_fine", "comune", "provincia", "distanza", "sito_web")}}
        hit = await db.cal_events.find_one({"sources": {"$elemMatch": {"source": source, "ext_id": ext_id}}, "merged_into": None}, {"_id": 0}) if ext_id else None
        cands = []
        if not hit and not manual:
            qy = {"merged_into": None, **({"anno": d["anno"]} if d.get("anno") else {})}
            pool = await db.cal_events.find({**qy, "$or": [{"nome_key": {"$regex": re.escape(d["nome_key"][:12])}}, *([{"data_inizio": d["data_inizio"]}] if d.get("data_inizio") else [])]},
                                            {"_id": 0}).to_list(300)
            cands = sorted(((score(d, e), e) for e in pool), key=lambda x: -x[0])
            if cands and cands[0][0] >= 0.85 and cands[0][1].get("data_inizio") == d.get("data_inizio"):
                hit = cands[0][1]
        if hit:
            await link_source(hit, d, src, by)
            return {"id": hit["id"], "action": "linked"}
        eid = uuid.uuid4().hex
        org_id = d.pop("organizer_id", None) or (await org_by_name(d.get("organizzatore") or "", {**d, "_source": source}, by) if d.get("organizzatore") else None)
        org = await db.cal_organizers.find_one({"id": org_id}, {"_id": 0, "nome": 1}) if org_id else None
        doc = {**{k: d.get(k) for k in EVENT_FIELDS if k != "organizzatore"}, "stato": d.get("stato") or "da_verificare",
               "stato_commerciale": d.get("stato_commerciale") or "da_qualificare", "nome_key": d["nome_key"], "id": eid, "organizer_id": org_id,
               "organizzatore_nome": (org or {}).get("nome"), "sources": [src], "merged_into": None, "data_da_verificare": False,
               "manual_fields": list(EVENT_FIELDS) if manual else [], "created_at": _now(), "updated_at": _now(), "last_sync_at": _now(), "last_check_at": _now()}
        await db.cal_events.insert_one({**doc})
        for s, e in cands[:3]:
            if s >= 0.6:
                a, b = sorted([eid, e["id"]])
                await db.cal_duplicates.update_one({"a": a, "b": b}, {"$setOnInsert": {"id": uuid.uuid4().hex, "a": a, "b": b, "score": s, "status": "open",
                                                                                       "created_at": _now()}}, upsert=True)
        return {"id": eid, "action": "created", "possible_duplicates": sum(1 for s, _ in cands[:3] if s >= 0.6)}

    async def link_source(ev: dict, d: dict, src: dict, by: str):
        srcs = [s for s in ev.get("sources") or [] if not (s["source"] == src["source"] and s.get("ext_id") == src.get("ext_id") and s.get("url") == src.get("url"))]
        upd, manual = {"sources": srcs + [src], "last_sync_at": _now(), "updated_at": _now()}, set(ev.get("manual_fields") or [])
        for k in ("data_inizio", "data_fine"):
            if d.get(k) and ev.get(k) and d[k] != ev[k]:
                upd["data_da_verificare"] = True
                await db.cal_conflicts.insert_one({"id": uuid.uuid4().hex, "event_id": ev["id"], "field": k, "value": ev[k], "other": d[k],
                                                   "source": src["source"], "url": src.get("url"), "at": _now(), "status": "open"})
        for k in ("sito_web", "pagina_iscrizioni", "email", "telefono", "indirizzo", "comune", "provincia", "regione"):
            if d.get(k) and not ev.get(k) and k not in manual:
                upd[k] = d[k]
                await history(ev["id"], k, None, d[k], src["source"], "automatica", by)
        await db.cal_events.update_one({"id": ev["id"]}, {"$set": upd})

    # ---------- duplicati e conflitti ----------
    @r.get("/duplicates")
    async def duplicates(admin: dict = Depends(sa)):
        rows = await db.cal_duplicates.find({"status": "open"}, {"_id": 0}).sort("score", -1).to_list(500)
        ids = {x for d in rows for x in (d["a"], d["b"])}
        evs = {e["id"]: e for e in await db.cal_events.find({"id": {"$in": list(ids)}}, {"_id": 0, "id": 1, "nome": 1, "data_inizio": 1, "comune": 1,
                                                                                         "provincia": 1, "distanza": 1, "sources.source": 1, "merged_into": 1}).to_list(1000)}
        conf = await db.cal_conflicts.find({"status": "open"}, {"_id": 0}).sort("at", -1).to_list(500)
        names = {e["id"]: e.get("nome") for e in await db.cal_events.find({"id": {"$in": [c["event_id"] for c in conf]}}, {"_id": 0, "id": 1, "nome": 1}).to_list(1000)}
        return {"duplicates": [{**d, "ev_a": evs.get(d["a"]), "ev_b": evs.get(d["b"])} for d in rows if evs.get(d["a"]) and evs.get(d["b"])],
                "conflicts": [{**c, "event_nome": names.get(c["event_id"])} for c in conf]}

    @r.post("/duplicates/{did}/resolve")
    async def resolve_dup(did: str, body: ResolveIn, admin: dict = Depends(sa)):
        d = await db.cal_duplicates.find_one({"id": did, "status": "open"}, {"_id": 0})
        if not d or body.action not in ("merge", "separate", "ignore"):
            raise HTTPException(status_code=400, detail="Segnalazione non valida")
        if body.action == "merge":
            keep, gone = [await db.cal_events.find_one({"id": x}, {"_id": 0}) for x in (d["a"], d["b"])]
            upd = {"sources": (keep.get("sources") or []) + (gone.get("sources") or []), "updated_at": _now()}
            for k in EVENT_FIELDS:
                if not keep.get(k) and gone.get(k):
                    upd[k] = gone[k]
            await db.cal_events.update_one({"id": keep["id"]}, {"$set": upd})
            await db.cal_events.update_one({"id": gone["id"]}, {"$set": {"merged_into": keep["id"], "updated_at": _now()}})
            await history(keep["id"], "unione", gone["id"], keep["id"], "manuale", "manuale", admin.get("email"))
        await db.cal_duplicates.update_one({"id": did}, {"$set": {"status": body.action, "resolved_by": admin.get("email"), "resolved_at": _now()}})
        await audit(admin, "cal_duplicate_resolve", detail=f"{d['a']} / {d['b']} → {body.action}")
        return {"ok": True}

    @r.post("/conflicts/{cid}/resolve")
    async def resolve_conflict(cid: str, body: ResolveIn, admin: dict = Depends(sa)):
        c = await db.cal_conflicts.find_one({"id": cid, "status": "open"}, {"_id": 0})
        if not c or body.action not in ("keep", "use_other"):
            raise HTTPException(status_code=400, detail="Conflitto non valido")
        if body.action == "use_other":
            await db.cal_events.update_one({"id": c["event_id"]}, {"$set": {c["field"]: c["other"], "updated_at": _now()}, "$addToSet": {"manual_fields": c["field"]}})
            await history(c["event_id"], c["field"], c["value"], c["other"], c["source"], "manuale", admin.get("email"))
        await db.cal_conflicts.update_one({"id": cid}, {"$set": {"status": "resolved", "resolution": body.action, "resolved_at": _now()}})
        if not await db.cal_conflicts.find_one({"event_id": c["event_id"], "status": "open"}):
            await db.cal_events.update_one({"id": c["event_id"]}, {"$set": {"data_da_verificare": False}})
        return {"ok": True}

    # ---------- organizzatori ----------
    @r.get("/organizers")
    async def list_orgs(admin: dict = Depends(sa), q: str = "", privacy: str = "", stato_commerciale: str = "", page: int = 1, limit: int = 50):
        qq = {"merged_into": None}
        if q:
            qq["$or"] = [{k: {"$regex": re.escape(q), "$options": "i"}} for k in ("nome", "comune", "email_generale", "sito_web")]
        if privacy:
            qq["privacy.status"] = privacy
        if stato_commerciale:
            qq["stato_commerciale"] = stato_commerciale
        tot = await db.cal_organizers.count_documents(qq)
        rows = await db.cal_organizers.find(qq, {"_id": 0}).sort("nome", 1).skip((max(page, 1) - 1) * limit).limit(min(limit, 500)).to_list(500)
        cnt = {x["_id"]: x["n"] for x in await db.cal_events.aggregate([{"$match": {"organizer_id": {"$in": [o["id"] for o in rows]}, "merged_into": None}},
                                                                         {"$group": {"_id": "$organizer_id", "n": {"$sum": 1}}}]).to_list(1000)}
        return {"total": tot, "rows": [{**o, "eventi": cnt.get(o["id"], 0)} for o in rows]}

    @r.get("/organizers/{oid}")
    async def get_org(oid: str, admin: dict = Depends(sa)):
        o = await db.cal_organizers.find_one({"id": oid}, {"_id": 0})
        if not o:
            raise HTTPException(status_code=404, detail="Organizzatore non trovato")
        evs = await db.cal_events.find({"organizer_id": oid, "merged_into": None}, {"_id": 0, "id": 1, "nome": 1, "anno": 1, "data_inizio": 1, "stato": 1, "comune": 1}).sort("data_inizio", -1).to_list(500)
        hist = await db.cal_history.find({"entity_id": oid}, {"_id": 0}).sort("at", -1).to_list(100)
        return {**o, "events": evs, "history": hist, "communications": []}

    @r.post("/organizers")
    async def create_org(body: OrganizerIn, admin: dict = Depends(sa)):
        key = _norm(body.nome)
        if await db.cal_organizers.find_one({"nome_key": key, "merged_into": None}):
            raise HTTPException(status_code=400, detail="Organizzatore gi\u00e0 presente con questo nome")
        oid = uuid.uuid4().hex
        doc = {**body.model_dump(), "id": oid, "nome_key": key, "dominio": _domain(body.sito_web) or None, "merged_into": None, "created_at": _now(),
               "created_by": admin.get("email"), "privacy": {"status": "da_verificare", "fonte": "manuale", "data_acquisizione": _now()[:10]}}
        await db.cal_organizers.insert_one({**doc})
        await audit(admin, "cal_organizer_create", detail=body.nome)
        return doc

    @r.put("/organizers/{oid}")
    async def update_org(oid: str, body: OrganizerIn, admin: dict = Depends(sa)):
        cur = await db.cal_organizers.find_one({"id": oid}, {"_id": 0})
        if not cur:
            raise HTTPException(status_code=404, detail="Organizzatore non trovato")
        d = body.model_dump()
        for k, v in d.items():
            if cur.get(k) != v:
                await history(oid, k, cur.get(k), v, "manuale", "manuale", admin.get("email"))
        await db.cal_organizers.update_one({"id": oid}, {"$set": {**d, "nome_key": _norm(body.nome), "dominio": _domain(body.sito_web) or None, "updated_at": _now()}})
        await db.cal_events.update_many({"organizer_id": oid}, {"$set": {"organizzatore_nome": body.nome}})
        return await get_org(oid, admin)

    @r.put("/organizers/{oid}/privacy")
    async def set_privacy(oid: str, body: PrivacyIn, admin: dict = Depends(sa)):
        if body.status not in PRIVACY:
            raise HTTPException(status_code=400, detail="Stato privacy non valido")
        if body.status == "idoneo" and not ((body.base_giuridica or "").strip() and (body.finalita or "").strip() and (body.fonte or "").strip()):
            raise HTTPException(status_code=400, detail="Per 'Idoneo' servono fonte, finalit\u00e0 e base giuridica documentata")
        cur = await db.cal_organizers.find_one({"id": oid}, {"_id": 0, "privacy": 1})
        if cur is None:
            raise HTTPException(status_code=404, detail="Organizzatore non trovato")
        if (cur.get("privacy") or {}).get("status") in ("disiscritto", "opposizione") and body.status == "idoneo":
            raise HTTPException(status_code=400, detail="Disiscrizione/opposizione registrata: il contatto non pu\u00f2 tornare idoneo")
        p = {**(cur.get("privacy") or {}), **body.model_dump(), "ultima_verifica": _now(), "verificato_da": admin.get("email")}
        await db.cal_organizers.update_one({"id": oid}, {"$set": {"privacy": p}})
        await history(oid, "privacy", (cur.get("privacy") or {}).get("status"), body.status, "manuale", "manuale", admin.get("email"))
        await audit(admin, "cal_privacy_update", detail=f"{oid} → {body.status}")
        return p

    @r.post("/organizers/merge")
    async def merge_orgs(body: MergeIn, admin: dict = Depends(sa)):
        ids = [x for x in body.merge_ids if x != body.keep_id]
        if not ids or not await db.cal_organizers.find_one({"id": body.keep_id}):
            raise HTTPException(status_code=400, detail="Selezione non valida")
        keep = await db.cal_organizers.find_one({"id": body.keep_id}, {"_id": 0})
        for o in await db.cal_organizers.find({"id": {"$in": ids}}, {"_id": 0}).to_list(100):
            fill = {k: o[k] for k in ("ragione_sociale", "sito_web", "email_generale", "email_organizzativa", "telefono", "cellulare", "comune", "provincia", "regione")
                    if o.get(k) and not keep.get(k)}
            if fill:
                await db.cal_organizers.update_one({"id": keep["id"]}, {"$set": fill})
                keep.update(fill)
            await db.cal_events.update_many({"organizer_id": o["id"]}, {"$set": {"organizer_id": keep["id"], "organizzatore_nome": keep["nome"]}})
            await db.cal_organizers.update_one({"id": o["id"]}, {"$set": {"merged_into": keep["id"], "updated_at": _now()}})
            await history(keep["id"], "unione", o["nome"], keep["nome"], "manuale", "manuale", admin.get("email"))
        await audit(admin, "cal_organizer_merge", detail=f"{keep['nome']} ← {len(ids)}")
        return await get_org(keep["id"], admin)

    # ---------- import / export ----------
    def auto_map(cols: list) -> dict:
        out = {}
        for c in cols:
            n = _norm(c)
            for f, labels in LABELS.items():
                if f not in out.values() and n in labels:
                    out[c] = f
                    break
        return out

    @r.post("/import/preview")
    async def import_preview(file: UploadFile = File(...), admin: dict = Depends(sa)):
        ext = (file.filename or "").rsplit(".", 1)[-1].lower()
        if ext not in ("csv", "xlsx", "xls"):
            raise HTTPException(status_code=400, detail="Formato non supportato (CSV, XLSX, XLS)")
        cols, rows = read_rows(await file.read(), ext)
        return {"columns": cols, "mapping": auto_map(cols), "sample": rows[:5], "total": len(rows), "fields": EVENT_FIELDS + ["ext_id"]}

    async def run_import(job_id: str, rows: list, cols: list, mapping: dict, source: str, by: str):
        res = Counter()
        errs = []
        for i, row in enumerate(rows, start=2):
            try:
                d = {mapping[c]: (row[j] if j < len(row) else "") for j, c in enumerate(cols) if mapping.get(c)}
                if not str(d.get("nome") or "").strip():
                    raise ValueError("nome mancante")
                ext = str(d.pop("ext_id", "") or "").strip() or None
                for k in ("anno", "partecipanti"):
                    d[k] = int(float(d[k])) if str(d.get(k) or "").strip() else None
                for k in ("lat", "lng"):
                    d[k] = float(str(d[k]).replace(",", ".")) if str(d.get(k) or "").strip() else None
                d = clean_event({**EventIn(nome=str(d["nome"]).strip()[:200]).model_dump(), **{k: (v.strip() if isinstance(v, str) else v) or None for k, v in d.items()}})
                out = await upsert_event(d, source, d.get("sito_web"), ext, by)
                res[out["action"]] += 1
                res["possible_duplicates"] += out.get("possible_duplicates", 0)
            except Exception as e:  # noqa: BLE001
                res["errors"] += 1
                errs.append({"row": i, "error": str(e)[:150]})
            if i % 50 == 0:
                await db.cal_imports.update_one({"id": job_id}, {"$set": {"progress": i - 1, "result": dict(res)}})
        await db.cal_imports.update_one({"id": job_id}, {"$set": {"status": "done", "progress": len(rows), "result": dict(res), "errors": errs[:200], "finished_at": _now()}})

    @r.post("/import")
    async def import_file(file: UploadFile = File(...), mapping: str = Form(...), source: str = Form("manuale"), admin: dict = Depends(sa)):
        ext = (file.filename or "").rsplit(".", 1)[-1].lower()
        if ext not in ("csv", "xlsx", "xls"):
            raise HTTPException(status_code=400, detail="Formato non supportato")
        mp = {k: v for k, v in json.loads(mapping).items() if v in EVENT_FIELDS + ["ext_id"]}
        if "nome" not in mp.values():
            raise HTTPException(status_code=400, detail="Associa almeno la colonna del nome manifestazione")
        cols, rows = read_rows(await file.read(), ext)
        jid = uuid.uuid4().hex
        await db.cal_imports.insert_one({"id": jid, "file": file.filename, "source": source if source in [s[0] for s in SOURCES] else "manuale", "status": "running",
                                         "total": len(rows), "progress": 0, "created_by": admin.get("email"), "created_at": _now()})
        asyncio.create_task(run_import(jid, rows, cols, mp, source, admin.get("email")))
        await audit(admin, "cal_import", detail=f"{file.filename} · {len(rows)} righe")
        return {"job_id": jid, "total": len(rows)}

    @r.get("/import/{jid}")
    async def import_status(jid: str, admin: dict = Depends(sa)):
        return await db.cal_imports.find_one({"id": jid}, {"_id": 0}) or {}

    @r.get("/export")
    async def export(admin: dict = Depends(sa), format: str = "csv", anno: str = "", mese: str = "", regione: str = "", provincia: str = "", disciplina: str = "",
                     distanza: str = "", stato: str = "", stato_commerciale: str = "", has_email: str = "", q: str = ""):
        f = dict(anno=anno, mese=mese, regione=regione, provincia=provincia, disciplina=disciplina, distanza=distanza, stato=stato,
                 stato_commerciale=stato_commerciale, has_email=has_email, q=q)
        days = (await settings())["giorni_post_evento"]
        rows = await db.cal_events.find(event_query(f), {"_id": 0}).sort("data_inizio", 1).to_list(50000)
        head = ["id", "nome", "disciplina", "specialita", "distanza", "edizione", "anno", "data_inizio", "data_fine", "regione", "provincia", "comune",
                "organizzatore_nome", "email", "telefono", "sito_web", "stato", "stato_commerciale", "data_comunicazione", "fonti"]
        data = [[comm_date(e, days) if h == "data_comunicazione" else ", ".join(sorted({s["source"] for s in e.get("sources") or []})) if h == "fonti" else e.get(h)
                 for h in head] for e in rows]
        await audit(admin, "cal_export", detail=f"{len(rows)} eventi · {format}")
        if format == "xlsx":
            import openpyxl
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.append(head)
            for x in data:
                ws.append(x)
            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)
            return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                     headers={"Content-Disposition": "attachment; filename=calendario-eventi-italia.xlsx"})
        s = io.StringIO()
        w = csv.writer(s, delimiter=";")
        w.writerow(head)
        w.writerows(data)
        return StreamingResponse(io.BytesIO(("\ufeff" + s.getvalue()).encode()), media_type="text/csv",
                                 headers={"Content-Disposition": "attachment; filename=calendario-eventi-italia.csv"})

    # ---------- dashboard, fonti, impostazioni ----------
    @r.get("/dashboard")
    async def dashboard(admin: dict = Depends(sa)):
        y = datetime.now(timezone.utc).year
        evs = await db.cal_events.find({"merged_into": None}, {"_id": 0, "anno": 1, "data_inizio": 1, "disciplina": 1, "regione": 1, "distanza": 1}).to_list(100000)
        orgs = await db.cal_organizers.find({"merged_into": None}, {"_id": 0, "email_generale": 1, "email_organizzativa": 1, "privacy.status": 1, "stato_commerciale": 1}).to_list(100000)
        mesi = Counter((e.get("data_inizio") or "")[5:7] for e in evs if e.get("data_inizio") and e.get("anno") in (y, y + 1))
        return {"kpi": {"eventi": len(evs), "anno_corrente": sum(1 for e in evs if e.get("anno") == y), "anno_prossimo": sum(1 for e in evs if e.get("anno") == y + 1),
                        "organizzatori": len(orgs), "con_email": sum(1 for o in orgs if o.get("email_generale") or o.get("email_organizzativa")),
                        "da_verificare": sum(1 for o in orgs if (o.get("privacy") or {}).get("status", "da_verificare") == "da_verificare"),
                        "idonei": sum(1 for o in orgs if (o.get("privacy") or {}).get("status") == "idoneo"),
                        "demo_richieste": sum(1 for o in orgs if o.get("stato_commerciale") == "demo_richiesta"),
                        "clienti": sum(1 for o in orgs if o.get("stato_commerciale") == "cliente_acquisito"),
                        "duplicati_aperti": await db.cal_duplicates.count_documents({"status": "open"}),
                        "conflitti_aperti": await db.cal_conflicts.count_documents({"status": "open"}),
                        "email_programmate": 0, "email_inviate": 0},
                "per_mese": [{"mese": f"{m:02d}", "n": mesi.get(f"{m:02d}", 0)} for m in range(1, 13)],
                "per_disciplina": [{"k": k, "n": n} for k, n in Counter(e.get("disciplina") or "N/D" for e in evs).most_common()],
                "per_regione": [{"k": k, "n": n} for k, n in Counter(e.get("regione") or "N/D" for e in evs).most_common(20)],
                "per_distanza": [{"k": k, "n": n} for k, n in Counter(e.get("distanza") or "N/D" for e in evs).most_common(12)],
                "anni": [y, y + 1]}

    # ---------- fonti (Fase 2): verifica accesso, collegamento solo se consentita, sincronizzazione ----------
    async def all_sources() -> list:
        st = {s["id"]: s for s in await db.cal_sources.find({}, {"_id": 0}).to_list(200)}
        running = {k for k, s in st.items() if (s.get("lock_until") or "") > _now()}
        out = []
        for k, n, d, u in SOURCES:
            base = cal_feeds.VERIFICHE.get(k, {})
            s = st.get(k) or {}
            out.append({"id": k, "nome": n, "disciplina": d, "url": u, "custom": False, **s,
                        "verifica": s.get("verifica") or {**base, "verificata_il": cal_feeds.VERIFICATA_IL, "verificata_da": "Verifica iniziale Fase 2"}})
        out += [{**s, "custom": True} for s in st.values() if s.get("custom")]
        for s in out:
            if s["id"] == "manuale":
                s["stato"] = "attiva"
            elif s["verifica"].get("esito") != "consentita":
                s["stato"] = "non_disponibile"
            elif not (s.get("attiva") and s.get("feed_url")):
                s["stato"] = "disabilitata"
            else:
                s["stato"] = "in_aggiornamento" if s["id"] in running else ("errore" if s.get("ultimo_esito") == "errore" else "attiva")
        return out

    async def get_source(sid: str) -> dict:
        s = next((x for x in await all_sources() if x["id"] == sid), None)
        if not s:
            raise HTTPException(status_code=404, detail="Fonte non trovata")
        return s

    @r.get("/sources")
    async def sources(admin: dict = Depends(sa)):
        cnt = {x["_id"]: x["n"] for x in await db.cal_events.aggregate([{"$match": {"merged_into": None}}, {"$unwind": "$sources"},
                                                                         {"$group": {"_id": "$sources.source", "n": {"$sum": 1}}}]).to_list(200)}
        imports = await db.cal_imports.find({}, {"_id": 0, "errors": 0}).sort("created_at", -1).to_list(30)
        s = await settings()
        return {"sources": [{**x, "eventi": cnt.get(x["id"], 0)} for x in await all_sources()], "imports": imports, "formati": cal_feeds.FORMATI,
                "raccolta_automatica": s["raccolta_automatica"], "ultima_sync_automatica": s.get("ultima_sync_automatica")}

    @r.put("/sources/{sid}/verifica")
    async def set_verifica(sid: str, body: VerificaIn, admin: dict = Depends(sa)):
        src = await get_source(sid)
        if sid == "manuale" or body.esito not in ("consentita", "non_consentita", "da_verificare"):
            raise HTTPException(status_code=400, detail="Esito non valido")
        if body.esito == "consentita" and not ((body.metodo or "").strip() and (body.prova or "").strip()):
            raise HTTPException(status_code=400, detail="Per 'Consentita' indica il metodo di accesso autorizzato e la prova (accordo, licenza, documentazione API)")
        v = {**body.model_dump(), "evidenze": src["verifica"].get("evidenze") or [], "come_sbloccare": src["verifica"].get("come_sbloccare"),
             "verificata_il": _now()[:10], "verificata_da": admin.get("email")}
        upd = {"verifica": v, "updated_at": _now(), **({} if body.esito == "consentita" else {"attiva": False})}
        await db.cal_sources.update_one({"id": sid}, {"$set": upd}, upsert=True)
        await audit(admin, "cal_source_verifica", detail=f"{sid} → {body.esito}")
        return await get_source(sid)

    def check_conn(feed_url: str, formato: str) -> str:
        if formato not in cal_feeds.FORMATI:
            raise HTTPException(status_code=400, detail="Formato non supportato")
        try:
            return cal_feeds.check_url(feed_url)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @r.put("/sources/{sid}/connessione")
    async def set_conn(sid: str, body: ConnIn, admin: dict = Depends(sa)):
        src = await get_source(sid)
        if sid == "manuale" or src["verifica"].get("esito") != "consentita":
            raise HTTPException(status_code=400, detail="Fonte non autorizzata: registra prima una verifica con esito 'Consentita'")
        url = check_conn(body.feed_url, body.formato)
        await db.cal_sources.update_one({"id": sid}, {"$set": {"feed_url": url, "formato": body.formato, "attiva": body.attiva, "updated_at": _now()}}, upsert=True)
        await audit(admin, "cal_source_connessione", detail=f"{sid} · {body.formato} · attiva={body.attiva}")
        return await get_source(sid)

    @r.post("/sources")
    async def add_source(body: FonteIn, admin: dict = Depends(sa)):
        url = check_conn(body.feed_url, body.formato)
        sid = f"fonte_{uuid.uuid4().hex[:8]}"
        doc = {"id": sid, "custom": True, "nome": body.nome, "disciplina": body.disciplina if body.disciplina in DISCIPLINE else "*", "url": body.url,
               "feed_url": url, "formato": body.formato, "attiva": True, "created_at": _now(), "created_by": admin.get("email"),
               "verifica": {"esito": "consentita", "metodo": body.metodo, "prova": body.prova, "note": body.note, "evidenze": [],
                            "verificata_il": _now()[:10], "verificata_da": admin.get("email")}}
        await db.cal_sources.insert_one({**doc})
        await audit(admin, "cal_source_create", detail=f"{body.nome} · {body.formato}")
        return await get_source(sid)

    @r.delete("/sources/{sid}")
    async def delete_source(sid: str, admin: dict = Depends(sa)):
        res = await db.cal_sources.delete_one({"id": sid, "custom": True})
        if not res.deleted_count:
            raise HTTPException(status_code=400, detail="Si possono eliminare solo le fonti autorizzate aggiunte a mano")
        await audit(admin, "cal_source_delete", detail=sid)
        return {"ok": True}

    @r.post("/sources/{sid}/test")
    async def test_source(sid: str, admin: dict = Depends(sa)):
        src = await get_source(sid)
        if src["verifica"].get("esito") != "consentita" or not src.get("feed_url"):
            raise HTTPException(status_code=400, detail="Fonte non autorizzata o senza indirizzo del feed")
        try:
            cols, rows = cal_feeds.parse(await cal_feeds.fetch(src["feed_url"], attempts=1), src.get("formato") or "csv")
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"Lettura non riuscita: {str(e)[:200]}") from e
        return {"columns": cols, "mapping": feed_map(cols), "sample": rows[:5], "total": len(rows)}

    def feed_map(cols: list) -> dict:
        fields = EVENT_FIELDS + ["ext_id"]
        return {**auto_map(cols), **{c: c for c in cols if c in fields}}

    async def sync_source(sid: str, by: str, trigger: str) -> dict:
        src = await get_source(sid)
        if src["verifica"].get("esito") != "consentita" or not (src.get("attiva") and src.get("feed_url")):
            return {"id": sid, "skipped": "non autorizzata o non attiva"}
        await db.cal_sources.update_one({"id": sid}, {"$setOnInsert": {"id": sid}}, upsert=True)
        lock = await db.cal_sources.update_one({"id": sid, "$or": [{"lock_until": None}, {"lock_until": {"$lt": _now()}}]},
                                               {"$set": {"lock_until": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()}})
        if not lock.modified_count:
            return {"id": sid, "skipped": "già in corso"}
        jid = uuid.uuid4().hex
        await db.cal_imports.insert_one({"id": jid, "file": src["feed_url"], "source": sid, "kind": "sync", "trigger": trigger, "status": "running",
                                         "total": 0, "progress": 0, "created_by": by, "created_at": _now()})
        try:
            cols, rows = cal_feeds.parse(await cal_feeds.fetch(src["feed_url"]), src.get("formato") or "csv")
            mp = feed_map(cols)
            if "disciplina" not in mp.values() and src.get("disciplina") in DISCIPLINE:
                cols, rows, mp = cols + ["_disciplina"], [r + [src["disciplina"]] for r in rows], {**mp, "_disciplina": "disciplina"}
            if "nome" not in mp.values():
                raise ValueError("Nel feed non c'è una colonna riconoscibile come nome della manifestazione")
            await db.cal_imports.update_one({"id": jid}, {"$set": {"total": len(rows)}})
            await run_import(jid, rows, cols, mp, sid, by)
            res = (await db.cal_imports.find_one({"id": jid}, {"_id": 0, "result": 1}) or {}).get("result") or {}
            await db.cal_sources.update_one({"id": sid}, {"$set": {"ultima_sync": _now(), "ultimo_esito": "ok", "ultimo_errore": None, "ultimo_risultato": res}}, upsert=True)
            return {"id": sid, "ok": True, **res}
        except Exception as e:  # noqa: BLE001
            msg = str(e)[:300]
            await db.cal_imports.update_one({"id": jid}, {"$set": {"status": "error", "error": msg, "finished_at": _now()}})
            await db.cal_sources.update_one({"id": sid}, {"$set": {"ultimo_tentativo": _now(), "ultimo_esito": "errore", "ultimo_errore": msg}}, upsert=True)
            return {"id": sid, "ok": False, "error": msg}
        finally:
            await db.cal_sources.update_one({"id": sid}, {"$set": {"lock_until": None}})

    async def sync_all(by: str, trigger: str) -> list:
        out = []
        for s in await all_sources():
            if s["id"] != "manuale" and s["verifica"].get("esito") == "consentita" and s.get("attiva") and s.get("feed_url"):
                out.append(await sync_source(s["id"], by, trigger))
        return out

    @r.post("/sources/{sid}/sync")
    async def sync_now(sid: str, admin: dict = Depends(sa)):
        src = await get_source(sid)
        if src["verifica"].get("esito") != "consentita" or not (src.get("attiva") and src.get("feed_url")):
            raise HTTPException(status_code=400, detail="Fonte non autorizzata o non attiva: nessuna sincronizzazione")
        if src["stato"] == "in_aggiornamento":
            raise HTTPException(status_code=409, detail="Sincronizzazione già in corso")
        asyncio.create_task(sync_source(sid, admin.get("email"), "manuale"))
        await audit(admin, "cal_source_sync", detail=sid)
        return {"ok": True, "started": sid}

    @r.post("/sync")
    async def sync_all_now(admin: dict = Depends(sa)):
        n = sum(1 for s in await all_sources() if s["stato"] in ("attiva", "errore") and s["id"] != "manuale")
        if n:
            asyncio.create_task(sync_all(admin.get("email"), "manuale"))
        await audit(admin, "cal_sync_all", detail=f"{n} fonti")
        return {"ok": True, "fonti": n}

    async def cron_tick() -> dict:
        s = await settings()
        if not s["raccolta_automatica"]:
            return {"skipped": "raccolta automatica disattivata"}
        await db.cal_settings.update_one({"id": "main"}, {"$set": {"ultima_sync_automatica": _now()}}, upsert=True)
        return {"results": await sync_all("cron", "automatica")}

    @r.get("/settings")
    async def get_settings(admin: dict = Depends(sa)):
        return await settings()

    @r.put("/settings")
    async def put_settings(body: SettingsIn, admin: dict = Depends(sa)):
        d = body.model_dump()
        d["modalita_invio"] = "manuale"  # automatica attivabile solo dalla Fase 4
        await db.cal_settings.update_one({"id": "main"}, {"$set": {**d, "updated_at": _now(), "updated_by": admin.get("email")}}, upsert=True)
        await audit(admin, "cal_settings_update", detail=json.dumps(d))
        return await settings()

    return {"router": r, "ensure_indexes": ensure_indexes, "upsert_event": upsert_event, "cron_tick": cron_tick}
