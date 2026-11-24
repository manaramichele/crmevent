"""Campagna Reels CRMEvent (Super Admin): progetti di montaggio riutilizzabili, rigenerazione con versioni, dati di pubblicazione social."""
import asyncio
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, Field

import storage_utils as SU
import promo_reels_render as RR

HERE = os.path.dirname(__file__)
ASSETS = os.path.join(HERE, "promo_reels", "assets")
MUSIC = os.path.join(HERE, "eventmap_assets", "music")
MANIFEST = os.path.join(HERE, "promo_reels", "v1_manifest.json")
CAMPAIGN = "CAMPAGNA CRMEVENT – PRESENTAZIONE PIATTAFORMA"
OUTRO = {"text": "SCOPRI CRMEVENT", "site": "www.crmevent.it", "dur": 3.8}


def S(asset, crop, dur, label=None):
    return {"asset": asset, "crop": crop, "dur": dur, "label": label}


def C(clip, dur, label=None, start=0):
    return {"clip": clip, "start": start, "dur": dur, "label": label}


EV_LIST = [288, 98, 502, 492]
PIPE = [288, 147, 720, 700]
BRIEF = [288, 425, 512, 445]
HOSP = [288, 98, 620, 620]
ISCR = [288, 98, 620, 620]
KANBAN = [288, 184, 542, 456]
AZ = [288, 233, 600, 700]
VOL = [330, 478, 800, 620]
TURNI = [288, 367, 760, 780]
REELS = [
    {"slug": "presentazione-45", "order": 0, "kind": "principale", "title": "CRMEvent – La piattaforma per i tuoi eventi sportivi",
     "description": "Eventi, staff e volontari, sponsor, mappe e percorsi: tutta l'organizzazione del tuo evento sportivo in un'unica piattaforma. Scopri CRMEvent su www.crmevent.it",
     "hashtags": "#CRMEvent #EventiSportivi #OrganizzazioneEventi #EventManagement #Volontari #Sponsor #Running #Trail #SportEvent",
     "timeline": {"music": "sportiva", "cover_text": "La piattaforma per i tuoi eventi sportivi", "hook": {"text": "ORGANIZZI EVENTI SPORTIVI?", "dur": 3},
                  "sections": [
                      {"text": "TUTTI I TUOI EVENTI, UN'UNICA PIATTAFORMA", "scenes": [S("eventi_list.png", EV_LIST, 2.8, "Elenco eventi"), C("clips/evento_create.mp4", 3.6, "Nuovo evento")]},
                      {"text": "ATTIVITÀ E SCADENZE SOTTO CONTROLLO", "scenes": [S("pipeline.png", PIPE, 3.4, "Pipeline attività")]},
                      {"text": "STAFF E VOLONTARI ORGANIZZATI", "scenes": [S("partecipa.png", [704, 61, 514, 624], 2.4, "Modulo disponibilità"), S("team.png", [288, 233, 814, 759], 2.3, "Team"), S("turni.png", TURNI, 2.3, "Turni e postazioni")]},
                      {"text": "SPONSOR E PARTNER IN PIPELINE", "scenes": [S("aziende.png", AZ, 2.4, "Anagrafica"), S("sponsor_kanban.png", KANBAN, 2.8, "Trattative")]},
                      {"text": "PROGETTA L'EVENTO SULLA MAPPA", "scenes": [C("clips/planner_struct.mp4", 4.4, "Event Planner")]},
                      {"text": "IL PERCORSO DIVENTA UN VIDEO", "scenes": [C("clips/map.mp4", 4.2, "Event Map", start=9)]},
                      {"text": "BRIEFING, OSPITALITÀ E ISCRITTI", "scenes": [S("briefing_top.png", BRIEF, 2.2, "Briefing"), S("ospitalita.png", HOSP, 2.2, "Ospitalità e pasti"), S("iscritti.png", ISCR, 2.2, "Elenco iscritti")]}],
                  "outro": OUTRO}},
    {"slug": "eventi-15", "order": 1, "kind": "breve", "title": "Organizza i tuoi eventi con CRMEvent",
     "description": "Tutti i tuoi eventi in un'unica piattaforma: crea l'evento, organizza le attività con scadenze e tieni tutto sotto controllo. Scopri CRMEvent su www.crmevent.it",
     "hashtags": "#CRMEvent #EventiSportivi #OrganizzazioneEventi #EventPlanning #GestioneEventi #Sport",
     "timeline": {"music": "sportiva", "cover_text": "Organizza i tuoi eventi con CRMEvent", "hook": {"text": "ORGANIZZI EVENTI SPORTIVI?", "dur": 3},
                  "sections": [{"text": "TUTTI I TUOI EVENTI, UN'UNICA PIATTAFORMA", "scenes": [S("eventi_list.png", EV_LIST, 2.4, "Elenco eventi"), C("clips/evento_create.mp4", 3.2, "Nuovo evento"), S("pipeline.png", PIPE, 2.6, "Attività e scadenze")]}],
                  "outro": OUTRO}},
    {"slug": "staff-15", "order": 2, "kind": "breve", "title": "Organizza staff e volontari",
     "description": "Disponibilità raccolte con un modulo pubblico, team con responsabile, ruoli: organizza il tuo team con CRMEvent. www.crmevent.it",
     "hashtags": "#CRMEvent #Volontari #StaffEventi #EventiSportivi #Volontariato #OrganizzazioneEventi",
     "timeline": {"music": "elettronica", "cover_text": "Organizza staff e volontari", "hook": {"text": "GESTIRE I VOLONTARI È COMPLICATO?", "dur": 3},
                  "sections": [{"text": "ORGANIZZA IL TUO TEAM CON CRMEVENT", "scenes": [S("partecipa.png", [704, 61, 514, 624], 2.1, "Disponibilità"), S("volontari.png", VOL, 2.0, "Ruoli e mansioni"), S("team.png", [288, 233, 814, 759], 2.0, "Team"), S("turni.png", TURNI, 2.1, "Assegnazioni")]}],
                  "outro": OUTRO}},
    {"slug": "sponsor-15", "order": 3, "kind": "breve", "title": "Gestisci sponsor e partner",
     "description": "Anagrafica unica, referenti e una pipeline commerciale per fasi collegata ai tuoi eventi: tutte le collaborazioni sotto controllo. www.crmevent.it",
     "hashtags": "#CRMEvent #Sponsor #Partner #Sponsorizzazioni #EventiSportivi #MarketingSportivo",
     "timeline": {"music": "emozionale", "cover_text": "Gestisci sponsor e partner", "hook": {"text": "COME GESTISCI I TUOI SPONSOR?", "dur": 3},
                  "sections": [{"text": "TUTTE LE COLLABORAZIONI SOTTO CONTROLLO", "scenes": [S("aziende.png", AZ, 2.0, "Anagrafica"), S("azienda_dialog.png", [624, 55, 671, 961], 2.0, "Contatti e referenti"), S("sponsor_kanban.png", KANBAN, 2.1, "Trattative"), S("deal_dialog.png", [624, 257, 671, 566], 2.1, "Accordo collegato all'evento")]}],
                  "outro": OUTRO}},
    {"slug": "planner-15", "order": 4, "kind": "breve", "title": "Progetta il tuo evento sulla mappa",
     "description": "Gazebo, transenne, archi e strutture in scala sulla mappa reale del tuo evento: progetta ogni spazio con Event Planner di CRMEvent. www.crmevent.it",
     "hashtags": "#CRMEvent #EventPlanner #Allestimenti #EventiSportivi #EventDesign #OrganizzazioneEventi",
     "timeline": {"music": "cinematografica", "cover_text": "Progetta il tuo evento sulla mappa", "hook": {"text": "COME PROGETTI GLI ALLESTIMENTI?", "dur": 3},
                  "sections": [{"text": "PROGETTA OGNI SPAZIO CON EVENT PLANNER", "scenes": [C("clips/planner_route.mp4", 2.4, "Percorso"), C("clips/planner_struct.mp4", 3.2, "Gazebo e strutture", start=1), C("clips/planner_drag.mp4", 2.6, "Archi e transenne")]}],
                  "outro": OUTRO}},
    {"slug": "map-15", "order": 5, "kind": "breve", "title": "Il tuo percorso prende vita",
     "description": "Dalla traccia GPX a un video animato con tracciato, movimento sulla mappa e profilo altimetrico dinamico: è Event Map di CRMEvent. www.crmevent.it",
     "hashtags": "#CRMEvent #EventMap #GPX #Trail #Running #PercorsoGara #EventiSportivi",
     "timeline": {"music": "cinematografica", "cover_text": "Il tuo percorso prende vita", "hook": {"text": "HAI UN PERCORSO GPX?", "dur": 3},
                  "sections": [{"text": "TRASFORMALO IN UN VIDEO CON EVENT MAP", "scenes": [C("clips/map.mp4", 2.8, "Tracciato animato", start=1), C("clips/map.mp4", 2.7, "Profilo altimetrico", start=9), C("clips/map.mp4", 2.7, "Fino all'arrivo", start=18)]}],
                  "outro": OUTRO}},
    {"slug": "organizzazione-15", "order": 6, "kind": "breve", "title": "Tutto quello che serve per il tuo evento",
     "description": "Attività e scadenze, briefing, percorsi, ospitalità e pasti, elenco iscritti: organizza tutto con CRMEvent. www.crmevent.it",
     "hashtags": "#CRMEvent #OrganizzazioneEventi #EventiSportivi #EventManagement #Briefing #Iscritti",
     "timeline": {"music": "elettronica", "cover_text": "Tutto quello che serve per il tuo evento", "hook": {"text": "TROPPI STRUMENTI PER UN SOLO EVENTO?", "dur": 3},
                  "sections": [{"text": "ORGANIZZA TUTTO CON CRMEVENT", "scenes": [S("pipeline.png", PIPE, 1.7, "Attività e scadenze"), S("briefing_top.png", BRIEF, 1.6, "Briefing"), S("percorsi.png", [577, 43, 766, 643], 1.6, "Percorsi"), S("ospitalita.png", HOSP, 1.6, "Ospitalità e pasti"), S("iscritti.png", ISCR, 1.7, "Elenco iscritti")]}],
                  "outro": OUTRO}},
]

KINDS = {"mp4": ("video.mp4", "video/mp4"), "mp4_nomusic": ("video_nomusic.mp4", "video/mp4"), "cover": ("cover.jpg", "image/jpeg")}


class SceneIn(BaseModel):
    asset: Optional[str] = None
    clip: Optional[str] = None
    crop: Optional[List[int]] = None
    start: float = 0
    dur: float = Field(gt=0.3, le=20)
    label: Optional[str] = Field(default=None, max_length=60)


class SectionIn(BaseModel):
    text: str = Field(min_length=1, max_length=120)
    scenes: List[SceneIn] = Field(min_length=1, max_length=12)


class TimelineIn(BaseModel):
    music: Optional[str] = None
    cover_text: str = Field(default="", max_length=120)
    hook: dict
    sections: List[SectionIn] = Field(min_length=1, max_length=10)
    outro: dict
    transition: float = Field(default=0.35, ge=0, le=1.5)


class MetaIn(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    description: str = Field(default="", max_length=2200)
    hashtags: str = Field(default="", max_length=600)
    publish_status: str = Field(default="da_pubblicare", pattern="^(da_pubblicare|programmato|pubblicato)$")
    publish_date: Optional[str] = Field(default=None, max_length=30)
    link_instagram: Optional[str] = Field(default=None, max_length=500)
    link_facebook: Optional[str] = Field(default=None, max_length=500)
    link_youtube: Optional[str] = Field(default=None, max_length=500)


def _now():
    return datetime.now(timezone.utc).isoformat()


def build(db, deps):
    sa = deps["require_superadmin"]
    router = APIRouter(prefix="/api/promo-reels")
    sem = asyncio.Semaphore(1)

    async def ensure():
        await db.promo_reels.create_index("slug", unique=True)
        man = json.load(open(MANIFEST)) if os.path.exists(MANIFEST) else {}
        for r in REELS:
            await db.promo_reels.update_one({"slug": r["slug"]}, {"$setOnInsert": {**r, "campaign": CAMPAIGN, "publish_status": "da_pubblicare", "publish_date": None,
                                                                              "link_instagram": None, "link_facebook": None, "link_youtube": None,
                                                                              "current_version_id": f"{r['slug']}-v1" if r["slug"] in man else None, "created_at": _now(), "updated_at": _now()}}, upsert=True)
            m = man.get(r["slug"])
            if m:
                files = {k: {"static": f"/media/reels/{r['slug']}-v1{suf}"} for k, suf in (("mp4", ".mp4"), ("mp4_nomusic", "-nomusic.mp4"), ("cover", "-cover.jpg"))}
                await db.promo_reel_versions.update_one({"id": f"{r['slug']}-v1"}, {"$setOnInsert": {"slug": r["slug"], "version": 1, "status": "completed", "files": files,
                                                                                                   "duration": m["duration"], "size": m.get("size"), "timeline": r["timeline"],
                                                                                                   "created_at": m.get("created_at") or _now(), "created_by": "sistema"}}, upsert=True)
                await db.promo_reels.update_one({"slug": r["slug"], "current_version_id": None}, {"$set": {"current_version_id": f"{r['slug']}-v1"}})
        await db.promo_reel_versions.update_many({"status": {"$in": ["queued", "processing"]}}, {"$set": {"status": "error", "error": "Rigenerazione interrotta dal riavvio del server: riprova"}})

    def _url(vid, slug, kind, f):
        return f["static"] if f.get("static") else f"/api/promo-reels/{slug}/versions/{vid}/file/{kind}"

    def _pub_version(v):
        return {**{k: v.get(k) for k in ("id", "version", "status", "progress", "duration", "size", "created_at", "created_by", "error")},
                "urls": {k: _url(v["id"], v["slug"], k, f) for k, f in (v.get("files") or {}).items()}}

    async def _reel(slug):
        r = await db.promo_reels.find_one({"slug": slug}, {"_id": 0})
        if not r:
            raise HTTPException(status_code=404, detail="Video non trovato")
        return r

    @router.get("")
    async def list_reels(_: dict = Depends(sa)):
        reels = await db.promo_reels.find({}, {"_id": 0}).sort("order", 1).to_list(50)
        for r in reels:
            vs = await db.promo_reel_versions.find({"slug": r["slug"]}, {"_id": 0}).sort("version", -1).to_list(50)
            r["versions"] = [_pub_version(v) for v in vs]
        return {"campaign": CAMPAIGN, "reels": reels, "assets": sorted(os.listdir(ASSETS)) + sorted("clips/" + c for c in os.listdir(os.path.join(ASSETS, "clips"))),
                "music": sorted(m[:-4] for m in os.listdir(MUSIC) if m.endswith(".mp3"))}

    @router.put("/{slug}")
    async def update_meta(slug: str, body: MetaIn, user: dict = Depends(sa)):
        await _reel(slug)
        await db.promo_reels.update_one({"slug": slug}, {"$set": {**body.model_dump(), "updated_at": _now(), "updated_by": user.get("email")}})
        return await _reel(slug)

    @router.put("/{slug}/timeline")
    async def update_timeline(slug: str, body: TimelineIn, user: dict = Depends(sa)):
        await _reel(slug)
        tl = body.model_dump()
        names = set(os.listdir(ASSETS)) | {"clips/" + c for c in os.listdir(os.path.join(ASSETS, "clips"))}
        for sec in tl["sections"]:
            for sc in sec["scenes"]:
                src = sc.get("clip") or sc.get("asset")
                if not src or src not in names or (sc.get("clip") and not src.startswith("clips/")):
                    raise HTTPException(status_code=422, detail=f"Elemento non disponibile: {src}")
                if sc.get("crop") is not None and (len(sc["crop"]) != 4 or min(sc["crop"]) < 0 or sc["crop"][2] < 50 or sc["crop"][3] < 50):
                    raise HTTPException(status_code=422, detail="Ritaglio non valido: servono x, y, larghezza, altezza")
        if tl.get("music") and not os.path.exists(os.path.join(MUSIC, f"{tl['music']}.mp3")):
            raise HTTPException(status_code=422, detail="Musica non disponibile")
        for part in ("hook", "outro"):
            try:
                dur = float(tl[part].get("dur", 0))
            except (TypeError, ValueError):
                dur = -1
            if not str(tl[part].get("text", "")).strip() or not (0.5 <= dur <= 10):
                raise HTTPException(status_code=422, detail=f"Testo o durata non validi per {part}")
        await db.promo_reels.update_one({"slug": slug}, {"$set": {"timeline": tl, "updated_at": _now(), "updated_by": user.get("email")}})
        return await _reel(slug)

    async def _process(vid):
        async with sem:
            v = await db.promo_reel_versions.find_one({"id": vid}, {"_id": 0})
            await db.promo_reel_versions.update_one({"id": vid}, {"$set": {"status": "processing", "progress": 0}})
            loop = asyncio.get_running_loop()
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    async def _set_progress(n):
                        await db.promo_reel_versions.update_one({"id": vid}, {"$set": {"progress": n}})

                    def prog(n):
                        asyncio.run_coroutine_threadsafe(_set_progress(n), loop)
                    out = await asyncio.to_thread(RR.render, v["timeline"], ASSETS, tmp, MUSIC, prog)
                    files, size = {}, 0
                    for k, (fn, ct) in KINDS.items():
                        data = open(out[k], "rb").read()
                        size += len(data) if k == "mp4" else 0
                        files[k] = {"storage": SU.save(f"promo_reels/{v['slug']}/v{v['version']}-{fn}", data, ct)}
                await db.promo_reel_versions.update_one({"id": vid}, {"$set": {"status": "completed", "progress": 100, "files": files, "duration": out["duration"], "size": size, "completed_at": _now()}})
                await db.promo_reels.update_one({"slug": v["slug"]}, {"$set": {"current_version_id": vid}})
            except Exception as e:
                await db.promo_reel_versions.update_one({"id": vid}, {"$set": {"status": "error", "error": f"Rigenerazione non riuscita: {str(e)[:200]}"}})

    @router.post("/{slug}/render")
    async def render(slug: str, user: dict = Depends(sa)):
        r = await _reel(slug)
        if await db.promo_reel_versions.find_one({"slug": slug, "status": {"$in": ["queued", "processing"]}}):
            raise HTTPException(status_code=409, detail="Rigenerazione già in corso per questo video")
        last = await db.promo_reel_versions.find_one({"slug": slug}, {"_id": 0, "version": 1}, sort=[("version", -1)])
        vid = uuid.uuid4().hex
        doc = {"id": vid, "slug": slug, "version": (last or {}).get("version", 0) + 1, "status": "queued", "timeline": r["timeline"], "created_at": _now(), "created_by": user.get("email")}
        await db.promo_reel_versions.insert_one(doc)
        asyncio.create_task(_process(vid))
        return _pub_version(doc)

    @router.post("/{slug}/versions/{vid}/current")
    async def set_current(slug: str, vid: str, _: dict = Depends(sa)):
        v = await db.promo_reel_versions.find_one({"id": vid, "slug": slug, "status": "completed"})
        if not v:
            raise HTTPException(status_code=404, detail="Versione non disponibile")
        await db.promo_reels.update_one({"slug": slug}, {"$set": {"current_version_id": vid}})
        return {"ok": True}

    @router.get("/{slug}/versions/{vid}/file/{kind}")
    async def file(slug: str, vid: str, kind: str, download: int = 0, _: dict = Depends(sa)):
        v = await db.promo_reel_versions.find_one({"id": vid, "slug": slug, "status": "completed"}, {"_id": 0})
        f = (v or {}).get("files", {}).get(kind)
        if not f:
            raise HTTPException(status_code=404, detail="File non trovato")
        if f.get("static"):
            return RedirectResponse(f["static"])
        data, _ct = SU.read(f["storage"]["path"], f["storage"].get("backend"))
        ext = "jpg" if kind == "cover" else "mp4"
        hdr = {"Content-Disposition": f'attachment; filename="crmevent-{slug}-v{v["version"]}{"-senza-musica" if kind == "mp4_nomusic" else ""}.{ext}"'} if download else {}
        return Response(content=data, media_type=KINDS[kind][1], headers=hdr)

    return {"router": router, "ensure": ensure}
