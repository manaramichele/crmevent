"""CRMEvent Partner: account (cookie separato), referral/campagne/click, commissioni su pagamenti Stripe confermati, liquidazioni, materiali, Super Admin."""
import asyncio
import csv
import hashlib
import io
import logging
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Literal, Optional

import jwt
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, EmailStr, Field

import brevo_funnel
import email_utils
import storage_utils
from pymongo.errors import DuplicateKeyError

log = logging.getLogger("partner_portal")
COOKIE = "partner_token"
TOKEN_DAYS = 7
MAX_ATTEMPTS, LOCK_MIN = 5, 15
PLANS = ("bronze", "silver", "gold")
DEFAULT_SETTINGS = {"id": "config", "commission_pct": 10.0, "duration_months": 24, "attribution_days": 30, "hold_days": 30,
                    "payout_frequency": "trimestrale", "min_payout_cents": 0, "auto_payout": False, "crmevent_tax_regime": "forfettario",
                    "payout_notes": "Liquidazioni da validare fiscalmente prima dell'attivazione dei pagamenti."}
CATEGORIE = ("professionista", "influencer", "agenzia", "organizzatore", "societa_sportiva", "altro")
SOGGETTI = ("privato", "professionista", "azienda")
CAT = Literal["professionista", "influencer", "agenzia", "organizzatore", "societa_sportiva", "altro"]
SOG = Literal["privato", "professionista", "azienda"]
TIPOLOGIE = {"persona_fisica": "Persona fisica", "professionista": "Professionista", "azienda": "Azienda", "influencer": "Influencer"}
TIP = Literal["persona_fisica", "professionista", "azienda", "influencer"]
STATO_IT = {"pending": "In attesa", "approved": "Approvato", "rejected": "Rifiutato", "suspended": "Sospeso"}
BREVO_PARTNER_LIST_ID = int(os.environ.get("BREVO_PARTNER_LIST_ID") or 18)
BREVO_ATTRS = {"PARTNER_TIPOLOGIA": "text", "PARTNER_RAGIONE_SOCIALE": "text", "PARTNER_CELLULARE": "text",
               "PARTNER_DATA_REGISTRAZIONE": "date", "PARTNER_STATO": "text", "PARTNER_CODICE": "text"}
KIND = {"subscription_create": "prima_sottoscrizione", "subscription_cycle": "rinnovo", "subscription_update": "upgrade"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(d: Optional[datetime] = None) -> str:
    return (d or _now()).isoformat()


def _dt(s: str) -> datetime:
    d = datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def partner_url() -> str:
    return (os.environ.get("PARTNER_URL") or "").rstrip("/")


def app_url() -> str:
    return (os.environ.get("APP_URL") or "").rstrip("/")


def commission_base_cents(inv: dict) -> int:
    """Importo abbonamento effettivamente incassato, imposte escluse (nessuna IVA presunta)."""
    paid = inv.get("amount_paid")
    paid = inv.get("total") or 0 if paid is None else paid
    tax = inv.get("tax")
    if tax is None:
        tax = sum((t or {}).get("amount", 0) or 0 for t in (inv.get("total_taxes") or inv.get("total_tax_amounts") or []))
    return max(0, int(paid) - int(tax or 0))


def _invoice_pi(inv: dict) -> Optional[str]:
    pi = inv.get("payment_intent")
    if isinstance(pi, dict):
        pi = pi.get("id")
    if pi:
        return pi
    for p in ((inv.get("payments") or {}).get("data") or []):
        v = (p.get("payment") or {}).get("payment_intent")
        if v:
            return v if isinstance(v, str) else v.get("id")
    return None


def _add_months(d: datetime, months: int) -> datetime:
    m = d.month - 1 + months
    return d.replace(year=d.year + m // 12, month=m % 12 + 1, day=min(d.day, 28))


def quarter_end(d: datetime) -> datetime:
    q = (d.month - 1) // 3
    return _add_months(d.replace(month=q * 3 + 1, day=1, hour=0, minute=0, second=0, microsecond=0), 3)


def quarter_label(d: datetime) -> str:
    return f"{d.year}-T{(d.month - 1) // 3 + 1}"


def com_status(c: dict, hold_days: int, now: Optional[datetime] = None) -> str:
    """maturata → liquidabile (trimestre chiuso e almeno hold_days dal pagamento) → in_liquidazione → pagata | stornata."""
    if c["status"] != "maturata":
        return c["status"]
    now = now or _now()
    pa = _dt(c["paid_at"])
    return "liquidabile" if now >= quarter_end(pa) and now >= pa + timedelta(days=hold_days) and c.get("commission_net_cents", 0) > 0 else "maturata"


def intl_phone(s: str) -> Optional[str]:
    t = re.sub(r"[\s\-./()]", "", s or "")
    if t.startswith("00"):
        t = "+" + t[2:]
    elif not t.startswith("+") and re.fullmatch(r"3\d{8,9}", t):
        t = "+39" + t
    return t if re.fullmatch(r"\+[1-9]\d{7,14}", t) else None


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:40]


class Indirizzo(BaseModel):
    via: Optional[str] = Field(default=None, max_length=160)
    cap: Optional[str] = Field(default=None, max_length=12)
    citta: Optional[str] = Field(default=None, max_length=80)
    provincia: Optional[str] = Field(default=None, max_length=40)
    paese: Optional[str] = Field(default="IT", max_length=40)


class ProfileIn(BaseModel):
    nome: Optional[str] = Field(default=None, max_length=80)
    cognome: Optional[str] = Field(default=None, max_length=80)
    telefono: Optional[str] = Field(default=None, max_length=30)
    categoria: Optional[CAT] = None
    soggetto: Optional[SOG] = None
    ragione_sociale: Optional[str] = Field(default=None, max_length=160)
    codice_fiscale: Optional[str] = Field(default=None, max_length=20)
    partita_iva: Optional[str] = Field(default=None, max_length=20)
    regime_fiscale: Optional[str] = Field(default=None, max_length=60)
    indirizzo: Optional[Indirizzo] = None
    sito_web: Optional[str] = Field(default=None, max_length=200)
    social: Optional[str] = Field(default=None, max_length=400)
    iban: Optional[str] = Field(default=None, max_length=40)
    accept_terms: Optional[bool] = None


class RegisterIn(BaseModel):
    nome: str = Field(min_length=1, max_length=80)
    cognome: str = Field(min_length=1, max_length=80)
    email: EmailStr
    telefono: str = Field(min_length=6, max_length=30)
    tipologia: TIP
    ragione_sociale: Optional[str] = Field(default=None, max_length=160)
    password: str = Field(min_length=8, max_length=200)
    password_confirm: str = Field(max_length=200)
    accept_terms: bool = False
    accept_privacy: bool = False


class BrevoSyncIn(BaseModel):
    only_failed: bool = True


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=200)


class TrackIn(BaseModel):
    ref: str = Field(max_length=20)
    cmp: Optional[str] = Field(default=None, max_length=60)


class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class StatusIn(BaseModel):
    status: Literal["pending", "approved", "rejected", "suspended"]
    note: Optional[str] = Field(default=None, max_length=300)


class SettingsIn(BaseModel):
    commission_pct: float = Field(ge=0, le=100)
    duration_months: int = Field(ge=1, le=120)
    attribution_days: int = Field(ge=1, le=365)
    hold_days: int = Field(ge=0, le=180)
    payout_frequency: Literal["trimestrale", "mensile", "semestrale"]
    min_payout_cents: int = Field(ge=0)
    crmevent_tax_regime: Literal["forfettario", "ordinario"]
    payout_notes: Optional[str] = Field(default=None, max_length=1000)


class AttributionIn(BaseModel):
    partner_id: Optional[str] = None
    campaign: Optional[str] = Field(default=None, max_length=60)
    note: str = Field(min_length=3, max_length=300)


class AdjustIn(BaseModel):
    amount_cents: int
    note: str = Field(min_length=3, max_length=300)


class PayoutIn(BaseModel):
    partner_id: str


class PayoutPaidIn(BaseModel):
    reference: Optional[str] = Field(default=None, max_length=120)


PROFILE_FIELDS = ("categoria", "soggetto", "ragione_sociale", "codice_fiscale", "partita_iva", "regime_fiscale", "indirizzo", "sito_web", "social", "iban")
PUBLIC_FIELDS = ("id", "email", "nome", "cognome", "telefono", "tipologia", "status", "code", "created_at", "approved_at", "auth_provider") + PROFILE_FIELDS


def public_partner(p: dict) -> dict:
    out = {k: p.get(k) for k in PUBLIC_FIELDS}
    out["has_password"] = bool(p.get("password_hash"))
    out["profile_complete"] = bool(p.get("categoria") and p.get("soggetto") and p.get("telefono") and p.get("accepted_terms_at"))
    out["referral_link"] = f"{app_url()}/registrati?ref={p['code']}" if p.get("code") else None
    return out


def _clean_profile(body: BaseModel, person_name) -> dict:
    upd = {}
    for k, v in body.model_dump(exclude_none=True).items():
        if k in ("accept_terms", "email", "password"):
            continue
        upd[k] = v.strip() if isinstance(v, str) else v
    for k in ("codice_fiscale", "iban"):
        if upd.get(k):
            upd[k] = re.sub(r"\s+", "", upd[k]).upper()
    for k in ("nome", "cognome"):
        if upd.get(k):
            upd[k] = person_name(upd[k])
    return upd


def _check_fiscal(merged: dict):
    if merged.get("soggetto") in ("professionista", "azienda") and not (merged.get("partita_iva") or "").strip():
        raise HTTPException(status_code=400, detail="La partita IVA è obbligatoria per professionisti e aziende")
    if merged.get("soggetto") == "azienda" and not (merged.get("ragione_sociale") or "").strip():
        raise HTTPException(status_code=400, detail="La ragione sociale è obbligatoria per le aziende")
    iban = merged.get("iban")
    if iban and not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", iban):
        raise HTTPException(status_code=400, detail="IBAN non valido")


def build(db, deps: dict) -> dict:
    r = APIRouter(prefix="/api")
    secret = os.environ["JWT_SECRET"]
    person_name = deps["person_name"]

    async def get_settings() -> dict:
        doc = await db.partner_settings.find_one({"id": "config"}, {"_id": 0}) or {}
        if doc and not doc.get("v2"):  # migrazione una tantum: 24 mesi + nuovi parametri
            doc.update({"duration_months": 24, "v2": True})
            await db.partner_settings.update_one({"id": "config"}, {"$set": {"duration_months": 24, "v2": True}})
        return {**DEFAULT_SETTINGS, **doc}

    async def ensure_indexes():
        await db.partner_commissions.create_index("stripe_invoice_id", unique=True)
        await db.partner_referrals.create_index("org_id", unique=True)
        await db.partners.create_index("email", unique=True)
        idx = (await db.partners.index_information()).get("code_1")
        if idx and not idx.get("partialFilterExpression"):
            await db.partners.drop_index("code_1")
        await db.partners.create_index("code", unique=True, partialFilterExpression={"code": {"$type": "string"}})
        await db.partner_reset_tokens.create_index("expires_at", expireAfterSeconds=0)
        await db.partner_clicks.create_index([("partner_id", 1), ("at", -1)])

    async def _new_code() -> str:
        while True:
            c = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))
            if not await db.partners.find_one({"code": c}, {"_id": 1}):
                return c

    def _set_cookie(resp: Response, partner_id: str):
        tok = jwt.encode({"sub": partner_id, "type": "partner", "exp": _now() + timedelta(days=TOKEN_DAYS)}, secret, algorithm="HS256")
        resp.set_cookie(COOKIE, tok, httponly=True, secure=True, samesite="none", max_age=TOKEN_DAYS * 86400, path="/")

    async def current_partner(request: Request) -> dict:
        tok = request.cookies.get(COOKIE)
        if not tok:
            raise HTTPException(status_code=401, detail="Non autenticato")
        try:
            pl = jwt.decode(tok, secret, algorithms=["HS256"])
        except jwt.PyJWTError:
            raise HTTPException(status_code=401, detail="Sessione scaduta")
        if pl.get("type") != "partner":
            raise HTTPException(status_code=401, detail="Sessione non valida")
        p = await db.partners.find_one({"id": pl["sub"]}, {"_id": 0})
        if not p:
            raise HTTPException(status_code=401, detail="Account partner non trovato")
        return p

    async def approved_partner(p: dict = Depends(current_partner)) -> dict:
        if p.get("status") != "approved":
            raise HTTPException(status_code=403, detail={"code": "partner_not_approved", "status": p.get("status"),
                                                         "message": "Il tuo account partner è in attesa di approvazione."})
        return p

    async def _mail(p: dict, subject: str, intro: str, cta: str, path: str):
        try:
            html = email_utils.link_email(name=p.get("nome") or "", intro=intro, cta_label=cta, url=f"{partner_url()}{path}",
                                          footer_note="Hai ricevuto questa email perché sei registrato al programma CRMEvent Partner.")
            await email_utils.send_email(to=p["email"], subject=subject, html=html)
        except Exception as e:
            log.warning("partner email failed: %s", type(e).__name__)

    brevo_attrs_ok = {"done": False}

    async def _brevo_attrs():
        if brevo_attrs_ok["done"]:
            return
        sc, data, err = await brevo_funnel._request("GET", "/v3/contacts/attributes")
        if sc != 200:
            raise RuntimeError(err or "Attributi Brevo non leggibili")
        have = {a.get("name") for a in (data or {}).get("attributes", [])}
        for name, typ in BREVO_ATTRS.items():
            if name not in have:
                sc2, _, err2 = await brevo_funnel._request("POST", f"/v3/contacts/attributes/normal/{name}", json={"type": typ})
                if sc2 not in (200, 201, 204):
                    raise RuntimeError(f"Creazione attributo {name}: {err2}")
        brevo_attrs_ok["done"] = True

    async def brevo_sync(pid: str) -> dict:
        p = await db.partners.find_one({"id": pid}, {"_id": 0})
        if not p:
            return {"ok": False, "error": "Partner non trovato"}
        res = {"ok": False, "error": "Brevo non configurato"}
        try:
            if brevo_funnel.is_configured():
                await _brevo_attrs()
                attrs = {"NOME": p.get("nome"), "COGNOME": p.get("cognome"), "SMS": p.get("telefono"), "PARTNER_CELLULARE": p.get("telefono"),
                         "PARTNER_TIPOLOGIA": TIPOLOGIE.get(p.get("tipologia")) or p.get("categoria"), "PARTNER_RAGIONE_SOCIALE": p.get("ragione_sociale"),
                         "PARTNER_DATA_REGISTRAZIONE": (p.get("created_at") or "")[:10] or None, "PARTNER_STATO": STATO_IT.get(p.get("status")),
                         "PARTNER_CODICE": p.get("code") if p.get("status") != "pending" else None}
                attrs = {k: v for k, v in attrs.items() if v}
                res = await brevo_funnel.upsert_registered_contact(email=p["email"], attributes=attrs, list_ids=[BREVO_PARTNER_LIST_ID])
                if not res["ok"] and "SMS" in attrs and "sms" in str(res.get("error") or "").lower():
                    attrs.pop("SMS")  # numero già associato a un altro contatto Brevo: resta in PARTNER_CELLULARE
                    res = await brevo_funnel.upsert_registered_contact(email=p["email"], attributes=attrs, list_ids=[BREVO_PARTNER_LIST_ID])
        except Exception as e:
            res = {"ok": False, "error": str(e)[:200] or type(e).__name__}
        st = {"status": "ok" if res["ok"] else "error", "at": _iso(), "error": None if res["ok"] else str(res.get("error"))[:200]}
        await db.partners.update_one({"id": pid}, {"$set": {"brevo_sync": st}})
        if not res["ok"]:
            log.warning("brevo partner sync failed partner=%s error=%s", pid, st["error"])
        return {"ok": res["ok"], "error": st["error"]}

    async def _after_register(p: dict):
        await _mail(p, "Abbiamo ricevuto la tua candidatura CRMEvent Partner",
                    "Grazie per la tua richiesta di adesione al programma CRMEvent Partner. Il nostro team verificherà i dati e riceverai un'email quando il tuo account sarà approvato.",
                    "Vai al portale partner", "/")
        try:
            html = email_utils.link_email(name="", intro=f"Nuova richiesta partner: {p.get('nome')} {p.get('cognome')} ({p['email']}), tipologia {TIPOLOGIE.get(p.get('tipologia'))}"
                                          f"{', ' + p['ragione_sociale'] if p.get('ragione_sociale') else ''}. Approva o rifiuta la richiesta dal Super Admin.",
                                          cta_label="Apri Super Admin → Partner", url=f"{app_url()}/piattaforma/partner", footer_note="Notifica automatica CRMEvent Partner.")
            await email_utils.send_email(to=os.environ["ADMIN_EMAIL"], subject="Nuova richiesta CRMEvent Partner", html=html)
        except Exception as e:
            log.warning("partner admin notify failed: %s", type(e).__name__)
        await brevo_sync(p["id"])

    # ---------- pubblico ----------
    @r.get("/partner/public-config")
    async def public_config():
        s = await get_settings()
        cfg = await deps["saas_config"]()
        plans = [{"key": k, "label": p.get("label"), "color": p.get("color"), "semester": round(p.get("monthly", 0) * 6, 2), "yearly": p.get("yearly")}
                 for k, p in (cfg.get("plans") or {}).items() if p.get("active", True) and k in PLANS]
        return {"commission_pct": s["commission_pct"], "duration_months": s["duration_months"], "attribution_days": s["attribution_days"],
                "payout_frequency": s["payout_frequency"], "plans": plans}

    @r.post("/partner/track")
    async def track(body: TrackIn, request: Request):
        code = re.sub(r"[^A-Z0-9]", "", body.ref.upper())[:12]
        p = await db.partners.find_one({"code": code, "status": "approved"}, {"_id": 0, "id": 1}) if code else None
        if not p:
            return {"ok": False}
        day = _now().strftime("%Y-%m-%d")
        ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "")).split(",")[0].strip()
        fp = hashlib.sha256(f"{ip}|{request.headers.get('user-agent', '')}|{day}|{secret}".encode()).hexdigest()[:32]
        cmp = slugify(body.cmp or "") or None
        if not await db.partner_clicks.find_one({"partner_id": p["id"], "fp": fp, "cmp": cmp, "at": {"$gte": _iso(_now() - timedelta(minutes=30))}}, {"_id": 1}):
            await db.partner_clicks.insert_one({"partner_id": p["id"], "cmp": cmp, "fp": fp, "day": day, "at": _iso()})
        return {"ok": True}

    @r.post("/partner/register")
    async def register(body: RegisterIn):
        if not body.accept_terms or not body.accept_privacy:
            raise HTTPException(status_code=400, detail="Devi accettare le condizioni del programma Partner e la Privacy Policy")
        if body.password != body.password_confirm:
            raise HTTPException(status_code=400, detail="Le password non coincidono")
        tel = intl_phone(body.telefono)
        if not tel:
            raise HTTPException(status_code=400, detail="Numero di cellulare non valido: usa il formato internazionale, es. +39 333 1234567")
        rs = (body.ragione_sociale or "").strip() or None
        if body.tipologia == "azienda" and not rs:
            raise HTTPException(status_code=400, detail="La ragione sociale è obbligatoria per le aziende")
        email = body.email.lower()
        if await db.partners.find_one({"email": email}, {"_id": 1}):
            raise HTTPException(status_code=409, detail="Esiste già una registrazione partner con questa email. Accedi o recupera la password.")
        t = body.tipologia
        p = {"id": uuid.uuid4().hex, "email": email, "nome": person_name(body.nome.strip()), "cognome": person_name(body.cognome.strip()), "telefono": tel,
             "tipologia": t, "ragione_sociale": rs, "soggetto": {"professionista": "professionista", "azienda": "azienda"}.get(t, "privato"),
             "categoria": {"influencer": "influencer", "professionista": "professionista"}.get(t, "altro"),
             "password_hash": deps["hash_password"](body.password), "auth_provider": "password", "status": "pending",
             "accepted_terms_at": _iso(), "accepted_privacy_at": _iso(), "created_at": _iso()}
        try:
            await db.partners.insert_one(dict(p))
        except DuplicateKeyError:
            raise HTTPException(status_code=409, detail="Esiste già una registrazione partner con questa email. Accedi o recupera la password.")
        asyncio.create_task(_after_register(p))
        return {"ok": True, "email": email, "status": "pending"}

    @r.post("/partner/login")
    async def login(body: LoginIn, request: Request, response: Response):
        email = body.email.lower()
        ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "-")).split(",")[0].strip()
        ident = f"{ip}:{email}"
        att = await db.partner_login_attempts.find_one({"identifier": ident}, {"_id": 0})
        if att and att.get("count", 0) >= MAX_ATTEMPTS and att.get("locked_until") and _dt(att["locked_until"]) > _now():
            raise HTTPException(status_code=429, detail="Troppi tentativi. Riprova tra 15 minuti.")
        p = await db.partners.find_one({"email": email}, {"_id": 0})
        if not p or not p.get("password_hash") or not deps["verify_password"](body.password, p["password_hash"]):
            n = (att or {}).get("count", 0) + 1
            await db.partner_login_attempts.update_one({"identifier": ident}, {"$set": {"count": n, "locked_until": _iso(_now() + timedelta(minutes=LOCK_MIN)) if n >= MAX_ATTEMPTS else None}}, upsert=True)
            raise HTTPException(status_code=401, detail="Credenziali non valide")
        await db.partner_login_attempts.delete_one({"identifier": ident})
        await db.partners.update_one({"id": p["id"]}, {"$set": {"last_login_at": _iso()}})
        _set_cookie(response, p["id"])
        return public_partner(p)

    @r.post("/partner/logout")
    async def logout(response: Response):
        response.delete_cookie(COOKIE, path="/", secure=True, samesite="none")
        return {"ok": True}

    @r.post("/partner/forgot-password")
    async def forgot(body: ForgotIn):
        p = await db.partners.find_one({"email": body.email.lower()}, {"_id": 0})
        if p:
            tok = secrets.token_urlsafe(32)
            await db.partner_reset_tokens.insert_one({"hash": hashlib.sha256(tok.encode()).hexdigest(), "partner_id": p["id"], "used": False,
                                                      "expires_at": _now() + timedelta(hours=1)})
            await _mail(p, "Reimposta la password CRMEvent Partner", "Hai chiesto di reimpostare la password dell'area partner. Il link è valido per 1 ora.",
                        "Reimposta password", f"/reimposta-password?token={tok}")
        return {"ok": True}

    @r.post("/partner/reset-password")
    async def reset(body: ResetIn):
        t = await db.partner_reset_tokens.find_one_and_update({"hash": hashlib.sha256(body.token.encode()).hexdigest(), "used": False}, {"$set": {"used": True}})
        if not t or t["expires_at"].replace(tzinfo=timezone.utc) < _now():
            raise HTTPException(status_code=400, detail="Link scaduto o non valido. Richiedi un nuovo link.")
        await db.partners.update_one({"id": t["partner_id"]}, {"$set": {"password_hash": deps["hash_password"](body.password), "updated_at": _iso()}})
        return {"ok": True}

    @r.get("/partner/me")
    async def me(p: dict = Depends(current_partner)):
        return public_partner(p)

    @r.patch("/partner/profile")
    async def profile(body: ProfileIn, p: dict = Depends(current_partner)):
        upd = _clean_profile(body, person_name)
        _check_fiscal({**p, **upd})
        if body.accept_terms and not p.get("accepted_terms_at"):
            upd["accepted_terms_at"] = _iso()
        if upd:
            await db.partners.update_one({"id": p["id"]}, {"$set": {**upd, "updated_at": _iso()}})
        return public_partner(await db.partners.find_one({"id": p["id"]}, {"_id": 0}))

    # ---------- statistiche condivise ----------
    async def partner_stats(pid: Optional[str] = None) -> dict:
        q = {"partner_id": pid} if pid else {}
        clicks = await db.partner_clicks.count_documents(q)
        uniq = len(await db.partner_clicks.distinct("fp", q))
        refs = await db.partner_referrals.find(q, {"_id": 0}).to_list(5000)
        orgs = {o["id"]: o for o in await db.organizations.find({"id": {"$in": [x["org_id"] for x in refs]}}, {"_id": 0, "id": 1, "saas": 1}).to_list(5000)}
        trial = sum(1 for x in refs if ((orgs.get(x["org_id"]) or {}).get("saas") or {}).get("mode") == "trial")
        active = sum(1 for x in refs if ((orgs.get(x["org_id"]) or {}).get("saas") or {}).get("stripe_status") in ("active", "past_due"))
        converted = sum(1 for x in refs if x.get("first_paid_at"))
        coms = await db.partner_commissions.find(q, {"_id": 0}).to_list(20000)
        s = await get_settings()
        tot = {"maturate_cents": 0, "liquidabili_cents": 0, "in_liquidazione_cents": 0, "pagate_cents": 0}
        for c in coms:
            st = com_status(c, s["hold_days"])
            k = {"maturata": "maturate_cents", "liquidabile": "liquidabili_cents", "in_liquidazione": "in_liquidazione_cents", "pagata": "pagate_cents"}.get(st)
            if k:
                tot[k] += c.get("commission_net_cents", 0)
        revenue = sum(c.get("base_cents", 0) - round(c.get("base_cents", 0) * (c.get("refunded_cents", 0) / c["amount_paid_cents"]) if c.get("amount_paid_cents") else 0) for c in coms)
        return {"clicks": clicks, "visitors": uniq, "registrations": len(refs), "trial": trial, "active": active, "converted": converted,
                "conversion_rate": round(converted / len(refs) * 100, 1) if refs else 0.0, "click_to_signup": round(len(refs) / uniq * 100, 1) if uniq else 0.0,
                "revenue_cents": revenue, **tot}

    async def campaign_stats(pid: Optional[str] = None) -> list:
        m = {"partner_id": pid} if pid else {}
        out = {}
        for x in await db.partner_clicks.aggregate([{"$match": m}, {"$group": {"_id": {"p": "$partner_id", "c": "$cmp"}, "clicks": {"$sum": 1}, "fps": {"$addToSet": "$fp"}}}]).to_list(5000):
            out[(x["_id"]["p"], x["_id"]["c"])] = {"clicks": x["clicks"], "visitors": len(x["fps"]), "registrations": 0, "converted": 0}
        for x in await db.partner_referrals.find(m, {"_id": 0, "partner_id": 1, "campaign": 1, "first_paid_at": 1}).to_list(5000):
            row = out.setdefault((x["partner_id"], x.get("campaign")), {"clicks": 0, "visitors": 0, "registrations": 0, "converted": 0})
            row["registrations"] += 1
            row["converted"] += 1 if x.get("first_paid_at") else 0
        return [{"partner_id": k[0], "campaign": k[1] or "principale", **v} for k, v in out.items()]

    def _com_out(c: dict, s: dict) -> dict:
        keys = ("id", "org_name", "paid_at", "kind", "plan", "billing_cycle", "base_cents", "commission_pct", "commission_cents", "commission_net_cents",
                "refunded_cents", "payout_id", "adjustments")
        return {**{k: c.get(k) for k in keys}, "status": com_status(c, s["hold_days"])}

    @r.get("/partner/dashboard")
    async def dashboard(p: dict = Depends(approved_partner)):
        s = await get_settings()
        refs = await db.partner_referrals.find({"partner_id": p["id"]}, {"_id": 0}).sort("created_at", -1).to_list(2000)
        orgs = {o["id"]: o for o in await db.organizations.find({"id": {"$in": [x["org_id"] for x in refs]}}, {"_id": 0, "id": 1, "nome": 1, "saas": 1}).to_list(2000)}
        rows = []
        for x in refs:
            sa = (orgs.get(x["org_id"]) or {}).get("saas") or {}
            stato = "abbonato" if sa.get("stripe_status") in ("active", "past_due") else "prova" if sa.get("mode") == "trial" else "non_attivo"
            rows.append({"id": x["id"], "org_name": (orgs.get(x["org_id"]) or {}).get("nome") or x.get("org_name"), "created_at": x["created_at"],
                         "campaign": x.get("campaign"), "plan": sa.get("plan") if stato == "abbonato" else None, "stato": stato,
                         "commission_until": x.get("commission_until")})
        coms = await db.partner_commissions.find({"partner_id": p["id"]}, {"_id": 0}).sort("paid_at", -1).to_list(5000)
        payouts = await db.partner_payouts.find({"partner_id": p["id"]}, {"_id": 0, "iban_snapshot": 0}).sort("created_at", -1).to_list(500)
        camps = await db.partner_campaigns.find({"partner_id": p["id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
        cst = {x["campaign"]: x for x in await campaign_stats(p["id"])}
        for c in camps:
            c["link"] = f"{app_url()}/registrati?ref={p['code']}&cmp={c['slug']}"
            c["stats"] = cst.get(c["slug"], {"clicks": 0, "visitors": 0, "registrations": 0, "converted": 0})
        return {"partner": public_partner(p), "stats": await partner_stats(p["id"]), "referrals": rows, "commissions": [_com_out(c, s) for c in coms],
                "payouts": payouts, "campaigns": camps, "main_stats": cst.get("principale", {"clicks": 0, "visitors": 0, "registrations": 0, "converted": 0}),
                "settings": {k: s[k] for k in ("commission_pct", "duration_months", "attribution_days", "hold_days", "payout_frequency")}}

    @r.post("/partner/campaigns")
    async def add_campaign(body: CampaignIn, p: dict = Depends(approved_partner)):
        slug = slugify(body.name)
        if not slug or slug == "principale":
            raise HTTPException(status_code=400, detail="Nome campagna non valido")
        if await db.partner_campaigns.count_documents({"partner_id": p["id"]}) >= 50:
            raise HTTPException(status_code=400, detail="Hai raggiunto il numero massimo di campagne")
        if await db.partner_campaigns.find_one({"partner_id": p["id"], "slug": slug}, {"_id": 1}):
            raise HTTPException(status_code=400, detail="Esiste già una campagna con questo nome")
        c = {"id": uuid.uuid4().hex, "partner_id": p["id"], "name": body.name.strip(), "slug": slug, "created_at": _iso()}
        await db.partner_campaigns.insert_one(dict(c))
        return c

    @r.delete("/partner/campaigns/{cid}")
    async def del_campaign(cid: str, p: dict = Depends(approved_partner)):
        await db.partner_campaigns.delete_one({"id": cid, "partner_id": p["id"]})
        return {"ok": True}

    @r.get("/partner/materials")
    async def materials(p: dict = Depends(approved_partner)):
        return await db.partner_materials.find({"active": True}, {"_id": 0, "file_path": 0}).sort("created_at", -1).to_list(200)

    @r.get("/partner/materials/{mid}/file")
    async def material_file(mid: str, p: dict = Depends(approved_partner)):
        m = await db.partner_materials.find_one({"id": mid, "active": True}, {"_id": 0})
        if not m or not m.get("file_path"):
            raise HTTPException(status_code=404, detail="File non trovato")
        try:
            data, ct = storage_utils.read(m["file_path"], m.get("storage_backend"), m.get("content_type"))
        except Exception:
            raise HTTPException(status_code=404, detail="File non trovato")
        return Response(data, media_type=ct, headers={"Content-Disposition": f'attachment; filename="{m.get("file_name") or "materiale"}"'})

    # ---------- referral e commissioni (chiamati dal backend principale) ----------
    async def attach_referral(org_id: str, org_name: str, user: dict, ref) -> bool:
        ref = ref or {}
        code = re.sub(r"[^A-Z0-9]", "", str(ref.get("code") or "").upper())[:12]
        if not code:
            return False
        s = await get_settings()
        try:
            at = _dt(ref["at"]) if ref.get("at") else _now()
        except (ValueError, TypeError):
            return False
        if at < _now() - timedelta(days=s["attribution_days"]) or at > _now() + timedelta(minutes=5):
            return False
        p = await db.partners.find_one({"code": code, "status": "approved"}, {"_id": 0})
        email = (user.get("email") or "").lower()
        if not p or p["email"] == email or (p.get("telefono") and p.get("telefono") == user.get("telefono")):
            return False
        try:
            await db.partner_referrals.insert_one({"id": uuid.uuid4().hex, "partner_id": p["id"], "partner_code": code, "org_id": org_id, "org_name": org_name,
                                                  "campaign": slugify(ref.get("cmp") or "") or None, "ref_at": _iso(at), "created_at": _iso(),
                                                  "first_paid_at": None, "commission_until": None, "source": "referral"})
        except Exception:  # indice univoco org_id: un solo partner per organizzazione
            return False
        log.info("referral org=%s partner=%s", org_id, p["id"])
        return True

    async def on_subscription_paid(org: dict, inv: dict):
        sa = org.get("saas") or {}
        ref = await db.partner_referrals.find_one({"org_id": org["id"]}, {"_id": 0})
        if not ref or not inv.get("id") or sa.get("plan") not in PLANS or (inv.get("status") and inv.get("status") != "paid"):
            return
        p = await db.partners.find_one({"id": ref["partner_id"]}, {"_id": 0})
        if not p or p.get("status") != "approved":
            return
        s = await get_settings()
        paid_at = datetime.fromtimestamp(inv["created"], timezone.utc) if inv.get("created") else _now()
        if not ref.get("first_paid_at"):
            until = _add_months(paid_at, int(s["duration_months"]))
            await db.partner_referrals.update_one({"id": ref["id"]}, {"$set": {"first_paid_at": _iso(paid_at), "commission_until": _iso(until)}})
            ref["commission_until"] = _iso(until)
        if paid_at > _dt(ref["commission_until"]):
            return
        base = commission_base_cents(inv)
        if base <= 0:
            return
        pct = float(s["commission_pct"])
        com = int(round(base * pct / 100))
        doc = {"id": uuid.uuid4().hex, "partner_id": p["id"], "org_id": org["id"], "org_name": org.get("nome"), "stripe_invoice_id": inv["id"],
               "payment_intent": _invoice_pi(inv), "paid_at": _iso(paid_at), "kind": KIND.get(inv.get("billing_reason"), "altro"),
               "plan": sa.get("plan"), "billing_cycle": sa.get("billing_cycle"), "amount_paid_cents": inv.get("amount_paid"),
               "base_cents": base, "commission_pct": pct, "commission_cents": com, "commission_net_cents": com, "refunded_cents": 0,
               "crmevent_tax_regime": s["crmevent_tax_regime"],
               "partner_fiscal": {k: p.get(k) for k in ("soggetto", "regime_fiscale", "partita_iva", "codice_fiscale")},
               "status": "maturata", "adjustments": [{"at": _iso(), "type": "maturazione", "amount_cents": com, "note": f"{pct}% di {base / 100:.2f} €"}],
               "created_at": _iso()}
        try:
            await db.partner_commissions.insert_one(doc)
        except Exception:  # idempotenza: indice univoco su stripe_invoice_id
            return

    async def on_refund(charge: dict) -> bool:
        inv_id = charge.get("invoice") if isinstance(charge.get("invoice"), str) else (charge.get("invoice") or {}).get("id")
        pi = charge.get("payment_intent") if isinstance(charge.get("payment_intent"), str) else (charge.get("payment_intent") or {}).get("id")
        q = [x for x in ({"stripe_invoice_id": inv_id} if inv_id else None, {"payment_intent": pi} if pi else None) if x]
        c = await db.partner_commissions.find_one({"$or": q}, {"_id": 0}) if q else None
        if not c:
            return False
        amount, refunded = charge.get("amount") or 0, charge.get("amount_refunded") or 0
        ratio = min(1.0, refunded / amount) if amount else 1.0
        manual = sum(a["amount_cents"] for a in c.get("adjustments", []) if a["type"] == "rettifica")
        net = max(0, int(round(c["commission_cents"] * (1 - ratio))) + manual)
        prev = c.get("commission_net_cents", c["commission_cents"])
        if net == prev and refunded == c.get("refunded_cents"):
            return True
        upd = {"refunded_cents": refunded, "commission_net_cents": net, "updated_at": _iso()}
        if c["status"] in ("pagata", "in_liquidazione") and net < prev:
            upd["recupero_cents"] = prev - net + c.get("recupero_cents", 0)
        elif net == 0:
            upd["status"] = "stornata"
        await db.partner_commissions.update_one({"id": c["id"]}, {"$set": upd, "$push": {"adjustments": {"at": _iso(), "type": "storno_rimborso", "amount_cents": net - prev,
                                                                                                         "note": f"Rimborso Stripe {refunded / 100:.2f} €"}}})
        return True

    # ---------- Google (intent=partner) ----------
    async def google_identity(ident: dict) -> RedirectResponse:
        base = partner_url()
        if not ident.get("email_verified"):
            return RedirectResponse(f"{base}/login?google_error=unverified", status_code=302)
        p = await db.partners.find_one({"google_sub": ident["sub"]}, {"_id": 0}) or await db.partners.find_one({"email": ident["email"]}, {"_id": 0})
        if p and p.get("google_sub") and p["google_sub"] != ident["sub"]:
            return RedirectResponse(f"{base}/login?google_error=conflict", status_code=302)
        if not p:
            name = (ident.get("name") or "").split(" ", 1)
            p = {"id": uuid.uuid4().hex, "email": ident["email"], "auth_provider": "google", "google_sub": ident["sub"],
                 "nome": person_name(name[0]) if name[0] else None, "cognome": person_name(name[1]) if len(name) > 1 else None,
                 "status": "pending", "created_at": _iso()}
            await db.partners.insert_one(dict(p))
            asyncio.create_task(brevo_sync(p["id"]))
        else:
            await db.partners.update_one({"id": p["id"]}, {"$set": {"google_sub": ident["sub"], "last_login_at": _iso()}})
        resp = RedirectResponse(f"{base}{'/dashboard' if public_partner(p)['profile_complete'] else '/completa-profilo'}", status_code=302)
        _set_cookie(resp, p["id"])
        return resp

    # ---------- Super Admin ----------
    sa_dep = deps["require_superadmin"]
    audit = deps["record_audit"]

    @r.get("/platform/partners")
    async def sa_partners(q: str = "", status: str = "", admin: dict = Depends(sa_dep)):
        f = {}
        if status in ("pending", "approved", "rejected", "suspended"):
            f["status"] = status
        if q.strip():
            rx = {"$regex": re.escape(q.strip()), "$options": "i"}
            f["$or"] = [{"email": rx}, {"nome": rx}, {"cognome": rx}, {"ragione_sociale": rx}, {"code": rx}, {"partita_iva": rx}, {"codice_fiscale": rx}]
        ps = await db.partners.find(f, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(2000)
        refs = {x["_id"]: x["n"] for x in await db.partner_referrals.aggregate([{"$group": {"_id": "$partner_id", "n": {"$sum": 1}}}]).to_list(2000)}
        return [{**public_partner(p), "referrals": refs.get(p["id"], 0), "status_note": p.get("status_note"), "brevo_sync": p.get("brevo_sync")} for p in ps]

    @r.post("/platform/partners/brevo-sync")
    async def sa_brevo_sync_all(body: BrevoSyncIn, admin: dict = Depends(sa_dep)):
        f = {"brevo_sync.status": {"$ne": "ok"}} if body.only_failed else {}
        ids = [x["id"] for x in await db.partners.find(f, {"_id": 0, "id": 1}).to_list(2000)]
        res = [await brevo_sync(i) for i in ids]
        ok = sum(1 for x in res if x["ok"])
        await audit(admin, "partner_brevo_sync", detail=f"{ok}/{len(ids)} sincronizzati")
        return {"total": len(ids), "ok": ok, "failed": len(ids) - ok, "errors": [x["error"] for x in res if not x["ok"]][:5]}

    @r.post("/platform/partners/{pid}/brevo-sync")
    async def sa_brevo_sync_one(pid: str, admin: dict = Depends(sa_dep)):
        return await brevo_sync(pid)

    @r.get("/platform/partners/{pid}")
    async def sa_partner(pid: str, admin: dict = Depends(sa_dep)):
        p = await db.partners.find_one({"id": pid}, {"_id": 0, "password_hash": 0})
        if not p:
            raise HTTPException(status_code=404, detail="Partner non trovato")
        return {"partner": {**public_partner(p), "status_note": p.get("status_note"), "last_login_at": p.get("last_login_at")}, "stats": await partner_stats(pid),
                "campaigns": await campaign_stats(pid)}

    @r.post("/platform/partners/{pid}/status")
    async def sa_status(pid: str, body: StatusIn, admin: dict = Depends(sa_dep)):
        p = await db.partners.find_one({"id": pid}, {"_id": 0})
        if not p:
            raise HTTPException(status_code=404, detail="Partner non trovato")
        upd = {"status": body.status, "status_note": body.note, "updated_at": _iso()}
        if body.status == "approved" and not p.get("approved_at"):
            upd["approved_at"] = _iso()
        if body.status == "approved" and not p.get("code"):
            upd["code"] = p["code"] = await _new_code()
        await db.partners.update_one({"id": pid}, {"$set": upd})
        await audit(admin, "partner_status", detail=f"{p['email']} → {body.status}")
        asyncio.create_task(brevo_sync(pid))
        if body.status != p.get("status") and body.status == "approved":
            how = "con il tuo account Google" if p.get("auth_provider") == "google" else "con la password scelta in fase di registrazione"
            await _mail(p, "Benvenuto nel programma CRMEvent Partner",
                        f"La tua candidatura è stata approvata. Accedi all'area partner con l'email {p['email']} {how}. "
                        f"Nella dashboard trovi il tuo link referral personale (codice {p['code']}): copialo e condividilo con gli organizzatori di eventi.",
                        "Accedi all'area partner", "/login")
        elif body.status != p.get("status") and body.status == "rejected":
            await _mail(p, "Candidatura CRMEvent Partner", "Dopo la verifica non possiamo approvare la tua candidatura al programma partner. Per informazioni scrivi a support@crmevent.it.",
                        "Vai al portale partner", "/")
        return {"ok": True, "status": body.status}

    @r.get("/platform/partner-stats")
    async def sa_stats(admin: dict = Depends(sa_dep)):
        ps = await db.partners.find({}, {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "email": 1, "code": 1, "status": 1}).to_list(2000)
        names = {p["id"]: f"{p.get('nome') or ''} {p.get('cognome') or ''}".strip() or p["email"] for p in ps}
        per = [{"partner_id": p["id"], "name": names[p["id"]], "code": p["code"], "status": p["status"], **await partner_stats(p["id"])} for p in ps]
        camps = [{**c, "name": names.get(c["partner_id"], c["partner_id"])} for c in await campaign_stats()]
        return {"totals": await partner_stats(), "partners": per, "campaigns": camps}

    @r.get("/platform/partner-referrals")
    async def sa_referrals(admin: dict = Depends(sa_dep)):
        refs = await db.partner_referrals.find({}, {"_id": 0}).sort("created_at", -1).to_list(5000)
        orgs = {o["id"]: o for o in await db.organizations.find({"id": {"$in": [x["org_id"] for x in refs]}}, {"_id": 0, "id": 1, "nome": 1, "saas": 1, "created_at": 1}).to_list(5000)}
        names = {p["id"]: f"{p.get('nome') or ''} {p.get('cognome') or ''}".strip() or p["email"] for p in await db.partners.find({}, {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "email": 1}).to_list(2000)}
        renew = {x["_id"]: x for x in await db.partner_commissions.aggregate([{"$group": {"_id": "$org_id", "n": {"$sum": 1}, "rinnovi": {"$sum": {"$cond": [{"$eq": ["$kind", "rinnovo"]}, 1, 0]}},
                                                                                         "last": {"$max": "$paid_at"}}}]).to_list(5000)}
        out = []
        for x in refs:
            o = orgs.get(x["org_id"]) or {}
            sa = o.get("saas") or {}
            out.append({**x, "partner_name": names.get(x["partner_id"]), "org_name": o.get("nome") or x.get("org_name"), "plan": sa.get("plan"),
                        "billing_cycle": sa.get("billing_cycle"), "saas_mode": sa.get("mode"), "stripe_status": sa.get("stripe_status"),
                        "payments": (renew.get(x["org_id"]) or {}).get("n", 0), "renewals": (renew.get(x["org_id"]) or {}).get("rinnovi", 0),
                        "last_payment_at": (renew.get(x["org_id"]) or {}).get("last")})
        return out

    @r.put("/platform/partner-referrals/{org_id}")
    async def sa_set_attribution(org_id: str, body: AttributionIn, admin: dict = Depends(sa_dep)):
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "id": 1, "nome": 1})
        if not org:
            raise HTTPException(status_code=404, detail="Organizzazione non trovata")
        old = await db.partner_referrals.find_one({"org_id": org_id}, {"_id": 0})
        if body.partner_id:
            p = await db.partners.find_one({"id": body.partner_id}, {"_id": 0})
            if not p:
                raise HTTPException(status_code=404, detail="Partner non trovato")
            if old:
                await db.partner_referrals.update_one({"org_id": org_id}, {"$set": {"partner_id": p["id"], "partner_code": p["code"], "campaign": slugify(body.campaign or "") or None,
                                                                                    "source": "manuale", "updated_at": _iso()}})
            else:
                await db.partner_referrals.insert_one({"id": uuid.uuid4().hex, "partner_id": p["id"], "partner_code": p["code"], "org_id": org_id, "org_name": org.get("nome"),
                                                      "campaign": slugify(body.campaign or "") or None, "created_at": _iso(), "first_paid_at": None,
                                                      "commission_until": None, "source": "manuale"})
        elif old:
            await db.partner_referrals.delete_one({"org_id": org_id})
        await db.partner_attribution_log.insert_one({"id": uuid.uuid4().hex, "org_id": org_id, "org_name": org.get("nome"), "from_partner_id": (old or {}).get("partner_id"),
                                                    "to_partner_id": body.partner_id, "note": body.note, "by": admin.get("email"), "at": _iso()})
        await audit(admin, "partner_attribution", org_id=org_id, org_name=org.get("nome"), detail=f"{(old or {}).get('partner_id')} → {body.partner_id}: {body.note}")
        return {"ok": True}

    @r.get("/platform/partner-attribution-log")
    async def sa_attr_log(admin: dict = Depends(sa_dep)):
        return await db.partner_attribution_log.find({}, {"_id": 0}).sort("at", -1).to_list(1000)

    async def _commissions(partner_id: Optional[str], status: Optional[str]) -> list:
        s = await get_settings()
        names = {p["id"]: f"{p.get('nome') or ''} {p.get('cognome') or ''}".strip() or p["email"] for p in await db.partners.find({}, {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "email": 1}).to_list(2000)}
        rows = [{**c, "status": com_status(c, s["hold_days"]), "partner_name": names.get(c["partner_id"])}
                for c in await db.partner_commissions.find({"partner_id": partner_id} if partner_id else {}, {"_id": 0}).sort("paid_at", -1).to_list(20000)]
        return [x for x in rows if not status or x["status"] == status]

    @r.get("/platform/partner-commissions")
    async def sa_commissions(partner_id: Optional[str] = None, status: Optional[str] = None, admin: dict = Depends(sa_dep)):
        return await _commissions(partner_id, status)

    @r.get("/platform/partner-commissions.csv")
    async def sa_commissions_csv(partner_id: Optional[str] = None, status: Optional[str] = None, admin: dict = Depends(sa_dep)):
        buf = io.StringIO()
        buf.write("\ufeff")
        w = csv.writer(buf, delimiter=";")
        w.writerow(["ID", "Partner", "Organizzazione", "Data pagamento", "Tipo", "Piano", "Durata", "ID fattura Stripe", "Incassato netto imposte €",
                    "Percentuale", "Commissione €", "Rimborsato €", "Commissione netta €", "Stato", "Liquidazione", "Regime CRMEvent", "Soggetto partner"])
        f = lambda c: f"{(c or 0) / 100:.2f}".replace(".", ",")  # noqa: E731
        for c in await _commissions(partner_id, status):
            w.writerow([c["id"], c.get("partner_name"), c.get("org_name"), c["paid_at"][:10], c.get("kind"), c.get("plan"), c.get("billing_cycle"), c["stripe_invoice_id"],
                        f(c["base_cents"]), str(c["commission_pct"]).replace(".", ","), f(c["commission_cents"]), f(c.get("refunded_cents")), f(c.get("commission_net_cents")),
                        c["status"], c.get("payout_id") or "", c.get("crmevent_tax_regime"), (c.get("partner_fiscal") or {}).get("soggetto")])
        return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
                                 headers={"Content-Disposition": f'attachment; filename="commissioni-partner-{_now():%Y%m%d}.csv"'})

    @r.post("/platform/partner-commissions/{cid}/adjust")
    async def sa_adjust(cid: str, body: AdjustIn, admin: dict = Depends(sa_dep)):
        c = await db.partner_commissions.find_one({"id": cid}, {"_id": 0})
        if not c or c["status"] in ("pagata", "in_liquidazione"):
            raise HTTPException(status_code=400, detail="Commissione non rettificabile (già in liquidazione o pagata)")
        net = max(0, c.get("commission_net_cents", 0) + body.amount_cents)
        await db.partner_commissions.update_one({"id": cid}, {"$set": {"commission_net_cents": net, "status": "stornata" if net == 0 else "maturata", "updated_at": _iso()},
                                                             "$push": {"adjustments": {"at": _iso(), "type": "rettifica", "amount_cents": body.amount_cents, "note": body.note, "by": admin.get("email")}}})
        await audit(admin, "partner_commission_adjust", detail=f"{cid}: {body.amount_cents} ({body.note})")
        return {"ok": True, "commission_net_cents": net}

    @r.get("/platform/partner-payouts")
    async def sa_payouts(admin: dict = Depends(sa_dep)):
        return await db.partner_payouts.find({}, {"_id": 0}).sort("created_at", -1).to_list(2000)

    @r.post("/platform/partner-payouts")
    async def sa_payout_create(body: PayoutIn, admin: dict = Depends(sa_dep)):
        p = await db.partners.find_one({"id": body.partner_id}, {"_id": 0})
        if not p:
            raise HTTPException(status_code=404, detail="Partner non trovato")
        if not p.get("iban"):
            raise HTTPException(status_code=400, detail="Il partner non ha ancora indicato l'IBAN: richiedilo prima della liquidazione")
        s = await get_settings()
        coms = [c for c in await db.partner_commissions.find({"partner_id": p["id"], "status": "maturata"}, {"_id": 0}).to_list(5000) if com_status(c, s["hold_days"]) == "liquidabile"]
        amount = sum(c["commission_net_cents"] for c in coms)
        if not coms or amount < s["min_payout_cents"]:
            raise HTTPException(status_code=400, detail="Nessuna commissione liquidabile per questo partner")
        po = {"id": uuid.uuid4().hex, "partner_id": p["id"], "partner_name": f"{p.get('nome') or ''} {p.get('cognome') or ''}".strip(), "period": quarter_label(_now() - timedelta(days=1)),
              "commission_ids": [c["id"] for c in coms], "amount_cents": amount, "status": "in_preparazione", "iban_snapshot": p["iban"],
              "fiscal_snapshot": {k: p.get(k) for k in ("soggetto", "ragione_sociale", "codice_fiscale", "partita_iva", "regime_fiscale", "indirizzo")},
              "crmevent_tax_regime": s["crmevent_tax_regime"], "created_at": _iso(), "created_by": admin.get("email")}
        await db.partner_payouts.insert_one(dict(po))
        await db.partner_commissions.update_many({"id": {"$in": po["commission_ids"]}, "status": "maturata"}, {"$set": {"status": "in_liquidazione", "payout_id": po["id"]}})
        await audit(admin, "partner_payout_create", detail=f"{p['email']} {amount / 100:.2f} €")
        po.pop("_id", None)
        return po

    @r.post("/platform/partner-payouts/{poid}/paid")
    async def sa_payout_paid(poid: str, body: PayoutPaidIn, admin: dict = Depends(sa_dep)):
        res = await db.partner_payouts.update_one({"id": poid, "status": "in_preparazione"}, {"$set": {"status": "pagata", "paid_at": _iso(), "reference": body.reference, "paid_by": admin.get("email")}})
        if not res.modified_count:
            raise HTTPException(status_code=400, detail="Liquidazione non aggiornabile")
        await db.partner_commissions.update_many({"payout_id": poid, "status": "in_liquidazione"}, {"$set": {"status": "pagata", "liquidata_at": _iso()}})
        await audit(admin, "partner_payout_paid", detail=poid)
        return {"ok": True}

    @r.post("/platform/partner-payouts/{poid}/cancel")
    async def sa_payout_cancel(poid: str, admin: dict = Depends(sa_dep)):
        res = await db.partner_payouts.update_one({"id": poid, "status": "in_preparazione"}, {"$set": {"status": "annullata", "canceled_at": _iso()}})
        if not res.modified_count:
            raise HTTPException(status_code=400, detail="Liquidazione non annullabile")
        await db.partner_commissions.update_many({"payout_id": poid, "status": "in_liquidazione"}, {"$set": {"status": "maturata"}, "$unset": {"payout_id": ""}})
        return {"ok": True}

    @r.get("/platform/partner-settings")
    async def sa_settings(admin: dict = Depends(sa_dep)):
        return await get_settings()

    @r.put("/platform/partner-settings")
    async def sa_settings_put(body: SettingsIn, admin: dict = Depends(sa_dep)):
        await db.partner_settings.update_one({"id": "config"}, {"$set": {**body.model_dump(), "v2": True, "updated_at": _iso(), "updated_by": admin.get("email")}}, upsert=True)
        await audit(admin, "partner_settings", detail=f"{body.commission_pct}% · {body.duration_months} mesi · attribuzione {body.attribution_days} gg · regime {body.crmevent_tax_regime}")
        return await get_settings()

    @r.get("/platform/partner-materials")
    async def sa_materials(admin: dict = Depends(sa_dep)):
        return await db.partner_materials.find({}, {"_id": 0, "file_path": 0}).sort("created_at", -1).to_list(500)

    @r.post("/platform/partner-materials")
    async def sa_material_add(title: str = Form(..., max_length=120), description: str = Form("", max_length=600), url: str = Form("", max_length=500),
                              file: Optional[UploadFile] = File(None), admin: dict = Depends(sa_dep)):
        if not url.strip() and not file:
            raise HTTPException(status_code=400, detail="Indica un link o carica un file")
        if url.strip() and not re.match(r"^https?://", url.strip()):
            raise HTTPException(status_code=400, detail="Link non valido")
        m = {"id": uuid.uuid4().hex, "title": title.strip(), "description": description.strip(), "url": url.strip() or None, "active": True, "created_at": _iso()}
        if file:
            data = await file.read()
            if len(data) > 20 * 1024 * 1024:
                raise HTTPException(status_code=400, detail="File troppo grande (max 20 MB)")
            name = re.sub(r"[^A-Za-z0-9._-]", "_", file.filename or "file")[-80:]
            ct = file.content_type or "application/octet-stream"
            saved = storage_utils.save(f"partner_materials/{m['id']}_{name}", data, ct)
            m.update({"file_path": saved["path"], "storage_backend": saved.get("backend"), "content_type": ct, "file_name": name, "has_file": True})
        await db.partner_materials.insert_one(dict(m))
        m.pop("file_path", None)
        return m

    @r.delete("/platform/partner-materials/{mid}")
    async def sa_material_del(mid: str, admin: dict = Depends(sa_dep)):
        await db.partner_materials.delete_one({"id": mid})
        return {"ok": True}

    # ---------- anteprima portale (solo sviluppo: PARTNER_PREVIEW_DIR) ----------
    @r.get("/partner-preview")
    @r.get("/partner-preview/{path:path}")
    async def preview(path: str = ""):
        root = os.environ.get("PARTNER_PREVIEW_DIR")
        if not root or not Path(root, "index.html").is_file():
            raise HTTPException(status_code=404, detail="Not found")
        base = Path(root).resolve()
        f = (base / path).resolve()
        if path and base in f.parents and f.is_file():
            return FileResponse(f)
        return FileResponse(base / "index.html", headers={"Cache-Control": "no-store"})

    return {"router": r, "attach_referral": attach_referral, "on_subscription_paid": on_subscription_paid, "on_refund": on_refund,
            "google_identity": google_identity, "get_settings": get_settings, "ensure_indexes": ensure_indexes}
