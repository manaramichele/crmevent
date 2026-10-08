"""Novità CRMEvent: bozze generate SOLO per rilasci effettivamente in esecuzione in produzione.

Fonte di verità del rilascio = releases.json distribuito insieme al codice in esecuzione.
Le bozze nascono solo se CRMEVENT_ENV=production (server realmente deployato); mai da repo/branch/preview.
"""
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

logger = logging.getLogger("crmevent.news")

MANIFEST = Path(__file__).parent / "releases.json"
LLM_MODEL = ("openai", "gpt-5.6-terra")

SYSTEM = (
    "Sei il redattore delle 'Novità' di CRMEvent, CRM italiano per organizzatori di eventi. "
    "Ricevi note interne di un aggiornamento GIÀ DISPONIBILE. Scrivi una comunicazione per l'utente finale: "
    "titolo breve (max 6 parole) e descrizione di 1-2 frasi (max 40 parole) orientata al vantaggio concreto. "
    "Seconda persona ('Ora puoi...'). VIETATO citare file, componenti, endpoint, codice, database, test, branch. "
    "Non parlare di funzioni future. Rispondi SOLO con JSON: {\"titolo\": \"...\", \"descrizione\": \"...\"}."
)


def is_production() -> bool:
    return os.environ.get("CRMEVENT_ENV", "").strip().lower() == "production"


def load_manifest() -> list:
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"releases.json non leggibile: {e}")
        return []


def _groups(release: dict) -> dict:
    """Raggruppa per area le sole modifiche visibili all'utente (no bugfix/tecniche)."""
    out = {}
    for c in release.get("changes") or []:
        if not c.get("user_visible", True) or c.get("kind") in ("bugfix", "tecnica", "refactoring", "server"):
            continue
        out.setdefault(c.get("area") or "Generale", []).append(c)
    return out


def _parse(text: str) -> dict:
    t = (text or "").strip()
    s, e = t.find("{"), t.rfind("}")
    return json.loads(t[s:e + 1])


async def _generate(area: str, changes: list) -> tuple:
    notes = "\n".join(f"- {c.get('note', '')}" for c in changes)
    fallback = changes[0].get("fallback_title") or f"Novità in {area}", " ".join(c.get("fallback_text", "") for c in changes).strip() or notes
    if any(c.get("fixed_text") for c in changes):  # testo approvato dal cliente: nessuna riscrittura AI
        return (*fallback, "fixed")
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        return (*fallback, "fallback")
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(api_key=key, session_id=uuid.uuid4().hex, system_message=SYSTEM).with_model(*LLM_MODEL)
        res = _parse(await chat.send_message(UserMessage(text=f"Area: {area}\nNote interne dell'aggiornamento:\n{notes}")))
        if res.get("titolo") and res.get("descrizione"):
            return res["titolo"].strip(), res["descrizione"].strip(), "ai"
    except Exception as e:
        logger.warning(f"Generazione AI Novità fallita, uso testo di riserva: {e}")
    return (*fallback, "fallback")


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


async def create_drafts(db, release: dict, simulated: bool = False) -> int:
    n = 0
    for area, changes in _groups(release).items():
        titolo, descr, gen = await _generate(area, changes)
        await db.news_items.insert_one({
            "id": uuid.uuid4().hex, "release_id": release["id"], "release_date": release.get("date"),
            "area": area, "status": "bozza", "titolo": titolo, "descrizione": descr,
            "generated_titolo": titolo, "generated_descrizione": descr, "generator": gen, "edited": False,
            "source_notes": [c.get("note") for c in changes], "simulated": simulated,
            "requires_service": next((c["requires_service"] for c in changes if c.get("requires_service")), None),
            "created_at": _now(), "approved_by": None, "published_at": None,
        })
        n += 1
    return n


async def sync_releases(db) -> int:
    """Solo in produzione: registra i rilasci del codice in esecuzione mai visti e ne crea le bozze."""
    if not is_production():
        return 0
    await db.news_releases.create_index("id", unique=True)
    total = 0
    for rel in load_manifest():
        if not rel.get("id"):
            continue
        try:  # lock atomico: un solo worker processa il rilascio
            await db.news_releases.insert_one({"id": rel["id"], "date": rel.get("date"), "detected_at": _now(), "env": "production"})
        except DuplicateKeyError:
            continue
        total += await create_drafts(db, rel)
    if total:
        logger.info(f"Novità: create {total} bozze da rilasci in produzione")
    return total


class NewsEdit(BaseModel):
    titolo: str
    descrizione: str


class SimulateIn(BaseModel):
    release_id: str


ADMIN_FIELDS = ("id", "release_id", "release_date", "area", "status", "titolo", "descrizione", "generated_titolo",
                "generated_descrizione", "generator", "edited", "source_notes", "simulated", "created_at",
                "approved_by", "published_at", "withdrawn_at", "withdrawn_by")


def build_router(db, get_current_user, require_superadmin, record_audit) -> APIRouter:
    r = APIRouter(prefix="/api")

    async def _get(nid):
        doc = await db.news_items.find_one({"id": nid}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Novità non trovata")
        return doc

    def _actor(a):
        return {"user_id": a.get("user_id"), "email": a.get("email"), "name": a.get("name")}

    async def _audit(admin, action, doc, extra=None):
        await record_audit(admin, action, detail=doc.get("titolo"),
                           meta={"news_id": doc["id"], "release_id": doc.get("release_id"), "area": doc.get("area"), **(extra or {})})

    @r.get("/platform/news")
    async def admin_list(admin: dict = Depends(require_superadmin)):
        rows = await db.news_items.find({}, {"_id": 0}).sort("created_at", -1).to_list(2000)
        return [{k: x.get(k) for k in ADMIN_FIELDS} for x in rows]

    @r.get("/platform/news/env")
    async def admin_env(admin: dict = Depends(require_superadmin)):
        seen = {x["id"] for x in await db.news_releases.find({}, {"_id": 0, "id": 1}).to_list(5000)}
        sim = set(await db.news_items.distinct("release_id", {"simulated": True}))
        return {"production": is_production(), "releases": [
            {"id": x.get("id"), "date": x.get("date"), "areas": list(_groups(x).keys()),
             "detected": x.get("id") in seen, "simulated": x.get("id") in sim} for x in load_manifest()]}

    @r.post("/platform/news/simulate-release")
    async def admin_simulate(body: SimulateIn, admin: dict = Depends(require_superadmin)):
        if is_production():
            raise HTTPException(status_code=403, detail="Simulazione non disponibile in produzione")
        rel = next((x for x in load_manifest() if x.get("id") == body.release_id), None)
        if not rel:
            raise HTTPException(status_code=404, detail="Rilascio non presente nel registro")
        n = await create_drafts(db, rel, simulated=True)
        await record_audit(admin, "news_simulated", detail=rel["id"], meta={"release_id": rel["id"], "drafts": n})
        return {"created": n}

    @r.put("/platform/news/{nid}")
    async def admin_edit(nid: str, body: NewsEdit, admin: dict = Depends(require_superadmin)):
        doc = await _get(nid)
        if doc["status"] != "bozza":
            raise HTTPException(status_code=400, detail="Puoi modificare solo le bozze da approvare")
        t, d = body.titolo.strip(), body.descrizione.strip()
        if not t or not d:
            raise HTTPException(status_code=400, detail="Titolo e descrizione sono obbligatori")
        upd = {"titolo": t, "descrizione": d, "edited": True, "edited_at": _now(), "edited_by": _actor(admin)}
        await db.news_items.update_one({"id": nid}, {"$set": upd})
        await _audit(admin, "news_edited", {**doc, **upd})
        return {**{k: doc.get(k) for k in ADMIN_FIELDS}, **upd}

    @r.post("/platform/news/{nid}/publish")
    async def admin_publish(nid: str, admin: dict = Depends(require_superadmin)):
        doc = await _get(nid)
        if doc["status"] == "pubblicata":
            raise HTTPException(status_code=400, detail="Novità già pubblicata")
        if doc.get("requires_service"):
            svc = await db.credit_services.find_one({"key": doc["requires_service"]}, {"_id": 0, "active": 1, "consumo_active": 1})
            if not (svc and svc.get("active") and svc.get("consumo_active")):
                raise HTTPException(status_code=400, detail="La funzione descritta non è ancora attiva: attivala prima di pubblicare la Novità")
        upd = {"status": "pubblicata", "approved_by": _actor(admin), "published_at": _now(), "withdrawn_at": None, "withdrawn_by": None}
        await db.news_items.update_one({"id": nid}, {"$set": upd})
        await _audit(admin, "news_published", doc)
        return {"ok": True}

    @r.post("/platform/news/{nid}/withdraw")
    async def admin_withdraw(nid: str, admin: dict = Depends(require_superadmin)):
        doc = await _get(nid)
        if doc["status"] != "pubblicata":
            raise HTTPException(status_code=400, detail="Solo le Novità pubblicate possono essere ritirate")
        await db.news_items.update_one({"id": nid}, {"$set": {"status": "ritirata", "withdrawn_at": _now(), "withdrawn_by": _actor(admin)}})
        await _audit(admin, "news_withdrawn", doc)
        return {"ok": True}

    @r.delete("/platform/news/{nid}")
    async def admin_delete(nid: str, admin: dict = Depends(require_superadmin)):
        doc = await _get(nid)
        if doc["status"] == "pubblicata":
            raise HTTPException(status_code=400, detail="Ritira la Novità prima di eliminarla")
        await db.news_items.delete_one({"id": nid})
        await _audit(admin, "news_deleted", doc, {"testo": doc.get("descrizione")})
        return {"ok": True}

    async def _published(limit=500):
        return await db.news_items.find({"status": "pubblicata"}, {"_id": 0, "id": 1, "titolo": 1, "descrizione": 1, "area": 1, "published_at": 1}) \
            .sort("published_at", -1).to_list(limit)

    @r.get("/news")
    async def user_list(user: dict = Depends(get_current_user)):
        return await _published()

    @r.get("/news/unread-count")
    async def user_unread(user: dict = Depends(get_current_user)):
        rd = await db.news_reads.find_one({"user_id": user["user_id"]}, {"_id": 0}) or {}
        q = {"status": "pubblicata"}
        if rd.get("seen_at"):
            q["published_at"] = {"$gt": rd["seen_at"]}
        return {"count": await db.news_items.count_documents(q)}

    @r.post("/news/mark-read")
    async def user_mark_read(user: dict = Depends(get_current_user)):
        await db.news_reads.update_one({"user_id": user["user_id"]}, {"$set": {"seen_at": _now()}}, upsert=True)
        return {"ok": True}

    return r
