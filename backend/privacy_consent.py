"""Privacy e Cookie: configurazione banner/servizi/versioni, registro consensi pseudonimo (TTL 24 mesi), Super Admin."""
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

CATEGORIES = ("necessary", "analytics", "marketing")
# Servizi collegati a script reali: categoria bloccata (non spostabili tra i "necessari").
LOCKED_SERVICES = {"ga4": "analytics", "posthog": "analytics", "brevo": "marketing", "crmevent_core": "necessary"}
RETENTION_DAYS = 730
REASK_DAYS = 180
CONSENT_ID_RE = re.compile(r"^[a-f0-9-]{36}$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ck(name, dur_it, dur_en, it, en):
    return {"name": name, "duration_it": dur_it, "duration_en": dur_en, "description_it": it, "description_en": en}


DEFAULTS = {
    "id": "main",
    "banner": {
        "it": {"title": "Rispettiamo la tua privacy",
               "text": "CRMEvent utilizza cookie tecnici necessari al funzionamento della piattaforma. Con il tuo consenso useremmo anche cookie analitici, per capire come viene usato il sito, e di marketing, per comunicazioni più pertinenti. Puoi accettare, rifiutare o scegliere le categorie: rifiutare non limita l'uso di CRMEvent. Puoi cambiare idea in qualsiasi momento da \"Preferenze cookie\"."},
        "en": {"title": "We respect your privacy",
               "text": "CRMEvent uses technical cookies required for the platform to work. With your consent we would also use analytics cookies, to understand how the site is used, and marketing cookies, for more relevant communications. You can accept, reject or choose categories: rejecting does not limit your use of CRMEvent. You can change your mind at any time from \"Cookie preferences\"."},
    },
    "categories": {
        "necessary": {"it": {"name": "Necessari", "description": "Indispensabili per sicurezza, accesso all'account e memorizzazione delle tue scelte sui cookie. Sempre attivi, non richiedono consenso."},
                      "en": {"name": "Necessary", "description": "Essential for security, account access and storing your cookie choices. Always active, no consent required."}},
        "analytics": {"it": {"name": "Analitici", "description": "Statistiche aggregate sull'uso del sito e dell'app per migliorare il servizio."},
                      "en": {"name": "Analytics", "description": "Aggregated statistics on site and app usage to improve the service."}},
        "marketing": {"it": {"name": "Marketing", "description": "Tracciamento della navigazione collegato al tuo contatto per comunicazioni e automazioni email più pertinenti."},
                      "en": {"name": "Marketing", "description": "Browsing tracking linked to your contact for more relevant emails and automations."}},
    },
    "services": [
        {"id": "crmevent_core", "name": "CRMEvent – sessione e sicurezza", "provider": "CRMEvent (prima parte)", "category": "necessary",
         "purpose_it": "Autenticazione, sicurezza dell'accesso con Google, memorizzazione delle preferenze cookie e dell'organizzazione attiva.",
         "purpose_en": "Authentication, Google sign-in security, storing cookie preferences and the active organisation.",
         "cookies": [_ck("access_token / session_token", "7 giorni", "7 days", "Cookie di sessione autenticata (HttpOnly).", "Authenticated session cookie (HttpOnly)."),
                     _ck("g_oauth_state / g_oauth_link", "10 minuti", "10 minutes", "Protezione della procedura di accesso con Google.", "Google sign-in flow protection."),
                     _ck("crmevent_consent (localStorage)", "6 mesi", "6 months", "Memorizza le tue scelte sui cookie e l'ID pseudonimo del consenso.", "Stores your cookie choices and pseudonymous consent ID."),
                     _ck("acting_org_id, platform_section (localStorage)", "Persistente", "Persistent", "Preferenze di navigazione dell'area riservata.", "Reserved-area navigation preferences.")]},
        {"id": "stripe", "name": "Stripe Checkout", "provider": "Stripe Payments Europe Ltd.", "category": "necessary",
         "purpose_it": "Pagamenti degli abbonamenti, sul dominio Stripe solo quando avvii un pagamento.",
         "purpose_en": "Subscription payments, on the Stripe domain only when you start a payment.", "cookies": []},
        {"id": "ga4", "name": "Google Analytics 4", "provider": "Google Ireland Ltd.", "category": "analytics",
         "purpose_it": "Statistiche di utilizzo con IP anonimizzato e Google Consent Mode v2; caricato solo con consenso.",
         "purpose_en": "Usage statistics with anonymised IP and Google Consent Mode v2; loaded only with consent.",
         "cookies": [_ck("_ga", "13 mesi", "13 months", "Distingue i visitatori in forma pseudonima.", "Distinguishes visitors pseudonymously."),
                     _ck("_ga_<ID>", "13 mesi", "13 months", "Mantiene lo stato della sessione.", "Keeps session state.")]},
        {"id": "posthog", "name": "PostHog (analisi della piattaforma di sviluppo)", "provider": "Emergent / PostHog Inc.", "category": "analytics",
         "purpose_it": "Analisi tecnica dell'utilizzo e delle sessioni dell'applicazione; caricato solo con consenso.",
         "purpose_en": "Technical analysis of application usage and sessions; loaded only with consent.",
         "cookies": [_ck("ph_<chiave>_posthog", "12 mesi", "12 months", "Identificativo pseudonimo di sessione/visitatore.", "Pseudonymous session/visitor identifier.")]},
        {"id": "partner_ref", "name": "Codice partner (?ref=)", "provider": "CRMEvent (prima parte)", "category": "analytics",
         "purpose_it": "Attribuzione della registrazione al partner che ti ha invitato.",
         "purpose_en": "Attributing your sign-up to the partner who invited you.",
         "cookies": [_ck("crmevent_ref (localStorage)", "30 giorni", "30 days", "Codice partner e campagna.", "Partner code and campaign.")]},
        {"id": "brevo", "name": "Brevo Tracker", "provider": "Sendinblue SAS (Brevo)", "category": "marketing",
         "purpose_it": "Associa la navigazione al tuo contatto Brevo per automazioni email; caricato solo con consenso Marketing.",
         "purpose_en": "Links browsing to your Brevo contact for email automations; loaded only with Marketing consent.",
         "cookies": [_ck("sib_cuid", "6-13 mesi", "6-13 months", "Identificativo del contatto/visitatore.", "Contact/visitor identifier."),
                     _ck("brevo_cid, sib_session", "13 mesi / sessione", "13 months / session", "Visitatore anonimo e sessione di tracciamento.", "Anonymous visitor and tracking session.")]},
    ],
    "versions": {"privacy": "2026.10.1", "cookie": "2026.10.1", "banner": "2026.10.1"},
    "history": [],
}


class CookieIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    duration_it: str = Field(default="", max_length=60)
    duration_en: str = Field(default="", max_length=60)
    description_it: str = Field(default="", max_length=400)
    description_en: str = Field(default="", max_length=400)


class ServiceIn(BaseModel):
    id: str = Field(min_length=2, max_length=40, pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=2, max_length=120)
    provider: str = Field(default="", max_length=120)
    category: Literal["necessary", "analytics", "marketing"]
    purpose_it: str = Field(min_length=3, max_length=600)
    purpose_en: str = Field(min_length=3, max_length=600)
    cookies: List[CookieIn] = []


class LangText(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    text: str = Field(min_length=40, max_length=1500)


class CatText(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    description: str = Field(min_length=10, max_length=600)


class SettingsIn(BaseModel):
    banner: dict
    categories: dict
    services: List[ServiceIn]


class PublishIn(BaseModel):
    doc: Literal["privacy", "cookie", "banner"]
    note: str = Field(min_length=3, max_length=500)
    legal_review: bool = False


class ConsentIn(BaseModel):
    consent_id: str
    analytics: bool
    marketing: bool
    action: Literal["accept_all", "reject_all", "custom"]
    source: Literal["banner", "preferences", "footer", "policy_page"]
    lang: Literal["it", "en"] = "it"
    versions: dict


def build(db, deps: dict):
    r = APIRouter(prefix="/api")
    sa = deps["require_superadmin"]

    async def ensure_indexes():
        await db.consent_records.create_index("created_at_dt", expireAfterSeconds=RETENTION_DAYS * 86400)
        await db.consent_records.create_index([("consent_id", 1), ("created_at", -1)])
        await db.consent_records.create_index("user_id", sparse=True)

    async def settings() -> dict:
        doc = await db.privacy_settings.find_one({"id": "main"}, {"_id": 0})
        if not doc:
            await db.privacy_settings.insert_one(dict(DEFAULTS))
            doc = {k: v for k, v in DEFAULTS.items() if k != "_id"}
        return doc

    def _public(s: dict) -> dict:
        return {"banner": s["banner"], "categories": s["categories"], "services": s["services"], "versions": s["versions"],
                "reask_days": REASK_DAYS, "updated_at": s.get("updated_at")}

    @r.get("/privacy/config")
    async def public_config():
        return _public(await settings())

    @r.post("/privacy/consents")
    async def record_consent(body: ConsentIn, request: Request):
        if not CONSENT_ID_RE.match(body.consent_id):
            raise HTTPException(400, "ID consenso non valido")
        hour_ago = (_now() - timedelta(hours=1)).isoformat()
        if await db.consent_records.count_documents({"consent_id": body.consent_id, "created_at": {"$gte": hour_ago}}) >= 20:
            raise HTTPException(429, "Troppe richieste")
        cur = (await settings())["versions"]
        prev = await db.consent_records.find_one({"consent_id": body.consent_id}, {"_id": 0, "choices": 1}, sort=[("created_at", -1)])
        user = await deps["optional_user"](request)
        choices = {"necessary": True, "analytics": body.analytics, "marketing": body.marketing}
        revoked = [c for c in ("analytics", "marketing") if prev and prev["choices"].get(c) and not choices[c]]
        now = _now()
        doc = {"id": str(uuid.uuid4()), "consent_id": body.consent_id,
               "user_id": user["user_id"] if user and not user.get("support") else None,
               "created_at": now.isoformat(), "created_at_dt": now, "choices": choices, "action": body.action,
               "event": "first" if not prev else ("revoke" if revoked else "update"), "revoked": revoked,
               "versions": {k: cur.get(k) for k in ("privacy", "cookie", "banner")},
               "client_versions": {k: str(body.versions.get(k))[:20] for k in ("privacy", "cookie", "banner")},
               "source": body.source, "lang": body.lang}
        await db.consent_records.insert_one(doc)
        return {"ok": True, "versions": doc["versions"], "recorded_at": doc["created_at"]}

    # ---------------- Super Admin ----------------
    @r.get("/platform/privacy/settings")
    async def get_settings(admin: dict = Depends(sa)):
        s = await settings()
        return {**s, "locked_services": LOCKED_SERVICES, "retention_days": RETENTION_DAYS}

    @r.put("/platform/privacy/settings")
    async def put_settings(body: SettingsIn, admin: dict = Depends(sa)):
        banner = {lang: LangText(**(body.banner.get(lang) or {})).model_dump() for lang in ("it", "en")}
        cats = {}
        for c in CATEGORIES:
            cats[c] = {lang: CatText(**((body.categories.get(c) or {}).get(lang) or {})).model_dump() for lang in ("it", "en")}
        ids = [s.id for s in body.services]
        if len(ids) != len(set(ids)):
            raise HTTPException(400, "ID servizio duplicato")
        for sid, cat in LOCKED_SERVICES.items():
            svc = next((s for s in body.services if s.id == sid), None)
            if not svc:
                raise HTTPException(400, f"Il servizio '{sid}' è collegato a uno script reale e non può essere rimosso")
            if svc.category != cat:
                raise HTTPException(400, f"Il servizio '{svc.name}' deve restare nella categoria '{cat}'")
        await settings()
        await db.privacy_settings.update_one({"id": "main"}, {"$set": {"banner": banner, "categories": cats,
                                             "services": [s.model_dump() for s in body.services], "updated_at": _now().isoformat(),
                                             "updated_by": admin.get("email")}})
        await deps["record_audit"](admin, "privacy_settings_updated", detail="Testi banner/categorie/servizi aggiornati")
        return await get_settings(admin)

    @r.post("/platform/privacy/publish")
    async def publish(body: PublishIn, admin: dict = Depends(sa)):
        s = await settings()
        now = _now()
        prefix = now.strftime("%Y.%m")
        old = s["versions"].get(body.doc, "")
        n = int(old.split(".")[-1]) + 1 if old.startswith(prefix + ".") else 1
        ver = f"{prefix}.{n}"
        entry = {"doc": body.doc, "version": ver, "previous": old, "note": body.note, "legal_review": body.legal_review,
                 "published_at": now.isoformat(), "by": admin.get("email")}
        await db.privacy_settings.update_one({"id": "main"}, {"$set": {f"versions.{body.doc}": ver}, "$push": {"history": entry}})
        await deps["record_audit"](admin, "privacy_version_published", detail=f"{body.doc} {ver} – {body.note}")
        return entry

    @r.get("/platform/privacy/consents")
    async def list_consents(admin: dict = Depends(sa), q: Optional[str] = Query(None, max_length=60),
                            page: int = Query(1, ge=1), limit: int = Query(50, ge=1, le=200)):
        f = {}
        if q:
            f = {"$or": [{"consent_id": q.strip()}, {"user_id": q.strip()}]}
        total = await db.consent_records.count_documents(f)
        items = await db.consent_records.find(f, {"_id": 0, "created_at_dt": 0}).sort("created_at", -1).skip((page - 1) * limit).to_list(limit)
        await deps["record_audit"](admin, "privacy_consents_viewed", detail=f"Registro consensi consultato (filtro: {q or '—'}, pagina {page})")
        return {"items": items, "total": total, "page": page, "limit": limit}

    @r.get("/platform/privacy/stats")
    async def stats(admin: dict = Depends(sa), days: int = Query(30, ge=1, le=730)):
        since = (_now() - timedelta(days=days)).isoformat()
        base = {"created_at": {"$gte": since}}
        actions = {a: await db.consent_records.count_documents({**base, "action": a}) for a in ("accept_all", "reject_all", "custom")}
        total = sum(actions.values())
        latest = await db.consent_records.aggregate([
            {"$match": base}, {"$sort": {"created_at": -1}},
            {"$group": {"_id": "$consent_id", "a": {"$first": "$choices.analytics"}, "m": {"$first": "$choices.marketing"}}},
            {"$group": {"_id": None, "n": {"$sum": 1}, "a": {"$sum": {"$cond": ["$a", 1, 0]}}, "m": {"$sum": {"$cond": ["$m", 1, 0]}}}},
        ]).to_list(1)
        lt = latest[0] if latest else {"n": 0, "a": 0, "m": 0}
        return {"days": days, "records": total, "actions": actions,
                "revocations": await db.consent_records.count_documents({**base, "event": "revoke"}),
                "devices": lt["n"], "analytics_granted": lt["a"], "marketing_granted": lt["m"]}

    return {"router": r, "ensure_indexes": ensure_indexes}
