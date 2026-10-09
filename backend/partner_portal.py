"""CRMEvent Partner: account partner (cookie separato), referral, commissioni sugli abbonamenti incassati e anteprima portale."""
import logging
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, EmailStr, Field

log = logging.getLogger("partner_portal")
COOKIE = "partner_token"
TOKEN_DAYS = 7
MAX_ATTEMPTS, LOCK_MIN = 5, 15
DEFAULT_SETTINGS = {"id": "config", "commission_pct": 10.0, "duration_months": 12, "crmevent_tax_regime": "forfettario"}
TAX_REGIMES = ("forfettario", "ordinario")
PARTNER_TYPES = ("privato", "professionista", "azienda")
STATUSES = ("pending", "approved", "rejected", "suspended")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(d: Optional[datetime] = None) -> str:
    return (d or _now()).isoformat()


def partner_url() -> str:
    return (os.environ.get("PARTNER_URL") or "").rstrip("/")


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
    y, m = d.year + m // 12, m % 12 + 1
    return d.replace(year=y, month=m, day=min(d.day, 28))


class RegisterIn(BaseModel):
    nome: str = Field(min_length=1, max_length=80)
    cognome: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    telefono: str = Field(min_length=6, max_length=30)
    tipo: Literal["privato", "professionista", "azienda"]
    ragione_sociale: Optional[str] = Field(default=None, max_length=160)
    codice_fiscale: Optional[str] = Field(default=None, max_length=20)
    partita_iva: Optional[str] = Field(default=None, max_length=20)
    regime_fiscale: Optional[str] = Field(default=None, max_length=60)
    accept_terms: bool = False


class ProfileIn(BaseModel):
    nome: Optional[str] = Field(default=None, max_length=80)
    cognome: Optional[str] = Field(default=None, max_length=80)
    telefono: Optional[str] = Field(default=None, max_length=30)
    tipo: Optional[Literal["privato", "professionista", "azienda"]] = None
    ragione_sociale: Optional[str] = Field(default=None, max_length=160)
    codice_fiscale: Optional[str] = Field(default=None, max_length=20)
    partita_iva: Optional[str] = Field(default=None, max_length=20)
    regime_fiscale: Optional[str] = Field(default=None, max_length=60)
    iban: Optional[str] = Field(default=None, max_length=40)
    accept_terms: Optional[bool] = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class StatusIn(BaseModel):
    status: Literal["pending", "approved", "rejected", "suspended"]
    note: Optional[str] = Field(default=None, max_length=300)


class SettingsIn(BaseModel):
    commission_pct: float = Field(ge=0, le=100)
    duration_months: int = Field(ge=1, le=120)
    crmevent_tax_regime: Literal["forfettario", "ordinario"]


FISCAL_FIELDS = ("tipo", "ragione_sociale", "codice_fiscale", "partita_iva", "regime_fiscale", "iban")
PUBLIC_FIELDS = ("id", "email", "nome", "cognome", "telefono", "status", "code", "created_at", "approved_at", "auth_provider") + FISCAL_FIELDS


def public_partner(p: dict) -> dict:
    out = {k: p.get(k) for k in PUBLIC_FIELDS}
    out["has_password"] = bool(p.get("password_hash"))
    out["profile_complete"] = bool(p.get("tipo") and p.get("telefono") and p.get("accepted_terms_at"))
    out["referral_link"] = f"{(os.environ.get('APP_URL') or '').rstrip('/')}/registrati?ref={p.get('code')}"
    return out


def build(db, deps: dict) -> dict:
    r = APIRouter(prefix="/api")
    secret = os.environ["JWT_SECRET"]

    async def get_settings() -> dict:
        doc = await db.partner_settings.find_one({"id": "config"}, {"_id": 0})
        return {**DEFAULT_SETTINGS, **(doc or {})}

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

    # ---------- pubblico ----------
    @r.get("/partner/public-config")
    async def public_config():
        s = await get_settings()
        cfg = await deps["saas_config"]()
        plans = [{"key": k, "label": p.get("label"), "color": p.get("color"), "semester": round(p.get("monthly", 0) * 6, 2), "yearly": p.get("yearly")}
                 for k, p in (cfg.get("plans") or {}).items() if p.get("active", True)]
        return {"commission_pct": s["commission_pct"], "duration_months": s["duration_months"], "plans": plans}

    @r.post("/partner/register")
    async def register(body: RegisterIn, response: Response):
        if not body.accept_terms:
            raise HTTPException(status_code=400, detail="Devi accettare le condizioni del programma partner")
        email = body.email.lower()
        if await db.partners.find_one({"email": email}, {"_id": 1}):
            raise HTTPException(status_code=400, detail="Email già registrata come partner")
        if body.tipo != "privato" and not (body.partita_iva or "").strip():
            raise HTTPException(status_code=400, detail="La partita IVA è obbligatoria per professionisti e aziende")
        p = {"id": uuid.uuid4().hex, "email": email, "password_hash": deps["hash_password"](body.password), "auth_provider": "password",
             "nome": deps["person_name"](body.nome), "cognome": deps["person_name"](body.cognome), "telefono": body.telefono.strip(),
             "tipo": body.tipo, "ragione_sociale": (body.ragione_sociale or "").strip() or None,
             "codice_fiscale": (body.codice_fiscale or "").strip().upper() or None, "partita_iva": (body.partita_iva or "").strip() or None,
             "regime_fiscale": (body.regime_fiscale or "").strip() or None, "status": "pending", "code": await _new_code(),
             "accepted_terms_at": _iso(), "created_at": _iso()}
        await db.partners.insert_one(dict(p))
        _set_cookie(response, p["id"])
        return public_partner(p)

    @r.post("/partner/login")
    async def login(body: LoginIn, request: Request, response: Response):
        email = body.email.lower()
        ident = f"{request.client.host if request.client else '-'}:{email}"
        att = await db.partner_login_attempts.find_one({"identifier": ident}, {"_id": 0})
        if att and att.get("count", 0) >= MAX_ATTEMPTS and att.get("locked_until") and datetime.fromisoformat(att["locked_until"]) > _now():
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

    @r.get("/partner/me")
    async def me(p: dict = Depends(current_partner)):
        return public_partner(p)

    @r.patch("/partner/profile")
    async def profile(body: ProfileIn, p: dict = Depends(current_partner)):
        upd = {k: (v.strip() if isinstance(v, str) else v) for k, v in body.model_dump(exclude_none=True).items() if k != "accept_terms"}
        if "codice_fiscale" in upd:
            upd["codice_fiscale"] = upd["codice_fiscale"].upper()
        for k in ("nome", "cognome"):
            if k in upd:
                upd[k] = deps["person_name"](upd[k])
        if body.accept_terms:
            upd["accepted_terms_at"] = p.get("accepted_terms_at") or _iso()
        tipo = upd.get("tipo", p.get("tipo"))
        if tipo and tipo != "privato" and not (upd.get("partita_iva", p.get("partita_iva")) or "").strip():
            raise HTTPException(status_code=400, detail="La partita IVA è obbligatoria per professionisti e aziende")
        if upd:
            await db.partners.update_one({"id": p["id"]}, {"$set": {**upd, "updated_at": _iso()}})
        return public_partner(await db.partners.find_one({"id": p["id"]}, {"_id": 0}))

    @r.get("/partner/dashboard")
    async def dashboard(p: dict = Depends(approved_partner)):
        refs = await db.partner_referrals.find({"partner_id": p["id"]}, {"_id": 0}).sort("created_at", -1).to_list(1000)
        coms = await db.partner_commissions.find({"partner_id": p["id"]}, {"_id": 0}).sort("paid_at", -1).to_list(2000)
        orgs = {o["id"]: o for o in await db.organizations.find({"id": {"$in": [x["org_id"] for x in refs]}}, {"_id": 0, "id": 1, "nome": 1, "saas": 1}).to_list(1000)}
        rows = []
        for x in refs:
            s = (orgs.get(x["org_id"]) or {}).get("saas") or {}
            rows.append({"org_id": x["org_id"], "org_name": (orgs.get(x["org_id"]) or {}).get("nome") or x.get("org_name"), "created_at": x["created_at"],
                         "plan": s.get("plan"), "billing_cycle": s.get("billing_cycle"), "paying": bool(x.get("first_paid_at")) and s.get("stripe_status") in ("active", "trialing", "past_due"),
                         "first_paid_at": x.get("first_paid_at"), "commission_until": x.get("commission_until")})
        net = lambda c: c.get("commission_net_cents", c.get("commission_cents", 0))  # noqa: E731
        tot = {"maturate_cents": sum(net(c) for c in coms if c["status"] == "maturata"), "pagate_cents": sum(net(c) for c in coms if c["status"] == "pagata"),
               "referrals": len(refs), "paganti": sum(1 for x in rows if x["paying"])}
        return {"partner": public_partner(p), "totals": tot, "referrals": rows,
                "commissions": [{k: c.get(k) for k in ("id", "org_name", "paid_at", "base_cents", "commission_pct", "commission_cents", "commission_net_cents", "refunded_cents", "status", "plan", "billing_cycle")} for c in coms]}

    # ---------- referral e commissioni (chiamati dal backend principale) ----------
    async def attach_referral(org_id: str, org_name: str, user_email: str, code: Optional[str]) -> bool:
        code = re.sub(r"[^A-Z0-9]", "", (code or "").upper())[:12]
        if not code:
            return False
        p = await db.partners.find_one({"code": code, "status": "approved"}, {"_id": 0})
        if not p or p["email"] == (user_email or "").lower() or await db.partner_referrals.find_one({"org_id": org_id}, {"_id": 1}):
            return False
        await db.partner_referrals.insert_one({"id": uuid.uuid4().hex, "partner_id": p["id"], "partner_code": code, "org_id": org_id,
                                              "org_name": org_name, "created_at": _iso(), "first_paid_at": None, "commission_until": None})
        log.info("referral org=%s partner=%s", org_id, p["id"])
        return True

    async def on_subscription_paid(org: dict, inv: dict):
        ref = await db.partner_referrals.find_one({"org_id": org["id"]}, {"_id": 0})
        if not ref or not inv.get("id") or await db.partner_commissions.find_one({"stripe_invoice_id": inv["id"]}, {"_id": 1}):
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
        if paid_at > datetime.fromisoformat(ref["commission_until"]):
            return
        base = commission_base_cents(inv)
        if base <= 0:
            return
        pct = float(s["commission_pct"])
        com = int(round(base * pct / 100))
        sa = org.get("saas") or {}
        await db.partner_commissions.insert_one({
            "id": uuid.uuid4().hex, "partner_id": p["id"], "org_id": org["id"], "org_name": org.get("nome"), "stripe_invoice_id": inv["id"],
            "payment_intent": _invoice_pi(inv), "paid_at": _iso(paid_at), "plan": sa.get("plan"), "billing_cycle": sa.get("billing_cycle"),
            "amount_paid_cents": inv.get("amount_paid"), "tax_cents": (inv.get("amount_paid") or 0) - base if inv.get("amount_paid") is not None else None,
            "base_cents": base, "commission_pct": pct, "commission_cents": com, "commission_net_cents": com, "refunded_cents": 0,
            "crmevent_tax_regime": s["crmevent_tax_regime"], "partner_fiscal": {k: p.get(k) for k in ("tipo", "regime_fiscale", "partita_iva", "codice_fiscale")},
            "status": "maturata", "created_at": _iso()})

    async def on_refund(charge: dict) -> bool:
        inv_id = charge.get("invoice") if isinstance(charge.get("invoice"), str) else (charge.get("invoice") or {}).get("id")
        pi = charge.get("payment_intent") if isinstance(charge.get("payment_intent"), str) else (charge.get("payment_intent") or {}).get("id")
        q = [x for x in ({"stripe_invoice_id": inv_id} if inv_id else None, {"payment_intent": pi} if pi else None) if x]
        c = await db.partner_commissions.find_one({"$or": q}, {"_id": 0}) if q else None
        if not c:
            return False
        amount, refunded = charge.get("amount") or 0, charge.get("amount_refunded") or 0
        ratio = min(1.0, refunded / amount) if amount else 1.0
        net = int(round(c["commission_cents"] * (1 - ratio)))
        upd = {"refunded_cents": refunded, "commission_net_cents": net, "updated_at": _iso()}
        if c["status"] == "pagata" and net < c.get("commission_net_cents", c["commission_cents"]):
            upd["recupero_cents"] = c.get("commission_net_cents", c["commission_cents"]) - net + c.get("recupero_cents", 0)
        elif net == 0:
            upd["status"] = "stornata"
        await db.partner_commissions.update_one({"id": c["id"]}, {"$set": upd})
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
                 "nome": deps["person_name"](name[0]) if name[0] else None, "cognome": deps["person_name"](name[1]) if len(name) > 1 else None,
                 "status": "pending", "code": await _new_code(), "created_at": _iso()}
            await db.partners.insert_one(dict(p))
        else:
            await db.partners.update_one({"id": p["id"]}, {"$set": {"google_sub": ident["sub"], "last_login_at": _iso()}})
        complete = p.get("tipo") and p.get("telefono") and p.get("accepted_terms_at")
        resp = RedirectResponse(f"{base}{'/dashboard' if complete else '/completa-profilo'}", status_code=302)
        _set_cookie(resp, p["id"])
        return resp

    # ---------- Super Admin ----------
    sa = deps["require_superadmin"]

    @r.get("/platform/partners")
    async def sa_partners(admin: dict = Depends(sa)):
        ps = await db.partners.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(2000)
        agg = {x["_id"]: x for x in await db.partner_commissions.aggregate([{"$group": {"_id": "$partner_id",
               "maturate": {"$sum": {"$cond": [{"$eq": ["$status", "maturata"]}, "$commission_net_cents", 0]}},
               "pagate": {"$sum": {"$cond": [{"$eq": ["$status", "pagata"]}, "$commission_net_cents", 0]}}}}]).to_list(2000)}
        refs = {x["_id"]: x["n"] for x in await db.partner_referrals.aggregate([{"$group": {"_id": "$partner_id", "n": {"$sum": 1}}}]).to_list(2000)}
        return [{**public_partner(p), "referrals": refs.get(p["id"], 0), "maturate_cents": (agg.get(p["id"]) or {}).get("maturate", 0),
                 "pagate_cents": (agg.get(p["id"]) or {}).get("pagate", 0)} for p in ps]

    @r.post("/platform/partners/{pid}/status")
    async def sa_status(pid: str, body: StatusIn, admin: dict = Depends(sa)):
        p = await db.partners.find_one({"id": pid}, {"_id": 0})
        if not p:
            raise HTTPException(status_code=404, detail="Partner non trovato")
        upd = {"status": body.status, "status_note": body.note, "updated_at": _iso()}
        if body.status == "approved" and not p.get("approved_at"):
            upd["approved_at"] = _iso()
        await db.partners.update_one({"id": pid}, {"$set": upd})
        await deps["record_audit"](admin, "partner_status", detail=f"{p['email']} → {body.status}")
        return {"ok": True, "status": body.status}

    @r.get("/platform/partner-settings")
    async def sa_settings(admin: dict = Depends(sa)):
        return await get_settings()

    @r.put("/platform/partner-settings")
    async def sa_settings_put(body: SettingsIn, admin: dict = Depends(sa)):
        await db.partner_settings.update_one({"id": "config"}, {"$set": {**body.model_dump(), "updated_at": _iso(), "updated_by": admin.get("email")}}, upsert=True)
        await deps["record_audit"](admin, "partner_settings", detail=f"{body.commission_pct}% · {body.duration_months} mesi · regime {body.crmevent_tax_regime}")
        return await get_settings()

    @r.get("/platform/partner-commissions")
    async def sa_commissions(partner_id: Optional[str] = None, admin: dict = Depends(sa)):
        return await db.partner_commissions.find({"partner_id": partner_id} if partner_id else {}, {"_id": 0}).sort("paid_at", -1).to_list(5000)

    @r.post("/platform/partner-commissions/{cid}/paid")
    async def sa_mark_paid(cid: str, admin: dict = Depends(sa)):
        res = await db.partner_commissions.update_one({"id": cid, "status": "maturata"}, {"$set": {"status": "pagata", "liquidata_at": _iso(), "liquidata_by": admin.get("email")}})
        if not res.modified_count:
            raise HTTPException(status_code=400, detail="Commissione non liquidabile")
        await deps["record_audit"](admin, "partner_commission_paid", detail=cid)
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
            "google_identity": google_identity, "get_settings": get_settings}
