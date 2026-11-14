"""Event Map — tracce GPX, anteprime e generazione video MP4 in coda (processo separato con FFmpeg)."""
import asyncio
import json
import logging
import os
import re
import sys
import tempfile
import uuid
from datetime import date, datetime, timezone
from typing import List, Optional

import imageio_ffmpeg
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

import eventmap_render as ER
import storage_utils as SU

logger = logging.getLogger("eventmap")
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.environ.get("EVENTMAP_CACHE_DIR") or os.path.join(tempfile.gettempdir(), "eventmap_cache")
MUSIC = {"sportiva": "Sportiva ed energica", "emozionale": "Emozionale", "elettronica": "Elettronica", "cinematografica": "Cinematografica"}
STYLES = {"dark": "Scuro", "streets": "Stradale"}
DURATIONS = (15, 30, 60)
SPEEDS = {"slow": ("Lenta", "Movimento panoramico e dettagliato"), "normal": ("Normale", "Movimento equilibrato"), "fast": ("Veloce", "Movimento dinamico e sportivo")}
MAX_GPX = 15 * 1024 * 1024
MAX_LOGO = 5 * 1024 * 1024
STATUS = ("queued", "processing", "completed", "error")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class VideoIn(BaseModel):
    track_id: str
    style: str = "dark"
    format: str = "9:16"
    duration: int = 30
    music: Optional[str] = None
    logo: Optional[str] = "event"  # "event" = logo dell'anagrafica, id di un logo caricato, None = senza logo
    speed: str = "normal"
    show_aid: bool = True
    show_elevation: bool = True


class PreviewIn(BaseModel):
    style: str = "dark"
    format: str = "9:16"
    logo: Optional[str] = "event"
    speed: str = "normal"
    show_aid: bool = True
    show_elevation: bool = True


class SettingsIn(BaseModel):
    date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")  # None = data dell'anagrafica

    @field_validator("date")
    @classmethod
    def _real_date(cls, v):
        if v:
            date.fromisoformat(v)  # ValueError -> 422 per date impossibili (es. 2026-02-31)
        return v


class AidIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    km: float = Field(ge=0)
    desc: str = Field(default="", max_length=120)
    source: str = "manual"


class AidListIn(BaseModel):
    items: List[AidIn] = Field(default_factory=list, max_length=30)


def build(db, deps: dict):
    r = APIRouter(prefix="/api/eventmap")
    admin_dep, audit, addons = deps["require_admin"], deps["record_audit"], deps["addons"]
    sem = asyncio.Semaphore(int(os.environ.get("EVENTMAP_CONCURRENCY", "1")))
    locks: dict = {}
    tasks: set = set()

    async def ensure():
        await db.eventmap_tracks.create_index([("org_id", 1), ("event_id", 1)])
        await db.eventmap_logos.create_index([("org_id", 1), ("event_id", 1)])
        await db.eventmap_settings.create_index([("org_id", 1), ("event_id", 1)], unique=True)
        await db.eventmap_videos.create_index([("org_id", 1), ("event_id", 1), ("created_at", -1)])
        await db.eventmap_videos.update_many({"status": {"$in": ["queued", "processing"]}},
                                             {"$set": {"status": "error", "error": "Elaborazione interrotta dal riavvio del server: riprova (nessun video scalato)"}})

    async def _event(org_id, eid):
        ev = await db.events.find_one({"org_id": org_id, "id": eid}, {"_id": 0, "id": 1, "nome": 1, "data_inizio": 1, "logo_url": 1})
        if not ev:
            raise HTTPException(status_code=404, detail="Evento non trovato")
        return ev

    async def _rights(org_id, eid):
        s = await addons["summary"](org_id, "eventmap")
        on = s["unrestricted"] or any(a["event_id"] == eid and a["covered"] for a in s["activations"])
        inflight = s["videos_in_progress"]
        now = _now()
        valid = [g for g in s["grants"] if g.get("status") == "active" and (not g.get("expires_at") or g["expires_at"] > now)]
        if s["unrestricted"] or s["included_used"] > 0 or any(not g.get("formats") for g in valid):
            formats = list(ER.SIZES)
        else:
            formats = sorted({f for g in valid for f in g.get("formats") or []} & set(ER.SIZES))
        remaining = None if s["unrestricted"] else s["videos_available"]
        return {"active": on, "unrestricted": s["unrestricted"], "videos_total": s.get("videos_total", 0), "videos_used": s.get("videos_used", 0),
                "in_progress": inflight, "videos_remaining": remaining, "formats": formats,
                "expires_at": min([g["expires_at"] for g in valid if g.get("expires_at")], default=None)}

    def _date_it(d):
        mesi = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", d or "")
        return f"{int(m.group(3))} {mesi[int(m.group(2)) - 1]} {m.group(1)}" if m and 1 <= int(m.group(2)) <= 12 and 1 <= int(m.group(3)) <= 31 else ""

    @r.get("/options")
    async def options(user: dict = Depends(admin_dep)):
        return {"styles": [{"key": k, "label": v} for k, v in STYLES.items()] + [{"key": "satellite", "label": "Satellitare", "disabled": True, "note": "Disponibile con MapTiler"}],
                "formats": [{"key": "9:16", "label": "9:16 · Reels, Stories, TikTok"}, {"key": "1:1", "label": "1:1 · Post social"}, {"key": "16:9", "label": "16:9 · YouTube, Facebook, siti web"}],
                "durations": list(DURATIONS), "music": [{"key": k, "label": v, "preview": f"/media/music/{k}.mp3"} for k, v in MUSIC.items()],
                "speeds": [{"key": k, "label": v[0], "note": v[1]} for k, v in SPEEDS.items()]}

    async def _settings(org_id, eid):
        return await db.eventmap_settings.find_one({"org_id": org_id, "event_id": eid}, {"_id": 0, "org_id": 0}) or {"date": None}

    async def _upgrade_track(t):
        """Tracce caricate prima di altimetria/ristori: dati ricalcolati una volta dal GPX salvato."""
        if "has_elevation" in t:
            return t
        try:
            sm = ER.summary(SU.read(t["storage"]["path"], t["storage"].get("backend"))[0])
        except Exception:
            return t
        upd = {k: sm[k] for k in ("has_elevation", "ele_min", "ele_max", "ele_gain", "aid_detected", "waypoints") if k in sm}
        await db.eventmap_tracks.update_one({"id": t["id"]}, {"$set": upd})
        return {**t, **upd}

    def _aid_list(t):
        return t["aid_stations"] if "aid_stations" in t else (t.get("aid_detected") or [])

    @r.put("/events/{eid}/settings")
    async def put_settings(eid: str, body: SettingsIn, user: dict = Depends(admin_dep)):
        await _event(user["org_id"], eid)
        await _require_active(user["org_id"], eid)
        await db.eventmap_settings.update_one({"org_id": user["org_id"], "event_id": eid},
                                              {"$set": {"date": body.date, "updated_at": _now(), "updated_by": user.get("email")}}, upsert=True)
        return await _settings(user["org_id"], eid)

    @r.put("/tracks/{tid}/aid-stations")
    async def put_aid(tid: str, body: AidListIn, user: dict = Depends(admin_dep)):
        t = await _track(user["org_id"], tid)
        await _require_active(user["org_id"], t["event_id"])
        tot = t["distance_m"] / 1000
        pts, _, _ = ER.parse_gpx(SU.read(t["storage"]["path"], t["storage"].get("backend"))[0])
        dist = ER.cumdist(pts)
        items = []
        for a in sorted(body.items, key=lambda x: x.km):
            if a.km > tot + 0.01:
                raise HTTPException(status_code=400, detail=f"Il ristoro «{a.name}» è oltre la lunghezza del percorso ({tot:.2f} km)".replace(".", ","))
            lat, lon = ER.locate(pts, dist, a.km * 1000)
            items.append({"name": a.name.strip(), "km": round(a.km, 2), "desc": a.desc.strip(), "lat": round(lat, 6), "lon": round(lon, 6),
                          "source": "gpx" if a.source == "gpx" else "manual"})
        await db.eventmap_tracks.update_one({"id": tid, "org_id": user["org_id"]}, {"$set": {"aid_stations": items}})
        await audit(user, "eventmap_aid_update", detail=f"{t['event_id']} · {len(items)} ristori")
        return {"aid_stations": items}

    @r.get("/events/{eid}")
    async def event_state(eid: str, user: dict = Depends(admin_dep)):
        ev = await _event(user["org_id"], eid)
        maps = await db.event_maps.find({"org_id": user["org_id"], "evento_id": eid, "gpx_url": {"$nin": [None, ""]}}, {"_id": 0, "id": 1, "nome": 1, "titolo": 1}).to_list(100)
        sett = await _settings(user["org_id"], eid)
        tracks = [await _upgrade_track(t) for t in await db.eventmap_tracks.find({"org_id": user["org_id"], "event_id": eid}, {"_id": 0}).sort("created_at", -1).to_list(50)]
        for t in tracks:
            t["aid_stations"] = _aid_list(t)
            t.pop("storage", None)
            t.pop("preview", None)
        return {"event": {"id": ev["id"], "nome": ev.get("nome"), "data": _date_it(sett.get("date") or ev.get("data_inizio")), "data_iso": (ev.get("data_inizio") or "")[:10],
                          "has_logo": bool(ev.get("logo_url"))}, "settings": sett,
                "rights": await _rights(user["org_id"], eid), "maps": maps,
                "tracks": tracks,
                "logos": await db.eventmap_logos.find({"org_id": user["org_id"], "event_id": eid}, {"_id": 0, "storage": 0}).sort("created_at", -1).to_list(20),
                "videos": await db.eventmap_videos.find({"org_id": user["org_id"], "event_id": eid}, {"_id": 0, "storage": 0, "job": 0}).sort("created_at", -1).to_list(100)}

    async def _require_active(org_id, eid):
        if not (await _rights(org_id, eid))["active"]:
            raise HTTPException(status_code=403, detail={"code": "addon_required", "product": "eventmap", "slug": "event-map",
                                                         "message": "Event Map non è attivo per questo evento: attivalo dal Marketplace"})

    async def _save_track(user, eid, data: bytes, name: str):
        await _require_active(user["org_id"], eid)
        if len(data) > MAX_GPX:
            raise HTTPException(status_code=400, detail="File GPX troppo grande (max 15 MB)")
        try:
            sm = ER.summary(data)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"GPX non valido: {e}" if isinstance(e, ValueError) else "GPX non valido: il file non è leggibile")
        tid = uuid.uuid4().hex
        st = SU.save(f"eventmap/{user['org_id']}/{eid}/{tid}.gpx", data, "application/gpx+xml")
        doc = {"id": tid, "org_id": user["org_id"], "event_id": eid, "name": name[:120], "storage": st, **sm, "created_by": user.get("email"), "created_at": _now()}
        await db.eventmap_tracks.insert_one({**doc})
        await audit(user, "eventmap_track_upload", detail=f"{eid} · {name} · {sm['distance_m']} m")
        return {k: v for k, v in doc.items() if k != "storage"}

    @r.post("/events/{eid}/tracks")
    async def upload_track(eid: str, file: UploadFile = File(...), user: dict = Depends(admin_dep)):
        await _event(user["org_id"], eid)
        if not (file.filename or "").lower().endswith(".gpx"):
            raise HTTPException(status_code=400, detail="Carica un file con estensione .gpx")
        return await _save_track(user, eid, await file.read(MAX_GPX + 1), file.filename)

    @r.post("/events/{eid}/tracks/from-map/{map_id}")
    async def track_from_map(eid: str, map_id: str, user: dict = Depends(admin_dep)):
        await _event(user["org_id"], eid)
        mp = await db.event_maps.find_one({"org_id": user["org_id"], "evento_id": eid, "id": map_id}, {"_id": 0})
        rec = await deps["resolve_attachment"](mp.get("gpx_url"), user["org_id"]) if mp else None
        if not rec or not rec.get("storage_path"):
            raise HTTPException(status_code=404, detail="Traccia GPX dell'evento non trovata")
        data, _ = await deps["read_file_rec"](rec)
        return await _save_track(user, eid, data, mp.get("nome") or mp.get("titolo") or rec.get("original_filename") or "Percorso evento")

    async def _track(org_id, tid):
        t = await db.eventmap_tracks.find_one({"org_id": org_id, "id": tid}, {"_id": 0})
        if not t:
            raise HTTPException(status_code=404, detail="Traccia non trovata")
        return t

    async def _logo_bytes(org_id, ev, choice):
        if not choice:
            return None
        if choice == "event":
            if not ev.get("logo_url"):
                return None
            fid = ev["logo_url"].rstrip("/").split("/")[-1]
            rec = await db.files.find_one({"org_id": org_id, "$or": [{"id": fid}, {"public_token": fid}], "is_deleted": {"$ne": True}}, {"_id": 0})
            if not rec:
                return None
            try:
                return (await deps["read_file_rec"](rec))[0]
            except Exception:
                return None
        lg = await db.eventmap_logos.find_one({"org_id": org_id, "event_id": ev["id"], "id": choice}, {"_id": 0})
        if not lg:
            raise HTTPException(status_code=404, detail="Logo non trovato")
        return SU.read(lg["storage"]["path"], lg["storage"].get("backend"))[0]

    @r.post("/events/{eid}/logos")
    async def upload_logo(eid: str, file: UploadFile = File(...), user: dict = Depends(admin_dep)):
        await _event(user["org_id"], eid)
        await _require_active(user["org_id"], eid)
        data = await file.read(MAX_LOGO + 1)
        if len(data) > MAX_LOGO:
            raise HTTPException(status_code=400, detail="Logo troppo grande (max 5 MB)")
        try:
            from PIL import Image
            import io
            im = Image.open(io.BytesIO(data))
            if im.format != "PNG":
                raise ValueError
            im = im.convert("RGBA")
            im.thumbnail((1600, 1600))
            buf = io.BytesIO()
            im.save(buf, "PNG")
        except Exception:
            raise HTTPException(status_code=400, detail="Carica un'immagine PNG valida (preferibilmente con sfondo trasparente)")
        lid = uuid.uuid4().hex
        st = SU.save(f"eventmap/{user['org_id']}/{eid}/logo-{lid}.png", buf.getvalue(), "image/png")
        transparent = im.getchannel("A").getextrema()[0] < 255
        doc = {"id": lid, "org_id": user["org_id"], "event_id": eid, "name": (file.filename or "logo.png")[:120], "width": im.width, "height": im.height,
               "transparent": transparent, "storage": st, "created_by": user.get("email"), "created_at": _now()}
        await db.eventmap_logos.insert_one({**doc})
        await audit(user, "eventmap_logo_upload", detail=f"{eid} · {doc['name']}")
        return {k: v for k, v in doc.items() if k not in ("storage", "org_id")}

    @r.delete("/events/{eid}/logos/{lid}")
    async def delete_logo(eid: str, lid: str, user: dict = Depends(admin_dep)):
        lg = await db.eventmap_logos.find_one_and_delete({"org_id": user["org_id"], "event_id": eid, "id": lid}, {"_id": 0})
        if not lg:
            raise HTTPException(status_code=404, detail="Logo non trovato")
        await audit(user, "eventmap_logo_delete", detail=f"{eid} · {lg.get('name')}")
        return {"ok": True}

    @r.get("/events/{eid}/logos/{lid}/image")
    async def logo_image(eid: str, lid: str, user: dict = Depends(admin_dep)):
        ev = await _event(user["org_id"], eid)
        data = await _logo_bytes(user["org_id"], ev, lid)
        if not data:
            raise HTTPException(status_code=404, detail="Logo non disponibile")
        return Response(content=data, media_type="image/png" if data[:4] == b"\x89PNG" else "image/jpeg", headers={"Cache-Control": "private, max-age=300"})

    async def _job_files(tmp, t, ev, logo_choice="event"):
        gpx = os.path.join(tmp, "track.gpx")
        data, _ = SU.read(t["storage"]["path"], t["storage"].get("backend"))
        open(gpx, "wb").write(data)
        b = await _logo_bytes(t["org_id"], ev, logo_choice)
        logo = None
        if b:
            logo = os.path.join(tmp, "logo.img")
            open(logo, "wb").write(b)
        return gpx, logo

    async def _run(job: dict, on_progress=None) -> tuple:
        path = os.path.join(os.path.dirname(job["out_path"]), "job.json")
        json.dump(job, open(path, "w"))
        p = await asyncio.create_subprocess_exec("nice", "-n", "10", sys.executable, os.path.join(HERE, "eventmap_render.py"), path,
                                                 stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, cwd=HERE)
        err = None
        async for line in p.stdout:
            s = line.decode(errors="ignore").strip()
            if s.startswith("PROGRESS") and on_progress:
                await on_progress(int(s.split()[1]))
            elif s.startswith("ERROR"):
                err = s[6:]
        code = await p.wait()
        return code == 0 and os.path.exists(job["out_path"]), err

    def _base_job(t, ev, style, fmt, tmp, gpx, logo, opts):
        return {"gpx_path": gpx, "style": style, "format": fmt, "title": ev.get("nome"), "date": _date_it(opts.get("date") or ev.get("data_inizio")),
                "logo_path": logo, "cache_dir": CACHE, "ffmpeg": imageio_ffmpeg.get_ffmpeg_exe(), "speed": opts.get("speed") or "normal",
                "show_aid": opts.get("show_aid", True), "show_elevation": opts.get("show_elevation", True), "aid_stations": opts.get("aid_stations") or []}

    @r.post("/tracks/{tid}/preview")
    async def preview(tid: str, body: PreviewIn, user: dict = Depends(admin_dep)):
        t = await _track(user["org_id"], tid)
        ev = await _event(user["org_id"], t["event_id"])
        await _require_active(user["org_id"], t["event_id"])
        if body.style not in STYLES or body.format not in ER.SIZES or body.speed not in SPEEDS:
            raise HTTPException(status_code=400, detail="Stile o formato non valido")
        t = await _upgrade_track(t)
        opts = {"date": (await _settings(user["org_id"], t["event_id"])).get("date"), "speed": body.speed, "show_aid": body.show_aid,
                "show_elevation": body.show_elevation, "aid_stations": _aid_list(t)}
        with tempfile.TemporaryDirectory() as tmp:
            gpx, logo = await _job_files(tmp, t, ev, body.logo)
            job = {**_base_job(t, ev, body.style, body.format, tmp, gpx, logo, opts), "still": True, "out_path": os.path.join(tmp, "preview.jpg")}
            ok, err = await _run(job)
            if not ok:
                raise HTTPException(status_code=500, detail=f"Anteprima non riuscita{': ' + err if err else ''}")
            return Response(content=open(job["out_path"], "rb").read(), media_type="image/jpeg")

    async def _process(vid: str):
        async with sem:
            v = await db.eventmap_videos.find_one({"id": vid, "status": "queued"}, {"_id": 0})
            if not v:
                return
            await db.eventmap_videos.update_one({"id": vid}, {"$set": {"status": "processing", "started_at": _now(), "progress": 0}})
            try:
                t = await _track(v["org_id"], v["track_id"])
                ev = await _event(v["org_id"], v["event_id"])
                with tempfile.TemporaryDirectory() as tmp:
                    gpx, logo = await _job_files(tmp, t, ev, v.get("logo", "event"))
                    if v.get("logo") and not logo:
                        raise RuntimeError("logo non disponibile")
                    job = {**_base_job(t, ev, v["style"], v["format"], tmp, gpx, logo, v), "duration": v["duration"], "out_path": os.path.join(tmp, "video.mp4"),
                           "music_path": os.path.join(HERE, "eventmap_assets", "music", f"{v['music']}.mp3") if v.get("music") else None}

                    async def prog(n):
                        await db.eventmap_videos.update_one({"id": vid}, {"$set": {"progress": n}})
                    ok, err = await _run(job, prog)
                    if not ok:
                        raise RuntimeError(err or "rendering non riuscito")
                    data = open(job["out_path"], "rb").read()
                st = SU.save(f"eventmap/{v['org_id']}/{v['event_id']}/{vid}.mp4", data, "video/mp4")
                res = await db.eventmap_videos.update_one({"id": vid, "status": "processing", "consumed": {"$ne": True}},
                                                          {"$set": {"status": "completed", "progress": 100, "storage": st, "size": len(data), "completed_at": _now(), "consumed": True}})
                if res.modified_count:  # il video si scala solo a MP4 salvato, una sola volta
                    await db.addon_usage.update_one({"org_id": v["org_id"], "product": "eventmap"}, {"$inc": {"videos_used": 1}}, upsert=True)
            except Exception as e:
                logger.error(f"eventmap render {vid}: {e}")
                await db.eventmap_videos.update_one({"id": vid}, {"$set": {"status": "error", "completed_at": _now(),
                                                                    "error": "Generazione non riuscita: il video non è stato scalato, riprova o carica di nuovo la traccia GPX."}})

    @r.post("/events/{eid}/videos")
    async def create_video(eid: str, body: VideoIn, user: dict = Depends(admin_dep)):
        await _event(user["org_id"], eid)
        t = await _track(user["org_id"], body.track_id)
        if t["event_id"] != eid:
            raise HTTPException(status_code=400, detail="La traccia appartiene a un altro evento")
        if body.style not in STYLES or body.format not in ER.SIZES or body.duration not in DURATIONS or (body.music and body.music not in MUSIC) or body.speed not in SPEEDS:
            raise HTTPException(status_code=400, detail="Opzioni video non valide")
        ev = await _event(user["org_id"], eid)
        if body.logo and body.logo != "event":
            await _logo_bytes(user["org_id"], ev, body.logo)
        elif body.logo == "event" and not await _logo_bytes(user["org_id"], ev, "event"):
            body.logo = None  # logo in anagrafica non leggibile: video senza logo invece di un errore in coda
        lock = locks.setdefault(user["org_id"], asyncio.Lock())
        async with lock:
            rg = await _rights(user["org_id"], eid)
            if not rg["active"]:
                raise HTTPException(status_code=403, detail={"code": "addon_required", "product": "eventmap", "slug": "event-map",
                                                             "message": "Event Map non è attivo per questo evento: attivalo dal Marketplace"})
            if body.format not in rg["formats"]:
                raise HTTPException(status_code=403, detail="Formato non incluso nel tuo pacchetto Event Map")
            if rg["videos_remaining"] is not None and rg["videos_remaining"] <= 0:
                raise HTTPException(status_code=403, detail={"code": "addon_videos", "message": "Non hai video disponibili: acquista un pacchetto Event Map nel Marketplace"})
            vid = uuid.uuid4().hex
            t = await _upgrade_track(t)
            # impostazioni fotografate alla richiesta: modifiche successive non cambiano i video già in coda
            doc = {"id": vid, "org_id": user["org_id"], "event_id": eid, "track_id": t["id"], "track_name": t.get("name"), "distance_m": t["distance_m"],
                   "style": body.style, "format": body.format, "duration": body.duration, "music": body.music, "logo": body.logo,
                   "date": (await _settings(user["org_id"], eid)).get("date"), "speed": body.speed, "show_aid": body.show_aid,
                   "show_elevation": body.show_elevation and bool(t.get("has_elevation")), "aid_stations": _aid_list(t) if body.show_aid else [],
                   "status": "queued", "progress": 0,
                   "created_by": user.get("email"), "created_at": _now()}
            await db.eventmap_videos.insert_one({**doc})
        task = asyncio.create_task(_process(vid))
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        await audit(user, "eventmap_video_request", detail=f"{eid} · {body.format} · {body.duration}s · {body.music or 'senza musica'}")
        return {k: v for k, v in doc.items() if k != "org_id"}

    @r.get("/videos/{vid}")
    async def video_status(vid: str, user: dict = Depends(admin_dep)):
        v = await db.eventmap_videos.find_one({"org_id": user["org_id"], "id": vid}, {"_id": 0, "storage": 0, "job": 0})
        if not v:
            raise HTTPException(status_code=404, detail="Video non trovato")
        return v

    @r.get("/videos/{vid}/file")
    async def video_file(vid: str, request: Request, download: int = 0, user: dict = Depends(admin_dep)):
        v = await db.eventmap_videos.find_one({"org_id": user["org_id"], "id": vid, "status": "completed"}, {"_id": 0})
        if not v:
            raise HTTPException(status_code=404, detail="Video non disponibile")
        data, _ = SU.read(v["storage"]["path"], v["storage"].get("backend"))
        base = re.sub(r"\.gpx$", "", v.get("track_name") or "percorso", flags=re.I)
        name = re.sub(r"[^A-Za-z0-9_-]+", "-", f"event-map-{base}-{v['format'].replace(':', 'x')}-{v['duration']}s").strip("-")
        disp = "attachment" if download else "inline"
        hdr = {"Content-Disposition": f'{disp}; filename="{name}.mp4"', "Accept-Ranges": "bytes"}
        m = re.match(r"bytes=(\d*)-(\d*)", request.headers.get("range") or "")
        if m and (m.group(1) or m.group(2)):  # Safari/iPhone richiedono risposte 206
            n = len(data)
            a, b = (int(m.group(1)), int(m.group(2) or n - 1)) if m.group(1) else (n - int(m.group(2)), n - 1)
            a, b = max(0, a), min(b, n - 1)
            return Response(content=data[a:b + 1], status_code=206, media_type="video/mp4", headers={**hdr, "Content-Range": f"bytes {a}-{b}/{n}"})
        return Response(content=data, media_type="video/mp4", headers=hdr)

    return {"router": r, "ensure": ensure}
