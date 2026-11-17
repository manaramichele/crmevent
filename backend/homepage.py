"""Marketing → Home Page: carosello pubblico dei loghi eventi (pubblicazione decisa dal Super Admin)."""
import asyncio
import hashlib
import io
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from PIL import Image
from pydantic import BaseModel, Field

DEFAULTS = {"carousel_enabled": True, "carousel_title": "Scelto dai migliori organizzatori di eventi", "auto_new": False, "auto_since": None}
THUMB = (320, 160)


class SettingsIn(BaseModel):
    carousel_enabled: bool
    carousel_title: str = Field(min_length=3, max_length=120)
    auto_new: bool


class StatusIn(BaseModel):
    status: Optional[Literal["approved", "excluded"]] = None


def _now():
    return datetime.now(timezone.utc).isoformat()


def _fid(ev: dict) -> str:
    return (ev.get("logo_url") or "").rstrip("/").split("/")[-1]


def _thumb(data: bytes) -> bytes:
    im = Image.open(io.BytesIO(data))
    im = im.convert("RGBA") if im.mode in ("P", "LA", "RGBA") else im.convert("RGB")
    im.thumbnail((THUMB[0] * 2, THUMB[1] * 2), Image.LANCZOS)
    out = io.BytesIO()
    im.save(out, "WEBP", quality=82, method=4)
    return out.getvalue()


def build(db, deps):
    r = APIRouter(prefix="/api")
    sa, audit, read_file = deps["require_superadmin"], deps["record_audit"], deps["read_file_rec"]

    async def _settings() -> dict:
        return {**DEFAULTS, **(await db.homepage_settings.find_one({"_id": "main"}, {"_id": 0}) or {})}

    def _published(ev: dict, s: dict) -> bool:
        st = (ev.get("homepage_logo") or {}).get("status")
        if not ev.get("logo_url") or st == "excluded":
            return False
        if st == "approved":
            return True
        return bool(s["auto_new"] and s["auto_since"] and (ev.get("created_at") or "") >= s["auto_since"])

    def _src(ev: dict) -> str:
        v = hashlib.sha1(f"{_fid(ev)}".encode()).hexdigest()[:10]
        return f"/api/public/home-logos/{ev['id']}.webp?v={v}"

    def _sorted(evs: list) -> list:
        return sorted(evs, key=lambda e: ((e.get("nome") or "").casefold(), e["id"]))

    async def _with_file(evs: list) -> set:
        fids = list({_fid(e) for e in evs})
        recs = await db.files.find({"$or": [{"id": {"$in": fids}}, {"public_token": {"$in": fids}}], "is_deleted": False, "content_type": {"$regex": "^image/"}}, {"_id": 0, "id": 1, "public_token": 1}).to_list(10000)
        ok = {r["id"] for r in recs} | {r.get("public_token") for r in recs}
        return {e["id"] for e in evs if _fid(e) in ok}

    @r.get("/public/home-carousel")
    async def public_carousel(response: Response):
        s = await _settings()
        response.headers["Cache-Control"] = "public, max-age=60"
        if not s["carousel_enabled"]:
            return {"enabled": False, "title": s["carousel_title"], "logos": []}
        evs = await db.events.find({"logo_url": {"$nin": [None, ""]}}, {"_id": 0, "id": 1, "nome": 1, "logo_url": 1, "homepage_logo": 1, "created_at": 1}).to_list(5000)
        evs = [e for e in evs if _published(e, s)]
        ok = await _with_file(evs)
        return {"enabled": True, "title": s["carousel_title"], "logos": [{"id": e["id"], "name": e.get("nome") or "", "src": _src(e)} for e in _sorted(evs) if e["id"] in ok]}

    @r.get("/public/home-logos/{event_id}.webp")
    async def public_logo(event_id: str, preview: int = 0, _: Optional[str] = None):
        ev = await db.events.find_one({"id": event_id}, {"_id": 0, "id": 1, "logo_url": 1, "homepage_logo": 1, "created_at": 1})
        if not ev or (not preview and not _published(ev, await _settings())) or not ev.get("logo_url"):
            raise HTTPException(status_code=404, detail="Logo non disponibile")
        fid = _fid(ev)
        cached = await db.homepage_logo_cache.find_one({"_id": event_id})
        if cached and cached.get("fid") == fid:
            data = cached["data"]
        else:
            rec = await db.files.find_one({"$or": [{"id": fid}, {"public_token": fid}], "is_deleted": False}, {"_id": 0})
            if not rec or not (rec.get("content_type") or "").startswith("image/"):
                raise HTTPException(status_code=404, detail="Logo non disponibile")
            raw, _ct = await read_file(rec)
            data = await asyncio.to_thread(_thumb, raw)
            await db.homepage_logo_cache.update_one({"_id": event_id}, {"$set": {"fid": fid, "data": data, "at": _now()}}, upsert=True)
        return Response(content=data, media_type="image/webp", headers={"Cache-Control": "public, max-age=604800, immutable" if not preview else "private, max-age=60"})

    @r.get("/homepage/settings")
    async def get_settings(_: dict = Depends(sa)):
        return await _settings()

    @r.put("/homepage/settings")
    async def put_settings(body: SettingsIn, user: dict = Depends(sa)):
        cur = await _settings()
        upd = body.model_dump() | {"updated_at": _now()}
        if body.auto_new and not cur["auto_new"]:
            upd["auto_since"] = _now()
        await db.homepage_settings.update_one({"_id": "main"}, {"$set": upd}, upsert=True)
        await audit(user, "homepage_settings", detail=f"carosello={'visibile' if body.carousel_enabled else 'nascosto'} · nuovi eventi={'pubblicati' if body.auto_new else 'da approvare'}")
        return await _settings()

    @r.get("/homepage/logos")
    async def list_logos(_: dict = Depends(sa)):
        s = await _settings()
        orgs = {o["id"]: o.get("nome") for o in await db.organizations.find({}, {"_id": 0, "id": 1, "nome": 1}).to_list(5000)}
        evs = await db.events.find({"logo_url": {"$nin": [None, ""]}}, {"_id": 0, "id": 1, "nome": 1, "org_id": 1, "logo_url": 1, "homepage_logo": 1, "created_at": 1, "updated_at": 1}).to_list(5000)
        out = []
        ok = await _with_file(evs)
        for e in _sorted(evs):
            st = (e.get("homepage_logo") or {}).get("status")
            pub = _published(e, s) and e["id"] in ok
            out.append({"id": e["id"], "nome": e.get("nome"), "org_id": e.get("org_id"), "org_nome": orgs.get(e.get("org_id"), "—"),
                        "status": "excluded" if st == "excluded" else "published" if pub else "pending", "manual": st, "valid": e["id"] in ok,
                        "updated_at": max(filter(None, [e.get("updated_at"), e.get("created_at"), (e.get("homepage_logo") or {}).get("at")]), default=None),
                        "thumb": _src(e) + "&preview=1"})
        return out

    @r.post("/homepage/logos/{event_id}")
    async def set_logo(event_id: str, body: StatusIn, user: dict = Depends(sa)):
        ev = await db.events.find_one({"id": event_id}, {"_id": 0, "id": 1, "nome": 1, "org_id": 1})
        if not ev:
            raise HTTPException(status_code=404, detail="Evento non trovato")
        await db.events.update_one({"id": event_id}, {"$set": {"homepage_logo": {"status": body.status, "at": _now(), "by": user.get("email")}}})
        label = {"approved": "pubblicato", "excluded": "escluso", None: "riportato allo stato predefinito"}[body.status]
        await audit(user, "homepage_logo", org_id=ev.get("org_id"), detail=f"{ev.get('nome')} · logo {label} nella homepage")
        return {"ok": True}

    return {"router": r}
