from dotenv import load_dotenv
from pathlib import Path
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import re
import uuid
import logging
import secrets
import time
import hashlib
import json
from collections import defaultdict
import support_service
from datetime import datetime, timezone, timedelta
from typing import List, Optional

import jwt
import bcrypt
import httpx
from fastapi import FastAPI, APIRouter, Request, Response, HTTPException, Depends, UploadFile, File, Header
from fastapi.responses import RedirectResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr

import asyncio
import email_utils
import storage_utils
import gcal_utils
import brevo_funnel

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

JWT_SECRET = os.environ['JWT_SECRET']
JWT_ALG = "HS256"
FRONTEND_URL = os.environ.get("FRONTEND_URL", "")
APP_URL = os.environ.get("APP_URL") or FRONTEND_URL
EMERGENT_SESSION_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"

app = FastAPI(title="CRMEvent API")
api = APIRouter(prefix="/api")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("crmevent")

ADMIN_ROLES = {"admin"}  # organization admin (org owner)
TRIAL_DAYS = 14
PRICE_MONTHLY = 19.90
PRICE_YEARLY = 199.00


# ---------------- helpers ----------------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return uuid.uuid4().hex


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except Exception:
        return False


def create_access_token(user_id: str, email: str) -> str:
    payload = {"sub": user_id, "email": email, "type": "access",
               "exp": datetime.now(timezone.utc) + timedelta(days=7)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def set_auth_cookie(response: Response, name: str, value: str, max_age: int):
    response.set_cookie(key=name, value=value, httponly=True, secure=True,
                        samesite="none", max_age=max_age, path="/")


async def resolve_user_from_token(token: str) -> Optional[dict]:
    sess = await db.user_sessions.find_one({"session_token": token})
    if sess:
        exp = sess.get("expires_at")
        if isinstance(exp, str):
            exp = datetime.fromisoformat(exp)
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp > datetime.now(timezone.utc):
            return await db.users.find_one({"user_id": sess["user_id"]}, {"_id": 0, "password_hash": 0})
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        if payload.get("type") == "access":
            return await db.users.find_one({"user_id": payload["sub"]}, {"_id": 0, "password_hash": 0})
    except jwt.PyJWTError:
        return None
    return None


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("session_token") or request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Non autenticato")
    user = await resolve_user_from_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Sessione non valida o scaduta")
    if user.get("active") is False:
        raise HTTPException(status_code=403, detail="Accesso disabilitato")
    return user


async def _resolve_active_org(request: Request, user: dict):
    """Resolve the effective (org_id, org_role) for this request.
    - Super Admin: any org via server-validated X-Org-Id header (audited impersonation).
    - Operational user: only an org for which an ACTIVE membership exists; the optional
      X-Org-Id header must match one of those memberships, else 403. Defaults to primary.
    Data always stays org-scoped through oq() — no cross-tenant bypass."""
    if user.get("role") == "superadmin":
        acting = request.headers.get("X-Org-Id")
        if not acting:
            raise HTTPException(status_code=428, detail="Seleziona un'organizzazione attiva")
        org = await db.organizations.find_one({"id": acting}, {"_id": 0})
        if not org:
            raise HTTPException(status_code=404, detail="Organizzazione non trovata")
        return acting, "superadmin"
    mems = await db.memberships.find({"user_id": user["user_id"], "active": True}, {"_id": 0}).to_list(200)
    if not mems:
        raise HTTPException(status_code=403, detail="Nessuna organizzazione associata all'account")
    header = request.headers.get("X-Org-Id")
    chosen = None
    if header:
        chosen = next((m for m in mems if m["org_id"] == header), None)
        if not chosen:
            raise HTTPException(status_code=403, detail="Accesso all'organizzazione non consentito")
    if not chosen:
        chosen = next((m for m in mems if m["org_id"] == user.get("org_id")), None) or mems[0]
    org = await db.organizations.find_one({"id": chosen["org_id"]}, {"_id": 0})
    if not org or org.get("status") == "disabled":
        raise HTTPException(status_code=403, detail="Organizzazione non disponibile")
    return chosen["org_id"], chosen["role"]


async def require_admin(request: Request, user: dict = Depends(get_current_user)) -> dict:
    org_id, org_role = await _resolve_active_org(request, user)
    return {**user, "org_id": org_id, "org_role": org_role, "acting_org": org_id}


async def require_org_admin(request: Request, user: dict = Depends(get_current_user)) -> dict:
    org_id, org_role = await _resolve_active_org(request, user)
    if org_role not in ("admin_org", "superadmin"):
        raise HTTPException(status_code=403, detail="Riservato agli amministratori dell'organizzazione")
    return {**user, "org_id": org_id, "org_role": org_role, "acting_org": org_id}


async def require_superadmin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "superadmin":
        raise HTTPException(status_code=403, detail="Accesso riservato al Super Admin CRMEvent")
    return user


async def require_support_manager(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="Accesso riservato")
    return user


def oq(user: dict, **extra) -> dict:
    """Org-scoped Mongo query: pins the current user's org_id. Anti cross-tenant."""
    return {"org_id": user["org_id"], **extra}


# ---------------- multi-tenant & subscription ----------------
def _days_left(iso_dt: Optional[str]) -> int:
    if not iso_dt:
        return 0
    try:
        d = datetime.fromisoformat(iso_dt)
    except Exception:
        return 0
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    secs = (d - datetime.now(timezone.utc)).total_seconds()
    return max(0, int((secs + 86399) // 86400))


def _sub_summary(org: dict) -> dict:
    otype = (org or {}).get("type", "cliente")
    sub = (org or {}).get("subscription", {}) or {}
    if otype != "cliente":
        # Internal/Test organizations: no trial, no Stripe, no CRMEvent billing.
        return {"status": otype, "plan": sub.get("plan", "crmevent"), "billing_cycle": None,
                "trial_end": None, "current_period_end": None, "days_left": None,
                "access": "full", "price_monthly": PRICE_MONTHLY, "price_yearly": PRICE_YEARLY,
                "org_type": otype}
    status = sub.get("status", "trial")
    trial_end = sub.get("trial_end")
    period_end = sub.get("current_period_end")
    ref = trial_end if status == "trial" else period_end
    days_left = _days_left(ref)
    if status == "trial" and days_left <= 0:
        status = "expired"
    active = status == "active" or (status == "trial" and days_left > 0)
    return {"status": status, "plan": sub.get("plan", "crmevent"),
            "billing_cycle": sub.get("billing_cycle"), "trial_end": trial_end,
            "current_period_end": period_end, "days_left": days_left,
            "access": "full" if active else "limited",
            "price_monthly": PRICE_MONTHLY, "price_yearly": PRICE_YEARLY, "org_type": "cliente"}


async def _create_organization(name: str, owner_user_id: Optional[str] = None,
                               org_type: str = "cliente", status: str = "active") -> dict:
    now = datetime.now(timezone.utc)
    if org_type == "cliente":
        sub = {"status": "trial", "plan": "crmevent", "billing_cycle": None,
               "trial_start": now.isoformat(),
               "trial_end": (now + timedelta(days=TRIAL_DAYS)).isoformat(),
               "current_period_end": None, "stripe_customer_id": None, "stripe_subscription_id": None}
    else:
        # Internal / Test orgs never enter a trial or Stripe flow.
        sub = {"status": org_type, "plan": "crmevent", "billing_cycle": None, "trial_start": None,
               "trial_end": None, "current_period_end": None, "stripe_customer_id": None,
               "stripe_subscription_id": None}
    org = {"id": new_id(), "nome": name, "type": org_type, "status": status,
           "owner_user_id": owner_user_id, "subscription": sub,
           "created_at": now_iso(), "updated_at": now_iso()}
    await db.organizations.insert_one(org)
    return org


async def _ensure_membership(user_id: str, org_id: str, role: str, added_by: Optional[str] = None):
    existing = await db.memberships.find_one({"user_id": user_id, "org_id": org_id})
    if existing:
        return existing, False
    doc = {"id": new_id(), "user_id": user_id, "org_id": org_id, "role": role,
           "active": True, "permissions": {}, "added_by": added_by,
           "created_at": now_iso(), "updated_at": now_iso(), "last_login_at": None}
    await db.memberships.insert_one(doc)
    return doc, True


async def _can_manage_org(user: dict, org_id: str) -> bool:
    if user.get("role") == "superadmin":
        return True
    m = await db.memberships.find_one({"user_id": user["user_id"], "org_id": org_id, "active": True})
    return bool(m and m.get("role") == "admin_org")


async def _guard_last_admin(org: dict, exclude_user_id: str) -> None:
    """A Client org must always keep at least one active Admin Organizzazione."""
    if org.get("type") != "cliente":
        return
    admins = await db.memberships.find(
        {"org_id": org["id"], "role": "admin_org", "active": True}, {"_id": 0}).to_list(500)
    if not [m for m in admins if m["user_id"] != exclude_user_id]:
        raise HTTPException(status_code=400,
                            detail="L'organizzazione Cliente deve mantenere almeno un Admin Organizzazione. Assegnane un altro prima di procedere.")


# ---------------- generic crud ----------------
async def _create(coll, data):
    doc = {**data, "id": new_id(), "created_at": now_iso(), "updated_at": now_iso()}
    await db[coll].insert_one(doc)
    doc.pop("_id", None)
    return doc


async def _list(coll, query=None):
    return await db[coll].find(query or {}, {"_id": 0}).sort("created_at", -1).to_list(5000)


async def _get(coll, _id):
    doc = await db[coll].find_one({"id": _id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Elemento non trovato")
    return doc


async def _update(coll, _id, data):
    clean = {k: v for k, v in data.items() if v is not None}
    clean["updated_at"] = now_iso()
    res = await db[coll].update_one({"id": _id}, {"$set": clean})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Elemento non trovato")
    return await _get(coll, _id)


async def _delete(coll, _id):
    await db[coll].delete_one({"id": _id})
    return {"ok": True}


# ---------------- auth ----------------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    name: str


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ChangePwIn(BaseModel):
    current_password: str
    new_password: str


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str
    new_password: str


class ActivateIn(BaseModel):
    token: str
    password: str
    name: Optional[str] = None


def public_user(u: dict) -> dict:
    return {"user_id": u["user_id"], "email": u["email"], "name": u.get("name"),
            "role": u.get("role", "admin"), "picture": u.get("picture", ""),
            "auth_provider": u.get("auth_provider", "password"), "person_id": u.get("person_id"),
            "org_id": u.get("org_id")}


async def user_payload(u: dict, active_org_id: Optional[str] = None) -> dict:
    base = public_user(u)
    role = u.get("role")
    if role == "superadmin":
        base["needs_org"] = False
        return base
    if role in ("volunteer", "staff"):
        base["needs_org"] = not bool(u.get("org_id"))
        if u.get("org_id"):
            org = await db.organizations.find_one({"id": u["org_id"]}, {"_id": 0})
            base["org_name"] = (org or {}).get("nome")
        return base
    # Operational member (global role admin/user/member) — access via memberships.
    mems = await db.memberships.find({"user_id": u["user_id"], "active": True}, {"_id": 0}).to_list(200)
    orgs_out = []
    for m in mems:
        org = await db.organizations.find_one({"id": m["org_id"]}, {"_id": 0})
        if not org or org.get("status") == "disabled":
            continue
        orgs_out.append({"org_id": org["id"], "nome": org.get("nome"), "type": org.get("type", "cliente"),
                         "role": m["role"], "status": org.get("status", "active")})
    base["organizations"] = orgs_out
    if not orgs_out:
        base["needs_org"] = True
        return base
    chosen = next((o for o in orgs_out if o["org_id"] == active_org_id), None) \
        or next((o for o in orgs_out if o["org_id"] == u.get("org_id")), None) or orgs_out[0]
    org = await db.organizations.find_one({"id": chosen["org_id"]}, {"_id": 0})
    base["needs_org"] = False
    base["org_id"] = chosen["org_id"]
    base["active_org_id"] = chosen["org_id"]
    base["org_name"] = chosen["nome"]
    base["org_role"] = chosen["role"]
    base["org_type"] = chosen["type"]
    base["subscription"] = _sub_summary(org)
    return base


class OrgRegisterIn(BaseModel):
    nome: str
    cognome: Optional[str] = None
    email: EmailStr
    password: str
    org_name: str
    telefono: Optional[str] = None
    accept_terms: bool = False


class CompleteOrgIn(BaseModel):
    org_name: str
    telefono: Optional[str] = None
    accept_terms: bool = False


@api.post("/auth/register-organization")
async def register_organization(body: OrgRegisterIn, response: Response):
    if not body.accept_terms:
        raise HTTPException(status_code=400, detail="Devi accettare le condizioni per registrarti")
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="La password deve avere almeno 8 caratteri")
    if not body.org_name.strip():
        raise HTTPException(status_code=400, detail="Il nome dell'organizzazione è obbligatorio")
    email = body.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email già registrata")
    uid = f"user_{uuid.uuid4().hex[:12]}"
    org = await _create_organization(body.org_name.strip(), uid)
    full_name = f"{body.nome} {body.cognome or ''}".strip()
    await db.users.insert_one({"user_id": uid, "email": email, "name": full_name,
                               "password_hash": hash_password(body.password), "role": "admin",
                               "auth_provider": "password", "org_id": org["id"], "telefono": body.telefono,
                               "picture": "", "active": True, "accepted_terms_at": now_iso(), "created_at": now_iso()})
    await _ensure_membership(uid, org["id"], "admin_org", uid)
    # Lead continuity: if this email already requested a demo, link that lead to the new account
    # (no duplicate contact) and advance the funnel — preserving the lead → demo → trial history.
    lead = await db.leads.find_one({"email": email})
    if lead:
        await db.leads.update_one({"id": lead["id"]}, {"$set": {"user_id": uid,
            "funnel_status": "trial_started", "funnel_ts_trial_started": now_iso(), "updated_at": now_iso()}})
        await _sync_brevo_funnel_status(email, "trial_started")
        # Immediate STOP: close the active demo enrollment so emails 2/3/4 never fire post-conversion.
        await _stop_active_demo_enrollment(lead["id"], "trial_started")
    token = create_access_token(uid, email)
    set_auth_cookie(response, "access_token", token, 7 * 24 * 3600)
    u = await db.users.find_one({"user_id": uid}, {"_id": 0})
    return await user_payload(u)


@api.post("/auth/complete-organization")
async def complete_organization(body: CompleteOrgIn, user: dict = Depends(get_current_user)):
    if user.get("role") == "superadmin":
        raise HTTPException(status_code=400, detail="Il Super Admin non crea organizzazioni")
    if user.get("org_id"):
        raise HTTPException(status_code=400, detail="Organizzazione già presente")
    if not body.accept_terms:
        raise HTTPException(status_code=400, detail="Devi accettare le condizioni per continuare")
    if not body.org_name.strip():
        raise HTTPException(status_code=400, detail="Il nome dell'organizzazione è obbligatorio")
    org = await _create_organization(body.org_name.strip(), user["user_id"])
    await db.users.update_one({"user_id": user["user_id"]},
                              {"$set": {"org_id": org["id"], "role": "admin", "telefono": body.telefono,
                                        "accepted_terms_at": now_iso()}})
    await _ensure_membership(user["user_id"], org["id"], "admin_org", user["user_id"])
    u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    return await user_payload(u)


@api.post("/auth/login")
async def login(body: LoginIn, response: Response):
    email = body.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or not user.get("password_hash") or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Credenziali non valide")
    if user.get("active") is False:
        raise HTTPException(status_code=403, detail="Accesso disabilitato")
    token = create_access_token(user["user_id"], email)
    set_auth_cookie(response, "access_token", token, 7 * 24 * 3600)
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"last_login_at": now_iso()}})
    return await user_payload(user)


@api.post("/auth/session")
async def google_session(request: Request, response: Response):
    session_id = request.headers.get("X-Session-ID")
    if not session_id:
        raise HTTPException(status_code=400, detail="Session ID mancante")
    async with httpx.AsyncClient() as http:
        r = await http.get(EMERGENT_SESSION_URL, headers={"X-Session-ID": session_id})
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Sessione Google non valida")
    data = r.json()
    email = data["email"].lower()
    user = await db.users.find_one({"email": email})
    if not user:
        uid = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one({"user_id": uid, "email": email, "name": data.get("name", email),
                                   "role": "admin", "auth_provider": "google", "active": True,
                                   "picture": data.get("picture", ""), "created_at": now_iso()})
    else:
        uid = user["user_id"]
        await db.users.update_one({"user_id": uid}, {"$set": {"picture": data.get("picture", ""), "name": data.get("name", user.get("name"))}})
    session_token = data["session_token"]
    await db.user_sessions.insert_one({"user_id": uid, "session_token": session_token,
                                       "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
                                       "created_at": now_iso()})
    set_auth_cookie(response, "session_token", session_token, 7 * 24 * 3600)
    await db.users.update_one({"user_id": uid}, {"$set": {"last_login_at": now_iso()}})
    u = await db.users.find_one({"user_id": uid}, {"_id": 0})
    return await user_payload(u)


@api.get("/auth/me")
async def me(request: Request, user: dict = Depends(get_current_user)):
    return await user_payload(user, request.headers.get("X-Org-Id"))


@api.post("/auth/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if token:
        await db.user_sessions.delete_one({"session_token": token})
    response.delete_cookie("session_token", path="/")
    response.delete_cookie("access_token", path="/")
    return {"ok": True}


@api.post("/auth/change-password")
async def change_password(body: ChangePwIn, user: dict = Depends(get_current_user)):
    full = await db.users.find_one({"user_id": user["user_id"]})
    if not full.get("password_hash"):
        raise HTTPException(status_code=400, detail="Account collegato a Google: nessuna password locale")
    if not verify_password(body.current_password, full["password_hash"]):
        raise HTTPException(status_code=400, detail="Password attuale errata")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="La nuova password deve avere almeno 8 caratteri")
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"password_hash": hash_password(body.new_password)}})
    return {"ok": True}


@api.post("/auth/forgot-password")
async def forgot_password(body: ForgotIn):
    email = body.email.lower()
    user = await db.users.find_one({"email": email})
    if user and user.get("password_hash"):
        token = secrets.token_urlsafe(32)
        await db.password_reset_tokens.insert_one({"token": token, "user_id": user["user_id"],
                                                   "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                                                   "used": False, "created_at": now_iso()})
        link = f"{APP_URL}/reset-password?token={token}"
        try:
            await email_utils.send_email(to=email, subject="Reimposta la tua password CRMEvent",
                                         html=email_utils.link_email(name=user.get("name", ""),
                                                                     intro="Hai richiesto il reset della password. Il link scade tra 1 ora.",
                                                                     cta_label="Reimposta password", url=link,
                                                                     footer_note="Se non hai richiesto tu il reset ignora questa email."))
        except Exception as e:
            logger.error(f"reset email failed: {e}")
    return {"ok": True}


@api.post("/auth/reset-password")
async def reset_password(body: ResetIn):
    rec = await db.password_reset_tokens.find_one({"token": body.token})
    if not rec or rec.get("used"):
        raise HTTPException(status_code=400, detail="Token non valido o già utilizzato")
    exp = datetime.fromisoformat(rec["expires_at"])
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Token scaduto")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="La password deve avere almeno 8 caratteri")
    await db.users.update_one({"user_id": rec["user_id"]}, {"$set": {"password_hash": hash_password(body.new_password)}})
    await db.password_reset_tokens.update_one({"token": body.token}, {"$set": {"used": True}})
    return {"ok": True}


@api.post("/auth/activate")
async def activate(body: ActivateIn, response: Response):
    user = await db.users.find_one({"activation_token": body.token})
    if not user:
        raise HTTPException(status_code=400, detail="Invito non valido")
    exp = user.get("activation_expires")
    if exp:
        e = datetime.fromisoformat(exp)
        if e.tzinfo is None:
            e = e.replace(tzinfo=timezone.utc)
        if e < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="Invito scaduto")
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="La password deve avere almeno 8 caratteri")
    upd = {"password_hash": hash_password(body.password), "active": True, "activation_token": None}
    if body.name:
        upd["name"] = body.name
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": upd})
    if user.get("person_id"):
        await db.persons.update_one({"id": user["person_id"]}, {"$set": {"invite_status": "account_attivato"}})
    token = create_access_token(user["user_id"], user["email"])
    set_auth_cookie(response, "access_token", token, 7 * 24 * 3600)
    u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    return await user_payload(u)


# ---------------- entity models ----------------
class Event(BaseModel):
    nome: str
    edizione: Optional[str] = None
    logo_url: Optional[str] = None
    tipologia: Optional[str] = None
    data_inizio: Optional[str] = None
    data_fine: Optional[str] = None
    ora_inizio: Optional[str] = None
    ora_fine: Optional[str] = None
    localita: Optional[str] = None
    indirizzo: Optional[str] = None
    citta: Optional[str] = None
    provincia: Optional[str] = None
    regione: Optional[str] = None
    nazione: Optional[str] = "Italia"
    organizzatore: Optional[str] = None
    responsabile: Optional[str] = None
    sito_web: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    partecipanti_previsti: Optional[int] = None
    budget: Optional[float] = None
    stato: Optional[str] = "pianificato"
    descrizione: Optional[str] = None
    note: Optional[str] = None


class Company(BaseModel):
    nome: str
    settore: Optional[str] = None
    partita_iva: Optional[str] = None
    sito_web: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    indirizzo: Optional[str] = None
    cap: Optional[str] = None
    citta: Optional[str] = None
    provincia: Optional[str] = None
    regione: Optional[str] = None
    nazione: Optional[str] = "Italia"
    tipo: Optional[str] = "azienda"
    tipologie: Optional[List[str]] = None
    responsabile_interno: Optional[str] = None
    note: Optional[str] = None


class Person(BaseModel):
    nome: str
    cognome: Optional[str] = None
    email: Optional[str] = None
    email_secondaria: Optional[str] = None
    telefono: Optional[str] = None
    cellulare: Optional[str] = None
    ruolo: Optional[str] = None
    azienda_id: Optional[str] = None
    data_nascita: Optional[str] = None
    indirizzo: Optional[str] = None
    cap: Optional[str] = None
    citta: Optional[str] = None
    provincia: Optional[str] = None
    regione: Optional[str] = None
    nazione: Optional[str] = None
    linkedin: Optional[str] = None
    foto_url: Optional[str] = None
    tag: Optional[List[str]] = None
    esigenze_alimentari: Optional[List[str]] = None
    esigenze_note: Optional[str] = None
    note: Optional[str] = None


class Deal(BaseModel):
    azienda_id: str
    evento_id: str
    tipo: Optional[str] = "sponsor"
    fase: Optional[str] = "prospect"
    valore: Optional[float] = 0
    valore_confermato: Optional[float] = 0
    livello: Optional[str] = None
    referente_id: Optional[str] = None
    stato: Optional[str] = "aperta"
    note: Optional[str] = None


class Presence(BaseModel):  # collection: staff (Persona <-> Evento)
    persona_id: str
    evento_id: str
    categoria: Optional[str] = "staff"
    area: Optional[str] = None
    ruolo: Optional[str] = None
    team_id: Optional[str] = None
    responsabile: Optional[str] = None
    punto_ritrovo: Optional[str] = None
    luogo_operativo: Optional[str] = None
    data_arrivo: Optional[str] = None
    ora_arrivo: Optional[str] = None
    data_partenza: Optional[str] = None
    ora_partenza: Optional[str] = None
    stato: Optional[str] = "da_contattare"
    note_operative: Optional[str] = None
    esigenze_alimentari: Optional[List[str]] = None
    esigenze_note: Optional[str] = None


class Team(BaseModel):
    nome: str
    evento_id: str
    area: Optional[str] = None
    responsabile_id: Optional[str] = None
    descrizione: Optional[str] = None
    luogo_operativo: Optional[str] = None
    punto_ritrovo: Optional[str] = None
    note: Optional[str] = None


class Shift(BaseModel):
    evento_id: str
    persona_id: Optional[str] = None
    data: Optional[str] = None
    ora_inizio: Optional[str] = None
    ora_fine: Optional[str] = None
    area: Optional[str] = None
    ruolo: Optional[str] = None
    team_id: Optional[str] = None
    luogo: Optional[str] = None
    punto_ritrovo: Optional[str] = None
    responsabile: Optional[str] = None
    note: Optional[str] = None


class EventMap(BaseModel):
    evento_id: str
    nome: str
    tipologia: Optional[str] = None
    descrizione: Optional[str] = None
    immagine_url: Optional[str] = None
    pdf_url: Optional[str] = None
    file_url: Optional[str] = None
    gpx_url: Optional[str] = None
    distanza: Optional[float] = None
    url_esterno: Optional[str] = None
    google_maps_url: Optional[str] = None
    team_id: Optional[str] = None
    area: Optional[str] = None
    note: Optional[str] = None


class Activity(BaseModel):
    titolo: str
    tipo: Optional[str] = "generica"
    evento_id: Optional[str] = None
    azienda_id: Optional[str] = None
    persona_id: Optional[str] = None
    data: Optional[str] = None
    stato: Optional[str] = "da_fare"
    note: Optional[str] = None


class Followup(BaseModel):
    titolo: str
    evento_id: Optional[str] = None
    azienda_id: Optional[str] = None
    persona_id: Optional[str] = None
    scadenza: Optional[str] = None
    priorita: Optional[str] = "media"
    stato: Optional[str] = "aperto"
    note: Optional[str] = None


class Lodging(BaseModel):  # collection: lodgings — pernottamento (persona <-> evento)
    evento_id: str
    persona_id: str
    struttura_id: Optional[str] = None
    struttura_nome: Optional[str] = None
    tipo_struttura: Optional[str] = None  # hotel/bnb/appartamento/foresteria/altro
    indirizzo: Optional[str] = None
    check_in: Optional[str] = None
    check_out: Optional[str] = None
    tipo_camera: Optional[str] = None  # singola/doppia/tripla/multipla
    compagni_camera: Optional[str] = None
    codice_prenotazione: Optional[str] = None
    referente: Optional[str] = None
    telefono: Optional[str] = None
    a_carico_di: Optional[str] = None  # organizzazione/persona/sponsor/altro/da_definire
    costo: Optional[float] = None
    stato_pagamento: Optional[str] = None  # pagato/non_pagato
    note: Optional[str] = None
    note_amministrative: Optional[str] = None
    gruppo_id: Optional[str] = None


class Meal(BaseModel):  # collection: meals — colazione/pranzo/cena (persona <-> evento)
    evento_id: str
    persona_id: str
    struttura_id: Optional[str] = None
    data: Optional[str] = None
    tipo_pasto: Optional[str] = None  # colazione/pranzo/cena
    tipologia_servizio: Optional[str] = None
    struttura_nome: Optional[str] = None
    luogo: Optional[str] = None
    indirizzo: Optional[str] = None
    orario: Optional[str] = None
    referente: Optional[str] = None
    telefono: Optional[str] = None
    a_carico_di: Optional[str] = None
    costo: Optional[float] = None
    note: Optional[str] = None
    note_amministrative: Optional[str] = None
    gruppo_id: Optional[str] = None


def _opt(model):
    class M(model):
        pass
    for name, f in M.model_fields.items():
        f.default = None
        f.default_factory = None
    M.model_rebuild(force=True)
    return M


def crud_routes(path, coll, model, org_scoped=True):
    upd_model = _opt(model)

    if not org_scoped:
        @api.get(f"/{path}", name=f"list_{path}")
        async def _l(evento_id: Optional[str] = None, user: dict = Depends(require_support_manager)):
            return await _list(coll, {"evento_id": evento_id} if evento_id else {})

        @api.post(f"/{path}", name=f"create_{path}")
        async def _c(body: model, user: dict = Depends(require_support_manager)):
            return await _create(coll, body.model_dump())

        @api.get(f"/{path}/{{item_id}}", name=f"get_{path}")
        async def _g(item_id: str, user: dict = Depends(require_support_manager)):
            return await _get(coll, item_id)

        @api.put(f"/{path}/{{item_id}}", name=f"update_{path}")
        async def _u(item_id: str, body: upd_model, user: dict = Depends(require_support_manager)):
            return await _update(coll, item_id, body.model_dump(exclude_unset=True))

        @api.delete(f"/{path}/{{item_id}}", name=f"delete_{path}")
        async def _d(item_id: str, user: dict = Depends(require_support_manager)):
            return await _delete(coll, item_id)
        return

    @api.get(f"/{path}", name=f"list_{path}")
    async def _l(evento_id: Optional[str] = None, user: dict = Depends(require_admin)):
        q = oq(user)
        if evento_id:
            q["evento_id"] = evento_id
        return await _list(coll, q)

    @api.post(f"/{path}", name=f"create_{path}")
    async def _c(body: model, user: dict = Depends(require_admin)):
        data = body.model_dump()
        data["org_id"] = user["org_id"]
        return await _create(coll, data)

    @api.get(f"/{path}/{{item_id}}", name=f"get_{path}")
    async def _g(item_id: str, user: dict = Depends(require_admin)):
        doc = await db[coll].find_one(oq(user, id=item_id), {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Elemento non trovato")
        return doc

    @api.put(f"/{path}/{{item_id}}", name=f"update_{path}")
    async def _u(item_id: str, body: upd_model, user: dict = Depends(require_admin)):
        clean = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
        clean["updated_at"] = now_iso()
        res = await db[coll].update_one(oq(user, id=item_id), {"$set": clean})
        if res.matched_count == 0:
            raise HTTPException(status_code=404, detail="Elemento non trovato")
        return await db[coll].find_one(oq(user, id=item_id), {"_id": 0})

    @api.delete(f"/{path}/{{item_id}}", name=f"delete_{path}")
    async def _d(item_id: str, user: dict = Depends(require_admin)):
        await db[coll].delete_one(oq(user, id=item_id))
        return {"ok": True}


crud_routes("events", "events", Event)
crud_routes("companies", "companies", Company)
crud_routes("persons", "persons", Person)
crud_routes("deals", "deals", Deal)
crud_routes("staff", "staff", Presence)
crud_routes("teams", "teams", Team)
crud_routes("shifts", "shifts", Shift)
crud_routes("maps", "event_maps", EventMap)
crud_routes("activities", "activities", Activity)
crud_routes("followups", "followups", Followup)
crud_routes("lodgings", "lodgings", Lodging)
crud_routes("meals", "meals", Meal)


class Structure(BaseModel):  # collection: structures — anagrafica strutture riutilizzabile (org)
    nome: str
    tipologia: Optional[str] = None
    indirizzo: Optional[str] = None
    cap: Optional[str] = None
    citta: Optional[str] = None
    provincia: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    sito_web: Optional[str] = None
    referente: Optional[str] = None
    telefono_referente: Optional[str] = None
    google_maps_url: Optional[str] = None
    note: Optional[str] = None


crud_routes("structures", "structures", Structure)


async def _attach_structures(records: list, org_id: str) -> None:
    """Enrich lodgings/meals with the linked Structure (name, address, maps link)
    read once from the reusable anagraphic — no data duplication on the assignment."""
    ids = list({r.get("struttura_id") for r in records if r.get("struttura_id")})
    if not ids:
        return
    smap = {}
    for s in await db.structures.find({"org_id": org_id, "id": {"$in": ids}}, {"_id": 0}).to_list(2000):
        smap[s["id"]] = s
    for r in records:
        s = smap.get(r.get("struttura_id"))
        if not s:
            continue
        r["struttura"] = {"id": s["id"], "nome": s.get("nome"), "tipologia": s.get("tipologia"),
                          "indirizzo": s.get("indirizzo"), "citta": s.get("citta"), "provincia": s.get("provincia"),
                          "telefono": s.get("telefono"), "referente": s.get("referente"),
                          "google_maps_url": s.get("google_maps_url")}
        if not r.get("struttura_nome"):
            r["struttura_nome"] = s.get("nome")


# ---------------- ospitalità & pasti ----------------
COST_FIELDS = ("costo", "stato_pagamento", "note_amministrative")


class BulkAssignIn(BaseModel):
    evento_id: str
    persona_ids: Optional[List[str]] = None
    categorie: Optional[List[str]] = None
    ruoli: Optional[List[str]] = None
    team_ids: Optional[List[str]] = None
    tutti: Optional[bool] = False
    data: dict = {}


async def _resolve_persons(b: BulkAssignIn, org_id: str) -> list:
    ids = set(b.persona_ids or [])
    if b.tutti or b.categorie or b.ruoli or b.team_ids:
        links = await db.staff.find({"org_id": org_id, "evento_id": b.evento_id}, {"_id": 0}).to_list(5000)
        for l in links:
            if b.tutti:
                ids.add(l["persona_id"])
                continue
            if b.categorie and l.get("categoria") in b.categorie:
                ids.add(l["persona_id"])
            if b.ruoli and l.get("ruolo") in b.ruoli:
                ids.add(l["persona_id"])
            if b.team_ids and l.get("team_id") in b.team_ids:
                ids.add(l["persona_id"])
    return list(ids)


@api.post("/lodgings/bulk")
async def lodgings_bulk(b: BulkAssignIn, admin: dict = Depends(require_admin)):
    persons = await _resolve_persons(b, admin["org_id"])
    if not persons:
        raise HTTPException(status_code=400, detail="Nessuna persona selezionata")
    gid = new_id()
    for pid in persons:
        await _create("lodgings", {**b.data, "org_id": admin["org_id"], "evento_id": b.evento_id, "persona_id": pid, "gruppo_id": gid})
    return {"ok": True, "gruppo_id": gid, "count": len(persons)}


@api.post("/meals/bulk")
async def meals_bulk(b: BulkAssignIn, admin: dict = Depends(require_admin)):
    persons = await _resolve_persons(b, admin["org_id"])
    if not persons:
        raise HTTPException(status_code=400, detail="Nessuna persona selezionata")
    gid = new_id()
    for pid in persons:
        await _create("meals", {**b.data, "org_id": admin["org_id"], "evento_id": b.evento_id, "persona_id": pid, "gruppo_id": gid})
    return {"ok": True, "gruppo_id": gid, "count": len(persons)}


@api.delete("/hospitality/group/{gruppo_id}")
async def delete_hospitality_group(gruppo_id: str, tipo: str, admin: dict = Depends(require_admin)):
    coll = "lodgings" if tipo == "lodging" else "meals"
    res = await db[coll].delete_many({"org_id": admin["org_id"], "gruppo_id": gruppo_id})
    return {"ok": True, "deleted": res.deleted_count}


@api.get("/events/{event_id}/hospitality")
async def event_hospitality(event_id: str, admin: dict = Depends(require_admin)):
    event = await db.events.find_one(oq(admin, id=event_id), {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Evento non trovato")
    can_costs = admin.get("role") == "admin"
    links = await db.staff.find(oq(admin, evento_id=event_id), {"_id": 0}).to_list(5000)
    lodgings = await db.lodgings.find(oq(admin, evento_id=event_id), {"_id": 0}).to_list(5000)
    meals = await db.meals.find(oq(admin, evento_id=event_id), {"_id": 0}).to_list(20000)
    if not can_costs:
        for x in lodgings + meals:
            for f in COST_FIELDS:
                x.pop(f, None)
    await _attach_structures(lodgings + meals, admin["org_id"])
    teams = {t["id"]: t for t in await db.teams.find(oq(admin, evento_id=event_id), {"_id": 0}).to_list(1000)}
    lod_by, meal_by = {}, {}
    for l in lodgings:
        lod_by.setdefault(l["persona_id"], []).append(l)
    for m in meals:
        meal_by.setdefault(m["persona_id"], []).append(m)
    persons = []
    for l in links:
        p = await db.persons.find_one({"id": l["persona_id"]}, {"_id": 0})
        if not p:
            continue
        override = l.get("esigenze_alimentari") is not None
        eff_esig = l.get("esigenze_alimentari") if override else p.get("esigenze_alimentari")
        eff_note = l.get("esigenze_note") or p.get("esigenze_note")
        plod = lod_by.get(l["persona_id"], [])
        pmeal = meal_by.get(l["persona_id"], [])
        if not plod and not pmeal:
            stato = "da_definire"
        elif plod and pmeal:
            stato = "completo"
        else:
            stato = "parziale"
        persons.append({
            "persona_id": p["id"], "nome": p.get("nome"), "cognome": p.get("cognome"),
            "ruolo": l.get("ruolo") or p.get("ruolo"), "categoria": l.get("categoria"),
            "team_id": l.get("team_id"), "team_nome": teams.get(l.get("team_id"), {}).get("nome"),
            "presence_id": l.get("id"),
            "esigenze_alimentari": eff_esig or [], "esigenze_note": eff_note, "esigenze_override": override,
            "lodgings": plod, "meals": pmeal, "stato": stato,
        })
    persons.sort(key=lambda x: ((x.get("cognome") or "").lower(), (x.get("nome") or "").lower()))

    def _c(t):
        return len([m for m in meals if m.get("tipo_pasto") == t])

    servizi_da_def = len([x for x in lodgings + meals if x.get("a_carico_di") in (None, "", "da_definire")])
    summary = {
        "persone_gestite": len([1 for x in persons if x["lodgings"] or x["meals"]]),
        "persone_totali": len(persons),
        "pernottamenti": len(lodgings), "camere": len(lodgings),
        "colazioni": _c("colazione"), "pranzi": _c("pranzo"), "cene": _c("cena"),
        "servizi_da_definire": servizi_da_def,
        "senza_sistemazione": len([x for x in persons if not x["lodgings"]]),
    }
    return {"event": event, "persons": persons, "lodgings": lodgings, "meals": meals,
            "summary": summary, "can_view_costs": can_costs}


# ---------------- persons <-> companies relations & unified views ----------------
class PersonCompany(BaseModel):
    person_id: str
    company_id: str
    qualifica: Optional[str] = None
    ruolo: Optional[str] = None
    referente_principale: Optional[bool] = False
    note: Optional[str] = None


class ContactIn(BaseModel):
    person_id: Optional[str] = None
    nome: Optional[str] = None
    cognome: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    cellulare: Optional[str] = None
    ruolo: Optional[str] = None
    linkedin: Optional[str] = None
    referente_principale: Optional[bool] = False
    note: Optional[str] = None


class ContactUpdate(BaseModel):
    qualifica: Optional[str] = None
    ruolo: Optional[str] = None
    referente_principale: Optional[bool] = None
    note: Optional[str] = None


async def _company_contacts(company_id: str, org_id: str):
    rels = await db.person_companies.find({"org_id": org_id, "company_id": company_id}, {"_id": 0}).to_list(500)
    have = {r["person_id"] for r in rels}
    out = []
    for r in rels:
        p = await db.persons.find_one({"id": r["person_id"], "org_id": org_id}, {"_id": 0})
        if p:
            out.append({"relation": r, "person": p})
    legacy = await db.persons.find({"azienda_id": company_id, "org_id": org_id}, {"_id": 0}).to_list(500)
    for p in legacy:
        if p["id"] not in have:
            out.append({"relation": {"id": None, "company_id": company_id, "person_id": p["id"],
                                     "qualifica": p.get("ruolo"), "referente_principale": True, "legacy": True},
                        "person": p})
    return out


@api.get("/persons-enriched")
async def persons_enriched(admin: dict = Depends(require_admin)):
    persons = await _list("persons", oq(admin))
    rels = await db.person_companies.find(oq(admin), {"_id": 0}).to_list(10000)
    pres = await db.staff.find(oq(admin), {"_id": 0}).to_list(10000)
    companies = {c["id"]: c for c in await _list("companies", oq(admin))}
    rel_by = defaultdict(list)
    for r in rels:
        rel_by[r["person_id"]].append(r)
    pres_by = defaultdict(list)
    for p in pres:
        pres_by[p["persona_id"]].append(p)
    out = []
    for p in persons:
        pid = p["id"]
        prs = pres_by.get(pid, [])
        cats = {x.get("categoria") for x in prs}
        rp = rel_by.get(pid, [])
        aziende = [companies[r["company_id"]]["nome"] for r in rp if companies.get(r["company_id"])]
        if p.get("azienda_id") and companies.get(p["azienda_id"]):
            n = companies[p["azienda_id"]]["nome"]
            if n not in aziende:
                aziende.append(n)
        out.append({**p,
                    "is_referente": bool(rp) or bool(p.get("azienda_id")),
                    "is_staff": bool(cats & {"staff", "collaboratore"}),
                    "is_volontario": "volontario" in cats,
                    "is_team": "team" in cats,
                    "aziende_nomi": aziende,
                    "eventi_count": len({x["evento_id"] for x in prs})})
    return out


@api.post("/persons-match")
async def persons_match(body: dict, admin: dict = Depends(require_admin)):
    email = (body.get("email") or "").strip()
    tel = (body.get("telefono") or body.get("cellulare") or "").strip()
    nome = (body.get("nome") or "").strip()
    cognome = (body.get("cognome") or "").strip()
    conds = []
    if email:
        conds.append({"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}})
    if tel:
        conds.append({"$or": [{"telefono": tel}, {"cellulare": tel}]})
    if nome and cognome:
        conds.append({"nome": {"$regex": f"^{re.escape(nome)}$", "$options": "i"},
                      "cognome": {"$regex": f"^{re.escape(cognome)}$", "$options": "i"}})
    if not conds:
        return {"matches": []}
    docs = await db.persons.find({"org_id": admin["org_id"], "$or": conds}, {"_id": 0}).limit(10).to_list(10)
    return {"matches": docs}


@api.get("/persons/{person_id}/detail")
async def person_detail(person_id: str, admin: dict = Depends(require_admin)):
    p = await db.persons.find_one(oq(admin, id=person_id), {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Persona non trovata")
    rels = await db.person_companies.find(oq(admin, person_id=person_id), {"_id": 0}).to_list(200)
    companies = []
    seen = set()
    for r in rels:
        c = await db.companies.find_one({"id": r["company_id"], "org_id": admin["org_id"]}, {"_id": 0})
        if c:
            companies.append({"relation": r, "company": c})
            seen.add(r["company_id"])
    if p.get("azienda_id") and p["azienda_id"] not in seen:
        c = await db.companies.find_one({"id": p["azienda_id"], "org_id": admin["org_id"]}, {"_id": 0})
        if c:
            companies.append({"relation": {"id": None, "company_id": c["id"], "person_id": person_id,
                                           "qualifica": p.get("ruolo"), "referente_principale": True, "legacy": True},
                              "company": c})
    presences = await db.staff.find(oq(admin, persona_id=person_id), {"_id": 0}).to_list(300)
    events = []
    for pr in presences:
        e = await db.events.find_one({"id": pr["evento_id"], "org_id": admin["org_id"]}, {"_id": 0})
        events.append({"presence": pr, "event": e})
    tids = {pr.get("team_id") for pr in presences if pr.get("team_id")}
    for t in await db.teams.find(oq(admin, responsabile_id=person_id), {"_id": 0}).to_list(100):
        tids.add(t["id"])
    teams = [t for t in [await db.teams.find_one({"id": tid, "org_id": admin["org_id"]}, {"_id": 0}) for tid in tids] if t]
    shifts = await db.shifts.find(oq(admin, persona_id=person_id), {"_id": 0}).to_list(300)
    activities = await db.activities.find(oq(admin, persona_id=person_id), {"_id": 0}).to_list(300)
    followups = await db.followups.find(oq(admin, persona_id=person_id), {"_id": 0}).to_list(300)
    return {"person": p, "companies": companies, "events": events, "teams": teams,
            "shifts": shifts, "activities": activities, "followups": followups}


@api.get("/companies/{company_id}/detail")
async def company_detail(company_id: str, admin: dict = Depends(require_admin)):
    c = await db.companies.find_one(oq(admin, id=company_id), {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Azienda non trovata")
    contacts = await _company_contacts(company_id, admin["org_id"])
    deals = await db.deals.find(oq(admin, azienda_id=company_id), {"_id": 0}).to_list(300)
    events = []
    seen = set()
    for d in deals:
        if d["evento_id"] in seen:
            continue
        seen.add(d["evento_id"])
        e = await db.events.find_one({"id": d["evento_id"], "org_id": admin["org_id"]}, {"_id": 0})
        if e:
            events.append({"event": e, "tipo": d.get("tipo"), "fase": d.get("fase")})
    activities = await db.activities.find(oq(admin, azienda_id=company_id), {"_id": 0}).to_list(300)
    followups = await db.followups.find(oq(admin, azienda_id=company_id), {"_id": 0}).to_list(300)
    return {"company": c, "contacts": contacts, "deals": deals, "events": events,
            "activities": activities, "followups": followups}


@api.get("/companies/{company_id}/contacts")
async def get_company_contacts(company_id: str, admin: dict = Depends(require_admin)):
    return await _company_contacts(company_id, admin["org_id"])


@api.post("/companies/{company_id}/contacts")
async def add_company_contact(company_id: str, body: ContactIn, admin: dict = Depends(require_admin)):
    company = await db.companies.find_one(oq(admin, id=company_id), {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Azienda non trovata")
    if body.person_id:
        person = await db.persons.find_one({"id": body.person_id, "org_id": admin["org_id"]}, {"_id": 0})
        if not person:
            raise HTTPException(status_code=404, detail="Persona non trovata")
        pid = body.person_id
    else:
        if not body.nome:
            raise HTTPException(status_code=400, detail="Nome referente obbligatorio")
        person = await _create("persons", {"org_id": admin["org_id"], "nome": body.nome, "cognome": body.cognome, "email": body.email,
                                           "telefono": body.telefono, "cellulare": body.cellulare, "ruolo": body.ruolo,
                                           "linkedin": body.linkedin, "azienda_id": company_id, "note": body.note,
                                           "invite_status": "non_invitato"})
        pid = person["id"]
    existing = await db.person_companies.find_one({"org_id": admin["org_id"], "person_id": pid, "company_id": company_id})
    rel_data = {"org_id": admin["org_id"], "person_id": pid, "company_id": company_id, "qualifica": body.ruolo, "ruolo": body.ruolo,
                "referente_principale": bool(body.referente_principale), "note": body.note}
    if existing:
        rel = await _update("person_companies", existing["id"], rel_data)
    else:
        rel = await _create("person_companies", rel_data)
    if body.referente_principale:
        await db.person_companies.update_many({"org_id": admin["org_id"], "company_id": company_id, "id": {"$ne": rel["id"]}},
                                              {"$set": {"referente_principale": False}})
    return {"relation": rel, "person": person}


@api.put("/company-contacts/{rel_id}")
async def update_company_contact(rel_id: str, body: ContactUpdate, admin: dict = Depends(require_admin)):
    existing = await db.person_companies.find_one(oq(admin, id=rel_id), {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Relazione non trovata")
    rel = await _update("person_companies", rel_id, body.model_dump(exclude_unset=True))
    if body.referente_principale:
        await db.person_companies.update_many({"org_id": admin["org_id"], "company_id": rel["company_id"], "id": {"$ne": rel_id}},
                                              {"$set": {"referente_principale": False}})
    return rel


@api.delete("/company-contacts/{rel_id}")
async def delete_company_contact(rel_id: str, admin: dict = Depends(require_admin)):
    await db.person_companies.delete_one(oq(admin, id=rel_id))
    return {"ok": True}


# ---------------- person invite ----------------
class InviteIn(BaseModel):
    role: str = "volunteer"


class AccessIn(BaseModel):
    enabled: bool


@api.post("/persons/{person_id}/invite")
async def invite_person(person_id: str, body: InviteIn, admin: dict = Depends(require_admin)):
    person = await db.persons.find_one(oq(admin, id=person_id), {"_id": 0})
    if not person:
        raise HTTPException(status_code=404, detail="Persona non trovata")
    if not person.get("email"):
        raise HTTPException(status_code=400, detail="La persona non ha un'email")
    role = body.role if body.role in ("staff", "volunteer") else "volunteer"
    email = person["email"].lower()
    token = secrets.token_urlsafe(32)
    existing = await db.users.find_one({"email": email})
    if existing:
        await db.users.update_one({"email": email}, {"$set": {"person_id": person_id, "role": role, "org_id": admin["org_id"],
                                                              "activation_token": token, "active": True,
                                                              "activation_expires": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()}})
    else:
        uid = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one({"user_id": uid, "email": email, "name": f"{person['nome']} {person.get('cognome','')}".strip(),
                                   "role": role, "auth_provider": "password", "person_id": person_id, "org_id": admin["org_id"], "active": True,
                                   "picture": person.get("foto_url", ""), "activation_token": token,
                                   "activation_expires": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
                                   "created_at": now_iso()})
    link = f"{APP_URL}/attiva?token={token}"
    sent = True
    try:
        await email_utils.send_email(to=email, subject="Il tuo accesso a CRMEvent",
                                     html=email_utils.link_email(name=person["nome"],
                                                                 intro="Sei stato invitato ad accedere alla tua area personale su CRMEvent. Attiva l'account e imposta la tua password.",
                                                                 cta_label="Attiva il mio account", url=link,
                                                                 footer_note="L'invito scade tra 7 giorni."))
    except Exception as e:
        logger.error(f"invite email failed: {e}")
        sent = False
    await db.persons.update_one(oq(admin, id=person_id), {"$set": {"invite_status": "invito_inviato", "user_role": role}})
    return {"ok": True, "email_sent": sent}


@api.put("/persons/{person_id}/access")
async def set_access(person_id: str, body: AccessIn, admin: dict = Depends(require_admin)):
    person = await db.persons.find_one(oq(admin, id=person_id), {"_id": 0})
    if not person:
        raise HTTPException(status_code=404, detail="Persona non trovata")
    u = await db.users.find_one({"person_id": person_id, "org_id": admin["org_id"]})
    if not u:
        raise HTTPException(status_code=404, detail="Nessun account collegato")
    await db.users.update_one({"person_id": person_id, "org_id": admin["org_id"]}, {"$set": {"active": body.enabled}})
    await db.persons.update_one(oq(admin, id=person_id), {"$set": {"invite_status": "account_attivato" if body.enabled else "accesso_disabilitato"}})
    return {"ok": True}


# ---------------- file upload ----------------
MIME = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif",
        "webp": "image/webp", "pdf": "application/pdf", "csv": "text/csv", "txt": "text/plain"}


@api.post("/upload")
async def upload(file: UploadFile = File(...), admin: dict = Depends(require_admin)):
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "bin"
    fid = new_id()
    path = f"{storage_utils.APP_NAME}/uploads/{admin['user_id']}/{fid}.{ext}"
    data = await file.read()
    ctype = file.content_type or MIME.get(ext, "application/octet-stream")
    result = storage_utils.put_object(path, data, ctype)
    await db.files.insert_one({"id": fid, "org_id": admin["org_id"], "storage_path": result["path"], "original_filename": file.filename,
                               "content_type": ctype, "size": result.get("size"), "is_deleted": False, "created_at": now_iso()})
    return {"id": fid, "url": f"/api/files/{fid}", "filename": file.filename}


@api.get("/files/{file_id}")
async def download(file_id: str, user: dict = Depends(get_current_user)):
    rec = await db.files.find_one({"id": file_id, "is_deleted": False}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="File non trovato")
    if user.get("role") != "superadmin" and rec.get("org_id") not in (None, user.get("org_id")):
        raise HTTPException(status_code=404, detail="File non trovato")
    data, ctype = storage_utils.get_object(rec["storage_path"])
    return Response(content=data, media_type=rec.get("content_type", ctype))


# ---------------- dashboard / search / notifications ----------------
@api.get("/dashboard")
async def dashboard(evento_id: Optional[str] = None, admin: dict = Depends(require_admin)):
    ev_q = oq(admin) if not evento_id else oq(admin, id=evento_id)
    rel_q = oq(admin) if not evento_id else oq(admin, evento_id=evento_id)
    events = await db.events.find(ev_q, {"_id": 0}).to_list(5000)
    companies = await db.companies.find(oq(admin), {"_id": 0}).to_list(5000)
    persons = await db.persons.find(oq(admin), {"_id": 0}).to_list(5000)
    deals = await db.deals.find(rel_q, {"_id": 0}).to_list(5000)
    staff = await db.staff.find(rel_q, {"_id": 0}).to_list(5000)
    teams = await db.teams.find(rel_q, {"_id": 0}).to_list(5000)
    shifts = await db.shifts.find(rel_q, {"_id": 0}).to_list(5000)
    activities = await db.activities.find(rel_q, {"_id": 0}).to_list(5000)
    followups = await db.followups.find(rel_q, {"_id": 0}).to_list(5000)
    today = datetime.now(timezone.utc).date().isoformat()

    def fut(e):
        return (e.get("data_inizio") or "") > today

    prospect = len([c for c in companies if c.get("tipo") == "prospect"]) + len([d for d in deals if d.get("tipo") == "prospect"])
    thirty = (datetime.now(timezone.utc).date() - timedelta(days=30)).isoformat()
    nuovi = len([p for p in persons if (p.get("created_at") or "")[:10] >= thirty])

    valore_pipeline = sum(float(d.get("valore") or 0) for d in deals if d.get("fase") != "perso")
    valore_conf = sum(float(d.get("valore_confermato") or d.get("valore") or 0) for d in deals if d.get("fase") == "confermato")

    conf_stati = {"confermato"}
    dacon = {"da_contattare", "disponibilita_richiesta", "disponibile", "da_riconfermare"}
    rinuncia = {"rinunciato", "non_disponibile"}

    return {
        "eventi": {"attivi": len([e for e in events if e.get("stato") == "attivo"]),
                   "prossimi": len([e for e in events if fut(e) and e.get("stato") != "concluso"]),
                   "conclusi": len([e for e in events if e.get("stato") == "concluso"]), "totali": len(events)},
        "crm": {"aziende": len(companies), "persone": len(persons), "nuovi_contatti": nuovi, "prospect": prospect},
        "commerciale": {"trattative_aperte": len([d for d in deals if d.get("stato") == "aperta" and d.get("fase") not in ("confermato", "perso")]),
                        "proposte_inviate": len([d for d in deals if d.get("fase") == "proposta_inviata"]),
                        "sponsor_confermati": len([d for d in deals if d.get("fase") == "confermato"]),
                        "valore_pipeline": valore_pipeline, "valore_confermato": valore_conf},
        "attivita": {"followup_oggi": len([f for f in followups if (f.get("scadenza") or "")[:10] == today and f.get("stato") != "completato"]),
                     "followup_scaduti": len([f for f in followups if (f.get("scadenza") or "9999")[:10] < today and f.get("stato") != "completato"]),
                     "prossime": len([a for a in activities if a.get("stato") == "da_fare"]),
                     "completate": len([a for a in activities if a.get("stato") == "completata"]) + len([f for f in followups if f.get("stato") == "completato"])},
        "staff": {"staff_totale": len([s for s in staff if s.get("categoria") in ("staff", "collaboratore")]),
                  "volontari_totali": len([s for s in staff if s.get("categoria") == "volontario"]),
                  "confermati": len([s for s in staff if s.get("stato") in conf_stati]),
                  "da_confermare": len([s for s in staff if s.get("stato") in dacon]),
                  "rinunce": len([s for s in staff if s.get("stato") in rinuncia]),
                  "team_creati": len(teams),
                  "team_senza_responsabile": len([t for t in teams if not t.get("responsabile_id")]),
                  "turni_totali": len(shifts),
                  "turni_scoperti": len([s for s in shifts if not s.get("persona_id")]),
                  "persone_senza_ruolo": len([s for s in staff if not s.get("ruolo")]),
                  "persone_senza_team": len([s for s in staff if not s.get("team_id")])},
        "pipeline_chart": [{"fase": f, "count": len([d for d in deals if d.get("fase") == f]),
                            "valore": sum(float(d.get("valore") or 0) for d in deals if d.get("fase") == f)}
                           for f in ["prospect", "contattato", "proposta_inviata", "in_trattativa", "confermato", "perso"]],
        "tipo_chart": [{"tipo": k, "count": len([d for d in deals if d.get("tipo") == k])}
                       for k in sorted(set(d.get("tipo", "sponsor") for d in deals))] if deals else [],
    }


@api.get("/notifications")
async def notifications(admin: dict = Depends(require_admin)):
    today = datetime.now(timezone.utc).date().isoformat()
    fus = await db.followups.find(oq(admin, stato={"$ne": "completato"}), {"_id": 0}).to_list(3000)
    items = []
    for f in fus:
        sc = (f.get("scadenza") or "")[:10]
        if sc and sc < today:
            items.append({"id": f["id"], "tipo": "scaduto", "titolo": f["titolo"], "scadenza": sc})
        elif sc == today:
            items.append({"id": f["id"], "tipo": "oggi", "titolo": f["titolo"], "scadenza": sc})
    items.sort(key=lambda x: x["scadenza"])
    return {"count": len(items), "items": items[:30]}


@api.get("/search")
async def search(q: str, admin: dict = Depends(require_admin)):
    if not q or len(q) < 2:
        return {"results": []}
    rx = {"$regex": q, "$options": "i"}
    oid = admin["org_id"]
    results = []
    for e in await db.events.find({"org_id": oid, "nome": rx}, {"_id": 0}).limit(6).to_list(6):
        results.append({"tipo": "evento", "id": e["id"], "label": e["nome"], "sub": e.get("citta", "")})
    for c in await db.companies.find({"org_id": oid, "nome": rx}, {"_id": 0}).limit(6).to_list(6):
        results.append({"tipo": "azienda", "id": c["id"], "label": c["nome"], "sub": c.get("settore", "")})
    for p in await db.persons.find({"org_id": oid, "$or": [{"nome": rx}, {"cognome": rx}, {"email": rx}]}, {"_id": 0}).limit(6).to_list(6):
        results.append({"tipo": "persona", "id": p["id"], "label": f"{p['nome']} {p.get('cognome','')}".strip(), "sub": p.get("ruolo", "")})
    return {"results": results}


# ---------------- settings ----------------
def default_settings(org_id="global"):
    return {"id": org_id,
            "tipologie_evento": ["Fiera", "Congresso", "Concerto", "Festival", "Conferenza", "Workshop", "Gala"],
            "settori": ["Tecnologia", "Food & Beverage", "Moda", "Automotive", "Finanza", "Media", "No Profit"],
            "ruoli_staff": ["Coordinatore", "Hostess", "Tecnico", "Sicurezza", "Accoglienza", "Logistica"],
            "aree_operative": ["Expo", "Palco", "Ingresso", "Ristoro", "Logistica", "Parcheggi", "Percorso"],
            "livelli_sponsorship": ["Main Sponsor", "Gold", "Silver", "Bronze", "Technical Partner"],
            "fasi_pipeline": ["prospect", "contattato", "proposta_inviata", "in_trattativa", "confermato", "perso"],
            "demo_disabled": False}


@api.get("/settings")
async def get_settings(admin: dict = Depends(require_admin)):
    sid = admin["org_id"]
    doc = await db.settings.find_one({"id": sid}, {"_id": 0})
    if not doc:
        doc = default_settings(sid)
        await db.settings.insert_one(dict(doc))
    return doc


@api.put("/settings")
async def update_settings(body: dict, admin: dict = Depends(require_admin)):
    body.pop("_id", None)
    body["id"] = admin["org_id"]
    await db.settings.update_one({"id": admin["org_id"]}, {"$set": body}, upsert=True)
    return await db.settings.find_one({"id": admin["org_id"]}, {"_id": 0})


USAGE_MAP = {"tipologie_evento": ("events", "tipologia"), "settori": ("companies", "settore"),
             "ruoli_staff": ("staff", "ruolo"), "aree_operative": ("staff", "area"),
             "livelli_sponsorship": ("deals", "livello")}


@api.get("/settings/usage")
async def settings_usage(list: str, value: str, admin: dict = Depends(require_admin)):
    m = USAGE_MAP.get(list)
    if not m:
        return {"count": 0}
    coll, field = m
    count = await db[coll].count_documents({"org_id": admin["org_id"], field: value})
    return {"count": count}


# ---------------- Support Assistant (AI) ----------------
DEFAULT_ORG = "default"


class KBEntry(BaseModel):
    titolo: str
    categoria: Optional[str] = None
    domanda: Optional[str] = None
    risposta: str
    parole_chiave: Optional[str] = None
    stato: Optional[str] = "bozza"
    ruoli: Optional[str] = None  # ruoli a cui si applica (es. "admin", "staff,volontario", "tutti")
    org_id: Optional[str] = DEFAULT_ORG
    embedding: Optional[List[float]] = None  # predisposizione ricerca semantica futura


class FAQEntry(BaseModel):
    domanda: str
    risposta: str
    categoria: Optional[str] = None
    parole_chiave: Optional[str] = None
    stato: Optional[str] = "bozza"
    richieste_count: Optional[int] = 0
    suggested: Optional[bool] = False
    org_id: Optional[str] = DEFAULT_ORG


class SupportCategory(BaseModel):
    nome: str
    slug: Optional[str] = None
    org_id: Optional[str] = DEFAULT_ORG


class FeatureRequest(BaseModel):
    titolo: str
    descrizione: Optional[str] = None
    stato: Optional[str] = "nuova"
    utenti_count: Optional[int] = 1
    organizzazioni: Optional[List[str]] = None
    org_id: Optional[str] = DEFAULT_ORG


class SupportTicket(BaseModel):
    conversation_id: Optional[str] = None
    utente: Optional[str] = None
    domanda: Optional[str] = None
    stato: Optional[str] = "aperto"
    org_id: Optional[str] = DEFAULT_ORG


crud_routes("support-kb", "support_knowledge_base", KBEntry, org_scoped=False)
crud_routes("support-faq", "support_faq", FAQEntry, org_scoped=False)
crud_routes("support-categories", "support_categories", SupportCategory, org_scoped=False)
crud_routes("support-feature-requests", "support_feature_requests", FeatureRequest, org_scoped=False)
crud_routes("support-tickets", "support_tickets", SupportTicket, org_scoped=False)


def _sup_tokens(s: str):
    return set(re.findall(r"[a-zàèéìòù0-9]{3,}", (s or "").lower()))


def _as_list(v):
    if not v:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return [x.strip() for x in str(v).split(",") if x.strip()]


def _support_role(user: dict) -> str:
    return {"admin": "admin", "member": "admin", "staff": "staff", "volunteer": "volontario"}.get(user.get("role"), "admin")


def _kb_visible(entry: dict, role: str) -> bool:
    roles = _as_list(entry.get("ruoli"))
    if not roles:
        return role == "admin"  # procedure amministrative visibili solo all'organizzatore
    if "tutti" in roles:
        return True
    return role in roles


async def build_kb_context(question: str, role: str = "admin"):
    q = _sup_tokens(question)
    kb = await db.support_knowledge_base.find({"stato": "pubblicato"}, {"_id": 0}).to_list(2000)
    faq = await db.support_faq.find({"stato": "pubblicato"}, {"_id": 0}).to_list(2000)
    kb = [e for e in kb if _kb_visible(e, role)]
    scored = []
    for e in kb + faq:
        kws = _as_list(e.get("parole_chiave"))
        text = " ".join([e.get("titolo", ""), e.get("domanda", ""), e.get("risposta", ""), " ".join(kws)])
        score = len(q & _sup_tokens(text))
        for kwd in kws:
            if kwd and kwd.lower() in (question or "").lower():
                score += 2
        if score > 0:
            scored.append((score, e))
    scored.sort(key=lambda x: -x[0])
    top = [e for _, e in scored[:4]]
    ctx = "\n\n".join([f"[{e.get('categoria', 'generale')}] {e.get('titolo') or e.get('domanda')}\nD: {e.get('domanda', '')}\nR: {e.get('risposta')}" for e in top])
    return ctx, [e["id"] for e in top], (scored[0][0] if scored else 0)


async def _record_feature_request(title: str, question: str, conv_id: str, user: dict, org: str):
    existing = await db.support_feature_requests.find({"org_id": org}, {"_id": 0}).to_list(1000)
    qt = _sup_tokens(title)
    best, bs = None, 0
    for fr in existing:
        s = len(qt & _sup_tokens(f"{fr.get('titolo', '')} {fr.get('descrizione', '')}"))
        if s > bs:
            bs, best = s, fr
    if best and bs >= 2:
        orgs = set(best.get("organizzazioni") or [])
        orgs.add(org)
        await db.support_feature_requests.update_one({"id": best["id"]}, {"$set": {"ultima_richiesta": now_iso(), "organizzazioni": list(orgs)}, "$inc": {"utenti_count": 1}})
        fr_id = best["id"]
    else:
        fr = await _create("support_feature_requests", {"org_id": org, "titolo": title[:140], "descrizione": question,
                                                         "stato": "nuova", "utenti_count": 1, "organizzazioni": [org],
                                                         "prima_richiesta": now_iso(), "ultima_richiesta": now_iso()})
        fr_id = fr["id"]
    await _create("support_feature_request_matches", {"org_id": org, "feature_request_id": fr_id,
                                                       "conversation_id": conv_id, "user_id": user["user_id"], "question": question})


async def _resolve_org_for_support(request: Request, user: dict):
    """Resolve the active org for the assistant AND whether this user may see operational
    data for it. STRICT isolation: never returns an org the user is not authorized for.
    Returns (org_id | None, is_manager: bool)."""
    role = user.get("role")
    if role == "superadmin":
        acting = request.headers.get("X-Org-Id")
        if not acting:
            return None, False
        org = await db.organizations.find_one({"id": acting}, {"_id": 0})
        return (acting, True) if org else (None, False)
    mems = await db.memberships.find({"user_id": user["user_id"], "active": True}, {"_id": 0}).to_list(200)
    header = request.headers.get("X-Org-Id")
    chosen = None
    if mems:
        if header:
            chosen = next((m for m in mems if m["org_id"] == header), None)
            if not chosen:
                return None, False  # asked for an org they are not a member of
        if not chosen:
            chosen = next((m for m in mems if m["org_id"] == user.get("org_id")), None) or mems[0]
        org = await db.organizations.find_one({"id": chosen["org_id"], "status": {"$ne": "disabled"}}, {"_id": 0})
        if not org:
            return None, False
        is_mgr = chosen.get("role") == "admin_org" or role == "admin"
        return chosen["org_id"], is_mgr
    # No memberships: fall back to the user's own org (org admin/owner only).
    oid = user.get("org_id")
    if oid and role == "admin":
        return oid, True
    return None, False


def _fmt_person(p: dict) -> str:
    return f"{(p.get('nome') or '').strip()} {(p.get('cognome') or '').strip()}".strip()


async def build_org_data_context(org_id: str, question: str = "") -> str:
    """Build a compact, human-readable snapshot of the org's operational data for the AI
    assistant. EVERY query is filtered by org_id — no cross-tenant data can appear here."""
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        return ""
    today = datetime.now(timezone.utc).date().isoformat()
    events = await db.events.find({"org_id": org_id}, {"_id": 0}).to_list(2000)
    persons = {p["id"]: p for p in await db.persons.find({"org_id": org_id}, {"_id": 0}).to_list(20000)}
    companies = {c["id"]: c for c in await db.companies.find({"org_id": org_id}, {"_id": 0}).to_list(20000)}
    structures = {s["id"]: s for s in await db.structures.find({"org_id": org_id}, {"_id": 0}).to_list(5000)}

    lines = [f"ORGANIZZAZIONE: {org.get('nome')} (tipo: {org.get('type', 'cliente')}).",
             f"Data odierna: {today}.",
             f"EVENTI TOTALI: {len(events)}.", f"PERSONE IN ANAGRAFICA: {len(persons)}.",
             f"AZIENDE IN ANAGRAFICA: {len(companies)}.", ""]

    for ev in sorted(events, key=lambda e: (e.get("data_inizio") or "")):
        eid = ev["id"]
        staff = await db.staff.find({"org_id": org_id, "evento_id": eid}, {"_id": 0}).to_list(20000)
        teams = await db.teams.find({"org_id": org_id, "evento_id": eid}, {"_id": 0}).to_list(5000)
        shifts = await db.shifts.find({"org_id": org_id, "evento_id": eid}, {"_id": 0}).to_list(20000)
        deals = await db.deals.find({"org_id": org_id, "evento_id": eid}, {"_id": 0}).to_list(5000)
        acts = await db.activities.find({"org_id": org_id, "evento_id": eid}, {"_id": 0}).to_list(20000)
        fups = await db.followups.find({"org_id": org_id, "evento_id": eid}, {"_id": 0}).to_list(20000)
        lodgings = await db.lodgings.find({"org_id": org_id, "evento_id": eid}, {"_id": 0}).to_list(20000)
        meals = await db.meals.find({"org_id": org_id, "evento_id": eid}, {"_id": 0}).to_list(50000)
        maps = await db.event_maps.find({"org_id": org_id, "evento_id": eid}, {"_id": 0}).to_list(5000)

        team_map = {t["id"]: t for t in teams}
        n_staff = len([s for s in staff if s.get("categoria") in ("staff", "collaboratore")])
        n_vol = len([s for s in staff if s.get("categoria") == "volontario"])

        lines.append("=" * 60)
        lines.append(f"EVENTO: {ev.get('nome')} — stato: {ev.get('stato')} — data: {ev.get('data_inizio') or 'n/d'}"
                     + (f"→{ev.get('data_fine')}" if ev.get('data_fine') else "")
                     + f" — luogo: {ev.get('localita') or ev.get('citta') or 'n/d'}"
                     + (f" — partecipanti previsti: {ev.get('partecipanti_previsti')}" if ev.get('partecipanti_previsti') else ""))
        if ev.get("responsabile"):
            lines.append(f"  Responsabile evento: {ev.get('responsabile')} | contatti: {ev.get('email') or ''} {ev.get('telefono') or ''}".rstrip())
        lines.append(f"  PERSONE COLLEGATE: {len(staff)} (staff: {n_staff}, volontari: {n_vol}).")

        if teams:
            lines.append(f"  TEAM ({len(teams)}):")
            for t in teams:
                resp = persons.get(t.get("responsabile_id"))
                membri = [s for s in staff if s.get("team_id") == t["id"]]
                lines.append(f"    - {t.get('nome')} (area: {t.get('area') or 'n/d'}) — Team Leader: "
                             f"{_fmt_person(resp) if resp else 'NON ASSEGNATO'} — membri: {len(membri)}"
                             + (f" — ritrovo: {t.get('punto_ritrovo')}" if t.get('punto_ritrovo') else ""))

        if staff:
            lines.append("  ELENCO STAFF/VOLONTARI:")
            for s in staff[:100]:
                p = persons.get(s.get("persona_id"))
                if not p:
                    continue
                tnome = team_map.get(s.get("team_id"), {}).get("nome")
                arr = f"arrivo {s.get('data_arrivo')} {s.get('ora_arrivo') or ''}".strip() if s.get("data_arrivo") else ""
                lines.append(f"    - {_fmt_person(p)} — {s.get('categoria') or 'staff'} — ruolo: {s.get('ruolo') or p.get('ruolo') or 'n/d'}"
                             f" — team: {tnome or 'n/d'} — area: {s.get('area') or 'n/d'} — stato: {s.get('stato') or 'n/d'}"
                             + (f" — {arr}" if arr else "")
                             + (f" — referente: {s.get('responsabile')}" if s.get('responsabile') else ""))

        scoperti = [s for s in shifts if not s.get("persona_id")]
        lines.append(f"  TURNI: {len(shifts)} totali, {len(scoperti)} SCOPERTI.")
        for s in shifts[:120]:
            p = persons.get(s.get("persona_id")) if s.get("persona_id") else None
            lines.append(f"    - {s.get('data') or 'n/d'} {s.get('ora_inizio') or ''}-{s.get('ora_fine') or ''}"
                         f" | area: {s.get('area') or 'n/d'} | team: {team_map.get(s.get('team_id'), {}).get('nome') or 'n/d'}"
                         f" | {'COPERTO da ' + _fmt_person(p) if p else 'SCOPERTO'}")

        if deals:
            pipeline = sum(float(d.get("valore") or 0) for d in deals if d.get("fase") != "perso")
            confermato = sum(float(d.get("valore_confermato") or d.get("valore") or 0) for d in deals if d.get("fase") == "confermato")
            lines.append(f"  SPONSOR/PIPELINE: {len(deals)} trattative — VALORE PIPELINE (escluse perse): "
                         f"€{pipeline:,.0f} — VALORE CONFERMATO: €{confermato:,.0f}.".replace(",", "."))
            for d in deals:
                c = companies.get(d.get("azienda_id"))
                lines.append(f"    - {c.get('nome') if c else 'azienda n/d'} — tipo: {d.get('tipo')} — fase: {d.get('fase')}"
                             f" — livello: {d.get('livello') or 'n/d'} — valore: €{float(d.get('valore') or 0):,.0f}"
                             f" — confermato: €{float(d.get('valore_confermato') or 0):,.0f}".replace(",", "."))

        if acts:
            def _act_bucket(a):
                if a.get("stato") == "completata":
                    return "completata"
                if a.get("stato") == "in_corso":
                    return "in_corso"
                if (a.get("data") or "") and (a.get("data") or "")[:10] < today:
                    return "scaduta"
                return "da_fare"
            buckets = {"completata": 0, "in_corso": 0, "da_fare": 0, "scaduta": 0}
            scadute = []
            for a in acts:
                b = _act_bucket(a)
                buckets[b] += 1
                if b == "scaduta":
                    scadute.append(a)
            lines.append(f"  ATTIVITÀ: {len(acts)} — completate: {buckets['completata']}, in corso: {buckets['in_corso']}, "
                         f"da iniziare: {buckets['da_fare']}, SCADUTE: {buckets['scaduta']}.")
            for a in scadute:
                lines.append(f"    - SCADUTA: {a.get('titolo')} (scadenza {a.get('data')})")

        if fups:
            fscad = [f for f in fups if (f.get("scadenza") or "9999")[:10] < today and f.get("stato") != "completato"]
            lines.append(f"  FOLLOW-UP: {len(fups)} — scaduti: {len(fscad)}.")
            for f in fups[:40]:
                c = companies.get(f.get("azienda_id"))
                lines.append(f"    - {f.get('titolo')} — scadenza: {f.get('scadenza') or 'n/d'} — stato: {f.get('stato')}"
                             f" — priorità: {f.get('priorita') or 'n/d'}" + (f" — azienda: {c.get('nome')}" if c else ""))

        if lodgings or meals:
            lines.append(f"  OSPITALITÀ: {len(lodgings)} pernottamenti, {len(meals)} pasti.")
            for l in lodgings[:60]:
                p = persons.get(l.get("persona_id"))
                st = structures.get(l.get("struttura_id"))
                sname = (st or {}).get("nome") or l.get("struttura_nome") or "struttura n/d"
                lines.append(f"    - PERNOTTAMENTO: {_fmt_person(p) if p else 'n/d'} @ {sname}"
                             f" — check-in {l.get('check_in') or 'n/d'} / check-out {l.get('check_out') or 'n/d'}"
                             f" — a carico di: {l.get('a_carico_di') or 'n/d'}")
            mcount = {}
            for m in meals:
                key = (m.get("data"), m.get("tipo_pasto"))
                mcount[key] = mcount.get(key, 0) + 1
            for (d, tp), n in sorted(mcount.items(), key=lambda x: (x[0][0] or "")):
                lines.append(f"    - PASTI {d or 'n/d'} {tp or ''}: {n} persone")

        if maps:
            lines.append(f"  MAPPE/PERCORSI: " + ", ".join(f"{m.get('nome')}" + (f" ({m.get('distanza')}km)" if m.get('distanza') else "") for m in maps))

        # Criticità sintetiche
        crit = []
        if scoperti:
            crit.append(f"{len(scoperti)} turni scoperti")
        teams_no_resp = [t.get("nome") for t in teams if not t.get("responsabile_id")]
        if teams_no_resp:
            crit.append("team senza responsabile: " + ", ".join(teams_no_resp))
        act_scad = len([a for a in acts if a.get("stato") != "completata" and (a.get("data") or "")[:10] < today and a.get("data")])
        if act_scad:
            crit.append(f"{act_scad} attività scadute")
        fup_scad = len([f for f in fups if (f.get("scadenza") or "9999")[:10] < today and f.get("stato") != "completato"])
        if fup_scad:
            crit.append(f"{fup_scad} follow-up scaduti")
        vol_no_ref = len([s for s in staff if s.get("categoria") == "volontario" and not s.get("responsabile")])
        if vol_no_ref:
            crit.append(f"{vol_no_ref} volontari senza referente")
        lines.append("  CRITICITÀ: " + ("; ".join(crit) if crit else "nessuna rilevata."))
        lines.append("")

    return "\n".join(lines)


class ChatIn(BaseModel):
    question: str
    conversation_id: Optional[str] = None
    page_context: Optional[str] = None
    event_id: Optional[str] = None


@api.post("/support/chat")
async def support_chat(body: ChatIn, request: Request, user: dict = Depends(get_current_user)):
    org = DEFAULT_ORG
    if body.conversation_id:
        conv = await db.support_conversations.find_one({"id": body.conversation_id}, {"_id": 0})
        if not conv or conv["user_id"] != user["user_id"]:
            raise HTTPException(status_code=404, detail="Conversazione non trovata")
    else:
        conv = await _create("support_conversations", {"org_id": org, "user_id": user["user_id"],
                                                        "user_email": user.get("email"), "user_name": user.get("name") or user.get("email"),
                                                        "event_id": body.event_id, "page_context": body.page_context,
                                                        "category": None, "stato": "aperta", "last_question": body.question})
    await _create("support_messages", {"org_id": org, "conversation_id": conv["id"], "role": "user",
                                        "content": body.question, "user_id": user["user_id"], "feedback": None})
    hist = await db.support_messages.find({"conversation_id": conv["id"]}, {"_id": 0}).sort("created_at", 1).to_list(50)
    role = _support_role(user)
    ctx, sources, _ = await build_kb_context(body.question, role=role)
    # Live operational data of the user's active org (STRICTLY isolated by org_id).
    # Only managers (org admin / super admin acting on an org) receive it.
    org_data = None
    try:
        oid, is_mgr = await _resolve_org_for_support(request, user)
        if oid and is_mgr:
            org_data = await build_org_data_context(oid, body.question)
    except Exception as e:  # noqa: BLE001
        logger.warning("Contesto dati assistente non disponibile: %s", e)
        org_data = None
    result = await support_service.answer_question(body.question, ctx, page_context=body.page_context,
                                                   history=[{"role": m["role"], "content": m["content"]} for m in hist[:-1]],
                                                   role=role, org_data=org_data)
    amsg = await _create("support_messages", {"org_id": org, "conversation_id": conv["id"], "role": "assistant",
                                              "content": result["answer"], "category": result.get("category"),
                                              "confidence": result.get("confidence"), "answered": result.get("answered", True),
                                              "sources": sources, "feedback": None})
    upd = {"category": result.get("category"), "last_question": body.question, "updated_at": now_iso()}
    if body.event_id:
        upd["event_id"] = body.event_id
    await db.support_conversations.update_one({"id": conv["id"]}, {"$set": upd})
    if result.get("is_feature_request"):
        await _record_feature_request(result.get("feature_request_summary") or body.question, body.question, conv["id"], user, org)
    return {"conversation_id": conv["id"], "message_id": amsg["id"], "answer": result["answer"],
            "answered": result.get("answered", True), "category": result.get("category"),
            "confidence": result.get("confidence"), "is_feature_request": result.get("is_feature_request", False)}


class FeedbackIn(BaseModel):
    message_id: str
    value: str  # up | down


@api.post("/support/feedback")
async def support_feedback(body: FeedbackIn, user: dict = Depends(get_current_user)):
    m = await db.support_messages.find_one({"id": body.message_id}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="Messaggio non trovato")
    conv = await db.support_conversations.find_one({"id": m["conversation_id"]}, {"_id": 0})
    if conv and conv["user_id"] != user["user_id"] and user.get("role") not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Non autorizzato")
    val = "down" if body.value == "down" else "up"
    await db.support_messages.update_one({"id": body.message_id}, {"$set": {"feedback": val}})
    await _create("support_feedback", {"org_id": m.get("org_id", DEFAULT_ORG), "message_id": body.message_id,
                                       "conversation_id": m["conversation_id"], "user_id": user["user_id"], "value": val})
    return {"ok": True}


@api.post("/support/ticket")
async def support_create_ticket(body: dict, user: dict = Depends(get_current_user)):
    cid = body.get("conversation_id")
    conv = await db.support_conversations.find_one({"id": cid}, {"_id": 0})
    if not conv or (conv["user_id"] != user["user_id"] and user.get("role") not in ADMIN_ROLES):
        raise HTTPException(status_code=404, detail="Conversazione non trovata")
    msgs = await db.support_messages.find({"conversation_id": cid}, {"_id": 0}).sort("created_at", 1).to_list(100)
    domanda = next((m["content"] for m in msgs if m["role"] == "user"), conv.get("last_question"))
    t = await _create("support_tickets", {"org_id": conv.get("org_id", DEFAULT_ORG), "conversation_id": cid, "user_id": user["user_id"],
                                          "utente": user.get("email"), "event_id": conv.get("event_id"),
                                          "page_context": conv.get("page_context"), "domanda": domanda,
                                          "cronologia": [{"role": m["role"], "content": m["content"]} for m in msgs], "stato": "aperto"})
    await db.support_conversations.update_one({"id": cid}, {"$set": {"stato": "ticket"}})
    return t


@api.get("/support/my-conversations")
async def support_my_conversations(user: dict = Depends(get_current_user)):
    return await db.support_conversations.find({"user_id": user["user_id"]}, {"_id": 0}).sort("updated_at", -1).to_list(500)


@api.get("/support/conversations")
async def support_conversations(user_id: Optional[str] = None, category: Optional[str] = None,
                                event_id: Optional[str] = None, feedback: Optional[str] = None,
                                resolved: Optional[str] = None, q: Optional[str] = None,
                                date_from: Optional[str] = None, date_to: Optional[str] = None,
                                admin: dict = Depends(require_superadmin)):
    query = {"org_id": DEFAULT_ORG}
    if user_id:
        query["user_id"] = user_id
    if category:
        query["category"] = category
    if event_id:
        query["event_id"] = event_id
    if resolved == "true":
        query["stato"] = "risolta"
    elif resolved == "false":
        query["stato"] = {"$ne": "risolta"}
    if date_from or date_to:
        rng = {}
        if date_from:
            rng["$gte"] = date_from
        if date_to:
            rng["$lte"] = date_to + "T23:59:59"
        query["created_at"] = rng
    convs = await db.support_conversations.find(query, {"_id": 0}).sort("updated_at", -1).to_list(2000)
    if feedback in ("up", "down"):
        fb_convs = set(m["conversation_id"] for m in await db.support_messages.find({"feedback": feedback}, {"_id": 0, "conversation_id": 1}).to_list(5000))
        convs = [c for c in convs if c["id"] in fb_convs]
    if q:
        ql = q.lower()
        match_ids = set(m["conversation_id"] for m in await db.support_messages.find({}, {"_id": 0, "conversation_id": 1, "content": 1}).to_list(20000) if ql in (m.get("content") or "").lower())
        convs = [c for c in convs if c["id"] in match_ids or ql in (c.get("last_question") or "").lower()]
    return convs


@api.get("/support/conversations/{cid}")
async def support_conversation_detail(cid: str, user: dict = Depends(get_current_user)):
    conv = await db.support_conversations.find_one({"id": cid}, {"_id": 0})
    if not conv:
        raise HTTPException(status_code=404, detail="Conversazione non trovata")
    if conv["user_id"] != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Non autorizzato")
    msgs = await db.support_messages.find({"conversation_id": cid}, {"_id": 0}).sort("created_at", 1).to_list(500)
    return {"conversation": conv, "messages": msgs}


@api.put("/support/conversations/{cid}/resolve")
async def support_resolve_conversation(cid: str, body: dict, admin: dict = Depends(require_superadmin)):
    await db.support_conversations.update_one({"id": cid}, {"$set": {"stato": "risolta" if body.get("resolved", True) else "aperta"}})
    return {"ok": True}


@api.post("/support/faq/generate")
async def support_faq_generate(body: dict, admin: dict = Depends(require_superadmin)):
    question = body.get("question") or ""
    ctx, _, _ = await build_kb_context(question)
    return await support_service.draft_faq(question, ctx)


@api.get("/support/insights")
async def support_insights(admin: dict = Depends(require_superadmin)):
    org = DEFAULT_ORG
    convs = await db.support_conversations.find({"org_id": org}, {"_id": 0}).to_list(5000)
    msgs = await db.support_messages.find({"org_id": org}, {"_id": 0}).to_list(50000)
    user_msgs = [m for m in msgs if m["role"] == "user"]
    asst_msgs = [m for m in msgs if m["role"] == "assistant"]
    tickets = await db.support_tickets.count_documents({"org_id": org})
    up = sum(1 for m in asst_msgs if m.get("feedback") == "up")
    down = sum(1 for m in asst_msgs if m.get("feedback") == "down")
    rated = up + down
    unanswered = [{"message_id": m["id"], "conversation_id": m["conversation_id"], "content": m["content"], "created_at": m.get("created_at")}
                  for m in asst_msgs if m.get("answered") is False]
    negatives = []
    for m in asst_msgs:
        if m.get("feedback") == "down":
            uq = next((x["content"] for x in user_msgs if x["conversation_id"] == m["conversation_id"]), "")
            negatives.append({"message_id": m["id"], "conversation_id": m["conversation_id"], "question": uq, "answer": m["content"]})
    cat_count = defaultdict(int)
    for c in convs:
        if c.get("category"):
            cat_count[c["category"]] += 1
    categorie = sorted([{"categoria": k, "count": v} for k, v in cat_count.items()], key=lambda x: -x["count"])
    freq = defaultdict(lambda: {"count": 0, "example": ""})
    for m in user_msgs:
        key = " ".join(sorted(list(_sup_tokens(m["content"]))[:6]))
        freq[key]["count"] += 1
        if not freq[key]["example"]:
            freq[key]["example"] = m["content"]
    domande_frequenti = sorted([{"argomento": v["example"], "count": v["count"]} for v in freq.values() if v["count"] > 0], key=lambda x: -x["count"])[:15]
    from collections import Counter
    day_count = Counter((m.get("created_at") or "")[:10] for m in user_msgs if m.get("created_at"))
    trend = [{"data": d, "count": c} for d, c in sorted(day_count.items())][-14:]
    return {
        "domande_totali": len(user_msgs),
        "utenti_attivi": len(set(c["user_id"] for c in convs)),
        "conversazioni": len(convs),
        "perc_utili": round(up / rated * 100, 1) if rated else 0,
        "perc_non_utili": round(down / rated * 100, 1) if rated else 0,
        "domande_senza_risposta": len(unanswered),
        "ticket_generati": tickets,
        "categorie_piu_richieste": categorie,
        "domande_frequenti": domande_frequenti,
        "trend": trend,
        "unanswered_list": unanswered[:50],
        "negative_list": negatives[:50],
    }


async def seed_support():
    if await db.support_categories.count_documents({}) == 0:
        for n in ["Eventi", "Persone", "Aziende", "Sponsor", "Staff", "Volontari", "Team", "Turni",
                  "Attività", "Documenti", "Briefing", "Impostazioni", "Account"]:
            await _create("support_categories", {"org_id": DEFAULT_ORG, "nome": n, "slug": n.lower()})
    kb = [
        ("Creare un nuovo evento", "eventi", "Come creo un nuovo evento?",
         "Vai in 'Eventi' e premi 'Aggiungi'. Inserisci nome, tipologia, date di inizio e fine, orari, località e organizzatore, poi salva. L'evento sarà subito disponibile per collegare persone, sponsor, team e turni.",
         ["creare evento", "nuovo evento", "aggiungere evento"]),
        ("Modificare o eliminare un evento", "eventi", "Come modifico o elimino un evento?",
         "In 'Eventi' usa l'icona a forma di matita sulla riga per modificare i dati, oppure l'icona cestino per eliminarlo (l'azione va confermata). Le associazioni collegate all'evento restano coerenti con l'anagrafica centrale.",
         ["modificare evento", "eliminare evento", "cancellare evento"]),
        ("Gestire date, orari e stato dell'evento", "eventi", "Come gestisco le date e lo stato di un evento?",
         "Nella scheda dell'evento imposti data/ora di inizio e fine ufficiali e lo stato (es. pianificato, in corso, concluso). Le date dell'evento sono distinte dalle presenze/turni dello staff, che gestisci separatamente.",
         ["date evento", "orari evento", "stato evento"]),
        ("Inserire uno sponsor", "sponsor", "Come inserisco uno sponsor?",
         "Vai in 'Sponsor & Partner' per la pipeline commerciale, oppure apri l'Azienda in 'Aziende'. Se l'azienda non esiste creala con 'Aggiungi azienda', imposta il tipo 'Sponsor' e aggiungi i referenti nella stessa schermata. Per collegarla a un evento usa una trattativa (deal) nella pipeline Sponsor & Partner indicando evento, livello e valore.",
         ["sponsor", "aggiungere sponsor", "nuovo sponsor", "inserire sponsor", "pipeline"]),
        ("Gestire la pipeline sponsor e le trattative", "sponsor", "Come gestisco la pipeline degli sponsor?",
         "In 'Sponsor & Partner' ogni trattativa (deal) ha una fase: Prospect, Contattato, Proposta inviata, In trattativa, Confermato, Perso. Crea una trattativa collegando azienda ed evento, indica livello e valore e aggiornane la fase man mano che avanza. La pipeline legge sempre dall'anagrafica Aziende, senza duplicare i dati.",
         ["pipeline", "trattativa", "deal", "fase sponsor", "partner"]),
        ("Aggiungere una persona in anagrafica", "persone", "Come aggiungo una nuova persona?",
         "Vai in 'Persone' e premi 'Aggiungi persona'. Compila nome, cognome, contatti e gli altri campi utili (azienda, qualifica, indirizzo, LinkedIn). La persona è un record unico: potrai poi collegarla a più aziende ed eventi con ruoli diversi.",
         ["aggiungere persona", "nuova persona", "anagrafica persona"]),
        ("Assegnare un volontario a un evento", "volontari", "Come assegno un volontario a un evento?",
         "Apri 'Persone', clicca sulla persona e vai nella scheda 'Eventi': seleziona l'evento, scegli la categoria 'Volontario', assegna eventualmente ruolo, area e team e premi 'Associa'. La stessa persona può essere volontaria in un evento e staff in un altro senza duplicare l'anagrafica.",
         ["volontario", "assegnare volontario", "associare volontario", "evento"]),
        ("Aggiungere una persona allo staff di un evento", "staff", "Come aggiungo una persona allo staff?",
         "Apri la persona in 'Persone', scheda 'Eventi', seleziona l'evento e imposta la categoria 'Staff' (o 'Collaboratore'), con ruolo, area, team e stato di presenza. Il ruolo dipende dalla relazione persona-evento, quindi la stessa persona può avere ruoli diversi in eventi diversi.",
         ["staff", "aggiungere staff", "membro staff", "collaboratore"]),
        ("Collegare una persona a più eventi", "persone", "Come collego una persona a più eventi?",
         "In CRMEvent l'anagrafica è unica: apri la persona in 'Persone' e nella scheda 'Eventi' aggiungi tutte le associazioni evento che servono, ognuna con la propria categoria e ruolo. Non creare anagrafiche separate: la stessa persona resta un unico record.",
         ["collegare persona", "più eventi", "persona multipla", "associare persona"]),
        ("Creare un'azienda e aggiungere referenti", "aziende", "Come creo un'azienda con i suoi referenti?",
         "Vai in 'Aziende' → 'Aggiungi azienda'. Compila ragione sociale, settore, tipo e contatti. Nella stessa schermata puoi aggiungere uno o più referenti con 'Aggiungi referente': al salvataggio il sistema crea l'azienda e crea/collega automaticamente le persone in anagrafica, verificando i duplicati.",
         ["creare azienda", "nuova azienda", "referente", "referenti azienda"]),
        ("Modificare i dati di un'azienda", "aziende", "Come modifico i dati di un'azienda?",
         "Vai in 'Aziende', clicca sulla riga dell'azienda per aprire la scheda e premi 'Modifica'. Puoi aggiornare ragione sociale, settore, contatti e responsabile interno. Dalla scheda gestisci anche i referenti nella tab 'Referenti'.",
         ["modificare azienda", "aggiornare azienda", "dati azienda"]),
        ("Aggiungere referenti a un'azienda con controllo duplicati", "aziende", "Come aggiungo un referente a un'azienda esistente?",
         "Apri la scheda azienda, tab 'Referenti', 'Aggiungi referente': inserisci i dati e premi 'Verifica e salva'. Il sistema controlla i duplicati per email, cellulare e nome+cognome: se trova una persona esistente propone di collegarla invece di crearne una nuova.",
         ["referente", "aggiungere referente", "contatto azienda", "duplicati"]),
        ("Creare un team e assegnare un Team Leader", "team", "Come creo un team e assegno il responsabile?",
         "Vai in 'Persone' → scheda 'Team' (oppure dalla scheda evento) e premi 'Aggiungi'. Indica nome team, evento, area e seleziona il Team Leader tra le persone in anagrafica. I membri del team si gestiscono tramite le presenze/associazioni all'evento.",
         ["team", "creare team", "team leader", "responsabile team", "squadra"]),
        ("Creare un turno", "turni", "Come creo un turno?",
         "Vai in 'Persone' → scheda 'Turni' (oppure nella scheda dell'evento) e usa 'Aggiungi'. Indica evento, data, ora inizio/fine, area, ruolo, team e luogo. Lascia la persona vuota per creare un turno scoperto da assegnare in seguito.",
         ["turno", "creare turno", "nuovo turno", "shift"]),
        ("Coprire un turno scoperto", "turni", "Come assegno un turno scoperto a una persona?",
         "I turni senza persona risultano 'Scoperti'. Apri il turno in modifica e seleziona la persona da assegnare: il turno passerà da scoperto ad assegnato. Puoi filtrare i turni per evento, area e team per individuare rapidamente quelli ancora da coprire.",
         ["turno scoperto", "assegnare turno", "coprire turno"]),
        ("Registrare un'attività (chiamata, email, meeting)", "attivita", "Come registro un'attività?",
         "Vai in 'Attività' e premi 'Aggiungi'. Scegli il tipo (chiamata, email, meeting, nota), il titolo, la data e collega eventualmente persona, azienda o evento. Le attività tengono traccia dello storico delle interazioni.",
         ["attività", "registrare attività", "chiamata", "email", "meeting", "nota"]),
        ("Creare un follow-up con scadenza", "attivita", "Come creo un follow-up con promemoria?",
         "Vai in 'Follow-up' e premi 'Aggiungi': indica titolo, scadenza e collega azienda, persona o evento. I follow-up in scadenza o scaduti compaiono nelle notifiche in alto e nella dashboard per non perdere le azioni importanti.",
         ["follow-up", "followup", "promemoria", "scadenza", "ricontattare"]),
        ("Preparare il briefing dello staff", "briefing", "Come preparo il briefing dello staff?",
         "Nella scheda dell'evento trovi le viste operative Staff, Volontari, Team e Turni: da qui verifica ruoli, aree, punti di ritrovo e turni assegnati. Puoi allegare mappe e percorsi nella sezione Mappe dell'evento per distribuire le informazioni operative al team.",
         ["briefing", "staff", "preparare briefing", "istruzioni staff"]),
        ("Caricare mappe e percorsi di un evento", "documenti", "Come carico mappe e percorsi per un evento?",
         "Nella scheda dell'evento apri la sezione Mappe e usa il caricamento per allegare immagini o PDF (planimetrie, percorsi) e aggiungere link a Google Maps. Le mappe sono poi visibili anche allo staff/volontari nella loro area personale.",
         ["mappe", "percorsi", "planimetria", "documenti evento", "caricare file"]),
        ("Invitare una persona all'accesso (area personale)", "account", "Come invito una persona ad accedere a CRMEvent?",
         "Apri la persona in 'Persone' e usa 'Gestisci accesso' / l'icona invito: scegli il ruolo (Staff o Volontario) e invia l'invito. La persona riceve un'email per attivare l'account e impostare la password; lo stato passa da 'Non invitato' a 'Invito inviato' e poi 'Account attivo'.",
         ["invito", "invitare persona", "accesso", "attivare account", "area personale"]),
        ("Disabilitare o riattivare un accesso", "account", "Come disabilito o riattivo l'accesso di una persona?",
         "Dalla scheda persona, tab 'Accesso' (o 'Gestisci accesso'), puoi disabilitare l'accesso di un account attivo o riattivarlo in seguito. L'anagrafica della persona resta invariata, cambia solo la possibilità di accedere.",
         ["disabilitare accesso", "riattivare accesso", "bloccare utente"]),
        ("Recuperare o cambiare la password", "account", "Come recupero o cambio la mia password?",
         "Dalla pagina di login usa 'Password dimenticata' per ricevere via email il link di reimpostazione. Se sei già dentro, vai in 'Profilo & Account' per cambiare la password inserendo quella attuale e la nuova.",
         ["password", "recupero password", "cambiare password", "reset password"]),
        ("Collegare e sincronizzare Google Calendar", "impostazioni", "Come collego Google Calendar?",
         "Vai in 'Profilo & Account' (o Impostazioni) e collega il tuo account Google. Una volta connesso puoi sincronizzare eventi e turni sul tuo calendario; le voci create riportano il prefisso 'CRMEvent'. La sincronizzazione evita duplicati.",
         ["google calendar", "sincronizzare calendario", "collegare google", "calendario"]),
        ("Personalizzare le liste in Impostazioni", "impostazioni", "Come personalizzo tipologie, settori, ruoli e aree?",
         "In 'Impostazioni' gestisci le liste dinamiche: tipologie evento, settori azienda, ruoli staff, aree operative e livelli di sponsorship. Puoi aggiungere, rinominare ed eliminare le voci; prima di eliminarne una il sistema verifica che non sia già in uso.",
         ["impostazioni", "liste", "tipologie", "settori", "ruoli", "aree", "personalizzare"]),
        ("Usare la ricerca globale", "altro", "Come cerco velocemente persone, aziende o eventi?",
         "Usa la barra di ricerca in alto: digitando trovi eventi, aziende e persone. Ogni persona e ogni azienda compaiono come risultato unico, così da aprire direttamente la scheda con tutte le relazioni collegate.",
         ["ricerca", "cercare", "ricerca globale", "trovare"]),
    ]
    existing_titles = set(e.get("titolo") for e in await db.support_knowledge_base.find({}, {"_id": 0, "titolo": 1}).to_list(5000))
    added = 0
    for titolo, cat, dom, risp, kw in kb:
        if titolo in existing_titles:
            continue
        await _create("support_knowledge_base", {"org_id": DEFAULT_ORG, "titolo": titolo, "categoria": cat,
                                                 "domanda": dom, "risposta": risp, "parole_chiave": kw, "stato": "pubblicato"})
        added += 1
    if added:
        logger.info(f"Support KB: +{added} voci pubblicate")
    portal = [
        ("Area personale: i miei eventi", "eventi", "Come vedo i miei eventi?",
         "Nella tua area personale, in 'I miei eventi', trovi tutti gli eventi a cui sei stato associato, con il tuo ruolo e lo stato. Tocca un evento per aprirne i dettagli operativi.",
         ["miei eventi", "vedere eventi", "area personale", "eventi assegnati"], "staff,volontario"),
        ("Area personale: i miei turni", "turni", "Come vedo i miei turni?",
         "Apri l'evento dalla tua area personale: nel blocco 'I miei turni' trovi ogni turno con data, orario di inizio e fine, ruolo, area e luogo. Con il pulsante 'Calendar' puoi aggiungere un turno a Google Calendar.",
         ["miei turni", "vedere turni", "orario turno", "quando lavoro"], "staff,volontario"),
        ("Area personale: data, orario e luogo del turno", "turni", "Dove vedo data, ora e luogo del mio turno?",
         "Nel dettaglio dell'evento, nel blocco 'I miei turni', ogni turno mostra data e orario; area, luogo operativo e punto di ritrovo li trovi nel blocco 'Il mio ruolo'.",
         ["luogo turno", "orario turno", "dove devo andare", "punto di ritrovo"], "staff,volontario"),
        ("Area personale: il mio team e il Team Leader", "team", "Come vedo il mio team e chi è il Team Leader?",
         "Nel dettaglio dell'evento, il blocco 'Il mio ruolo' mostra il tuo team; nel blocco 'Il mio Team' vedi i colleghi e il Team Leader è indicato accanto al nome.",
         ["mio team", "team leader", "colleghi", "squadra"], "staff,volontario"),
        ("Area personale: briefing e informazioni operative", "briefing", "Dove trovo il briefing e le informazioni operative?",
         "Nel dettaglio dell'evento trovi ruolo, area, luogo operativo, punto di ritrovo ed eventuali note operative nel blocco 'Il mio ruolo', oltre alla descrizione dell'evento in alto. Sono le informazioni condivise dall'organizzatore per la tua attività.",
         ["briefing", "informazioni operative", "istruzioni", "note operative"], "staff,volontario"),
        ("Area personale: mappe, percorsi e documenti", "documenti", "Come vedo mappe, percorsi e documenti condivisi?",
         "Nel dettaglio dell'evento, nel blocco 'Mappe e percorsi', puoi aprire le immagini, i PDF, i file e i link a Google Maps che l'organizzatore ha condiviso per l'evento.",
         ["mappe", "percorsi", "documenti", "planimetria", "come arrivo"], "staff,volontario"),
        ("Area personale: la mia disponibilità e presenza (sola lettura)", "volontari", "Come vedo o confermo la mia disponibilità e presenza?",
         "Nell'area personale puoi VISUALIZZARE il tuo stato di presenza (es. confermato, da riconfermare) e gli orari di arrivo e partenza nel blocco 'La mia presenza'. La conferma o la modifica dello stato è gestita dall'organizzatore: per comunicare la tua disponibilità o eventuali variazioni contatta il tuo Team Leader o l'organizzatore dell'evento.",
         ["disponibilità", "confermare presenza", "mia presenza", "stato presenza"], "staff,volontario"),
        ("Area personale: modifiche e comunicazioni sul turno", "turni", "Come modifico il mio turno o segnalo un problema?",
         "I turni sono assegnati dall'organizzatore e nella tua area personale sono in sola lettura: non puoi modificarli direttamente. Per richieste di cambio turno o segnalazioni contatta il tuo Team Leader o l'organizzatore dell'evento.",
         ["modificare turno", "cambiare turno", "segnalare problema turno"], "staff,volontario"),
        ("Area personale: usare CRMEvent da smartphone", "account", "Posso usare l'area personale dal telefono?",
         "Sì, l'area personale è ottimizzata per smartphone e tablet: puoi consultare i tuoi eventi, turni, team, mappe e sincronizzare i tuoi impegni con Google Calendar direttamente dal cellulare.",
         ["smartphone", "telefono", "mobile", "cellulare", "app"], "staff,volontario"),
        ("Area personale: aggiungere eventi e turni a Google Calendar", "impostazioni", "Come aggiungo i miei turni al calendario?",
         "Dal dettaglio dell'evento premi 'Aggiungi a Google Calendar' per l'evento, oppure il pulsante 'Calendar' accanto a ciascun turno. È necessario avere il proprio account Google collegato.",
         ["google calendar", "aggiungere al calendario", "sincronizzare turni"], "staff,volontario"),
        ("Accesso e recupero password (staff e volontari)", "account", "Non riesco ad accedere, come recupero la password?",
         "Dalla pagina di login usa 'Password dimenticata' per ricevere via email il link di reimpostazione. Se hai appena ricevuto un invito, controlla l'email di attivazione (anche nello spam) per impostare la prima password. Se l'accesso risulta disabilitato, contatta l'organizzatore.",
         ["accesso", "login", "password dimenticata", "recupero password", "non riesco ad accedere"], "tutti"),
    ]
    for titolo, cat, dom, risp, kw, ruoli in portal:
        if titolo in existing_titles:
            continue
        await _create("support_knowledge_base", {"org_id": DEFAULT_ORG, "titolo": titolo, "categoria": cat,
                                                 "domanda": dom, "risposta": risp, "parole_chiave": kw,
                                                 "stato": "pubblicato", "ruoli": ruoli})
        added += 1
    # Segnala funzionalità area personale non ancora disponibili (da valutare)
    gaps = [
        ("Conferma disponibilità dall'area personale", "Staff e volontari vorrebbero confermare/aggiornare la propria disponibilità e lo stato di presenza direttamente dall'area personale (oggi in sola lettura)."),
        ("Check-in / registrazione presenze dall'area personale", "Possibilità per staff e volontari di registrare l'arrivo/partenza (check-in) dal proprio dispositivo."),
        ("Modifica turno e richieste di cambio dall'area personale", "Staff e volontari vorrebbero poter richiedere o segnalare cambi turno dall'area personale."),
        ("Comunicazioni/messaggi con il Team Leader dall'area personale", "Canale di comunicazione tra volontari/staff e Team Leader/organizzatore all'interno dell'app."),
    ]
    existing_fr = set(f.get("titolo") for f in await db.support_feature_requests.find({"stato": {"$in": ["nuova", "da_valutare", "pianificata", "in_sviluppo"]}}, {"_id": 0, "titolo": 1}).to_list(2000))
    for titolo, desc in gaps:
        if titolo in existing_fr:
            continue
        await _create("support_feature_requests", {"org_id": DEFAULT_ORG, "titolo": titolo, "descrizione": desc,
                                                    "stato": "da_valutare", "utenti_count": 0, "organizzazioni": [DEFAULT_ORG],
                                                    "prima_richiesta": now_iso(), "ultima_richiesta": now_iso(), "origine": "area_personale"})


# ---------------- Google Calendar ----------------
def _cal_state(user_id: str):
    """Return (state_jwt, jti). The jti ties the PKCE verifier to this specific OAuth request."""
    jti = secrets.token_urlsafe(24)
    state = jwt.encode({"uid": user_id, "jti": jti,
                        "exp": datetime.now(timezone.utc) + timedelta(minutes=15)},
                       JWT_SECRET, algorithm=JWT_ALG)
    return state, jti


@api.get("/calendar/status")
async def calendar_status(user: dict = Depends(get_current_user)):
    if not gcal_utils.is_configured():
        return {"configured": False, "connected": False}
    conn = await db.calendar_connections.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not conn:
        return {"configured": True, "connected": False}
    return {"configured": True, "connected": True, "google_email": conn.get("google_email"),
            "calendar_id": conn.get("calendar_id", "primary")}


@api.get("/calendar/connect")
async def calendar_connect(user: dict = Depends(get_current_user)):
    if not gcal_utils.is_configured():
        raise HTTPException(status_code=400, detail="Google Calendar non è configurato. Aggiungi GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET nei Secrets.")
    state, jti = _cal_state(user["user_id"])
    auth_url, code_verifier = gcal_utils.authorization_url(state)
    # Store the PKCE verifier server-side (Mongo → multi-pod safe), single-use, short TTL.
    await db.calendar_oauth_pkce.update_one({"jti": jti}, {"$set": {
        "jti": jti, "uid": user["user_id"], "code_verifier": code_verifier,
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10), "created_at": now_iso()}}, upsert=True)
    logger.info("gcal connect: redirect_uri=%s scopes=%s", gcal_utils.REDIRECT_URI, gcal_utils.SCOPES)
    return {"authorization_url": auth_url}


@api.get("/oauth/calendar/callback")
async def calendar_callback(code: str = "", state: str = "", error: str = "", error_description: str = ""):
    # Google can redirect back with ?error=... (e.g. access_denied) instead of a code.
    if error:
        logger.warning("gcal callback: google returned error stage=consent error=%s desc=%s",
                       error, (error_description or "")[:200])
        return RedirectResponse(f"{APP_URL}/app?calendar=error")
    try:
        payload = jwt.decode(state, JWT_SECRET, algorithms=[JWT_ALG])
        uid = payload["uid"]
        jti = payload.get("jti")
    except jwt.PyJWTError as e:
        logger.warning("gcal callback: invalid state jwt stage=state_decode (%s)", type(e).__name__)
        return RedirectResponse(f"{APP_URL}/app?calendar=error")
    # Retrieve the single-use PKCE verifier (delete on read); must match this uid + jti.
    pkce = await db.calendar_oauth_pkce.find_one_and_delete({"jti": jti, "uid": uid}) if jti else None
    if not pkce:
        logger.warning("gcal callback: pkce verifier missing or already used stage=pkce_lookup")
        return RedirectResponse(f"{APP_URL}/app?calendar=error")
    exp = pkce.get("expires_at")
    if isinstance(exp, datetime):
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            logger.warning("gcal callback: pkce verifier expired stage=pkce_expired")
            return RedirectResponse(f"{APP_URL}/app?calendar=error")
    try:
        tokens = gcal_utils.exchange_code(code, pkce.get("code_verifier"))
    except Exception as e:
        logger.error("gcal callback: exchange_code exception stage=code_to_token %s: %s",
                     type(e).__name__, str(e)[:200])
        return RedirectResponse(f"{APP_URL}/app?calendar=error")
    # Pop the non-sensitive diagnostic status so it is never persisted with the tokens.
    http_status = tokens.pop("_http_status", None)
    if "access_token" not in tokens:
        # Safe diagnostic log: OAuth error code + description only. NEVER logs code/tokens/secret/state.
        logger.error("gcal callback: token exchange failed stage=code_to_token http_status=%s error=%s desc=%s",
                     http_status, tokens.get("error"), str(tokens.get("error_description"))[:300])
        return RedirectResponse(f"{APP_URL}/app?calendar=error")
    info = gcal_utils.userinfo(tokens["access_token"])
    await db.calendar_connections.update_one({"user_id": uid},
        {"$set": {"user_id": uid, "tokens": tokens, "google_email": info.get("email"),
                  "calendar_id": "primary", "updated_at": now_iso()}}, upsert=True)
    return RedirectResponse(f"{APP_URL}/app?calendar=connected")


@api.get("/calendar/calendars")
async def calendar_list(user: dict = Depends(get_current_user)):
    conn = await db.calendar_connections.find_one({"user_id": user["user_id"]})
    if not conn:
        raise HTTPException(status_code=400, detail="Google Calendar non collegato")
    try:
        return {"calendars": gcal_utils.list_calendars(conn["tokens"])}
    except Exception as e:
        logger.error(f"calendar list error: {e}")
        raise HTTPException(status_code=502, detail="Errore Google Calendar")


class SelectCalIn(BaseModel):
    calendar_id: str


@api.post("/calendar/select")
async def calendar_select(body: SelectCalIn, user: dict = Depends(get_current_user)):
    await db.calendar_connections.update_one({"user_id": user["user_id"]}, {"$set": {"calendar_id": body.calendar_id}})
    return {"ok": True}


@api.post("/calendar/disconnect")
async def calendar_disconnect(user: dict = Depends(get_current_user)):
    await db.calendar_connections.delete_one({"user_id": user["user_id"]})
    return {"ok": True}


async def _sync_object(user_id: str, kind: str, ref_id: str, body: dict):
    conn = await db.calendar_connections.find_one({"user_id": user_id})
    if not conn:
        raise HTTPException(status_code=400, detail="Google Calendar non collegato")
    link = await db.calendar_event_links.find_one({"user_id": user_id, "kind": kind, "ref_id": ref_id})
    gid = link.get("google_event_id") if link else None
    cal_id = conn.get("calendar_id", "primary")
    try:
        ev = gcal_utils.upsert_event(conn["tokens"], cal_id, body, gid)
    except Exception as e:
        logger.error(f"calendar sync error: {e}")
        raise HTTPException(status_code=502, detail="Errore sincronizzazione Google Calendar")
    await db.calendar_event_links.update_one({"user_id": user_id, "kind": kind, "ref_id": ref_id},
        {"$set": {"user_id": user_id, "kind": kind, "ref_id": ref_id, "google_event_id": ev["id"],
                  "calendar_id": cal_id, "html_link": ev.get("htmlLink"), "updated_at": now_iso()}}, upsert=True)
    return ev


@api.post("/events/{event_id}/calendar-sync")
async def sync_event(event_id: str, user: dict = Depends(require_admin)):
    e = await db.events.find_one(oq(user, id=event_id), {"_id": 0})
    if not e:
        raise HTTPException(status_code=404, detail="Evento non trovato")
    link = f"{APP_URL}/eventi?id={event_id}"
    desc = (e.get("descrizione") or "") + f"\n\nScheda evento: {link}"
    loc = ", ".join([x for x in [e.get("localita"), e.get("indirizzo"), e.get("citta")] if x])
    body = gcal_utils.build_event_body(summary=f"CRMEvent · {e['nome']}", description=desc, location=loc,
                                       date_start=e.get("data_inizio"), date_end=e.get("data_fine"),
                                       time_start=e.get("ora_inizio"), time_end=e.get("ora_fine"))
    if not e.get("data_inizio"):
        raise HTTPException(status_code=400, detail="L'evento non ha una data di inizio")
    ev = await _sync_object(user["user_id"], "event", event_id, body)
    return {"ok": True, "google_event_id": ev["id"], "html_link": ev.get("htmlLink")}


@api.get("/events/{event_id}/calendar-status")
async def event_cal_status(event_id: str, user: dict = Depends(get_current_user)):
    link = await db.calendar_event_links.find_one({"user_id": user["user_id"], "kind": "event", "ref_id": event_id}, {"_id": 0})
    return {"synced": bool(link), "html_link": link.get("html_link") if link else None}


# ---------------- Staff / Volunteer personal area (/me) ----------------
def _safe_colleague(p: dict, presence: dict, team: dict) -> dict:
    return {"nome": p.get("nome"), "cognome": p.get("cognome"), "ruolo": presence.get("ruolo"),
            "foto_url": p.get("foto_url"), "is_leader": bool(team and team.get("responsabile_id") == p.get("id"))}


@api.get("/me/events")
async def my_events(user: dict = Depends(get_current_user)):
    pid = user.get("person_id")
    if not pid:
        return {"events": []}
    oid = user.get("org_id")
    presences = await db.staff.find({"persona_id": pid, "org_id": oid}, {"_id": 0}).to_list(500)
    out = []
    for pr in presences:
        ev = await db.events.find_one({"id": pr["evento_id"], "org_id": oid}, {"_id": 0})
        if ev:
            out.append({"event": ev, "presence": pr})
    out.sort(key=lambda x: x["event"].get("data_inizio") or "9999")
    return {"events": out}


@api.get("/me/events/{event_id}")
async def my_event_detail(event_id: str, user: dict = Depends(get_current_user)):
    pid = user.get("person_id")
    oid = user.get("org_id")
    presence = await db.staff.find_one({"persona_id": pid, "evento_id": event_id, "org_id": oid}, {"_id": 0})
    if not presence:
        raise HTTPException(status_code=404, detail="Evento non trovato")  # object check
    event = await db.events.find_one({"id": event_id, "org_id": oid}, {"_id": 0})
    my_shifts = await db.shifts.find({"persona_id": pid, "evento_id": event_id, "org_id": oid}, {"_id": 0}).to_list(200)
    my_shifts.sort(key=lambda s: (s.get("data") or "", s.get("ora_inizio") or ""))
    team = None
    colleagues = []
    if presence.get("team_id"):
        team = await db.teams.find_one({"id": presence["team_id"], "org_id": oid}, {"_id": 0})
        mates = await db.staff.find({"team_id": presence["team_id"], "evento_id": event_id, "org_id": oid}, {"_id": 0}).to_list(200)
        for m in mates:
            p = await db.persons.find_one({"id": m["persona_id"], "org_id": oid}, {"_id": 0})
            if p:
                colleagues.append(_safe_colleague(p, m, team))
    leader = None
    if team and team.get("responsabile_id"):
        lp = await db.persons.find_one({"id": team["responsabile_id"], "org_id": oid}, {"_id": 0})
        if lp:
            leader = {"nome": lp.get("nome"), "cognome": lp.get("cognome"), "foto_url": lp.get("foto_url")}
    maps = await db.event_maps.find({"evento_id": event_id, "org_id": oid}, {"_id": 0}).to_list(200)
    prio = [m for m in maps if m.get("team_id") == presence.get("team_id") or m.get("area") == presence.get("area")]
    others = [m for m in maps if m not in prio]
    return {"event": event, "presence": presence, "shifts": my_shifts, "team": team,
            "team_leader": leader, "colleagues": colleagues, "maps": prio + others}


@api.get("/me/shifts")
async def my_shifts(user: dict = Depends(get_current_user)):
    pid = user.get("person_id")
    if not pid:
        return {"shifts": []}
    s = await db.shifts.find({"persona_id": pid, "org_id": user.get("org_id")}, {"_id": 0}).to_list(500)
    s.sort(key=lambda x: (x.get("data") or "", x.get("ora_inizio") or ""))
    return {"shifts": s}


@api.post("/me/events/{event_id}/calendar-sync")
async def my_sync_event(event_id: str, user: dict = Depends(get_current_user)):
    pid = user.get("person_id")
    presence = await db.staff.find_one({"persona_id": pid, "evento_id": event_id}, {"_id": 0})
    if not presence:
        raise HTTPException(status_code=404, detail="Evento non trovato")
    e = await db.events.find_one({"id": event_id}, {"_id": 0})
    link = f"{APP_URL}/eventi?id={event_id}"
    desc = f"Ruolo: {presence.get('ruolo') or '-'} | Area: {presence.get('area') or '-'} | Punto ritrovo: {presence.get('punto_ritrovo') or '-'}\n{link}"
    body = gcal_utils.build_event_body(summary=f"CRMEvent · {e['nome']}", description=desc,
                                       location=", ".join([x for x in [e.get("localita"), e.get("citta")] if x]),
                                       date_start=e.get("data_inizio"), date_end=e.get("data_fine"),
                                       time_start=e.get("ora_inizio"), time_end=e.get("ora_fine"))
    ev = await _sync_object(user["user_id"], "event", event_id, body)
    return {"ok": True, "html_link": ev.get("htmlLink")}


@api.post("/me/shifts/{shift_id}/calendar-sync")
async def my_sync_shift(shift_id: str, user: dict = Depends(get_current_user)):
    pid = user.get("person_id")
    sh = await db.shifts.find_one({"id": shift_id, "persona_id": pid}, {"_id": 0})
    if not sh:
        raise HTTPException(status_code=404, detail="Turno non trovato")
    e = await db.events.find_one({"id": sh["evento_id"]}, {"_id": 0})
    team = await db.teams.find_one({"id": sh.get("team_id")}, {"_id": 0}) if sh.get("team_id") else None
    link = f"{APP_URL}/eventi?id={sh['evento_id']}"
    desc = f"Turno {e['nome']} | Ruolo: {sh.get('ruolo') or '-'} | Team: {team.get('nome') if team else '-'} | Luogo: {sh.get('luogo') or '-'} | Ritrovo: {sh.get('punto_ritrovo') or '-'}\n{link}"
    body = gcal_utils.build_event_body(summary=f"CRMEvent · Turno · {e['nome']}", description=desc, location=sh.get("luogo") or "",
                                       date_start=sh.get("data"), date_end=sh.get("data"),
                                       time_start=sh.get("ora_inizio"), time_end=sh.get("ora_fine"))
    if not sh.get("data"):
        raise HTTPException(status_code=400, detail="Il turno non ha una data")
    ev = await _sync_object(user["user_id"], f"shift", shift_id, body)
    return {"ok": True, "html_link": ev.get("htmlLink")}


# ---------------- leads (commercial CRM) ----------------
class Lead(BaseModel):
    nome: str
    cognome: Optional[str] = None
    organizzazione: Optional[str] = None
    email: EmailStr
    telefono: Optional[str] = None
    tipologia_eventi: Optional[str] = None
    eventi_anno: Optional[str] = None
    messaggio: Optional[str] = None
    privacy: Optional[bool] = False
    source: Optional[str] = None


class LeadUpdate(BaseModel):
    stato: Optional[str] = None
    note: Optional[str] = None


# Marketing funnel stages (ready for future email automations). Kept separate from the manual
# CRM `stato`. No PII is ever needed to move these stages.
ALLOWED_FUNNEL = {"nuovo", "demo_requested", "demo_started", "demo_completed", "trial_started", "cliente", "perso"}


class FunnelIn(BaseModel):
    status: str


@api.post("/leads")
async def create_lead(body: Lead):
    if not body.privacy:
        raise HTTPException(status_code=400, detail="È necessario accettare la privacy policy")
    now = now_iso()
    doc = await _create("leads", {**body.model_dump(), "stato": "nuovo", "note": "",
                                  "funnel_status": "demo_requested", "requested_at": now,
                                  "funnel_ts_demo_requested": now})
    try:
        await email_utils.send_email(to=os.environ["ADMIN_EMAIL"], subject="Nuova richiesta demo CRMEvent",
                                     html=email_utils.link_email(name="Michele",
                                                                 intro=f"Nuova richiesta demo da {body.nome} {body.cognome or ''} ({body.organizzazione or '-'}) — email {body.email}, tel {body.telefono or '-'}. Tipologia: {body.tipologia_eventi or '-'}, eventi/anno: {body.eventi_anno or '-'}. Provenienza: {body.source or '-'}.",
                                                                 cta_label="Apri CRMEvent", url=f"{APP_URL}/lead",
                                                                 footer_note="Gestisci il lead nella sezione Lead."))
    except Exception as e:
        logger.error(f"lead notify failed: {e}")
    # Sync the contact to Brevo (best-effort; this call never sends an email).
    try:
        list_id = await _lead_list_id()
        await brevo_funnel.upsert_contact(email=body.email, nome=body.nome, cognome=body.cognome,
                                          organizzazione=body.organizzazione, tipologia_eventi=body.tipologia_eventi,
                                          source=body.source or "richiedi-demo", funnel_status="demo_requested",
                                          list_ids=([list_id] if list_id else None))
    except Exception as e:
        logger.error(f"brevo contact upsert failed: {e}")
    # Demo funnel: when ACTIVE, EMAIL 1 replaces the legacy confirmation email (avoid double emails).
    enrolled = False
    try:
        enrolled = (await _enroll_lead(doc)).get("enrolled", False)
    except Exception as e:
        logger.error(f"funnel enroll failed: {e}")
    if not enrolled:
        # Legacy single confirmation email (used when the funnel is not active).
        try:
            await email_utils.send_email(to=body.email, subject="La tua demo di CRMEvent",
                                         html=email_utils.link_email(name=body.nome,
                                                                     intro="Grazie per il tuo interesse in CRMEvent! Puoi guardare la demo interattiva quando vuoi cliccando qui sotto. Quando sei pronto, attiva la prova gratuita di 14 giorni.",
                                                                     cta_label="Guarda la demo", url=f"{APP_URL}/demo",
                                                                     footer_note="Hai ricevuto questa email perché hai richiesto una demo su crmevent.it."))
        except Exception as e:
            logger.error(f"lead demo email failed: {e}")
    return {"ok": True, "id": doc["id"]}


@api.post("/leads/{lead_id}/funnel")
async def lead_funnel(lead_id: str, body: FunnelIn):
    """Advance a lead through the marketing funnel. Public (moved by a random lead id, no PII)."""
    if body.status not in ALLOWED_FUNNEL:
        raise HTTPException(status_code=400, detail="Stato funnel non valido")
    r = await db.leads.update_one({"id": lead_id}, {"$set": {"funnel_status": body.status,
        f"funnel_ts_{body.status}": now_iso(), "updated_at": now_iso()}})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Lead non trovato")
    lead = await db.leads.find_one({"id": lead_id}, {"_id": 0, "email": 1})
    if lead:
        await _sync_brevo_funnel_status(lead.get("email"), body.status)
    # Immediate STOP if the new status is a stop condition (mirrors the cron re-check).
    if body.status in brevo_funnel.STOP_FUNNEL_STATUSES:
        await _stop_active_demo_enrollment(lead_id, body.status)
    return {"ok": True}


@api.get("/leads")
async def list_leads(admin: dict = Depends(require_superadmin)):
    return await _list("leads")


@api.put("/leads/{lead_id}")
async def update_lead(lead_id: str, body: LeadUpdate, admin: dict = Depends(require_superadmin)):
    return await _update("leads", lead_id, body.model_dump(exclude_unset=True))


@api.delete("/leads/{lead_id}")
async def delete_lead(lead_id: str, admin: dict = Depends(require_superadmin)):
    return await _delete("leads", lead_id)


# ==================== Organizations, memberships & invites management ====================
ORG_ROLE_LABELS = {"admin_org": "Admin Organizzazione", "user": "Utente"}


def _norm_role(r: str) -> str:
    return "admin_org" if r == "admin_org" else "user"


async def _org_or_404(org_id: str) -> dict:
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=404, detail="Organizzazione non trovata")
    return org


async def _require_manage(user: dict, org_id: str) -> None:
    if not await _can_manage_org(user, org_id):
        raise HTTPException(status_code=403, detail="Non autorizzato a gestire questa organizzazione")


async def _member_view(m: dict) -> dict:
    u = await db.users.find_one({"user_id": m["user_id"]}, {"_id": 0, "password_hash": 0})
    return {"user_id": m["user_id"], "email": (u or {}).get("email"), "name": (u or {}).get("name"),
            "role": m["role"], "role_label": ORG_ROLE_LABELS.get(m["role"], m["role"]),
            "active": m.get("active", True), "account_active": (u or {}).get("active", True),
            "created_at": (u or {}).get("created_at"), "last_login_at": (u or {}).get("last_login_at"),
            "auth_provider": (u or {}).get("auth_provider"),
            "is_superadmin": (u or {}).get("role") == "superadmin"}


async def _org_detail(org_id: str) -> dict:
    org = await _org_or_404(org_id)
    members = await db.memberships.count_documents({"org_id": org_id, "active": True})
    events = await db.events.count_documents({"org_id": org_id})
    return {"id": org["id"], "nome": org.get("nome"), "type": org.get("type", "cliente"),
            "status": org.get("status", "active"), "created_at": org.get("created_at"),
            "members": members, "events": events, "subscription": _sub_summary(org)}


class OrgCreateIn(BaseModel):
    nome: str
    type: str = "cliente"
    status: str = "active"


class OrgUpdateIn(BaseModel):
    nome: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None


class MemberAddIn(BaseModel):
    email: EmailStr
    role: str = "user"


class MemberUpdateIn(BaseModel):
    role: Optional[str] = None
    active: Optional[bool] = None


class InviteCreateIn(BaseModel):
    email: EmailStr
    role: str = "user"


@api.post("/platform/organizations")
async def create_organization_admin(body: OrgCreateIn, admin: dict = Depends(require_superadmin)):
    if not body.nome.strip():
        raise HTTPException(status_code=400, detail="Nome organizzazione obbligatorio")
    otype = body.type if body.type in ("cliente", "interna", "test") else "cliente"
    status = body.status if body.status in ("active", "disabled") else "active"
    org = await _create_organization(body.nome.strip(), owner_user_id=None, org_type=otype, status=status)
    await record_audit(admin, "org_created", org_id=org["id"], org_name=org["nome"],
                       detail=f"Tipo: {otype} · Stato: {status}")
    return await _org_detail(org["id"])


@api.patch("/platform/organizations/{org_id}")
async def update_organization_admin(org_id: str, body: OrgUpdateIn, admin: dict = Depends(require_superadmin)):
    org = await _org_or_404(org_id)
    upd, changes = {}, []
    if body.nome and body.nome.strip() != org.get("nome"):
        upd["nome"] = body.nome.strip(); changes.append(f"nome: {org.get('nome')} → {body.nome.strip()}")
    if body.type and body.type in ("cliente", "interna", "test") and body.type != org.get("type"):
        upd["type"] = body.type; changes.append(f"tipo: {org.get('type')} → {body.type}")
    if body.status and body.status in ("active", "disabled") and body.status != org.get("status"):
        upd["status"] = body.status; changes.append(f"stato: {org.get('status')} → {body.status}")
    if upd:
        upd["updated_at"] = now_iso()
        await db.organizations.update_one({"id": org_id}, {"$set": upd})
        if "status" in upd and set(upd.keys()) <= {"status", "updated_at"}:
            await record_audit(admin, "org_disabled" if upd["status"] == "disabled" else "org_enabled",
                               org_id=org_id, org_name=org.get("nome"), detail="; ".join(changes))
        else:
            await record_audit(admin, "org_updated", org_id=org_id, org_name=upd.get("nome", org.get("nome")),
                               detail="; ".join(changes))
            if "status" in upd:
                await record_audit(admin, "org_disabled" if upd["status"] == "disabled" else "org_enabled",
                                   org_id=org_id, org_name=org.get("nome"), detail="Stato aggiornato")
    return await _org_detail(org_id)


@api.get("/platform/organizations/{org_id}/detail")
async def get_organization_detail(org_id: str, admin: dict = Depends(require_superadmin)):
    return await _org_detail(org_id)


@api.get("/platform/organizations/{org_id}/members")
async def list_org_members(org_id: str, user: dict = Depends(get_current_user)):
    await _require_manage(user, org_id)
    mems = await db.memberships.find({"org_id": org_id}, {"_id": 0}).to_list(500)
    return [await _member_view(m) for m in mems]


@api.post("/platform/organizations/{org_id}/members")
async def add_org_member(org_id: str, body: MemberAddIn, user: dict = Depends(get_current_user)):
    await _require_manage(user, org_id)
    org = await _org_or_404(org_id)
    email = body.email.lower()
    target = await db.users.find_one({"email": email}, {"_id": 0, "password_hash": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Nessun account CRMEvent con questa email. Usa «Invita utente» per invitarlo.")
    if target.get("role") in ("volunteer", "staff"):
        raise HTTPException(status_code=400, detail="Questo account è un membro staff/volontario e non può essere aggiunto come utente dell'organizzazione.")
    role = _norm_role(body.role)
    existing = await db.memberships.find_one({"user_id": target["user_id"], "org_id": org_id})
    if existing and existing.get("active"):
        raise HTTPException(status_code=400, detail="L'utente è già associato a questa organizzazione")
    if existing:
        await db.memberships.update_one({"id": existing["id"]}, {"$set": {"active": True, "role": role, "updated_at": now_iso()}})
    else:
        await _ensure_membership(target["user_id"], org_id, role, user["user_id"])
    await record_audit(user, "member_added", org_id=org_id, org_name=org.get("nome"),
                       target_email=email, target_name=target.get("name"), detail=f"Ruolo: {ORG_ROLE_LABELS[role]}")
    return {"ok": True}


@api.patch("/platform/organizations/{org_id}/members/{target_id}")
async def update_org_member(org_id: str, target_id: str, body: MemberUpdateIn, user: dict = Depends(get_current_user)):
    await _require_manage(user, org_id)
    org = await _org_or_404(org_id)
    m = await db.memberships.find_one({"org_id": org_id, "user_id": target_id})
    if not m:
        raise HTTPException(status_code=404, detail="Associazione non trovata")
    tgt = await db.users.find_one({"user_id": target_id}, {"_id": 0})
    upd, changes, action = {}, [], None
    if body.role and _norm_role(body.role) != m["role"]:
        new_role = _norm_role(body.role)
        if m["role"] == "admin_org" and new_role != "admin_org":
            await _guard_last_admin(org, target_id)
        upd["role"] = new_role; changes.append(f"ruolo: {ORG_ROLE_LABELS[m['role']]} → {ORG_ROLE_LABELS[new_role]}"); action = "member_role_changed"
    if body.active is not None and body.active != m.get("active", True):
        if not body.active and m["role"] == "admin_org":
            await _guard_last_admin(org, target_id)
        upd["active"] = body.active; changes.append(f"accesso: {'attivo' if body.active else 'disabilitato'}")
        action = action or ("member_enabled" if body.active else "member_disabled")
    if upd:
        upd["updated_at"] = now_iso()
        await db.memberships.update_one({"id": m["id"]}, {"$set": upd})
        await record_audit(user, action, org_id=org_id, org_name=org.get("nome"),
                           target_email=(tgt or {}).get("email"), target_name=(tgt or {}).get("name"),
                           detail="; ".join(changes))
    return {"ok": True}


@api.delete("/platform/organizations/{org_id}/members/{target_id}")
async def remove_org_member(org_id: str, target_id: str, user: dict = Depends(get_current_user)):
    await _require_manage(user, org_id)
    org = await _org_or_404(org_id)
    m = await db.memberships.find_one({"org_id": org_id, "user_id": target_id})
    if not m:
        raise HTTPException(status_code=404, detail="Associazione non trovata")
    if m["role"] == "admin_org" and m.get("active", True):
        await _guard_last_admin(org, target_id)
    tgt = await db.users.find_one({"user_id": target_id}, {"_id": 0})
    await db.memberships.delete_one({"id": m["id"]})
    await record_audit(user, "member_removed", org_id=org_id, org_name=org.get("nome"),
                       target_email=(tgt or {}).get("email"), target_name=(tgt or {}).get("name"),
                       detail="Associazione rimossa · dati dell'organizzazione conservati")
    return {"ok": True}


# ---------------- platform: account & org management (superadmin) ----------------
# Collections whose documents belong EXCLUSIVELY to a single organization (org_id scoped).
ORG_CASCADE_COLLECTIONS = ["events", "companies", "persons", "deals", "staff", "teams", "shifts",
                           "event_maps", "activities", "followups", "calendar_event_links", "files",
                           "person_companies", "lodgings", "meals", "briefing_versions", "invoices",
                           "structures", "fic_settings", "org_invites", "leads", "memberships"]
ROLE_LABELS_USER = {"superadmin": "Super Admin", "admin": "Admin Organizzazione",
                    "member": "Utente", "staff": "Staff", "volunteer": "Volontario"}


async def _blocking_admin_orgs(user_id: str) -> list:
    """Client orgs where this user is the ONLY active Admin Organizzazione (would be left
    without any admin). Returns list of org names — used to block disable/delete."""
    blocking = []
    mems = await db.memberships.find({"user_id": user_id, "role": "admin_org", "active": True}, {"_id": 0}).to_list(500)
    for m in mems:
        org = await db.organizations.find_one({"id": m["org_id"]}, {"_id": 0})
        if not org or org.get("type") != "cliente":
            continue
        others = await db.memberships.count_documents(
            {"org_id": m["org_id"], "role": "admin_org", "active": True, "user_id": {"$ne": user_id}})
        if others == 0:
            blocking.append(org.get("nome") or m["org_id"])
    return blocking


async def _user_row(u: dict) -> dict:
    mems = await db.memberships.find({"user_id": u["user_id"]}, {"_id": 0}).to_list(200)
    org_names = []
    memberships = []
    for m in mems:
        o = await db.organizations.find_one({"id": m["org_id"]}, {"_id": 0, "nome": 1, "id": 1})
        memberships.append({"org_id": m["org_id"], "org_nome": (o or {}).get("nome"),
                            "role": m.get("role"), "active": m.get("active", True)})
        if o:
            org_names.append(o.get("nome"))
    primary = None
    if u.get("org_id"):
        po = await db.organizations.find_one({"id": u["org_id"]}, {"_id": 0, "nome": 1, "id": 1})
        primary = {"id": u["org_id"], "nome": (po or {}).get("nome")} if po else None
    return {"user_id": u["user_id"], "name": u.get("name"), "email": u.get("email"),
            "role": u.get("role"), "role_label": ROLE_LABELS_USER.get(u.get("role"), u.get("role")),
            "active": u.get("active", True), "created_at": u.get("created_at"),
            "last_login_at": u.get("last_login_at"), "auth_provider": u.get("auth_provider"),
            "person_id": u.get("person_id"), "primary_org": primary,
            "org_names": sorted(set(n for n in org_names if n)), "memberships": memberships,
            "is_superadmin": u.get("role") == "superadmin"}


@api.get("/platform/users")
async def platform_users(q: Optional[str] = None, admin: dict = Depends(require_superadmin)):
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(10000)
    rows = [await _user_row(u) for u in users]
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in (r.get("email") or "").lower() or ql in (r.get("name") or "").lower()]
    return rows


class UserUpdateIn(BaseModel):
    active: bool


@api.patch("/platform/users/{user_id}")
async def platform_user_update(user_id: str, body: UserUpdateIn, admin: dict = Depends(require_superadmin)):
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not u:
        raise HTTPException(status_code=404, detail="Account non trovato")
    if u.get("role") == "superadmin":
        raise HTTPException(status_code=400, detail="L'account Super Admin non può essere disabilitato")
    if not body.active:
        blocking = await _blocking_admin_orgs(user_id)
        if blocking:
            raise HTTPException(status_code=400, detail=f"È l'unico Admin Organizzazione di: {', '.join(blocking)}. Assegna un altro Admin prima di disabilitare l'account.")
    await db.users.update_one({"user_id": user_id}, {"$set": {"active": body.active, "updated_at": now_iso()}})
    await record_audit(admin, "account_enabled" if body.active else "account_disabled",
                       org_id=u.get("org_id"), target_email=u.get("email"), target_name=u.get("name"),
                       detail="Accesso " + ("riattivato" if body.active else "disabilitato"))
    return {"ok": True}


@api.delete("/platform/users/{user_id}")
async def platform_user_delete(user_id: str, admin: dict = Depends(require_superadmin)):
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not u:
        raise HTTPException(status_code=404, detail="Account non trovato")
    if u.get("role") == "superadmin":
        raise HTTPException(status_code=400, detail="L'account Super Admin non può essere eliminato")
    if user_id == admin.get("user_id"):
        raise HTTPException(status_code=400, detail="Non puoi eliminare il tuo stesso account")
    blocking = await _blocking_admin_orgs(user_id)
    if blocking:
        raise HTTPException(status_code=400, detail=f"È l'unico Admin Organizzazione di: {', '.join(blocking)}. Assegna il ruolo Admin Organizzazione a un altro account prima di eliminare questo.")
    # Preserve organization data. Only the login account and its personal links are removed.
    await db.memberships.delete_many({"user_id": user_id})
    await db.organizations.update_many({"owner_user_id": user_id}, {"$set": {"owner_user_id": None, "updated_at": now_iso()}})
    # Keep the Persona anagraphic — only unlink it from the deleted login account.
    if u.get("person_id"):
        await db.persons.update_one({"id": u["person_id"]},
                                    {"$set": {"invite_status": None, "user_role": None, "updated_at": now_iso()}})
    for coll in ("user_sessions", "password_reset_tokens", "calendar_connections", "calendar_event_links"):
        await db[coll].delete_many({"user_id": user_id})
    await db.users.delete_one({"user_id": user_id})
    await record_audit(admin, "account_deleted", org_id=u.get("org_id"),
                       target_email=u.get("email"), target_name=u.get("name"),
                       detail="Account eliminato · anagrafica Persona e dati organizzazione conservati")
    return {"ok": True}


class OrgDeleteIn(BaseModel):
    confirm_name: str


@api.delete("/platform/organizations/{org_id}")
async def platform_org_delete(org_id: str, body: OrgDeleteIn, admin: dict = Depends(require_superadmin)):
    org = await _org_or_404(org_id)
    if (body.confirm_name or "").strip() != (org.get("nome") or "").strip():
        raise HTTPException(status_code=400, detail="Il nome digitato non corrisponde al nome dell'organizzazione")
    counts = {}
    for coll in ORG_CASCADE_COLLECTIONS:
        res = await db[coll].delete_many({"org_id": org_id})
        if res.deleted_count:
            counts[coll] = res.deleted_count
    # settings are keyed by id == org_id
    await db.settings.delete_many({"id": org_id})
    # Org-specific accounts (staff/volunteer) exist only within this org → remove them.
    sv = await db.users.delete_many({"org_id": org_id, "role": {"$in": ["staff", "volunteer"]}})
    if sv.deleted_count:
        counts["users_staff_volontari"] = sv.deleted_count
    # Other accounts: detach from this org without deleting the account.
    await db.users.update_many({"org_id": org_id, "role": {"$nin": ["staff", "volunteer"]}},
                               {"$set": {"org_id": None, "updated_at": now_iso()}})
    await db.organizations.delete_one({"id": org_id})
    await record_audit(admin, "org_deleted", org_id=org_id, org_name=org.get("nome"),
                       detail="Eliminazione definitiva · " + (", ".join(f"{k}: {v}" for k, v in counts.items()) or "nessun dato collegato"))
    return {"ok": True, "counts": counts}


class SeedDemoIn(BaseModel):
    wipe: bool = False


@api.post("/platform/organizations/{org_id}/seed-demo")
async def platform_seed_demo(org_id: str, body: SeedDemoIn, admin: dict = Depends(require_superadmin)):
    org = await _org_or_404(org_id)
    if org.get("type") != "test":
        raise HTTPException(status_code=400, detail="Il popolamento del dataset Demo è consentito SOLO su organizzazioni di tipo Test.")
    import seed_demo
    seed_demo.db = db  # inject the running server DB handle (same isolation, org_id scoped)
    if body.wipe:
        await seed_demo.wipe(org_id)
    await seed_demo.seed(org_id)
    counts = await seed_demo.report_counts(org_id)
    await record_audit(admin, "demo_seeded", org_id=org_id, org_name=org.get("nome"),
                       detail=("Ripristino (wipe+seed)" if body.wipe else "Popolamento") + f" · {sum(counts.values())} record demo")
    return {"ok": True, "counts": counts, "wiped": body.wipe}


# ------- Brevo integration (connection check only — no email/campaign is ever sent here) -------
@api.get("/integrations/brevo/check")
async def brevo_connection_check(admin: dict = Depends(require_superadmin)):
    """Validate the Brevo API key (GET /v3/account). Backend-only, superadmin-only.
    Reads BREVO_API_KEY from the environment; the key is never returned, logged, or stored,
    and NO email/campaign is sent. Only a safe {configured, valid, status, message} is returned."""
    key = os.environ.get("BREVO_API_KEY", "").strip()
    if not key:
        return {"configured": False, "valid": False, "status": None,
                "message": "BREVO_API_KEY non configurata. Inseriscila nei Secrets di produzione."}
    try:
        async with httpx.AsyncClient(base_url="https://api.brevo.com",
                                     timeout=httpx.Timeout(10.0, connect=5.0),
                                     follow_redirects=False) as client:
            resp = await client.get("/v3/account", headers={"api-key": key})
    except httpx.TimeoutException:
        return {"configured": True, "valid": False, "status": None, "message": "Timeout nella richiesta a Brevo"}
    except httpx.HTTPError:
        return {"configured": True, "valid": False, "status": None, "message": "Impossibile raggiungere Brevo"}
    sc = resp.status_code
    if sc == 200:
        # Do NOT expose Brevo's account payload; return only a safe confirmation.
        return {"configured": True, "valid": True, "status": 200, "message": "Chiave API Brevo valida: connessione riuscita."}
    if sc == 401:
        return {"configured": True, "valid": False, "status": 401, "message": "Chiave API Brevo non valida o mancante."}
    if sc == 403:
        return {"configured": True, "valid": False, "status": 403, "message": "Brevo ha rifiutato la richiesta: verifica IP security o permessi della chiave."}
    if sc == 429:
        return {"configured": True, "valid": False, "status": 429, "message": "Limite di rate Brevo raggiunto: riprova più tardi."}
    logger.warning("Brevo check: risposta inattesa status=%s", sc)
    return {"configured": True, "valid": False, "status": sc, "message": "Brevo ha restituito un errore inatteso."}


@api.get("/integrations/brevo/senders")
async def brevo_list_senders(admin: dict = Depends(require_superadmin)):
    """List Brevo account senders (GET /v3/senders), superadmin-only.
    Returns a safe normalized view: name, email, active (verified/usable), email domain.
    The API key is never returned or logged; no email is sent."""
    key = os.environ.get("BREVO_API_KEY", "").strip()
    if not key:
        return {"configured": False, "senders": [], "message": "BREVO_API_KEY non configurata. Inseriscila nei Secrets di produzione."}
    try:
        async with httpx.AsyncClient(base_url="https://api.brevo.com",
                                     timeout=httpx.Timeout(10.0, connect=5.0),
                                     follow_redirects=False) as client:
            resp = await client.get("/v3/senders", headers={"api-key": key})
    except httpx.TimeoutException:
        return {"configured": True, "senders": [], "message": "Timeout nella richiesta a Brevo"}
    except httpx.HTTPError:
        return {"configured": True, "senders": [], "message": "Impossibile raggiungere Brevo"}
    if resp.status_code != 200:
        logger.warning("Brevo senders: risposta inattesa status=%s", resp.status_code)
        return {"configured": True, "senders": [], "message": f"Brevo ha restituito un errore (HTTP {resp.status_code})."}
    raw = resp.json().get("senders", []) or []
    senders = [{
        "id": s.get("id"),
        "name": s.get("name"),
        "email": s.get("email"),
        "active": bool(s.get("active")),
        "domain": (s.get("email") or "").rsplit("@", 1)[-1].lower() if s.get("email") else None,
    } for s in raw]
    return {"configured": True, "senders": senders, "message": "OK"}


class BrevoTestEmail(BaseModel):
    to: EmailStr
    sender_email: EmailStr
    sender_name: str = "CRMEvent"
    subject: str = "CRMEvent · Test collegamento Brevo"
    content: str = ("CRMEvent è correttamente collegato a Brevo.\n"
                    "Questa è un'email di test inviata tramite l'integrazione API CRMEvent → Brevo.")


@api.post("/integrations/brevo/send-test")
async def brevo_send_test(body: BrevoTestEmail, admin: dict = Depends(require_superadmin)):
    """Send a single transactional test email via Brevo (POST /v3/smtp/email), superadmin-only.
    Returns {success, status, messageId, timestamp, message}. The API key is never exposed."""
    key = os.environ.get("BREVO_API_KEY", "").strip()
    ts = datetime.now(timezone.utc).isoformat()
    if not key:
        return {"success": False, "status": None, "messageId": None, "timestamp": ts,
                "message": "BREVO_API_KEY non configurata. Inseriscila nei Secrets di produzione."}
    text = body.content
    html = "<p>" + text.replace("\n", "<br>") + "</p>"
    payload = {
        "sender": {"email": str(body.sender_email), "name": body.sender_name},
        "to": [{"email": str(body.to)}],
        "subject": body.subject,
        "textContent": text,
        "htmlContent": html,
    }
    try:
        async with httpx.AsyncClient(base_url="https://api.brevo.com",
                                     timeout=httpx.Timeout(15.0, connect=5.0),
                                     follow_redirects=False) as client:
            resp = await client.post("/v3/smtp/email",
                                     headers={"api-key": key, "Content-Type": "application/json"},
                                     json=payload)
    except httpx.TimeoutException:
        return {"success": False, "status": None, "messageId": None, "timestamp": ts, "message": "Timeout nella richiesta a Brevo"}
    except httpx.HTTPError:
        return {"success": False, "status": None, "messageId": None, "timestamp": ts, "message": "Impossibile raggiungere Brevo"}
    sc = resp.status_code
    if sc == 201:
        mid = None
        try:
            mid = resp.json().get("messageId")
        except Exception:
            pass
        return {"success": True, "status": 201, "messageId": mid, "timestamp": ts,
                "message": "Email di test inviata correttamente."}
    detail = None
    try:
        j = resp.json()
        detail = j.get("message") or j.get("code")
    except Exception:
        pass
    logger.warning("Brevo send-test: errore status=%s code=%s", sc, detail)
    friendly = {
        400: f"Richiesta rifiutata da Brevo: {detail or 'dati non validi'}. Verifica che il mittente sia verificato.",
        401: "Chiave API Brevo non valida o mancante.",
        403: "Brevo ha rifiutato la richiesta: verifica IP security o permessi della chiave.",
        429: "Limite di rate Brevo raggiunto: riprova più tardi.",
    }.get(sc, f"Brevo ha restituito un errore (HTTP {sc}){': ' + detail if detail else ''}.")
    return {"success": False, "status": sc, "messageId": None, "timestamp": ts, "message": friendly}


# ==================== Brevo Demo Funnel (email automation) ====================
# CRMEvent is the source of truth for lead/funnel state. Brevo handles contacts, delivery, stats.
BREVO_WEBHOOK_TOKEN = os.environ.get("BREVO_WEBHOOK_TOKEN", "")
WEBHOOK_CRON_SECRET = os.environ.get("WEBHOOK_CRON_SECRET", "")
BACKEND_PUBLIC_URL = os.environ.get("BACKEND_PUBLIC_URL") or APP_URL
PUBLIC_SITE_URL = "https://crmevent.it"
DEMO_URL = f"{PUBLIC_SITE_URL}/demo"
TRIAL_URL = f"{PUBLIC_SITE_URL}/registrati"


async def _get_setting(key: str, default=None):
    doc = await db.settings.find_one({"key": key}, {"_id": 0})
    return doc["value"] if doc else default


async def _set_setting(key: str, value):
    await db.settings.update_one({"key": key}, {"$set": {"key": key, "value": value, "updated_at": now_iso()}}, upsert=True)


async def _lead_list_id(create: bool = True):
    """Return the Brevo 'CRMEvent · Lead' list id, cached in settings. Creates it if missing."""
    lid = await _get_setting("brevo_lead_list_id")
    if lid:
        return lid
    if not (create and brevo_funnel.is_configured()):
        return None
    res = await brevo_funnel.ensure_list()
    if res.get("id"):
        await _set_setting("brevo_lead_list_id", res["id"])
        await _set_setting("brevo_lead_list_name", res.get("name") or brevo_funnel.LIST_NAME)
        return res["id"]
    return None


async def _sync_brevo_funnel_status(email: str, funnel_status: str):
    """Best-effort: keep the Brevo contact's FUNNEL_STATUS aligned with CRMEvent (source of truth)."""
    if not email:
        return
    try:
        lid = await _lead_list_id(create=False)
        await brevo_funnel.upsert_contact(email=email, funnel_status=funnel_status,
                                          list_ids=([lid] if lid else None))
    except Exception as e:
        logger.error(f"brevo funnel_status sync failed: {e}")


async def _get_demo_funnel() -> dict:
    f = await db.email_funnels.find_one({"key": brevo_funnel.FUNNEL_KEY}, {"_id": 0})
    if not f:
        f = {"id": new_id(), "key": brevo_funnel.FUNNEL_KEY, "name": brevo_funnel.FUNNEL_NAME,
             "status": "draft", "created_at": now_iso(), "updated_at": now_iso()}
        await db.email_funnels.insert_one(dict(f))
    return f


async def _template_map() -> dict:
    rows = await db.brevo_templates.find({}, {"_id": 0}).to_list(50)
    return {r["template_key"]: r["brevo_id"] for r in rows if r.get("brevo_id")}


async def _lead_unsub_url(lead: dict) -> str:
    token = lead.get("unsub_token")
    if not token:
        token = secrets.token_urlsafe(24)
        await db.leads.update_one({"id": lead["id"]}, {"$set": {"unsub_token": token}})
        lead["unsub_token"] = token
    return f"{BACKEND_PUBLIC_URL}/api/brevo/unsubscribe?token={token}"


async def _send_params(lead: dict) -> dict:
    return {"NOME": lead.get("nome") or "", "DEMO_URL": DEMO_URL, "TRIAL_URL": TRIAL_URL,
            "UNSUB_URL": await _lead_unsub_url(lead)}


def _stop_reason(lead: dict):
    if lead.get("marketing_opt_out"):
        return "unsubscribed"
    if lead.get("email_bounced"):
        return "hard_bounce"
    if lead.get("email_spam"):
        return "spam"
    if lead.get("funnel_status") in brevo_funnel.STOP_FUNNEL_STATUSES:
        return lead.get("funnel_status")
    if lead.get("user_id"):
        # Lead converted to an account → must never receive demo nurture (defense in depth).
        return "trial_started"
    return None


async def _cancel_enrollment(enr: dict, reason: str):
    steps = enr.get("steps", [])
    for s in steps:
        if s["status"] == "scheduled":
            s["status"] = "canceled"
    await db.funnel_enrollments.update_one({"id": enr["id"]}, {"$set": {
        "status": "stopped", "stop_reason": reason, "steps": steps,
        "stopped_at": now_iso(), "updated_at": now_iso()}})


async def _stop_active_demo_enrollment(lead_id: str, reason: str):
    """Immediately close the active demo enrollment for a lead (idempotent: only acts if active)."""
    enr = await db.funnel_enrollments.find_one(
        {"funnel_key": brevo_funnel.FUNNEL_KEY, "lead_id": lead_id, "status": "active"}, {"_id": 0})
    if enr:
        await _cancel_enrollment(enr, reason)


async def _send_step(lead: dict, step_cfg: dict, tmpl_map: dict) -> dict:
    tid = tmpl_map.get(step_cfg["template_key"])
    if not tid:
        return {"ok": False, "error": "Template non sincronizzato su Brevo", "status": None, "messageId": None}
    params = await _send_params(lead)
    res = await brevo_funnel.send_template(template_id=tid, to_email=lead["email"],
                                           to_name=(lead.get("nome") or None), params=params)
    return res


async def _enroll_lead(lead: dict):
    """Enroll a fresh lead into the demo funnel: send EMAIL 1 immediately, schedule EMAIL 2-4.
    Only runs when the funnel is ACTIVE and the lead is contactable. Never duplicates."""
    funnel = await _get_demo_funnel()
    if funnel.get("status") != "active":
        return {"enrolled": False, "reason": "funnel_not_active"}
    if _stop_reason(lead):
        return {"enrolled": False, "reason": "not_contactable"}
    existing = await db.funnel_enrollments.find_one({"funnel_key": brevo_funnel.FUNNEL_KEY, "lead_id": lead["id"]})
    if existing:
        return {"enrolled": False, "reason": "already_enrolled"}
    tmpl_map = await _template_map()
    if not tmpl_map.get("demo_1"):
        return {"enrolled": False, "reason": "templates_not_synced"}
    entered = datetime.now(timezone.utc)
    steps = []
    for cfg in brevo_funnel.FUNNEL_STEPS:
        steps.append({"step": cfg["step"], "template_key": cfg["template_key"],
                      "scheduled_at": (entered + timedelta(days=cfg["delay_days"])).isoformat(),
                      "sent_at": None, "status": "scheduled", "brevo_message_id": None, "error": None})
    enr = {"id": new_id(), "funnel_key": brevo_funnel.FUNNEL_KEY, "lead_id": lead["id"],
           "email": lead["email"], "status": "active", "stop_reason": None,
           "entered_at": entered.isoformat(), "steps": steps,
           "created_at": now_iso(), "updated_at": now_iso()}
    # Send EMAIL 1 immediately.
    res = await _send_step(lead, brevo_funnel.FUNNEL_STEPS[0], tmpl_map)
    steps[0]["status"] = "sent" if res.get("ok") else "failed"
    steps[0]["sent_at"] = now_iso()
    steps[0]["brevo_message_id"] = res.get("messageId")
    steps[0]["error"] = None if res.get("ok") else res.get("error")
    await db.funnel_enrollments.insert_one(dict(enr))
    return {"enrolled": True, "email1_ok": res.get("ok"), "error": res.get("error")}


async def process_due_funnel_steps() -> dict:
    """Cron worker: re-checks stop conditions before EVERY send. Idempotent."""
    funnel = await _get_demo_funnel()
    if funnel.get("status") != "active":
        return {"processed": 0, "reason": "funnel_not_active"}
    tmpl_map = await _template_map()
    now = datetime.now(timezone.utc)
    processed = 0
    stopped = 0
    cursor = db.funnel_enrollments.find({"funnel_key": brevo_funnel.FUNNEL_KEY, "status": "active"}, {"_id": 0})
    enrollments = await cursor.to_list(5000)
    for enr in enrollments:
        lead = await db.leads.find_one({"id": enr["lead_id"]}, {"_id": 0})
        if not lead:
            await db.funnel_enrollments.update_one({"id": enr["id"]},
                {"$set": {"status": "stopped", "stop_reason": "lead_deleted", "updated_at": now_iso()}})
            continue
        reason = _stop_reason(lead)
        if reason:
            await _cancel_enrollment(enr, reason)
            stopped += 1
            continue
        steps = enr["steps"]
        changed = False
        for cfg in brevo_funnel.FUNNEL_STEPS:
            s = next((x for x in steps if x["step"] == cfg["step"]), None)
            if not s or s["status"] != "scheduled":
                continue
            if datetime.fromisoformat(s["scheduled_at"]) > now:
                continue
            # Re-check stop conditions immediately before this send.
            reason = _stop_reason(lead)
            if reason:
                await _cancel_enrollment(enr, reason)
                stopped += 1
                changed = False
                break
            res = await _send_step(lead, cfg, tmpl_map)
            s["status"] = "sent" if res.get("ok") else "failed"
            s["sent_at"] = now_iso()
            s["brevo_message_id"] = res.get("messageId")
            s["error"] = None if res.get("ok") else res.get("error")
            processed += 1
            changed = True
        if changed:
            all_done = all(x["status"] != "scheduled" for x in steps)
            upd = {"steps": steps, "updated_at": now_iso()}
            if all_done:
                upd["status"] = "completed"
            await db.funnel_enrollments.update_one({"id": enr["id"]}, {"$set": upd})
    return {"processed": processed, "stopped": stopped, "enrollments": len(enrollments)}


async def _funnel_stats() -> dict:
    leads_total = await db.leads.count_documents({})
    demo_requested = await db.leads.count_documents({"funnel_ts_demo_requested": {"$exists": True}})
    demo_started = await db.leads.count_documents({"$or": [
        {"funnel_ts_demo_started": {"$exists": True}},
        {"funnel_status": {"$in": ["demo_started", "demo_completed", "trial_started", "cliente"]}}]})
    trial_started = await db.leads.count_documents({"$or": [
        {"funnel_ts_trial_started": {"$exists": True}}, {"funnel_status": "trial_started"}]})
    clienti = await db.leads.count_documents({"funnel_status": "cliente"})
    enrolled = await db.funnel_enrollments.count_documents({"funnel_key": brevo_funnel.FUNNEL_KEY})
    # Emails sent from enrollment step records.
    emails_sent = 0
    async for e in db.funnel_enrollments.find({"funnel_key": brevo_funnel.FUNNEL_KEY}, {"_id": 0, "steps": 1}):
        emails_sent += sum(1 for s in e.get("steps", []) if s.get("status") == "sent")
    ev = {}
    for name in ["delivered", "opened", "clicked", "hard_bounce", "unsubscribed", "spam"]:
        ev[name] = await db.brevo_events.count_documents({"event": name})
    return {"lead_entrati": enrolled, "demo_richieste": demo_requested, "demo_avviate": demo_started,
            "trial_avviati": trial_started, "clienti": clienti, "lead_totali": leads_total,
            "email_inviate": emails_sent, "email_consegnate": ev["delivered"], "aperture": ev["opened"],
            "click": ev["clicked"], "bounce": ev["hard_bounce"], "unsubscribe": ev["unsubscribed"],
            "spam": ev["spam"]}


@api.get("/platform/funnels")
async def list_funnels(admin: dict = Depends(require_superadmin)):
    funnel = await _get_demo_funnel()
    tmpl_map = await _template_map()
    stats = await _funnel_stats()
    return [{"key": funnel["key"], "name": funnel["name"], "status": funnel["status"],
             "templates_synced": bool(tmpl_map.get("demo_1")), "brevo_configured": brevo_funnel.is_configured(),
             "stats": stats}]


@api.get("/platform/funnels/{key}")
async def get_funnel(key: str, admin: dict = Depends(require_superadmin)):
    if key != brevo_funnel.FUNNEL_KEY:
        raise HTTPException(status_code=404, detail="Funnel non trovato")
    funnel = await _get_demo_funnel()
    tmpl_map = await _template_map()
    steps = [{"step": c["step"], "template_key": c["template_key"], "name": c["name"],
              "subject": c["subject"], "delay_days": c["delay_days"],
              "timing": ("Immediata" if c["delay_days"] == 0 else f"+{c['delay_days']} giorni"),
              "require_not_engaged": c["require_not_engaged"],
              "brevo_template_id": tmpl_map.get(c["template_key"]),
              "synced": bool(tmpl_map.get(c["template_key"]))} for c in brevo_funnel.FUNNEL_STEPS]
    lead_list_id = await _get_setting("brevo_lead_list_id")
    lead_list_name = await _get_setting("brevo_lead_list_name") or brevo_funnel.LIST_NAME
    return {"key": funnel["key"], "name": funnel["name"], "status": funnel["status"],
            "brevo_configured": brevo_funnel.is_configured(),
            "templates_synced": all(s["synced"] for s in steps),
            "sender": brevo_funnel.SENDER, "demo_url": DEMO_URL, "trial_url": TRIAL_URL,
            "lead_list": {"id": lead_list_id, "name": lead_list_name, "configured": bool(lead_list_id)},
            "stop_conditions": ["Prova gratuita avviata (trial_started)", "Diventa cliente",
                                "Disiscrizione", "Hard bounce", "Spam complaint"],
            "steps": steps, "stats": await _funnel_stats()}


class FunnelStatusIn(BaseModel):
    status: str


@api.post("/platform/funnels/{key}/status")
async def set_funnel_status(key: str, body: FunnelStatusIn, admin: dict = Depends(require_superadmin)):
    if key != brevo_funnel.FUNNEL_KEY:
        raise HTTPException(status_code=404, detail="Funnel non trovato")
    if body.status not in {"draft", "active", "paused"}:
        raise HTTPException(status_code=400, detail="Stato non valido")
    await _get_demo_funnel()
    if body.status == "active":
        tmpl_map = await _template_map()
        if not brevo_funnel.is_configured():
            raise HTTPException(status_code=400, detail="Brevo non configurato: impossibile attivare.")
        if not tmpl_map.get("demo_1"):
            raise HTTPException(status_code=400, detail="Sincronizza prima i template su Brevo.")
    await db.email_funnels.update_one({"key": key}, {"$set": {"status": body.status, "updated_at": now_iso()}})
    await record_audit(admin, "funnel_status", detail=f"Funnel {key} impostato su {body.status}")
    return {"ok": True, "status": body.status}


@api.post("/platform/funnels/{key}/reconcile")
async def reconcile_funnel(key: str, admin: dict = Depends(require_superadmin)):
    """Close any active enrollment whose lead now meets a stop condition (trial/cliente/converted/
    unsubscribe/bounce/spam). Sends NO email. Works regardless of the funnel's draft/active status."""
    if key != brevo_funnel.FUNNEL_KEY:
        raise HTTPException(status_code=404, detail="Funnel non trovato")
    enrollments = await db.funnel_enrollments.find(
        {"funnel_key": key, "status": "active"}, {"_id": 0}).to_list(5000)
    closed = 0
    for enr in enrollments:
        lead = await db.leads.find_one({"id": enr["lead_id"]}, {"_id": 0})
        if not lead:
            await _cancel_enrollment(enr, "lead_deleted")
            closed += 1
            continue
        reason = _stop_reason(lead)
        if reason:
            # Normalise a converted lead's funnel_status so the UI shows the correct reason.
            if lead.get("user_id") and lead.get("funnel_status") not in brevo_funnel.STOP_FUNNEL_STATUSES:
                await db.leads.update_one({"id": lead["id"]}, {"$set": {
                    "funnel_status": "trial_started",
                    "funnel_ts_trial_started": lead.get("funnel_ts_trial_started") or now_iso(),
                    "updated_at": now_iso()}})
            await _cancel_enrollment(enr, reason)
            closed += 1
    return {"ok": True, "active_before": len(enrollments), "closed": closed}


@api.post("/platform/funnels/{key}/sync-templates")
async def sync_funnel_templates(key: str, force: bool = False, admin: dict = Depends(require_superadmin)):
    if key != brevo_funnel.FUNNEL_KEY:
        raise HTTPException(status_code=404, detail="Funnel non trovato")
    if not brevo_funnel.is_configured():
        raise HTTPException(status_code=400, detail="BREVO_API_KEY non configurata.")
    await brevo_funnel.ensure_attributes()
    results = []
    for cfg in brevo_funnel.FUNNEL_STEPS:
        existing = await db.brevo_templates.find_one({"template_key": cfg["template_key"]}, {"_id": 0})
        res = await brevo_funnel.create_or_update_template(cfg, existing_id=(existing or {}).get("brevo_id"), force=force)
        if res.get("ok") and res.get("id"):
            await db.brevo_templates.update_one({"template_key": cfg["template_key"]},
                {"$set": {"template_key": cfg["template_key"], "brevo_id": res["id"], "name": cfg["name"],
                          "subject": cfg["subject"], "updated_at": now_iso()}}, upsert=True)
        results.append({"template_key": cfg["template_key"], "name": cfg["name"],
                        "brevo_template_id": res.get("id"), "ok": res.get("ok"),
                        "created": res.get("created"), "error": res.get("error")})
    ok = all(r["ok"] for r in results)
    return {"ok": ok, "results": results}


@api.post("/platform/funnels/{key}/register-webhook")
async def register_funnel_webhook(key: str, admin: dict = Depends(require_superadmin)):
    """Register the Brevo transactional webhook server-side. The secret token is read from
    the environment and embedded in the callback URL; it is NEVER returned to the frontend."""
    if key != brevo_funnel.FUNNEL_KEY:
        raise HTTPException(status_code=404, detail="Funnel non trovato")
    if not brevo_funnel.is_configured():
        raise HTTPException(status_code=400, detail="BREVO_API_KEY non configurata.")
    if not BREVO_WEBHOOK_TOKEN:
        raise HTTPException(status_code=400, detail="BREVO_WEBHOOK_TOKEN non configurato nei Secrets.")
    callback = f"{BACKEND_PUBLIC_URL}/api/brevo/webhook/{BREVO_WEBHOOK_TOKEN}"
    res = await brevo_funnel.register_webhook(callback)
    await record_audit(admin, "funnel_webhook", detail=f"Registrazione webhook Brevo ({'ok' if res.get('ok') else 'errore'})")
    # Do NOT return the callback URL (it contains the secret token).
    return {"ok": res.get("ok"), "webhook_id": res.get("id"), "created": res.get("created"),
            "error": res.get("error")}


@api.post("/platform/funnels/{key}/ensure-list")
async def ensure_funnel_list(key: str, admin: dict = Depends(require_superadmin)):
    """Find or create the Brevo 'CRMEvent · Lead' list and cache its id in CRMEvent."""
    if key != brevo_funnel.FUNNEL_KEY:
        raise HTTPException(status_code=404, detail="Funnel non trovato")
    if not brevo_funnel.is_configured():
        raise HTTPException(status_code=400, detail="BREVO_API_KEY non configurata.")
    res = await brevo_funnel.ensure_list()
    if res.get("id"):
        await _set_setting("brevo_lead_list_id", res["id"])
        await _set_setting("brevo_lead_list_name", res.get("name") or brevo_funnel.LIST_NAME)
    return {"ok": res.get("ok"), "list_id": res.get("id"), "name": res.get("name"),
            "created": res.get("created"), "error": res.get("error")}


class FunnelTestIn(BaseModel):
    email: EmailStr


@api.post("/platform/funnels/{key}/test")
async def test_funnel(key: str, body: FunnelTestIn, admin: dict = Depends(require_superadmin)):
    """Send all funnel emails immediately to a test address WITHOUT touching real leads or waiting."""
    if key != brevo_funnel.FUNNEL_KEY:
        raise HTTPException(status_code=404, detail="Funnel non trovato")
    if not brevo_funnel.is_configured():
        raise HTTPException(status_code=400, detail="BREVO_API_KEY non configurata.")
    tmpl_map = await _template_map()
    if not tmpl_map.get("demo_1"):
        raise HTTPException(status_code=400, detail="Sincronizza prima i template su Brevo.")
    params = {"NOME": "Test", "DEMO_URL": DEMO_URL, "TRIAL_URL": TRIAL_URL,
              "UNSUB_URL": f"{BACKEND_PUBLIC_URL}/api/brevo/unsubscribe?token=test"}
    results = []
    for cfg in brevo_funnel.FUNNEL_STEPS:
        tid = tmpl_map.get(cfg["template_key"])
        res = await brevo_funnel.send_template(template_id=tid, to_email=str(body.email),
                                               to_name="Test", params=params)
        results.append({"step": cfg["step"], "template_key": cfg["template_key"], "subject": cfg["subject"],
                        "ok": res.get("ok"), "status": res.get("status"),
                        "messageId": res.get("messageId"), "error": res.get("error"),
                        "timestamp": now_iso()})
    return {"ok": all(r["ok"] for r in results), "sent_to": str(body.email), "results": results}


# ---------------- Brevo webhook & unsubscribe (public) ----------------
@api.post("/brevo/webhook/{token}")
async def brevo_webhook(token: str, request: Request):
    if not BREVO_WEBHOOK_TOKEN or not secrets.compare_digest(token, BREVO_WEBHOOK_TOKEN):
        raise HTTPException(status_code=401, detail="unauthorized")
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid body")
    events = payload if isinstance(payload, list) else [payload]
    for e in events:
        if not isinstance(e, dict):
            continue
        email = (e.get("email") or "").strip().lower()
        norm = brevo_funnel.normalize_event(e.get("event", ""))
        message_id = e.get("message-id") or e.get("messageId")
        dedupe = hashlib.sha256(f"{email}|{norm}|{message_id}|{e.get('ts') or e.get('date') or ''}".encode()).hexdigest()
        existing = await db.brevo_events.find_one({"dedupe": dedupe}, {"_id": 0, "dedupe": 1})
        if existing:
            continue
        await db.brevo_events.insert_one({"id": new_id(), "dedupe": dedupe, "event": norm, "email": email,
                                          "message_id": message_id, "created_at": now_iso()})
        if not email:
            continue
        flag = None
        if norm == "unsubscribed":
            flag = {"marketing_opt_out": True}
        elif norm == "hard_bounce":
            flag = {"email_bounced": True}
        elif norm == "spam":
            flag = {"email_spam": True}
        if flag:
            await db.leads.update_many({"email": email}, {"$set": {**flag, "updated_at": now_iso()}})
            enrs = await db.funnel_enrollments.find({"email": email, "status": "active"}, {"_id": 0}).to_list(100)
            reason = "unsubscribed" if norm == "unsubscribed" else ("hard_bounce" if norm == "hard_bounce" else "spam")
            for enr in enrs:
                await _cancel_enrollment(enr, reason)
    return {"received": len(events)}


@app.get("/api/brevo/unsubscribe")
async def brevo_unsubscribe(token: str):
    page = ("<!doctype html><html lang='it'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>CRMEvent</title></head><body style='font-family:Arial,sans-serif;background:#f1f5f9;"
            "margin:0;padding:48px 16px;text-align:center'>"
            "<div style='max-width:460px;margin:0 auto;background:#fff;border:1px solid #e2e8f0;"
            "border-radius:16px;padding:32px'>"
            "<div style='height:4px;width:60px;background:#81D8D0;margin:0 auto 20px;border-radius:2px'></div>"
            "<h1 style='font-size:20px;color:#0f172a;margin:0 0 12px'>{title}</h1>"
            "<p style='color:#475569;font-size:14px;line-height:1.6;margin:0'>{msg}</p></div></body></html>")
    lead = await db.leads.find_one({"unsub_token": token}, {"_id": 0}) if token else None
    if not lead:
        from fastapi.responses import HTMLResponse
        return HTMLResponse(page.format(title="Link non valido",
                            msg="Questo link di disiscrizione non è valido o è scaduto."), status_code=404)
    await db.leads.update_one({"id": lead["id"]}, {"$set": {"marketing_opt_out": True, "updated_at": now_iso()}})
    enrs = await db.funnel_enrollments.find({"email": lead["email"], "status": "active"}, {"_id": 0}).to_list(100)
    for enr in enrs:
        await _cancel_enrollment(enr, "unsubscribed")
    try:
        await brevo_funnel.blocklist_contact(lead["email"])
    except Exception as ex:
        logger.error(f"brevo blocklist failed: {ex}")
    from fastapi.responses import HTMLResponse
    return HTMLResponse(page.format(title="Disiscrizione completata",
                        msg="Non riceverai più email marketing da CRMEvent. Puoi chiudere questa pagina."))


# ---------------- cron ----------------
@api.post("/cron/brevo-funnel-tick")
async def cron_brevo_funnel_tick(request: Request, authorization: str = Header(default="")):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    expected = f"Bearer {WEBHOOK_CRON_SECRET}"
    if not WEBHOOK_CRON_SECRET or not secrets.compare_digest(authorization or "", expected):
        raise HTTPException(status_code=401, detail="unauthorized")
    asyncio.create_task(process_due_funnel_steps())
    return {"accepted": True}


# ------- invites -------
def _invite_status(inv: dict) -> str:
    if inv.get("status") in ("accepted", "revoked"):
        return inv["status"]
    exp = inv.get("expires_at")
    if exp:
        try:
            e = datetime.fromisoformat(exp)
            if e.tzinfo is None:
                e = e.replace(tzinfo=timezone.utc)
            if e < datetime.now(timezone.utc):
                return "expired"
        except Exception:
            pass
    return "pending"


def _invite_view(inv: dict) -> dict:
    return {"id": inv["id"], "email": inv["email"], "role": inv["role"],
            "role_label": ORG_ROLE_LABELS.get(inv["role"], inv["role"]),
            "status": _invite_status(inv), "created_at": inv.get("created_at"), "expires_at": inv.get("expires_at")}


async def _send_invite_email(email: str, org_name: str, token: str, role: str) -> None:
    link = f"{APP_URL}/invito?token={token}"
    await email_utils.send_email(
        to=email, subject=f"Invito ad accedere a {org_name} su CRMEvent",
        html=email_utils.link_email(
            name=email.split("@")[0],
            intro=f"Sei stato invitato ad accedere all'organizzazione «{org_name}» su CRMEvent con il ruolo {ORG_ROLE_LABELS.get(role, role)}. Clicca per accettare l'invito e accedere.",
            cta_label="Accetta l'invito", url=link,
            footer_note="L'invito scade tra 7 giorni ed è utilizzabile una sola volta."))


async def _create_invite(org: dict, email: str, role: str, invited_by: str, lead_id: Optional[str] = None) -> dict:
    await db.org_invites.update_many({"org_id": org["id"], "email": email, "status": "pending"},
                                     {"$set": {"status": "revoked", "updated_at": now_iso()}})
    token = secrets.token_urlsafe(32)
    inv = {"id": new_id(), "org_id": org["id"], "email": email, "role": role, "token": token,
           "status": "pending", "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
           "invited_by": invited_by, "lead_id": lead_id, "created_at": now_iso(), "updated_at": now_iso()}
    await db.org_invites.insert_one(inv)
    return inv


@api.get("/platform/organizations/{org_id}/invites")
async def list_org_invites(org_id: str, user: dict = Depends(get_current_user)):
    await _require_manage(user, org_id)
    invs = await db.org_invites.find({"org_id": org_id}, {"_id": 0, "token": 0}).sort("created_at", -1).to_list(500)
    return [_invite_view(i) for i in invs]


@api.post("/platform/organizations/{org_id}/invites")
async def create_org_invite(org_id: str, body: InviteCreateIn, user: dict = Depends(get_current_user)):
    await _require_manage(user, org_id)
    org = await _org_or_404(org_id)
    email, role = body.email.lower(), _norm_role(body.role)
    eu = await db.users.find_one({"email": email}, {"_id": 0})
    if eu and await db.memberships.find_one({"user_id": eu["user_id"], "org_id": org_id, "active": True}):
        raise HTTPException(status_code=400, detail="Questo utente è già associato all'organizzazione")
    inv = await _create_invite(org, email, role, user["user_id"])
    sent = True
    try:
        await _send_invite_email(email, org.get("nome"), inv["token"], role)
    except Exception as e:
        logger.error(f"invite email failed: {e}"); sent = False
    await record_audit(user, "invite_sent", org_id=org_id, org_name=org.get("nome"),
                       target_email=email, detail=f"Ruolo: {ORG_ROLE_LABELS[role]}")
    return {"ok": True, "email_sent": sent, "id": inv["id"]}


@api.post("/platform/invites/{invite_id}/resend")
async def resend_org_invite(invite_id: str, user: dict = Depends(get_current_user)):
    inv = await db.org_invites.find_one({"id": invite_id}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Invito non trovato")
    await _require_manage(user, inv["org_id"])
    org = await _org_or_404(inv["org_id"])
    token = secrets.token_urlsafe(32)
    await db.org_invites.update_one({"id": invite_id}, {"$set": {"token": token, "status": "pending",
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(), "updated_at": now_iso()}})
    sent = True
    try:
        await _send_invite_email(inv["email"], org.get("nome"), token, inv["role"])
    except Exception as e:
        logger.error(f"invite resend failed: {e}"); sent = False
    await record_audit(user, "invite_resent", org_id=inv["org_id"], org_name=org.get("nome"), target_email=inv["email"])
    return {"ok": True, "email_sent": sent}


@api.delete("/platform/invites/{invite_id}")
async def revoke_org_invite(invite_id: str, hard: bool = False, user: dict = Depends(get_current_user)):
    inv = await db.org_invites.find_one({"id": invite_id}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Invito non trovato")
    await _require_manage(user, inv["org_id"])
    org = await db.organizations.find_one({"id": inv["org_id"]}, {"_id": 0})
    if hard:
        # Hard-delete removes the invite row entirely (cleanup). The linked account, if it already
        # accepted, is NEVER touched — only the invite record is removed.
        await db.org_invites.delete_one({"id": invite_id})
        detail = "Invito eliminato"
    else:
        await db.org_invites.update_one({"id": invite_id}, {"$set": {"status": "revoked", "updated_at": now_iso()}})
        detail = "Invito revocato"
    await record_audit(user, "invite_revoked", org_id=inv["org_id"], org_name=(org or {}).get("nome"),
                       target_email=inv["email"], detail=detail)
    return {"ok": True}


@api.post("/platform/organizations/{org_id}/invites/cleanup")
async def cleanup_org_invites(org_id: str, user: dict = Depends(get_current_user)):
    """Remove redundant/duplicate invite rows (revoked, expired, duplicate accepted, or pending
    invites for emails that already have an active membership). Never touches accounts/memberships."""
    await _require_manage(user, org_id)
    org = await _org_or_404(org_id)
    invs = await db.org_invites.find({"org_id": org_id}, {"_id": 0}).sort("created_at", -1).to_list(2000)
    by_email = {}
    for i in invs:
        by_email.setdefault(i["email"], []).append(i)
    removed = 0
    for email, items in by_email.items():
        eu = await db.users.find_one({"email": email.lower()}, {"_id": 0})
        has_member = bool(eu and await db.memberships.find_one(
            {"user_id": eu["user_id"], "org_id": org_id, "active": True}))
        accepted = [x for x in items if x.get("status") == "accepted"]
        keep_id = None
        if accepted:
            keep_id = accepted[0]["id"]  # newest accepted (list is desc by created_at)
        elif not has_member:
            pend = [x for x in items if _invite_status(x) == "pending"]
            keep_id = pend[0]["id"] if pend else items[0]["id"]
        # if has_member and no accepted -> keep_id stays None -> all redundant pending removed
        for x in items:
            if x["id"] != keep_id:
                await db.org_invites.delete_one({"id": x["id"]})
                removed += 1
    await record_audit(user, "invites_cleaned", org_id=org_id, org_name=org.get("nome"),
                       detail=f"Pulizia inviti · {removed} rimossi")
    return {"ok": True, "removed": removed}


# ------- invite acceptance (public / auth) -------
class InviteRegisterIn(BaseModel):
    name: Optional[str] = None
    password: str


async def _get_valid_invite(token: str) -> dict:
    inv = await db.org_invites.find_one({"token": token}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Invito non valido")
    st = _invite_status(inv)
    if st != "pending":
        raise HTTPException(status_code=400, detail={"expired": "Invito scaduto", "accepted": "Invito già utilizzato",
                            "revoked": "Invito revocato"}.get(st, "Invito non valido"))
    return inv


async def _accept_invite(inv: dict, target_user: dict) -> None:
    role = _norm_role(inv["role"])
    m = await db.memberships.find_one({"user_id": target_user["user_id"], "org_id": inv["org_id"]})
    if m:
        await db.memberships.update_one({"id": m["id"]}, {"$set": {"active": True, "role": role, "updated_at": now_iso()}})
    else:
        await _ensure_membership(target_user["user_id"], inv["org_id"], role, inv.get("invited_by"))
    await db.org_invites.update_one({"id": inv["id"]}, {"$set": {"status": "accepted", "accepted_at": now_iso(),
        "accepted_user_id": target_user["user_id"], "updated_at": now_iso()}})
    # Dedupe: once accepted, remove any other invite rows for the same email in this org so the
    # same account can never show up twice in the invite list (fixes duplicate accepted rows).
    await db.org_invites.delete_many({"org_id": inv["org_id"], "email": inv["email"], "id": {"$ne": inv["id"]}})
    if inv.get("lead_id"):
        await db.leads.update_one({"id": inv["lead_id"]}, {"$set": {"user_id": target_user["user_id"], "updated_at": now_iso()}})
    org = await db.organizations.find_one({"id": inv["org_id"]}, {"_id": 0})
    await record_audit(target_user, "invite_accepted", org_id=inv["org_id"], org_name=(org or {}).get("nome"),
                       target_email=target_user.get("email"), target_name=target_user.get("name"),
                       detail=f"Ruolo: {ORG_ROLE_LABELS[role]}")


@api.get("/invites/{token}")
async def get_invite(token: str):
    inv = await db.org_invites.find_one({"token": token}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Invito non valido")
    org = await db.organizations.find_one({"id": inv["org_id"]}, {"_id": 0})
    exists = bool(await db.users.find_one({"email": inv["email"].lower()}))
    return {"email": inv["email"], "role": inv["role"], "role_label": ORG_ROLE_LABELS.get(inv["role"], inv["role"]),
            "org_name": (org or {}).get("nome"), "status": _invite_status(inv), "account_exists": exists}


@api.post("/invites/{token}/register")
async def register_via_invite(token: str, body: InviteRegisterIn, response: Response):
    inv = await _get_valid_invite(token)
    email = inv["email"].lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Esiste già un account con questa email. Accedi e accetta l'invito.")
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="La password deve avere almeno 8 caratteri")
    uid = f"user_{uuid.uuid4().hex[:12]}"
    await db.users.insert_one({"user_id": uid, "email": email, "name": (body.name or email.split("@")[0]).strip(),
        "password_hash": hash_password(body.password), "role": "member", "auth_provider": "password",
        "org_id": inv["org_id"], "picture": "", "active": True, "last_login_at": now_iso(), "created_at": now_iso()})
    u = await db.users.find_one({"user_id": uid}, {"_id": 0})
    await _accept_invite(inv, u)
    tok = create_access_token(uid, email)
    set_auth_cookie(response, "access_token", tok, 7 * 24 * 3600)
    return await user_payload(u, inv["org_id"])


@api.post("/invites/{token}/accept")
async def accept_invite(token: str, user: dict = Depends(get_current_user)):
    inv = await _get_valid_invite(token)
    if (user.get("email") or "").lower() != inv["email"].lower():
        raise HTTPException(status_code=403, detail=f"L'invito è indirizzato a {inv['email']}. Accedi con quell'indirizzo email per accettarlo.")
    await _accept_invite(inv, user)
    return {"ok": True, "org_id": inv["org_id"]}


# ------- user's own organizations (active-org switcher) -------
@api.get("/my/organizations")
async def my_organizations(user: dict = Depends(get_current_user)):
    if user.get("role") == "superadmin":
        return []
    mems = await db.memberships.find({"user_id": user["user_id"], "active": True}, {"_id": 0}).to_list(200)
    out = []
    for m in mems:
        org = await db.organizations.find_one({"id": m["org_id"]}, {"_id": 0})
        if not org or org.get("status") == "disabled":
            continue
        out.append({"id": org["id"], "nome": org.get("nome"), "type": org.get("type", "cliente"), "role": m["role"]})
    return out


# ------- lead <-> user linking / org assignment -------
async def _account_for_email(email: Optional[str]) -> Optional[dict]:
    if not email:
        return None
    u = await db.users.find_one({"email": email.lower()}, {"_id": 0, "password_hash": 0})
    if not u:
        return None
    mems = await db.memberships.find({"user_id": u["user_id"]}, {"_id": 0}).to_list(200)
    orgs = []
    for m in mems:
        o = await db.organizations.find_one({"id": m["org_id"]}, {"_id": 0})
        if o:
            orgs.append({"org_id": o["id"], "nome": o.get("nome"), "role": m["role"],
                         "role_label": ORG_ROLE_LABELS.get(m["role"], m["role"]), "active": m.get("active", True)})
    return {"user_id": u["user_id"], "email": u["email"], "name": u.get("name"),
            "active": u.get("active", True), "role": u.get("role"), "organizations": orgs}


class LeadAssignIn(BaseModel):
    org_id: str
    role: str = "user"


@api.get("/leads/{lead_id}")
async def get_lead(lead_id: str, admin: dict = Depends(require_superadmin)):
    lead = await db.leads.find_one({"id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead non trovato")
    account = None
    if lead.get("user_id"):
        u = await db.users.find_one({"user_id": lead["user_id"]}, {"_id": 0})
        if u:
            account = await _account_for_email(u.get("email"))
    if not account:
        account = await _account_for_email(lead.get("email"))
    enrollment = await db.funnel_enrollments.find_one(
        {"funnel_key": brevo_funnel.FUNNEL_KEY, "lead_id": lead_id}, {"_id": 0})
    return {"lead": lead, "account": account, "linked": bool(lead.get("user_id")),
            "funnel": enrollment}


@api.post("/leads/{lead_id}/link-account")
async def link_lead_account(lead_id: str, admin: dict = Depends(require_superadmin)):
    lead = await db.leads.find_one({"id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead non trovato")
    u = await db.users.find_one({"email": (lead.get("email") or "").lower()}, {"_id": 0})
    if not u:
        raise HTTPException(status_code=404, detail="Nessun account CRMEvent con l'email del lead")
    await db.leads.update_one({"id": lead_id}, {"$set": {"user_id": u["user_id"], "updated_at": now_iso()}})
    await record_audit(admin, "lead_linked", target_email=u["email"], target_name=u.get("name"),
                       detail=f"Lead «{lead.get('nome', '')} {lead.get('cognome', '') or ''}» collegato all'account")
    return {"ok": True}


@api.post("/leads/{lead_id}/assign-org")
async def assign_lead_org(lead_id: str, body: LeadAssignIn, admin: dict = Depends(require_superadmin)):
    lead = await db.leads.find_one({"id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead non trovato")
    org = await _org_or_404(body.org_id)
    u = None
    if lead.get("user_id"):
        u = await db.users.find_one({"user_id": lead["user_id"]}, {"_id": 0})
    if not u:
        u = await db.users.find_one({"email": (lead.get("email") or "").lower()}, {"_id": 0})
    if not u:
        raise HTTPException(status_code=404, detail="Nessun account CRMEvent per questo lead. Usa «Invita in CRMEvent».")
    role = _norm_role(body.role)
    m = await db.memberships.find_one({"user_id": u["user_id"], "org_id": body.org_id})
    if m:
        await db.memberships.update_one({"id": m["id"]}, {"$set": {"active": True, "role": role, "updated_at": now_iso()}})
    else:
        await _ensure_membership(u["user_id"], body.org_id, role, admin["user_id"])
    if not lead.get("user_id"):
        await db.leads.update_one({"id": lead_id}, {"$set": {"user_id": u["user_id"], "updated_at": now_iso()}})
    await record_audit(admin, "member_added", org_id=body.org_id, org_name=org.get("nome"),
                       target_email=u["email"], target_name=u.get("name"),
                       detail=f"Assegnato da Lead · Ruolo: {ORG_ROLE_LABELS[role]}")
    return {"ok": True}


@api.post("/leads/{lead_id}/invite")
async def invite_lead(lead_id: str, body: LeadAssignIn, admin: dict = Depends(require_superadmin)):
    lead = await db.leads.find_one({"id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead non trovato")
    org = await _org_or_404(body.org_id)
    email = (lead.get("email") or "").lower()
    if not email:
        raise HTTPException(status_code=400, detail="Il lead non ha un'email")
    role = _norm_role(body.role)
    eu = await db.users.find_one({"email": email}, {"_id": 0})
    if eu and await db.memberships.find_one({"user_id": eu["user_id"], "org_id": body.org_id, "active": True}):
        raise HTTPException(status_code=400, detail="Questo utente è già associato all'organizzazione")
    inv = await _create_invite(org, email, role, admin["user_id"], lead_id=lead_id)
    sent = True
    try:
        await _send_invite_email(email, org.get("nome"), inv["token"], role)
    except Exception as e:
        logger.error(f"lead invite failed: {e}"); sent = False
    await record_audit(admin, "invite_sent", org_id=body.org_id, org_name=org.get("nome"), target_email=email,
                       detail=f"Invito da Lead · Ruolo: {ORG_ROLE_LABELS[role]}")
    return {"ok": True, "email_sent": sent}


# ---------------- briefing evento ----------------
def _briefing_hash(data: dict) -> str:
    payload = json.dumps(data.get("sections", {}), sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


async def _build_briefing(event_id: str, org_id: str) -> dict:
    event = await db.events.find_one({"id": event_id, "org_id": org_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Evento non trovato")

    persons = {p["id"]: p for p in await db.persons.find({"org_id": org_id}, {"_id": 0}).to_list(10000)}
    teams = await db.teams.find({"evento_id": event_id, "org_id": org_id}, {"_id": 0}).to_list(1000)
    links = await db.staff.find({"evento_id": event_id, "org_id": org_id}, {"_id": 0}).to_list(5000)
    shifts = await db.shifts.find({"evento_id": event_id, "org_id": org_id}, {"_id": 0}).sort([("data", 1), ("ora_inizio", 1)]).to_list(5000)
    maps = await db.event_maps.find({"evento_id": event_id, "org_id": org_id}, {"_id": 0}).to_list(1000)
    lodgings = await db.lodgings.find({"evento_id": event_id, "org_id": org_id}, {"_id": 0}).to_list(5000)
    meals = await db.meals.find({"evento_id": event_id, "org_id": org_id}, {"_id": 0}).to_list(20000)
    await _attach_structures(lodgings + meals, org_id)
    deals = await db.deals.find({"evento_id": event_id, "org_id": org_id}, {"_id": 0}).to_list(2000)
    companies = {c["id"]: c for c in await db.companies.find({"org_id": org_id}, {"_id": 0}).to_list(10000)}

    team_map = {t["id"]: t for t in teams}

    def pfull(pid):
        p = persons.get(pid)
        if not p:
            return None
        return {"id": p["id"], "nome": p.get("nome"), "cognome": p.get("cognome"),
                "telefono": p.get("cellulare") or p.get("telefono"), "email": p.get("email"),
                "ruolo": p.get("ruolo")}

    staff_out = []
    for l in links:
        p = persons.get(l["persona_id"])
        if not p:
            continue
        staff_out.append({
            "persona_id": p["id"], "nome": p.get("nome"), "cognome": p.get("cognome"),
            "categoria": l.get("categoria"), "ruolo": l.get("ruolo") or p.get("ruolo"),
            "team_id": l.get("team_id"), "team_nome": team_map.get(l.get("team_id"), {}).get("nome"),
            "responsabile": l.get("responsabile"),
            "telefono": p.get("cellulare") or p.get("telefono"), "email": p.get("email"),
            "area": l.get("area"), "punto_ritrovo": l.get("punto_ritrovo"), "luogo_operativo": l.get("luogo_operativo"),
            "data_arrivo": l.get("data_arrivo"), "ora_arrivo": l.get("ora_arrivo"),
            "data_partenza": l.get("data_partenza"), "ora_partenza": l.get("ora_partenza"),
            "stato": l.get("stato"),
        })
    staff_out.sort(key=lambda x: ((x.get("cognome") or "").lower(), (x.get("nome") or "").lower()))

    members_by_team = defaultdict(list)
    for s in staff_out:
        if s.get("team_id"):
            members_by_team[s["team_id"]].append(s)
    teams_out = []
    for t in teams:
        resp = pfull(t.get("responsabile_id")) if t.get("responsabile_id") else None
        mem = members_by_team.get(t["id"], [])
        teams_out.append({
            "id": t["id"], "nome": t.get("nome"), "area": t.get("area"),
            "descrizione": t.get("descrizione"), "luogo_operativo": t.get("luogo_operativo"),
            "punto_ritrovo": t.get("punto_ritrovo"), "responsabile": resp, "membri": mem,
            "staff_count": len([m for m in mem if m.get("categoria") != "volontario"]),
            "volontari_count": len([m for m in mem if m.get("categoria") == "volontario"]),
        })
    teams_out.sort(key=lambda x: (x.get("nome") or "").lower())

    shifts_out = []
    for s in shifts:
        p = persons.get(s.get("persona_id")) if s.get("persona_id") else None
        shifts_out.append({
            "id": s["id"], "data": s.get("data"), "ora_inizio": s.get("ora_inizio"), "ora_fine": s.get("ora_fine"),
            "area": s.get("area"), "ruolo": s.get("ruolo"),
            "team_nome": team_map.get(s.get("team_id"), {}).get("nome"),
            "luogo": s.get("luogo"), "punto_ritrovo": s.get("punto_ritrovo"),
            "persona_nome": (f"{p.get('nome', '')} {p.get('cognome') or ''}".strip() if p else None),
            "coperto": bool(s.get("persona_id")),
        })

    lod_by, meal_by = defaultdict(list), defaultdict(list)
    for x in lodgings:
        for f in COST_FIELDS:
            x.pop(f, None)
        lod_by[x["persona_id"]].append(x)
    for x in meals:
        for f in COST_FIELDS:
            x.pop(f, None)
        meal_by[x["persona_id"]].append(x)
    hosp_persons = []
    for l in links:
        p = persons.get(l["persona_id"])
        if not p:
            continue
        plod, pmeal = lod_by.get(l["persona_id"], []), meal_by.get(l["persona_id"], [])
        if not plod and not pmeal:
            continue
        eff_esig = l.get("esigenze_alimentari") if l.get("esigenze_alimentari") is not None else p.get("esigenze_alimentari")
        hosp_persons.append({
            "nome": p.get("nome"), "cognome": p.get("cognome"),
            "esigenze_alimentari": eff_esig or [], "lodgings": plod, "meals": pmeal,
        })
    hosp_persons.sort(key=lambda x: ((x.get("cognome") or "").lower(), (x.get("nome") or "").lower()))

    sponsors_out = []
    for d in deals:
        c = companies.get(d.get("azienda_id"))
        if not c:
            continue
        sponsors_out.append({
            "azienda": c.get("nome"), "tipo": d.get("tipo"), "fase": d.get("fase"),
            "livello": d.get("livello"), "valore_confermato": d.get("valore_confermato"), "stato": d.get("stato"),
        })

    tl = defaultdict(list)
    for s in shifts_out:
        if s.get("data"):
            tl[s["data"]].append(s)
    timeline = [{"data": d, "turni": tl[d]} for d in sorted(tl.keys())]

    staff_count = len([s for s in staff_out if s.get("categoria") in ("staff", "collaboratore")])
    volontari_count = len([s for s in staff_out if s.get("categoria") == "volontario"])
    turni_scoperti = len([s for s in shifts_out if not s["coperto"]])
    stats = {
        "persone_count": len(staff_out), "staff_count": staff_count, "volontari_count": volontari_count,
        "teams_count": len(teams_out), "turni_count": len(shifts_out), "turni_scoperti": turni_scoperti,
        "mappe_count": len(maps), "sponsor_count": len(sponsors_out),
        "pernottamenti": len(lodgings), "pasti": len(meals),
    }

    sections = {
        "teams": teams_out, "staff": staff_out, "shifts": shifts_out,
        "hospitality": hosp_persons, "maps": maps, "sponsors": sponsors_out, "timeline": timeline,
    }

    checks = []

    def add(key, label, ok, detail=""):
        checks.append({"key": key, "label": label, "status": "ok" if ok else "warning", "detail": detail})

    add("evento_date", "Date evento definite", bool(event.get("data_inizio")),
        "" if event.get("data_inizio") else "Manca la data di inizio evento")
    add("evento_luogo", "Località / venue definita", bool(event.get("localita") or event.get("citta")),
        "" if (event.get("localita") or event.get("citta")) else "Manca la località dell'evento")
    add("staff_presente", "Staff/volontari collegati", len(staff_out) > 0,
        "" if staff_out else "Nessuna persona collegata all'evento")
    teams_no_resp = [t["nome"] for t in teams_out if not t["responsabile"]]
    add("team_responsabili", "Team con responsabile", len(teams_out) > 0 and not teams_no_resp,
        ("Team senza responsabile: " + ", ".join(teams_no_resp)) if teams_no_resp else ("Nessun team creato" if not teams_out else ""))
    add("turni_coperti", "Turni tutti coperti", turni_scoperti == 0,
        f"{turni_scoperti} turni scoperti da coprire" if turni_scoperti else "")
    add("mappe", "Mappe / percorsi presenti", len(maps) > 0,
        "Nessuna mappa o percorso caricato" if not maps else "")
    vol_no_resp = [f"{s['nome']} {s.get('cognome') or ''}".strip() for s in staff_out
                   if not s.get("responsabile") and s.get("categoria") == "volontario"]
    add("referenti", "Volontari con referente", not vol_no_resp,
        (f"{len(vol_no_resp)} volontari senza referente assegnato") if vol_no_resp else "")
    add("ospitalita", "Ospitalità / pasti gestiti", len(hosp_persons) > 0,
        "Nessuna ospitalità o pasto assegnato" if not hosp_persons else "")

    passed = len([c for c in checks if c["status"] == "ok"])
    percent = round(passed / len(checks) * 100) if checks else 0
    completeness = {"percent": percent, "passed": passed, "total": len(checks), "checks": checks}

    return {"event": event, "sections": sections, "stats": stats,
            "completeness": completeness, "generated_at": now_iso()}


@api.get("/events/{event_id}/briefing-live")
async def briefing_live(event_id: str, admin: dict = Depends(require_admin)):
    data = await _build_briefing(event_id, admin["org_id"])
    versions = await db.briefing_versions.find(oq(admin, evento_id=event_id), {"content": 0, "_id": 0}).sort("versione", -1).to_list(200)
    live_hash = _briefing_hash(data)
    latest = versions[0] if versions else None
    data["live_hash"] = live_hash
    data["latest_version"] = latest
    data["is_stale"] = bool(latest and latest.get("content_hash") != live_hash)
    return data


class BriefingPublishIn(BaseModel):
    titolo: Optional[str] = None
    note: Optional[str] = None


@api.post("/events/{event_id}/briefing-versions")
async def publish_briefing(event_id: str, body: BriefingPublishIn, admin: dict = Depends(require_admin)):
    data = await _build_briefing(event_id, admin["org_id"])
    last = await db.briefing_versions.find_one(oq(admin, evento_id=event_id), sort=[("versione", -1)])
    versione = (last.get("versione", 0) + 1) if last else 1
    doc = {"id": new_id(), "org_id": admin["org_id"], "evento_id": event_id, "versione": versione,
           "titolo": body.titolo or f"Versione {versione}", "note": body.note,
           "content": data, "content_hash": _briefing_hash(data),
           "published_by": admin.get("name") or admin.get("email"), "created_at": now_iso()}
    await db.briefing_versions.insert_one(doc)
    return {"id": doc["id"], "versione": versione, "titolo": doc["titolo"], "created_at": doc["created_at"]}


@api.get("/events/{event_id}/briefing-versions")
async def list_briefing_versions(event_id: str, admin: dict = Depends(require_admin)):
    return await db.briefing_versions.find(oq(admin, evento_id=event_id), {"content": 0, "_id": 0}).sort("versione", -1).to_list(200)


@api.get("/briefing-versions/{version_id}")
async def get_briefing_version(version_id: str, admin: dict = Depends(require_admin)):
    v = await db.briefing_versions.find_one(oq(admin, id=version_id), {"_id": 0})
    if not v:
        raise HTTPException(status_code=404, detail="Versione non trovata")
    return v


@api.delete("/briefing-versions/{version_id}")
async def delete_briefing_version(version_id: str, admin: dict = Depends(require_admin)):
    await db.briefing_versions.delete_one(oq(admin, id=version_id))
    return {"ok": True}


# ---------------- admin reset ----------------
OPERATIONAL = ["events", "companies", "persons", "deals", "staff", "teams", "shifts",
               "event_maps", "activities", "followups", "calendar_event_links", "files",
               "person_companies", "lodgings", "meals", "briefing_versions", "invoices"]


@api.post("/admin/reset-data")
async def reset_data(admin: dict = Depends(require_admin)):
    for c in OPERATIONAL:
        await db[c].delete_many({"org_id": admin["org_id"]})
    await db.users.delete_many({"role": {"$in": ["staff", "volunteer"]}, "org_id": admin["org_id"]})
    counts = {c: await db[c].count_documents({"org_id": admin["org_id"]}) for c in OPERATIONAL}
    return {"ok": True, "counts": counts}


# ---------------- account & platform (superadmin) ----------------
@api.get("/account/subscription")
async def account_subscription(user: dict = Depends(require_admin)):
    org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=404, detail="Organizzazione non trovata")
    return {"organization": {"id": org["id"], "nome": org.get("nome"), "created_at": org.get("created_at")},
            "subscription": _sub_summary(org)}


@api.get("/platform/stats")
async def platform_stats(admin: dict = Depends(require_superadmin)):
    orgs = await db.organizations.find({}, {"_id": 0}).to_list(5000)
    summaries = [_sub_summary(o) for o in orgs]
    trial = len([s for s in summaries if s["status"] == "trial"])
    active = len([s for s in summaries if s["status"] == "active"])
    expired = len([s for s in summaries if s["status"] in ("expired", "canceled", "suspended", "past_due")])

    def _mrr(s):
        if s["status"] != "active":
            return 0
        return PRICE_MONTHLY if s["billing_cycle"] == "monthly" else (PRICE_YEARLY / 12 if s["billing_cycle"] == "yearly" else 0)
    mrr = sum(_mrr(s) for s in summaries)
    return {"organizations": len(orgs), "trial": trial, "active": active, "expired": expired,
            "mrr": round(mrr, 2), "arr": round(mrr * 12, 2), "leads": await db.leads.count_documents({})}


@api.get("/platform/organizations")
async def platform_organizations(admin: dict = Depends(require_superadmin)):
    orgs = await db.organizations.find({}, {"_id": 0}).sort("created_at", -1).to_list(5000)
    out = []
    for o in orgs:
        owner = await db.users.find_one({"user_id": o.get("owner_user_id")}, {"_id": 0, "password_hash": 0})
        members = await db.memberships.count_documents({"org_id": o["id"], "active": True})
        events = await db.events.count_documents({"org_id": o["id"]})
        out.append({"id": o["id"], "nome": o.get("nome"), "type": o.get("type", "cliente"),
                    "status": o.get("status", "active"), "created_at": o.get("created_at"),
                    "owner_email": (owner or {}).get("email"), "owner_name": (owner or {}).get("name"),
                    "members": members, "events": events, "subscription": _sub_summary(o)})
    return out


# ---------------- platform audit log (extensible) ----------------
# Append-only trail of privileged Super Admin actions. No API surface mutates/deletes it.
# NEVER store passwords, tokens, secrets or payment data here — only non-sensitive metadata.
AUDIT_ACTION_LABELS = {
    "org_access": "Accesso organizzazione",
    "org_switch": "Cambio organizzazione",
    "org_created": "Creazione organizzazione",
    "org_updated": "Modifica organizzazione",
    "member_added": "Associazione utente",
    "member_removed": "Rimozione utente",
    "member_role_changed": "Modifica ruolo",
    "member_enabled": "Riattivazione accesso",
    "member_disabled": "Disabilitazione accesso",
    "invite_sent": "Invio invito",
    "invite_resent": "Reinvio invito",
    "invite_revoked": "Revoca invito",
    "invite_accepted": "Accettazione invito",
    "lead_linked": "Collegamento account a Lead",
    "account_disabled": "Disabilitazione account",
    "account_enabled": "Riattivazione account",
    "account_deleted": "Eliminazione account",
    "org_disabled": "Disabilitazione organizzazione",
    "org_enabled": "Riattivazione organizzazione",
    "org_deleted": "Eliminazione organizzazione",
    "demo_seeded": "Popolamento dati Demo",
    "invites_cleaned": "Pulizia inviti",
}


async def record_audit(actor: dict, action: str, org_id: Optional[str] = None,
                        org_name: Optional[str] = None, meta: Optional[dict] = None,
                        target_email: Optional[str] = None, target_name: Optional[str] = None,
                        detail: Optional[str] = None) -> dict:
    doc = {"id": new_id(), "created_at": now_iso(),
           "actor_user_id": actor.get("user_id"), "actor_email": actor.get("email"),
           "actor_name": actor.get("name"), "actor_role": actor.get("role"),
           "action": action, "action_label": AUDIT_ACTION_LABELS.get(action, action),
           "org_id": org_id, "org_name": org_name,
           "target_email": target_email, "target_name": target_name, "detail": detail,
           "meta": meta or {}}
    await db.audit_logs.insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}


class OrgAccessIn(BaseModel):
    org_id: str
    previous_org_id: Optional[str] = None


@api.post("/platform/audit/org-access")
async def audit_org_access(body: OrgAccessIn, user: dict = Depends(get_current_user)):
    org = await db.organizations.find_one({"id": body.org_id}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=404, detail="Organizzazione non trovata")
    if user.get("role") != "superadmin":
        m = await db.memberships.find_one({"user_id": user["user_id"], "org_id": body.org_id, "active": True})
        if not m:
            raise HTTPException(status_code=403, detail="Accesso all'organizzazione non consentito")
        await db.memberships.update_one({"id": m["id"]}, {"$set": {"last_login_at": now_iso()}})
    action, meta = "org_access", {}
    if body.previous_org_id and body.previous_org_id != body.org_id:
        prev = await db.organizations.find_one({"id": body.previous_org_id}, {"_id": 0})
        action = "org_switch"
        meta = {"previous_org_id": body.previous_org_id, "previous_org_name": (prev or {}).get("nome")}
    doc = await record_audit(user, action, org_id=org["id"], org_name=org.get("nome"), meta=meta)
    return {"ok": True, "id": doc["id"]}


@api.get("/platform/audit")
async def audit_list(org_id: Optional[str] = None, actor_user_id: Optional[str] = None,
                     date_from: Optional[str] = None, date_to: Optional[str] = None,
                     action: Optional[str] = None, limit: int = 300,
                     admin: dict = Depends(require_superadmin)):
    q: dict = {}
    if org_id:
        q["org_id"] = org_id
    if actor_user_id:
        q["actor_user_id"] = actor_user_id
    if action:
        q["action"] = action
    if date_from or date_to:
        rng = {}
        if date_from:
            rng["$gte"] = date_from
        if date_to:
            rng["$lte"] = date_to + "T23:59:59.999999"
        q["created_at"] = rng
    rows = await db.audit_logs.find(q, {"_id": 0}).sort("created_at", -1).limit(min(max(limit, 1), 1000)).to_list(1000)
    actor_ids = await db.audit_logs.distinct("actor_user_id")
    actors = []
    for aid in actor_ids:
        u = await db.users.find_one({"user_id": aid}, {"_id": 0, "user_id": 1, "email": 1, "name": 1})
        if u:
            actors.append({"user_id": u["user_id"], "email": u.get("email"), "name": u.get("name")})
    return {"items": rows, "actors": actors}


# ---------------- stripe billing ----------------
import stripe as stripe_sdk
stripe_sdk.api_key = os.environ.get("STRIPE_SECRET_KEY") or "sk_test_emergent"
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
PRICE_LOOKUPS = {"monthly": "crmevent_monthly", "yearly": "crmevent_yearly"}
STRIPE_STATUS_MAP = {"active": "active", "trialing": "active", "past_due": "past_due",
                     "canceled": "canceled", "unpaid": "suspended", "incomplete": "past_due",
                     "incomplete_expired": "expired"}


class BillingDetails(BaseModel):
    tipo: Optional[str] = "azienda"          # azienda | privato
    paese: Optional[str] = "IT"
    ragione_sociale: Optional[str] = None
    nome: Optional[str] = None
    cognome: Optional[str] = None
    indirizzo: Optional[str] = None
    cap: Optional[str] = None
    citta: Optional[str] = None
    provincia: Optional[str] = None
    codice_fiscale: Optional[str] = None
    partita_iva: Optional[str] = None
    codice_sdi: Optional[str] = None
    pec: Optional[str] = None
    email_fatturazione: Optional[str] = None


@api.get("/account/billing")
async def get_billing(user: dict = Depends(require_admin)):
    org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0})
    return (org or {}).get("billing") or {}


@api.put("/account/billing")
async def put_billing(body: BillingDetails, user: dict = Depends(require_admin)):
    data = body.model_dump()
    await db.organizations.update_one({"id": user["org_id"]}, {"$set": {"billing": data, "updated_at": now_iso()}})
    return data


async def _ensure_stripe_customer(org: dict, user: dict) -> str:
    existing = (org.get("subscription") or {}).get("stripe_customer_id")
    if existing:
        return existing
    b = org.get("billing") or {}
    name = b.get("ragione_sociale") or (f"{b.get('nome','')} {b.get('cognome','')}".strip()) or org.get("nome")
    address = {k: v for k, v in {"line1": b.get("indirizzo"), "postal_code": b.get("cap"),
                                 "city": b.get("citta"), "state": b.get("provincia"),
                                 "country": (b.get("paese") or "IT")}.items() if v}
    cust = stripe_sdk.Customer.create(name=name, email=b.get("email_fatturazione") or user.get("email"),
                                      address=address or None, metadata={"org_id": org["id"]})
    await db.organizations.update_one({"id": org["id"]}, {"$set": {"subscription.stripe_customer_id": cust.id}})
    return cust.id


class CheckoutIn(BaseModel):
    billing_cycle: str
    origin_url: str


@api.post("/account/checkout")
async def create_checkout(body: CheckoutIn, user: dict = Depends(require_admin)):
    if body.billing_cycle not in PRICE_LOOKUPS:
        raise HTTPException(status_code=400, detail="Ciclo di fatturazione non valido")
    org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0})
    if not (org.get("billing") or {}).get("paese"):
        raise HTTPException(status_code=400, detail="Completa prima i dati di fatturazione")
    prices = stripe_sdk.Price.list(lookup_keys=[PRICE_LOOKUPS[body.billing_cycle]], active=True, limit=1).data
    if not prices:
        raise HTTPException(status_code=500, detail="Prezzo non configurato su Stripe")
    cust_id = await _ensure_stripe_customer(org, user)
    session = stripe_sdk.checkout.Session.create(
        mode="subscription", customer=cust_id,
        line_items=[{"price": prices[0].id, "quantity": 1}],
        success_url=f"{body.origin_url}/account?checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{body.origin_url}/account?checkout=cancel",
        metadata={"org_id": org["id"], "billing_cycle": body.billing_cycle},
        subscription_data={"metadata": {"org_id": org["id"], "billing_cycle": body.billing_cycle}},
    )
    return {"checkout_url": session.url, "session_id": session.id}


@api.get("/account/checkout-confirmation")
async def checkout_confirmation(session_id: str, user: dict = Depends(require_admin)):
    """Verify a Stripe checkout session was really paid. Returns ONLY non-personal
    data so the frontend can emit a GA4 `purchase` event (no PII, no customer id)."""
    try:
        sess = stripe_sdk.checkout.Session.retrieve(session_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Sessione di checkout non trovata")
    org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0})
    # Ensure the session belongs to this org's Stripe customer (isolation).
    cust = (org.get("subscription") or {}).get("stripe_customer_id")
    if cust and sess.get("customer") and sess.get("customer") != cust:
        raise HTTPException(status_code=403, detail="Sessione non associata all'organizzazione")
    paid = sess.get("payment_status") == "paid"
    if not paid:
        return {"paid": False}
    # Unique, non-personal transaction reference (Stripe invoice > payment_intent > session id).
    transaction_id = sess.get("invoice") or sess.get("payment_intent") or sess.get("id")
    billing_cycle = (sess.get("metadata") or {}).get("billing_cycle")
    return {
        "paid": True,
        "transaction_id": transaction_id,
        "value": round((sess.get("amount_total") or 0) / 100.0, 2),
        "currency": (sess.get("currency") or "eur").upper(),
        "billing_cycle": billing_cycle,
    }


@api.post("/account/portal")
async def billing_portal(body: dict, user: dict = Depends(require_admin)):
    org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0})
    cust = (org.get("subscription") or {}).get("stripe_customer_id")
    if not cust:
        raise HTTPException(status_code=400, detail="Nessun cliente Stripe associato")
    origin = body.get("origin_url") or APP_URL
    ps = stripe_sdk.billing_portal.Session.create(customer=cust, return_url=f"{origin}/account")
    return {"url": ps.url}


async def _sync_subscription(sub: dict, org_id: Optional[str] = None):
    org_id = org_id or (sub.get("metadata") or {}).get("org_id")
    if not org_id:
        o = await db.organizations.find_one({"subscription.stripe_customer_id": sub.get("customer")}, {"_id": 0})
        org_id = o["id"] if o else None
    if not org_id:
        return
    items = (sub.get("items") or {}).get("data") or []
    interval = items[0]["price"]["recurring"]["interval"] if items else None
    cycle = "yearly" if interval == "year" else ("monthly" if interval == "month" else None)
    cpe = sub.get("current_period_end")
    await db.organizations.update_one({"id": org_id}, {"$set": {
        "subscription.status": STRIPE_STATUS_MAP.get(sub.get("status"), sub.get("status")),
        "subscription.stripe_subscription_id": sub.get("id"),
        "subscription.stripe_customer_id": sub.get("customer"),
        "subscription.billing_cycle": cycle,
        "subscription.cancel_at_period_end": bool(sub.get("cancel_at_period_end")),
        "subscription.current_period_end": datetime.fromtimestamp(cpe, timezone.utc).isoformat() if cpe else None,
        "updated_at": now_iso()}})


async def _record_invoice(inv: dict, payment_status: str):
    o = await db.organizations.find_one({"subscription.stripe_customer_id": inv.get("customer")}, {"_id": 0})
    if not o:
        return
    created = inv.get("created")
    doc = {"org_id": o["id"], "stripe_invoice_id": inv.get("id"), "stripe_payment_intent": inv.get("payment_intent"),
           "numero_stripe": inv.get("number"),
           "data": datetime.fromtimestamp(created, timezone.utc).isoformat() if created else now_iso(),
           "imponibile": (inv.get("subtotal") or 0) / 100.0, "iva": (inv.get("tax") or 0) / 100.0,
           "totale": (inv.get("total") or 0) / 100.0, "valuta": inv.get("currency"),
           "hosted_invoice_url": inv.get("hosted_invoice_url"), "stripe_pdf": inv.get("invoice_pdf"),
           "payment_status": payment_status, "updated_at": now_iso()}
    existing = await db.invoices.find_one({"stripe_invoice_id": inv.get("id")})
    if existing:
        await db.invoices.update_one({"stripe_invoice_id": inv.get("id")}, {"$set": doc})
    else:
        # Fatture in Cloud (SDI) scaffold — populated later when FIC is wired
        doc.update({"id": new_id(), "created_at": now_iso(), "fic_document_id": None, "fic_numero": None,
                    "fic_data": None, "fic_stato_documento": "da_emettere", "fic_stato_sdi": "non_inviato",
                    "fic_pdf_url": None})
        await db.invoices.insert_one(doc)


@api.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = stripe_sdk.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except Exception:
        raise HTTPException(status_code=400, detail="Firma webhook non valida")
    t, obj = event["type"], event["data"]["object"]
    if t == "customer.subscription.deleted":
        await db.organizations.update_one({"subscription.stripe_subscription_id": obj["id"]},
                                          {"$set": {"subscription.status": "canceled", "updated_at": now_iso()}})
    elif t in ("customer.subscription.created", "customer.subscription.updated"):
        await _sync_subscription(obj)
    elif t == "checkout.session.completed":
        if obj.get("subscription"):
            sub = stripe_sdk.Subscription.retrieve(obj["subscription"])
            await _sync_subscription(sub, (obj.get("metadata") or {}).get("org_id"))
    elif t in ("invoice.paid", "invoice.payment_succeeded"):
        await _record_invoice(obj, "paid")
    elif t == "invoice.payment_failed":
        await db.organizations.update_one({"subscription.stripe_customer_id": obj.get("customer")},
                                          {"$set": {"subscription.status": "past_due", "updated_at": now_iso()}})
        await _record_invoice(obj, "payment_failed")
    return {"received": True}


@api.post("/account/sync-subscription")
async def sync_subscription_now(user: dict = Depends(require_admin)):
    """Fallback sync (also useful in tests): pull latest subscription from Stripe."""
    org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0})
    cust = (org.get("subscription") or {}).get("stripe_customer_id")
    if not cust:
        return {"synced": False}
    subs = stripe_sdk.Subscription.list(customer=cust, status="all", limit=1).data
    if subs:
        await _sync_subscription(subs[0])
    org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0})
    return {"synced": True, "subscription": _sub_summary(org)}


@api.get("/account/invoices")
async def account_invoices(user: dict = Depends(require_admin)):
    return await db.invoices.find(oq(user), {"_id": 0}).sort("data", -1).to_list(500)


@api.get("/platform/subscriptions")
async def platform_subscriptions(admin: dict = Depends(require_superadmin)):
    orgs = await db.organizations.find({}, {"_id": 0}).sort("created_at", -1).to_list(5000)
    out = []
    for o in orgs:
        sub = o.get("subscription") or {}
        s = _sub_summary(o)
        last_inv = await db.invoices.find_one({"org_id": o["id"]}, {"_id": 0}, sort=[("data", -1)])
        amount = PRICE_YEARLY if s["billing_cycle"] == "yearly" else (PRICE_MONTHLY if s["billing_cycle"] == "monthly" else None)
        out.append({"id": o["id"], "nome": o.get("nome"), "status": s["status"],
                    "billing_cycle": s["billing_cycle"], "amount": amount,
                    "current_period_end": s["current_period_end"], "days_left": s["days_left"],
                    "stripe_customer_id": sub.get("stripe_customer_id"),
                    "stripe_subscription_id": sub.get("stripe_subscription_id"),
                    "fatturazione": (last_inv or {}).get("fic_stato_sdi", "—") if last_inv else "—"})
    return out


# ---------------- fatture in cloud (e-invoicing) ----------------
FIC_BASE = "https://api-v2.fattureincloud.it"
FIC_CLIENT_ID = os.environ.get("FIC_CLIENT_ID", "")
FIC_CLIENT_SECRET = os.environ.get("FIC_CLIENT_SECRET", "")
FIC_REDIRECT_URI = os.environ.get("FIC_REDIRECT_URI", "")
FIC_COMPANY_ID = os.environ.get("FIC_COMPANY_ID", "")
FIC_SCOPES = "issued_documents.invoices:r issued_documents.invoices:a settings:r"


def fic_configured() -> bool:
    return bool(FIC_CLIENT_ID and FIC_CLIENT_SECRET and FIC_REDIRECT_URI)


async def _fic_save_tokens(t: dict):
    await db.fic_settings.update_one({"provider": "fic"}, {"$set": {
        "provider": "fic", "access_token": t["access_token"], "refresh_token": t["refresh_token"],
        "expires_at": time.time() + int(t.get("expires_in", 86400)), "updated_at": now_iso()}}, upsert=True)


async def _fic_token() -> str:
    doc = await db.fic_settings.find_one({"provider": "fic"})
    if not doc:
        raise HTTPException(status_code=409, detail="Fatture in Cloud non collegato")
    if doc.get("expires_at", 0) < time.time() + 60:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(f"{FIC_BASE}/oauth/token", json={"grant_type": "refresh_token",
                "client_id": FIC_CLIENT_ID, "client_secret": FIC_CLIENT_SECRET, "refresh_token": doc["refresh_token"]})
        r.raise_for_status()
        t = r.json(); await _fic_save_tokens(t); return t["access_token"]
    return doc["access_token"]


async def _fic_company_id() -> str:
    doc = await db.fic_settings.find_one({"provider": "fic"})
    return (doc or {}).get("company_id") or FIC_COMPANY_ID


@api.get("/fic/status")
async def fic_status(admin: dict = Depends(require_superadmin)):
    doc = await db.fic_settings.find_one({"provider": "fic"}, {"_id": 0, "access_token": 0, "refresh_token": 0})
    return {"configured": fic_configured(), "connected": bool(doc), "redirect_uri": FIC_REDIRECT_URI,
            "company_id": await _fic_company_id(), "updated_at": (doc or {}).get("updated_at")}


@api.get("/fic/oauth/start")
async def fic_oauth_start(admin: dict = Depends(require_superadmin)):
    if not fic_configured():
        raise HTTPException(status_code=400, detail="Configura prima FIC_CLIENT_ID / SECRET / REDIRECT_URI")
    state = secrets.token_urlsafe(24)
    await db.fic_oauth_states.insert_one({"state": state, "created_at": time.time()})
    from urllib.parse import urlencode
    q = urlencode({"response_type": "code", "client_id": FIC_CLIENT_ID, "redirect_uri": FIC_REDIRECT_URI,
                   "scope": FIC_SCOPES, "state": state})
    return {"authorize_url": f"{FIC_BASE}/oauth/authorize?{q}"}


@api.get("/fic/oauth/callback")
async def fic_oauth_callback(code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    if error or not code or not state:
        return RedirectResponse(f"{APP_URL}/piattaforma?fic=error")
    saved = await db.fic_oauth_states.find_one_and_delete({"state": state})
    if not saved or time.time() - saved["created_at"] > 600:
        return RedirectResponse(f"{APP_URL}/piattaforma?fic=state_error")
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{FIC_BASE}/oauth/token", json={"grant_type": "authorization_code",
            "client_id": FIC_CLIENT_ID, "client_secret": FIC_CLIENT_SECRET,
            "redirect_uri": FIC_REDIRECT_URI, "code": code})
    if r.status_code >= 400:
        return RedirectResponse(f"{APP_URL}/piattaforma?fic=token_error")
    await _fic_save_tokens(r.json())
    # auto-detect company_id if not set
    try:
        token = await _fic_token()
        async with httpx.AsyncClient(timeout=20) as c:
            cr = await c.get(f"{FIC_BASE}/user/companies", headers={"Authorization": f"Bearer {token}"})
        comps = (cr.json().get("data") or {}).get("companies") or cr.json().get("data") or []
        if not FIC_COMPANY_ID and comps:
            await db.fic_settings.update_one({"provider": "fic"}, {"$set": {"company_id": str(comps[0]["id"])}})
    except Exception as e:
        logger.warning(f"FIC company detect failed: {e}")
    return RedirectResponse(f"{APP_URL}/piattaforma?fic=connected")


@api.post("/fic/disconnect")
async def fic_disconnect(admin: dict = Depends(require_superadmin)):
    await db.fic_settings.delete_one({"provider": "fic"})
    return {"ok": True}


@api.get("/fic/companies")
async def fic_companies(admin: dict = Depends(require_superadmin)):
    token = await _fic_token()
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(f"{FIC_BASE}/user/companies", headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    return r.json().get("data")


async def _fic_vat_id(company_id: str, token: str) -> Optional[int]:
    override = os.environ.get("FIC_VAT_ID")
    if override:
        return int(override)
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(f"{FIC_BASE}/c/{company_id}/settings/vat_types", headers={"Authorization": f"Bearer {token}"})
        for v in (r.json().get("data") or []):
            if abs(float(v.get("value", 0)) - 22.0) < 0.01:
                return v["id"]
    except Exception:
        pass
    return None


def _fic_entity(org: dict) -> dict:
    b = org.get("billing") or {}
    paese = (b.get("paese") or "IT").upper()
    name = b.get("ragione_sociale") or (f"{b.get('nome','')} {b.get('cognome','')}".strip()) or org.get("nome")
    ei = b.get("codice_sdi") or ("XXXXXXX" if paese != "IT" else "0000000")
    ent = {"name": name, "vat_number": b.get("partita_iva"), "tax_code": b.get("codice_fiscale"),
           "address_street": b.get("indirizzo"), "address_postal_code": b.get("cap"),
           "address_city": b.get("citta"), "address_province": b.get("provincia"),
           "country": "Italia" if paese == "IT" else (b.get("paese") or ""), "ei_code": ei}
    if b.get("pec"):
        ent["certified_email"] = b.get("pec")
    return ent


async def _fic_issue_document(inv: dict, dry_run: bool = True) -> dict:
    """Create an issued invoice in FIC from a CRMEvent invoice record (TEST: no real SDI transmission)."""
    org = await db.organizations.find_one({"id": inv["org_id"]}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=404, detail="Organizzazione non trovata")
    token = await _fic_token()
    cid = await _fic_company_id()
    if not cid:
        raise HTTPException(status_code=400, detail="company_id FIC mancante")
    vat_id = await _fic_vat_id(cid, token)
    net = inv.get("imponibile") or inv.get("totale") or 0
    line = {"name": f"Abbonamento CRMEvent ({org.get('nome')})", "qty": 1, "net_price": net}
    if vat_id is not None:
        line["vat"] = {"id": vat_id}
    body = {"data": {"type": "invoice", "e_invoice": True, "entity": _fic_entity(org),
                     "items_list": [line], "currency": {"id": "EUR"}, "language": {"code": "it"}}}
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{FIC_BASE}/c/{cid}/issued_documents",
                         headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, json=body)
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail={"fic_create": r.json()})
    d = r.json().get("data", {})
    amounts = {"imponibile": d.get("amount_net"), "iva": d.get("amount_vat"), "totale": d.get("amount_gross")}
    validation = None
    doc_id = d.get("id")
    if dry_run and doc_id:
        try:
            async with httpx.AsyncClient(timeout=30) as c:
                vr = await c.post(f"{FIC_BASE}/c/{cid}/issued_documents/{doc_id}/e_invoice/send",
                                  headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                                  json={"data": {}, "options": {"dry_run": True}})
            validation = {"status": vr.status_code, "body": vr.json() if vr.content else None}
        except Exception as e:
            validation = {"error": str(e)[:200]}
    upd = {"fic_document_id": doc_id, "fic_numero": d.get("number"), "fic_data": d.get("date"),
           "fic_stato_documento": "creato_test", "fic_stato_sdi": "dry_run_validato" if dry_run else "non_inviato",
           "fic_pdf_url": d.get("url") or d.get("pdf_url"),
           "imponibile": amounts["imponibile"] if amounts["imponibile"] is not None else inv.get("imponibile"),
           "iva": amounts["iva"] if amounts["iva"] is not None else inv.get("iva"),
           "totale": amounts["totale"] if amounts["totale"] is not None else inv.get("totale"),
           "updated_at": now_iso()}
    await db.invoices.update_one({"id": inv["id"]}, {"$set": upd})
    return {"document": d, "amounts": amounts, "validation": validation}


@api.post("/fic/issue/{invoice_id}")
async def fic_issue(invoice_id: str, admin: dict = Depends(require_superadmin)):
    inv = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    return await _fic_issue_document(inv, dry_run=True)


# ---- FIC SIMULATION (TEST): builds the payload internally, makes NO FIC call, NO SDI. ----
def _fic_build_payload(org: dict, inv: dict, vat_percent: float = 22.0) -> dict:
    """Build the exact FIC issued_document payload that WOULD be sent — without sending it.
    Contains only the org's own billing data; no secrets/tokens."""
    net = inv.get("imponibile") or inv.get("totale") or 0
    line = {"name": f"Abbonamento CRMEvent ({org.get('nome')})", "qty": 1,
            "net_price": net, "vat": {"value": vat_percent}}
    return {"data": {"type": "invoice", "e_invoice": True, "entity": _fic_entity(org),
                     "items_list": [line], "currency": {"id": "EUR"}, "language": {"code": "it"}}}


async def _fic_simulate(inv: dict) -> dict:
    org = await db.organizations.find_one({"id": inv["org_id"]}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=404, detail="Organizzazione non trovata")
    payload = _fic_build_payload(org, inv)
    imponibile = inv.get("imponibile")
    if imponibile is None:
        imponibile = inv.get("totale") or 0
    iva = inv.get("iva")
    if iva is None:
        iva = round(imponibile * 0.22, 2)
    totale = inv.get("totale") or round(imponibile + iva, 2)
    numero = f"SIM/{datetime.now(timezone.utc).year}/{str(inv.get('id', ''))[:6].upper()}"
    data_doc = datetime.now(timezone.utc).date().isoformat()
    upd = {"fic_document_id": None, "fic_numero": numero, "fic_data": data_doc,
           "fic_stato_documento": "simulato_test", "fic_stato_sdi": "simulato_test",
           "fic_simulated": True, "fic_payload_preview": payload,
           "imponibile": imponibile, "iva": iva, "totale": totale, "updated_at": now_iso()}
    await db.invoices.update_one({"id": inv["id"]}, {"$set": upd})
    logger.info("FIC SIMULATION (TEST — no FIC call, no SDI) inv=%s numero=%s entity=%s totale=%s",
                inv.get("id"), numero, payload["data"]["entity"].get("name"), totale)
    return {"simulated": True, "mode": "SIMULAZIONE_TEST",
            "cliente": payload["data"]["entity"],
            "intestazione": payload["data"]["entity"].get("name"),
            "numero_simulato": numero, "data_simulata": data_doc,
            "imponibile": imponibile, "iva": iva, "totale": totale,
            "piano": inv.get("piano") or (org.get("subscription") or {}).get("plan"),
            "riferimento_stripe": {"stripe_invoice_id": inv.get("stripe_invoice_id"),
                                   "numero_stripe": inv.get("numero_stripe"),
                                   "payment_intent": inv.get("stripe_payment_intent")},
            "stato_fattura": inv.get("payment_status"),
            "fic_payload_preview": payload,
            "note": "SIMULAZIONE INTERNA: nessun documento reale creato su Fatture in Cloud, nessuna numerazione fiscale, nessun invio SDI."}


@api.post("/fic/simulate/{invoice_id}")
async def fic_simulate(invoice_id: str, user: dict = Depends(require_admin)):
    """TEST-only internal simulation of the FIC invoice. Org-scoped; makes NO call to FIC
    and NEVER transmits to SDI. Kept fully separate from the real /fic/issue LIVE flow."""
    inv = await db.invoices.find_one({"id": invoice_id, "org_id": user["org_id"]}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    return await _fic_simulate(inv)


# ---------------- seed ----------------
async def seed_admin():
    email = os.environ["ADMIN_EMAIL"].lower()
    pw = os.environ["ADMIN_PASSWORD"]
    existing = await db.users.find_one({"email": email})
    if not existing:
        # First-time bootstrap only. ADMIN_PASSWORD is used solely to create the
        # initial account; it is never re-applied afterwards.
        await db.users.insert_one({"user_id": f"user_{uuid.uuid4().hex[:12]}", "email": email, "name": "Michele Manara",
                                   "password_hash": hash_password(pw), "role": "superadmin", "auth_provider": "password",
                                   "org_id": None, "picture": "", "active": True, "created_at": now_iso()})
        logger.info("Super Admin account bootstrapped")
        return
    # Existing account: promote to Super Admin CRMEvent (platform owner, no org),
    # keep it enabled, but NEVER modify the password_hash.
    upd = {}
    if existing.get("role") != "superadmin":
        upd["role"] = "superadmin"
    if existing.get("org_id") is not None:
        upd["org_id"] = None
    if existing.get("active") is False:
        upd["active"] = True
    if upd:
        await db.users.update_one({"email": email}, {"$set": upd})


async def seed_demo():
    st = await db.settings.find_one({"id": "global"})
    if not st:
        await db.settings.insert_one(default_settings())
        st = await db.settings.find_one({"id": "global"})
    if st.get("demo_disabled"):
        return
    if await db.events.count_documents({}) > 0:
        return
    logger.info("Seeding demo data...")

    async def ins(coll, data):
        doc = {**data, "id": new_id(), "created_at": now_iso(), "updated_at": now_iso()}
        await db[coll].insert_one(doc)
        return doc["id"]

    ev1 = await ins("events", {"nome": "Tech Summit Milano", "edizione": "2026", "tipologia": "Congresso",
                               "data_inizio": "2026-09-15", "data_fine": "2026-09-17", "ora_inizio": "09:00", "ora_fine": "18:00",
                               "localita": "MiCo Milano", "citta": "Milano", "provincia": "MI", "regione": "Lombardia", "nazione": "Italia",
                               "organizzatore": "CRMEvent Agency", "responsabile": "Michele Manara", "sito_web": "https://techsummit.it",
                               "email": "info@techsummit.it", "telefono": "+39 02 1234567", "partecipanti_previsti": 3500,
                               "budget": 450000, "stato": "attivo", "descrizione": "Il più grande evento tech del Nord Italia."})
    ev2 = await ins("events", {"nome": "Green Food Festival", "edizione": "2026", "tipologia": "Festival",
                               "data_inizio": "2026-07-04", "data_fine": "2026-07-06", "localita": "Parco Dora",
                               "citta": "Torino", "provincia": "TO", "regione": "Piemonte", "nazione": "Italia",
                               "organizzatore": "CRMEvent Agency", "responsabile": "Laura Bianchi", "partecipanti_previsti": 12000,
                               "budget": 220000, "stato": "attivo", "descrizione": "Festival del cibo sostenibile."})
    ev3 = await ins("events", {"nome": "Gala della Moda", "edizione": "2025", "tipologia": "Gala",
                               "data_inizio": "2025-11-20", "data_fine": "2025-11-20", "localita": "Palazzo Reale",
                               "citta": "Napoli", "provincia": "NA", "regione": "Campania", "nazione": "Italia",
                               "organizzatore": "CRMEvent Agency", "partecipanti_previsti": 600, "budget": 180000, "stato": "concluso"})

    comps = []
    for nome, sett, tipo in [("TechNova S.p.A.", "Tecnologia", "prospect"), ("BioGusto Srl", "Food & Beverage", "azienda"),
                             ("Moda Italia Group", "Moda", "azienda"), ("AutoDrive Motors", "Automotive", "prospect"),
                             ("FinCore Bank", "Finanza", "azienda"), ("MediaWave", "Media", "azienda"),
                             ("EcoFuture Onlus", "No Profit", "azienda"), ("Cloudbyte Solutions", "Tecnologia", "prospect")]:
        comps.append(await ins("companies", {"nome": nome, "settore": sett, "tipo": tipo, "citta": "Milano",
                                             "provincia": "MI", "regione": "Lombardia", "nazione": "Italia",
                                             "email": f"info@{nome.split()[0].lower()}.it", "telefono": "+39 02 0000000"}))

    persons = []
    for nome, cognome, ruolo, cidx in [("Giulia", "Ferrari", "Marketing Manager", 0), ("Luca", "Esposito", "CEO", 1),
                                       ("Sara", "Colombo", "Sponsorship Lead", 2), ("Andrea", "Romano", "Direttore Vendite", 3),
                                       ("Chiara", "Greco", "Event Manager", 4), ("Matteo", "Bruno", "CFO", 5),
                                       ("Elena", "Gallo", "Responsabile CSR", 6), ("Davide", "Costa", "CTO", 7),
                                       ("Francesca", "Rizzo", "Volontaria", None), ("Simone", "Marino", "Tecnico", None),
                                       ("Mario", "Rossi", "Volontario", None)]:
        persons.append(await ins("persons", {"nome": nome, "cognome": cognome, "ruolo": ruolo,
                                             "email": f"{nome.lower()}.{cognome.lower()}@mail.it", "telefono": "+39 333 0000000",
                                             "azienda_id": comps[cidx] if cidx is not None else None, "citta": "Milano",
                                             "invite_status": "non_invitato"}))

    for cidx, ev, tipo, fase, val, conf, pidx, liv in [
            (0, ev1, "sponsor", "confermato", 60000, 60000, 0, "Gold"), (1, ev2, "partner", "in_trattativa", 25000, 0, 1, None),
            (2, ev1, "sponsor", "proposta_inviata", 40000, 0, 2, "Silver"), (3, ev1, "prospect", "contattato", 30000, 0, 3, None),
            (4, ev1, "sponsor", "confermato", 80000, 80000, 5, "Main Sponsor"), (5, ev2, "partner", "proposta_inviata", 15000, 0, 4, None),
            (7, ev1, "prospect", "prospect", 20000, 0, 7, None), (6, ev2, "sponsor", "in_trattativa", 12000, 0, 6, "Bronze")]:
        await ins("deals", {"azienda_id": comps[cidx], "evento_id": ev, "tipo": tipo, "fase": fase, "valore": val,
                            "valore_confermato": conf, "referente_id": persons[pidx], "livello": liv,
                            "stato": "aperta" if fase not in ("confermato", "perso") else "chiusa"})

    team1 = await ins("teams", {"nome": "Team Ristoro km 20", "evento_id": ev2, "area": "Ristoro",
                                "responsabile_id": persons[8], "descrizione": "Gestione punto ristoro", "luogo_operativo": "Parco Dora - Zona B",
                                "punto_ritrovo": "Ingresso Est ore 08:30"})
    team2 = await ins("teams", {"nome": "Team Expo", "evento_id": ev1, "area": "Expo", "responsabile_id": persons[4],
                                "luogo_operativo": "Hall 3", "punto_ritrovo": "Reception ore 08:00"})

    for pidx, ev, cat, ruolo, area, team, stato, resp in [
            (10, ev2, "volontario", "Accoglienza", "Ristoro", team1, "confermato", "Francesca Rizzo"),
            (8, ev2, "volontario", "Coordinatore", "Ristoro", team1, "confermato", None),
            (9, ev1, "collaboratore", "Tecnico", "Expo", team2, "confermato", "Chiara Greco"),
            (4, ev1, "staff", "Coordinatore", "Expo", team2, "confermato", None),
            (10, ev1, "volontario", "Logistica", None, None, "da_riconfermare", None)]:
        await ins("staff", {"persona_id": persons[pidx], "evento_id": ev, "categoria": cat, "ruolo": ruolo, "area": area,
                            "team_id": team, "stato": stato, "responsabile": resp,
                            "data_arrivo": "2026-07-04" if ev == ev2 else "2026-09-15", "ora_arrivo": "08:30",
                            "data_partenza": "2026-07-06" if ev == ev2 else "2026-09-17", "ora_partenza": "18:00",
                            "punto_ritrovo": "Ingresso Est", "luogo_operativo": "Zona B"})

    for ev, pidx, data, oi, of, area, ruolo, team, luogo in [
            (ev2, 10, "2026-07-04", "09:00", "13:00", "Ristoro", "Accoglienza", team1, "Punto ristoro km 20"),
            (ev2, 10, "2026-07-05", "14:00", "18:00", "Ristoro", "Accoglienza", team1, "Punto ristoro km 20"),
            (ev1, 9, "2026-09-15", "07:00", "15:00", "Expo", "Tecnico", team2, "Hall 3"),
            (ev2, None, "2026-07-06", "09:00", "13:00", "Ristoro", "Accoglienza", team1, "Punto ristoro km 20")]:
        await ins("shifts", {"evento_id": ev, "persona_id": persons[pidx] if pidx is not None else None, "data": data,
                            "ora_inizio": oi, "ora_fine": of, "area": area, "ruolo": ruolo, "team_id": team,
                            "luogo": luogo, "punto_ritrovo": "Ingresso Est"})

    await ins("event_maps", {"evento_id": ev2, "nome": "Percorso Gara", "tipologia": "Percorso",
                             "descrizione": "Tracciato completo 21 km", "google_maps_url": "https://maps.google.com/?q=Parco+Dora+Torino",
                             "team_id": team1, "area": "Ristoro"})
    await ins("event_maps", {"evento_id": ev1, "nome": "Mappa Expo Hall 3", "tipologia": "Mappa Expo",
                             "descrizione": "Disposizione stand", "area": "Expo", "team_id": team2})

    today = datetime.now(timezone.utc).date()
    await ins("activities", {"titolo": "Chiamata sponsor TechNova", "tipo": "chiamata", "evento_id": ev1,
                             "azienda_id": comps[0], "persona_id": persons[0], "data": today.isoformat(), "stato": "da_fare"})
    await ins("activities", {"titolo": "Invio proposta Moda Italia", "tipo": "email", "evento_id": ev1,
                             "azienda_id": comps[2], "persona_id": persons[2], "data": today.isoformat(), "stato": "completata"})
    for tit, ev, cidx, pidx, sc, pr in [
            ("Ricontattare AutoDrive Motors", ev1, 3, 3, (today - timedelta(days=2)).isoformat(), "alta"),
            ("Follow-up proposta CloudByte", ev1, 7, 7, today.isoformat(), "media"),
            ("Confermare budget BioGusto", ev2, 1, 1, (today + timedelta(days=3)).isoformat(), "media"),
            ("Verifica contratto FinCore", ev1, 4, 5, (today - timedelta(days=1)).isoformat(), "alta")]:
        await ins("followups", {"titolo": tit, "evento_id": ev, "azienda_id": comps[cidx], "persona_id": persons[pidx],
                               "scadenza": sc, "priorita": pr, "stato": "aperto"})
    logger.info("Demo data seeded")


async def migrate_person_companies():
    """Idempotent: turn legacy person.azienda_id into person_companies relations."""
    persons = await db.persons.find({"azienda_id": {"$nin": [None, ""]}}, {"_id": 0}).to_list(10000)
    created = 0
    for p in persons:
        exists = await db.person_companies.find_one({"person_id": p["id"], "company_id": p["azienda_id"]})
        if exists:
            continue
        company = await db.companies.find_one({"id": p["azienda_id"]})
        if not company:
            continue
        await _create("person_companies", {"person_id": p["id"], "company_id": p["azienda_id"],
                                            "qualifica": p.get("ruolo"), "ruolo": p.get("ruolo"),
                                            "referente_principale": True, "note": None})
        created += 1
    if created:
        logger.info(f"Migrated {created} person-company relations")


async def migrate_memberships():
    """Idempotent: give org type/status defaults and create memberships for existing
    operational users (admin/user/member). Volunteers/staff are intentionally excluded."""
    await db.organizations.update_many({"type": {"$exists": False}}, {"$set": {"type": "cliente"}})
    await db.organizations.update_many({"status": {"$exists": False}}, {"$set": {"status": "active"}})
    users = await db.users.find({"org_id": {"$nin": [None, ""]}, "role": {"$in": ["admin", "user", "member"]}}, {"_id": 0}).to_list(10000)
    created = 0
    for u in users:
        role = "admin_org" if u.get("role") == "admin" else "user"
        _, made = await _ensure_membership(u["user_id"], u["org_id"], role, u["user_id"])
        if made:
            created += 1
    if created:
        logger.info(f"Migrated {created} memberships")


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.user_sessions.create_index("session_token")
    try:
        await db.memberships.create_index([("user_id", 1), ("org_id", 1)], unique=True)
        await db.memberships.create_index("org_id")
        await db.org_invites.create_index("token")
        await db.org_invites.create_index("org_id")
        await db.audit_logs.create_index("created_at")
    except Exception:
        pass
    for c in ["events", "companies", "persons", "deals", "staff", "teams", "shifts",
              "event_maps", "activities", "followups", "lodgings", "meals",
              "person_companies", "briefing_versions", "files"]:
        try:
            await db[c].create_index("org_id")
        except Exception:
            pass
    try:
        await db.funnel_enrollments.create_index([("funnel_key", 1), ("lead_id", 1)])
        await db.funnel_enrollments.create_index("status")
        await db.brevo_events.create_index("dedupe", unique=True)
        await db.brevo_events.create_index("event")
        await db.leads.create_index("unsub_token")
        await db.brevo_templates.create_index("template_key", unique=True)
        await db.calendar_oauth_pkce.create_index("expires_at", expireAfterSeconds=0)
        await db.calendar_oauth_pkce.create_index([("jti", 1), ("uid", 1)])
    except Exception:
        pass
    try:
        storage_utils.init_storage()
        logger.info("Storage initialized")
    except Exception as e:
        logger.error(f"Storage init failed: {e}")
    await seed_admin()
    await migrate_person_companies()
    await migrate_memberships()
    await seed_support()
    creds = ROOT_DIR.parent / "memory" / "test_credentials.md"
    try:
        creds.write_text(
            f"# Test Credentials\n\n## Super Admin CRMEvent (platform owner, email/password)\n- Email: {os.environ['ADMIN_EMAIL']}\n- Password: {os.environ['ADMIN_PASSWORD']}\n- Role: superadmin (NO organization; manages the platform at /piattaforma)\n\n## Roles\n- superadmin: platform owner (CRMEvent). No org_id. Sees /piattaforma. Cannot access org CRM data.\n- admin: organization admin/owner. Has org_id. Full CRM access for own org only.\n- staff/volunteer: org members, personal area only (/app), linked to a Person via invite.\n\n## Organization signup (self-serve organizer)\n- POST /api/auth/register-organization {{nome, cognome, email, password, org_name, telefono, accept_terms}} -> creates Organization + admin user + 14-day trial\n- POST /api/auth/complete-organization {{org_name, telefono, accept_terms}} -> for Google users without an org\n- Public pages: /prezzi (pricing), /registrati (signup)\n\n## Multi-tenant\n- Every operational document carries org_id; all reads/writes are scoped server-side to the caller's org_id (anti cross-tenant/IDOR).\n\n## Auth endpoints\n- POST /api/auth/login, /api/auth/logout, /api/auth/register-organization, /api/auth/complete-organization\n- POST /api/auth/change-password, /api/auth/forgot-password, /api/auth/reset-password\n- POST /api/auth/activate (invito), /api/auth/session (Google login)\n\n## Notes\n- Google Calendar OAuth requires GOOGLE_CLIENT_ID/SECRET in .env (currently empty).\n- Stripe billing is scaffolded (subscription states + data model) but real payments are NOT active yet.\n"
        )
    except Exception as e:
        logger.warning(f"creds write failed: {e}")


@app.on_event("shutdown")
async def shutdown():
    client.close()


app.include_router(api)
app.add_middleware(CORSMiddleware,
                   allow_origins=[o for o in os.environ.get("CORS_ORIGINS", "").split(",") if o],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
