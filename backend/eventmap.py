"""Event Map — tracce GPX, anteprime e generazione video MP4 in coda (processo separato con FFmpeg)."""
import asyncio
import json
import logging
import os
import re
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Optional

import imageio_ffmpeg
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

import eventmap_render as ER
import storage_utils as SU

logger = logging.getLogger("eventmap")
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.environ.get("EVENTMAP_CACHE_DIR") or os.path.join(tempfile.gettempdir(), "eventmap_cache")
MUSIC = {"sportiva": "Sportiva ed energica", "emozionale": "Emozionale", "elettronica": "Elettronica", "cinematografica": "Cinematografica"}
STYLES = {"dark": "Scuro", "streets": "Stradale"}
DURATIONS = (15, 30, 60)
MAX_GPX = 15 * 1024 * 1024
STATUS = ("queued", "processing", "completed", "error")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class VideoIn(BaseModel):
    track_id: str
    style: str = "dark"
    format: str = "9:16"
    duration: int = 30
    music: Optional[str] = None


class PreviewIn(BaseModel):
    style: str = "dark"
    format: str = "9:16"


def build(db, deps: dict):
    r = APIRouter(prefix="/api/eventmap")
    admin_dep, audit, addons = deps["require_admin"], deps["record_audit"], deps["addons"]
    sem = asyncio.Semaphore(int(os.environ.get("EVENTMAP_CONCURRENCY", "1")))
    locks: dict = {}
    tasks: set = set()

    async def ensure():
        await db.eventmap_tracks.create_index([("org_id", 1), ("event_id", 1)])
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
        inflight = await db.eventmap_videos.count_documents({"org_id": org_id, "status": {"$in": ["queued", "processing"]}})
        now = _now()
        valid = [g for g in s["grants"] if g.get("status") == "active" and (not g.get("expires_at") or g["expires_at"] > now)]
        if s["unrestricted"] or s["included_used"] > 0 or any(not g.get("formats") for g in valid):
            formats = list(ER.SIZES)
        else:
            formats = sorted({f for g in valid for f in g.get("formats") or []} & set(ER.SIZES))
        remaining = None if s["unrestricted"] else max(0, s["videos_total"] - s["videos_used"] - inflight)
        return {"active": on, "unrestricted": s["unrestricted"], "videos_total": s.get("videos_total", 0), "videos_used": s.get("videos_used", 0),
                "in_progress": inflight, "videos_remaining": remaining, "formats": formats,
                "expires_at": min([g["expires_at"] for g in valid if g.get("expires_at")], default=None)}

    def _date_it(d):
        mesi = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", d or "")
        return f"{int(m.group(3))} {mesi[int(m.group(2)) - 1]} {m.group(1)}" if m else ""

    @r.get("/options")
    async def options(user: dict = Depends(admin_dep)):
        return {"styles": [{"key": k, "label": v} for k, v in STYLES.items()] + [{"key": "satellite", "label": "Satellitare", "disabled": True, "note": "Disponibile con MapTiler"}],
                "formats": [{"key": "9:16", "label": "9:16 · Reels, Stories, TikTok"}, {"key": "1:1", "label": "1:1 · Post social"}, {"key": "16:9", "label": "16:9 · YouTube, Facebook, siti web"}],
                "durations": list(DURATIONS), "music": [{"key": k, "label": v, "preview": f"/media/music/{k}.mp3"} for k, v in MUSIC.items()]}

    @r.get("/events/{eid}")
    async def event_state(eid: str, user: dict = Depends(admin_dep)):
        ev = await _event(user["org_id"], eid)
        maps = await db.event_maps.find({"org_id": user["org_id"], "evento_id": eid, "gpx_url": {"$nin": [None, ""]}}, {"_id": 0, "id": 1, "nome": 1, "titolo": 1}).to_list(100)
        return {"event": {"id": ev["id"], "nome": ev.get("nome"), "data": _date_it(ev.get("data_inizio")), "has_logo": bool(ev.get("logo_url"))},
                "rights": await _rights(user["org_id"], eid), "maps": maps,
                "tracks": await db.eventmap_tracks.find({"org_id": user["org_id"], "event_id": eid}, {"_id": 0, "storage": 0}).sort("created_at", -1).to_list(50),
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

    async def _job_files(tmp, t, ev):
        gpx = os.path.join(tmp, "track.gpx")
        data, _ = SU.read(t["storage"]["path"], t["storage"].get("backend"))
        open(gpx, "wb").write(data)
        logo = None
        if ev.get("logo_url"):
            try:
                fid = ev["logo_url"].rstrip("/").split("/")[-1]
                rec = await db.files.find_one({"$or": [{"id": fid}, {"public_token": fid}], "is_deleted": {"$ne": True}}, {"_id": 0})
                if rec:
                    b, _ = await deps["read_file_rec"](rec)
                    logo = os.path.join(tmp, "logo.img")
                    open(logo, "wb").write(b)
            except Exception:
                logo = None
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

    def _base_job(t, ev, style, fmt, tmp, gpx, logo):
        return {"gpx_path": gpx, "style": style, "format": fmt, "title": ev.get("nome"), "date": _date_it(ev.get("data_inizio")),
                "logo_path": logo, "cache_dir": CACHE, "ffmpeg": imageio_ffmpeg.get_ffmpeg_exe()}

    @r.post("/tracks/{tid}/preview")
    async def preview(tid: str, body: PreviewIn, user: dict = Depends(admin_dep)):
        t = await _track(user["org_id"], tid)
        ev = await _event(user["org_id"], t["event_id"])
        await _require_active(user["org_id"], t["event_id"])
        if body.style not in STYLES or body.format not in ER.SIZES:
            raise HTTPException(status_code=400, detail="Stile o formato non valido")
        with tempfile.TemporaryDirectory() as tmp:
            gpx, logo = await _job_files(tmp, t, ev)
            job = {**_base_job(t, ev, body.style, body.format, tmp, gpx, logo), "still": True, "out_path": os.path.join(tmp, "preview.jpg")}
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
                    gpx, logo = await _job_files(tmp, t, ev)
                    job = {**_base_job(t, ev, v["style"], v["format"], tmp, gpx, logo), "duration": v["duration"], "out_path": os.path.join(tmp, "video.mp4"),
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
                await db.eventmap_videos.update_one({"id": vid}, {"$set": {"status": "error", "error": f"Generazione non riuscita: {e}"[:300], "completed_at": _now()}})

    @r.post("/events/{eid}/videos")
    async def create_video(eid: str, body: VideoIn, user: dict = Depends(admin_dep)):
        await _event(user["org_id"], eid)
        t = await _track(user["org_id"], body.track_id)
        if t["event_id"] != eid:
            raise HTTPException(status_code=400, detail="La traccia appartiene a un altro evento")
        if body.style not in STYLES or body.format not in ER.SIZES or body.duration not in DURATIONS or (body.music and body.music not in MUSIC):
            raise HTTPException(status_code=400, detail="Opzioni video non valide")
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
            doc = {"id": vid, "org_id": user["org_id"], "event_id": eid, "track_id": t["id"], "track_name": t.get("name"), "distance_m": t["distance_m"],
                   "style": body.style, "format": body.format, "duration": body.duration, "music": body.music, "status": "queued", "progress": 0,
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
