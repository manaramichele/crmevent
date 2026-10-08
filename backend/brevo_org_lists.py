"""Liste Brevo per organizzazione (Staff, Collaboratori, Utenti invitati, Volontari, Referenti Aziendali).

Affiancano le liste esistenti (Lead, Utenti registrati, Disponibilità eventi, Prospect), che NON vengono mai toccate.
- Isolamento: una lista fisica per (org_id, categoria), collegata tramite ID salvato in DB (rinominare l'org non rompe nulla).
- Creazione lazy: solo per categorie con almeno un contatto, dentro la cartella "CRMEvent · Organizzazioni".
- Mai rimozioni/spostamenti/modifiche di automazioni; mai riattivazione di contatti disiscritti; nessun funnel.
- Nulla parte senza l'interruttore del Super Admin; la sincronizzazione di un'org è avviata manualmente dopo l'anteprima.
"""
import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import brevo_client

logger = logging.getLogger("crmevent.brevo_org_lists")

FOLDER_NAME = "CRMEvent · Organizzazioni"
SETTING_KEY = "brevo_org_lists_enabled"
CATEGORIES = [
    ("staff", "Staff"), ("collaboratori", "Collaboratori"), ("utenti_invitati", "Utenti_invitati"),
    ("volontari", "Volontari"), ("referenti_aziendali", "Referenti_Aziendali"),
]
CAT_LABEL = dict(CATEGORIES)
EMAIL_RX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _now():
    return datetime.now(timezone.utc).isoformat()


def list_name(org_name: str, cat: str) -> str:
    slug = re.sub(r"[^0-9A-Za-zÀ-ÿ]+", "_", (org_name or "Organizzazione").strip()).strip("_") or "Organizzazione"
    return f"{slug}_{CAT_LABEL[cat]}"


async def is_enabled(db) -> bool:
    doc = await db.settings.find_one({"key": SETTING_KEY}, {"_id": 0})
    return bool(doc and doc.get("value"))


async def org_members(db, org_id: str) -> dict:
    """Contatti per categoria (solo con email valida, deduplicati per email)."""
    out = {c: {} for c, _ in CATEGORIES}

    def add(cat, p):
        em = (p.get("email") or "").strip().lower()
        if EMAIL_RX.match(em) and em not in out[cat]:
            out[cat][em] = {"email": em, "nome": p.get("nome") or "", "cognome": p.get("cognome") or ""}

    links = await db.staff.find({"org_id": org_id}, {"_id": 0, "persona_id": 1, "categoria": 1}).to_list(100000)
    cat_by = {"staff": "staff", "collaboratore": "collaboratori", "volontario": "volontari"}
    pids = {l["persona_id"] for l in links if l.get("persona_id")}
    persons = {p["id"]: p for p in await db.persons.find({"org_id": org_id, "id": {"$in": list(pids)}}, {"_id": 0}).to_list(100000)}
    for l in links:
        cat = cat_by.get(l.get("categoria"))
        if cat and l.get("persona_id") in persons:
            add(cat, persons[l["persona_id"]])
    # Referenti aziendali = contatti delle Aziende (relazioni person_companies + legacy azienda_id)
    rel_pids = {r["person_id"] for r in await db.person_companies.find({"org_id": org_id}, {"_id": 0, "person_id": 1}).to_list(100000)}
    async for p in db.persons.find({"org_id": org_id, "$or": [{"id": {"$in": list(rel_pids)}}, {"azienda_id": {"$nin": [None, ""]}}]}, {"_id": 0}):
        add("referenti_aziendali", p)
    # Utenti invitati = account entrati nell'org tramite invito/aggiunta (non il titolare che si è registrato)
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "owner_user_id": 1}) or {}
    mems = await db.memberships.find({"org_id": org_id, "active": True, "user_id": {"$ne": org.get("owner_user_id")}}, {"_id": 0, "user_id": 1}).to_list(10000)
    async for u in db.users.find({"user_id": {"$in": [m["user_id"] for m in mems]}, "role": {"$ne": "superadmin"}}, {"_id": 0}):
        add("utenti_invitati", u)
    return {c: list(v.values()) for c, v in out.items()}


async def _folder_id(c) -> int:
    for f in await c.folders():
        if (f.get("name") or "").strip().lower() == FOLDER_NAME.lower():
            return f["id"]
    return (await c.create_folder(FOLDER_NAME))["id"]


async def _ensure_list(db, c, org: dict, cat: str, folder_cache: dict) -> int:
    doc = await db.brevo_org_lists.find_one({"org_id": org["id"], "category": cat}, {"_id": 0})
    if doc:
        return doc["list_id"]
    if "id" not in folder_cache:
        folder_cache["id"] = await _folder_id(c)
    name = list_name(org.get("nome"), cat)
    lst = await c.create_list(name, folder_cache["id"])
    await db.brevo_org_lists.insert_one({"org_id": org["id"], "category": cat, "list_id": lst["id"], "list_name": name, "created_at": _now()})
    return lst["id"]


async def _add_contact(c, list_id: int, m: dict) -> str:
    contact = await c.get_contact(m["email"])
    if contact:
        if list_id in (contact.get("listUnsubscribed") or []):
            return "disiscritto"
        if list_id in (contact.get("listIds") or []):
            return "gia_presente"
        await c.add_existing_to_list(m["email"], list_id)  # solo listIds: attributi/consensi esistenti intatti
        return "aggiunto"
    attrs = {k: v for k, v in {"NOME": m["nome"], "COGNOME": m["cognome"]}.items() if v}
    await c.create_contact(m["email"], list_id, attrs or None)
    return "creato"


async def sync_org(db, org: dict, categories=None, only_emails=None) -> dict:
    members = await org_members(db, org["id"])
    stats, folder = {}, {}
    async with brevo_client.BrevoClient() as c:
        for cat, _ in CATEGORIES:
            if categories and cat not in categories:
                continue
            rows = [m for m in members[cat] if not only_emails or m["email"] in only_emails]
            if not rows:
                continue
            lid = await _ensure_list(db, c, org, cat, folder)
            s = stats.setdefault(cat, {"list_id": lid, "creato": 0, "aggiunto": 0, "gia_presente": 0, "disiscritto": 0, "errore": 0})
            for m in rows:
                try:
                    s[await _add_contact(c, lid, m)] += 1
                except Exception as e:
                    s["errore"] += 1
                    logger.warning(f"brevo org list add failed ({cat}): {e}")
    await db.brevo_org_sync_log.insert_one({"org_id": org["id"], "stats": stats, "only_emails": only_emails, "created_at": _now()})
    return stats


async def sync_invited_user(db, user_id: str, org_id: str):
    """Invitato accettato: va SOLO nella lista Utenti_invitati dell'org (mai nei funnel commerciali)."""
    if not (await is_enabled(db) and brevo_client.is_configured()):
        return None
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1})
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "id": 1, "nome": 1})
    if not (u and u.get("email") and org):
        return None
    try:
        return await sync_org(db, org, categories=["utenti_invitati"], only_emails=[u["email"].lower()])
    except Exception as e:
        logger.error(f"sync invited user failed: {e}")
        return None


class EnabledIn(BaseModel):
    enabled: bool


def build_router(db, require_superadmin, record_audit) -> APIRouter:
    r = APIRouter(prefix="/api/platform/brevo/org-lists")

    @r.get("/settings")
    async def get_settings(admin: dict = Depends(require_superadmin)):
        return {"enabled": await is_enabled(db), "configured": brevo_client.is_configured(), "folder": FOLDER_NAME,
                "unchanged_lists": ["CRMEvent · Lead", "CRMEvent · Utenti registrati", "CRMEvent · Disponibilità eventi", "CRMEvent – Prospect"]}

    @r.put("/settings")
    async def put_settings(body: EnabledIn, admin: dict = Depends(require_superadmin)):
        await db.settings.update_one({"key": SETTING_KEY}, {"$set": {"key": SETTING_KEY, "value": body.enabled, "updated_at": _now()}}, upsert=True)
        await record_audit(admin, "brevo_org_lists_toggle", detail="attivata" if body.enabled else "disattivata")
        return {"enabled": body.enabled}

    @r.get("/preview")
    async def preview(org_id: str, admin: dict = Depends(require_superadmin)):
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "id": 1, "nome": 1})
        if not org:
            raise HTTPException(status_code=404, detail="Organizzazione non trovata")
        members = await org_members(db, org_id)
        linked = {d["category"]: d async for d in db.brevo_org_lists.find({"org_id": org_id}, {"_id": 0})}
        last = await db.brevo_org_sync_log.find_one({"org_id": org_id, "only_emails": None}, {"_id": 0}, sort=[("created_at", -1)])
        return {"org": org, "enabled": await is_enabled(db), "configured": brevo_client.is_configured(), "last_sync": last,
                "lists": [{"category": cat, "label": lbl.replace("_", " "), "list_name": (linked.get(cat) or {}).get("list_name") or list_name(org["nome"], cat),
                           "list_id": (linked.get(cat) or {}).get("list_id"), "contacts": len(members[cat]),
                           "sample": members[cat][:5]} for cat, lbl in CATEGORIES]}

    @r.post("/sync/{org_id}")
    async def sync(org_id: str, admin: dict = Depends(require_superadmin)):
        if not await is_enabled(db):
            raise HTTPException(status_code=400, detail="Attiva prima le liste Brevo per organizzazione")
        if not brevo_client.is_configured():
            raise HTTPException(status_code=400, detail="Brevo non configurato")
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "id": 1, "nome": 1})
        if not org:
            raise HTTPException(status_code=404, detail="Organizzazione non trovata")
        try:
            stats = await sync_org(db, org)
        except brevo_client.BrevoError as e:
            raise HTTPException(status_code=502, detail=f"Brevo ha rifiutato la richiesta ({e.status})")
        await record_audit(admin, "brevo_org_lists_sync", org_id=org_id, org_name=org.get("nome"), meta={"stats": stats})
        return {"stats": stats}

    return r
