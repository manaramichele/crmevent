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
    """Server realmente deployato. CRMEVENT_ENV esplicito prevale; se assente, il dominio pubblico (APP_URL) di produzione non è un'anteprima."""
    env = os.environ.get("CRMEVENT_ENV", "").strip().lower()
    if env:
        return env == "production"
    url = (os.environ.get("APP_URL") or "").lower()
    return bool(url) and not any(x in url for x in ("preview.emergentagent.com", "localhost", "127.0.0.1"))


AUDIENCE_TYPES = ("all", "superadmin", "plans", "service")
PLANS = ("bronze", "silver", "gold")


def _audience(changes: list) -> dict:
    a = next((c["audience"] for c in changes if isinstance(c.get("audience"), dict)), None) or {}
    t = a.get("type") if a.get("type") in AUDIENCE_TYPES else "all"
    return {"type": t, "plans": [p for p in a.get("plans") or [] if p in PLANS], "service": a.get("service")}


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
        complete = any((c.get("note") or c.get("fallback_text") or "").strip() for c in changes)
        if complete:
            titolo, descr, gen = await _generate(area, changes)
        else:  # informazioni insufficienti: bozza da completare, nessun testo inventato
            titolo, descr, gen = f"Da completare: novità {area}", "", "incompleta"
        await db.news_items.insert_one({
            "id": uuid.uuid4().hex, "release_id": release["id"], "release_date": release.get("date"),
            "area": area, "status": "bozza", "titolo": titolo, "descrizione": descr,
            "generated_titolo": titolo, "generated_descrizione": descr, "generator": gen, "edited": False, "needs_completion": not complete,
            "source_notes": [c.get("note") for c in changes if c.get("note")], "simulated": simulated, "audience": _audience(changes),
            "requires_service": next((c["requires_service"] for c in changes if c.get("requires_service")), None),
            "created_at": _now(), "approved_by": None, "published_at": None,
        })
        n += 1
    return n


async def _log_check(db, **kw):
    await db.news_checks.insert_one({"id": uuid.uuid4().hex, "at": _now(), "production": is_production(), **kw})


async def sync_releases(db) -> int:
    """Solo in produzione: registra i rilasci del codice in esecuzione mai visti e ne crea le bozze. Ogni controllo è registrato."""
    manifest = load_manifest()
    if not is_production():
        await _log_check(db, outcome="skipped", message="Anteprima: nessuna bozza automatica (solo simulazione)", releases=len(manifest), new=[], drafts=0)
        return 0
    await db.news_releases.create_index("id", unique=True)
    total, new, errors = 0, [], []
    for rel in manifest:
        if not rel.get("id"):
            continue
        try:  # lock atomico: un solo worker processa il rilascio
            await db.news_releases.insert_one({"id": rel["id"], "date": rel.get("date"), "detected_at": _now(), "env": "production"})
        except DuplicateKeyError:
            continue
        try:
            n = await create_drafts(db, rel)
            total += n
            new.append(rel["id"])
            await db.news_releases.update_one({"id": rel["id"]}, {"$set": {"drafts": n}})
        except Exception as e:
            logger.exception(f"Novità: errore bozze rilascio {rel['id']}")
            errors.append(f"{rel['id']}: {e}")
            await db.news_releases.update_one({"id": rel["id"]}, {"$set": {"error": str(e)[:500]}})
    await _log_check(db, outcome="error" if errors else "ok", releases=len(manifest), new=new, drafts=total, errors=errors,
                     message=(f"{len(new)} nuovi rilasci, {total} bozze create" if new else "Nessun nuovo rilascio") + (f" · {len(errors)} errori" if errors else ""))
    if total:
        logger.info(f"Novità: create {total} bozze da rilasci in produzione")
    return total


class Audience(BaseModel):
    type: str = "all"
    plans: list = []
    service: Optional[str] = None


class NewsEdit(BaseModel):
    titolo: str
    descrizione: str
    area: Optional[str] = None
    audience: Optional[Audience] = None


class SimulateIn(BaseModel):
    release_id: str


ADMIN_FIELDS = ("id", "release_id", "release_date", "area", "status", "titolo", "descrizione", "generated_titolo",
                "generated_descrizione", "generator", "edited", "source_notes", "simulated", "created_at",
                "approved_by", "published_at", "withdrawn_at", "withdrawn_by", "audience", "needs_completion")


def build_router(db, get_current_user, require_superadmin, record_audit, org_context=None) -> APIRouter:
    r = APIRouter(prefix="/api")

    def _clean_audience(a: Optional[Audience]) -> dict:
        a = a or Audience()
        if a.type not in AUDIENCE_TYPES:
            raise HTTPException(status_code=400, detail={"field": "audience", "message": "Destinatari non validi"})
        plans = [p for p in a.plans if p in PLANS]
        if a.type == "plans" and not plans:
            raise HTTPException(status_code=400, detail={"field": "audience", "message": "Seleziona almeno un piano (Bronze, Silver o Gold)"})
        if a.type == "service" and not (a.service or "").strip():
            raise HTTPException(status_code=400, detail={"field": "audience", "message": "Seleziona il modulo Marketplace dei destinatari"})
        return {"type": a.type, "plans": plans if a.type == "plans" else [], "service": a.service if a.type == "service" else None}

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
        rels = {x["id"]: x for x in await db.news_releases.find({}, {"_id": 0}).to_list(5000)}
        sim = set(await db.news_items.distinct("release_id", {"simulated": True}))
        last = await db.news_checks.find({}, {"_id": 0}).sort("at", -1).to_list(5)
        return {"production": is_production(), "checks": last, "releases": [
            {"id": x.get("id"), "date": x.get("date"), "areas": list(_groups(x).keys()), "detected": x.get("id") in rels,
             "error": (rels.get(x.get("id")) or {}).get("error"), "simulated": x.get("id") in sim} for x in load_manifest()]}

    @r.post("/platform/news/check")
    async def admin_check(admin: dict = Depends(require_superadmin)):
        n = await sync_releases(db)
        return {"drafts": n, "production": is_production()}

    @r.post("/platform/news")
    async def admin_create(body: NewsEdit, admin: dict = Depends(require_superadmin)):
        t, d = body.titolo.strip(), body.descrizione.strip()
        if not t or not d:
            raise HTTPException(status_code=400, detail="Titolo e descrizione sono obbligatori")
        doc = {"id": uuid.uuid4().hex, "release_id": None, "release_date": None, "area": (body.area or "Generale").strip()[:60] or "Generale",
               "status": "bozza", "titolo": t, "descrizione": d, "generated_titolo": t, "generated_descrizione": d, "generator": "manual",
               "edited": False, "needs_completion": False, "source_notes": [], "simulated": False, "audience": _clean_audience(body.audience),
               "requires_service": None, "created_at": _now(), "created_by": _actor(admin), "approved_by": None, "published_at": None}
        await db.news_items.insert_one({**doc})
        await _audit(admin, "news_created", doc)
        return {k: doc.get(k) for k in ADMIN_FIELDS}

    @r.post("/platform/news/simulate-release")
    async def admin_simulate(body: SimulateIn, admin: dict = Depends(require_superadmin)):
        if is_production():
            raise HTTPException(status_code=403, detail="Simulazione non disponibile in produzione")
        rel = next((x for x in load_manifest() if x.get("id") == body.release_id), None)
        if not rel:
            raise HTTPException(status_code=404, detail="Rilascio non presente nel registro")
        if await db.news_items.count_documents({"release_id": rel["id"], "simulated": True}):
            raise HTTPException(status_code=409, detail="Rilascio già simulato: le bozze esistono già (nessun duplicato creato)")
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
        upd = {"titolo": t, "descrizione": d, "edited": True, "edited_at": _now(), "edited_by": _actor(admin), "needs_completion": False}
        if body.area is not None and body.area.strip():
            upd["area"] = body.area.strip()[:60]
        if body.audience is not None:
            upd["audience"] = _clean_audience(body.audience)
        await db.news_items.update_one({"id": nid}, {"$set": upd})
        await _audit(admin, "news_edited", {**doc, **upd})
        return {**{k: doc.get(k) for k in ADMIN_FIELDS}, **upd}

    @r.post("/platform/news/{nid}/publish")
    async def admin_publish(nid: str, admin: dict = Depends(require_superadmin)):
        doc = await _get(nid)
        if doc["status"] == "pubblicata":
            raise HTTPException(status_code=400, detail="Novità già pubblicata")
        if doc.get("needs_completion") or not (doc.get("descrizione") or "").strip():
            raise HTTPException(status_code=400, detail="Bozza da completare: scrivi titolo e descrizione con «Modifica» prima di pubblicare")
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

    async def _visible(user: dict) -> list:
        rows = await db.news_items.find({"status": "pubblicata"}, {"_id": 0, "id": 1, "titolo": 1, "descrizione": 1, "area": 1, "published_at": 1, "audience": 1}) \
            .sort("published_at", -1).to_list(500)
        if user.get("role") == "superadmin":
            return rows
        ctx = await org_context(user.get("org_id")) if (org_context and user.get("org_id")) else {"plan": None, "services": set()}

        def ok(n):
            a = n.get("audience") or {"type": "all"}
            t = a.get("type", "all")
            return t == "all" or (t == "plans" and ctx["plan"] in (a.get("plans") or [])) or (t == "service" and a.get("service") in ctx["services"])
        return [n for n in rows if ok(n)]

    async def _reads(user: dict) -> dict:
        return await db.news_reads.find_one({"user_id": user["user_id"]}, {"_id": 0}) or {}

    def _is_read(n: dict, rd: dict) -> bool:
        return n["id"] in (rd.get("read_ids") or []) or bool(rd.get("seen_at") and (n.get("published_at") or "") <= rd["seen_at"])

    @r.get("/news")
    async def user_list(user: dict = Depends(get_current_user)):
        rd = await _reads(user)
        return [{**n, "read": _is_read(n, rd)} for n in await _visible(user)]

    @r.get("/news/unread-count")
    async def user_unread(user: dict = Depends(get_current_user)):
        rd = await _reads(user)
        unread = [n for n in await _visible(user) if not _is_read(n, rd)]
        latest = unread[0] if unread else None
        banner = bool(latest) and (not rd.get("dismissed_at") or latest["published_at"] > rd["dismissed_at"])
        return {"count": len(unread), "latest": {k: latest.get(k) for k in ("id", "titolo", "descrizione", "area", "published_at")} if latest else None, "banner": banner}

    class ReadIn(BaseModel):
        ids: Optional[list] = None

    @r.post("/news/mark-read")
    async def user_mark_read(body: Optional[ReadIn] = None, user: dict = Depends(get_current_user)):
        ids = [n["id"] for n in await _visible(user)] if not (body and body.ids) else [str(i) for i in body.ids][:500]
        await db.news_reads.update_one({"user_id": user["user_id"]}, {"$addToSet": {"read_ids": {"$each": ids}}, "$set": {"read_at": _now()}}, upsert=True)
        return {"ok": True, "read": len(ids)}

    @r.post("/news/dismiss-banner")
    async def user_dismiss(user: dict = Depends(get_current_user)):
        await db.news_reads.update_one({"user_id": user["user_id"]}, {"$set": {"dismissed_at": _now()}}, upsert=True)
        return {"ok": True}

    return r
