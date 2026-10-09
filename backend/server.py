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
import contextlib
from collections import defaultdict
import support_service
from datetime import datetime, timezone, timedelta
from typing import Any, List, Optional
from zoneinfo import ZoneInfo

import jwt
import bcrypt
import httpx
from fastapi import FastAPI, APIRouter, Request, Response, HTTPException, Depends, UploadFile, File, Form, Header
from fastapi.responses import RedirectResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field, model_validator

import asyncio
import news
import brevo_org_lists
import email_utils
import permissions as P
import storage_utils
import gcal_utils
import video_support
import subscriptions
import pipeline_seed_sports
import demo_booking
import demo_slots
import text_normalize as TN
import home_widgets
import google_login
import partner_portal
import marketplace
import brevo_funnel
import social_ai
import social_creative
import instagram_utils
import leadfinder_scraper
import seed_leadfinder
import brevo_client
import pipeline_seed

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


SUPPORT_COOKIE = "support_session"
SUPPORT_MINUTES = 30
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _sha(v: str) -> str:
    return hashlib.sha256(v.encode()).hexdigest()


async def _end_support(sa: dict, s: dict, action: str) -> None:
    res = await db.support_sessions.update_one({"id": s["id"], "active": True},
                                               {"$set": {"active": False, "ended_at": now_iso(), "end_reason": action}})
    if res.modified_count:
        await record_audit(sa, action, org_id=s["org_id"], org_name=s.get("org_name"), target_email=s.get("target_email"),
                           target_name=s.get("target_name"), meta={"support_session_id": s["id"], "target_user_id": s["target_user_id"]})


async def _active_support(request: Request, base: dict) -> Optional[dict]:
    """Sessione di assistenza attiva del Super Admin (cookie httpOnly, token salvato solo come hash)."""
    tok = request.cookies.get(SUPPORT_COOKIE)
    if not tok or base.get("role") != "superadmin":
        return None
    s = await db.support_sessions.find_one({"token_hash": _sha(tok), "superadmin_id": base["user_id"], "active": True}, {"_id": 0})
    if not s:
        return None
    if datetime.fromisoformat(s["expires_at"]) <= datetime.now(timezone.utc):
        await _end_support(base, s, "impersonation_expired")
        return None
    return s


async def get_current_user(request: Request) -> dict:
    user = await _get_base_user(request)
    s = await _active_support(request, user)
    if s:
        target = await db.users.find_one({"user_id": s["target_user_id"]}, {"_id": 0, "password_hash": 0})
        if target and target.get("role") != "superadmin":
            if request.method not in SAFE_METHODS:
                path = request.url.path
                if s.get("read_only"):
                    raise HTTPException(status_code=403, detail="Modalità assistenza: account disabilitato, sola lettura")
                if path.startswith("/api/auth/"):
                    raise HTTPException(status_code=403, detail="Modalità assistenza: operazione sull'account non consentita")
                await record_audit(user, "impersonation_action", org_id=s["org_id"], org_name=s.get("org_name"),
                                   target_email=s.get("target_email"), target_name=s.get("target_name"),
                                   detail=f"{request.method} {path}", meta={"support_session_id": s["id"]})
            return {**target, "support": {"session_id": s["id"], "org_id": s["org_id"], "org_name": s.get("org_name"),
                                           "target_user_id": s["target_user_id"],
                                           "read_only": bool(s.get("read_only")), "expires_at": s["expires_at"],
                                           "target_name": s.get("target_name"), "orgs": s.get("orgs") or [],
                                           "superadmin_name": user.get("name") or user.get("email")}}
    if user.get("active") is False:
        raise HTTPException(status_code=403, detail="Accesso disabilitato")
    return user


async def _get_base_user(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    tokens = [t for t in (request.cookies.get("session_token"), request.cookies.get("access_token"),
                          auth[7:] if auth.startswith("Bearer ") else None) if t]
    if not tokens:
        raise HTTPException(status_code=401, detail="Non autenticato")
    for token in tokens:  # un cookie di sessione scaduto non deve oscurare un token valido
        user = await resolve_user_from_token(token)
        if user:
            return user
    raise HTTPException(status_code=401, detail="Sessione non valida o scaduta")


async def _resolve_active_org(request: Request, user: dict):
    """Resolve the effective (org_id, org_role) for this request.
    - Super Admin: any org via server-validated X-Org-Id header (audited impersonation).
    - Operational user: only an org for which an ACTIVE membership exists; the optional
      X-Org-Id header must match one of those memberships, else 403. Defaults to primary.
    Data always stays org-scoped through oq() — no cross-tenant bypass."""
    sup = user.get("support")
    if sup:  # assistenza: contesto fissato dalla sessione, ruolo reale dell'utente (X-Org-Id ignorato)
        m = await db.memberships.find_one({"user_id": user["user_id"], "org_id": sup["org_id"]}, {"_id": 0, "role": 1})
        if not m:
            raise HTTPException(status_code=403, detail="Nessuna organizzazione associata all'account")
        return sup["org_id"], m["role"]
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


PLATFORM_ORG_ID = "__platform__"


async def require_admin(request: Request, user: dict = Depends(get_current_user)) -> dict:
    if request.query_params.get("scope") == "platform":
        if user.get("role") != "superadmin":
            raise HTTPException(status_code=403, detail="Accesso riservato al Super Admin CRMEvent")
        return {**user, "org_id": PLATFORM_ORG_ID, "org_role": "superadmin",
                "acting_org": PLATFORM_ORG_ID, "platform_scope": True}
    org_id, org_role = await _resolve_active_org(request, user)
    perm = await _enforce_perm(request, user, org_id, org_role)
    await _enforce_plan(request, org_id, org_role)
    return {**user, "org_id": org_id, "org_role": org_role, "acting_org": org_id, "perm": perm}


SAAS: dict = {}
MKT: dict = {}


async def _enforce_plan(request: Request, org_id: str, org_role: str) -> None:
    """Funzionalità incluse nel piano + sola lettura a prova/abbonamento terminati (Super Admin escluso)."""
    if org_role == "superadmin" or not SAAS:
        return
    st = await SAAS["state_for"](org_id)
    if not st.get("enabled"):
        return
    tpl = getattr(request.scope.get("route"), "path", "") or ""
    tpl = tpl[4:] if tpl.startswith("/api") else tpl
    secs, _ = P.route_rule(tpl, request.method)
    SAAS["check"](st, secs, request.method, tpl)


# Collezioni con id di oggetto collegato a un evento: (param path, collezione, campo evento)
_CRUD_EVENT_COLL = {"deals": "deals", "staff": "staff", "teams": "teams", "shifts": "shifts",
                    "maps": "event_maps", "activities": "activities", "followups": "followups",
                    "lodgings": "lodgings", "meals": "meals"}
_OBJ_EVENT_PARAMS = {"task_id": ("pipeline_tasks", "event_id"), "cat_id": ("pipeline_categories", "event_id"),
                     "version_id": ("briefing_versions", "evento_id"), "aid": ("availabilities", "evento_id")}


async def _enforce_perm(request: Request, user: dict, org_id: str, org_role: str) -> dict:
    """Unico punto di controllo permessi per sezione/azione/evento (server-side, fail-closed)."""
    if org_role in ("admin_org", "superadmin"):
        return {"admin": True, "event_ids": None}
    mq = {"user_id": user["user_id"], "org_id": org_id} if user.get("support") else {"user_id": user["user_id"], "org_id": org_id, "active": True}
    mem = await db.memberships.find_one(mq, {"_id": 0, "role": 1, "permissions": 1, "persona_id": 1}) or {"role": org_role}
    eff = P.effective(mem)
    if eff.get("admin"):
        return {"admin": True, "event_ids": None}
    route = request.scope.get("route")
    tpl = getattr(route, "path", "") or ""
    tpl = tpl[4:] if tpl.startswith("/api") else tpl
    secs, action = P.route_rule(tpl, request.method)
    led = await _led_team_ids(user, org_id, mem.get("persona_id"))
    via_tl = False
    if secs is None or not P.allows(eff, secs, action):
        # Nomina Team Leader: accesso limitato ai soli Team guidati (revocato appena cambia il Team Leader)
        if led and P.tl_allows(eff, tpl, action):
            via_tl = True
        elif secs is None:
            raise HTTPException(status_code=403, detail="Funzione riservata all'Admin Organizzatore")
        else:
            raise HTTPException(status_code=403, detail="Non hai i permessi per questa operazione")
    ids = None if eff["events"] == "all" else list(eff["events"])
    team_ids = list(led) if via_tl else await _allowed_team_ids(user, org_id, eff.get("teams") or {}, mem.get("persona_id"), led)
    perm = {"admin": False, "role": eff["role"], "sections": eff["sections"], "event_ids": ids, "team_ids": team_ids,
            "teams": eff.get("teams") or {}, "send_invites": eff.get("send_invites", False),
            "marketplace_purchase": eff.get("marketplace_purchase", False),
            "team_leader": eff.get("team_leader") or {}, "led_team_ids": led, "via_tl": via_tl}
    pp = request.path_params
    nf = HTTPException(status_code=404, detail="Elemento non trovato")
    seg = tpl.split("/")[1] if tpl.count("/") >= 1 else ""
    if team_ids is not None and "item_id" in pp:
        if seg == "teams" and pp["item_id"] not in team_ids:
            raise nf
        if seg in ("staff", "shifts"):
            doc = await db[seg].find_one({"org_id": org_id, "id": pp["item_id"]}, {"_id": 0, "team_id": 1})
            # Staff/volontari senza Team: visibili e assegnabili (GET/PUT) al proprio Team, non eliminabili
            free = not via_tl and seg == "staff" and doc is not None and not doc.get("team_id") and request.method in ("GET", "PUT")
            if doc and not free and doc.get("team_id") not in team_ids:
                raise nf
    if team_ids is not None and "aid" in pp:
        a = await db.availabilities.find_one({"org_id": org_id, "id": pp["aid"]}, {"_id": 0, "persona_id": 1, "evento_id": 1})
        if a and a.get("persona_id") not in await _team_person_ids(org_id, team_ids, via_tl, a.get("evento_id")):
            raise nf
    if team_ids is not None and "person_id" in pp and request.method == "GET":
        if pp["person_id"] not in await _person_scope({**user, "org_id": org_id, "perm": perm}):
            raise HTTPException(status_code=404, detail="Persona non trovata")
    if ids is None:
        return perm
    eid = pp.get("event_id") or request.query_params.get("evento_id") or request.query_params.get("event_id")
    if eid and eid not in ids:
        raise nf
    checks = []
    if "item_id" in pp:
        if seg == "events" and pp["item_id"] not in ids:
            raise nf
        if seg in _CRUD_EVENT_COLL:
            checks.append((_CRUD_EVENT_COLL[seg], "evento_id", "id", pp["item_id"]))
    if "rec_id" in pp and seg in ("activities", "followups"):
        checks.append((seg, "evento_id", "id", pp["rec_id"]))
    if "gruppo_id" in pp:
        checks.append(("lodgings" if request.query_params.get("tipo") == "lodging" else "meals", "evento_id", "gruppo_id", pp["gruppo_id"]))
    for k, (coll, field) in _OBJ_EVENT_PARAMS.items():
        if k in pp:
            checks.append((coll, field, "id", pp[k]))
    for coll, field, key, val in checks:
        doc = await db[coll].find_one({"org_id": org_id, key: val}, {"_id": 0, field: 1})
        if doc and doc.get(field) and doc[field] not in ids:
            raise nf
    return perm


async def _led_team_ids(user: dict, org_id: str, persona_id: Optional[str] = None) -> list:
    """Team di cui l'utente è Team Leader (persona collegata all'account o con la stessa email)."""
    em = (user.get("email") or "").strip()
    pids = await db.persons.distinct("id", {"org_id": org_id, "email": {"$regex": f"^{re.escape(em)}$", "$options": "i"}}) if em else []
    if persona_id:
        pids = list(set(pids) | {persona_id})
    return sorted(await db.teams.distinct("id", {"org_id": org_id, "responsabile_id": {"$in": pids}})) if pids else []


async def _allowed_team_ids(user: dict, org_id: str, tp: dict, persona_id: Optional[str] = None, led: Optional[list] = None):
    """None = tutti i Team; altrimenti Team di cui è Team Leader (persona collegata o stessa email) + selezionati."""
    scope = tp.get("scope") or "all"
    if scope == "all":
        return None
    if led is None:
        led = await _led_team_ids(user, org_id, persona_id)
    sel = tp.get("ids") or [] if scope == "selected" else []
    return sorted(set(led) | set(sel))


MEMBER_CATS = ("staff", "collaboratore", "volontario")


async def _team_person_ids(org_id: str, team_ids: list, strict: bool, evento_id: Optional[str] = None) -> set:
    """Persone nei Team indicati (strict=False: anche presenze senza Team, regola esistente)."""
    allowed = list(team_ids) + ([] if strict else [None, ""])
    q = {"org_id": org_id, "team_id": {"$in": allowed}}
    if evento_id:
        q["evento_id"] = evento_id
    return set(await db.staff.distinct("persona_id", q))


async def _person_scope(user: dict) -> Optional[set]:
    """None = nessun limite; altrimenti persone visibili: componenti dei Team accessibili + contatti non Staff se ha Anagrafiche."""
    p = user.get("perm") or {"admin": True}
    tids = p.get("team_ids")
    if p.get("admin") or tids is None:
        return None
    vis = await _team_person_ids(user["org_id"], tids, p.get("via_tl"))
    if _can(user, "anagrafiche"):
        staffed = set(await db.staff.distinct("persona_id", {"org_id": user["org_id"], "categoria": {"$in": list(MEMBER_CATS)}}))
        vis |= set(await db.persons.distinct("id", {"org_id": user["org_id"], "id": {"$nin": list(staffed)}}))
    return vis


def _link_visible(user: dict, link: dict) -> bool:
    p = user.get("perm") or {"admin": True}
    tids = p.get("team_ids")
    if p.get("admin") or tids is None:
        return True
    return link.get("team_id") in tids or (not p.get("via_tl") and not link.get("team_id"))


def _team_ids(user: dict):
    return (user.get("perm") or {}).get("team_ids")


def _assert_team_allowed(user: dict, team_id: Optional[str]) -> None:
    tids = _team_ids(user)
    if tids is not None and team_id and team_id not in tids:
        raise HTTPException(status_code=404, detail="Team non trovato")


def _can(user: dict, section: str, action: str = "view") -> bool:
    p = user.get("perm") or {"admin": True}
    return P.allows(p, (section,), action)


def _ev_ids(user: dict):
    return (user.get("perm") or {}).get("event_ids")


def _assert_ev_allowed(user: dict, eid: Optional[str]) -> None:
    ids = _ev_ids(user)
    if ids is not None and eid and eid not in ids:
        raise HTTPException(status_code=404, detail="Evento non trovato")


def _ev_scope(user: dict, field: str = "evento_id") -> dict:
    """Filtro Mongo per utenti limitati a eventi selezionati (record senza evento restano visibili)."""
    ids = _ev_ids(user)
    return {} if ids is None else {field: {"$in": ids + [None, ""]}}


async def require_org_admin(request: Request, user: dict = Depends(get_current_user)) -> dict:
    if request.query_params.get("scope") == "platform":
        if user.get("role") != "superadmin":
            raise HTTPException(status_code=403, detail="Accesso riservato al Super Admin CRMEvent")
        return {**user, "org_id": PLATFORM_ORG_ID, "org_role": "superadmin",
                "acting_org": PLATFORM_ORG_ID, "platform_scope": True}
    org_id, org_role = await _resolve_active_org(request, user)
    if org_role not in ("admin_org", "superadmin"):
        raise HTTPException(status_code=403, detail="Riservato agli amministratori dell'organizzazione")
    await _enforce_plan(request, org_id, org_role)
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
                "access": "full", "account_plan": "internal", "effective_plan": "premium",
                "price_monthly": PRICE_MONTHLY, "price_yearly": PRICE_YEARLY,
                "org_type": otype}
    status = sub.get("status", "trial")
    trial_end = sub.get("trial_end")
    period_end = sub.get("current_period_end")
    ref = trial_end if status == "trial" else period_end
    days_left = _days_left(ref)
    if status == "trial" and days_left <= 0:
        status = "expired"
    active = status == "active" or (status == "trial" and days_left > 0)
    # FASE 2: account_plan (stato account) + effective_plan (piano attivo effettivo).
    # Durante il trial l'utente prova tutte le funzionalità PREMIUM; alla scadenza → sola lettura.
    account_plan = "trial" if status == "trial" else ("customer" if status == "active" else "free")
    if status == "trial" and active:
        effective_plan = "premium"
    elif status == "active":
        effective_plan = "premium"  # legacy ricorrente in grace finché non migrato (FASE 2 Stripe)
    else:
        effective_plan = "free"
    return {"status": status, "plan": sub.get("plan", "crmevent"),
            "billing_cycle": sub.get("billing_cycle"), "trial_end": trial_end,
            "current_period_end": period_end, "days_left": days_left,
            "access": "full" if active else "limited",
            "account_plan": account_plan, "effective_plan": effective_plan,
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
    org = {"id": new_id(), "nome": TN.business_name(name), "type": org_type, "status": status,
           "owner_user_id": owner_user_id, "subscription": sub,
           "created_at": now_iso(), "updated_at": now_iso()}
    await db.organizations.insert_one(org)
    if org_type == "cliente":
        await SAAS["init_trial"](org["id"], owner_user_id)  # nuovo modello: prova GOLD, nessun bonus crediti
    else:
        await _grant_signup_bonus(org["id"], org.get("nome"))
    return org


async def _ensure_membership(user_id: str, org_id: str, role: str, added_by: Optional[str] = None):
    if await db.users.find_one({"user_id": user_id, "role": "superadmin"}, {"_id": 1}):
        return None, False  # il Super Admin opera sulle organizzazioni senza diventarne membro
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
    data = TN.normalize_fields(coll, data)
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
    clean = {k: v for k, v in TN.normalize_fields(coll, data).items() if v is not None}
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


def _user_has_phone(u: dict) -> bool:
    return bool((u.get("telefono") or u.get("cellulare") or "").strip())


async def user_payload(u: dict, active_org_id: Optional[str] = None) -> dict:
    base = public_user(u)
    role = u.get("role")
    base["needs_phone"] = (role != "superadmin") and not _user_has_phone(u)
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
    perm_by_org = {}
    for m in mems:
        org = await db.organizations.find_one({"id": m["org_id"]}, {"_id": 0})
        if not org or org.get("status") == "disabled":
            continue
        perm_by_org[org["id"]] = P.effective(m)
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
    base["permissions"] = perm_by_org.get(chosen["org_id"])
    cm = next((m for m in mems if m["org_id"] == chosen["org_id"]), {})
    base["led_team_ids"] = [] if chosen["role"] == "admin_org" else await _led_team_ids(u, chosen["org_id"], cm.get("persona_id"))
    base["org_type"] = chosen["type"]
    base["subscription"] = _sub_summary(org)
    base["welcome_demo"] = u.get("welcome_demo") if chosen["role"] == "admin_org" else None
    base["saas"] = subscriptions.org_state(org, await SAAS["get_config"]())
    base["saas_usage"] = await SAAS["usage"](chosen["org_id"]) if base["saas"].get("enabled") and chosen["role"] == "admin_org" else None
    return base


import phonenumbers


def _normalize_phone(value: Optional[str], *, required: bool = True) -> Optional[str]:
    """Valida e normalizza un cellulare in formato E.164 (es. +393331234567). Richiede il prefisso
    internazionale. Solleva 400 con messaggio uniforme se obbligatorio e mancante/non valido."""
    v = (value or "").strip()
    if not v:
        if required:
            raise HTTPException(status_code=400, detail="Inserisci un numero di cellulare valido.")
        return None
    try:
        num = phonenumbers.parse(v, None)
        if not phonenumbers.is_valid_number(num):
            raise ValueError("invalid")
        return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
    except Exception:
        raise HTTPException(status_code=400, detail="Inserisci un numero di cellulare valido.")


class OrgRegisterIn(BaseModel):
    nome: str
    cognome: Optional[str] = None
    email: EmailStr
    password: str
    org_name: str
    telefono: Optional[str] = None
    accept_terms: bool = False
    ref: Optional[dict] = None


class CompleteOrgIn(BaseModel):
    org_name: str
    telefono: Optional[str] = None
    accept_terms: bool = False
    nome: Optional[str] = None
    cognome: Optional[str] = None
    marketing_consent: bool = False
    ref: Optional[dict] = None


TERMS_VERSION = "2026-10"


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
    phone = _normalize_phone(body.telefono)
    uid = f"user_{uuid.uuid4().hex[:12]}"
    org = await _create_organization(body.org_name.strip(), uid)
    body.nome, body.cognome = TN.person_name(body.nome), TN.person_name(body.cognome)
    full_name = f"{body.nome} {body.cognome or ''}".strip()
    await db.users.insert_one({"user_id": uid, "email": email, "name": full_name,
                               "nome": body.nome, "cognome": body.cognome, "registered_at": now_iso(),
                               "password_hash": hash_password(body.password), "role": "admin",
                               "auth_provider": "password", "org_id": org["id"], "telefono": phone,
                               "picture": "", "active": True, "accepted_terms_at": now_iso(), "created_at": now_iso(),
                               "self_registered": True, "welcome_demo": "pending"})
    await _ensure_membership(uid, org["id"], "admin_org", uid)
    await PARTNER["attach_referral"](org["id"], org.get("nome"), {"email": email, "telefono": phone}, body.ref)
    # Lead continuity: if this email already requested a demo, link that lead to the new account
    # (no duplicate contact) and advance the funnel — preserving the lead → demo → trial history.
    lead = await db.leads.find_one({"email": email})
    if lead:
        await db.leads.update_one({"id": lead["id"]}, {"$set": {"user_id": uid,
            "funnel_status": "trial_started", "funnel_ts_trial_started": now_iso(), "updated_at": now_iso()}})
        await _sync_brevo_funnel_status(email, "trial_started")
        # Immediate STOP: close the active demo enrollment so emails 2/3/4 never fire post-conversion.
        await _stop_active_demo_enrollment(lead["id"], "trial_started")
    try:
        await sync_registered_user(uid, org["id"], nome=body.nome, cognome=body.cognome, source="registration")
    except Exception as e:
        logger.error(f"registered-user sync error: {e}")
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
    nome, cognome = TN.person_name((body.nome or "").strip()), TN.person_name((body.cognome or "").strip())
    if body.nome is not None and not nome:
        raise HTTPException(status_code=400, detail="Il nome è obbligatorio")
    phone = _normalize_phone(body.telefono)
    if await db.memberships.find_one({"user_id": user["user_id"], "active": True}, {"_id": 1}):
        raise HTTPException(status_code=400, detail="Il tuo account è già collegato a un'organizzazione")
    # Blocco atomico anti doppio clic: una sola creazione organizzazione per utente.
    locked = await db.users.find_one_and_update(
        {"user_id": user["user_id"], "$or": [{"org_id": {"$exists": False}}, {"org_id": None}, {"org_id": ""}], "org_onboarding_lock": {"$ne": True}},
        {"$set": {"org_onboarding_lock": True}})
    if not locked:
        raise HTTPException(status_code=409, detail="Registrazione già in corso o completata. Ricarica la pagina.")
    try:
        org = await _create_organization(body.org_name.strip(), user["user_id"])
    except Exception:
        await db.users.update_one({"user_id": user["user_id"]}, {"$unset": {"org_onboarding_lock": ""}})
        raise
    now = now_iso()
    upd = {"org_id": org["id"], "role": "admin", "telefono": phone, "self_registered": True, "registered_at": now,
           "accepted_terms_at": now, "terms_version": TERMS_VERSION, "privacy_version": TERMS_VERSION,
           "marketing_consent": bool(body.marketing_consent), "marketing_consent_at": now if body.marketing_consent else None,
           "welcome_demo": "pending"}
    if nome:
        upd.update({"nome": nome, "cognome": cognome or None, "name": f"{nome} {cognome}".strip()})
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": upd, "$unset": {"org_onboarding_lock": ""}})
    await _ensure_membership(user["user_id"], org["id"], "admin_org", user["user_id"])
    await PARTNER["attach_referral"](org["id"], org.get("nome"), {"email": user.get("email"), "telefono": phone}, body.ref)
    try:
        await sync_registered_user(user["user_id"], org["id"], nome=nome or None, cognome=cognome or None, source="registration")
    except Exception as e:
        logger.error(f"registered-user sync error: {e}")
    u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    return await user_payload(u)


class CompleteProfileIn(BaseModel):
    telefono: Optional[str] = None


@api.post("/auth/complete-profile")
async def complete_profile(body: CompleteProfileIn, user: dict = Depends(get_current_user)):
    """Completamento profilo: il cellulare (E.164) è obbligatorio per qualunque account attivo
    (nuovo Google, Google su invito, anagrafiche legacy senza cellulare). Non crea org, trial o
    crediti e non altera il ruolo/organizzazione. Sincronizza Brevo solo per utenti registrati
    (membri di un'organizzazione), includendo CELLULARE."""
    if user.get("role") == "superadmin":
        raise HTTPException(status_code=400, detail="Il Super Admin non richiede questo passaggio")
    phone = _normalize_phone(body.telefono)
    full = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0}) or {}
    upd = {"telefono": phone}
    if not full.get("registered_at"):
        upd["registered_at"] = now_iso()
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": upd})
    mem = await db.memberships.find_one({"user_id": user["user_id"], "active": True}, {"_id": 0})
    if mem and mem.get("org_id"):
        try:
            await sync_registered_user(user["user_id"], mem["org_id"], source="profile_completion")
        except Exception as e:
            logger.error(f"registered-user sync error: {e}")
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
    response.delete_cookie("session_token", path="/", secure=True, samesite="none")
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
        await db.users.insert_one({"user_id": uid, "email": email, "name": TN.person_name(data.get("name")) or email,
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
    sup = user.get("support")
    out = await user_payload(user, sup["org_id"] if sup else request.headers.get("X-Org-Id"))
    if sup:
        out["support"] = sup
    return out


@api.post("/auth/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if token:
        await db.user_sessions.delete_one({"session_token": token})
    response.delete_cookie("session_token", path="/")
    response.delete_cookie("access_token", path="/")
    sup = request.cookies.get(SUPPORT_COOKIE)
    if sup:
        s = await db.support_sessions.find_one({"token_hash": _sha(sup), "active": True}, {"_id": 0})
        if s:
            sa = await db.users.find_one({"user_id": s["superadmin_id"]}, {"_id": 0, "password_hash": 0}) or {}
            await _end_support(sa, s, "impersonation_ended")
        response.delete_cookie(SUPPORT_COOKIE, path="/", secure=True, samesite="none")
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
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {**upd, "last_login_at": now_iso()}})
    if user.get("person_id"):
        await db.persons.update_one({"id": user["person_id"]}, {"$set": {"invite_status": "account_attivato", "invite_accepted_at": now_iso(), "updated_at": now_iso()}})
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
    data_inizio_allestimento: Optional[str] = None
    data_inizio: Optional[str] = None
    data_fine: Optional[str] = None
    data_fine_disallestimento: Optional[str] = None
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
    giorni_descrizioni: Optional[dict] = None

    @model_validator(mode="after")
    def _check_dates(self):
        seq = [("Data inizio allestimento", self.data_inizio_allestimento),
               ("Data inizio evento", self.data_inizio),
               ("Data fine evento", self.data_fine),
               ("Data fine disallestimento", self.data_fine_disallestimento)]
        prev = None
        for label, val in seq:
            if val:
                if prev and val < prev[1]:
                    raise ValueError(f"{label} non può essere precedente a {prev[0]}")
                prev = (label, val)
        # Descrizioni giornata: mantieni solo le date comprese nell'intervallo evento e non vuote.
        if self.giorni_descrizioni is not None and self.data_inizio:
            di = self.data_inizio[:10]
            df = (self.data_fine or self.data_inizio)[:10]
            self.giorni_descrizioni = {
                k[:10]: str(v).strip() for k, v in self.giorni_descrizioni.items()
                if v and str(v).strip() and di <= k[:10] <= df
            }
        return self


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
    codice_fiscale: Optional[str] = None
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
    servizio_ospitalita: Optional[str] = None
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
    volontari_richiesti: Optional[int] = Field(None, ge=0, le=100000)  # fabbisogno inserito dall'Admin


TEAM_RINUNCIA = {"rinunciato", "non_disponibile"}


def _team_coverage(teams: list, staff: list) -> dict:
    """Fabbisogno volontari: assegnati = presenze volontario (non rinunciate) con team_id del team."""
    tot = {"volontari_richiesti": 0, "volontari_assegnati": 0, "volontari_mancanti": 0, "volontari_esubero": 0}
    for t in teams:
        req = t.get("volontari_richiesti")
        if req is None:
            continue
        n = len({s["persona_id"] for s in staff if s.get("team_id") == t["id"] and s.get("categoria") == "volontario"
                 and s.get("stato") not in TEAM_RINUNCIA and s.get("persona_id")})
        tot["volontari_richiesti"] += req
        tot["volontari_assegnati"] += n
        tot["volontari_mancanti"] += max(req - n, 0)
        tot["volontari_esubero"] += max(n - req, 0)
    return tot


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
    responsabile_id: Optional[str] = None


class Followup(BaseModel):
    titolo: str
    evento_id: Optional[str] = None
    azienda_id: Optional[str] = None
    persona_id: Optional[str] = None
    scadenza: Optional[str] = None
    priorita: Optional[str] = "media"
    stato: Optional[str] = "aperto"
    note: Optional[str] = None
    responsabile_id: Optional[str] = None


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
    numero_camera: Optional[str] = None  # stessa struttura + stesso numero = stessa camera (date per persona)
    compagni_camera: Optional[str] = None
    occupanti: Optional[List[dict]] = None  # [{persona_id|None, nome}] — occupanti della camera (multi)
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
    data: Optional[str] = None  # legacy: data singola (retrocompatibile → data_inizio)
    data_inizio: Optional[str] = None
    data_fine: Optional[str] = None
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

    @model_validator(mode="after")
    def _meal_dates(self):
        # Retrocompatibilità: vecchia 'data' singola → data_inizio = data_fine
        if self.data and not self.data_inizio:
            self.data_inizio = self.data
        if self.data_inizio and not self.data_fine:
            self.data_fine = self.data_inizio
        if self.data_inizio and self.data_fine and self.data_fine < self.data_inizio:
            raise ValueError("La data di fine non può precedere la data di inizio")
        # Mantieni 'data' allineata all'inizio per i consumatori legacy
        if self.data_inizio and not self.data:
            self.data = self.data_inizio
        return self


def _normalize_meals(meals: list) -> None:
    """Assicura che ogni pasto esponga data_inizio/data_fine (retrocompat con 'data' singola).
    Calcolato in lettura: NON altera i record vecchi nel DB."""
    for m in meals:
        di = m.get("data_inizio") or m.get("data")
        m["data_inizio"] = di
        m["data_fine"] = m.get("data_fine") or di
        if not m.get("data"):
            m["data"] = di


_MEAL_ORDER = {"colazione": 0, "pranzo": 1, "cena": 2}


def _days_between(start: str, end: str) -> list:
    try:
        d0 = datetime.strptime(start[:10], "%Y-%m-%d").date()
        d1 = datetime.strptime((end or start)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return [start] if start else []
    out = []
    while d0 <= d1 and len(out) < 60:
        out.append(d0.isoformat())
        d0 += timedelta(days=1)
    return out


def _briefing_meals(meals: list, esig_by_person: dict) -> list:
    """Pasti raggruppati per data -> servizio -> luogo/orario. Solo conteggi, nessun nominativo."""
    groups = {}
    for m in meals:
        s = m.get("struttura") or {}
        luogo = s.get("nome") or m.get("struttura_nome") or m.get("luogo") or ""
        place_key = m.get("struttura_id") or luogo.strip().lower()
        tipo = (m.get("tipo_pasto") or "").lower()
        for day in (_days_between(m.get("data_inizio"), m.get("data_fine")) if m.get("data_inizio") else [""]):
            k = (day, tipo, place_key, m.get("orario") or "")
            g = groups.get(k)
            if not g:
                g = groups[k] = {
                    "data": day, "tipo_pasto": tipo, "luogo": luogo or None,
                    "tipologia_servizio": m.get("tipologia_servizio"),
                    "indirizzo": ", ".join([x for x in [s.get("indirizzo") or m.get("indirizzo"), s.get("citta")] if x]) or None,
                    "orario": m.get("orario") or None,
                    "referente": m.get("referente") or s.get("referente"),
                    "telefono": m.get("telefono") or s.get("telefono_referente") or s.get("telefono"),
                    "google_maps_url": s.get("google_maps_url"),
                    "_note": [], "_persone": set(), "_esig": defaultdict(int),
                }
            if m.get("note") and m["note"] not in g["_note"]:
                g["_note"].append(m["note"])
            pid = m.get("persona_id")
            if pid and pid not in g["_persone"]:
                g["_persone"].add(pid)
                for e in esig_by_person.get(pid) or []:
                    g["_esig"][e] += 1
    by_day = defaultdict(list)
    for g in groups.values():
        by_day[g["data"]].append(g)
    out = []
    for day in sorted(by_day.keys(), key=lambda d: (d == "", d)):
        servizi = defaultdict(list)
        for g in by_day[day]:
            servizi[g["tipo_pasto"]].append({
                **{k: v for k, v in g.items() if not k.startswith("_") and k not in ("data", "tipo_pasto")},
                "note": " · ".join(g["_note"]) or None, "persone": len(g["_persone"]),
                "esigenze": dict(sorted(g["_esig"].items())),
            })
        out.append({"data": day or None, "servizi": [
            {"tipo_pasto": t or None, "entries": sorted(servizi[t], key=lambda e: (e.get("orario") or "", (e.get("luogo") or "").lower()))}
            for t in sorted(servizi.keys(), key=lambda t: (_MEAL_ORDER.get(t, 9), t))
        ]})
    return out


def _briefing_lodgings(lodgings: list, persons: dict) -> list:
    """Ospitalità: Struttura -> Camera -> Ospiti, ognuno con le PROPRIE date (check-in/out per persona)."""
    structs = {}
    for l in lodgings:
        p = persons.get(l.get("persona_id"))
        if not p:
            continue
        s = l.get("struttura") or {}
        nome = s.get("nome") or l.get("struttura_nome") or "Struttura da definire"
        skey = l.get("struttura_id") or nome.strip().lower()
        st = structs.get(skey)
        if not st:
            st = structs[skey] = {
                "nome": nome, "tipologia": s.get("tipologia") or l.get("tipo_struttura"),
                "indirizzo": ", ".join([x for x in [s.get("indirizzo") or l.get("indirizzo"), s.get("citta")] if x]) or None,
                "telefono": s.get("telefono") or l.get("telefono"),
                "referente": s.get("referente") or l.get("referente"),
                "telefono_referente": s.get("telefono_referente"),
                "note": s.get("note"), "google_maps_url": s.get("google_maps_url"),
                "_rooms": {}, "_seen": set(),
            }
        num = (l.get("numero_camera") or "").strip()
        room = st["_rooms"].setdefault(num.lower(), {"numero": num or None, "tipo_camera": None, "ospiti": []})
        room["tipo_camera"] = room["tipo_camera"] or l.get("tipo_camera")
        room["ospiti"].append({"nome": p.get("nome"), "cognome": p.get("cognome"),
                               "check_in": l.get("check_in"), "check_out": l.get("check_out")})
        st["_seen"].add((num.lower(), l["persona_id"]))
        # Ospiti esterni (non in anagrafica) indicati come occupanti: stesse date della prenotazione
        if num:
            for o in l.get("occupanti") or []:
                if not o.get("persona_id") and o.get("nome") and (num.lower(), "ext:" + o["nome"].lower()) not in st["_seen"]:
                    st["_seen"].add((num.lower(), "ext:" + o["nome"].lower()))
                    room["ospiti"].append({"nome": o["nome"], "cognome": "", "esterno": True,
                                           "check_in": l.get("check_in"), "check_out": l.get("check_out")})
    out = []
    for st in sorted(structs.values(), key=lambda x: x["nome"].lower()):
        rooms = st.pop("_rooms")
        st.pop("_seen")
        for r in rooms.values():
            r["ospiti"].sort(key=lambda o: ((o.get("cognome") or "").lower(), (o.get("nome") or "").lower()))
        def rkey(n):
            return (int(n), "") if n.isdigit() else (10**9, n)
        st["camere"] = [rooms[k] for k in sorted([k for k in rooms if k], key=rkey)]
        st["da_assegnare"] = rooms[""]["ospiti"] if "" in rooms else []
        out.append(st)
    return out


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
        if coll == "events" and _ev_ids(user) is not None:
            q["id"] = {"$in": _ev_ids(user)}
        elif coll in _CRUD_EVENT_COLL.values():
            q.update(_ev_scope(user))
        if _team_ids(user) is not None and coll in ("teams", "staff", "shifts"):
            strict = (user.get("perm") or {}).get("via_tl")
            q["id" if coll == "teams" else "team_id"] = {"$in": _team_ids(user) + ([None, ""] if coll == "staff" and not strict else [])}
        if coll == "persons":
            scope = await _person_scope(user)
            if scope is not None:
                q["id"] = {"$in": list(scope)}
        if evento_id:
            q["evento_id"] = evento_id
        return await _list(coll, q)

    @api.post(f"/{path}", name=f"create_{path}")
    async def _c(body: model, user: dict = Depends(require_admin)):
        data = body.model_dump()
        data["org_id"] = user["org_id"]
        if coll == "events" and _ev_ids(user) is not None:
            raise HTTPException(status_code=403, detail="Puoi operare solo sugli eventi assegnati: non puoi creare nuovi eventi")
        if coll != "events":
            _assert_ev_allowed(user, data.get("evento_id"))
        if _team_ids(user) is not None and coll in ("teams", "staff", "shifts"):
            if coll == "teams":
                raise HTTPException(status_code=403, detail="Puoi operare solo sui Team assegnati: non puoi creare nuovi Team")
            if data.get("team_id") not in _team_ids(user):
                raise HTTPException(status_code=403, detail="Seleziona uno dei Team a cui hai accesso")
        if coll == "events":
            await SAAS["check_limit"](user["org_id"], "events")
        else:
            await _assert_org_operational(user["org_id"])
            if data.get("evento_id"):
                await _assert_event_operational(user["org_id"], data["evento_id"])
            if coll == "staff":
                await SAAS["check_people"](user["org_id"], data.get("persona_id"))
        return await _create(coll, data)

    @api.get(f"/{path}/{{item_id}}", name=f"get_{path}")
    async def _g(item_id: str, user: dict = Depends(require_admin)):
        doc = await db[coll].find_one(oq(user, id=item_id), {"_id": 0})
        if doc and coll == "persons":
            scope = await _person_scope(user)
            if scope is not None and item_id not in scope:
                doc = None
        if not doc:
            raise HTTPException(status_code=404, detail="Elemento non trovato")
        return doc

    @api.put(f"/{path}/{{item_id}}", name=f"update_{path}")
    async def _u(item_id: str, body: upd_model, user: dict = Depends(require_admin)):
        clean = {k: v for k, v in TN.normalize_fields(coll, body.model_dump(exclude_unset=True)).items() if v is not None}
        clean["updated_at"] = now_iso()
        await _assert_org_operational(user["org_id"])
        _assert_ev_allowed(user, clean.get("evento_id"))
        if coll in ("staff", "shifts"):
            _assert_team_allowed(user, clean.get("team_id"))
        if coll == "staff" and "team_id" in clean and not (user.get("perm") or {"admin": True}).get("admin"):
            cur = await db.staff.find_one({"org_id": user["org_id"], "id": item_id}, {"_id": 0, "categoria": 1, "team_id": 1}) or {}
            if cur.get("team_id") != clean["team_id"]:
                flag = "manage_volunteers" if (clean.get("categoria") or cur.get("categoria")) == "volontario" else "manage_staff"
                if (user["perm"].get("teams") or {}).get(flag, True) is False:
                    raise HTTPException(status_code=403, detail="Non hai il permesso di gestire " + ("i volontari" if flag == "manage_volunteers" else "lo staff") + " dei Team")
        if coll != "events":
            if clean.get("evento_id"):
                await _assert_event_operational(user["org_id"], clean["evento_id"])
            else:
                existing = await db[coll].find_one(oq(user, id=item_id), {"_id": 0, "evento_id": 1})
                if existing and existing.get("evento_id"):
                    await _assert_event_operational(user["org_id"], existing["evento_id"])
        old_ev = None
        if coll == "events":
            old_ev = await db[coll].find_one(oq(user, id=item_id), {"_id": 0, "data_inizio": 1, "data_fine": 1})
        res = await db[coll].update_one(oq(user, id=item_id), {"$set": clean})
        if res.matched_count == 0:
            raise HTTPException(status_code=404, detail="Elemento non trovato")
        if coll == "events" and old_ev and ("data_inizio" in clean or "data_fine" in clean):
            new_di = clean.get("data_inizio", old_ev.get("data_inizio"))
            new_df = clean.get("data_fine", old_ev.get("data_fine"))
            if old_ev.get("data_inizio") != new_di or old_ev.get("data_fine") != new_df:
                await record_audit(user, "event_date_change", org_id=user["org_id"],
                                   meta={"event_id": item_id,
                                         "from": {"data_inizio": old_ev.get("data_inizio"), "data_fine": old_ev.get("data_fine")},
                                         "to": {"data_inizio": new_di, "data_fine": new_df}})
        return await db[coll].find_one(oq(user, id=item_id), {"_id": 0})

    @api.delete(f"/{path}/{{item_id}}", name=f"delete_{path}")
    async def _d(item_id: str, user: dict = Depends(require_admin)):
        await _assert_org_operational(user["org_id"])
        await db[coll].delete_one(oq(user, id=item_id))
        if coll == "teams":
            # Cascade: nessun riferimento orfano al Team eliminato (scoped all'org).
            await db.staff.update_many(oq(user, team_id=item_id), {"$set": {"team_id": ""}})
            await db.shifts.update_many(oq(user, team_id=item_id), {"$set": {"team_id": ""}})
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
                          "telefono_referente": s.get("telefono_referente"), "note": s.get("note"),
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
    _assert_ev_allowed(admin, b.evento_id)
    persons = await _resolve_persons(b, admin["org_id"])
    if not persons:
        raise HTTPException(status_code=400, detail="Nessuna persona selezionata")
    gid = new_id()
    for pid in persons:
        await _create("lodgings", {**b.data, "org_id": admin["org_id"], "evento_id": b.evento_id, "persona_id": pid, "gruppo_id": gid})
    return {"ok": True, "gruppo_id": gid, "count": len(persons)}


@api.post("/meals/bulk")
async def meals_bulk(b: BulkAssignIn, admin: dict = Depends(require_admin)):
    _assert_ev_allowed(admin, b.evento_id)
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


def _room_bucket(t):
    return {"singola": "singole", "doppia": "doppie", "tripla": "triple"}.get(t, "altre")


def _compute_rooms(lodgings):
    """Riepilogo camere: una camera condivisa (occupanti comuni + stessa struttura/date) conta 1 volta."""
    n = len(lodgings)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    members = []
    for l in lodgings:
        s = {l.get("persona_id")}
        for occ in (l.get("occupanti") or []):
            if isinstance(occ, dict) and occ.get("persona_id"):
                s.add(occ["persona_id"])
        members.append(s)
    sig = [(l.get("struttura_nome") or "", l.get("check_in") or "", l.get("check_out") or "") for l in lodgings]
    room = [((l.get("struttura_id") or l.get("struttura_nome") or "").lower(), (l.get("numero_camera") or "").strip().lower()) for l in lodgings]
    for i in range(n):
        for j in range(i + 1, n):
            if room[i][1] and room[i] == room[j]:
                union(i, j)  # stesso numero camera nella stessa struttura: date per persona possono differire
            elif not room[i][1] and not room[j][1] and sig[i] == sig[j] and members[i] & members[j]:
                union(i, j)
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    by_type = {"singole": 0, "doppie": 0, "triple": 0, "altre": 0}
    by_struct = {}
    for idxs in groups.values():
        tipos = [lodgings[i].get("tipo_camera") for i in idxs if lodgings[i].get("tipo_camera")]
        bucket = _room_bucket(tipos[0] if tipos else None)
        by_type[bucket] += 1
        struct = lodgings[idxs[0]].get("struttura_nome") or "Struttura da definire"
        bs = by_struct.setdefault(struct, {"struttura": struct, "totali": 0, "singole": 0, "doppie": 0, "triple": 0, "altre": 0})
        bs["totali"] += 1
        bs[bucket] += 1
    return {"totali": sum(by_type.values()), **by_type,
            "per_struttura": sorted(by_struct.values(), key=lambda x: x["struttura"].lower())}


@api.get("/events/{event_id}/hospitality")
async def event_hospitality(event_id: str, admin: dict = Depends(require_admin)):
    event = await db.events.find_one(oq(admin, id=event_id), {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Evento non trovato")
    can_costs = admin.get("role") == "admin"
    links = await db.staff.find(oq(admin, evento_id=event_id), {"_id": 0}).to_list(5000)
    lodgings = await db.lodgings.find(oq(admin, evento_id=event_id), {"_id": 0}).to_list(5000)
    meals = await db.meals.find(oq(admin, evento_id=event_id), {"_id": 0}).to_list(20000)
    _normalize_meals(meals)
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
    # Dedup per persona: una persona può avere più record staff (più team/ruoli/turni) ma in
    # Ospitalità & Pasti deve comparire UNA sola volta per evento. Rappresentante = link con
    # servizio definito (badge/stato coerente) o con override esigenze, altrimenti il primo.
    by_person = {}
    for l in links:
        pid = l["persona_id"]
        cur = by_person.get(pid)
        if cur is None:
            by_person[pid] = l
            continue
        srv = l.get("servizio_ospitalita")
        cur_srv = cur.get("servizio_ospitalita")
        if srv and srv != "da_definire" and (not cur_srv or cur_srv == "da_definire"):
            by_person[pid] = l
        elif l.get("esigenze_alimentari") is not None and cur.get("esigenze_alimentari") is None:
            by_person[pid] = l
    links = list(by_person.values())
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
        servizio = l.get("servizio_ospitalita") or "da_definire"
        persons.append({
            "persona_id": p["id"], "nome": p.get("nome"), "cognome": p.get("cognome"),
            "ruolo": l.get("ruolo") or p.get("ruolo"), "categoria": l.get("categoria"),
            "team_id": l.get("team_id"), "team_nome": teams.get(l.get("team_id"), {}).get("nome"),
            "presence_id": l.get("id"),
            "servizio_ospitalita": servizio,
            "esigenze_alimentari": eff_esig or [], "esigenze_note": eff_note, "esigenze_override": override,
            "lodgings": plod, "meals": pmeal, "stato": servizio,
        })
    persons.sort(key=lambda x: ((x.get("cognome") or "").lower(), (x.get("nome") or "").lower()))

    def _c(t):
        return len([m for m in meals if m.get("tipo_pasto") == t])

    servizi_da_def = len([x for x in persons if (x.get("servizio_ospitalita") or "da_definire") == "da_definire"])
    senza_sist = len([x for x in persons if x.get("servizio_ospitalita") in ("solo_ospitalita", "ospitalita_pasti") and not x["lodgings"]])
    summary = {
        "persone_gestite": len([1 for x in persons if x["lodgings"] or x["meals"]]),
        "persone_totali": len(persons),
        "pernottamenti": len(lodgings), "camere": len(lodgings),
        "colazioni": _c("colazione"), "pranzi": _c("pranzo"), "cene": _c("cena"),
        "servizi_da_definire": servizi_da_def,
        "senza_sistemazione": senza_sist,
    }
    return {"event": event, "persons": persons, "lodgings": lodgings, "meals": meals,
            "summary": summary, "rooms": _compute_rooms(lodgings), "can_view_costs": can_costs}


class CopyServicesIn(BaseModel):
    evento_id: str
    source_persona_id: str
    target_persona_ids: List[str]
    what: str = "both"   # ospitalita | pasti | both
    mode: str = "keep"   # keep | replace


@api.post("/hospitality/copy")
async def hospitality_copy(b: CopyServicesIn, admin: dict = Depends(require_admin)):
    _assert_ev_allowed(admin, b.evento_id)
    oid = admin["org_id"]
    do_lod = b.what in ("ospitalita", "both")
    do_meal = b.what in ("pasti", "both")
    src_lod = await db.lodgings.find(oq(admin, evento_id=b.evento_id, persona_id=b.source_persona_id), {"_id": 0}).to_list(100) if do_lod else []
    src_meal = await db.meals.find(oq(admin, evento_id=b.evento_id, persona_id=b.source_persona_id), {"_id": 0}).to_list(500) if do_meal else []
    # Non si copiano: occupanti della camera (specifici per persona) né esigenze alimentari (in anagrafica).
    STRIP = ("id", "persona_id", "gruppo_id", "occupanti", "compagni_camera", "created_at", "updated_at")

    def _clone(rec, pid):
        d = {k: v for k, v in rec.items() if k not in STRIP}
        d.update({"id": new_id(), "org_id": oid, "persona_id": pid, "evento_id": b.evento_id, "created_at": now_iso()})
        return d

    count = 0
    for tid in b.target_persona_ids:
        if tid == b.source_persona_id:
            continue
        if do_lod:
            existing = await db.lodgings.count_documents(oq(admin, evento_id=b.evento_id, persona_id=tid))
            if not (existing and b.mode == "keep"):
                if existing and b.mode == "replace":
                    await db.lodgings.delete_many(oq(admin, evento_id=b.evento_id, persona_id=tid))
                for r in src_lod:
                    await db.lodgings.insert_one(_clone(r, tid))
        if do_meal:
            existing = await db.meals.count_documents(oq(admin, evento_id=b.evento_id, persona_id=tid))
            if not (existing and b.mode == "keep"):
                if existing and b.mode == "replace":
                    await db.meals.delete_many(oq(admin, evento_id=b.evento_id, persona_id=tid))
                for r in src_meal:
                    await db.meals.insert_one(_clone(r, tid))
        hl = await db.lodgings.count_documents(oq(admin, evento_id=b.evento_id, persona_id=tid))
        hm = await db.meals.count_documents(oq(admin, evento_id=b.evento_id, persona_id=tid))
        st = "ospitalita_pasti" if (hl and hm) else ("solo_ospitalita" if hl else ("solo_pasti" if hm else None))
        if st:
            await db.staff.update_many(oq(admin, evento_id=b.evento_id, persona_id=tid), {"$set": {"servizio_ospitalita": st}})
        count += 1
    return {"ok": True, "count": count}


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
    scope = await _person_scope(admin)
    if scope is not None:
        persons = [p for p in persons if p["id"] in scope]
    rels = await db.person_companies.find(oq(admin), {"_id": 0}).to_list(10000)
    pres = [x for x in await db.staff.find(oq(admin), {"_id": 0}).to_list(10000) if _link_visible(admin, x)]
    companies = {c["id"]: c for c in await _list("companies", oq(admin))}
    teams_map = {t["id"]: t.get("nome") for t in await _list("teams", oq(admin))}
    events_map = {e["id"]: e.get("nome") for e in await _list("events", oq(admin))}
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
        teams_nomi = []
        for x in prs:
            tn = teams_map.get(x.get("team_id"))
            if tn and tn not in teams_nomi:
                teams_nomi.append(tn)
        eventi_nomi = []
        for x in prs:
            en = events_map.get(x.get("evento_id"))
            if en and en not in eventi_nomi:
                eventi_nomi.append(en)
        out.append({**p,
                    "is_referente": bool(rp) or bool(p.get("azienda_id")),
                    "is_evento": bool(prs),
                    "is_staff": bool(cats & {"staff", "collaboratore"}),
                    "is_volontario": "volontario" in cats,
                    "is_team": "team" in cats,
                    "aziende_nomi": aziende,
                    "teams_nomi": teams_nomi,
                    "eventi_nomi": eventi_nomi,
                    "eventi_ids": list({x["evento_id"] for x in prs}),
                    "eventi_count": len({x["evento_id"] for x in prs})})
    return out


class StaffQuickAddIn(BaseModel):
    evento_id: str
    nome: str
    cognome: Optional[str] = None
    cellulare: Optional[str] = None
    email: Optional[str] = None
    categoria: Optional[str] = "staff"
    team_id: Optional[str] = None
    use_existing_person_id: Optional[str] = None
    confirm_existing: bool = False


@api.post("/staff/quick-add")
async def staff_quick_add(body: StaffQuickAddIn, admin: dict = Depends(require_admin)):
    _assert_ev_allowed(admin, body.evento_id)
    if _team_ids(admin) is not None and body.team_id not in _team_ids(admin):
        raise HTTPException(status_code=403, detail="Seleziona uno dei Team a cui hai accesso")
    if not body.evento_id:
        raise HTTPException(status_code=400, detail="Evento mancante")
    if not (body.nome or "").strip():
        raise HTTPException(status_code=400, detail="Il nome è obbligatorio")
    email = (body.email or "").strip().lower()
    tel = ""
    if (body.cellulare or "").strip():
        try:
            tel = _normalize_phone(body.cellulare)
        except Exception:
            tel = (body.cellulare or "").strip()
    person = None
    if body.use_existing_person_id:
        person = await db.persons.find_one({**oq(admin), "id": body.use_existing_person_id}, {"_id": 0})
    if not person and (email or tel):
        conds = []
        if email: conds.append({"email": email})
        if tel: conds.append({"cellulare": tel})
        existing = await db.persons.find_one({**oq(admin), "$or": conds}, {"_id": 0}) if conds else None
        if existing and not body.confirm_existing:
            return {"status": "exists", "person": {"id": existing["id"], "nome": existing.get("nome"), "cognome": existing.get("cognome"), "email": existing.get("email"), "cellulare": existing.get("cellulare")}}
        person = existing
    await SAAS["check_people"](admin["org_id"], (person or {}).get("id"))
    if not person:
        person = TN.normalize_fields("persons", {"id": new_id(), "org_id": admin["org_id"], "nome": body.nome.strip(), "cognome": (body.cognome or "").strip(), "email": email, "cellulare": tel, "created_at": now_iso()})
        await db.persons.insert_one({**person})
    categoria = body.categoria if body.categoria in ("staff", "volontario") else "staff"
    link = await db.staff.find_one({**oq(admin), "persona_id": person["id"], "evento_id": body.evento_id}, {"_id": 0})
    if not link:
        doc = {"id": new_id(), "org_id": admin["org_id"], "persona_id": person["id"], "evento_id": body.evento_id, "categoria": categoria, "stato": "da_contattare", "created_at": now_iso()}
        if body.team_id:
            doc["team_id"] = body.team_id
        await db.staff.insert_one({**doc})
    else:
        upd = {}
        # Allinea la categoria se non è già coerente con una classificazione operativa
        if categoria == "volontario":
            if link.get("categoria") != "volontario":
                upd["categoria"] = "volontario"
        elif link.get("categoria") not in ("staff", "collaboratore"):
            upd["categoria"] = "staff"
        if body.team_id:
            upd["team_id"] = body.team_id
        if upd:
            await db.staff.update_one({"id": link["id"]}, {"$set": upd})
    return {"status": "ok", "person": {"id": person["id"], "nome": person.get("nome"), "cognome": person.get("cognome")}}


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
    if not _can(admin, "anagrafiche"):
        companies = []
    presences = [x for x in await db.staff.find(oq(admin, persona_id=person_id), {"_id": 0}).to_list(300) if _link_visible(admin, x)]
    events = []
    for pr in presences:
        e = await db.events.find_one({"id": pr["evento_id"], "org_id": admin["org_id"]}, {"_id": 0})
        events.append({"presence": pr, "event": e})
    tids = {pr.get("team_id") for pr in presences if pr.get("team_id")}
    for t in await db.teams.find(oq(admin, responsabile_id=person_id), {"_id": 0}).to_list(100):
        tids.add(t["id"])
    if _team_ids(admin) is not None:
        tids &= set(_team_ids(admin))
    teams = [t for t in [await db.teams.find_one({"id": tid, "org_id": admin["org_id"]}, {"_id": 0}) for tid in tids] if t]
    shifts = [s for s in await db.shifts.find(oq(admin, persona_id=person_id), {"_id": 0}).to_list(300)
              if _team_ids(admin) is None or s.get("team_id") in _team_ids(admin)]
    activities = await db.activities.find(oq(admin, persona_id=person_id), {"_id": 0}).to_list(300) if _can(admin, "attivita") else []
    followups = await db.followups.find(oq(admin, persona_id=person_id), {"_id": 0}).to_list(300) if _can(admin, "followup") else []
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
    role: Optional[str] = None
    force: bool = False


class BulkInviteIn(BaseModel):
    person_ids: List[str]


class AccessIn(BaseModel):
    enabled: bool


INVITE_DUP_HOURS = 24


def _assert_can_invite(user: dict) -> None:
    p = user.get("perm") or {"admin": True}
    if not (p.get("admin") or p.get("send_invites")):
        raise HTTPException(status_code=403, detail="Non hai il permesso di inviare inviti email")


async def _invite_roles_for(user: dict, person: dict) -> set:
    """Ruoli invitabili per la persona: Admin tutti; altri solo da presenze in Team/eventi/categorie gestiti."""
    p = user.get("perm") or {"admin": True}
    if p.get("admin"):
        return {"staff", "volunteer"}
    tids, eids, tp = p.get("team_ids"), p.get("event_ids"), p.get("teams") or {}
    if not P.allows(p, ("staff",), "view"):  # senza sezione Staff: solo i Team guidati
        tids = p.get("led_team_ids") or []
    links = await db.staff.find({"org_id": user["org_id"], "persona_id": person["id"]},
                                {"_id": 0, "categoria": 1, "team_id": 1, "evento_id": 1}).to_list(1000)
    roles = set()
    for l in links:
        cat = l.get("categoria")
        if cat not in ("staff", "collaboratore", "volontario"):
            continue
        if (eids is not None and l.get("evento_id") not in eids) or (tids is not None and l.get("team_id") not in tids):
            continue
        if tp.get("manage_volunteers" if cat == "volontario" else "manage_staff", True) is False:
            continue
        roles.add("volunteer" if cat == "volontario" else "staff")
    return roles


async def _send_person_invite(user: dict, person: dict, role: Optional[str], force: bool) -> dict:
    """Invito area personale (template/link esistenti) con controllo accesso destinatario e anti-doppione."""
    if not person.get("email"):
        raise HTTPException(status_code=400, detail="La persona non ha un'email")
    is_admin = (user.get("perm") or {"admin": True}).get("admin")
    allowed = await _invite_roles_for(user, person)
    if not allowed:
        raise HTTPException(status_code=403, detail="Non hai accesso a questa persona")
    if role not in ("staff", "volunteer"):
        role = person.get("user_role") if person.get("user_role") in allowed else ("volunteer" if "volunteer" in allowed else "staff")
    if role not in allowed:
        raise HTTPException(status_code=403, detail="Non puoi invitare questa persona con il ruolo selezionato")
    email = person["email"].lower()
    existing = await db.users.find_one({"email": email}, {"_id": 0, "user_id": 1, "role": 1})
    if not is_admin:
        if person.get("invite_status") == "accesso_disabilitato":
            raise HTTPException(status_code=403, detail="Accesso disabilitato dall'Admin: non puoi reinviare l'invito")
        if existing and (existing.get("role") not in ("staff", "volunteer") or await db.memberships.find_one({"user_id": existing["user_id"]}, {"_id": 1})):
            raise HTTPException(status_code=409, detail="Questa persona dispone già di un account CRMEvent")
    last = person.get("last_invite_at")
    if last and not force:
        try:
            dt = datetime.fromisoformat(last)
            if datetime.now(timezone.utc) - dt < timedelta(hours=INVITE_DUP_HOURS):
                raise HTTPException(status_code=409, detail={"code": "recent_invite", "last_invite_at": last,
                                    "message": f"Invito già inviato il {dt.astimezone(ZoneInfo('Europe/Rome')).strftime('%d/%m/%Y alle %H:%M')}"})
        except ValueError:
            pass
    return await _do_person_invite(user, person, role, email)


async def _do_person_invite(admin: dict, person: dict, role: str, email: str) -> dict:
    person_id = person["id"]
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
    ts = now_iso()
    await db.persons.update_one(oq(admin, id=person_id), {"$set": {"invite_status": "invito_inviato", "user_role": role,
                                                                  "last_invite_at": ts, "last_invite_by": admin.get("name") or admin.get("email")},
                                                         "$inc": {"invite_count": 1}})
    await record_audit(admin, "person_invite_sent", org_id=admin["org_id"], target_email=email,
                       target_name=f"{person.get('cognome') or ''} {person.get('nome') or ''}".strip(),
                       detail=f"Ruolo: {'Staff' if role == 'staff' else 'Volontario'}" + ("" if sent else " · email non inviata"))
    return {"ok": True, "email_sent": sent, "last_invite_at": ts, "role": role}


@api.post("/persons/{person_id}/invite")
async def invite_person(person_id: str, body: InviteIn, admin: dict = Depends(require_admin)):
    _assert_can_invite(admin)
    person = await db.persons.find_one(oq(admin, id=person_id), {"_id": 0})
    if not person:
        raise HTTPException(status_code=404, detail="Persona non trovata")
    return await _send_person_invite(admin, person, body.role, body.force)


@api.post("/person-invites/bulk")
async def invite_persons_bulk(body: BulkInviteIn, admin: dict = Depends(require_admin)):
    """Invio multiplo: chi è già stato invitato nelle ultime 24h, senza email o fuori dal proprio ambito viene saltato."""
    _assert_can_invite(admin)
    ids = list(dict.fromkeys(body.person_ids))[:200]
    persons = {p["id"]: p for p in await db.persons.find(oq(admin, id={"$in": ids}), {"_id": 0}).to_list(200)}
    sent, skipped = [], []
    for pid in ids:
        p = persons.get(pid)
        name = f"{(p or {}).get('cognome') or ''} {(p or {}).get('nome') or ''}".strip() or pid
        if not p:
            skipped.append({"id": pid, "name": name, "reason": "Persona non trovata"}); continue
        try:
            r = await _send_person_invite(admin, p, None, False)
            sent.append({"id": pid, "name": name, "email_sent": r["email_sent"]})
        except HTTPException as e:
            d = e.detail
            skipped.append({"id": pid, "name": name, "reason": d.get("message") if isinstance(d, dict) else d})
    return {"sent": sent, "skipped": skipped}


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
        "webp": "image/webp", "pdf": "application/pdf", "csv": "text/csv", "txt": "text/plain",
        "kml": "application/vnd.google-earth.kml+xml", "kmz": "application/vnd.google-earth.kmz"}


async def _read_file_rec(rec: dict):
    """Legge i byte di un file dal backend corretto (local per i nuovi, Emergent per i legacy)."""
    return await asyncio.to_thread(storage_utils.read, rec["storage_path"],
                                   rec.get("storage_backend"), rec.get("content_type"))


def _public_file_url(token: str) -> str:
    return f"{BACKEND_PUBLIC_URL}/api/files/public/{token}"


async def _ensure_public_token(file_rec: dict) -> str:
    """Garantisce (creandolo se assente) un public_token per un file immagine. Idempotente."""
    tok = file_rec.get("public_token")
    if tok:
        return tok
    tok = storage_utils.make_token()
    await db.files.update_one({"id": file_rec["id"]}, {"$set": {"public_token": tok}})
    file_rec["public_token"] = tok
    return tok


def _upload_error(e: ValueError) -> HTTPException:
    return HTTPException(status_code=400,
                         detail="File troppo grande" if str(e).startswith("too_large")
                         else "Tipo di file non supportato")


@api.post("/upload")
async def upload(file: UploadFile = File(...), admin: dict = Depends(require_admin)):
    data = await file.read()
    try:
        kind, ext = storage_utils.classify_and_validate(file.filename, file.content_type, len(data))
    except ValueError as e:
        raise _upload_error(e)
    fid = new_id()
    rel = f"uploads/{admin['org_id']}/{fid}.{ext}"
    ctype = file.content_type or MIME.get(ext, "application/octet-stream")
    result = await asyncio.to_thread(storage_utils.save, rel, data, ctype)
    doc = {"id": fid, "org_id": admin["org_id"], "storage_path": result["path"],
           "storage_backend": result.get("backend"), "original_filename": file.filename,
           "content_type": ctype, "size": result.get("size"), "is_deleted": False, "created_at": now_iso()}
    if kind in storage_utils.PUBLIC_KINDS:
        doc["public_token"] = storage_utils.make_token()
    await db.files.insert_one(doc)
    url = _public_file_url(doc["public_token"]) if doc.get("public_token") else f"/api/files/{fid}"
    return {"id": fid, "url": url, "filename": file.filename}


@api.get("/files/{file_id}")
async def download(file_id: str, user: dict = Depends(get_current_user)):
    rec = await db.files.find_one({"id": file_id, "is_deleted": {"$ne": True}}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="File non trovato")
    if user.get("role") != "superadmin" and rec.get("org_id") not in (None, user.get("org_id")):
        raise HTTPException(status_code=404, detail="File non trovato")
    data, ctype = await _read_file_rec(rec)
    return Response(content=data, media_type=rec.get("content_type", ctype))


MAP_FILE_FIELDS = [("gpx_url", "gpx"), ("pdf_url", "pdf"), ("immagine_url", "image"), ("file_url", "file")]


async def _resolve_attachment(url: str, org_id: str) -> Optional[dict]:
    """Solo allegati realmente esistenti: file CRMEvent (privati o con token) o link esterni (archivio precedente)."""
    if not url:
        return None
    url_path = url.split("?", 1)[0].split("#", 1)[0]
    m = re.search(r"/api/files/public/([A-Za-z0-9_\-]+)$", url_path)
    proj = {"_id": 0, "original_filename": 1, "content_type": 1, "org_id": 1, "storage_path": 1}
    alive = {"is_deleted": {"$ne": True}}  # i file migrati possono non avere il campo is_deleted
    if m:
        rec = await db.files.find_one({"public_token": m.group(1), **alive}, proj)
    else:
        m = re.search(r"/api/files/([A-Za-z0-9_\-]+)$", url_path)
        rec = await db.files.find_one({"id": m.group(1), **alive}, proj) if m else None
    if m:
        if not rec or rec.get("org_id") not in (None, org_id):
            return None
        name = rec.get("original_filename") or (rec.get("storage_path") or "").rsplit("/", 1)[-1] or None
        return {"url": url, "name": name, "content_type": rec.get("content_type")}
    if url.startswith("http") or url.startswith("/"):
        return {"url": url, "name": url_path.rsplit("/", 1)[-1] or None, "content_type": None}
    return None


def _attachment_kind(field_kind: str, a: dict) -> str:
    name, ct = (a.get("name") or "").lower(), (a.get("content_type") or "").lower()
    if name.endswith(".gpx") or "gpx" in ct:
        return "gpx"
    if name.endswith(".pdf") or ct == "application/pdf":
        return "pdf"
    if ct.startswith("image/") or re.search(r"\.(png|jpe?g|webp|gif|heic)$", name):
        return "image"
    if re.search(r"\.(kml|kmz|zip|docx?|xlsx?|csv|txt)$", name):
        return "file"
    return field_kind if field_kind in ("gpx", "pdf", "image") and not name else "file"


@api.get("/maps-attachments")
async def maps_attachments(evento_id: str, user: dict = Depends(require_admin)):
    """Allegati esistenti per ogni percorso dell'evento (GPX, PDF, immagini, altri file), senza link non funzionanti."""
    q = oq(user, evento_id=evento_id)
    if _team_ids(user) is not None:
        q["$or"] = [{"team_id": {"$in": _team_ids(user)}}, {"team_id": {"$in": [None, ""]}}]
    out = {}
    for mp in await db.event_maps.find(q, {"_id": 0}).to_list(500):
        items, seen = [], set()
        for field, kind in MAP_FILE_FIELDS:
            url = mp.get(field)
            if not url or url in seen:
                continue
            seen.add(url)
            a = await _resolve_attachment(url, user["org_id"])
            if a:
                items.append({**a, "field": field, "kind": _attachment_kind(kind, a)})
        out[mp["id"]] = items
    return out


@api.get("/files/public/{token}")
async def file_public(token: str):
    """Serve pubblicamente (senza cookie) un file tramite token imprevedibile. Solo file con public_token."""
    rec = await db.files.find_one({"public_token": token, "is_deleted": {"$ne": True}}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Not found")
    data, ctype = await _read_file_rec(rec)
    return Response(content=data, media_type=rec.get("content_type") or ctype,
                    headers={"Cache-Control": "public, max-age=31536000, immutable"})


# ---------------- onboarding / tutorial ----------------
@api.get("/onboarding/status")
async def onboarding_status(request: Request, user: dict = Depends(get_current_user)):
    # Super Admin navigation must never trigger/alter organizers' onboarding.
    if user.get("role") == "superadmin":
        return {"superadmin": True, "show": False, "events": [], "state": {}}
    # Guida informativa: sola lettura, nessun conteggio/avanzamento basato sui dati.
    org_id, _role = await _resolve_active_org(request, user)
    events = await db.events.find({"org_id": org_id}, {"_id": 0, "id": 1, "nome": 1, "created_at": 1}) \
        .sort("created_at", -1).to_list(2000)
    u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "onboarding": 1}) or {}
    ob = u.get("onboarding") or {}
    return {
        "superadmin": False, "show": True,
        "events": [{"id": e["id"], "nome": e.get("nome")} for e in events],
        "state": {"seen": bool(ob.get("seen")), "later": bool(ob.get("later"))},
    }


class OnboardingStateIn(BaseModel):
    seen: Optional[bool] = None
    started: Optional[bool] = None
    later: Optional[bool] = None
    card_hidden: Optional[bool] = None
    completed: Optional[bool] = None
    skip: Optional[str] = None
    unskip: Optional[str] = None


@api.post("/onboarding/state")
async def onboarding_set_state(body: OnboardingStateIn, user: dict = Depends(get_current_user)):
    if user.get("role") == "superadmin":
        return {"ok": True, "superadmin": True}
    u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "onboarding": 1}) or {}
    ob = u.get("onboarding") or {}
    now = now_iso()
    if body.seen is not None:
        ob["seen"] = body.seen
    if body.later is not None:
        ob["later"] = body.later
    if body.card_hidden is not None:
        ob["card_hidden"] = body.card_hidden
    if body.started:
        ob["started"] = True
        ob.setdefault("started_at", now)
    if body.completed:
        ob["completed"] = True
        ob.setdefault("completed_at", now)
    if body.skip:
        ob.setdefault("skipped", {})[body.skip] = True
    if body.unskip and ob.get("skipped"):
        ob["skipped"].pop(body.unskip, None)
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"onboarding": ob}})
    return {"ok": True, "onboarding": ob}


# ---------------- dashboard / search / notifications ----------------
@api.get("/dashboard")
async def dashboard(evento_id: Optional[str] = None, admin: dict = Depends(require_admin)):
    ev_q = oq(admin) if not evento_id else oq(admin, id=evento_id)
    rel_q = oq(admin) if not evento_id else oq(admin, evento_id=evento_id)
    if _ev_ids(admin) is not None and not evento_id:
        ev_q["id"] = {"$in": _ev_ids(admin)}
        rel_q.update(_ev_scope(admin))
    can = {k: _can(admin, k) for k in ("eventi", "aziende", "anagrafiche", "staff", "sponsor", "attivita", "followup", "pipeline", "ospitalita", "briefing")}
    events = await db.events.find(ev_q, {"_id": 0}).to_list(5000) if can["eventi"] else []
    companies = await db.companies.find(oq(admin), {"_id": 0}).to_list(5000) if can["aziende"] else []
    persons = await db.persons.find(oq(admin), {"_id": 0}).to_list(5000) if can["anagrafiche"] else []
    deals = await db.deals.find(rel_q, {"_id": 0}).to_list(5000) if can["sponsor"] else []
    staff = await db.staff.find(rel_q, {"_id": 0}).to_list(5000) if can["staff"] else []
    teams = await db.teams.find(rel_q, {"_id": 0}).to_list(5000) if can["staff"] else []
    shifts = await db.shifts.find(rel_q, {"_id": 0}).to_list(5000) if can["staff"] else []
    if _team_ids(admin) is not None:
        tids = set(_team_ids(admin))
        staff = [s for s in staff if s.get("team_id") in tids]
        teams = [t for t in teams if t["id"] in tids]
        shifts = [s for s in shifts if s.get("team_id") in tids]
    activities = await db.activities.find(rel_q, {"_id": 0}).to_list(5000) if can["attivita"] else []
    followups = await db.followups.find(rel_q, {"_id": 0}).to_list(5000) if can["followup"] else []
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

    out = {
        "sections": can,
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
                  "persone_senza_team": len([s for s in staff if not s.get("team_id")]),
                  **_team_coverage(teams, staff)},
        "pipeline_chart": [{"fase": f, "count": len([d for d in deals if d.get("fase") == f]),
                            "valore": sum(float(d.get("valore") or 0) for d in deals if d.get("fase") == f)}
                           for f in ["prospect", "contattato", "proposta_inviata", "in_trattativa", "confermato", "perso"]],
        "tipo_chart": [{"tipo": k, "count": len([d for d in deals if d.get("tipo") == k])}
                       for k in sorted(set(d.get("tipo", "sponsor") for d in deals))] if deals else [],
    }
    # Blocchi di sezioni non autorizzate: rimossi dalla risposta (non solo nascosti in UI)
    if not can["eventi"]:
        out.pop("eventi")
    if not (can["aziende"] or can["anagrafiche"]):
        out.pop("crm")
    elif not can["aziende"]:
        out["crm"] = {"persone": out["crm"]["persone"], "nuovi_contatti": out["crm"]["nuovi_contatti"]}
    elif not can["anagrafiche"]:
        out["crm"] = {"aziende": out["crm"]["aziende"], "prospect": out["crm"]["prospect"]}
    if not can["sponsor"]:
        for k in ("commerciale", "pipeline_chart", "tipo_chart"):
            out.pop(k)
    if not (can["attivita"] or can["followup"]):
        out.pop("attivita")
    else:
        a = out["attivita"]
        if not can["followup"]:
            a.pop("followup_oggi"); a.pop("followup_scaduti")
        if not can["attivita"]:
            a.pop("prossime")
    if not can["staff"]:
        out.pop("staff")
    if (admin.get("perm") or {}).get("led_team_ids"):
        out["my_teams"] = await _my_teams_overview(admin)
    return out


async def _my_teams_overview(user: dict) -> list:
    """Riepilogo dei soli Team di cui l'utente è Team Leader."""
    oid, led = user["org_id"], user["perm"]["led_team_ids"]
    teams = await db.teams.find({"org_id": oid, "id": {"$in": led}, **_ev_scope(user)}, {"_id": 0}).to_list(500)
    evs = {e["id"]: e.get("nome") for e in await db.events.find({"org_id": oid, "id": {"$in": [t.get("evento_id") for t in teams]}}, {"_id": 0, "id": 1, "nome": 1}).to_list(500)}
    links = await db.staff.find({"org_id": oid, "team_id": {"$in": led}}, {"_id": 0}).to_list(20000)
    shifts = await db.shifts.find({"org_id": oid, "team_id": {"$in": led}}, {"_id": 0, "team_id": 1, "persona_id": 1}).to_list(20000)
    pids = list({l["persona_id"] for l in links if l.get("persona_id")})
    inv = {p["id"]: p.get("invite_status") for p in await db.persons.find({"org_id": oid, "id": {"$in": pids}}, {"_id": 0, "id": 1, "invite_status": 1}).to_list(20000)}
    out = []
    for t in sorted(teams, key=lambda x: (x.get("nome") or "").lower()):
        mine = [l for l in links if l.get("team_id") == t["id"] and l.get("stato") not in TEAM_RINUNCIA and l.get("persona_id")]
        st = {l["persona_id"] for l in mine if l.get("categoria") in ("staff", "collaboratore")}
        vo = {l["persona_id"] for l in mine if l.get("categoria") == "volontario"}
        members = st | vo
        cov = _team_coverage([t], links)
        sh = [s for s in shifts if s.get("team_id") == t["id"]]
        disp = await db.availabilities.count_documents({"org_id": oid, "evento_id": t.get("evento_id"), "persona_id": {"$in": list(members)}}) if members else 0
        req = t.get("volontari_richiesti")
        out.append({"id": t["id"], "nome": t.get("nome"), "evento_id": t.get("evento_id"), "evento_nome": evs.get(t.get("evento_id")),
                    "componenti": len(members), "staff": len(st), "volontari": len(vo), "volontari_richiesti": req,
                    "volontari_assegnati": len(vo), "volontari_mancanti": cov["volontari_mancanti"] if req is not None else None,
                    "turni_totali": len(sh), "turni_scoperti": len([s for s in sh if not s.get("persona_id")]), "disponibilita": disp,
                    "inviti_inviati": len([p for p in members if inv.get(p) in ("invito_inviato", "account_attivato", "accesso_disabilitato")]),
                    "registrati": len([p for p in members if inv.get(p) == "account_attivato"])})
    return out


@api.get("/notifications")
async def notifications(admin: dict = Depends(require_admin)):
    today = datetime.now(timezone.utc).date().isoformat()
    if not _can(admin, "followup"):
        return {"count": 0, "items": []}
    fus = await db.followups.find(oq(admin, stato={"$ne": "completato"}, **_ev_scope(admin)), {"_id": 0}).to_list(3000)
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
    ev_q = {"org_id": oid, "nome": rx}
    if _ev_ids(admin) is not None:
        ev_q["id"] = {"$in": _ev_ids(admin)}
    for e in (await db.events.find(ev_q, {"_id": 0}).limit(6).to_list(6) if _can(admin, "eventi") else []):
        results.append({"tipo": "evento", "id": e["id"], "label": e["nome"], "sub": e.get("citta", "")})
    for c in (await db.companies.find({"org_id": oid, "nome": rx}, {"_id": 0}).limit(6).to_list(6) if _can(admin, "aziende") else []):
        results.append({"tipo": "azienda", "id": c["id"], "label": c["nome"], "sub": c.get("settore", "")})
    can_p = _can(admin, "anagrafiche") or _can(admin, "staff")
    for p in (await db.persons.find({"org_id": oid, "$or": [{"nome": rx}, {"cognome": rx}, {"email": rx}]}, {"_id": 0}).limit(6).to_list(6) if can_p else []):
        results.append({"tipo": "persona", "id": p["id"], "label": f"{p.get('cognome','')} {p['nome']}".strip(), "sub": p.get("ruolo", "")})
    return {"results": results}


# ---------------- settings ----------------
def default_settings(org_id="global"):
    return {"id": org_id,
            "tipologie_evento": ["Fiera", "Congresso", "Concerto", "Festival", "Conferenza", "Workshop", "Gala", "Running", "Trail", "Triathlon", "Nuoto", "Ciclismo", "Tennis"],
            "settori": ["Tecnologia", "Food & Beverage", "Moda", "Automotive", "Finanza", "Media", "No Profit"],
            "tipi_azienda": ["Azienda", "Espositore", "Fornitore", "Istituzione", "Partner", "Prospect", "Sponsor"],
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
    defaults = default_settings(sid)
    missing = {k: v for k, v in defaults.items() if k not in doc}
    if missing:
        await db.settings.update_one({"id": sid}, {"$set": missing})
        doc.update(missing)
    return doc


@api.put("/settings")
async def update_settings(body: dict, admin: dict = Depends(require_admin)):
    body.pop("_id", None)
    body["id"] = admin["org_id"]
    await db.settings.update_one({"id": admin["org_id"]}, {"$set": body}, upsert=True)
    return await db.settings.find_one({"id": admin["org_id"]}, {"_id": 0})


USAGE_MAP = {"tipologie_evento": ("events", "tipologia"), "settori": ("companies", "settore"),
             "tipi_azienda": ("companies", "tipo"),
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
    return f"{(p.get('cognome') or '').strip()} {(p.get('nome') or '').strip()}".strip()


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
    request_id: Optional[str] = None  # idempotenza consumo crediti (UUID lato client, riusato sui retry)


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
    # Org reale dell'utente: serve sia per i dati operativi sia per il consumo crediti del wallet org.
    oid, is_mgr = None, False
    try:
        oid, is_mgr = await _resolve_org_for_support(request, user)
    except Exception as e:  # noqa: BLE001
        logger.warning("Risoluzione org assistente non disponibile: %s", e)
    # Live operational data of the user's active org (STRICTLY isolated by org_id).
    # Only managers (org admin / super admin acting on an org) receive it.
    org_data = None
    if oid and is_mgr:
        try:
            org_data = await build_org_data_context(oid, body.question)
        except Exception as e:  # noqa: BLE001
            logger.warning("Contesto dati assistente non disponibile: %s", e)
            org_data = None

    async def _ask():
        return await support_service.answer_question(body.question, ctx, page_context=body.page_context,
                                                     history=[{"role": m["role"], "content": m["content"]} for m in hist[:-1]],
                                                     role=role, org_data=org_data)

    # Consumo crediti centralizzato (servizio 'ai_assistant', costo letto dal catalogo).
    # Saldo verificato PRIMA della chiamata AI (402 se insufficiente). Addebito SOLO se la risposta
    # è realmente utile: answered=true e NON una semplice richiesta di funzionalità (feature request).
    saas_st = (await SAAS["state_for"](oid)) if (oid and SAAS) else {}
    if saas_st.get("enabled"):
        # Abbonamento (Bronze/Silver/Gold): assistente incluso, nessun consumo crediti.
        if not saas_st.get("writable"):
            raise HTTPException(status_code=402, detail="Per utilizzare l'Assistente CRMEvent scegli un piano di abbonamento.")
        result = await _ask()
    elif oid:
        idem = f"ai_assistant:{body.request_id}" if body.request_id else None
        async with ai_charge(oid, "ai_assistant", user_id=user.get("user_id"), event_id=body.event_id,
                             idempotency_key=idem, note="Assistente CRMEvent") as ctl:
            result = await _ask()
            if result.get("answered") and not result.get("is_feature_request"):
                await ctl.settle()
    else:
        result = await _ask()

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
    await _assert_event_operational(user["org_id"], event_id)
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


# ---------------- Google Calendar: sblocco a crediti + sync Attività/Follow-up ----------------
GCAL_UNLOCK_COST = 20


async def _gcal_unlocked(org_id: str) -> bool:
    return True  # sistema a crediti dismesso: Google Calendar sempre disponibile
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "features": 1, "saas": 1})
    return bool((org or {}).get("saas")) or bool((org or {}).get("features", {}).get("google_calendar"))


@api.get("/calendar/feature")
async def calendar_feature(user: dict = Depends(require_admin)):
    oid = user["org_id"]
    c = await _ensure_org_credits(oid)
    await _ensure_credits_setup()
    return {"configured": gcal_utils.is_configured(), "unlocked": await _gcal_unlocked(oid),
            "cost": (await _svc_cfg("google_calendar"))["cost"], "balance": c.get("balance", 0)}


@api.post("/calendar/unlock")
async def calendar_unlock(user: dict = Depends(require_org_admin)):
    oid = user["org_id"]
    if await _gcal_unlocked(oid):
        c = await _ensure_org_credits(oid)
        return {"unlocked": True, "charged": False, "balance": c.get("balance", 0)}
    await _ensure_credits_setup()
    cost = (await _svc_cfg("google_calendar"))["cost"]
    if cost is None:
        raise HTTPException(status_code=400, detail="Servizio 'Google Calendar' non configurato")
    if cost > 0:
        await _apply_credit_movement(oid, -cost, reason_code="google_calendar_unlock",
                                 type_="spend", service_key="google_calendar", quantity=1,
                                 unit_cost=cost, user_id=user.get("user_id"),
                                 idempotency_key=f"gcal_unlock:{oid}", note="Attivazione Google Calendar")
    await db.organizations.update_one({"id": oid}, {"$set": {"features.google_calendar": True, "features.google_calendar_at": now_iso()}})
    c = await _ensure_org_credits(oid)
    return {"unlocked": True, "charged": True, "balance": c.get("balance", 0)}


@api.post("/platform/orgs/{org_id}/calendar-feature")
async def calendar_feature_admin(org_id: str, body: dict, admin: dict = Depends(require_superadmin)):
    active = bool(body.get("active"))
    await db.organizations.update_one({"id": org_id}, {"$set": {"features.google_calendar": active, "features.google_calendar_at": now_iso()}})
    return {"org_id": org_id, "unlocked": active}


async def _gcal_record_body(kind: str, rec: dict, ora: Optional[str]):
    oid = rec.get("org_id")
    ev = await db.events.find_one({"id": rec.get("evento_id"), "org_id": oid}, {"_id": 0, "nome": 1}) if rec.get("evento_id") else None
    az = await db.companies.find_one({"id": rec.get("azienda_id"), "org_id": oid}, {"_id": 0, "nome": 1}) if rec.get("azienda_id") else None
    pe = await db.persons.find_one({"id": rec.get("persona_id"), "org_id": oid}, {"_id": 0, "nome": 1, "cognome": 1}) if rec.get("persona_id") else None
    ref = (f"{pe.get('cognome', '')} {pe.get('nome', '')}".strip()) if pe else None
    parts = [rec.get("note"), f"Evento: {ev['nome']}" if ev else None, f"Azienda: {az['nome']}" if az else None, f"Referente: {ref}" if ref else None]
    if kind == "activity":
        date = rec.get("data")
    else:
        date = rec.get("scadenza")
        if rec.get("priorita"):
            parts.append(f"Priorità: {rec.get('priorita')}")
    if not date:
        raise HTTPException(status_code=400, detail="Manca la data per creare l'evento su Google Calendar")
    d = str(date)[:10]
    desc = "\n".join([p for p in parts if p])
    return gcal_utils.build_event_body(summary=rec.get("titolo") or "CRMEvent", description=desc,
                                       location="", date_start=d, date_end=d, time_start=(ora or None))


async def _gcal_sync_record(user: dict, coll: str, kind: str, rec_id: str, ora: Optional[str]):
    oid = user["org_id"]
    if not await _gcal_unlocked(oid):
        raise HTTPException(status_code=402, detail="Funzione Google Calendar non attiva per questa organizzazione")
    rec = await db[coll].find_one({"id": rec_id, "org_id": oid}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Record non trovato")
    body = await _gcal_record_body(kind, rec, ora)
    ev = await _sync_object(user["user_id"], kind, rec_id, body)
    if ora is not None:
        await db[coll].update_one({"id": rec_id, "org_id": oid}, {"$set": {"ora": ora}})
    return {"ok": True, "google_event_id": ev["id"], "html_link": ev.get("htmlLink")}


async def _gcal_delete(user: dict, kind: str, rec_id: str):
    link = await db.calendar_event_links.find_one({"user_id": user["user_id"], "kind": kind, "ref_id": rec_id})
    if not link:
        return {"deleted": False}
    conn = await db.calendar_connections.find_one({"user_id": user["user_id"]})
    if conn:
        try:
            svc = gcal_utils.service_for(conn["tokens"])
            svc.events().delete(calendarId=link.get("calendar_id", "primary"), eventId=link["google_event_id"]).execute()
        except Exception as e:
            logger.error(f"gcal delete error: {e}")
    await db.calendar_event_links.delete_one({"user_id": user["user_id"], "kind": kind, "ref_id": rec_id})
    return {"deleted": True}


@api.post("/activities/{rec_id}/calendar-sync")
async def activity_cal_sync(rec_id: str, body: dict = None, user: dict = Depends(require_admin)):
    return await _gcal_sync_record(user, "activities", "activity", rec_id, (body or {}).get("ora"))


@api.post("/followups/{rec_id}/calendar-sync")
async def followup_cal_sync(rec_id: str, body: dict = None, user: dict = Depends(require_admin)):
    return await _gcal_sync_record(user, "followups", "followup", rec_id, (body or {}).get("ora"))


@api.get("/activities/{rec_id}/calendar-status")
async def activity_cal_status(rec_id: str, user: dict = Depends(get_current_user)):
    link = await db.calendar_event_links.find_one({"user_id": user["user_id"], "kind": "activity", "ref_id": rec_id}, {"_id": 0})
    return {"synced": bool(link), "html_link": link.get("html_link") if link else None}


@api.get("/followups/{rec_id}/calendar-status")
async def followup_cal_status(rec_id: str, user: dict = Depends(get_current_user)):
    link = await db.calendar_event_links.find_one({"user_id": user["user_id"], "kind": "followup", "ref_id": rec_id}, {"_id": 0})
    return {"synced": bool(link), "html_link": link.get("html_link") if link else None}


@api.delete("/activities/{rec_id}/calendar-event")
async def activity_cal_delete(rec_id: str, user: dict = Depends(require_admin)):
    return await _gcal_delete(user, "activity", rec_id)


@api.delete("/followups/{rec_id}/calendar-event")
async def followup_cal_delete(rec_id: str, user: dict = Depends(require_admin)):
    return await _gcal_delete(user, "followup", rec_id)


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
    # Ospitalità e pasti: SOLO le assegnazioni di questa persona. I campi economici/amministrativi
    # non vengono mai esposti allo staff (scoping lato API, non solo nel frontend).
    my_lodgings = await db.lodgings.find({"persona_id": pid, "evento_id": event_id, "org_id": oid}, {"_id": 0}).to_list(100)
    my_meals = await db.meals.find({"persona_id": pid, "evento_id": event_id, "org_id": oid}, {"_id": 0}).to_list(500)
    _normalize_meals(my_meals)
    # Stato servizio ospitalità (per persona/evento): l'Area personale mostra SOLO le sezioni
    # coerenti con la scelta. "da_definire"/"nessun_servizio" => nulla; "solo_ospitalita" => solo
    # pernottamenti; "solo_pasti" => solo pasti; "ospitalita_pasti" => entrambi.
    servizio = presence.get("servizio_ospitalita") or "da_definire"
    if servizio in ("da_definire", "nessun_servizio"):
        my_lodgings, my_meals = [], []
    elif servizio == "solo_ospitalita":
        my_meals = []
    elif servizio == "solo_pasti":
        my_lodgings = []
    _STAFF_HIDE = ("costo", "stato_pagamento", "note_amministrative", "a_carico_di", "codice_prenotazione")
    for x in my_lodgings + my_meals:
        for f in _STAFF_HIDE:
            x.pop(f, None)
    await _attach_structures(my_lodgings + my_meals, oid)
    my_meals.sort(key=lambda m: ((m.get("data") or ""), (m.get("orario") or "")))
    return {"event": event, "presence": presence, "shifts": my_shifts, "team": team,
            "team_leader": leader, "colleagues": colleagues, "maps": prio + others,
            "lodgings": my_lodgings, "meals": my_meals}


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
    marketing_consent: Optional[bool] = False
    demo_data: Optional[str] = None  # YYYY-MM-DD preferita
    demo_ora: Optional[str] = None  # HH:MM preferita


class DemoActionIn(BaseModel):
    action: str  # confirm | reschedule | cancel
    demo_data: Optional[str] = None
    demo_ora: Optional[str] = None


def _demo_slot(d: Optional[str], t: Optional[str]) -> Optional[str]:
    if not d:
        return None
    try:
        return datetime.strptime(f"{d}T{t or '10:00'}", "%Y-%m-%dT%H:%M").strftime("%Y-%m-%dT%H:%M")
    except ValueError:
        raise HTTPException(status_code=400, detail="Data o ora della demo non valida")


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
    slot = _demo_slot(body.demo_data, body.demo_ora)
    data = body.model_dump(exclude={"demo_data", "demo_ora"})
    data.update({"marketing_consent": bool(body.marketing_consent), "marketing_consent_at": now if body.marketing_consent else None,
                 "demo_slot": slot, "demo_status": "da_confermare" if slot else None})
    doc = await _create("leads", {**data, "stato": "nuovo", "note": "",
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
    # Brevo: lista Lead esistente (ID reale), nessun duplicato; errori registrati e ritentati dal cron.
    try:
        await demo_booking.sync_lead(db, doc)
    except Exception as e:
        logger.error(f"brevo contact upsert failed: {e}")
        await db.leads.update_one({"id": doc["id"]}, {"$set": {"brevo_sync": {"status": "errore", "attempts": 1, "last_attempt_at": now_iso(), "error": type(e).__name__}}})
    # Funnel commerciale SOLO con consenso marketing, mai ripetuto per la stessa email, mai se disiscritto.
    enrolled = False
    if body.marketing_consent:
        try:
            prior = await db.funnel_enrollments.find_one({"funnel_key": brevo_funnel.FUNNEL_KEY, "email": {"$regex": f"^{re.escape(body.email)}$", "$options": "i"}})
            opted_out = await db.leads.find_one({"email": {"$regex": f"^{re.escape(body.email)}$", "$options": "i"}, "marketing_opt_out": True})
            if not prior and not opted_out:
                enrolled = (await _enroll_lead(doc)).get("enrolled", False)
        except Exception as e:
            logger.error(f"funnel enroll failed: {e}")
    if not enrolled:
        await demo_booking.send_operational(doc, "ricevuta", APP_URL)
    return {"ok": True, "id": doc["id"]}


@api.post("/leads/{lead_id}/demo")
async def lead_demo_action(lead_id: str, body: DemoActionIn, admin: dict = Depends(require_superadmin)):
    lead = await db.leads.find_one({"id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead non trovato")
    upd = {}
    if body.action == "confirm":
        if not lead.get("demo_slot"):
            raise HTTPException(status_code=400, detail="Nessuna data demo da confermare")
        upd, kind = {"demo_status": "confermata"}, "confermata"
    elif body.action == "reschedule":
        slot = _demo_slot(body.demo_data, body.demo_ora)
        if not slot:
            raise HTTPException(status_code=400, detail="Indica la nuova data della demo")
        upd, kind = {"demo_status": "riprogrammata", "demo_slot": slot}, "riprogrammata"
    elif body.action == "cancel":
        upd, kind = {"demo_status": "annullata"}, "annullata"
    else:
        raise HTTPException(status_code=400, detail="Azione non valida")
    upd["updated_at"] = now_iso()
    upd.update(await demo_booking.meet_for_demo(db, {**lead, **upd}, body.action))
    await db.leads.update_one({"id": lead_id}, {"$set": upd})
    lead.update(upd)
    sent = await demo_booking.send_operational(lead, kind, APP_URL)
    sync = await demo_booking.sync_lead(db, lead)
    await record_audit(admin, "lead_demo_" + body.action, target_email=lead.get("email"), detail=demo_booking.fmt_slot(lead.get("demo_slot")))
    return {"ok": True, "demo_status": lead["demo_status"], "demo_slot": lead.get("demo_slot"), "demo_meet_link": lead.get("demo_meet_link"), "email_sent": sent, "brevo_sync": sync}


@api.post("/leads/{lead_id}/brevo-sync")
async def lead_brevo_sync(lead_id: str, admin: dict = Depends(require_superadmin)):
    lead = await db.leads.find_one({"id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead non trovato")
    return await demo_booking.sync_lead(db, lead)


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


def _lead_origine(lead: dict) -> str:
    """Derive the Lead origin (non-destructive, computed at read time).
    Explicit `origine` wins; converted Lead Finder records are tagged; demo-site leads are
    detected via demo funnel timestamp/source; everything else defaults to manual."""
    if lead.get("origine"):
        return lead["origine"]
    if lead.get("lead_finder_organizer_id"):
        return "lead_finder"
    src = (lead.get("source") or "").lower()
    if lead.get("funnel_ts_demo_requested") or "demo" in src or "richiedi" in src:
        return "demo_sito"
    return "manuale"


@api.get("/leads")
async def list_leads(admin: dict = Depends(require_superadmin)):
    rows = await _list("leads")
    for l in rows:
        l["origine"] = _lead_origine(l)
    return rows


@api.put("/leads/{lead_id}")
async def update_lead(lead_id: str, body: LeadUpdate, admin: dict = Depends(require_superadmin)):
    return await _update("leads", lead_id, body.model_dump(exclude_unset=True))


@api.delete("/leads/{lead_id}")
async def delete_lead(lead_id: str, admin: dict = Depends(require_superadmin)):
    return await _delete("leads", lead_id)


# ==================== Organizations, memberships & invites management ====================
ORG_ROLE_LABELS = {"admin_org": "Admin Organizzazione", "user": "Utente", "collaboratore": "Collaboratore"}


def _norm_role(r: str) -> str:
    return r if r in ("admin_org", "collaboratore") else "user"


# ---------- Permessi per organizzazione (gestiti dall'Admin Organizzatore) ----------
class PermUpdateIn(BaseModel):
    role: Optional[str] = None
    sections: Optional[dict] = None
    events: Optional[Any] = None
    teams: Optional[dict] = None
    send_invites: Optional[bool] = None
    marketplace_purchase: Optional[bool] = None
    team_leader: Optional[dict] = None
    persona_id: Optional[str] = None  # "" = scollega
    reset: bool = False


def _perm_summary(role: str, perm: dict) -> str:
    if role == "admin_org":
        return "Admin Organizzatore: accesso completo"
    secs = perm.get("sections") or {}
    parts = [f"{lbl}: {'/'.join(P.ACTION_LABELS[a] for a in secs.get(k, []))}" for k, lbl in P.SECTIONS if secs.get(k)]
    ev = perm.get("events")
    evs = "tutti gli eventi" if ev == "all" else f"{len(ev or [])} eventi selezionati"
    tp = perm.get("teams") or {}
    tms = {"all": "tutti i Team", "leader": "solo Team di cui è Team Leader"}.get(tp.get("scope"), f"{len(tp.get('ids') or [])} Team selezionati + Team di cui è leader")
    tl = perm.get("team_leader") or {}
    inv = ("inviti email: sì" if perm.get("send_invites") else "inviti email: no") + \
        (" · acquisti Marketplace: sì" if perm.get("marketplace_purchase") else "") + \
        f" · Team Leader: componenti {'modifica' if tl.get('edit_members') else 'sola lettura'}, turni {'sì' if tl.get('manage_shifts') else 'no'}"
    return f"{P.ROLES.get(role, role)} · {evs} · {tms} · {inv} · " + ("; ".join(parts) or "nessuna sezione")


@api.get("/org/permissions")
async def org_permissions(admin: dict = Depends(require_org_admin)):
    oid = admin["org_id"]
    mems = await db.memberships.find({"org_id": oid}, {"_id": 0}).to_list(1000)
    users = {u["user_id"]: u for u in await db.users.find(
        {"user_id": {"$in": [m["user_id"] for m in mems]}}, {"_id": 0, "user_id": 1, "name": 1, "email": 1, "role": 1}).to_list(1000)}
    members = []
    for m in mems:
        u = users.get(m["user_id"]) or {}
        if u.get("role") == "superadmin":
            continue
        eff = P.effective(m)
        members.append({"user_id": m["user_id"], "name": u.get("name"), "email": u.get("email"),
                        "role": m["role"], "role_label": P.ROLES.get(m["role"], m["role"]),
                        "active": m.get("active", True), "is_self": m["user_id"] == admin["user_id"],
                        "custom": bool(m.get("permissions")), "permissions": eff, "persona_id": m.get("persona_id")})
    members.sort(key=lambda x: ((x["name"] or x["email"] or "").lower()))
    events = await db.events.find({"org_id": oid}, {"_id": 0, "id": 1, "nome": 1, "data_inizio": 1}).sort("data_inizio", -1).to_list(2000)
    teams = await db.teams.find({"org_id": oid}, {"_id": 0, "id": 1, "nome": 1, "evento_id": 1, "responsabile_id": 1}).sort("nome", 1).to_list(5000)
    persons = await db.persons.find({"org_id": oid}, {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "email": 1}).to_list(20000)
    persons.sort(key=lambda p: (f"{p.get('cognome') or ''} {p.get('nome') or ''}").strip().lower())
    return {"sections": [{"key": k, "label": l} for k, l in P.SECTIONS], "actions": P.ACTION_LABELS,
            "roles": P.ROLES, "defaults": {r: P.default_permissions(r) for r in ("user", "collaboratore")},
            "members": members, "events": events, "teams": teams, "persons": persons}


@api.put("/org/permissions/{target_id}")
async def update_org_permissions(target_id: str, body: PermUpdateIn, admin: dict = Depends(require_org_admin)):
    oid = admin["org_id"]
    if target_id == admin["user_id"]:
        raise HTTPException(status_code=400, detail="Non puoi modificare il tuo ruolo o i tuoi permessi")
    m = await db.memberships.find_one({"org_id": oid, "user_id": target_id}, {"_id": 0})
    tgt = await db.users.find_one({"user_id": target_id}, {"_id": 0, "email": 1, "name": 1, "role": 1})
    if not m or not tgt or tgt.get("role") == "superadmin":
        raise HTTPException(status_code=404, detail="Utente non trovato nell'organizzazione")
    org = await _org_or_404(oid)
    new_role = m["role"]
    if body.role is not None:
        if body.role not in P.ROLES:
            raise HTTPException(status_code=400, detail="Ruolo non valido")
        new_role = body.role
    if m["role"] == "admin_org" and new_role != "admin_org":
        await _guard_last_admin(org, target_id)
    if new_role == "admin_org" or body.reset:
        new_perm = {}
    elif any(x is not None for x in (body.sections, body.events, body.teams, body.send_invites, body.marketplace_purchase, body.team_leader)):
        cur = P.effective({**m, "role": new_role})
        raw = {"sections": body.sections if body.sections is not None else cur["sections"],
               "events": body.events if body.events is not None else cur["events"],
               "teams": body.teams if body.teams is not None else cur.get("teams"),
               "send_invites": body.send_invites if body.send_invites is not None else cur.get("send_invites", False),
               "marketplace_purchase": body.marketplace_purchase if body.marketplace_purchase is not None else cur.get("marketplace_purchase", False),
               "team_leader": body.team_leader if body.team_leader is not None else cur.get("team_leader")}
        new_perm = P.normalize_permissions(raw, new_role)
        if new_perm["teams"]["ids"]:
            valid_t = set(await db.teams.distinct("id", {"org_id": oid, "id": {"$in": new_perm["teams"]["ids"]}}))
            new_perm["teams"]["ids"] = [t for t in new_perm["teams"]["ids"] if t in valid_t]
        if new_perm["events"] != "all":
            valid = set(await db.events.distinct("id", {"org_id": oid, "id": {"$in": new_perm["events"]}}))
            new_perm["events"] = [e for e in new_perm["events"] if e in valid]
    else:
        new_perm = {} if new_role != m["role"] else (m.get("permissions") or {})
    new_pid = m.get("persona_id")
    if body.persona_id is not None:
        new_pid = body.persona_id or None
        if new_pid and not await db.persons.find_one({"org_id": oid, "id": new_pid}, {"_id": 1}):
            raise HTTPException(status_code=404, detail="Persona non trovata nell'organizzazione")
    before = {"role": m["role"], "permissions": P.effective(m), "persona_id": m.get("persona_id")}
    after_m = {**m, "role": new_role, "permissions": new_perm}
    after = {"role": new_role, "permissions": P.effective(after_m), "persona_id": new_pid}
    if before == after and (m.get("permissions") or {}) == new_perm:
        return {"ok": True, "changed": False}
    await db.memberships.update_one({"org_id": oid, "user_id": target_id},
                                    {"$set": {"role": new_role, "permissions": new_perm, "persona_id": new_pid, "updated_at": now_iso()}})
    detail = f"Prima: {_perm_summary(before['role'], before['permissions'])} → Dopo: {_perm_summary(after['role'], after['permissions'])}"
    await record_audit(admin, "permissions_changed", org_id=oid, org_name=org.get("nome"),
                       target_email=tgt.get("email"), target_name=tgt.get("name"), detail=detail,
                       meta={"target_user_id": target_id, "before": before, "after": after})
    return {"ok": True, "changed": True, "permissions": after["permissions"], "role": new_role}


@api.get("/org/permissions/audit")
async def org_permissions_audit(admin: dict = Depends(require_org_admin)):
    rows = await db.audit_logs.find(
        {"org_id": admin["org_id"], "action": {"$in": ["permissions_changed", "member_role_changed"]}},
        {"_id": 0, "meta": 0}).sort("created_at", -1).to_list(200)
    return {"items": [_org_visible_audit(r) for r in rows]}


ADMIN_DISPLAY_NAME = "Assistenza CRMEvent"


def _org_visible_audit(r: dict) -> dict:
    """Vista per l'organizzazione: le operazioni del Super Admin non appaiono come attività di un collaboratore.
    L'identità reale resta nel registro tecnico (/platform/audit, solo Super Admin)."""
    if r.get("actor_role") == "superadmin" or r.get("scope") == "platform_admin":
        return {**r, "actor_name": ADMIN_DISPLAY_NAME, "actor_email": None, "actor_user_id": None, "actor_role": "platform_admin"}
    return r


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
    uu = u or {}
    _nm = uu.get("name") or ""
    per = await db.persons.find_one({"org_id": m["org_id"], "id": m["persona_id"]}, {"_id": 0, "nome": 1, "cognome": 1}) if m.get("persona_id") else None
    return {"user_id": m["user_id"], "email": uu.get("email"), "name": uu.get("name"),
            "nome": (per or {}).get("nome") or uu.get("nome") or (_nm.split(" ")[0] if _nm else ""),
            "cognome": (per or {}).get("cognome") or uu.get("cognome") or (" ".join(_nm.split(" ")[1:]) if _nm else ""),
            "telefono": (u or {}).get("telefono"),
            "role": m["role"], "role_label": ORG_ROLE_LABELS.get(m["role"], m["role"]),
            "active": m.get("active", True), "account_active": (u or {}).get("active", True),
            "created_at": (u or {}).get("created_at"), "last_login_at": (u or {}).get("last_login_at"),
            "auth_provider": (u or {}).get("auth_provider"),
            "is_superadmin": (u or {}).get("role") == "superadmin"}


async def _org_detail(org_id: str) -> dict:
    org = await _org_or_404(org_id)
    members = await db.memberships.count_documents({"org_id": org_id, "active": True})
    events = await db.events.count_documents({"org_id": org_id})
    st = subscriptions.org_state(org, await SAAS["get_config"]())
    return {"id": org["id"], "nome": org.get("nome"), "type": org.get("type", "cliente"),
            "status": org.get("status", "active"), "created_at": org.get("created_at"),
            "members": members, "events": events, "subscription": _sub_summary(org),
            "formula": st.get("assigned_plan") if st.get("enabled") else None, "saas": st}


class OrgCreateIn(BaseModel):
    nome: str
    type: str = "cliente"
    status: str = "active"


class OrgUpdateIn(BaseModel):
    nome: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None
    formula: Optional[str] = None  # "" = nessuna formula


class MemberAddIn(BaseModel):
    email: EmailStr
    role: str = "user"
    persona_id: Optional[str] = None


class MemberUpdateIn(BaseModel):
    role: Optional[str] = None
    active: Optional[bool] = None


class InviteCreateIn(BaseModel):
    email: EmailStr
    role: str = "user"
    nome: Optional[str] = None
    cognome: Optional[str] = None
    telefono: Optional[str] = None
    permissions: Optional[dict] = None  # configurati alla creazione, applicati all'accettazione
    persona_id: Optional[str] = None


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
    if body.nome and TN.business_name(body.nome.strip()) != org.get("nome"):
        upd["nome"] = TN.business_name(body.nome.strip()); changes.append(f"nome: {org.get('nome')} → {upd['nome']}")
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
    if body.formula is not None:
        await SAAS["set_formula"](org_id, body.formula or None, admin)
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
    if not body.persona_id or not await db.staff.find_one({"org_id": org_id, "persona_id": body.persona_id, "categoria": {"$in": ["staff", "collaboratore"]}}, {"_id": 1}):
        raise HTTPException(status_code=400, detail="Ogni account deve partire da una persona dello Staff dell'organizzazione: usa «Invita utente»")
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
    await SAAS["check_limit"](org_id, "users")
    if existing:
        await db.memberships.update_one({"id": existing["id"]}, {"$set": {"active": True, "role": role, "updated_at": now_iso()}})
    else:
        await _ensure_membership(target["user_id"], org_id, role, user["user_id"])
    await db.memberships.update_one({"user_id": target["user_id"], "org_id": org_id}, {"$set": {"persona_id": body.persona_id}})
    await record_audit(user, "member_added", org_id=org_id, org_name=org.get("nome"),
                       target_email=email, target_name=target.get("name"), detail=f"Ruolo: {ORG_ROLE_LABELS[role]}")
    asyncio.create_task(brevo_org_lists.sync_invited_user(db, target["user_id"], org_id))
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
        upd["role"] = new_role; upd["permissions"] = {}; changes.append(f"ruolo: {ORG_ROLE_LABELS[m['role']]} → {ORG_ROLE_LABELS[new_role]}"); action = "member_role_changed"
    if body.active is not None and body.active != m.get("active", True):
        if not body.active and m["role"] == "admin_org":
            await _guard_last_admin(org, target_id)
        if body.active:
            await SAAS["check_limit"](org_id, "users")
        upd["active"] = body.active; changes.append(f"accesso: {'attivo' if body.active else 'disabilitato'}")
        action = action or ("member_enabled" if body.active else "member_disabled")
    if upd:
        upd["updated_at"] = now_iso()
        await db.memberships.update_one({"id": m["id"]}, {"$set": upd})
        await record_audit(user, action, org_id=org_id, org_name=org.get("nome"),
                           target_email=(tgt or {}).get("email"), target_name=(tgt or {}).get("name"),
                           detail="; ".join(changes))
        # Cambio ruolo/accesso → aggiorna gli attributi Brevo (il contatto non viene mai rimosso).
        try:
            await sync_registered_user(target_id, org_id, source="member_updated")
        except Exception as e:
            logger.error(f"registered-user sync error: {e}")
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
    nome, cognome = _split_name(u)
    return {"user_id": u["user_id"], "name": u.get("name"), "email": u.get("email"), "nome": nome, "cognome": cognome,
            "role": u.get("role"), "role_label": ROLE_LABELS_USER.get(u.get("role"), u.get("role")),
            "active": u.get("active", True), "created_at": u.get("created_at"),
            "last_login_at": u.get("last_login_at"), "auth_provider": u.get("auth_provider"),
            "person_id": u.get("person_id"), "primary_org": primary,
            "org_names": sorted(set(n for n in org_names if n)), "memberships": memberships,
            "is_superadmin": u.get("role") == "superadmin"}


def _split_name(u: dict):
    nm = (u.get("name") or "").strip()
    return (u.get("nome") or (nm.split(" ")[0] if nm else ""),
            u.get("cognome") or (" ".join(nm.split(" ")[1:]) if nm else ""))


async def require_base_superadmin(request: Request) -> dict:
    """Super Admin reale (ignora un'eventuale sessione di assistenza attiva)."""
    u = await _get_base_user(request)
    if u.get("role") != "superadmin":
        raise HTTPException(status_code=403, detail="Accesso riservato al Super Admin CRMEvent")
    return u


class SupportStartIn(BaseModel):
    user_id: str
    org_id: Optional[str] = None


@api.post("/platform/impersonate")
async def support_start(body: SupportStartIn, request: Request, response: Response, sa: dict = Depends(require_base_superadmin)):
    t = await db.users.find_one({"user_id": body.user_id}, {"_id": 0, "password_hash": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Account non trovato")
    if t.get("role") == "superadmin":
        raise HTTPException(status_code=400, detail="Non è possibile accedere come Super Admin")
    mems = {m["org_id"]: m for m in await db.memberships.find({"user_id": t["user_id"]}, {"_id": 0}).to_list(200)}
    opts = list(mems) or ([t["org_id"]] if t.get("org_id") else [])
    orgs = [{"org_id": o["id"], "nome": o.get("nome")} for o in await db.organizations.find({"id": {"$in": opts}}, {"_id": 0, "id": 1, "nome": 1}).to_list(200)]
    orgs.sort(key=lambda o: (o["nome"] or "").lower())
    if not orgs:
        raise HTTPException(status_code=400, detail="L'utente non appartiene a nessuna organizzazione")
    org_id = body.org_id or (orgs[0]["org_id"] if len(orgs) == 1 else None)
    if not org_id:
        raise HTTPException(status_code=409, detail={"code": "choose_org", "orgs": orgs, "message": "Scegli l'organizzazione da visualizzare"})
    org = next((o for o in orgs if o["org_id"] == org_id), None)
    if not org:
        raise HTTPException(status_code=400, detail="L'utente non appartiene all'organizzazione selezionata")
    prev = request.cookies.get(SUPPORT_COOKIE)
    if prev:
        ps = await db.support_sessions.find_one({"token_hash": _sha(prev), "superadmin_id": sa["user_id"], "active": True}, {"_id": 0})
        if ps:
            await _end_support(sa, ps, "impersonation_ended")
    nome, cognome = _split_name(t)
    read_only = t.get("active") is False or (org_id in mems and mems[org_id].get("active", True) is False)
    tok = secrets.token_urlsafe(32)
    s = {"id": new_id(), "token_hash": _sha(tok), "superadmin_id": sa["user_id"], "target_user_id": t["user_id"],
         "target_email": t.get("email"), "target_name": f"{cognome} {nome}".strip() or t.get("email"),
         "org_id": org_id, "org_name": org["nome"], "orgs": orgs, "read_only": read_only, "active": True,
         "started_at": now_iso(), "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=SUPPORT_MINUTES)).isoformat()}
    await db.support_sessions.insert_one({**s})
    set_auth_cookie(response, SUPPORT_COOKIE, tok, SUPPORT_MINUTES * 60)
    await record_audit(sa, "impersonation_started", org_id=org_id, org_name=org["nome"], target_email=s["target_email"],
                       target_name=s["target_name"], detail="Sola lettura (account disabilitato)" if read_only else None,
                       meta={"support_session_id": s["id"], "target_user_id": t["user_id"], "expires_at": s["expires_at"]})
    return {"ok": True, "expires_at": s["expires_at"], "read_only": read_only, "org_id": org_id}


@api.post("/platform/impersonate/stop")
async def support_stop(request: Request, response: Response, sa: dict = Depends(require_base_superadmin)):
    tok = request.cookies.get(SUPPORT_COOKIE)
    if tok:
        s = await db.support_sessions.find_one({"token_hash": _sha(tok), "superadmin_id": sa["user_id"], "active": True}, {"_id": 0})
        if s:
            await _end_support(sa, s, "impersonation_ended")
    response.delete_cookie(SUPPORT_COOKIE, path="/", secure=True, samesite="none")
    return {"ok": True}


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
    for coll in ("user_sessions", "password_reset_tokens", "calendar_connections", "calendar_event_links", "user_notes"):
        await db[coll].delete_many({"user_id": user_id})
    await db.users.delete_one({"user_id": user_id})
    await record_audit(admin, "account_deleted", org_id=u.get("org_id"),
                       target_email=u.get("email"), target_name=u.get("name"),
                       detail="Account eliminato · anagrafica Persona e dati organizzazione conservati")
    return {"ok": True}


class PlatformUserProfileIn(BaseModel):
    nome: str
    cognome: Optional[str] = None
    email: str
    telefono: Optional[str] = None


@api.patch("/platform/users/{user_id}/profile")
async def platform_user_profile_update(user_id: str, body: PlatformUserProfileIn, admin: dict = Depends(require_superadmin)):
    """Super Admin: corregge l'anagrafica di un account collegato (Nome, Cognome, Email, Cellulare).
    Il cellulare è obbligatorio e salvato in E.164 (permette di completare utenti legacy senza numero).
    Non tocca crediti, ruoli od organizzazioni; aggiorna solo il contatto Brevo dell'utente registrato."""
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not u:
        raise HTTPException(status_code=404, detail="Account non trovato")
    if u.get("role") == "superadmin":
        raise HTTPException(status_code=400, detail="L'anagrafica del Super Admin non è modificabile da qui")
    nome = TN.person_name((body.nome or "").strip())
    cognome = TN.person_name((body.cognome or "").strip())
    if not nome:
        raise HTTPException(status_code=400, detail="Il nome è obbligatorio")
    email = (body.email or "").strip().lower()
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="Email non valida")
    if email != (u.get("email") or "").lower():
        clash = await db.users.find_one({"email": email, "user_id": {"$ne": user_id}})
        if clash:
            raise HTTPException(status_code=400, detail="Esiste già un account con questa email")
    phone = _normalize_phone(body.telefono)
    full_name = f"{nome} {cognome}".strip()
    changes = []
    if full_name != (u.get("name") or ""): changes.append("nome")
    if email != (u.get("email") or "").lower(): changes.append("email")
    if phone != (u.get("telefono") or ""): changes.append("cellulare")
    await db.users.update_one({"user_id": user_id}, {"$set": {
        "name": full_name, "nome": nome, "cognome": cognome,
        "email": email, "telefono": phone, "updated_at": now_iso()}})
    mem = await db.memberships.find_one({"user_id": user_id, "active": True}, {"_id": 0})
    if mem and mem.get("org_id"):
        try:
            await sync_registered_user(user_id, mem["org_id"], nome=nome, cognome=cognome, source="profile_edit")
        except Exception as e:
            logger.error(f"registered-user sync error: {e}")
    await record_audit(admin, "account_profile_updated", org_id=u.get("org_id"),
                       target_email=email, target_name=full_name,
                       detail="Anagrafica aggiornata: " + (", ".join(changes) if changes else "nessuna modifica"))
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
PUBLIC_SITE_URL = (os.environ.get("PUBLIC_SITE_URL") or "https://crmevent.it").rstrip("/")
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


# ---------------- Utenti registrati CRMEvent (lista Brevo separata dai Lead) ----------------
async def _registered_list_id(create: bool = True):
    lid = await _get_setting("brevo_registered_list_id")
    if lid:
        return lid
    if not (create and brevo_funnel.is_configured()):
        return None
    res = await brevo_funnel.ensure_registered_list()
    if res.get("id"):
        await _set_setting("brevo_registered_list_id", res["id"])
        await _set_setting("brevo_registered_list_name", res.get("name") or brevo_funnel.REGISTERED_LIST_NAME)
        return res["id"]
    return None


async def _brevo_registered_attrs(u: dict) -> dict:
    """Attributi Brevo per un utente registrato, calcolati da TUTTE le sue membership attive.
    Multiutenza: ORGANIZZAZIONE elenca ogni org (separate da virgola, nessun duplicato),
    RUOLO_UTENTE usa il ruolo più alto; crediti/eventi sono aggregati. CRMEvent resta la fonte di verità."""
    mems = await db.memberships.find({"user_id": u["user_id"], "active": True}, {"_id": 0}).to_list(500)
    org_names, roles = [], []
    credits = created = activated = 0
    for m in mems:
        org = await db.organizations.find_one({"id": m["org_id"]}, {"_id": 0})
        if not org:
            continue
        if org.get("nome"):
            org_names.append(org["nome"])
        roles.append(m.get("role"))
        created += await db.events.count_documents({"org_id": m["org_id"]})
        activated += await db.events.count_documents({"org_id": m["org_id"], "credit_state": {"$in": ["attivo", "sospeso", "concluso"]}})
        credits += (org.get("credits") or {}).get("balance", 0)
    role_label = "Admin Organizzazione" if "admin_org" in roles else ("Utente" if roles else "Admin Organizzazione")
    name = u.get("name") or ""
    return {
        "NOME": u.get("nome") or (name.split(" ")[0] if name else None),
        "COGNOME": u.get("cognome") or (" ".join(name.split(" ")[1:]) or None),
        "ORGANIZZAZIONE": ", ".join(dict.fromkeys(org_names)) or None,
        "DATA_REGISTRAZIONE": (u.get("registered_at") or u.get("created_at") or now_iso())[:10],
        "CREDITI_DISPONIBILI": credits,
        "EVENTI_CREATI": created,
        "EVENTI_ATTIVATI": activated,
        "ULTIMO_ACCESSO": (u.get("last_login_at") or now_iso())[:10],
        "CELLULARE": u.get("telefono") or u.get("cellulare"),
        "RUOLO_UTENTE": role_label,
    }


async def sync_registered_user(user_id: str, org_id: str = None, *, nome=None, cognome=None, source="registration"):
    """Upsert (per email, nessun duplicato) di un utente REGISTRATO nella lista Brevo
    'CRMEvent · Utenti registrati'. Best-effort, nessuna email inviata. Gli attributi sono calcolati
    da TUTTE le membership attive (multiutenza). Non rimuove MAI il contatto da altre liste (es. Lead).
    `org_id` è solo informativo: gli attributi derivano comunque da tutte le org attive dell'utente."""
    if not brevo_funnel.is_configured():
        return {"ok": False, "skipped": True}
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not u or not u.get("email"):
        return {"ok": False, "error": "utente non trovato"}
    # Non sincronizzare account staff/volontari (solo area personale) né il Super Admin.
    if u.get("role") in ("volunteer", "staff", "superadmin"):
        return {"ok": False, "skipped": True}
    # Solo chi si è registrato autonomamente: gli invitati seguono il percorso dedicato (liste per organizzazione).
    if source != "registration" and not (u.get("self_registered") or await db.organizations.find_one({"owner_user_id": user_id}, {"_id": 1})):
        return {"ok": False, "skipped": True, "reason": "invited"}
    # Deve esistere almeno una membership attiva: un invito pending non rende "registrato" l'utente.
    if not await db.memberships.find_one({"user_id": user_id, "active": True}):
        return {"ok": False, "skipped": True}
    attrs = await _brevo_registered_attrs(u)
    if nome:
        attrs["NOME"] = nome
    if cognome:
        attrs["COGNOME"] = cognome
    try:
        await brevo_funnel.ensure_user_attributes()
    except Exception:
        pass
    lid = await _registered_list_id(create=True)
    try:
        res = await brevo_funnel.upsert_registered_contact(email=u["email"], attributes=attrs, list_ids=([lid] if lid else None))
    except Exception as e:
        logger.error(f"brevo registered sync failed: {e}")
        return {"ok": False, "error": str(e)}
    if res.get("ok"):
        await _set_setting("brevo_registered_last_sync", now_iso())
    return res


@api.get("/platform/brevo/registered-users")
async def platform_registered_users(admin: dict = Depends(require_superadmin)):
    """Stato della lista Brevo 'Utenti registrati' (separata da Lead e Disponibilità eventi)."""
    if not brevo_funnel.is_configured():
        return {"configured": False, "list_id": None, "name": brevo_funnel.REGISTERED_LIST_NAME,
                "contacts": None, "last_sync": None, "attributes": brevo_funnel.USER_ATTRIBUTES}
    lid = await _registered_list_id(create=True)
    count = None
    if lid:
        try:
            count = await brevo_funnel.list_contact_count(lid)
        except Exception:
            count = None
    return {"configured": True, "list_id": lid,
            "name": await _get_setting("brevo_registered_list_name") or brevo_funnel.REGISTERED_LIST_NAME,
            "contacts": count, "last_sync": await _get_setting("brevo_registered_last_sync"),
            "attributes": brevo_funnel.USER_ATTRIBUTES}


@api.post("/platform/brevo/sync-registered-users")
async def platform_sync_registered_users(admin: dict = Depends(require_superadmin)):
    """Riallineamento massivo e idempotente: fa l'upsert su Brevo di tutti gli utenti CRMEvent
    con almeno una membership attiva (un solo contatto per email, nessun duplicato).
    Non invia email, non tocca funnel/automazioni/template/lista Lead. Ritorna il conteggio
    'Analizzati · Inseriti · Aggiornati · Errori'."""
    if not brevo_funnel.is_configured():
        raise HTTPException(status_code=400, detail="BREVO_API_KEY non configurata nei Secrets")
    try:
        await brevo_funnel.ensure_user_attributes()
    except Exception:
        pass
    lid = await _registered_list_id(create=True)
    analyzed = inserted = updated = errors = 0
    seen = set()
    user_ids = await db.memberships.distinct("user_id", {"active": True})
    for uid in user_ids:
        u = await db.users.find_one({"user_id": uid}, {"_id": 0})
        if not u or not u.get("email"):
            continue
        if u.get("role") in ("volunteer", "staff", "superadmin"):
            continue
        if not (u.get("self_registered") or await db.organizations.find_one({"owner_user_id": uid}, {"_id": 1})):
            continue  # invitati: percorso dedicato (non si rimuovono quelli già presenti)
        email = u["email"].lower()
        if email in seen:
            continue
        seen.add(email)
        analyzed += 1
        attrs = await _brevo_registered_attrs(u)
        try:
            res = await brevo_funnel.upsert_registered_contact(
                email=u["email"], attributes=attrs, list_ids=([lid] if lid else None))
        except Exception as e:
            logger.error(f"brevo backfill sync failed for {email}: {e}")
            errors += 1
            continue
        if not res.get("ok"):
            errors += 1
        elif res.get("status") == 201:
            inserted += 1
        else:
            updated += 1
    await _set_setting("brevo_registered_last_sync", now_iso())
    return {"analyzed": analyzed, "inserted": inserted, "updated": updated, "errors": errors,
            "message": f"Analizzati {analyzed} · Inseriti {inserted} · Aggiornati {updated} · Errori {errors}"}


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
            "<div style='height:4px;width:60px;background:#0ABAB5;margin:0 auto 20px;border-radius:2px'></div>"
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
@api.post("/cron/event-renewals")
async def cron_event_renewals(authorization: str = Header(default="")):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    expected = f"Bearer {WEBHOOK_CRON_SECRET}"
    if not WEBHOOK_CRON_SECRET or not secrets.compare_digest(authorization or "", expected):
        raise HTTPException(status_code=401, detail="unauthorized")
    asyncio.create_task(run_event_renewals())  # idempotente: addebiti protetti da idempotency_key per mese
    return {"accepted": True}


@api.post("/cron/brevo-funnel-tick")
async def cron_brevo_funnel_tick(request: Request, authorization: str = Header(default="")):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    expected = f"Bearer {WEBHOOK_CRON_SECRET}"
    if not WEBHOOK_CRON_SECRET or not secrets.compare_digest(authorization or "", expected):
        raise HTTPException(status_code=401, detail="unauthorized")
    asyncio.create_task(process_due_funnel_steps())
    asyncio.create_task(demo_booking.tick(db, APP_URL))  # retry sync Brevo demo + promemoria del giorno prima
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
            "nome": inv.get("nome"), "cognome": inv.get("cognome"), "telefono": inv.get("telefono"),
            "status": _invite_status(inv), "created_at": inv.get("created_at"), "expires_at": inv.get("expires_at")}


async def _send_invite_email(email: str, org_name: str, token: str, role: str, nome: Optional[str] = None) -> None:
    link = f"{APP_URL}/invito?token={token}"
    await email_utils.send_email(
        to=email, subject=f"Invito ad accedere a {org_name} su CRMEvent",
        html=email_utils.link_email(
            name=nome or "",
            intro=f"Sei stato invitato ad accedere all'organizzazione «{org_name}» su CRMEvent con il ruolo {ORG_ROLE_LABELS.get(role, role)}. Clicca per accettare l'invito e accedere.",
            cta_label="Accetta l'invito", url=link,
            footer_note="L'invito scade tra 7 giorni ed è utilizzabile una sola volta."))


async def _create_invite(org: dict, email: str, role: str, invited_by: str, lead_id: Optional[str] = None,
                         nome: Optional[str] = None, cognome: Optional[str] = None, telefono: Optional[str] = None) -> dict:
    await db.org_invites.update_many({"org_id": org["id"], "email": email, "status": "pending"},
                                     {"$set": {"status": "revoked", "updated_at": now_iso()}})
    await SAAS["check_limit"](org["id"], "users")
    token = secrets.token_urlsafe(32)
    inv = {"id": new_id(), "org_id": org["id"], "email": email, "role": role, "token": token,
           "nome": (nome or "").strip() or None, "cognome": (cognome or "").strip() or None, "telefono": telefono,
           "status": "pending", "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
           "invited_by": invited_by, "lead_id": lead_id, "created_at": now_iso(), "updated_at": now_iso()}
    await db.org_invites.insert_one(inv)
    return inv


@api.get("/platform/organizations/{org_id}/invites")
async def list_org_invites(org_id: str, user: dict = Depends(get_current_user)):
    await _require_manage(user, org_id)
    invs = await db.org_invites.find({"org_id": org_id}, {"_id": 0, "token": 0}).sort("created_at", -1).to_list(500)
    return [_invite_view(i) for i in invs]


STAFF_CATS = ["staff", "collaboratore"]


async def _staff_person_account(org_id: str, p: dict) -> Optional[dict]:
    """Account CRMEvent già collegato alla persona Staff (per ID o, in subordine, per email)."""
    m = await db.memberships.find_one({"org_id": org_id, "persona_id": p["id"]}, {"_id": 0})
    if not m and p.get("email"):
        u = await db.users.find_one({"email": p["email"].lower()}, {"_id": 0, "user_id": 1})
        if u:
            m = await db.memberships.find_one({"org_id": org_id, "user_id": u["user_id"]}, {"_id": 0})
    if not m:
        return None
    return {"user_id": m["user_id"], "role": m["role"], "role_label": ORG_ROLE_LABELS.get(m["role"], m["role"]),
            "active": m.get("active", True), "linked_by_id": m.get("persona_id") == p["id"]}


@api.get("/platform/organizations/{org_id}/staff-candidates")
async def staff_candidates(org_id: str, q: str = "", user: dict = Depends(get_current_user)):
    """Persone dell'org con almeno una presenza Staff/Collaboratore: base obbligatoria per gli inviti."""
    await _require_manage(user, org_id)
    links = await db.staff.find({"org_id": org_id, "categoria": {"$in": STAFF_CATS}}, {"_id": 0}).to_list(50000)
    pids = list({l["persona_id"] for l in links if l.get("persona_id")})
    query = {"org_id": org_id, "id": {"$in": pids}}
    if q.strip():
        rx = {"$regex": re.escape(q.strip()), "$options": "i"}
        query["$or"] = [{"nome": rx}, {"cognome": rx}, {"email": rx}, {"cellulare": rx}, {"telefono": rx}]
    persons = await db.persons.find(query, {"_id": 0}).to_list(5000)
    persons.sort(key=lambda p: ((p.get("cognome") or "").lower(), (p.get("nome") or "").lower()))
    persons = persons[:60]
    events = {e["id"]: e for e in await db.events.find({"org_id": org_id}, {"_id": 0, "id": 1, "nome": 1, "data_inizio": 1}).to_list(5000)}
    teams = {t["id"]: t for t in await db.teams.find({"org_id": org_id}, {"_id": 0, "id": 1, "nome": 1, "evento_id": 1, "responsabile_id": 1}).to_list(10000)}
    all_links = await db.staff.find({"org_id": org_id, "persona_id": {"$in": [p["id"] for p in persons]}}, {"_id": 0}).to_list(50000)
    out = []
    for p in persons:
        mine = [l for l in all_links if l["persona_id"] == p["id"]]
        tnames = sorted({teams[l["team_id"]]["nome"] for l in mine if l.get("team_id") in teams}, key=str.lower)
        leader = sorted({t["nome"] for t in teams.values() if t.get("responsabile_id") == p["id"]}, key=str.lower)
        evs = sorted({events[l["evento_id"]]["nome"] for l in mine if l.get("evento_id") in events}, key=str.lower)
        cats = sorted({l.get("categoria") for l in mine if l.get("categoria")})
        pend = await db.org_invites.find_one({"org_id": org_id, "persona_id": p["id"], "status": "pending"}, {"_id": 0, "id": 1, "email": 1})
        out.append({"id": p["id"], "nome": p.get("nome") or "", "cognome": p.get("cognome") or "", "email": p.get("email") or "",
                    "cellulare": p.get("cellulare") or p.get("telefono") or "", "categorie": cats, "teams": tnames,
                    "leader_of": leader, "events": evs, "account": await _staff_person_account(org_id, p), "pending_invite": pend})
    ev_list = sorted(events.values(), key=lambda e: e.get("data_inizio") or "", reverse=True)
    return {"items": out, "events": [{"id": e["id"], "nome": e.get("nome")} for e in ev_list]}


class StaffCandidateIn(BaseModel):
    evento_id: str
    nome: str
    cognome: str
    email: Optional[str] = None
    cellulare: Optional[str] = None


@api.post("/platform/organizations/{org_id}/staff-candidates")
async def add_staff_candidate(org_id: str, body: StaffCandidateIn, user: dict = Depends(get_current_user)):
    """'Aggiungi allo Staff' dal flusso invito: anagrafica + presenza Staff sull'evento (riusa persona se già esiste)."""
    await _require_manage(user, org_id)
    if not await db.events.find_one({"org_id": org_id, "id": body.evento_id}, {"_id": 1}):
        raise HTTPException(status_code=404, detail="Evento non trovato")
    if not body.nome.strip() or not body.cognome.strip():
        raise HTTPException(status_code=400, detail="Nome e cognome sono obbligatori")
    email = (body.email or "").strip().lower()
    tel = _normalize_phone(body.cellulare) if (body.cellulare or "").strip() else ""
    conds = ([{"email": email}] if email else []) + ([{"cellulare": tel}] if tel else [])
    person = await db.persons.find_one({"org_id": org_id, "$or": conds}, {"_id": 0}) if conds else None
    await SAAS["check_people"](org_id, (person or {}).get("id"))
    if not person:
        person = TN.normalize_fields("persons", {"id": new_id(), "org_id": org_id, "nome": body.nome.strip(), "cognome": body.cognome.strip(),
                  "email": email, "cellulare": tel, "created_at": now_iso()})
        await db.persons.insert_one({**person})
    link = await db.staff.find_one({"org_id": org_id, "persona_id": person["id"], "evento_id": body.evento_id}, {"_id": 0})
    if not link:
        await db.staff.insert_one({"id": new_id(), "org_id": org_id, "persona_id": person["id"], "evento_id": body.evento_id,
                                   "categoria": "staff", "stato": "da_contattare", "created_at": now_iso()})
    elif link.get("categoria") not in STAFF_CATS:
        await db.staff.update_one({"id": link["id"]}, {"$set": {"categoria": "staff"}})
    return {"id": person["id"]}


@api.post("/platform/organizations/{org_id}/invites")
async def create_org_invite(org_id: str, body: InviteCreateIn, user: dict = Depends(get_current_user)):
    """Invito SEMPRE da una persona Staff esistente (persona_id): l'anagrafica resta il riferimento."""
    await _require_manage(user, org_id)
    org = await _org_or_404(org_id)
    role = _norm_role(body.role)
    if not body.persona_id:
        raise HTTPException(status_code=400, detail="Seleziona una persona dallo Staff dell'organizzazione")
    person = await db.persons.find_one({"org_id": org_id, "id": body.persona_id}, {"_id": 0})
    if not person or not await db.staff.find_one({"org_id": org_id, "persona_id": body.persona_id, "categoria": {"$in": STAFF_CATS}}, {"_id": 1}):
        raise HTTPException(status_code=400, detail="La persona selezionata non fa parte dello Staff dell'organizzazione")
    if await _staff_person_account(org_id, person):
        raise HTTPException(status_code=409, detail="Questo membro dello Staff dispone già di un account CRMEvent.")
    email = (person.get("email") or "").lower()
    if not email:  # Staff senza email: si completa la STESSA anagrafica
        email = body.email.lower()
        if await db.persons.find_one({"org_id": org_id, "email": email, "id": {"$ne": person["id"]}}, {"_id": 1}):
            raise HTTPException(status_code=400, detail="Email già usata da un'altra persona dell'organizzazione")
        await db.persons.update_one({"id": person["id"]}, {"$set": {"email": email, "updated_at": now_iso()}})
    eu = await db.users.find_one({"email": email}, {"_id": 0})
    if eu and await db.memberships.find_one({"user_id": eu["user_id"], "org_id": org_id}):
        raise HTTPException(status_code=409, detail="Questo membro dello Staff dispone già di un account CRMEvent.")
    telefono = _normalize_phone(person.get("cellulare") or person.get("telefono")) if (person.get("cellulare") or person.get("telefono")) else None
    inv = await _create_invite(org, email, role, user["user_id"],
                               nome=person.get("nome"), cognome=person.get("cognome"), telefono=telefono)
    pre = {"persona_id": person["id"]}
    if body.permissions and role != "admin_org":
        pre["permissions"] = P.normalize_permissions(body.permissions, role)
    await db.org_invites.update_one({"id": inv["id"]}, {"$set": pre})
    await db.persons.update_one({"id": person["id"]}, {"$set": {"invite_status": "invito_inviato", "updated_at": now_iso()}})
    nome = person.get("nome")
    sent = True
    try:
        await _send_invite_email(email, org.get("nome"), inv["token"], role, nome=nome)
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
        await _send_invite_email(inv["email"], org.get("nome"), token, inv["role"], nome=inv.get("nome"))
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
    telefono: Optional[str] = None


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
    if not (m and m.get("active", True)):
        await SAAS["check_limit"](inv["org_id"], "users_accept")
    if m:
        await db.memberships.update_one({"id": m["id"]}, {"$set": {"active": True, "role": role, "updated_at": now_iso()}})
    else:
        await _ensure_membership(target_user["user_id"], inv["org_id"], role, inv.get("invited_by"))
    pre = {k: inv[k] for k in ("permissions", "persona_id") if inv.get(k)}
    if pre:  # permessi/collegamento Staff configurati dall'Admin al momento dell'invito
        await db.memberships.update_one({"user_id": target_user["user_id"], "org_id": inv["org_id"]}, {"$set": pre})
    await db.org_invites.update_one({"id": inv["id"]}, {"$set": {"status": "accepted", "accepted_at": now_iso(),
        "accepted_user_id": target_user["user_id"], "updated_at": now_iso()}})
    # Dedupe: once accepted, remove any other invite rows for the same email in this org so the
    # same account can never show up twice in the invite list (fixes duplicate accepted rows).
    await db.org_invites.delete_many({"org_id": inv["org_id"], "email": inv["email"], "id": {"$ne": inv["id"]}})
    if inv.get("persona_id"):  # collegamento Account -> Persona Staff tramite ID
        await db.persons.update_one({"org_id": inv["org_id"], "id": inv["persona_id"]},
                                    {"$set": {"invite_status": "account_attivato", "user_id": target_user["user_id"], "updated_at": now_iso()}})
    if inv.get("lead_id"):
        await db.leads.update_one({"id": inv["lead_id"]}, {"$set": {"user_id": target_user["user_id"], "updated_at": now_iso()}})
    # Person (anagrafica) collegata a org+email: rifletti l'attivazione account sul profilo,
    # tenendola DISTINTA dallo 'stato' commerciale/operativo (es. da_contattare). Lo storico
    # commerciale del Lead non viene mai toccato qui.
    await db.persons.update_one(
        {"org_id": inv["org_id"], "email": inv["email"].lower()},
        {"$set": {"invite_status": "account_attivato", "user_id": target_user["user_id"],
                  "user_role": role, "invite_accepted_at": now_iso(), "updated_at": now_iso()}})
    await db.users.update_one({"user_id": target_user["user_id"]}, {"$set": {"last_login_at": now_iso()}})
    org = await db.organizations.find_one({"id": inv["org_id"]}, {"_id": 0})
    await record_audit(target_user, "invite_accepted", org_id=inv["org_id"], org_name=(org or {}).get("nome"),
                       target_email=target_user.get("email"), target_name=target_user.get("name"),
                       detail=f"Ruolo: {ORG_ROLE_LABELS[role]}")
    # Invitato: percorso dedicato (lista Utenti_invitati dell'org), mai la lista/funnel delle registrazioni autonome.
    asyncio.create_task(brevo_org_lists.sync_invited_user(db, target_user["user_id"], inv["org_id"]))


@api.get("/invites/{token}")
async def get_invite(token: str):
    inv = await db.org_invites.find_one({"token": token}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Invito non valido")
    org = await db.organizations.find_one({"id": inv["org_id"]}, {"_id": 0})
    exists = bool(await db.users.find_one({"email": inv["email"].lower()}))
    return {"email": inv["email"], "role": inv["role"], "role_label": ORG_ROLE_LABELS.get(inv["role"], inv["role"]),
            "nome": inv.get("nome"), "cognome": inv.get("cognome"), "telefono": inv.get("telefono"),
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
    inv_name = f"{(inv.get('nome') or '').strip()} {(inv.get('cognome') or '').strip()}".strip()
    full_name = TN.person_name((body.name or inv_name or "").strip())
    phone = _normalize_phone(body.telefono or inv.get("telefono"))
    await db.users.insert_one({"user_id": uid, "email": email, "name": full_name,
        "password_hash": hash_password(body.password), "role": "member", "auth_provider": "password",
        "telefono": phone, "registered_at": now_iso(),
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
    lead["origine"] = _lead_origine(lead)
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
    try:  # il lead si era registrato/richiesto demo autonomamente: resta nel percorso registrazioni
        await sync_registered_user(u["user_id"], body.org_id, source="registration")
    except Exception as e:
        logger.error(f"registered-user sync error: {e}")
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
        await _send_invite_email(email, org.get("nome"), inv["token"], role, nome=inv.get("nome"))
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
    _normalize_meals(meals)
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
            "persona_nome": (f"{p.get('cognome') or ''} {p.get('nome', '')}".strip() if p else None),
            "coperto": bool(s.get("persona_id")),
        })

    for x in lodgings + meals:
        for f in COST_FIELDS:
            x.pop(f, None)
    esig_by_person = {}
    for l in links:
        p = persons.get(l["persona_id"]) or {}
        esig_by_person[l["persona_id"]] = l.get("esigenze_alimentari") if l.get("esigenze_alimentari") is not None else p.get("esigenze_alimentari")
    meals_by_day = _briefing_meals(meals, esig_by_person)
    lodging_structures = _briefing_lodgings(lodgings, persons)

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
        "meals_by_day": meals_by_day, "lodging_structures": lodging_structures,
        "maps": maps, "sponsors": sponsors_out, "timeline": timeline,
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
    vol_no_resp = [f"{s.get('cognome') or ''} {s['nome']}".strip() for s in staff_out
                   if not s.get("responsabile") and s.get("categoria") == "volontario"]
    add("referenti", "Volontari con referente", not vol_no_resp,
        (f"{len(vol_no_resp)} volontari senza referente assegnato") if vol_no_resp else "")
    add("ospitalita", "Ospitalità / pasti gestiti", bool(meals_by_day or lodging_structures),
        "" if (meals_by_day or lodging_structures) else "Nessuna ospitalità o pasto assegnato")

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
    data["briefing_charge"] = await _briefing_charge_info(admin["org_id"], event_id)
    return data


class BriefingPublishIn(BaseModel):
    titolo: Optional[str] = None
    note: Optional[str] = None


async def _briefing_charge_info(org_id: str, event_id: str) -> dict:
    """Generazione briefing: addebito UNA TANTUM per evento (prima pubblicazione), poi gratis."""
    await _ensure_credits_setup()
    cfg = await _svc_cfg("ai_briefing")
    charged = bool(await db.credit_ledger.find_one({"org_id": org_id, "idempotency_key": f"ai_briefing:{event_id}"}, {"_id": 1}))
    applies = bool(cfg["active"] and cfg["cost"] and (cfg["svc"] or {}).get("consumo_active") and await _is_credit_model_org(org_id))
    return {"cost": cfg["cost"] if applies and not charged else 0, "charged": charged}


async def _charge_briefing_once(admin: dict, event_id: str):
    info = await _briefing_charge_info(admin["org_id"], event_id)
    if info["cost"]:
        ev = await db.events.find_one(oq(admin, id=event_id), {"_id": 0, "nome": 1}) or {}
        await _apply_credit_movement(admin["org_id"], -info["cost"], reason_code="ai_briefing", type_="debit",
                                     service_key="ai_briefing", event_id=event_id, user_id=admin.get("user_id"),
                                     idempotency_key=f"ai_briefing:{event_id}", note=f"Generazione briefing — {ev.get('nome')}")


@api.post("/events/{event_id}/briefing-versions")
async def publish_briefing(event_id: str, body: BriefingPublishIn, admin: dict = Depends(require_admin)):
    await _assert_event_operational(admin["org_id"], event_id)
    data = await _build_briefing(event_id, admin["org_id"])
    await _charge_briefing_once(admin, event_id)
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
async def reset_data(request: Request, user: dict = Depends(get_current_user)):
    # Riservato al Super Admin (anche via switcher "Org attiva"). Un Admin Organizzazione NON può
    # eseguire il reset, nemmeno con chiamata API diretta.
    if user.get("role") != "superadmin":
        raise HTTPException(status_code=403, detail="Operazione riservata al Super Admin")
    org_id = await _resolve_active_org(request, user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Seleziona un'organizzazione attiva prima del reset")
    for c in OPERATIONAL:
        await db[c].delete_many({"org_id": org_id})
    await db.users.delete_many({"role": {"$in": ["staff", "volunteer"]}, "org_id": org_id})
    counts = {c: await db[c].count_documents({"org_id": org_id}) for c in OPERATIONAL}
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


# ==================== Messaggi alle Organizzazioni (Super Admin → Dashboard org) ====================
MSG_TIPOLOGIE = {"informazione", "novita", "importante", "manutenzione"}
MSG_STATUSES = {"bozza", "attivo", "disattivato"}


class OrgMessageIn(BaseModel):
    titolo: str
    messaggio: str
    tipologia: str = "informazione"
    recipients_mode: str = "all"          # all | selected
    org_ids: Optional[List[str]] = None
    publish_at: Optional[str] = None      # iso; vuoto = subito
    end_at: Optional[str] = None
    require_ack: bool = False
    status: str = "attivo"                # bozza | attivo | disattivato


def _parse_iso(s):
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _msg_effective_status(m: dict) -> str:
    st = m.get("status", "attivo")
    if st in ("bozza", "disattivato"):
        return st
    now = datetime.now(timezone.utc)
    pub = _parse_iso(m.get("publish_at"))
    end = _parse_iso(m.get("end_at"))
    if pub and now < pub:
        return "programmato"
    if end and now > end:
        return "scaduto"
    return "pubblicato"


async def _msg_target_org_ids(m: dict, all_orgs=None):
    if m.get("recipients_mode") == "selected":
        return list(m.get("org_ids") or [])
    if all_orgs is None:
        all_orgs = await db.organizations.find({}, {"_id": 0, "id": 1, "status": 1}).to_list(5000)
    return [o["id"] for o in all_orgs if o.get("status") != "disabled"]


def _msg_clean(m: dict) -> dict:
    return {k: m.get(k) for k in ("id", "titolo", "messaggio", "tipologia", "recipients_mode",
            "org_ids", "publish_at", "end_at", "require_ack", "status", "created_at", "updated_at")}


@api.get("/platform/messages")
async def platform_list_messages(admin: dict = Depends(require_superadmin)):
    msgs = await db.org_messages.find({}, {"_id": 0}).sort("created_at", -1).to_list(2000)
    all_orgs = await db.organizations.find({}, {"_id": 0, "id": 1, "status": 1}).to_list(5000)
    out = []
    for m in msgs:
        target = await _msg_target_org_ids(m, all_orgs)
        recipients = len(await db.memberships.distinct("user_id", {"org_id": {"$in": target}, "active": True})) if target else 0
        reads = len(await db.org_message_reads.distinct("user_id", {"message_id": m["id"], "org_id": {"$in": target}, "read_at": {"$ne": None}})) if target else 0
        out.append({**_msg_clean(m), "effective_status": _msg_effective_status(m),
                    "orgs_reached": len(target), "recipients": recipients,
                    "read": reads, "unread": max(recipients - reads, 0)})
    return out


def _msg_doc_from_body(body: OrgMessageIn, existing: dict = None):
    tip = body.tipologia if body.tipologia in MSG_TIPOLOGIE else "informazione"
    status = body.status if body.status in MSG_STATUSES else ((existing or {}).get("status") or "attivo")
    mode = "selected" if body.recipients_mode == "selected" else "all"
    org_ids = [x for x in (body.org_ids or [])] if mode == "selected" else []
    if mode == "selected" and not org_ids:
        raise HTTPException(status_code=400, detail="Seleziona almeno un'organizzazione destinataria")
    if not body.titolo.strip() or not body.messaggio.strip():
        raise HTTPException(status_code=400, detail="Titolo e messaggio sono obbligatori")
    return {"titolo": body.titolo.strip(), "messaggio": body.messaggio.strip(), "tipologia": tip,
            "recipients_mode": mode, "org_ids": org_ids,
            "publish_at": body.publish_at or (existing or {}).get("publish_at") or now_iso(),
            "end_at": body.end_at or None, "require_ack": bool(body.require_ack) and tip == "importante",
            "status": status, "updated_at": now_iso()}


@api.post("/platform/messages")
async def platform_create_message(body: OrgMessageIn, admin: dict = Depends(require_superadmin)):
    doc = {"id": new_id(), **_msg_doc_from_body(body), "created_at": now_iso(), "created_by": admin["user_id"]}
    await db.org_messages.insert_one(doc)
    return _msg_clean(doc)


@api.put("/platform/messages/{mid}")
async def platform_update_message(mid: str, body: OrgMessageIn, admin: dict = Depends(require_superadmin)):
    m = await db.org_messages.find_one({"id": mid}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="Messaggio non trovato")
    upd = _msg_doc_from_body(body, existing=m)
    await db.org_messages.update_one({"id": mid}, {"$set": upd})
    return _msg_clean({**m, **upd})


@api.post("/platform/messages/{mid}/status")
async def platform_message_status(mid: str, body: dict, admin: dict = Depends(require_superadmin)):
    st = {"disattiva": "disattivato", "ripubblica": "attivo", "bozza": "bozza"}.get(body.get("action"))
    if not st:
        raise HTTPException(status_code=400, detail="Azione non valida")
    r = await db.org_messages.update_one({"id": mid}, {"$set": {"status": st, "updated_at": now_iso()}})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Messaggio non trovato")
    return {"ok": True, "status": st}


@api.delete("/platform/messages/{mid}")
async def platform_delete_message(mid: str, admin: dict = Depends(require_superadmin)):
    await db.org_messages.delete_one({"id": mid})
    await db.org_message_reads.delete_many({"message_id": mid})
    return {"ok": True}


@api.get("/platform/messages/{mid}/stats")
async def platform_message_stats(mid: str, admin: dict = Depends(require_superadmin)):
    m = await db.org_messages.find_one({"id": mid}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="Messaggio non trovato")
    target = await _msg_target_org_ids(m)
    mems = await db.memberships.find(
        {"org_id": {"$in": target}, "active": True}, {"_id": 0, "user_id": 1, "org_id": 1}
    ).to_list(20000) if target else []
    # Un utente è destinatario una sola volta per messaggio (la lettura è 1 doc per utente/messaggio)
    user_org = {}
    for mm in mems:
        user_org.setdefault(mm["user_id"], mm["org_id"])
    org_names = {o["id"]: o.get("nome") for o in await db.organizations.find(
        {"id": {"$in": target}}, {"_id": 0, "id": 1, "nome": 1}).to_list(5000)} if target else {}
    uids = list(user_org.keys())
    users = {u["user_id"]: u for u in await db.users.find(
        {"user_id": {"$in": uids}}, {"_id": 0, "user_id": 1, "name": 1, "email": 1}).to_list(20000)} if uids else {}
    read_docs = await db.org_message_reads.find(
        {"message_id": mid, "org_id": {"$in": target}, "read_at": {"$ne": None}},
        {"_id": 0, "user_id": 1, "org_id": 1, "read_at": 1}).to_list(20000)
    read_map = {r["user_id"]: (r.get("read_at"), r.get("org_id")) for r in read_docs}
    rows = []
    for uid, oid in user_org.items():
        rr = read_map.get(uid)
        read_at = rr[0] if rr else None
        disp_org = rr[1] if (rr and rr[1] in org_names) else oid
        u = users.get(uid) or {}
        rows.append({"org_id": disp_org, "org_name": org_names.get(disp_org),
                     "user_id": uid, "name": u.get("name") or "—",
                     "email": u.get("email") or "—", "read": bool(read_at), "read_at": read_at})
    rows.sort(key=lambda x: ((x["org_name"] or "").lower(), (x["name"] or "").lower()))
    total = len(rows)
    total_read = sum(1 for r in rows if r["read"])
    orgs = []
    for oid in target:
        orows = [r for r in rows if r["org_id"] == oid]
        orgs.append({"org_id": oid, "nome": org_names.get(oid), "recipients": len(orows),
                     "read": sum(1 for r in orows if r["read"]),
                     "unread": sum(1 for r in orows if not r["read"])})
    return {"message": _msg_clean(m), "effective_status": _msg_effective_status(m),
            "orgs_reached": len(target), "recipients": total, "read": total_read,
            "unread": max(total - total_read, 0), "users": rows, "orgs": orgs}


# -------- Org-facing: messaggi visibili nella Dashboard dell'organizzazione --------
@api.get("/my/messages")
async def my_messages(user: dict = Depends(require_admin)):
    org_id = user["org_id"]
    preview = user.get("role") == "superadmin"   # Super Admin che opera su un'org attiva = ANTEPRIMA
    q = {"status": "attivo", "$or": [{"recipients_mode": "all"}, {"org_ids": org_id}]}
    msgs = await db.org_messages.find(q, {"_id": 0}).sort("publish_at", -1).to_list(500)
    out = []
    for m in msgs:
        if _msg_effective_status(m) != "pubblicato":
            continue
        base = {"id": m["id"], "titolo": m["titolo"], "messaggio": m["messaggio"],
                "tipologia": m["tipologia"], "require_ack": bool(m.get("require_ack")),
                "publish_at": m.get("publish_at")}
        if preview:
            # Anteprima: nessuno stato personale, nessun filtro 'nascosto', nessuna scrittura.
            out.append({**base, "read": False, "ack": False})
            continue
        r = await db.org_message_reads.find_one({"message_id": m["id"], "user_id": user["user_id"]}, {"_id": 0})
        if r and r.get("hidden_at"):
            continue
        out.append({**base, "read": bool(r and r.get("read_at")), "ack": bool(r and r.get("ack_at"))})
    org_name = None
    if preview:
        o = await db.organizations.find_one({"id": org_id}, {"_id": 0, "nome": 1})
        org_name = (o or {}).get("nome")
    return {"preview": preview, "org_name": org_name, "messages": out}


async def _msg_assert_target(user: dict, m: dict):
    """Multi-tenant: la persona può interagire col messaggio solo se destinato alla sua org."""
    if m.get("recipients_mode") == "selected" and user["org_id"] not in (m.get("org_ids") or []):
        raise HTTPException(status_code=403, detail="Messaggio non destinato a questa organizzazione")


async def _msg_mark(user: dict, mid: str, *, hidden=False, ack=False):
    m = await db.org_messages.find_one({"id": mid}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="Messaggio non trovato")
    await _msg_assert_target(user, m)
    existing = await db.org_message_reads.find_one({"message_id": mid, "user_id": user["user_id"]}, {"_id": 0})
    patch = {"message_id": mid, "user_id": user["user_id"], "org_id": user["org_id"], "updated_at": now_iso(),
             "read_at": (existing or {}).get("read_at") or now_iso()}
    if hidden or ack:
        patch["hidden_at"] = now_iso()
    if ack:
        patch["ack_at"] = now_iso()
    if existing:
        await db.org_message_reads.update_one({"id": existing["id"]}, {"$set": patch})
    else:
        patch["id"] = new_id(); patch["created_at"] = now_iso()
        await db.org_message_reads.insert_one(patch)
    return {"ok": True}


@api.post("/my/messages/{mid}/read")
async def my_message_read(mid: str, user: dict = Depends(require_admin)):
    if user.get("role") == "superadmin":
        return {"ok": True, "preview": True}
    return await _msg_mark(user, mid)


@api.post("/my/messages/{mid}/hide")
async def my_message_hide(mid: str, user: dict = Depends(require_admin)):
    if user.get("role") == "superadmin":
        return {"ok": True, "preview": True}
    m = await db.org_messages.find_one({"id": mid}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="Messaggio non trovato")
    if m.get("require_ack"):
        ex = await db.org_message_reads.find_one({"message_id": mid, "user_id": user["user_id"]}, {"_id": 0})
        if not (ex and ex.get("ack_at")):
            raise HTTPException(status_code=400, detail="Questo messaggio richiede la conferma di lettura")
    return await _msg_mark(user, mid, hidden=True)


@api.post("/my/messages/{mid}/ack")
async def my_message_ack(mid: str, user: dict = Depends(require_admin)):
    if user.get("role") == "superadmin":
        return {"ok": True, "preview": True}
    return await _msg_mark(user, mid, ack=True, hidden=True)


# ---------------- platform audit log (extensible) ----------------
# Append-only trail of privileged Super Admin actions. No API surface mutates/deletes it.
# NEVER store passwords, tokens, secrets or payment data here — only non-sensitive metadata.
AUDIT_ACTION_LABELS = {
    "permissions_changed": "Modifica permessi",
    "org_access": "Accesso organizzazione",
    "impersonation_started": "Avvio accesso come utente",
    "impersonation_ended": "Termine accesso come utente",
    "impersonation_expired": "Scadenza accesso come utente",
    "impersonation_action": "Operazione in modalità assistenza",
    "payments_status_refresh": "Aggiornamento stato pagamenti",
    "video_support_booked": "Prenotazione assistenza video",
    "video_support_cancelled": "Annullamento assistenza video",
    "video_support_rescheduled": "Riprogrammazione assistenza video",
    "video_support_config": "Disponibilità assistenza video",
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
    "person_invite_sent": "Invito area personale",
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
    "news_edited": "Novità modificata",
    "news_published": "Novità approvata e pubblicata",
    "news_withdrawn": "Novità ritirata",
    "news_deleted": "Novità eliminata",
    "news_simulated": "Simulazione rilascio (test)",
    "brevo_org_lists_toggle": "Liste Brevo per organizzazione",
    "brevo_org_lists_sync": "Sincronizzazione liste Brevo organizzazione",
}


async def record_audit(actor: dict, action: str, org_id: Optional[str] = None,
                        org_name: Optional[str] = None, meta: Optional[dict] = None,
                        target_email: Optional[str] = None, target_name: Optional[str] = None,
                        detail: Optional[str] = None) -> dict:
    doc = {"id": new_id(), "created_at": now_iso(),
           "actor_user_id": actor.get("user_id"), "actor_email": actor.get("email"),
           "actor_name": actor.get("name"), "actor_role": actor.get("role"),
           "scope": "platform_admin" if actor.get("role") == "superadmin" else "org",
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

def _resolve_stripe_mode() -> str:
    """Modalità Stripe in ordine di priorità: CRMEVENT_STRIPE_MODE (custom key,
    modificabile dall'utente perché non intercettata dall'integrazione nativa) →
    STRIPE_MODE → default 'test'. Valori ammessi: 'test' | 'live'."""
    for _name in ("CRMEVENT_STRIPE_MODE", "STRIPE_MODE"):
        _v = (os.environ.get(_name) or "").strip().strip('"').strip("'").lower()
        if _v:
            return _v
    return "test"


STRIPE_MODE = _resolve_stripe_mode()


def _stripe_env(test_name: str, live_name: str) -> str:
    """TEST → legge il secret generico gestito dall'integrazione Stripe di Emergent
    (comportamento IDENTICO a oggi). LIVE → legge ESCLUSIVAMENTE il secret custom
    CRMEVENT_STRIPE_*_LIVE (non intercettato dall'integrazione Stripe), senza alcun fallback su TEST."""
    if STRIPE_MODE == "live":
        return (os.environ.get(live_name) or "").strip()
    return (os.environ.get(test_name) or "").strip()


STRIPE_SECRET_KEY = _stripe_env("STRIPE_SECRET_KEY", "CRMEVENT_STRIPE_SECRET_KEY_LIVE")
STRIPE_PUBLISHABLE_KEY = _stripe_env("STRIPE_PUBLISHABLE_KEY", "CRMEVENT_STRIPE_PUBLISHABLE_KEY_LIVE")
STRIPE_WEBHOOK_SECRET = _stripe_env("STRIPE_WEBHOOK_SECRET", "CRMEVENT_STRIPE_WEBHOOK_SECRET_LIVE")
STRIPE_ACCOUNT_ID = _stripe_env("STRIPE_ACCOUNT_ID", "CRMEVENT_STRIPE_ACCOUNT_ID_LIVE")
STRIPE_TAX_RATE_ID = _stripe_env("STRIPE_TAX_RATE_ID", "CRMEVENT_STRIPE_TAX_RATE_ID_LIVE")


def _validate_stripe_config():
    """Coerenza modalità↔chiavi. Nessun fallback LIVE→TEST. Ritorna (ok, errori)."""
    errs = []
    if STRIPE_MODE not in ("test", "live"):
        return False, [f"STRIPE_MODE non valido: '{STRIPE_MODE}' (ammessi: test | live)"]
    sk, pk = STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY
    if STRIPE_MODE == "live":
        if not (sk.startswith("sk_live_") or sk.startswith("rk_live_")):
            errs.append("STRIPE_MODE=live ma manca CRMEVENT_STRIPE_SECRET_KEY_LIVE (sk_live_... o rk_live_...)")
        if pk and not pk.startswith("pk_live_"):
            errs.append("CRMEVENT_STRIPE_PUBLISHABLE_KEY_LIVE non è una chiave live (pk_live_...)")
        if not STRIPE_WEBHOOK_SECRET.startswith("whsec_"):
            errs.append("CRMEVENT_STRIPE_WEBHOOK_SECRET_LIVE mancante")
    else:
        if sk.startswith("sk_live_") or sk.startswith("rk_live_"):
            errs.append("STRIPE_MODE=test ma la secret key è LIVE. Configurazione incoerente.")
        if pk.startswith("pk_live_"):
            errs.append("STRIPE_MODE=test ma la publishable key è LIVE. Configurazione incoerente.")
    return (len(errs) == 0), errs


STRIPE_CONFIG_OK, STRIPE_CONFIG_ERRORS = _validate_stripe_config()
# In TEST senza chiave esplicita si usa il placeholder gestito da Emergent (solo test).
stripe_sdk.api_key = STRIPE_SECRET_KEY or ("sk_test_emergent" if STRIPE_MODE == "test" else "")
if not STRIPE_CONFIG_OK:
    logger.error("Configurazione Stripe NON coerente (mode=%s): %s", STRIPE_MODE, "; ".join(STRIPE_CONFIG_ERRORS))
else:
    logger.info("Stripe inizializzato in modalità %s", STRIPE_MODE.upper())


def _assert_stripe_ready():
    if not STRIPE_CONFIG_OK:
        raise HTTPException(status_code=503, detail="Configurazione Stripe non valida o incoerente. Contatta l'amministratore.")
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


def _billing_missing(b: dict) -> list:
    """Dati minimi per la fatturazione (regole standard italiane / fattura elettronica).
    Privato: nome, cognome, codice fiscale (IT), indirizzo. Azienda/professionista IT:
    ragione sociale, P.IVA, indirizzo e Codice Destinatario SDI oppure PEC. Estero: SDI/PEC non richiesti."""
    b = b or {}
    tipo = (b.get("tipo") or "azienda").lower()
    paese = (b.get("paese") or "IT").upper()
    missing = []

    def need(field, label):
        if not (str(b.get(field) or "").strip()):
            missing.append(label)

    need("paese", "Paese")
    need("indirizzo", "Indirizzo")
    need("cap", "CAP")
    need("citta", "Città")
    if paese == "IT":
        need("provincia", "Provincia")
    if tipo == "privato":
        need("nome", "Nome")
        need("cognome", "Cognome")
        if paese == "IT":
            need("codice_fiscale", "Codice fiscale")
    else:
        need("ragione_sociale", "Ragione sociale")
        if paese == "IT":
            need("partita_iva", "Partita IVA")
            if not (str(b.get("codice_sdi") or "").strip()) and not (str(b.get("pec") or "").strip()):
                missing.append("Codice Destinatario (SDI) oppure PEC")
    return missing


@api.get("/account/billing")
async def get_billing(user: dict = Depends(require_admin)):
    org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0})
    return (org or {}).get("billing") or {}


@api.get("/account/billing/validate")
async def validate_billing(user: dict = Depends(require_admin)):
    org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0})
    missing = _billing_missing((org or {}).get("billing") or {})
    return {"valid": len(missing) == 0, "missing": missing}


@api.put("/account/billing")
async def put_billing(body: BillingDetails, user: dict = Depends(require_admin)):
    data = TN.normalize_fields("billing", body.model_dump())
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
    _assert_stripe_ready()
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


def _stripe_vat_cents(inv: dict) -> Optional[int]:
    """Robustly extract the VAT amount (in cents) from a Stripe Invoice object.
    The legacy top-level `tax` field is deprecated/removed in recent API versions;
    modern invoices expose per-rate amounts under `total_taxes`/`total_tax_amounts`."""
    tax = inv.get("tax")
    if tax is not None:
        return int(tax)
    arr = inv.get("total_taxes") or inv.get("total_tax_amounts") or []
    try:
        total = 0
        found = False
        for t in arr:
            amt = t.get("amount") if isinstance(t, dict) else None
            if amt is not None:
                total += int(amt)
                found = True
        return total if found else None
    except Exception:
        return None


async def _record_invoice(inv: dict, payment_status: str):
    o = await db.organizations.find_one({"subscription.stripe_customer_id": inv.get("customer")}, {"_id": 0})
    if not o:
        return
    created = inv.get("created")
    subtotal = round((inv.get("subtotal") or 0) / 100.0, 2)
    totale = round((inv.get("total") or 0) / 100.0, 2)
    vat_cents = _stripe_vat_cents(inv)
    # Prefer Stripe's own tax amount; fall back to (total - subtotal) so imponibile+IVA==totale.
    iva = round(vat_cents / 100.0, 2) if vat_cents is not None else round(totale - subtotal, 2)
    if iva < 0:
        iva = 0.0
    aliquota_iva = round(iva / subtotal * 100.0) if subtotal > 0 else 0.0
    billing = o.get("billing") or {}
    dati_fiscali_cliente = {
        "ragione_sociale": billing.get("ragione_sociale") or (f"{billing.get('nome','')} {billing.get('cognome','')}".strip() or o.get("nome")),
        "partita_iva": billing.get("partita_iva"), "codice_fiscale": billing.get("codice_fiscale"),
        "codice_sdi": billing.get("codice_sdi"), "pec": billing.get("pec"),
        "paese": (billing.get("paese") or "IT").upper(),
    }
    riferimento_stripe = {"stripe_invoice_id": inv.get("id"), "payment_intent": inv.get("payment_intent"),
                          "numero_stripe": inv.get("number"), "customer": inv.get("customer")}
    doc = {"org_id": o["id"], "stripe_invoice_id": inv.get("id"), "stripe_payment_intent": inv.get("payment_intent"),
           "numero_stripe": inv.get("number"),
           "data": datetime.fromtimestamp(created, timezone.utc).isoformat() if created else now_iso(),
           "imponibile": subtotal, "aliquota_iva": float(aliquota_iva), "importo_iva": iva, "iva": iva,
           "totale": totale, "valuta": (inv.get("currency") or "eur"),
           "dati_fiscali_cliente": dati_fiscali_cliente, "riferimento_stripe": riferimento_stripe,
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
    if t == "charge.refunded":
        await PARTNER["on_refund"](obj)
        return {"received": True}
    if await SAAS["handle_webhook"](t, obj) or await MKT["handle_webhook"](t, obj):
        return {"received": True}
    if t == "customer.subscription.deleted":
        await db.organizations.update_one({"subscription.stripe_subscription_id": obj["id"]},
                                          {"$set": {"subscription.status": "canceled", "updated_at": now_iso()}})
    elif t in ("customer.subscription.created", "customer.subscription.updated"):
        await _sync_subscription(obj)
    elif t == "checkout.session.completed":
        md = obj.get("metadata") or {}
        if md.get("kind") == "credit_purchase":
            await _activate_credit_purchase_from_session(obj)
        elif md.get("kind") in ("event_purchase", "event_upgrade"):
            await _activate_event_from_session(obj)
        elif obj.get("subscription"):
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
    return await db.invoices.find(oq(user, is_test={"$ne": True}), {"_id": 0}).sort("data", -1).to_list(500)


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


ORG_TYPE_LABEL = {"cliente": "Cliente", "test": "Test", "interna": "Interna", "internal": "Interna"}


def _is_test_purchase(p: dict) -> bool:
    return bool(p.get("is_test")) or str(p.get("stripe_session_id") or "").startswith("TEST")


@api.get("/platform/payments")
async def platform_payments(admin: dict = Depends(require_superadmin)):
    """Pagamenti e Crediti: dati dalle fonti attuali (crediti, acquisti, fatture), separati dal tipo di organizzazione."""
    orgs = await db.organizations.find({}, {"_id": 0, "id": 1, "nome": 1, "type": 1, "subscription.status": 1, "credits": 1}).to_list(5000)
    out = []
    for o in orgs:
        purchases = await db.credit_purchases.find({"org_id": o["id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
        paid = [p for p in purchases if p.get("status") == "paid"]
        last = (paid or purchases or [None])[0]
        inv = None
        if last and last.get("invoice_id"):
            inv = await db.invoices.find_one({"id": last["invoice_id"]}, {"_id": 0})
        if not inv:
            inv = await db.invoices.find_one({"org_id": o["id"]}, {"_id": 0}, sort=[("data", -1)])
        otype = o.get("type") or "cliente"
        tipo = ORG_TYPE_LABEL.get(otype, otype.capitalize())
        if otype == "cliente" and not paid and (o.get("subscription") or {}).get("status", "trial") == "trial":
            tipo = "Trial"
        sc = (last or {}).get("stripe_check") or {}
        out.append({
            "id": o["id"], "nome": o.get("nome"), "tipo": tipo, "balance": (o.get("credits") or {}).get("balance", 0),
            "purchases_paid": len(paid),
            "last_purchase": None if not last else {
                "date": last.get("paid_at") or last.get("created_at"), "amount_gross": last.get("amount_gross"),
                "credits_total": last.get("credits_total"), "status": last.get("status"), "is_test": _is_test_purchase(last),
                "stripe_payment_status": sc.get("payment_status"), "stripe_session_status": sc.get("session_status"),
                "stripe_pi_status": sc.get("pi_status"), "stripe_checked_at": sc.get("checked_at"), "stripe_error": sc.get("error")},
            "invoice": None if not inv else {
                "id": inv.get("id"), "numero": inv.get("fic_numero"), "data": inv.get("fic_data") or inv.get("data"),
                "totale": inv.get("totale"), "is_test": bool(inv.get("is_test")),
                "stato_documento": inv.get("fic_stato_documento"), "stato_sdi": inv.get("fic_stato_sdi"),
                "ei_status": inv.get("fic_ei_status"), "fic_checked_at": inv.get("fic_checked_at"), "fic_error": inv.get("fic_error")},
        })
    out.sort(key=lambda r: (r["nome"] or "").strip().lower())
    return out


FIC_EI_TO_SDI = {"not_sent": "non_inviato", "attempt": "in_invio", "pending": "in_invio", "processing": "in_consegna",
                 "sent": "inviato", "delivered": "consegnato", "accepted": "accettato", "manual_accepted": "accettato",
                 "rejected": "rifiutato", "manual_rejected": "rifiutato", "discarded": "scartato", "not_delivered": "non_consegnato",
                 "no_response": "decorrenza_termini", "error": "errore", "missing": "mancante"}


async def _refresh_org_payment_status(org_id: str) -> dict:
    """SOLA LETTURA su Stripe/FIC: aggiorna solo i campi di stato. Mai accrediti, pagamenti o fatture."""
    res = {"stripe_checked": 0, "fic_checked": 0, "errors": []}
    for p in await db.credit_purchases.find({"org_id": org_id}, {"_id": 0}).sort("created_at", -1).to_list(20):
        if _is_test_purchase(p) or not p.get("stripe_session_id"):
            continue
        chk = {"checked_at": now_iso()}
        try:
            s = stripe_sdk.checkout.Session.retrieve(p["stripe_session_id"])
            chk.update({"session_status": s.get("status"), "payment_status": s.get("payment_status"), "amount_total": s.get("amount_total")})
            if s.get("payment_intent"):
                chk["pi_status"] = stripe_sdk.PaymentIntent.retrieve(s["payment_intent"]).get("status")
        except Exception as e:  # noqa: BLE001
            chk["error"] = f"{type(e).__name__}"[:120]
            res["errors"].append(f"Stripe {p['stripe_session_id'][:14]}…: {chk['error']}")
        await db.credit_purchases.update_one({"stripe_session_id": p["stripe_session_id"]}, {"$set": {"stripe_check": chk}})
        res["stripe_checked"] += 1
    invs = await db.invoices.find({"org_id": org_id, "fic_document_id": {"$ne": None}, "is_test": {"$ne": True}}, {"_id": 0}).to_list(50)
    if invs and fic_configured() and await db.fic_settings.find_one({"provider": "fic"}):
        try:
            token, cid = await _fic_token(), await _fic_company_id()
        except Exception as e:  # noqa: BLE001
            res["errors"].append(f"Fatture in Cloud: {type(e).__name__}")
            return res
        async with httpx.AsyncClient(timeout=30) as c:
            for inv in invs:
                upd = {"fic_checked_at": now_iso()}
                try:
                    r = await c.get(f"{FIC_BASE}/c/{cid}/issued_documents/{inv['fic_document_id']}", params={"fieldset": "detailed"},
                                    headers={"Authorization": f"Bearer {token}"})
                    if r.status_code >= 400:
                        raise RuntimeError(f"HTTP {r.status_code}")
                    d = r.json().get("data", {})
                    ei = d.get("ei_status")
                    upd.update({"fic_ei_status": ei, "fic_numero": d.get("number") or inv.get("fic_numero"),
                                "fic_data": d.get("date") or inv.get("fic_data"), "fic_stato_documento": "emessa"})
                    if ei:
                        upd["fic_stato_sdi"] = FIC_EI_TO_SDI.get(ei, ei)
                except Exception as e:  # noqa: BLE001
                    upd["fic_check_error"] = str(e)[:200]
                    res["errors"].append(f"FIC documento {inv['fic_document_id']}: {str(e)[:80]}")
                await db.invoices.update_one({"id": inv["id"]}, {"$set": upd})
                res["fic_checked"] += 1
    return res


class PaymentsRefreshIn(BaseModel):
    org_id: Optional[str] = None


@api.post("/platform/payments/refresh")
async def platform_payments_refresh(body: PaymentsRefreshIn, admin: dict = Depends(require_superadmin)):
    ids = [body.org_id] if body.org_id else await db.organizations.distinct("id")
    tot = {"orgs": len(ids), "stripe_checked": 0, "fic_checked": 0, "errors": []}
    for oid in ids:
        r = await _refresh_org_payment_status(oid)
        tot["stripe_checked"] += r["stripe_checked"]
        tot["fic_checked"] += r["fic_checked"]
        tot["errors"] += r["errors"]
    await record_audit(admin, "payments_status_refresh", org_id=body.org_id,
                       meta={k: v for k, v in tot.items() if k != "errors"} | {"errors": len(tot["errors"])})
    return tot


# ---------------- fatture in cloud (e-invoicing) ----------------
FIC_BASE = "https://api-v2.fattureincloud.it"
FIC_CLIENT_ID = os.environ.get("FIC_CLIENT_ID", "")
FIC_CLIENT_SECRET = os.environ.get("FIC_CLIENT_SECRET", "")
FIC_REDIRECT_URI = os.environ.get("FIC_REDIRECT_URI", "")
FIC_COMPANY_ID = os.environ.get("FIC_COMPANY_ID", "")
FIC_SCOPES = "issued_documents.invoices:r issued_documents.invoices:a settings:r"
# Modalità Fatture in Cloud: 'test' = dry-run (nessun documento reale, nessun SDI); 'live' = emissione reale.
FIC_MODE = (os.environ.get("FIC_MODE") or "test").strip().strip('"').strip("'").lower()
FIC_PAYMENT_ACCOUNT_ID = (os.environ.get("FIC_PAYMENT_ACCOUNT_ID") or "").strip()
FIC_PAYMENT_METHOD_NAME = (os.environ.get("FIC_PAYMENT_METHOD_NAME") or "Carta di credito (Stripe)").strip()
# Codice FatturaPA ModalitaPagamento per ei_data.payment_method (obbligatorio se e_invoice): MP08 = carta di pagamento.
FIC_EI_PAYMENT_METHOD = (os.environ.get("FIC_EI_PAYMENT_METHOD") or "MP08").strip()


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


# Campi fiscali FIC API v2 (IssuedDocument / IssuedDocumentItemsListItem) per forzare
# documento SENZA rivalsa INPS, cassa previdenziale e ritenute (altrimenti FIC applica i default aziendali).
FIC_NO_WITHHOLDING_DOC = {"rivalsa": 0, "cassa": 0, "cassa2": 0, "withholding_tax": 0,
                          "withholding_tax_taxable": 0, "other_withholding_tax": 0, "use_gross_prices": False}
FIC_NO_WITHHOLDING_ITEM = {"apply_withholding_taxes": False}


def _invoice_line_name(inv: dict, org: dict) -> str:
    """Descrizione riga fattura: ricariche crediti vs abbonamento (coerente FIC reale/simulazione)."""
    if inv.get("descrizione"):
        return inv["descrizione"]
    if inv.get("kind") == "credit_recharge":
        return f"Ricarica {inv.get('credits_total')} crediti CRMEvent"
    return f"Abbonamento CRMEvent ({org.get('nome')})"


SAAS_WEBHOOK_EVENTS = ("customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted",
                       "invoice.paid", "invoice.payment_failed")
FIC_FORFETTARIO_NOTE = ("Operazione effettuata ai sensi dell'art. 1, commi da 54 a 89, della Legge n. 190/2014 – Regime forfettario. "
                        "Operazione senza applicazione dell'IVA.")
FIC_SAAS_NUMERATION = (os.environ.get("FIC_SAAS_NUMERATION") or "").strip()


async def _fic_vat_forfettario(company_id: str, token: str) -> Optional[int]:
    """Aliquota FIC 0% con natura N2.2 (forfettario). Override: FIC_VAT_ID_FORFETTARIO."""
    override = (os.environ.get("FIC_VAT_ID_FORFETTARIO") or "").strip()
    if override.isdigit():
        return int(override)
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(f"{FIC_BASE}/c/{company_id}/settings/vat_types", headers={"Authorization": f"Bearer {token}"})
    for v in (r.json().get("data") or []):
        if abs(float(v.get("value") or 0)) < 0.01 and str(v.get("ei_type") or "").upper() == "N2.2":
            return v["id"]
    return None


async def _emit_saas_invoice(inv_id: str):
    """Fattura reale abbonamento (FIC LIVE): forfettario N2.2, sezionale dedicato, invio SDI. Idempotente con tentativi."""
    inv = await db.invoices.find_one({"id": inv_id, "kind": {"$in": ["saas_subscription", "marketplace"]}}, {"_id": 0})
    if not inv or inv.get("is_test") or inv.get("payment_status") != "paid" or FIC_MODE != "live" or inv.get("fic_auto") is False:
        return
    if inv.get("fic_stato_sdi") == "inviato":
        return
    lock = await db.invoices.update_one({"id": inv_id, "fic_lock": {"$ne": True}}, {"$set": {"fic_lock": True}})
    if not lock.modified_count:
        return
    base = {"fic_attempts": int(inv.get("fic_attempts") or 0) + 1, "fic_last_attempt_at": now_iso(), "fic_mode": FIC_MODE, "updated_at": now_iso()}
    try:
        if not fic_configured() or not await db.fic_settings.find_one({"provider": "fic"}):
            raise RuntimeError("Fatture in Cloud non connesso (OAuth mancante)")
        token, cid = await _fic_token(), await _fic_company_id()
        doc_id = inv.get("fic_document_id")
        if not doc_id:
            org = await db.organizations.find_one({"id": inv["org_id"]}, {"_id": 0})
            vat_id = await _fic_vat_forfettario(cid, token)
            if vat_id is None:
                raise RuntimeError("Aliquota 0% natura N2.2 non trovata su Fatture in Cloud (imposta FIC_VAT_ID_FORFETTARIO)")
            tot = float(inv.get("totale") or 0)
            today = datetime.now(timezone.utc).date().isoformat()
            pay = {"amount": tot, "due_date": today, "paid_date": today, "status": "paid"}
            if FIC_PAYMENT_ACCOUNT_ID.isdigit():
                pay["payment_account"] = {"id": int(FIC_PAYMENT_ACCOUNT_ID)}
            data = {"type": "invoice", "e_invoice": True, "entity": _fic_entity(org or {}),
                    "items_list": [{"name": _invoice_line_name(inv, org or {}), "qty": 1, "net_price": tot, "vat": {"id": vat_id}, **FIC_NO_WITHHOLDING_ITEM}],
                    "currency": {"id": "EUR"}, "language": {"code": "it"}, "notes": FIC_FORFETTARIO_NOTE,
                    "ei_data": {"payment_method": FIC_EI_PAYMENT_METHOD}, "payment_method": {"name": FIC_PAYMENT_METHOD_NAME},
                    "payments_list": [pay], **FIC_NO_WITHHOLDING_DOC}
            if FIC_SAAS_NUMERATION:
                data["numeration"] = FIC_SAAS_NUMERATION
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.post(f"{FIC_BASE}/c/{cid}/issued_documents", headers={"Authorization": f"Bearer {token}"}, json={"data": data})
            if r.status_code >= 400:
                raise RuntimeError(f"creazione documento: {r.text[:300]}")
            d = r.json().get("data", {})
            doc_id = d.get("id")
            await db.invoices.update_one({"id": inv_id}, {"$set": {"fic_document_id": doc_id, "fic_numero": d.get("number"),
                                                                  "fic_data": d.get("date"), "fic_pdf_url": d.get("url"), "fic_stato_documento": "emessa"}})
        async with httpx.AsyncClient(timeout=30) as c:
            sr = await c.post(f"{FIC_BASE}/c/{cid}/issued_documents/{doc_id}/e_invoice/send",
                              headers={"Authorization": f"Bearer {token}"}, json={"data": {}})
        if sr.status_code >= 400:
            raise RuntimeError(f"invio SDI: {sr.text[:300]}")
        await db.invoices.update_one({"id": inv_id}, {"$set": {**base, "fic_stato_sdi": "inviato", "fic_error": None}})
    except Exception as e:  # noqa: BLE001
        logger.error(f"FIC abbonamento {inv_id}: {e}")
        await db.invoices.update_one({"id": inv_id}, {"$set": {**base, "fic_stato_documento": "errore_emissione" if not inv.get("fic_document_id") else "emessa",
                                                              "fic_error": str(e)[:500]}})
    finally:
        await db.invoices.update_one({"id": inv_id}, {"$set": {"fic_lock": False}})


async def _retry_saas_invoices() -> int:
    rows = await db.invoices.find({"kind": "saas_subscription", "is_test": {"$ne": True}, "payment_status": "paid",
                                   "fic_stato_sdi": {"$ne": "inviato"}, "fic_attempts": {"$not": {"$gte": 6}}}, {"_id": 0, "id": 1}).to_list(200)
    for r in rows:
        await _emit_saas_invoice(r["id"])
    return len(rows)


async def _fic_issue_document(inv: dict, dry_run: bool = True) -> dict:
    """Create an issued invoice in FIC from a CRMEvent invoice record (TEST: no real SDI transmission)."""
    if inv.get("is_test"):
        raise HTTPException(status_code=400, detail="Transazione TEST: emissione reale su Fatture in Cloud non consentita. Usa 'Simula fattura (TEST)'.")
    org = await db.organizations.find_one({"id": inv["org_id"]}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=404, detail="Organizzazione non trovata")
    token = await _fic_token()
    cid = await _fic_company_id()
    if not cid:
        raise HTTPException(status_code=400, detail="company_id FIC mancante")
    vat_id = await _fic_vat_id(cid, token)
    a = _derive_amounts(inv)
    net = a["imponibile"] if a["imponibile"] is not None else 0
    line = {"name": _invoice_line_name(inv, org), "qty": 1, "net_price": net, **FIC_NO_WITHHOLDING_ITEM}
    if vat_id is not None:
        line["vat"] = {"id": vat_id}
    else:
        line["vat"] = {"value": a["aliquota_iva"]}
    body = {"data": {"type": "invoice", "e_invoice": True, "entity": _fic_entity(org),
                     "items_list": [line], "currency": {"id": "EUR"}, "language": {"code": "it"},
                     "ei_data": {"payment_method": FIC_EI_PAYMENT_METHOD},
                     **FIC_NO_WITHHOLDING_DOC}}
    # Metodo di pagamento (solo emissione reale): pagamento già incassato via Stripe/carta.
    # L'account di pagamento FIC NON viene hardcodato: usato solo se FIC_PAYMENT_ACCOUNT_ID è configurato.
    if not dry_run:
        today = datetime.now(timezone.utc).date().isoformat()
        pay = {"amount": a.get("totale") or net, "due_date": today, "paid_date": today, "status": "paid"}
        if FIC_PAYMENT_ACCOUNT_ID.isdigit():
            pay["payment_account"] = {"id": int(FIC_PAYMENT_ACCOUNT_ID)}
        body["data"]["payment_method"] = {"name": FIC_PAYMENT_METHOD_NAME}
        body["data"]["payments_list"] = [pay]
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


def _derive_amounts(inv: dict) -> dict:
    """Robustly derive & reconcile fiscal amounts from a CRMEvent invoice record.
    Guarantees imponibile + importo_iva == totale (rounded to cents) and a coherent VAT rate.
    Never trusts a bare stored VAT of 0 when net/total imply otherwise."""
    def f2(x):
        return round(float(x), 2) if x is not None else None

    imponibile = f2(inv.get("imponibile"))
    totale = f2(inv.get("totale"))
    iva = f2(inv.get("importo_iva"))
    if iva is None:
        iva = f2(inv.get("iva"))
    aliquota = inv.get("aliquota_iva")

    # Reconcile using whichever pair is present, preferring explicit net + total.
    if imponibile is not None and totale is not None:
        expected = round(totale - imponibile, 2)
        if iva is None or abs((imponibile + iva) - totale) > 0.01:
            iva = expected
    elif imponibile is not None and iva is not None:
        totale = round(imponibile + iva, 2)
    elif totale is not None and iva is not None:
        imponibile = round(totale - iva, 2)
    elif imponibile is not None:
        rate = float(aliquota) if aliquota else 22.0
        iva = round(imponibile * rate / 100.0, 2)
        totale = round(imponibile + iva, 2)

    if imponibile is not None and imponibile > 0 and iva is not None:
        aliquota = round(iva / imponibile * 100.0)
    elif aliquota is None:
        aliquota = 22.0

    coerente = (imponibile is not None and iva is not None and totale is not None
                and abs((imponibile + iva) - totale) <= 0.01)
    return {"imponibile": imponibile, "aliquota_iva": float(aliquota), "importo_iva": iva,
            "totale": totale, "valuta": (inv.get("valuta") or "eur"), "coerente": coerente}


# ---- FIC SIMULATION (TEST): builds the payload internally, makes NO FIC call, NO SDI. ----
def _fic_build_payload(org: dict, amounts: dict, line_name: Optional[str] = None) -> dict:
    """Build the exact FIC issued_document payload that WOULD be sent — without sending it.
    Uses the reconciled net price and REAL VAT rate; contains only the org's own billing data.
    Include anche metodo di pagamento e incasso (pagato via Stripe) così l'anteprima è completa."""
    net = amounts["imponibile"] if amounts["imponibile"] is not None else 0
    line = {"name": line_name or f"Abbonamento CRMEvent ({org.get('nome')})", "qty": 1,
            "net_price": net, "vat": {"value": amounts["aliquota_iva"]}, **FIC_NO_WITHHOLDING_ITEM}
    today = datetime.now(timezone.utc).date().isoformat()
    pay = {"amount": amounts.get("totale") or net, "due_date": today, "paid_date": today, "status": "paid"}
    if FIC_PAYMENT_ACCOUNT_ID.isdigit():
        pay["payment_account"] = {"id": int(FIC_PAYMENT_ACCOUNT_ID)}
    return {"data": {"type": "invoice", "e_invoice": True, "entity": _fic_entity(org),
                     "items_list": [line], "currency": {"id": (amounts.get("valuta") or "eur").upper()},
                     "language": {"code": "it"}, **FIC_NO_WITHHOLDING_DOC,
                     "ei_data": {"payment_method": FIC_EI_PAYMENT_METHOD},
                     "payment_method": {"name": FIC_PAYMENT_METHOD_NAME},
                     "payments_list": [pay]}}


async def _fic_simulate(inv: dict) -> dict:
    org = await db.organizations.find_one({"id": inv["org_id"]}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=404, detail="Organizzazione non trovata")
    a = _derive_amounts(inv)
    payload = _fic_build_payload(org, a, _invoice_line_name(inv, org))
    numero = f"SIM/{datetime.now(timezone.utc).year}/{str(inv.get('id', ''))[:6].upper()}"
    data_doc = datetime.now(timezone.utc).date().isoformat()
    # Piano / ciclo di fatturazione (coerente con il tipo di pagamento Stripe).
    if inv.get("kind") == "credit_recharge":
        ciclo, piano_label = "una_tantum", f"Ricarica crediti CRMEvent ({inv.get('credits_total')} crediti · una tantum)"
    else:
        ciclo = (org.get("subscription") or {}).get("billing_cycle")
        piano_label = {"monthly": "Abbonamento CRMEvent · Mensile", "yearly": "Abbonamento CRMEvent · Annuale"}.get(ciclo, "Abbonamento CRMEvent")
    # Persist the reconciled fiscal fields so the stored test invoice is repaired in place.
    upd = {"fic_document_id": None, "fic_numero": numero, "fic_data": data_doc,
           "fic_stato_documento": "simulato_test", "fic_stato_sdi": "simulato_test",
           "fic_simulated": True, "fic_payload_preview": payload,
           "imponibile": a["imponibile"], "aliquota_iva": a["aliquota_iva"],
           "importo_iva": a["importo_iva"], "iva": a["importo_iva"],
           "totale": a["totale"], "valuta": a["valuta"], "updated_at": now_iso()}
    await db.invoices.update_one({"id": inv["id"]}, {"$set": upd})
    logger.info("FIC SIMULATION (TEST — no FIC call, no SDI) inv=%s numero=%s entity=%s imponibile=%s iva=%s(%s%%) totale=%s coerente=%s",
                inv.get("id"), numero, payload["data"]["entity"].get("name"),
                a["imponibile"], a["importo_iva"], a["aliquota_iva"], a["totale"], a["coerente"])
    return {"simulated": True, "mode": "SIMULAZIONE_TEST",
            "cliente": payload["data"]["entity"],
            "intestazione": payload["data"]["entity"].get("name"),
            "numero_simulato": numero, "data_simulata": data_doc,
            "imponibile": a["imponibile"], "aliquota_iva": a["aliquota_iva"],
            "importo_iva": a["importo_iva"], "iva": a["importo_iva"],
            "totale": a["totale"], "valuta": a["valuta"], "coerente": a["coerente"],
            "piano": inv.get("piano") or (org.get("subscription") or {}).get("plan"),
            "piano_label": piano_label, "ciclo_fatturazione": ciclo,
            "modalita_pagamento": FIC_PAYMENT_METHOD_NAME,
            "descrizione": inv.get("descrizione") or _invoice_line_name(inv, org),
            "riferimento_stripe": inv.get("riferimento_stripe") or {
                "stripe_invoice_id": inv.get("stripe_invoice_id"),
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


# ---------------- MARKETING · SOCIAL AI ----------------
SOCIAL_STATUSES = ["draft", "pending_approval", "approved", "scheduled", "published", "error"]
SOCIAL_STATUS_LABELS = {
    "draft": "Bozza", "pending_approval": "Da approvare", "approved": "Approvato",
    "scheduled": "Programmato", "published": "Pubblicato", "error": "Errore",
}
SOCIAL_PLATFORMS = ["instagram", "facebook", "linkedin"]  # extensible; only instagram wired in phase 1


class SocialSettingsIn(BaseModel):
    brand_name: Optional[str] = None
    description: Optional[str] = None
    website: Optional[str] = None
    target: Optional[str] = None
    tone_of_voice: Optional[str] = None
    main_goal: Optional[str] = None
    default_cta: Optional[str] = None
    frequency: Optional[str] = None
    preferred_days: Optional[List[str]] = None
    preferred_times: Optional[List[str]] = None
    logo_url: Optional[str] = None
    brand_colors: Optional[List[str]] = None
    main_hashtags: Optional[List[str]] = None
    avoid_info: Optional[str] = None
    ai_instructions: Optional[str] = None


class SocialPostIn(BaseModel):
    platform: Optional[str] = "instagram"
    category: Optional[str] = None
    topic: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None
    caption: Optional[str] = None
    cta: Optional[str] = None
    hashtags: Optional[List[str]] = None
    image_suggestion: Optional[str] = None
    image_brief: Optional[str] = None
    account_id: Optional[str] = None
    media_id: Optional[str] = None
    format: Optional[str] = "1:1"
    scheduled_at: Optional[str] = None
    event_id: Optional[str] = None


class SocialGenerateIn(BaseModel):
    topic: Optional[str] = None
    category: Optional[str] = None
    event_id: Optional[str] = None
    platform: Optional[str] = "instagram"
    extra_instructions: Optional[str] = None


class SocialPlanIn(BaseModel):
    date_from: str
    date_to: str
    posts_per_week: int = 3
    goal: Optional[str] = None
    event_id: Optional[str] = None
    platform: Optional[str] = "instagram"


class SocialScheduleIn(BaseModel):
    scheduled_at: str


class SocialMediaUpdateIn(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    event_id: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None


class SocialAccountIn(BaseModel):
    platform: str = "instagram"
    handle: Optional[str] = None


DEFAULT_SOCIAL_SETTINGS = {
    "brand_name": None, "description": None, "website": None, "target": None,
    "tone_of_voice": None, "main_goal": None, "default_cta": None, "frequency": None,
    "preferred_days": [], "preferred_times": [], "logo_url": None, "brand_colors": [],
    "main_hashtags": [], "avoid_info": None, "ai_instructions": None,
    "autopilot": "OFF",  # phase 1: always OFF
}


async def _get_social_settings(org_id: str) -> dict:
    s = await db.social_settings.find_one({"org_id": org_id}, {"_id": 0})
    if not s:
        s = {**DEFAULT_SOCIAL_SETTINGS, "id": new_id(), "org_id": org_id,
             "created_at": now_iso(), "updated_at": now_iso()}
        await db.social_settings.insert_one(dict(s))
        s.pop("_id", None)
    s["autopilot"] = "OFF"  # enforced OFF in phase 1
    return s


async def _social_log(user: dict, action: str, post_id: Optional[str] = None,
                       detail: Optional[str] = None, platform: Optional[str] = None,
                       error: Optional[str] = None):
    await db.social_publish_logs.insert_one({
        "id": new_id(), "org_id": user["org_id"], "post_id": post_id, "action": action,
        "actor_user_id": user.get("user_id"), "actor_email": user.get("email"),
        "actor_name": user.get("name"), "platform": platform, "detail": detail,
        "error": error, "created_at": now_iso()})


async def _event_public_context(event_id: str, org_id: str) -> Optional[dict]:
    """Return ONLY publishable event data for the AI — never personal/private data
    (no emails, phones, staff names, internal notes)."""
    ev = await db.events.find_one({"id": event_id, "org_id": org_id}, {"_id": 0})
    if not ev:
        return None
    ctx = {k: ev.get(k) for k in ["nome", "edizione", "tipologia", "data_inizio", "data_fine",
                                   "localita", "citta", "descrizione", "sito_web"] if ev.get(k)}
    maps = await db.event_maps.find({"org_id": org_id, "evento_id": event_id}, {"_id": 0}).to_list(200)
    percorsi = [m.get("nome") for m in maps if m.get("nome")]
    if percorsi:
        ctx["percorsi"] = percorsi
    deals = await db.deals.find({"org_id": org_id, "evento_id": event_id, "fase": "confermato"}, {"_id": 0}).to_list(500)
    sponsor_names = []
    for d in deals:
        c = await db.companies.find_one({"id": d.get("azienda_id"), "org_id": org_id}, {"_id": 0, "nome": 1})
        if c and c.get("nome"):
            sponsor_names.append(c["nome"])
    if sponsor_names:
        ctx["sponsor"] = sponsor_names
    di = ev.get("data_inizio")
    if di:
        try:
            d0 = datetime.fromisoformat(di[:10]).date()
            ctx["giorni_all_evento"] = (d0 - datetime.now(timezone.utc).date()).days
        except Exception:
            pass
    return ctx


def _plan_dates(date_from: str, date_to: str, posts_per_week: int, times: Optional[list]) -> list:
    """Evenly distribute publish datetimes across the period."""
    try:
        d0 = datetime.fromisoformat(date_from[:10]).date()
        d1 = datetime.fromisoformat(date_to[:10]).date()
    except Exception:
        raise HTTPException(status_code=400, detail="Date del piano non valide")
    if d1 < d0:
        raise HTTPException(status_code=400, detail="La data finale precede quella iniziale")
    span_days = (d1 - d0).days + 1
    weeks = max(1, (span_days + 6) // 7)
    total = max(1, min(posts_per_week, 14)) * weeks
    total = min(total, 40)
    hhmm = (times or ["10:00"])[0] if times else "10:00"
    try:
        hh, mm = [int(x) for x in hhmm.split(":")[:2]]
    except Exception:
        hh, mm = 10, 0
    out = []
    for i in range(total):
        offset = round(i * (span_days - 1) / max(1, total - 1)) if total > 1 else 0
        day = d0 + timedelta(days=offset)
        out.append(datetime(day.year, day.month, day.day, hh, mm, tzinfo=timezone.utc).isoformat())
    return out


def _sanitize_post(user: dict, body: SocialPostIn) -> dict:
    data = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    plat = data.get("platform")
    if plat and plat not in SOCIAL_PLATFORMS:
        raise HTTPException(status_code=400, detail="Canale social non supportato")
    return data


# ---- Settings ----
@api.get("/social/settings")
async def social_settings_get(user: dict = Depends(require_admin)):
    return await _get_social_settings(user["org_id"])


@api.put("/social/settings")
async def social_settings_put(body: SocialSettingsIn, user: dict = Depends(require_org_admin)):
    await _get_social_settings(user["org_id"])
    clean = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    clean["updated_at"] = now_iso()
    clean["autopilot"] = "OFF"
    await db.social_settings.update_one({"org_id": user["org_id"]}, {"$set": clean})
    await _social_log(user, "settings_updated")
    return await _get_social_settings(user["org_id"])


# ---- Dashboard ----
@api.get("/social/dashboard")
async def social_dashboard(user: dict = Depends(require_admin)):
    posts = await db.social_posts.find(oq(user), {"_id": 0}).to_list(5000)
    counts = {s: 0 for s in SOCIAL_STATUSES}
    for p in posts:
        counts[p.get("status", "draft")] = counts.get(p.get("status", "draft"), 0) + 1
    now = now_iso()
    upcoming = sorted([p for p in posts if p.get("status") in ("scheduled", "approved")
                       and (p.get("scheduled_at") or "") >= now],
                      key=lambda x: x.get("scheduled_at") or "")[:8]
    settings = await _get_social_settings(user["org_id"])
    accounts = await db.social_accounts.find(oq(user), {"_id": 0}).to_list(50)
    return {"counts": counts, "total": len(posts), "upcoming": upcoming,
            "autopilot": "OFF", "brand_name": settings.get("brand_name"),
            "accounts": [_san_account(a) for a in accounts]}


# ---- Posts CRUD ----
@api.get("/social/posts")
async def social_posts_list(status: Optional[str] = None, platform: Optional[str] = None,
                            event_id: Optional[str] = None, user: dict = Depends(require_admin)):
    q = oq(user)
    if status:
        q["status"] = status
    if platform:
        q["platform"] = platform
    if event_id:
        q["event_id"] = event_id
    return await db.social_posts.find(q, {"_id": 0}).sort("created_at", -1).to_list(5000)


@api.get("/social/posts/{post_id}")
async def social_post_get(post_id: str, user: dict = Depends(require_admin)):
    doc = await db.social_posts.find_one(oq(user, id=post_id), {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Contenuto non trovato")
    return doc


@api.post("/social/posts")
async def social_post_create(body: SocialPostIn, user: dict = Depends(require_admin)):
    if body.event_id:
        await _assert_event_operational(user["org_id"], body.event_id)
    data = _sanitize_post(user, body)
    data.update({"org_id": user["org_id"], "status": "draft", "platform": data.get("platform") or "instagram",
                 "source": "manual", "created_by": user.get("user_id"),
                 "created_by_name": user.get("name")})
    doc = await _create("social_posts", data)
    await _social_log(user, "created", post_id=doc["id"], platform=doc.get("platform"))
    return doc


@api.put("/social/posts/{post_id}")
async def social_post_update(post_id: str, body: SocialPostIn, user: dict = Depends(require_admin)):
    clean = _sanitize_post(user, body)
    clean["updated_at"] = now_iso()
    res = await db.social_posts.update_one(oq(user, id=post_id), {"$set": clean})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Contenuto non trovato")
    await _social_log(user, "edited", post_id=post_id)
    return await db.social_posts.find_one(oq(user, id=post_id), {"_id": 0})


@api.delete("/social/posts/{post_id}")
async def social_post_delete(post_id: str, user: dict = Depends(require_admin)):
    await db.social_posts.delete_one(oq(user, id=post_id))
    await _social_log(user, "deleted", post_id=post_id)
    return {"ok": True}


async def _connected_ig_accounts(user: dict) -> list:
    """Instagram accounts in the CURRENT scope that are actually publishable."""
    rows = await db.social_accounts.find(oq(user, platform="instagram"), {"_id": 0}).to_list(50)
    return [a for a in rows if a.get("connected") and a.get("access_token") and a.get("ig_user_id")]


async def _default_account_id(user: dict) -> Optional[str]:
    """Sole connected Instagram account id (for auto-assign to new posts), else None."""
    accts = await _connected_ig_accounts(user)
    return accts[0]["id"] if len(accts) == 1 else None


async def _resolve_post_account(user: dict, post: dict):
    """Return (account_or_None, connected_accounts). Auto-assigns the sole connected
    account to the post when exactly one exists and the post has none yet.
    Account and post are both scoped to user['org_id'] via oq()."""
    accts = await _connected_ig_accounts(user)
    chosen = None
    if post.get("account_id"):
        chosen = next((a for a in accts if a["id"] == post["account_id"]), None)
    if not chosen and len(accts) == 1:
        chosen = accts[0]
        if post.get("account_id") != chosen["id"]:
            await db.social_posts.update_one(oq(user, id=post["id"]),
                                             {"$set": {"account_id": chosen["id"], "updated_at": now_iso()}})
            post["account_id"] = chosen["id"]
    return chosen, accts


@api.post("/social/posts/{post_id}/approve")
async def social_post_approve(post_id: str, user: dict = Depends(require_org_admin)):
    post = await db.social_posts.find_one(oq(user, id=post_id), {"_id": 0})
    if not post:
        raise HTTPException(status_code=404, detail="Contenuto non trovato")
    missing = []
    if not post.get("creative_media_id"):
        missing.append("creatività immagine (caricala nella sezione Creatività)")
    if not (post.get("caption") or "").strip():
        missing.append("caption")
    if post.get("format") not in ("1:1", "4:5"):
        missing.append("formato feed valido (1:1 o 4:5)")
    chosen, accts = await _resolve_post_account(user, post)
    if not accts:
        missing.append("account Instagram collegato (collega @crmevent nelle Impostazioni)")
    elif len(accts) > 1 and not chosen:
        missing.append("account di pubblicazione selezionato")
    if missing:
        raise HTTPException(status_code=400, detail="Impossibile approvare · da completare: " + ", ".join(missing))
    await db.social_posts.update_one(oq(user, id=post_id), {"$set": {
        "status": "approved", "approved_by": user.get("user_id"),
        "approved_by_name": user.get("name"), "approved_at": now_iso(), "updated_at": now_iso()}})
    await _social_log(user, "approved", post_id=post_id)
    return await db.social_posts.find_one(oq(user, id=post_id), {"_id": 0})


@api.post("/social/posts/{post_id}/schedule")
async def social_post_schedule(post_id: str, body: SocialScheduleIn, user: dict = Depends(require_org_admin)):
    res = await db.social_posts.update_one(oq(user, id=post_id), {"$set": {
        "status": "scheduled", "scheduled_at": body.scheduled_at,
        "scheduled_by": user.get("user_id"), "scheduled_by_name": user.get("name"),
        "updated_at": now_iso()}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Contenuto non trovato")
    await _social_log(user, "scheduled", post_id=post_id, detail=body.scheduled_at)
    return await db.social_posts.find_one(oq(user, id=post_id), {"_id": 0})


# ---- Instagram publishing (Phase E): single feed image + caption. Autopilot stays OFF. ----
class SocialPublishIn(BaseModel):
    confirm: bool = False


async def _ensure_public_jpeg(org_id: str, media: dict):
    """Create a publicly reachable JPEG copy of the creative for Meta to fetch."""
    f = await db.files.find_one({"id": media.get("file_id"), "org_id": org_id}, {"_id": 0})
    if not f:
        raise HTTPException(status_code=400, detail="File creatività non trovato")
    data, _ct = await _read_file_rec(f)
    jpeg = social_creative.to_jpeg(data)
    token = new_id() + new_id()
    path = f"social/{org_id}/pub_{token}.jpg"
    res = await asyncio.to_thread(storage_utils.save, path, jpeg, "image/jpeg")
    await db.ig_public_media.insert_one({"token": token, "org_id": org_id, "storage_path": res["path"],
                                         "storage_backend": res.get("backend"),
                                         "created_at": now_iso()})
    return f"{instagram_utils.BACKEND_PUBLIC_URL}/api/social/public/creative/{token}"


@api.get("/social/public/creative/{token}")
async def social_public_creative(token: str):
    """Public (unauthenticated) JPEG endpoint so Meta can fetch the image at publish time."""
    rec = await db.ig_public_media.find_one({"token": token}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Not found")
    data, _ct = await _read_file_rec(rec)
    return Response(content=data, media_type="image/jpeg")


@api.post("/social/posts/{post_id}/publish")
async def social_post_publish(post_id: str, body: SocialPublishIn, user: dict = Depends(require_org_admin)):
    post = await db.social_posts.find_one(oq(user, id=post_id), {"_id": 0})
    if not post:
        raise HTTPException(status_code=404, detail="Contenuto non trovato")
    # Duplicate guard: never publish the same post twice.
    if post.get("status") == "published" or post.get("published_media_id"):
        raise HTTPException(status_code=409, detail="Questo contenuto è già stato pubblicato")
    acct, accts = await _resolve_post_account(user, post)
    problems = []
    if len(accts) > 1 and not acct:
        problems.append("account di pubblicazione selezionato")
    elif not acct or not acct.get("connected") or not acct.get("access_token") or not acct.get("ig_user_id"):
        problems.append("account Instagram collegato e token valido")
    else:
        exp = acct.get("token_expires_at")
        try:
            if exp and datetime.fromisoformat(exp) <= datetime.now(timezone.utc):
                problems.append("token valido (scaduto: aggiorna il token)")
        except Exception:
            pass
    if post.get("status") not in ("approved", "scheduled", "error"):
        problems.append("post approvato")
    if not post.get("creative_media_id"):
        problems.append("creatività presente")
    if post.get("format") not in ("1:1", "4:5"):
        problems.append("formato compatibile con il feed (1:1 o 4:5)")
    if not (post.get("caption") or "").strip():
        problems.append("caption presente")
    if problems:
        raise HTTPException(status_code=400, detail="Impossibile pubblicare · da completare: " + ", ".join(problems))
    if not body.confirm:
        raise HTTPException(status_code=428, detail="Conferma esplicita richiesta per pubblicare ora")
    # Atomic lock to prevent accidental double publish.
    prev_status = post.get("status")
    lock = await db.social_posts.update_one(
        {"id": post_id, "org_id": user["org_id"], "status": {"$in": ["approved", "scheduled", "error"]},
         "published_media_id": {"$in": [None, ""]}},
        {"$set": {"status": "publishing", "updated_at": now_iso()}})
    if lock.matched_count == 0:
        raise HTTPException(status_code=409, detail="Pubblicazione già in corso o completata")
    media = await db.social_media.find_one({"org_id": user["org_id"], "id": post["creative_media_id"]}, {"_id": 0})
    if not media:
        await db.social_posts.update_one({"id": post_id, "org_id": user["org_id"]}, {"$set": {"status": prev_status}})
        raise HTTPException(status_code=400, detail="Creatività non trovata")
    image_url = await _ensure_public_jpeg(user["org_id"], media)
    if not image_url.startswith("https://"):
        await db.social_posts.update_one({"id": post_id, "org_id": user["org_id"]}, {"$set": {"status": prev_status}})
        raise HTTPException(status_code=400, detail="URL immagine non HTTPS: BACKEND_PUBLIC_URL non configurato correttamente")
    caption = (post.get("caption") or "").strip()
    hashtags = post.get("hashtags") or []
    if hashtags:
        caption = caption + "\n\n" + " ".join(hashtags)
    await _social_log(user, "publish_requested", post_id=post_id, platform="instagram",
                      detail=f"acct=@{acct.get('username')} img={image_url}")
    async def _iglog(kind, detail):
        await _social_log(user, kind, post_id=post_id, platform="instagram", detail=detail)
    try:
        res = await instagram_utils.create_and_publish(
            acct["ig_user_id"], image_url, caption, acct["access_token"], log=_iglog)
        media_id = res["media_id"]
    except Exception as e:
        await db.social_posts.update_one({"id": post_id, "org_id": user["org_id"]},
                                         {"$set": {"status": "error", "last_publish_error": str(e)[:300],
                                                   "updated_at": now_iso()}})
        await _social_log(user, "publish_failed", post_id=post_id, platform="instagram", error=str(e)[:300])
        # A Meta validation rejection (Graph 4xx) is a client-side error, NOT an origin/gateway
        # failure: surface it as 422 with the Graph detail so it is not misclassified as a 502.
        if isinstance(e, instagram_utils.GraphAPIError) and getattr(e, "is_client_error", False):
            raise HTTPException(status_code=422, detail=f"Instagram ha rifiutato la pubblicazione: {str(e)[:200]}")
        raise HTTPException(status_code=502, detail=f"Pubblicazione Instagram fallita: {str(e)[:200]}")
    await db.social_posts.update_one({"id": post_id, "org_id": user["org_id"]}, {"$set": {
        "status": "published", "published_media_id": media_id, "published_at": now_iso(),
        "published_by": user.get("user_id"), "published_by_name": user.get("name"), "updated_at": now_iso()}})
    await _social_log(user, "publish_success", post_id=post_id, platform="instagram",
                      detail=f"media_id={media_id} acct=@{acct.get('username')}")
    return await db.social_posts.find_one(oq(user, id=post_id), {"_id": 0})


# ============ Lead Finder / Organizzatori (Super Admin, platform scope) ============
LF_STATES = ["da_verificare", "verificato", "interessante", "contattato",
             "demo_richiesta", "trial", "cliente", "non_interessato", "non_contattare"]


def _lf_domain(url):
    if not url:
        return None
    d = re.sub(r"^https?://", "", str(url).strip().lower()).split("/")[0].replace("www.", "")
    return d or None


def _lf_key(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _lf_norm_org(o: dict) -> dict:
    """Recompute derived dedup fields."""
    emails = [e.lower() for e in (o.get("emails") or []) if e]
    if o.get("email"):
        e = o["email"].lower()
        if e not in emails:
            emails.insert(0, e)
    o["emails"] = emails
    o["email"] = emails[0] if emails else None
    o["web_domain"] = _lf_domain(o.get("website"))
    o["name_key"] = _lf_key(o.get("name"))
    return o


async def _lf_find_dup(user, name=None, email=None, website=None, instagram_url=None, exclude_id=None):
    ors = []
    if email:
        ors.append({"emails": email.lower()})
    if website and _lf_domain(website):
        ors.append({"web_domain": _lf_domain(website)})
    if instagram_url:
        ors.append({"instagram_url": instagram_url})
    if name:
        ors.append({"name_key": _lf_key(name)})
    if not ors:
        return None
    q = {**oq(user), "$or": ors}
    if exclude_id:
        q["id"] = {"$ne": exclude_id}
    return await db.lf_organizers.find_one(q, {"_id": 0})


async def _lf_events_for(user, org_id):
    return await db.lf_events.find(oq(user, organizer_id=org_id), {"_id": 0}).sort("date", 1).to_list(200)


async def _lf_enrich(user, o):
    evs = await _lf_events_for(user, o["id"])
    o["events"] = evs
    o["events_count"] = len(evs)
    o["sports"] = sorted({e.get("sport") for e in evs if e.get("sport")})
    return o


@api.get("/leadfinder/organizers")
async def lf_list_organizers(user: dict = Depends(require_org_admin)):
    rows = await db.lf_organizers.find(oq(user), {"_id": 0}).sort("name", 1).to_list(2000)
    for o in rows:
        await _lf_enrich(user, o)
    return rows


@api.post("/leadfinder/organizers")
async def lf_create_organizer(body: dict, user: dict = Depends(require_org_admin)):
    if not (body.get("name") or "").strip():
        raise HTTPException(status_code=400, detail="Nome organizzazione obbligatorio")
    dup = await _lf_find_dup(user, name=body.get("name"), email=body.get("email"),
                             website=body.get("website"), instagram_url=body.get("instagram_url"))
    if dup:
        raise HTTPException(status_code=409, detail=f"Possibile duplicato: '{dup.get('name')}' — usa Unisci duplicati o modifica quello esistente")
    o = _lf_norm_org({**body})
    o.setdefault("status", "da_verificare")
    o.setdefault("socials_status", "da_verificare")
    o.setdefault("source_main", body.get("source_main") or "manuale")
    o.setdefault("sources", body.get("sources") or {})
    o["acquired_at"] = body.get("acquired_at") or now_iso()
    doc = await _create("lf_organizers", o)
    return await _lf_enrich(user, doc)


# ---- Lead Finder: inserimento manuale / importazione email (solo Super Admin platform scope) ----
LF_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


def _norm_email(e):
    return (e or "").strip().lower()


def _valid_email(e):
    return bool(LF_EMAIL_RE.match(e or ""))


async def _lf_existing_emails(user):
    out = set()
    async for o in db.lf_organizers.find(oq(user), {"_id": 0, "emails": 1}):
        for e in (o.get("emails") or []):
            if e:
                out.add(e.lower())
    return out


def _extract_email_cells(filename, content):
    """Return raw email strings from an .xlsx/.xls/.csv file (email column, else first column)."""
    import io
    ext = (filename or "").lower().rsplit(".", 1)[-1]
    rows = []
    if ext in ("csv", "txt"):
        import csv
        text = None
        for enc in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                text = content.decode(enc)
                break
            except Exception:
                continue
        text = text or content.decode("utf-8", "ignore")
        sample = text[:2000]
        delim = ";" if sample.count(";") > sample.count(",") else ","
        for r in csv.reader(io.StringIO(text), delimiter=delim):
            rows.append([str(c) for c in r])
    elif ext == "xlsx":
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        for r in wb.active.iter_rows(values_only=True):
            rows.append([("" if c is None else str(c)) for c in r])
        wb.close()
    elif ext == "xls":
        import xlrd
        sh = xlrd.open_workbook(file_contents=content).sheet_by_index(0)
        for i in range(sh.nrows):
            rows.append([("" if c is None else str(c)) for c in sh.row_values(i)])
    else:
        raise HTTPException(status_code=400, detail="Formato non supportato. Usa .xlsx, .xls o .csv")
    if not rows:
        return []
    header = [(c or "").strip().lower() for c in rows[0]]
    col, start = 0, 0
    if "email" in header:
        col, start = header.index("email"), 1
    elif header and header[0] in ("email", "e-mail", "mail", "indirizzo email"):
        col, start = 0, 1
    elif header and not _valid_email(header[0]):
        start = 1  # first row looks like a (non-email) header -> skip it
    out = []
    for r in rows[start:]:
        if col < len(r):
            v = (r[col] or "").strip()
            if v:
                out.append(v)
    return out


def _categorize_emails(raw_list, existing):
    valid, invalid = [], []
    for e in raw_list:
        ne = _norm_email(e)
        (valid if _valid_email(ne) else invalid).append(ne if _valid_email(ne) else e)
    seen, unique, dup_in_file = set(), [], 0
    for e in valid:
        if e in seen:
            dup_in_file += 1
        else:
            seen.add(e)
            unique.append(e)
    already = [e for e in unique if e in existing]
    new = [e for e in unique if e not in existing]
    return {
        "total": len(raw_list), "valid": len(valid), "invalid": invalid[:200],
        "invalid_count": len(invalid), "dup_in_file": dup_in_file,
        "unique_valid": len(unique), "existing_count": len(already),
        "new": new, "new_count": len(new),
    }


def _lf_email_record(user, email, origin):
    return _lf_norm_org({
        "org_id": user["org_id"], "email": email, "name": None, "website": None,
        "status": "da_completare", "verify_status": "non_verificato",
        "source_main": origin, "origin": origin,
        "sources": {"email": {"source": origin, "url": None}},
        "acquired_at": now_iso(),
    })


@api.post("/leadfinder/organizers/manual")
async def lf_manual_add(body: dict, user: dict = Depends(require_org_admin)):
    email = _norm_email(body.get("email"))
    if not email or not _valid_email(email):
        raise HTTPException(status_code=400, detail="Email valida obbligatoria")
    dup = await db.lf_organizers.find_one({**oq(user), "emails": email}, {"_id": 0})
    if dup:
        return {"status": "exists", "organizer": await _lf_enrich(user, dup)}
    o = _lf_email_record(user, email, "Inserimento manuale")
    if (body.get("name") or "").strip():
        o["name"] = body["name"].strip()
    if (body.get("website") or "").strip():
        o["website"] = body["website"].strip()
    if (body.get("notes") or "").strip():
        o["notes"] = body["notes"].strip()
    o = _lf_norm_org(o)
    doc = await _create("lf_organizers", o)
    return {"status": "created", "organizer": await _lf_enrich(user, doc)}


@api.post("/leadfinder/organizers/import/preview")
async def lf_import_preview(file: UploadFile = File(...), user: dict = Depends(require_org_admin)):
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File troppo grande (max 5MB)")
    raw = _extract_email_cells(file.filename, content)
    if not raw:
        raise HTTPException(status_code=400, detail="Nessuna email trovata nel file (attesa una colonna 'email')")
    existing = await _lf_existing_emails(user)
    return _categorize_emails(raw, existing)


@api.post("/leadfinder/organizers/import/confirm")
async def lf_import_confirm(body: dict, user: dict = Depends(require_org_admin)):
    emails = body.get("emails") or []
    existing = await _lf_existing_emails(user)
    created, skipped, seen = 0, 0, set()
    for raw in emails:
        e = _norm_email(raw)
        if not _valid_email(e) or e in existing or e in seen:
            skipped += 1
            continue
        seen.add(e)
        await _create("lf_organizers", _lf_email_record(user, e, "Importazione manuale"))
        created += 1
    return {"created": created, "skipped": skipped}


@api.get("/leadfinder/organizers/{oid}")
async def lf_get_organizer(oid: str, user: dict = Depends(require_org_admin)):
    o = await db.lf_organizers.find_one(oq(user, id=oid), {"_id": 0})
    if not o:
        raise HTTPException(status_code=404, detail="Organizzatore non trovato")
    return await _lf_enrich(user, o)


@api.put("/leadfinder/organizers/{oid}")
async def lf_update_organizer(oid: str, body: dict, user: dict = Depends(require_org_admin)):
    o = await db.lf_organizers.find_one(oq(user, id=oid), {"_id": 0})
    if not o:
        raise HTTPException(status_code=404, detail="Organizzatore non trovato")
    upd = {**o, **{k: v for k, v in body.items() if k not in ("id", "org_id")}}
    # "Non contattare" is sticky: a non-manual/automatic caller cannot overwrite it.
    if o.get("status") == "non_contattare" and body.get("status") and body.get("status") != "non_contattare" and not body.get("_manual"):
        upd["status"] = "non_contattare"
    upd = _lf_norm_org(upd)
    upd["updated_at"] = now_iso()
    if body.get("_verified"):
        upd["last_verified_at"] = now_iso()
    upd.pop("_manual", None); upd.pop("_verified", None)
    await db.lf_organizers.update_one(oq(user, id=oid), {"$set": upd})
    return await _lf_enrich(user, await db.lf_organizers.find_one(oq(user, id=oid), {"_id": 0}))


@api.get("/leadfinder/organizers/{oid}/relations")
async def lf_organizer_relations(oid: str, user: dict = Depends(require_org_admin)):
    o = await db.lf_organizers.find_one(oq(user, id=oid), {"_id": 0})
    if not o:
        raise HTTPException(status_code=404, detail="Organizzatore non trovato")
    events_count = await db.lf_events.count_documents(oq(user, organizer_id=oid))
    brevo_synced = bool(o.get("brevo_contact_id")) or o.get("brevo_status") in ("sincronizzato", "gia_presente")
    return {"events_count": events_count, "brevo_status": o.get("brevo_status") or "non_approvato",
            "brevo_synced": brevo_synced, "name": o.get("name") or o.get("email")}


async def _lf_delete_one(user: dict, oid: str) -> bool:
    o = await db.lf_organizers.find_one(oq(user, id=oid), {"_id": 0})
    if not o:
        return False
    # Non-destructive on events: unlink instead of deleting them. Brevo contact is NEVER touched.
    await db.lf_events.update_many(oq(user, organizer_id=oid), {"$set": {"organizer_id": None}})
    await db.lf_organizers.delete_one(oq(user, id=oid))
    return True


@api.delete("/leadfinder/organizers/{oid}")
async def lf_delete_organizer(oid: str, user: dict = Depends(require_org_admin)):
    if not await _lf_delete_one(user, oid):
        raise HTTPException(status_code=404, detail="Organizzatore non trovato")
    return {"deleted": True, "id": oid}


@api.post("/leadfinder/organizers/delete-bulk")
async def lf_delete_organizers_bulk(body: dict, user: dict = Depends(require_org_admin)):
    ids = [x for x in (body.get("ids") or []) if x]
    deleted = 0
    for oid in ids:
        if await _lf_delete_one(user, oid):
            deleted += 1
    return {"deleted": deleted, "requested": len(ids)}


class ConvertLeadIn(BaseModel):
    force: Optional[bool] = False


@api.post("/leadfinder/organizers/{oid}/convert-to-lead")
async def lf_convert_to_lead(oid: str, body: ConvertLeadIn = ConvertLeadIn(),
                             user: dict = Depends(require_org_admin)):
    """Convert a Lead Finder prospect into a commercial Lead.
    Keeps a bidirectional link to the original organizer. Detects duplicates by email and,
    when found, offers to LINK instead of creating a copy. Does NOT enroll the Demo funnel
    nor mutate Brevo — the LF→Brevo sync and the Demo automation are left untouched."""
    o = await db.lf_organizers.find_one(oq(user, id=oid), {"_id": 0})
    if not o:
        raise HTTPException(status_code=404, detail="Organizzatore non trovato")
    email = ((o.get("emails") or [o.get("email")]) or [None])[0]
    email = (email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email mancante: completa l'anagrafica prima di convertire")
    name = o.get("name") or o.get("legal_name")
    if not name:
        raise HTTPException(status_code=400, detail="Completa il Nome organizzazione prima di convertire in Lead")
    existing = await db.leads.find_one({"email": email}, {"_id": 0})
    if existing and not body.force:
        return {"duplicate": True, "lead_id": existing["id"],
                "lead_name": f"{existing.get('nome', '')} {existing.get('cognome', '') or ''}".strip(),
                "message": "Questo contatto è già presente nei Lead"}
    if existing:
        await db.leads.update_one({"id": existing["id"]}, {"$set": {"lead_finder_organizer_id": oid, "updated_at": now_iso()}})
        await db.lf_organizers.update_one(oq(user, id=oid), {"$set": {"lead_id": existing["id"], "updated_at": now_iso()}})
        return {"linked": True, "lead_id": existing["id"]}
    doc = await _create("leads", {"nome": name, "cognome": None, "organizzazione": name, "email": email,
                                  "telefono": o.get("phone"), "source": "lead_finder", "origine": "lead_finder",
                                  "stato": "nuovo", "note": "", "lead_finder_organizer_id": oid})
    await db.lf_organizers.update_one(oq(user, id=oid), {"$set": {"lead_id": doc["id"], "updated_at": now_iso()}})
    return {"created": True, "lead_id": doc["id"]}



@api.post("/leadfinder/organizers/merge")
async def lf_merge_organizers(body: dict, user: dict = Depends(require_org_admin)):
    primary_id = body.get("primary_id")
    dup_ids = [d for d in (body.get("duplicate_ids") or []) if d and d != primary_id]
    primary = await db.lf_organizers.find_one(oq(user, id=primary_id), {"_id": 0})
    if not primary or not dup_ids:
        raise HTTPException(status_code=400, detail="Selezione non valida")
    merged = {**primary}
    for did in dup_ids:
        d = await db.lf_organizers.find_one(oq(user, id=did), {"_id": 0})
        if not d:
            continue
        for f in ("website", "email", "phone", "instagram_url", "linkedin_url", "facebook_url",
                  "legal_name", "org_type", "city", "province", "region", "country"):
            if not merged.get(f) and d.get(f):
                merged[f] = d[f]
        merged["emails"] = list({*(merged.get("emails") or []), *(d.get("emails") or [])})
        merged["sources"] = {**(d.get("sources") or {}), **(merged.get("sources") or {})}
        if d.get("status") == "non_contattare":
            merged["status"] = "non_contattare"
        await db.lf_events.update_many(oq(user, organizer_id=did), {"$set": {"organizer_id": primary_id}})
        await db.lf_organizers.delete_one(oq(user, id=did))
    merged = _lf_norm_org(merged); merged["updated_at"] = now_iso()
    await db.lf_organizers.update_one(oq(user, id=primary_id), {"$set": merged})
    return await _lf_enrich(user, await db.lf_organizers.find_one(oq(user, id=primary_id), {"_id": 0}))


@api.get("/leadfinder/events")
async def lf_list_events(user: dict = Depends(require_org_admin)):
    rows = await db.lf_events.find(oq(user), {"_id": 0}).sort("date", 1).to_list(3000)
    omap = {o["id"]: o.get("name") for o in await db.lf_organizers.find(oq(user), {"_id": 0, "id": 1, "name": 1}).to_list(2000)}
    for e in rows:
        e["organizer_name"] = omap.get(e.get("organizer_id"))
    return rows


@api.post("/leadfinder/events")
async def lf_create_event(body: dict, user: dict = Depends(require_org_admin)):
    if not (body.get("name") or "").strip():
        raise HTTPException(status_code=400, detail="Nome evento obbligatorio")
    if not body.get("organizer_id"):
        raise HTTPException(status_code=400, detail="organizer_id obbligatorio")
    doc = await _create("lf_events", {**body, "sources": body.get("sources") or {}})
    return doc


@api.put("/leadfinder/events/{eid}")
async def lf_update_event(eid: str, body: dict, user: dict = Depends(require_org_admin)):
    e = await db.lf_events.find_one(oq(user, id=eid), {"_id": 0})
    if not e:
        raise HTTPException(status_code=404, detail="Evento non trovato")
    upd = {**e, **{k: v for k, v in body.items() if k not in ("id", "org_id")}, "updated_at": now_iso()}
    await db.lf_events.update_one(oq(user, id=eid), {"$set": upd})
    return await db.lf_events.find_one(oq(user, id=eid), {"_id": 0})


@api.get("/leadfinder/dashboard")
async def lf_dashboard(user: dict = Depends(require_org_admin)):
    orgs = await db.lf_organizers.find(oq(user), {"_id": 0}).to_list(3000)
    events = await db.lf_events.find(oq(user), {"_id": 0}).to_list(5000)
    leads = await db.leads.find({}, {"_id": 0}).to_list(5000)
    leads_demo = sum(1 for l in leads if _lead_origine(l) == "demo_sito")
    leads_manual = sum(1 for l in leads if _lead_origine(l) == "manuale")
    leads_lf = sum(1 for l in leads if _lead_origine(l) == "lead_finder")
    brevo_synced = sum(1 for o in orgs if o.get("brevo_status") in ("sincronizzato", "gia_presente"))
    def dist(items, key):
        d = {}
        for it in items:
            k = it.get(key) or "—"
            d[k] = d.get(k, 0) + 1
        return dict(sorted(d.items(), key=lambda x: -x[1]))
    return {
        "organizers_total": len(orgs),
        "organizers_verified": sum(1 for o in orgs if o.get("status") == "verificato"),
        "organizers_to_verify": sum(1 for o in orgs if o.get("status") == "da_verificare"),
        "leads_total": len(leads),
        "leads_demo": leads_demo,
        "leads_manual": leads_manual,
        "leads_lead_finder": leads_lf,
        "brevo_synced": brevo_synced,
        "events_total": len(events),
        "with_email": sum(1 for o in orgs if o.get("emails")),
        "with_instagram": sum(1 for o in orgs if o.get("instagram_url")),
        "with_linkedin": sum(1 for o in orgs if o.get("linkedin_url")),
        "by_region": dist(orgs, "region"),
        "by_sport": dist(events, "sport"),
        "by_source": dist(orgs, "source_main"),
        "states": LF_STATES,
    }


@api.post("/leadfinder/brevo-export")
async def lf_brevo_export(body: dict = {}, user: dict = Depends(require_org_admin)):
    raise HTTPException(status_code=501, detail="Usa 'Approva per Brevo' + 'Sincronizza con Brevo' (lista CRMEvent – Prospect).")


# ==================== BREVO — sincronizzazione controllata Prospect ====================
BREVO_STATES = ("non_approvato", "approvato", "in_corso", "sincronizzato",
                "gia_presente", "disiscritto_bloccato", "errore")


async def _brevo_config(user):
    c = await db.brevo_config.find_one(oq(user), {"_id": 0}) or {}
    return c


async def _brevo_save_config(user, patch):
    patch = {**patch, "updated_at": now_iso()}
    await db.brevo_config.update_one(oq(user), {"$set": {**patch, "org_id": user["org_id"]}}, upsert=True)
    return await _brevo_config(user)


def _brevo_attrs_for(org):
    """Build the custom-attribute payload from a CRMEvent organizer (only non-empty values)."""
    ev = (org.get("events") or [{}])
    first = ev[0] if ev else {}
    m = {
        "ORGANIZZAZIONE": org.get("legal_name") or org.get("name"),
        "EVENTO": first.get("name"),
        "SPORT": first.get("sport"),
        "REGIONE": org.get("region"),
        "CITTA": org.get("city"),
        "SITO": org.get("website"),
        "INSTAGRAM": org.get("instagram_url"),
        "LINKEDIN": org.get("linkedin_url"),
        "FONTE": org.get("source_main"),
        "DATA_ACQUISIZIONE": (org.get("acquired_at") or "")[:10] or None,
        "STATO_LEAD": org.get("status"),
    }
    return {k: v for k, v in m.items() if v}


@api.get("/brevo/status")
async def brevo_status(user: dict = Depends(require_org_admin)):
    cfg = await _brevo_config(user)
    return {
        "configured": brevo_client.is_configured(),
        "connection": cfg.get("connection", "sconosciuto"),
        "list_id": cfg.get("list_id"),
        "list_name": cfg.get("list_name"),
        "last_test": cfg.get("last_test"),
        "attributes_available": cfg.get("attributes_available", []),
        "attributes_missing": cfg.get("attributes_missing", []),
        "senders": cfg.get("senders", []),
        "prospect_list_name": brevo_client.PROSPECT_LIST_NAME,
        "desired_attributes": brevo_client.DESIRED_ATTRS,
    }


@api.post("/brevo/test")
async def brevo_test(user: dict = Depends(require_org_admin)):
    if not brevo_client.is_configured():
        raise HTTPException(status_code=400, detail="BREVO_API_KEY non configurata sul backend")
    try:
        async with brevo_client.BrevoClient() as c:
            acct = await c.account()
            lists = await c.lists()
            attrs = await c.attributes()
            senders = await c.senders()
            templates = await c.get_templates()
    except brevo_client.BrevoError as e:
        await _brevo_save_config(user, {"connection": "errore", "last_test": {"at": now_iso(), "ok": False, "error": f"HTTP {e.status}"}})
        raise HTTPException(status_code=502, detail=f"Brevo: errore connessione (HTTP {e.status})")
    attr_names = {a.get("name") for a in attrs}
    available = [a for a in brevo_client.DESIRED_ATTRS if a in attr_names]
    missing = [a for a in brevo_client.DESIRED_ATTRS if a not in attr_names]
    prospect = next((x for x in lists if (x.get("name") or "").strip().lower() == brevo_client.PROSPECT_LIST_NAME.lower()), None)
    tpl = next((t for t in templates if (t.get("name") or "").strip().lower() == brevo_client.PROSPECT_TEMPLATE_NAME.lower()), None)
    sender_list = [{"name": s.get("name"), "email": s.get("email"), "active": s.get("active")} for s in senders]
    cfg_patch = {
        "connection": "ok",
        "last_test": {"at": now_iso(), "ok": True, "account_email": (acct or {}).get("email")},
        "attributes_available": available, "attributes_missing": missing,
        "senders": sender_list,
    }
    if prospect:
        cfg_patch["list_id"] = prospect.get("id")
        cfg_patch["list_name"] = prospect.get("name")
    await _brevo_save_config(user, cfg_patch)
    return {
        "connection": "ok",
        "account_email": (acct or {}).get("email"),
        "lists": [{"id": x.get("id"), "name": x.get("name"), "total_subscribers": x.get("totalSubscribers")} for x in lists],
        "prospect_list": {"id": prospect.get("id"), "name": prospect.get("name")} if prospect else None,
        "prospect_list_exists": bool(prospect),
        "prospect_template": {"id": tpl.get("id"), "name": tpl.get("name")} if tpl else None,
        "prospect_template_exists": bool(tpl),
        "attributes_available": available, "attributes_missing": missing,
        "senders": sender_list,
        "note_demo": "La lista/funnel Demo NON viene toccata: la sync usa solo la lista Prospect qui sopra.",
    }


@api.post("/brevo/create-list")
async def brevo_create_list(body: dict = {}, user: dict = Depends(require_org_admin)):
    if not brevo_client.is_configured():
        raise HTTPException(status_code=400, detail="BREVO_API_KEY non configurata")
    try:
        async with brevo_client.BrevoClient() as c:
            existing = next((x for x in await c.lists() if (x.get("name") or "").strip().lower() == brevo_client.PROSPECT_LIST_NAME.lower()), None)
            if existing:
                await _brevo_save_config(user, {"list_id": existing["id"], "list_name": existing["name"]})
                return {"created": False, "list_id": existing["id"], "list_name": existing["name"], "detail": "Lista già esistente: usata quella."}
            folder_id = body.get("folder_id")
            if not folder_id:
                folders = await c.folders()
                if not folders:
                    raise HTTPException(status_code=400, detail="Nessuna cartella Brevo trovata: crea una cartella nel pannello Brevo e riprova.")
                folder_id = folders[0]["id"]
            res = await c.create_list(brevo_client.PROSPECT_LIST_NAME, folder_id)
            lid = res.get("id")
            await _brevo_save_config(user, {"list_id": lid, "list_name": brevo_client.PROSPECT_LIST_NAME})
            return {"created": True, "list_id": lid, "list_name": brevo_client.PROSPECT_LIST_NAME}
    except brevo_client.BrevoError as e:
        raise HTTPException(status_code=502, detail=f"Brevo: impossibile creare la lista (HTTP {e.status})")


def _prospect_email_html(domain: str) -> str:
    domain = (domain or "").rstrip("/")
    cta = f"{domain}/demo?utm_source=brevo&utm_medium=email&utm_campaign=prospect&utm_content=email1"
    logo = f"{domain}/logo-crmevent.png"
    return f"""<!DOCTYPE html>
<html lang="it"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1.0"/><meta name="x-apple-disable-message-reformatting"/><title>CRMEvent</title></head>
<body style="margin:0;padding:0;background:#f4f6f6;font-family:Arial,Helvetica,sans-serif;color:#1f2937;">
<span style="display:none;font-size:1px;color:#f4f6f6;line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;">Staff, volontari, sponsor, turni e briefing in un unico posto.</span>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f6;padding:24px 0;"><tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:600px;max-width:600px;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb;">
<tr><td style="padding:28px 32px 8px 32px;"><img src="{logo}" alt="CRMEvent" height="34" style="height:34px;display:block;border:0;"/></td></tr>
<tr><td style="padding:12px 32px 0 32px;"><h1 style="margin:0 0 8px 0;font-size:24px;line-height:1.25;color:#111827;font-weight:700;">Organizzare un evento sportivo senza rincorrere Excel, chat e documenti</h1></td></tr>
<tr><td style="padding:8px 32px 0 32px;font-size:15px;line-height:1.6;color:#374151;">
<p style="margin:0 0 12px 0;">Organizzare un evento è già abbastanza complicato.</p>
<p style="margin:0 0 12px 0;">Staff e volontari su WhatsApp.<br/>Sponsor nelle email.<br/>Turni su Excel.<br/>Hotel e pasti su un altro file.<br/>Briefing e documenti sparsi nelle cartelle.</p>
<p style="margin:0 0 12px 0;">È proprio da questa situazione che nasce <strong>CRMEvent</strong>.</p>
<p style="margin:0 0 8px 0;">Un unico spazio pensato per chi organizza eventi sportivi, dove gestire:</p>
<p style="margin:0 0 16px 0;color:#088F8A;font-weight:600;">Eventi · Staff · Volontari · Team e turni · Sponsor e partner · Ospitalità · Attività · Documenti e briefing</p>
<p style="margin:0 0 20px 0;">L'obiettivo è semplice: avere le informazioni dell'evento organizzate e accessibili quando servono.</p>
<p style="margin:0 0 20px 0;font-weight:600;">Vuoi vedere come funziona?</p></td></tr>
<tr><td align="center" style="padding:4px 32px 8px 32px;"><a href="{cta}" style="display:inline-block;background:#088F8A;color:#ffffff;text-decoration:none;font-weight:700;font-size:16px;padding:14px 32px;border-radius:999px;">GUARDA LA DEMO</a></td></tr>
<tr><td align="center" style="padding:0 32px 20px 32px;font-size:13px;line-height:1.5;color:#6b7280;">Una panoramica concreta di CRMEvent e di come può aiutarti nell'organizzazione del prossimo evento.</td></tr>
<tr><td style="padding:0 32px 28px 32px;font-size:15px;color:#374151;"><p style="margin:0;">A presto,<br/><strong>CRMEvent</strong></p></td></tr>
<tr><td style="padding:18px 32px;background:#0f172a;color:#cbd5e1;font-size:12px;line-height:1.6;"><strong style="color:#ffffff;">CRMEvent</strong><br/><a href="{domain}" style="color:#0ABAB5;text-decoration:none;">{domain}</a><br/>Ricevi questa email come organizzatore di eventi sportivi. Se non desideri più ricevere le nostre comunicazioni puoi <a href="{{{{ unsubscribe }}}}" style="color:#0ABAB5;">disiscriverti qui</a>.<br/>{{{{ contact.EMAIL }}}}</td></tr>
</table></td></tr></table></body></html>"""


@api.post("/brevo/create-email-template")
async def brevo_create_template(body: dict = {}, user: dict = Depends(require_org_admin)):
    if not brevo_client.is_configured():
        raise HTTPException(status_code=400, detail="BREVO_API_KEY non configurata")
    domain = PUBLIC_SITE_URL
    if not domain:
        raise HTTPException(status_code=400, detail="Dominio pubblico (PUBLIC_SITE_URL) non configurato")
    html = _prospect_email_html(domain)
    subject = "Organizzare un evento sportivo senza rincorrere Excel, chat e documenti"
    try:
        async with brevo_client.BrevoClient() as c:
            templates = await c.get_templates()
            existing = next((t for t in templates if (t.get("name") or "").strip().lower() == brevo_client.PROSPECT_TEMPLATE_NAME.lower()), None)
            if existing:
                return {"created": False, "template_id": existing.get("id"), "name": existing.get("name"),
                        "detail": "Template già esistente in Brevo: non duplicato."}
            senders = await c.senders()
            verified = [s for s in senders if s.get("active")]
            pref = next((s for s in verified if "crmevent" in (s.get("email") or "").lower()), None) or (verified[0] if verified else None)
            if not pref:
                raise HTTPException(status_code=400, detail="Nessun mittente verificato in Brevo: verifica un mittente CRMEvent prima di creare il template (nessun mittente creato).")
            sender = {"name": body.get("sender_name") or "CRMEvent", "email": pref["email"]}
            res = await c.create_email_template(brevo_client.PROSPECT_TEMPLATE_NAME, subject, html, sender)
            return {"created": True, "template_id": res.get("id"), "name": brevo_client.PROSPECT_TEMPLATE_NAME,
                    "sender": sender, "subject": subject,
                    "preheader": "Staff, volontari, sponsor, turni e briefing in un unico posto.",
                    "cta_url": f"{domain}/demo?utm_source=brevo&utm_medium=email&utm_campaign=prospect&utm_content=email1",
                    "is_active": False}
    except brevo_client.BrevoError as e:
        raise HTTPException(status_code=502, detail=f"Brevo: impossibile creare il template (HTTP {e.status})")


@api.post("/leadfinder/organizers/approve-brevo")
async def lf_approve_brevo(body: dict, user: dict = Depends(require_org_admin)):
    ids = body.get("ids") or []
    approved, skipped = 0, 0
    for oid in ids:
        o = await db.lf_organizers.find_one(oq(user, id=oid), {"_id": 0})
        if not o:
            continue
        # Blocklisted/unsubscribed contacts keep priority and are never re-approved.
        if o.get("brevo_status") == "disiscritto_bloccato":
            skipped += 1
            continue
        await db.lf_organizers.update_one(oq(user, id=oid), {"$set": {"brevo_status": "approvato", "updated_at": now_iso()}})
        approved += 1
    return {"approved": approved, "skipped": skipped}


async def _brevo_sync_one(c, allowed_attrs, org, list_id, user):
    email = (org.get("email") or "").strip().lower()
    row = {"id": org["id"], "email": email}
    if not email:
        row.update(status="errore", error="email mancante")
        return row
    try:
        contact = await c.get_contact(email)
        if contact:
            cid = contact.get("id")
            blocked = bool(contact.get("emailBlacklisted"))
            unsub_here = list_id in (contact.get("listUnsubscribed") or [])
            if blocked or unsub_here:
                new_status, res = "disiscritto_bloccato", "skipped_blocked"
            elif list_id in (contact.get("listIds") or []):
                new_status, res = "gia_presente", "already_present"
            else:
                await c.add_existing_to_list(email, list_id)
                new_status, res = "sincronizzato", "added"
        else:
            attrs = {k: v for k, v in _brevo_attrs_for(org).items() if k in allowed_attrs}
            created = await c.create_contact(email, list_id, attrs)
            cid = (created or {}).get("id")
            new_status, res = "sincronizzato", "created_and_added"
        row.update(status=new_status, result=res, contact_id=cid)
    except brevo_client.BrevoError as e:
        row.update(status="errore", error=f"HTTP {e.status}", result="error")
    # persist on organizer + audit log
    upd = {"brevo_status": row["status"], "brevo_list_id": list_id, "updated_at": now_iso()}
    if row.get("contact_id"):
        upd["brevo_contact_id"] = row["contact_id"]
    if row["status"] in ("sincronizzato", "gia_presente"):
        upd["brevo_synced_at"] = now_iso()
        upd["brevo_error"] = None
    if row.get("error"):
        upd["brevo_error"] = row["error"]
    await db.lf_organizers.update_one(oq(user, id=org["id"]), {"$set": upd})
    await db.brevo_sync_log.insert_one({
        "id": new_id(), "org_id": user["org_id"], "organizer_id": org["id"], "email": email,
        "list_id": list_id, "contact_id": row.get("contact_id"), "result": row.get("result"),
        "status": row["status"], "error": row.get("error"),
        "by_user": user.get("user_id"), "at": now_iso(),
    })
    return row


@api.post("/leadfinder/organizers/sync-brevo")
async def lf_sync_brevo(body: dict, user: dict = Depends(require_org_admin)):
    if not brevo_client.is_configured():
        raise HTTPException(status_code=400, detail="BREVO_API_KEY non configurata")
    cfg = await _brevo_config(user)
    list_id = cfg.get("list_id")
    if not list_id:
        raise HTTPException(status_code=400, detail="Lista Prospect non configurata: esegui Test connessione e salva/crea la lista.")
    ids = body.get("ids") or []
    results, skipped = [], 0
    try:
        async with brevo_client.BrevoClient() as c:
            allowed = set(await _brevo_config_allowed_attrs(c))
            for oid in ids:
                o = await db.lf_organizers.find_one(oq(user, id=oid), {"_id": 0})
                if not o:
                    continue
                if o.get("brevo_status") != "approvato":
                    skipped += 1
                    continue
                await db.lf_organizers.update_one(oq(user, id=oid), {"$set": {"brevo_status": "in_corso"}})
                o = await _lf_enrich(user, o)
                results.append(await _brevo_sync_one(c, allowed, o, list_id, user))
    except brevo_client.BrevoError as e:
        raise HTTPException(status_code=502, detail=f"Brevo: errore (HTTP {e.status})")
    return {"synced": sum(1 for r in results if r["status"] in ("sincronizzato", "gia_presente")),
            "blocked": sum(1 for r in results if r["status"] == "disiscritto_bloccato"),
            "errors": sum(1 for r in results if r["status"] == "errore"),
            "skipped_not_approved": skipped, "results": results, "list_name": cfg.get("list_name")}


async def _brevo_config_allowed_attrs(c):
    attr_names = {a.get("name") for a in await c.attributes()}
    return [a for a in brevo_client.DESIRED_ATTRS if a in attr_names]


# ---- Lead Finder: scansione ENDU → sito ufficiale → organizzatore → contatti/social ----
def _lf_src(url, source=None):
    d = {"url": url}
    if source:
        d["source"] = source
    return d


async def _lf_scan_persist(org_id: str, ev: dict, r: dict) -> dict:
    """Persist one scan result onto the event + its organizer (fill-if-empty, never overwrite
    manually confirmed data). Returns a report row. Dedup by email→domain→name→social."""
    uq = {"org_id": org_id}
    site = r.get("site") or {}
    endu_ig = r.get("endu_instagram")
    endu_fb = r.get("endu_facebook")
    social_page = r.get("social_page")
    official = r.get("official_site")
    org_site = site.get("org_site")
    emails = [e["email"] for e in site.get("emails", [])]
    email_sources = {e["email"]: e["source"] for e in site.get("emails", [])}
    ssrc = site.get("sources", {})

    # ---- event enrichment ----
    ev_sources = {**(ev.get("sources") or {})}
    ev_sources["endu"] = _lf_src(ev.get("endu_url"))
    ev_set = {"updated_at": now_iso(), "last_scanned_at": now_iso()}
    if r.get("name") and not ev.get("name"):
        ev_set["name"] = r["name"]
    if r.get("date") and not ev.get("date"):
        ev_set["date"] = r["date"]
    if r.get("city") and not ev.get("city"):
        ev_set["city"] = r["city"]
    if official:
        ev_set["website"] = official
        ev_sources["event_site"] = _lf_src(official, "ENDU")
    ev_ig = endu_ig or (social_page if r.get("endu_social_kind") == "instagram" else None)
    ev_fb = endu_fb or (social_page if r.get("endu_social_kind") == "facebook" else None)
    if ev_ig:
        ev_set["instagram_url"] = ev_ig
        ev_sources["instagram"] = _lf_src(ev_ig, "ENDU")
    if ev_fb:
        ev_set["facebook_url"] = ev_fb
        ev_sources["facebook"] = _lf_src(ev_fb, "ENDU")
    if social_page and not ev_ig and not ev_fb:
        ev_sources["social_page"] = _lf_src(social_page, "ENDU")
    ev_set["sources"] = ev_sources
    await db.lf_events.update_one({**uq, "id": ev["id"]}, {"$set": ev_set})

    # ---- organizer resolution & dedup ----
    org = await db.lf_organizers.find_one({**uq, "id": ev.get("organizer_id")}, {"_id": 0})
    org_website = org_site or official
    org_domain = leadfinder_scraper._host(org_website) if org_website else None
    # organizer socials: prefer official site; fall back to ENDU event social (high reliability)
    org_ig = site.get("instagram") or ev_ig
    org_fb = site.get("facebook") or ev_fb
    org_li = site.get("linkedin")  # NEVER inferred: only if explicitly found on site/ENDU

    # search for a possible pre-existing DIFFERENT organizer matching the scraped identity
    dup_ors = []
    if emails:
        dup_ors.append({"emails": {"$in": [e.lower() for e in emails]}})
    if org_domain:
        dup_ors.append({"web_domain": org_domain})
    if org_ig:
        dup_ors.append({"instagram_url": org_ig})
    duplicate_of = None
    if dup_ors:
        match = await db.lf_organizers.find_one(
            {**uq, "$or": dup_ors, "id": {"$ne": ev.get("organizer_id")}}, {"_id": 0})
        if match:
            duplicate_of = {"id": match["id"], "name": match.get("name")}

    if org:
        oset = {"updated_at": now_iso(), "last_verified_at": now_iso(),
                "source_main": org.get("source_main") or "ENDU"}
        osrc = {**(org.get("sources") or {})}
        osrc["endu"] = _lf_src(ev.get("endu_url"))
        # fill-if-empty (preserves manually confirmed data)
        if site.get("org_name") and not org.get("legal_name"):
            oset["legal_name"] = site["org_name"]
            osrc["legal_name"] = _lf_src(org_website or official)
        if org_website and not org.get("website"):
            oset["website"] = org_website
            osrc["website"] = _lf_src(org_website)
        if org_site and org_site != official:
            osrc["organizer_site"] = _lf_src(org_site)
        if official:
            osrc["event_site"] = _lf_src(official, "ENDU")
        if site.get("phone") and not org.get("phone"):
            oset["phone"] = site["phone"]
            osrc["phone"] = _lf_src(ssrc.get("phone"))
        # emails: append new, keep existing (manual) first
        merged_emails = list(dict.fromkeys([*(org.get("emails") or []), *[e.lower() for e in emails]]))
        if merged_emails:
            oset["emails"] = merged_emails
            oset["email"] = org.get("email") or merged_emails[0]
            for e in emails:
                osrc[f"email:{e.lower()}"] = _lf_src(email_sources.get(e))
        if org_ig and not org.get("instagram_url"):
            oset["instagram_url"] = org_ig
            osrc["instagram"] = _lf_src(ssrc.get("instagram") or ev.get("endu_url"),
                                        "sito ufficiale" if site.get("instagram") else "ENDU")
        if org_fb and not org.get("facebook_url"):
            oset["facebook_url"] = org_fb
            osrc["facebook"] = _lf_src(ssrc.get("facebook") or ev.get("endu_url"),
                                       "sito ufficiale" if site.get("facebook") else "ENDU")
        if org_li and not org.get("linkedin_url"):
            oset["linkedin_url"] = org_li
            osrc["linkedin"] = _lf_src(ssrc.get("linkedin"), "sito ufficiale")
        if duplicate_of:
            oset["possibile_duplicato"] = duplicate_of
        if org.get("status") != "non_contattare":
            oset["status"] = org.get("status") if org.get("status") not in (None, "") else "da_verificare"
            oset.setdefault("status", "da_verificare")
        oset["sources"] = osrc
        oset["web_domain"] = org_domain or org.get("web_domain")
        oset = _lf_norm_org({**org, **oset})
        await db.lf_organizers.update_one({**uq, "id": org["id"]}, {"$set": oset})
        org = {**org, **oset}

    # ---- report row ----
    has_org = bool((org or {}).get("legal_name") or site.get("org_name"))
    has_email = bool(emails)
    has_social = bool(org_ig or org_fb)
    reasons = []
    if not official:
        reasons.append("sito ufficiale non presente su ENDU")
    elif site.get("error"):
        reasons.append("sito non raggiungibile")
    if official and not site.get("error"):
        if not has_email:
            reasons.append("email non trovata sul sito")
        if not has_social:
            reasons.append("nessun social ufficiale")
        if not site.get("org_name"):
            reasons.append("ragione sociale organizzatore non identificata")
    if has_org and has_email and has_social:
        stato = "Completo"
    elif official and (has_email or has_social or site.get("org_name")):
        stato = "Parziale"
    else:
        stato = "Da verificare"
    return {
        "event": ev.get("name"), "endu_url": ev.get("endu_url"),
        "endu_ok": bool(r.get("endu_ok")),
        "endu_name": r.get("name"), "endu_date": r.get("date"), "endu_city": r.get("city"),
        "organizer": (org or {}).get("name"),
        "organizer_legal": (org or {}).get("legal_name") or site.get("org_name"),
        "event_site": official, "org_site": org_site,
        "emails": emails, "instagram": org_ig, "facebook": org_fb, "linkedin": org_li,
        "endu_has_site": bool(official), "endu_has_social": bool(social_page),
        "site_visited": len(site.get("visited") or []),
        "duplicate_of": duplicate_of, "status": stato, "reason": ", ".join(reasons) or None,
    }


async def _lf_run_scan(scan_id: str, org_id: str, event_ids: Optional[list]):
    uq = {"org_id": org_id}
    # If the platform event DB is empty, auto-seed the controlled 20-event ENDU list (idempotent).
    seeded = 0
    if not event_ids and org_id == PLATFORM_ORG_ID:
        if await db.lf_events.count_documents(uq) == 0:
            try:
                await asyncio.to_thread(seed_leadfinder.run)
                seeded = await db.lf_events.count_documents(uq)
            except Exception as e:
                await db.lf_scans.update_one({"id": scan_id}, {"$set": {
                    "status": "empty", "total": 0, "done": 0,
                    "message": "Nessun evento acquisito — scansione da verificare",
                    "reason": f"seed eventi ENDU fallito: {str(e)[:160]}", "finished_at": now_iso()}})
                return
    q = {**uq}
    if event_ids:
        q["id"] = {"$in": event_ids}
    events = await db.lf_events.find(q, {"_id": 0}).to_list(500)
    if not events:
        await db.lf_scans.update_one({"id": scan_id}, {"$set": {
            "status": "empty", "total": 0, "done": 0,
            "message": "Nessun evento acquisito — scansione da verificare",
            "reason": "Nessun evento ENDU presente nel database della piattaforma.",
            "finished_at": now_iso()}})
        return
    session = leadfinder_scraper.requests.Session()
    rows = []
    await db.lf_scans.update_one({"id": scan_id}, {"$set": {"total": len(events), "seeded": seeded}})
    for i, ev in enumerate(events):
        try:
            r = await asyncio.to_thread(leadfinder_scraper.scan_event, ev.get("endu_url"), session)
            row = await _lf_scan_persist(org_id, ev, r)
        except Exception as e:
            row = {"event": ev.get("name"), "endu_url": ev.get("endu_url"),
                   "endu_ok": False, "status": "Errore", "reason": str(e)[:160]}
        rows.append(row)
        await db.lf_scans.update_one({"id": scan_id}, {"$set": {"done": i + 1, "rows": rows, "updated_at": now_iso()}})

    def cnt(pred):
        return sum(1 for x in rows if pred(x))
    endu_ok = cnt(lambda x: x.get("endu_ok"))
    stats = {
        "events_analyzed": len(rows),
        "endu_reachable": endu_ok,
        "endu_with_site": cnt(lambda x: x.get("endu_has_site")),
        "endu_with_social": cnt(lambda x: x.get("endu_has_social")),
        "sites_visited": cnt(lambda x: (x.get("site_visited") or 0) > 0),
        "organizers_identified": len({x.get("organizer_legal") for x in rows if x.get("organizer_legal")}),
        "emails_found": cnt(lambda x: x.get("emails")),
        "instagram_found": cnt(lambda x: x.get("instagram")),
        "facebook_found": cnt(lambda x: x.get("facebook")),
        "linkedin_found": cnt(lambda x: x.get("linkedin")),
        "duplicates_found": cnt(lambda x: x.get("duplicate_of")),
        "complete": cnt(lambda x: x.get("status") == "Completo"),
        "partial": cnt(lambda x: x.get("status") == "Parziale"),
        "to_verify": cnt(lambda x: x.get("status") == "Da verificare"),
        "errors": cnt(lambda x: x.get("status") == "Errore"),
    }
    # Honest final status: if NOT ONE ENDU page could be fetched, this is a failure, not a success.
    if endu_ok == 0:
        final = {"status": "empty", "message": "Nessun evento acquisito — scansione da verificare",
                 "reason": "Nessuna pagina ENDU raggiungibile (possibile blocco rete/anti-bot o struttura cambiata)."}
    else:
        final = {"status": "done"}
    await db.lf_scans.update_one({"id": scan_id}, {"$set": {
        **final, "rows": rows, "stats": stats, "seeded": seeded, "finished_at": now_iso()}})


@api.post("/leadfinder/scan-endu")
async def lf_scan_endu(body: dict = {}, user: dict = Depends(require_org_admin)):
    scan_id = new_id()
    await db.lf_scans.insert_one({
        "id": scan_id, "org_id": user["org_id"], "status": "running", "total": 0, "done": 0,
        "rows": [], "stats": {}, "created_by": user.get("user_id"),
        "created_at": now_iso(), "updated_at": now_iso()})
    asyncio.create_task(_lf_run_scan(scan_id, user["org_id"], body.get("event_ids")))
    return {"scan_id": scan_id, "status": "running"}


@api.get("/leadfinder/scan/{scan_id}")
async def lf_scan_status(scan_id: str, user: dict = Depends(require_org_admin)):
    s = await db.lf_scans.find_one(oq(user, id=scan_id), {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Scansione non trovata")
    return s


@api.get("/leadfinder/scans")
async def lf_scans_list(user: dict = Depends(require_org_admin)):
    return await db.lf_scans.find(oq(user), {"_id": 0, "rows": 0}).sort("created_at", -1).to_list(20)


@api.get("/leadfinder/diagnose")
async def lf_diagnose(url: Optional[str] = None, user: dict = Depends(require_org_admin)):
    """Single-event end-to-end diagnostic (read-only, no DB writes): HTTP status → ENDU data →
    official site → social → official reachable. Defaults to a known ENDU event if no url given."""
    test_url = (url or "").strip() or "https://www.endu.net/events/pisa-half-marathon"
    if "endu.net" not in test_url:
        raise HTTPException(status_code=400, detail="Fornisci un URL di una pagina evento ENDU (endu.net)")
    return await asyncio.to_thread(leadfinder_scraper.diagnose_event, test_url)


# ---- AI generation ----
async def _record_generation(user: dict, gen_type: str, payload: dict, result) -> str:
    gid = new_id()
    await db.social_ai_generations.insert_one({
        "id": gid, "org_id": user["org_id"], "type": gen_type, "model": social_ai.MODEL,
        "input": payload, "output": result, "created_by": user.get("user_id"),
        "created_by_name": user.get("name"), "created_at": now_iso()})
    return gid


@api.post("/social/generate")
async def social_generate(body: SocialGenerateIn, user: dict = Depends(require_admin)):
    if body.event_id:
        await _assert_event_operational(user["org_id"], body.event_id)
    settings = await _get_social_settings(user["org_id"])
    event_ctx = None
    if body.event_id:
        event_ctx = await _event_public_context(body.event_id, user["org_id"])
    gen = await social_ai.generate_post(settings, event_ctx, topic=body.topic,
                                        category=body.category, platform=body.platform or "instagram",
                                        extra=body.extra_instructions)
    gid = await _record_generation(user, "post", body.model_dump(), gen)
    acct_id = await _default_account_id(user)
    data = {"org_id": user["org_id"], "status": "draft", "source": "ai", "account_id": acct_id,
            "platform": body.platform or "instagram", "event_id": body.event_id,
            "topic": gen.get("topic"), "title": gen.get("title"), "body": gen.get("body"),
            "caption": gen.get("caption"), "cta": gen.get("cta"), "hashtags": gen.get("hashtags"),
            "image_suggestion": gen.get("image_suggestion"), "image_brief": gen.get("image_brief"), "category": gen.get("category"),
            "format": gen.get("format"), "ai_generation_id": gid,
            "created_by": user.get("user_id"), "created_by_name": user.get("name")}
    doc = await _create("social_posts", data)
    await _social_log(user, "generated", post_id=doc["id"], platform=doc.get("platform"))
    return doc


@api.post("/social/posts/{post_id}/regenerate")
async def social_regenerate(post_id: str, body: SocialGenerateIn, user: dict = Depends(require_admin)):
    post = await db.social_posts.find_one(oq(user, id=post_id), {"_id": 0})
    if not post:
        raise HTTPException(status_code=404, detail="Contenuto non trovato")
    settings = await _get_social_settings(user["org_id"])
    ev_id = body.event_id or post.get("event_id")
    event_ctx = await _event_public_context(ev_id, user["org_id"]) if ev_id else None
    gen = await social_ai.generate_post(settings, event_ctx,
                                        topic=body.topic or post.get("topic"),
                                        category=body.category or post.get("category"),
                                        platform=post.get("platform") or "instagram",
                                        extra=body.extra_instructions)
    gid = await _record_generation(user, "post", {"regenerate": post_id, **body.model_dump()}, gen)
    upd = {"topic": gen.get("topic"), "title": gen.get("title"), "body": gen.get("body"),
           "caption": gen.get("caption"), "cta": gen.get("cta"), "hashtags": gen.get("hashtags"),
           "image_suggestion": gen.get("image_suggestion"), "image_brief": gen.get("image_brief"), "category": gen.get("category"),
           "format": gen.get("format"), "ai_generation_id": gid, "status": "draft", "updated_at": now_iso()}
    await db.social_posts.update_one(oq(user, id=post_id), {"$set": upd})
    await _social_log(user, "regenerated", post_id=post_id)
    return await db.social_posts.find_one(oq(user, id=post_id), {"_id": 0})


@api.post("/social/plan/generate")
async def social_plan_generate(body: SocialPlanIn, user: dict = Depends(require_admin)):
    if body.event_id:
        await _assert_event_operational(user["org_id"], body.event_id)
    settings = await _get_social_settings(user["org_id"])
    event_ctx = await _event_public_context(body.event_id, user["org_id"]) if body.event_id else None
    dates = _plan_dates(body.date_from, body.date_to, body.posts_per_week, settings.get("preferred_times"))
    posts = await social_ai.generate_plan(settings, event_ctx, goal=body.goal,
                                          count=len(dates), platform=body.platform or "instagram")
    plan_id = new_id()
    await db.social_calendar.insert_one({
        "id": plan_id, "org_id": user["org_id"], "date_from": body.date_from, "date_to": body.date_to,
        "posts_per_week": body.posts_per_week, "goal": body.goal, "event_id": body.event_id,
        "platform": body.platform or "instagram", "count": len(posts),
        "created_by": user.get("user_id"), "created_by_name": user.get("name"), "created_at": now_iso()})
    gid = await _record_generation(user, "plan", body.model_dump(), {"count": len(posts)})
    created = []
    acct_id = await _default_account_id(user)
    for i, gen in enumerate(posts):
        data = {"org_id": user["org_id"], "status": "draft", "source": "plan", "account_id": acct_id, "plan_id": plan_id,
                "platform": body.platform or "instagram", "event_id": body.event_id,
                "topic": gen.get("topic"), "title": gen.get("title"), "body": gen.get("body"),
                "caption": gen.get("caption"), "cta": gen.get("cta"), "hashtags": gen.get("hashtags"),
                "image_suggestion": gen.get("image_suggestion"), "image_brief": gen.get("image_brief"), "category": gen.get("category"),
                "format": gen.get("format"), "scheduled_at": dates[i] if i < len(dates) else None,
                "ai_generation_id": gid, "created_by": user.get("user_id"), "created_by_name": user.get("name")}
        created.append(await _create("social_posts", data))
    await _social_log(user, "plan_generated", detail=f"plan {plan_id} · {len(created)} post")
    return {"plan_id": plan_id, "count": len(created), "posts": created}


@api.get("/social/calendar")
async def social_calendar_list(date_from: Optional[str] = None, date_to: Optional[str] = None,
                               user: dict = Depends(require_admin)):
    q = oq(user, scheduled_at={"$ne": None})
    if date_from or date_to:
        rng = {}
        if date_from:
            rng["$gte"] = date_from
        if date_to:
            rng["$lte"] = date_to + "T23:59:59"
        q["scheduled_at"] = rng
    posts = await db.social_posts.find(q, {"_id": 0}).sort("scheduled_at", 1).to_list(5000)
    plans = await db.social_calendar.find(oq(user), {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"posts": posts, "plans": plans}


# ---- Media library ----
@api.get("/social/media")
async def social_media_list(category: Optional[str] = None, event_id: Optional[str] = None,
                            user: dict = Depends(require_admin)):
    q = oq(user)
    if category:
        q["category"] = category
    if event_id:
        q["event_id"] = event_id
    docs = await db.social_media.find(q, {"_id": 0}).sort("created_at", -1).to_list(5000)
    for d in docs:
        if (d.get("url") or "").startswith("http"):
            continue
        fid = d.get("file_id")
        if not fid:
            continue
        frec = await db.files.find_one({"id": fid}, {"_id": 0})
        if frec and (frec.get("content_type") or "").startswith("image/"):
            tok = await _ensure_public_token(frec)
            d["url"] = _public_file_url(tok)
    return docs


@api.post("/social/media")
async def social_media_upload(file: UploadFile = File(...), name: str = Form(None),
                              category: str = Form(None), event_id: str = Form(None),
                              description: str = Form(None), tags: str = Form(None),
                              user: dict = Depends(require_admin)):
    if event_id:
        await _assert_event_operational(user["org_id"], event_id)
    data = await file.read()
    try:
        kind, ext = storage_utils.classify_and_validate(file.filename, file.content_type, len(data))
    except ValueError as e:
        raise HTTPException(status_code=400,
                            detail="File troppo grande" if str(e).startswith("too_large")
                            else "Carica un'immagine valida (JPG, PNG, WEBP, GIF)")
    if kind != "image":
        raise HTTPException(status_code=400, detail="Sono ammesse solo immagini")
    fid = new_id()
    path = f"social/{user['org_id']}/{fid}.{ext}"
    ctype = file.content_type or MIME.get(ext, "image/jpeg")
    result = await asyncio.to_thread(storage_utils.save, path, data, ctype)
    token = storage_utils.make_token()
    # Register in files collection so the existing /api/files/{id} download works (org-checked).
    await db.files.insert_one({"id": fid, "org_id": user["org_id"], "storage_path": result["path"],
                               "storage_backend": result.get("backend"), "public_token": token,
                               "original_filename": file.filename, "content_type": ctype,
                               "size": result.get("size"), "is_deleted": False, "created_at": now_iso()})
    tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
    doc = await _create("social_media", {
        "org_id": user["org_id"], "file_id": fid, "url": _public_file_url(token),
        "name": name or file.filename, "category": category or "photo", "event_id": event_id or None,
        "description": description or None, "tags": tag_list, "content_type": ctype,
        "size": result.get("size"), "uploaded_by": user.get("user_id")})
    await _social_log(user, "media_uploaded", detail=doc["id"])
    return doc


@api.put("/social/media/{media_id}")
async def social_media_update(media_id: str, body: SocialMediaUpdateIn, user: dict = Depends(require_admin)):
    clean = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    clean["updated_at"] = now_iso()
    res = await db.social_media.update_one(oq(user, id=media_id), {"$set": clean})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Media non trovato")
    return await db.social_media.find_one(oq(user, id=media_id), {"_id": 0})


@api.delete("/social/media/{media_id}")
async def social_media_delete(media_id: str, user: dict = Depends(require_admin)):
    m = await db.social_media.find_one(oq(user, id=media_id), {"_id": 0})
    if m and m.get("file_id"):
        await db.files.update_one({"id": m["file_id"], "org_id": user["org_id"]}, {"$set": {"is_deleted": True}})
    await db.social_media.delete_one(oq(user, id=media_id))
    return {"ok": True}


# ---- Social accounts ----
def _san_account(a: dict) -> dict:
    """Never expose secrets (tokens) to the frontend."""
    return {k: v for k, v in a.items() if k not in ("access_token",)}


@api.get("/social/accounts")
async def social_accounts_list(user: dict = Depends(require_admin)):
    rows = await db.social_accounts.find(oq(user), {"_id": 0}).to_list(50)
    return [_san_account(a) for a in rows]


@api.post("/social/accounts")
async def social_account_upsert(body: SocialAccountIn, user: dict = Depends(require_org_admin)):
    if body.platform not in SOCIAL_PLATFORMS:
        raise HTTPException(status_code=400, detail="Canale social non supportato")
    existing = await db.social_accounts.find_one(oq(user, platform=body.platform), {"_id": 0})
    payload = {"handle": body.handle, "status": "pending_connection",
               "connected": False, "access_token": None, "updated_at": now_iso()}
    if existing:
        await db.social_accounts.update_one(oq(user, id=existing["id"]), {"$set": payload})
        doc = await db.social_accounts.find_one(oq(user, id=existing["id"]), {"_id": 0})
    else:
        doc = await _create("social_accounts", {"org_id": user["org_id"], "platform": body.platform, **payload})
    await _social_log(user, "account_saved", platform=body.platform)
    return doc


@api.delete("/social/accounts/{account_id}")
async def social_account_delete(account_id: str, user: dict = Depends(require_org_admin)):
    await db.social_accounts.delete_one(oq(user, id=account_id))
    await _social_log(user, "account_removed", detail=account_id)
    return {"ok": True}


@api.get("/social/logs")
async def social_logs(post_id: Optional[str] = None, user: dict = Depends(require_admin)):
    q = oq(user)
    if post_id:
        q["post_id"] = post_id
    return await db.social_publish_logs.find(q, {"_id": 0}).sort("created_at", -1).limit(300).to_list(300)


# ---- Instagram OAuth (Phase D) — connection & compliance only; publishing stays OFF ----
@api.get("/oauth/instagram/start")
async def instagram_oauth_start(user: dict = Depends(require_org_admin)):
    if not instagram_utils.configured():
        raise HTTPException(status_code=400,
                            detail="Instagram non configurato: aggiungi META_APP_ID e META_APP_SECRET nelle variabili d'ambiente.")
    jti = new_id()
    state = jwt.encode({"uid": user["user_id"], "org_id": user["org_id"], "jti": jti,
                        "exp": datetime.now(timezone.utc) + timedelta(minutes=15)}, JWT_SECRET, algorithm=JWT_ALG)
    await db.ig_oauth_states.insert_one({"jti": jti, "org_id": user["org_id"], "uid": user["user_id"],
                                         "expires_at": datetime.now(timezone.utc) + timedelta(minutes=15),
                                         "created_at": now_iso()})
    return {"authorize_url": instagram_utils.authorize_url(state)}


@api.get("/oauth/instagram/callback")
async def instagram_oauth_callback(code: str = "", state: str = "", error: str = "", error_description: str = ""):
    dest_ok = f"{APP_URL}/marketing/impostazioni?instagram=connected"
    dest_err = f"{APP_URL}/marketing/impostazioni?instagram=error"
    if error or not code:
        logger.warning("instagram callback: error=%s desc=%s", error, (error_description or "")[:160])
        return RedirectResponse(dest_err)
    try:
        payload = jwt.decode(state, JWT_SECRET, algorithms=[JWT_ALG])
        org_id, uid, jti = payload["org_id"], payload["uid"], payload.get("jti")
    except jwt.PyJWTError:
        return RedirectResponse(dest_err)
    st = await db.ig_oauth_states.find_one_and_delete({"jti": jti, "org_id": org_id})
    if not st:
        return RedirectResponse(dest_err)
    try:
        tok = await instagram_utils.exchange_code(code)
        ig_user_id = str(tok.get("user_id"))
        ll = await instagram_utils.long_lived_token(tok.get("access_token"))
        access_token = ll.get("access_token")
        expires_in = int(ll.get("expires_in") or instagram_utils.DEFAULT_LL_EXPIRY)
        info = await instagram_utils.me(access_token)
    except Exception as e:
        logger.error("instagram callback exchange failed %s: %s", type(e).__name__, str(e)[:200])
        return RedirectResponse(dest_err)
    doc_set = {"platform": "instagram", "ig_user_id": ig_user_id, "username": info.get("username"),
               "account_type": info.get("account_type"), "handle": info.get("username"),
               "access_token": access_token,
               "token_expires_at": (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat(),
               "connected": True, "status": "connected", "scopes": instagram_utils.SCOPES, "updated_at": now_iso()}
    existing = await db.social_accounts.find_one({"org_id": org_id, "platform": "instagram"}, {"_id": 0})
    if existing:
        await db.social_accounts.update_one({"org_id": org_id, "id": existing["id"]}, {"$set": doc_set})
    else:
        await _create("social_accounts", {"org_id": org_id, **doc_set})
    await db.social_publish_logs.insert_one({"id": new_id(), "org_id": org_id, "post_id": None,
        "action": "instagram_connected", "actor_user_id": uid, "platform": "instagram",
        "detail": info.get("username"), "created_at": now_iso()})
    return RedirectResponse(dest_ok)


@api.post("/social/accounts/{account_id}/refresh-token")
async def instagram_refresh(account_id: str, user: dict = Depends(require_org_admin)):
    a = await db.social_accounts.find_one(oq(user, id=account_id), {"_id": 0})
    if not a or a.get("platform") != "instagram" or not a.get("access_token"):
        raise HTTPException(status_code=400, detail="Account Instagram non collegato")
    try:
        r = await instagram_utils.refresh_token(a["access_token"])
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Refresh token fallito: {str(e)[:140]}")
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=int(r.get("expires_in") or instagram_utils.DEFAULT_LL_EXPIRY))).isoformat()
    await db.social_accounts.update_one(oq(user, id=account_id),
                                        {"$set": {"access_token": r.get("access_token"),
                                                  "token_expires_at": expires_at, "updated_at": now_iso()}})
    await _social_log(user, "instagram_token_refreshed", platform="instagram")
    return {"ok": True, "token_expires_at": expires_at}


@api.post("/oauth/instagram/deauthorize")
async def instagram_deauthorize(signed_request: str = Form(...)):
    data = instagram_utils.parse_signed_request(signed_request)
    if not data:
        raise HTTPException(status_code=400, detail="signed_request non valido")
    ig_user_id = str(data.get("user_id"))
    accts = await db.social_accounts.find({"platform": "instagram", "ig_user_id": ig_user_id}).to_list(50)
    for a in accts:
        await db.social_accounts.update_one({"id": a["id"]}, {"$set": {
            "connected": False, "status": "deauthorized", "access_token": None,
            "token_expires_at": None, "updated_at": now_iso()}})
        await db.social_publish_logs.insert_one({"id": new_id(), "org_id": a["org_id"], "post_id": None,
            "action": "instagram_deauthorized", "platform": "instagram", "detail": ig_user_id, "created_at": now_iso()})
    return {"ok": True}


@api.post("/oauth/instagram/data-deletion")
async def instagram_data_deletion(signed_request: str = Form(...)):
    data = instagram_utils.parse_signed_request(signed_request)
    if not data:
        raise HTTPException(status_code=400, detail="signed_request non valido")
    ig_user_id = str(data.get("user_id"))
    code = new_id()
    accts = await db.social_accounts.find({"platform": "instagram", "ig_user_id": ig_user_id}).to_list(50)
    for a in accts:
        await db.social_accounts.update_one({"id": a["id"]}, {"$set": {
            "connected": False, "status": "data_deleted", "access_token": None, "token_expires_at": None,
            "ig_user_id": None, "username": None, "handle": None, "updated_at": now_iso()}})
        await db.social_publish_logs.insert_one({"id": new_id(), "org_id": a["org_id"], "post_id": None,
            "action": "instagram_data_deletion", "platform": "instagram", "detail": code, "created_at": now_iso()})
    await db.ig_data_deletions.insert_one({"id": new_id(), "confirmation_code": code, "ig_user_id": ig_user_id,
        "accounts": [a["id"] for a in accts], "status": "completed", "created_at": now_iso()})
    status_url = f"{instagram_utils.BACKEND_PUBLIC_URL}/api/oauth/instagram/data-deletion/status?code={code}"
    return {"url": status_url, "confirmation_code": code}


@api.get("/oauth/instagram/data-deletion/status")
async def instagram_data_deletion_status(code: str):
    rec = await db.ig_data_deletions.find_one({"confirmation_code": code}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Codice non trovato")
    return {"confirmation_code": code, "status": rec.get("status"), "created_at": rec.get("created_at")}


CATEGORY_TEMPLATE = {
    "educational": "educational", "problema_soluzione": "problema_soluzione",
    "funzionalita_crmevent": "funzionalita", "organizzazione_evento": "foto_evento",
    "gestione_staff_volontari": "foto_evento", "sponsor": "foto_evento", "briefing": "funzionalita",
    "dietro_le_quinte": "foto_evento", "novita_prodotto": "funzionalita",
    "consigli_organizzatori": "quote", "countdown": "commerciale", "cta_demo_prova": "commerciale",
}
_LOGO_PATH = "/app/frontend/public/logo-crmevent.png"


class SocialCreativeIn(BaseModel):
    mode: Optional[str] = "auto"        # auto | photo | screenshot | ai
    template: Optional[str] = None
    format: Optional[str] = None
    media_id: Optional[str] = None
    show_cta: Optional[bool] = True
    ai_prompt: Optional[str] = None


async def _brand_logo_bytes(settings: dict) -> Optional[bytes]:
    url = (settings or {}).get("logo_url")
    if url and url.startswith("http"):
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(url)
            if r.status_code < 400:
                return r.content
        except Exception:
            pass
    try:
        with open(_LOGO_PATH, "rb") as f:
            return f.read()
    except Exception:
        return None


async def _load_media_bytes(org_id: str, media_id: str):
    m = await db.social_media.find_one({"org_id": org_id, "id": media_id}, {"_id": 0})
    if not m:
        return None, None
    f = await db.files.find_one({"id": m.get("file_id"), "org_id": org_id}, {"_id": 0})
    if not f:
        return None, None
    try:
        data, _ct = await _read_file_rec(f)
        return data, m
    except Exception:
        return None, None


async def _suggest_media(org_id: str, event_id: Optional[str], prefer: list):
    items = await db.social_media.find({"org_id": org_id, "category": {"$ne": "creative"}}, {"_id": 0}).to_list(500)
    if event_id:
        ev = [x for x in items if x.get("event_id") == event_id]
        items = ev or items
    pref = [x for x in items if x.get("category") in prefer]
    pick = pref or items
    return pick[0] if pick else None


def _detect_feed_format(width: int, height: int):
    """Return '1:1' or '4:5' if the image matches an Instagram feed ratio, else None."""
    if width <= 0 or height <= 0:
        return None
    ratio = width / height
    if abs(ratio - 1.0) <= 0.03:
        return "1:1"
    if abs(ratio - 0.8) <= 0.03:
        return "4:5"
    return None


async def _delete_creative_media(user: dict, media_id: Optional[str]):
    if not media_id:
        return
    m = await db.social_media.find_one(oq(user, id=media_id), {"_id": 0})
    if m and m.get("file_id"):
        await db.files.update_one({"id": m["file_id"], "org_id": user["org_id"]}, {"$set": {"is_deleted": True}})
    await db.social_media.delete_one(oq(user, id=media_id))


@api.post("/social/posts/{post_id}/creative/upload")
async def social_post_creative_upload(post_id: str, file: UploadFile = File(...),
                                      user: dict = Depends(require_admin)):
    """Manual upload of the final creative (graphic produced externally). No AI generation."""
    post = await db.social_posts.find_one(oq(user, id=post_id), {"_id": 0})
    if not post:
        raise HTTPException(status_code=404, detail="Contenuto non trovato")
    data = await file.read()
    ctype = (file.content_type or "").lower()
    fname = (file.filename or "").lower()
    if not (ctype.startswith("image/") or fname.endswith((".jpg", ".jpeg", ".png", ".webp"))):
        raise HTTPException(status_code=400, detail="Carica un'immagine (JPG, PNG o WEBP)")
    from PIL import Image
    import io as _io
    try:
        im = Image.open(_io.BytesIO(data)); im.load()
        w, h = im.size
    except Exception:
        raise HTTPException(status_code=400, detail="File immagine non valido o corrotto")
    fmt = _detect_feed_format(w, h)
    if not fmt:
        raise HTTPException(status_code=400,
                            detail=f"Formato {w}x{h}px non compatibile con il feed Instagram. Usa 1:1 (quadrato) o 4:5 (verticale).")
    try:
        social_creative.to_jpeg(data)  # technical check reused at publish time
    except Exception:
        raise HTTPException(status_code=400, detail="Immagine non elaborabile per la pubblicazione")
    old_id = post.get("creative_media_id")
    fid = new_id()
    ext = {"image/png": "png", "image/webp": "webp", "image/jpeg": "jpg"}.get(ctype) or (fname.rsplit(".", 1)[-1] if "." in fname else "jpg")
    path = f"social/{user['org_id']}/creative_{fid}.{ext}"
    result = await asyncio.to_thread(storage_utils.save, path, data, ctype or "image/jpeg")
    token = storage_utils.make_token()
    await db.files.insert_one({"id": fid, "org_id": user["org_id"], "storage_path": result["path"],
                               "storage_backend": result.get("backend"), "public_token": token,
                               "original_filename": file.filename or f"creative_{post_id}.{ext}",
                               "content_type": ctype or "image/jpeg", "size": result.get("size"),
                               "is_deleted": False, "created_at": now_iso()})
    meta = {"mode": "manual", "format": fmt, "width": w, "height": h}
    media_doc = await _create("social_media", {
        "org_id": user["org_id"], "file_id": fid, "url": _public_file_url(token),
        "name": f"Creatività (manuale) · {fmt}", "category": "creative",
        "event_id": post.get("event_id"), "post_id": post_id, "tags": ["creativity", "manual"],
        "content_type": ctype or "image/jpeg", "size": result.get("size"), "meta": meta,
        "uploaded_by": user.get("user_id")})
    await db.social_posts.update_one(oq(user, id=post_id), {"$set": {
        "creative_media_id": media_doc["id"], "creative_meta": meta, "format": fmt, "updated_at": now_iso()}})
    if old_id and old_id != media_doc["id"]:
        await _delete_creative_media(user, old_id)
    await _social_log(user, "creative_uploaded", post_id=post_id, detail=f"manual/{fmt}/{w}x{h}")
    post = await db.social_posts.find_one(oq(user, id=post_id), {"_id": 0})
    return {"post": post, "media": media_doc, "url": media_doc["url"]}


@api.delete("/social/posts/{post_id}/creative")
async def social_post_creative_delete(post_id: str, user: dict = Depends(require_admin)):
    post = await db.social_posts.find_one(oq(user, id=post_id), {"_id": 0})
    if not post:
        raise HTTPException(status_code=404, detail="Contenuto non trovato")
    await _delete_creative_media(user, post.get("creative_media_id"))
    new_status = post.get("status")
    if new_status in ("approved", "scheduled"):
        new_status = "draft"  # cannot remain approved/scheduled without a creative
    await db.social_posts.update_one(oq(user, id=post_id), {"$set": {
        "creative_media_id": None, "creative_meta": None, "status": new_status, "updated_at": now_iso()}})
    await _social_log(user, "creative_removed", post_id=post_id)
    return await db.social_posts.find_one(oq(user, id=post_id), {"_id": 0})


@api.get("/social/meta")
async def social_meta(user: dict = Depends(require_admin)):
    """Static metadata for the UI (statuses, categories, formats, platforms)."""
    events = await db.events.find(oq(user), {"_id": 0, "id": 1, "nome": 1, "data_inizio": 1}).to_list(2000)
    return {"statuses": SOCIAL_STATUSES, "status_labels": SOCIAL_STATUS_LABELS,
            "categories": social_ai.CATEGORIES, "formats": social_ai.FORMATS,
            "platforms": SOCIAL_PLATFORMS, "creative_templates": social_creative.TEMPLATES,
            "events": [{"id": e["id"], "nome": e.get("nome"), "data_inizio": e.get("data_inizio")} for e in events]}


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
    try:  # classificazione storica (non distruttiva): accessi/operazioni Super Admin = registro tecnico amministrativo
        sa_ids = [u["user_id"] for u in await db.users.find({"role": "superadmin"}, {"_id": 0, "user_id": 1}).to_list(50)]
        await db.audit_logs.update_many({"scope": {"$exists": False}, "$or": [{"actor_role": "superadmin"}, {"actor_user_id": {"$in": sa_ids}}]},
                                        {"$set": {"scope": "platform_admin"}})
        await db.audit_logs.update_many({"scope": {"$exists": False}}, {"$set": {"scope": "org"}})
        # Il Super Admin non è mai membro delle organizzazioni che consulta: disattiva eventuali membership create per errore (senza cancellarle).
        await db.memberships.update_many({"user_id": {"$in": sa_ids}, "active": True}, {"$set": {"active": False, "deactivated_reason": "platform_admin"}})
    except Exception as e:
        logger.error(f"audit scope migration: {e}")
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
              "person_companies", "briefing_versions", "files",
              "social_settings", "social_accounts", "social_posts", "social_calendar",
              "social_media", "social_ai_generations", "social_publish_logs"]:
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
        await db.ig_oauth_states.create_index("expires_at", expireAfterSeconds=0)
        await db.social_accounts.create_index([("platform", 1), ("ig_user_id", 1)])
        await db.ig_data_deletions.create_index("confirmation_code")
        await db.ig_public_media.create_index("token")
        await db.files.create_index("public_token", unique=True, sparse=True)
    except Exception:
        pass
    if storage_utils.STORAGE_BACKEND != "local":
        try:
            storage_utils.init_storage()
            logger.info("Storage initialized")
        except Exception as e:
            logger.error(f"Storage init failed: {e}")
    await seed_admin()
    await migrate_person_companies()
    await migrate_memberships()
    await seed_support()
    await migrate_legacy_orgs_to_trial()
    asyncio.create_task(news.sync_releases(db))  # bozze Novità solo se CRMEVENT_ENV=production
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


# ==================== RACCOLTA DISPONIBILITÀ STAFF/VOLONTARI ====================
# Public no-login availability collection, per-event. Data stays org-scoped: the secure
# random `code` is the ONLY way an anonymous visitor resolves (org + event); it exposes
# only the minimal public event info and accepts a single availability submission.
_WD_IT = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
_MO_IT = ["", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
          "agosto", "settembre", "ottobre", "novembre", "dicembre"]
_avail_rate = defaultdict(list)


def _avail_rate_ok(key, max_calls=6, window=60):
    now = time.time()
    b = _avail_rate[key]
    while b and b[0] < now - window:
        b.pop(0)
    if len(b) >= max_calls:
        return False
    b.append(now)
    return True


def _client_ip(request: Request) -> str:
    fwd = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    return fwd or (request.client.host if request.client else "?")


def _compute_age(dn: Optional[str]) -> Optional[int]:
    if not dn:
        return None
    try:
        b = datetime.strptime(dn[:10], "%Y-%m-%d").date()
    except Exception:
        return None
    t = datetime.now(timezone.utc).date()
    return t.year - b.year - ((t.month, t.day) < (b.month, b.day))


# ---- Codice Fiscale (Italian tax code) parsing & validation ----
_CF_OMO = {"L": "0", "M": "1", "N": "2", "P": "3", "Q": "4", "R": "5", "S": "6", "T": "7", "U": "8", "V": "9"}
_CF_MONTHS = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "H": 6, "L": 7, "M": 8, "P": 9, "R": 10, "S": 11, "T": 12}
_CF_ODD = {"0": 1, "1": 0, "2": 5, "3": 7, "4": 9, "5": 13, "6": 15, "7": 17, "8": 19, "9": 21,
           "A": 1, "B": 0, "C": 5, "D": 7, "E": 9, "F": 13, "G": 15, "H": 17, "I": 19, "J": 21,
           "K": 2, "L": 4, "M": 18, "N": 20, "O": 11, "P": 3, "Q": 6, "R": 8, "S": 12, "T": 14,
           "U": 16, "V": 10, "W": 22, "X": 25, "Y": 24, "Z": 23}


def _cf_normalize(cf: Optional[str]) -> str:
    return re.sub(r"[^A-Z0-9]", "", (cf or "").upper())


def _cf_valid(cf: str) -> bool:
    cf = _cf_normalize(cf)
    if len(cf) != 16 or not re.match(r"^[A-Z0-9]{16}$", cf):
        return False
    tot = 0
    for i, ch in enumerate(cf[:15]):
        if i % 2 == 0:  # odd position (1-indexed)
            tot += _CF_ODD.get(ch, -999)
        else:
            tot += (int(ch) if ch.isdigit() else ord(ch) - ord("A"))
    if tot < 0:
        return False
    return chr(ord("A") + tot % 26) == cf[15]


def _cf_birthdate(cf: str) -> Optional[str]:
    cf = _cf_normalize(cf)
    if len(cf) != 16:
        return None
    try:
        yy = int(_CF_OMO.get(cf[6], cf[6]) + _CF_OMO.get(cf[7], cf[7]))
        mon = _CF_MONTHS.get(cf[8])
        day = int(_CF_OMO.get(cf[9], cf[9]) + _CF_OMO.get(cf[10], cf[10]))
    except ValueError:
        return None
    if not mon:
        return None
    if day > 40:
        day -= 40
    if day < 1 or day > 31:
        return None
    cy = datetime.now(timezone.utc).year % 100
    year = 2000 + yy if yy <= cy else 1900 + yy
    try:
        return datetime(year, mon, day).strftime("%Y-%m-%d")
    except ValueError:
        return None


def _avail_days(event: dict) -> list:
    """Days offered on the public form: from setup start (allestimento) or event start,
    through teardown end (disallestimento) or event end. Each day is tagged
    'allestimento' (before event start), 'evento', or 'disallestimento' (after event end)."""
    di = event.get("data_inizio")
    df = event.get("data_fine") or di
    allest = event.get("data_inizio_allestimento")
    disallest = event.get("data_fine_disallestimento")
    start = allest or di
    end = disallest or df or di
    if not start or not end:
        return []
    try:
        s = datetime.strptime(start[:10], "%Y-%m-%d").date()
        e = datetime.strptime(end[:10], "%Y-%m-%d").date()
        evstart = datetime.strptime(di[:10], "%Y-%m-%d").date() if di else s
        evend = datetime.strptime(df[:10], "%Y-%m-%d").date() if df else evstart
    except Exception:
        return []
    if e < s:
        return []
    desc = event.get("giorni_descrizioni") or {}
    out, cur = [], s
    while cur <= e and len(out) < 120:
        if di and cur < evstart:
            fase = "allestimento"
        elif cur > evend:
            fase = "disallestimento"
        else:
            fase = "evento"
        day = {"date": cur.isoformat(), "fase": fase,
               "label": f"{_WD_IT[cur.weekday()]} {cur.day} {_MO_IT[cur.month]}"}
        if fase == "evento":
            day["descrizione"] = desc.get(cur.isoformat()) or None
        out.append(day)
        cur += timedelta(days=1)
    return out


def _avail_link_url(code: str) -> str:
    return f"{PUBLIC_SITE_URL}/partecipa/{code}"


# ---- Admin (org-scoped) ----
@api.post("/events/{event_id}/availability/link")
async def avail_generate_link(event_id: str, user: dict = Depends(require_admin)):
    event = await db.events.find_one(oq(user, id=event_id), {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Evento non trovato")
    await _assert_event_operational(user["org_id"], event_id)
    await db.avail_links.update_many({"org_id": user["org_id"], "evento_id": event_id, "active": True},
                                     {"$set": {"active": False, "revoked_at": now_iso()}})
    code = secrets.token_urlsafe(24)
    await db.avail_links.insert_one({"id": new_id(), "org_id": user["org_id"], "evento_id": event_id,
                                     "code": code, "active": True, "created_at": now_iso(),
                                     "created_by": user.get("user_id"), "revoked_at": None})
    return {"active": True, "code": code, "url": _avail_link_url(code)}


@api.get("/events/{event_id}/availability/link")
async def avail_get_link(event_id: str, user: dict = Depends(require_admin)):
    event = await db.events.find_one(oq(user, id=event_id), {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Evento non trovato")
    link = await db.avail_links.find_one({"org_id": user["org_id"], "evento_id": event_id, "active": True}, {"_id": 0})
    if not link:
        return {"active": False, "code": None, "url": None}
    return {"active": True, "code": link["code"], "url": _avail_link_url(link["code"])}


@api.post("/events/{event_id}/availability/link/deactivate")
async def avail_deactivate_link(event_id: str, user: dict = Depends(require_admin)):
    await db.avail_links.update_many({"org_id": user["org_id"], "evento_id": event_id, "active": True},
                                     {"$set": {"active": False, "revoked_at": now_iso()}})
    return {"active": False}


@api.get("/events/{event_id}/availabilities")
async def avail_list_received(event_id: str, user: dict = Depends(require_admin)):
    event = await db.events.find_one(oq(user, id=event_id), {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Evento non trovato")
    rows = await db.availabilities.find({"org_id": user["org_id"], "evento_id": event_id}, {"_id": 0}).sort("created_at", -1).to_list(3000)
    if _team_ids(user) is not None:
        vis = await _team_person_ids(user["org_id"], _team_ids(user), (user.get("perm") or {}).get("via_tl"), event_id)
        rows = [r for r in rows if r.get("persona_id") in vis]
    out = []
    for r in rows:
        p = await db.persons.find_one({"id": r.get("persona_id"), "org_id": user["org_id"]}, {"_id": 0}) or {}
        dn = p.get("data_nascita") or r.get("data_nascita")
        out.append({**r,
                    "persona": {"id": p.get("id") or r.get("persona_id"),
                                "nome": p.get("nome") or r.get("nome"),
                                "cognome": p.get("cognome") or r.get("cognome"),
                                "email": p.get("email") or r.get("email"),
                                "cellulare": p.get("cellulare") or r.get("cellulare"),
                                "data_nascita": dn},
                    "eta": _compute_age(dn)})
    return {"event": {"id": event["id"], "nome": event.get("nome"),
                      "data_inizio_allestimento": event.get("data_inizio_allestimento"),
                      "data_inizio": event.get("data_inizio"), "data_fine": event.get("data_fine"),
                      "data_fine_disallestimento": event.get("data_fine_disallestimento")},
            "availabilities": out}


# ---- Brevo sync per disponibilità (gated: nessun invio reale finché BREVO_AVAILABILITY_ENABLED è off) ----
AVAIL_LIST_NAME = "CRMEvent · Disponibilità eventi"
AVAIL_TPL_CONFERMA_DISP = "CRMEvent · Disponibilità ricevuta"
AVAIL_TPL_CONFERMA_PART = "CRMEvent · Partecipazione confermata"
AVAIL_TPL_CONFERMA_DISP_EN = "CRMEvent · Availability received (EN)"
AVAIL_TPL_CONFERMA_PART_EN = "CRMEvent · Participation confirmed (EN)"
AVAIL_TPL_KIND_LABEL = {"disponibilita": "Disponibilità", "conferma": "Conferma"}
AVAIL_TPL_SUBJECT = {
    "it": {
        "disponibilita": "Grazie {{params.NOME}}, abbiamo ricevuto la tua disponibilità",
        "conferma": "{{params.NOME_EVENTO}}: la tua disponibilità è confermata",
    },
    "en": {
        "disponibilita": "Thank you {{params.NOME}}, we have received your availability",
        "conferma": "{{params.NOME_EVENTO}}: your availability is confirmed",
    },
}
# Mappa nome-template-base (IT) -> nome localizzato per lingua. Fallback IT se EN assente.
AVAIL_TPL_LANG = {
    AVAIL_TPL_CONFERMA_DISP: {"it": AVAIL_TPL_CONFERMA_DISP, "en": AVAIL_TPL_CONFERMA_DISP_EN},
    AVAIL_TPL_CONFERMA_PART: {"it": AVAIL_TPL_CONFERMA_PART, "en": AVAIL_TPL_CONFERMA_PART_EN},
}


def _avail_lang(av: dict) -> str:
    """Lingua della comunicazione = lingua di compilazione del modulo (fallback it)."""
    return "en" if (av.get("compilation_lang") or "").lower().startswith("en") else "it"


def _brevo_avail_enabled():
    return os.environ.get("BREVO_AVAILABILITY_ENABLED", "").strip().lower() in ("1", "true", "on", "yes")


def _norm_phone(raw, default_cc="+39"):
    """Normalizza un numero al formato internazionale E.164 (+<8-15 cifre>).
    Gestisce spazi, trattini, parentesi, prefisso 00 e '+' già presente. Se non parte con '+'
    assume il prefisso di default (Italia). Ritorna None se non valido (il chiamante decide il fallback)."""
    if not raw:
        return None
    n = re.sub(r"[^\d+]", "", str(raw))
    if not n:
        return None
    if n.startswith("00"):
        n = "+" + n[2:]
    if n.startswith("+"):
        digits = re.sub(r"\D", "", n)
    else:
        cc = re.sub(r"\D", "", default_cc or "39")
        digits = cc + re.sub(r"\D", "", n).lstrip("0")
    if 8 <= len(digits) <= 15:
        return "+" + digits
    return None


async def _avail_list_id():
    """List ID Brevo salvato per la lista unica disponibilità (globale, un solo account Brevo)."""
    doc = await db.brevo_config.find_one({"key": "availability"}, {"_id": 0}) or {}
    return doc.get("list_id")


async def _avail_list_id_save(list_id, name=None):
    await db.brevo_config.update_one({"key": "availability"},
                                     {"$set": {"key": "availability", "list_id": list_id,
                                               "list_name": name or AVAIL_LIST_NAME, "updated_at": now_iso()}},
                                     upsert=True)


async def _ensure_avail_list(c):
    """Trova o crea (via API) la lista unica «CRMEvent · Disponibilità eventi» e persiste il List ID.
    Mai una lista per Evento: tutte le disponibilità confluiscono in questa unica lista."""
    list_id = await _avail_list_id()
    if list_id:
        return list_id
    lists = await c.lists()
    lst = next((l for l in lists if (l.get("name") or "").strip().lower() == AVAIL_LIST_NAME.lower()), None)
    if not lst:
        folders = await c.folders()
        lst = await c.create_list(AVAIL_LIST_NAME, folders[0]["id"] if folders else 1)
    list_id = lst.get("id")
    await _avail_list_id_save(list_id)
    return list_id


def _avail_email_html(kind: str, lang: str = "it") -> str:
    """Master template HTML (uno per lingua/tipo). Dati dinamici via {{params.*}}:
    NOME, NOME_EVENTO, DATA_EVENTO, LOCALITA_EVENTO, LOGO_EVENTO_URL. Il logo NON è salvato nel
    template: viene passato ad ogni invio (logo dell'Evento o fallback CRMEvent).
    Nome evento e contenuti dell'organizzatore NON vengono tradotti."""
    en = str(lang).lower().startswith("en")
    if kind == "conferma":
        if en:
            intro = ("<p>{% if params.NOME %}Hi {{params.NOME}},{% else %}Hi,{% endif %}</p>"
                     "<p>we're glad to confirm your participation in <strong>{{params.NOME_EVENTO}}</strong>. "
                     "Thank you for choosing to be part of the team that will help make this event happen.</p>")
            outro = ("<p>Over the next few days you'll receive the operational details about your activity, schedule, "
                     "meeting point and briefing. There's nothing else you need to do for now.</p>"
                     "<p>See you soon!<br/>The {{params.NOME_EVENTO}} team</p>")
        else:
            intro = ("<p>{% if params.NOME %}Ciao {{params.NOME}},{% else %}Ciao,{% endif %}</p>"
                     "<p>ci fa piacere confermarti la partecipazione a <strong>{{params.NOME_EVENTO}}</strong>. "
                     "Grazie per aver scelto di far parte della squadra che contribuirà alla realizzazione dell'evento.</p>")
            outro = ("<p>Nei prossimi giorni riceverai le informazioni operative relative alla tua attività, agli orari, "
                     "al punto di ritrovo e al briefing. Non devi fare altro per il momento.</p>"
                     "<p>A presto!<br/>Lo staff di {{params.NOME_EVENTO}}</p>")
    else:
        if en:
            intro = ("<p>{% if params.NOME %}Hi {{params.NOME}},{% else %}Hi,{% endif %}</p>"
                     "<p>thank you for sharing your availability for <strong>{{params.NOME_EVENTO}}</strong>. "
                     "We've correctly received your details and the days you indicated you're available.</p>"
                     "<p>The organizer is collecting all availabilities and will contact you later to confirm and "
                     "share the operational information.</p>")
            outro = ("<p>Thank you for your availability and for the time you've decided to dedicate to us.<br/>"
                     "The {{params.NOME_EVENTO}} team</p>")
        else:
            intro = ("<p>{% if params.NOME %}Ciao {{params.NOME}},{% else %}Ciao,{% endif %}</p>"
                     "<p>grazie per aver dato la tua disponibilità per <strong>{{params.NOME_EVENTO}}</strong>. "
                     "Abbiamo ricevuto correttamente i tuoi dati e le giornate in cui hai indicato di essere disponibile.</p>"
                     "<p>L'organizzazione sta raccogliendo tutte le disponibilità e ti contatterà successivamente per "
                     "comunicarti l'eventuale conferma e le informazioni operative.</p>")
            outro = ("<p>Grazie per la disponibilità e per il tempo che hai deciso di dedicarci.<br/>"
                     "Lo staff di {{params.NOME_EVENTO}}</p>")
    footer = "Communication managed via CRMEvent" if en else "Comunicazione gestita tramite CRMEvent"
    return (
        '<div style="background:#f1f5f9;padding:24px 0;font-family:Arial,Helvetica,sans-serif;">'
        '<div style="max-width:560px;margin:0 auto;background:#ffffff;border-radius:16px;overflow:hidden;border:1px solid #e2e8f0;">'
        '<div style="padding:28px 24px;text-align:center;">'
        '<img src="{{params.LOGO_EVENTO_URL}}" alt="{{params.NOME_EVENTO}}" style="max-width:200px;max-height:96px;height:auto;object-fit:contain;display:inline-block;border:0;"/>'
        '<h1 style="font-size:20px;color:#0f172a;margin:18px 0 4px;">{{params.NOME_EVENTO}}</h1>'
        '<p style="font-size:14px;color:#64748b;margin:0;">{{params.DATA_EVENTO}}</p>'
        '<p style="font-size:14px;color:#64748b;margin:2px 0 0;">{{params.LOCALITA_EVENTO}}</p>'
        '</div>'
        '<div style="padding:8px 28px 24px;color:#1f2a37;font-size:15px;line-height:1.6;">'
        f'{intro}{outro}'
        '</div>'
        '<div style="padding:16px 24px;background:#f8fafc;border-top:1px solid #e2e8f0;text-align:center;color:#94a3b8;font-size:12px;">'
        f'{footer}'
        '</div></div></div>'
    )


def _event_logo_url(event: dict, base: str = None) -> str:
    base = (base or PUBLIC_SITE_URL).rstrip("/")
    if event.get("logo_url"):
        return f"{base}/api/public/event-logo/{event.get('id')}"
    return f"{PUBLIC_SITE_URL}/logo-crmevent-dark.png?v=5"


def _avail_email_params(av: dict, event: dict, org: dict, logo_url: str) -> dict:
    """Solo i dati necessari alla comunicazione. MAI Codice Fiscale, data di nascita, note, rimborsi."""
    return {
        "NOME": av.get("nome") or "",
        "COGNOME": av.get("cognome") or "",
        "NOME_EVENTO": event.get("nome") or "",
        "DATA_EVENTO": event.get("data_inizio") or "",
        "LOCALITA_EVENTO": event.get("localita") or event.get("citta") or "",
        "LOGO_EVENTO_URL": logo_url or "",
        "NOME_ORGANIZZAZIONE": (org or {}).get("nome") or "",
        "DATA_INIZIO_ALLESTIMENTO": event.get("data_inizio_allestimento") or "",
        "DATA_FINE_DISALLESTIMENTO": event.get("data_fine_disallestimento") or "",
    }


async def _brevo_avail(action: str, av: dict, event: dict, org_nome: str = None, send_template: str = None):
    """Best-effort, gated Brevo sync for an availability. Never raises: availability data has
    priority. Records a brevo_sync_log row. Real contact upsert / email send happen ONLY when
    BREVO_AVAILABILITY_ENABLED is on AND a key is configured; otherwise the intent is logged as
    'pending' for later retry/approval. Codice Fiscale is NEVER sent to Brevo."""
    email = (av.get("email") or "").strip().lower()
    log = {"id": new_id(), "org_id": av.get("org_id"), "evento_id": av.get("evento_id"),
           "availability_id": av.get("id"), "email": email, "action": action,
           "template": send_template, "created_at": now_iso()}
    if not email:
        log["status"] = "skipped_no_email"
        await db.brevo_sync_log.insert_one(log)
        return {"status": "skipped_no_email", "sent": False}
    if not _brevo_avail_enabled() or not brevo_client.is_configured():
        log["status"] = "pending" if not _brevo_avail_enabled() else "skipped_no_key"
        await db.brevo_sync_log.insert_one(log)
        return {"status": log["status"], "sent": False}
    sent, err, phone_rejected = False, None, False
    sms = _norm_phone(av.get("cellulare"))
    try:
        attrs = {"NOME": av.get("nome"), "COGNOME": av.get("cognome"),
                 "EVENTO": event.get("nome"), "DATA_EVENTO": event.get("data_inizio"),
                 "ORGANIZZAZIONE": org_nome or "", "RUOLO_EVENTO": av.get("ruolo_evento") or "da_definire",
                 "STATO_DISPONIBILITA": av.get("stato") or "nuova"}
        if sms:
            attrs["SMS"] = sms
        async with brevo_client.BrevoClient() as c:
            list_id = await _ensure_avail_list(c)
            exists = bool(await c.get_contact(email))

            async def _upsert(a):
                if exists:
                    await c.update_contact(email, list_id=list_id, attributes=a)
                else:
                    await c.create_contact(email, list_id, attributes=a)

            try:
                await _upsert(attrs)
            except brevo_client.BrevoError as be:
                # Il telefono non deve MAI bloccare l'ingresso in lista: se Brevo rifiuta l'attributo
                # telefono (400), ritenta l'upsert senza SMS così il contatto entra e riceve le email.
                if "SMS" in attrs and be.status == 400:
                    phone_rejected = True
                    attrs.pop("SMS", None)
                    await _upsert(attrs)
                else:
                    raise
            if send_template:
                lang = _avail_lang(av)
                want_name = AVAIL_TPL_LANG.get(send_template, {}).get(lang, send_template)
                tpls = await c.get_templates()

                def _find_active(n):
                    return next((t for t in tpls if (t.get("name") or "").strip().lower() == n.lower() and t.get("isActive")), None)

                tpl = _find_active(want_name) or _find_active(send_template)  # fallback lingua IT
                if tpl:
                    params = _avail_email_params(av, event, {"nome": org_nome}, _event_logo_url(event))
                    await c._req("POST", "/smtp/email", json={"to": [{"email": email, "name": av.get("nome") or ""}],
                                                              "templateId": tpl.get("id"), "params": params})
                    sent = True
        log["status"] = "sent" if sent else "synced"
        if phone_rejected:
            log["phone_rejected"] = True
            log["warning"] = "Telefono rifiutato da Brevo: contatto sincronizzato senza numero."
    except Exception as e:
        err = str(e)[:300]
        log["status"] = "error"
        log["error"] = err
        logger.error(f"brevo avail sync failed: {err}")
    await db.brevo_sync_log.insert_one(log)
    return {"status": log["status"], "sent": sent, "error": err, "phone_rejected": phone_rejected}


async def _confirm_availability(a: dict, event: dict, org_nome: str, user: dict) -> bool:
    """Set an availability to 'confermata' (idempotent) and trigger the 2nd Brevo email at most once."""
    now = now_iso()
    upd = {"stato": "confermata", "updated_at": now,
           "confirmed_at": a.get("confirmed_at") or now,
           "confirmed_by": a.get("confirmed_by") or (user.get("email") or user.get("user_id"))}
    emailed = False
    if not a.get("confirmation_email_sent_at"):
        res = await _brevo_avail("confirm", {**a, "stato": "confermata"}, event, org_nome, send_template=AVAIL_TPL_CONFERMA_PART)
        upd["confirmation_email_status"] = res["status"]
        if res.get("sent"):
            upd["confirmation_email_sent_at"] = now
            emailed = True
        if res.get("error"):
            upd["confirmation_email_error"] = res["error"]
    await db.availabilities.update_one({"org_id": a["org_id"], "id": a["id"]}, {"$set": upd})
    return emailed


class AvailUpdate(BaseModel):
    ruolo_evento: Optional[str] = None
    stato: Optional[str] = None
    preferenza_attivita: Optional[str] = None
    preferenza_altro: Optional[str] = None
    apply_person: Optional[bool] = False


@api.put("/availabilities/{aid}")
async def avail_update_one(aid: str, body: AvailUpdate, user: dict = Depends(require_admin)):
    a = await db.availabilities.find_one({"org_id": user["org_id"], "id": aid}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Disponibilità non trovata")
    event = await db.events.find_one({"id": a.get("evento_id"), "org_id": user["org_id"]}, {"_id": 0}) or {}
    org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0}) or {}
    org_nome = org.get("nome")
    upd = {}
    ruolo_changed = stato_changed = False
    if body.ruolo_evento in ("da_definire", "staff", "volontario"):
        upd["ruolo_evento"] = body.ruolo_evento
        ruolo_changed = body.ruolo_evento != a.get("ruolo_evento")
    if body.preferenza_attivita is not None:
        upd["preferenza_attivita"] = body.preferenza_attivita
    if body.preferenza_altro is not None:
        upd["preferenza_altro"] = body.preferenza_altro
    if body.apply_person and a.get("mismatch"):
        sub = a.get("submitted") or {}
        pfields = {k: sub[k] for k in ("nome", "cognome", "email", "cellulare", "data_nascita", "codice_fiscale") if sub.get(k)}
        if a.get("persona_id") and pfields:
            await db.persons.update_one({"id": a["persona_id"], "org_id": user["org_id"]},
                                        {"$set": {**pfields, "updated_at": now_iso()}})
        upd["mismatch"] = None
        upd["has_mismatch"] = False
    prev_stato = a.get("stato")
    do_confirm = body.stato == "confermata" and prev_stato != "confermata"
    if body.stato in ("nuova", "confermata", "non_utilizzata") and not do_confirm:
        upd["stato"] = body.stato
        stato_changed = body.stato != prev_stato
    upd["updated_at"] = now_iso()
    await db.availabilities.update_one({"org_id": user["org_id"], "id": aid}, {"$set": upd})
    if do_confirm:
        await _confirm_availability({**a, **upd}, event, org_nome, user)
    elif ruolo_changed or stato_changed:
        final = await db.availabilities.find_one({"org_id": user["org_id"], "id": aid}, {"_id": 0})
        try:
            await _brevo_avail("attr_update", final, event, org_nome)
        except Exception:
            pass
    return await db.availabilities.find_one({"org_id": user["org_id"], "id": aid}, {"_id": 0})


class BulkConfirm(BaseModel):
    ids: List[str] = []


@api.post("/events/{event_id}/availabilities/confirm-bulk")
async def avail_confirm_bulk(event_id: str, body: BulkConfirm, user: dict = Depends(require_admin)):
    event = await db.events.find_one(oq(user, id=event_id), {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Evento non trovato")
    await _assert_event_operational(user["org_id"], event_id)
    org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0}) or {}
    confirmed, emailed = 0, 0
    for aid in (body.ids or []):
        a = await db.availabilities.find_one({"org_id": user["org_id"], "evento_id": event_id, "id": aid}, {"_id": 0})
        if not a or a.get("stato") == "confermata":
            continue
        e = await _confirm_availability(a, event, org.get("nome"), user)
        confirmed += 1
        emailed += 1 if e else 0
    return {"confirmed": confirmed, "emailed": emailed}


@api.post("/brevo/availability-list/ensure")
async def brevo_avail_list_ensure(user: dict = Depends(require_superadmin)):
    """Crea/verifica la lista unica «CRMEvent · Disponibilità eventi» via API e persiste il List ID.
    Idempotente: se esiste già riusa l'ID salvato. Nessun duplicato."""
    if not brevo_client.is_configured():
        raise HTTPException(status_code=400, detail="Brevo non configurato in questo ambiente (disponibile in produzione).")
    async with brevo_client.BrevoClient() as c:
        list_id = await _ensure_avail_list(c)
        contacts = None
        try:
            detail = await c.get_list(list_id)
            if isinstance(detail, dict):
                contacts = detail.get("totalSubscribers")
                if contacts is None:
                    contacts = detail.get("uniqueSubscribers")
        except Exception:
            contacts = None
    return {"list": {"id": list_id, "name": AVAIL_LIST_NAME, "contacts": contacts}}


class AvailTplActivate(BaseModel):
    kind: str = "all"


@api.post("/brevo/availability-templates/activate")
async def brevo_avail_templates_activate(body: AvailTplActivate, user: dict = Depends(require_superadmin)):
    """Attiva in Brevo (Bozza -> Attivo) i template master via API (PUT /smtp/templates/{id} isActive=true).
    Attivazione REALE su Brevo, nessuna forzatura dello stato nel DB CRMEvent. Idempotente."""
    if not brevo_client.is_configured():
        raise HTTPException(status_code=400, detail="Brevo non configurato in questo ambiente (disponibile in produzione).")
    want = {"disponibilita": [AVAIL_TPL_CONFERMA_DISP, AVAIL_TPL_CONFERMA_DISP_EN],
            "conferma": [AVAIL_TPL_CONFERMA_PART, AVAIL_TPL_CONFERMA_PART_EN]}.get(
                body.kind, [AVAIL_TPL_CONFERMA_DISP, AVAIL_TPL_CONFERMA_PART,
                            AVAIL_TPL_CONFERMA_DISP_EN, AVAIL_TPL_CONFERMA_PART_EN])
    out = []
    async with brevo_client.BrevoClient() as c:
        tpls = await c.get_templates()
        for name in want:
            t = next((x for x in tpls if (x.get("name") or "").strip().lower() == name.lower()), None)
            if not t:
                out.append({"name": name, "template_id": None, "activated": False, "error": "non trovato"})
                continue
            if t.get("isActive"):
                out.append({"name": name, "template_id": t.get("id"), "activated": True, "already": True})
                continue
            await c.activate_template(t.get("id"))
            out.append({"name": name, "template_id": t.get("id"), "activated": True})
    return {"templates": out}


@api.post("/brevo/create-availability-templates")
async def brevo_create_avail_templates(user: dict = Depends(require_superadmin)):
    """Create the two availability email templates as DRAFTS (isActive=false). Never sends.
    Anti-duplicato: se i due master esistono già, riusa i Template ID esistenti."""
    if not brevo_client.is_configured():
        raise HTTPException(status_code=400, detail="BREVO_API_KEY non configurata")
    try:
        async with brevo_client.BrevoClient() as c:
            senders = await c.senders()
            verified = [s for s in senders if s.get("active")]
            pref = next((s for s in verified if "crmevent" in (s.get("email") or "").lower()), None) or (verified[0] if verified else None)
            if not pref:
                raise HTTPException(status_code=400, detail="Nessun mittente verificato in Brevo.")
            sender = {"name": "CRMEvent", "email": pref["email"]}
            tpls = await c.get_templates()
            out = []
            for name, subject, kind, lang in [
                (AVAIL_TPL_CONFERMA_DISP, AVAIL_TPL_SUBJECT["it"]["disponibilita"], "disponibilita", "it"),
                (AVAIL_TPL_CONFERMA_PART, AVAIL_TPL_SUBJECT["it"]["conferma"], "conferma", "it"),
                (AVAIL_TPL_CONFERMA_DISP_EN, AVAIL_TPL_SUBJECT["en"]["disponibilita"], "disponibilita", "en"),
                (AVAIL_TPL_CONFERMA_PART_EN, AVAIL_TPL_SUBJECT["en"]["conferma"], "conferma", "en"),
            ]:
                ex = next((t for t in tpls if (t.get("name") or "").strip().lower() == name.lower()), None)
                if ex:
                    out.append({"name": name, "template_id": ex.get("id"), "created": False})
                    continue
                res = await c.create_email_template(name, subject, _avail_email_html(kind, lang), sender)
                out.append({"name": name, "template_id": res.get("id"), "created": True})
            list_id = await _ensure_avail_list(c)
            return {"sender": sender, "templates": out, "is_active": False,
                    "list": {"id": list_id, "name": AVAIL_LIST_NAME}}
    except brevo_client.BrevoError as e:
        raise HTTPException(status_code=502, detail=f"Brevo: impossibile creare i template (HTTP {e.status})")


@api.get("/brevo/availability-templates")
async def brevo_avail_templates_list(user: dict = Depends(require_superadmin)):
    """Elenca i due template master (nome + Template ID + stato attivo + tipo + ultimo aggiornamento).
    Riservato al Super Admin. Nessuna copia per evento."""
    base = [{"name": AVAIL_TPL_CONFERMA_DISP, "kind": "disponibilita", "lang": "it", "type_label": "Disponibilità · IT"},
            {"name": AVAIL_TPL_CONFERMA_PART, "kind": "conferma", "lang": "it", "type_label": "Conferma · IT"},
            {"name": AVAIL_TPL_CONFERMA_DISP_EN, "kind": "disponibilita", "lang": "en", "type_label": "Availability · EN"},
            {"name": AVAIL_TPL_CONFERMA_PART_EN, "kind": "conferma", "lang": "en", "type_label": "Confirmation · EN"}]
    cfg = await db.brevo_config.find_one({"key": "availability"}, {"_id": 0}) or {}
    lst = {"id": cfg.get("list_id"), "name": cfg.get("list_name") or AVAIL_LIST_NAME, "contacts": None}
    succ = await db.brevo_sync_log.find_one({"availability_id": {"$ne": None}, "status": {"$in": ["sent", "synced"]}},
                                            {"_id": 0}, sort=[("created_at", -1)])
    errdoc = await db.brevo_sync_log.find_one({"availability_id": {"$ne": None}, "status": "error"},
                                              {"_id": 0}, sort=[("created_at", -1)])
    lst["last_sync"] = succ.get("created_at") if succ else None
    if errdoc and (not succ or (errdoc.get("created_at") or "") > (succ.get("created_at") or "")):
        lst["last_error"] = {"error": errdoc.get("error") or "Errore di sincronizzazione", "at": errdoc.get("created_at")}
    else:
        lst["last_error"] = None
    if not brevo_client.is_configured():
        return {"configured": False, "enabled": _brevo_avail_enabled(), "list": lst,
                "templates": [{**b, "template_id": None, "is_active": None, "updated_at": None} for b in base]}
    out = []
    async with brevo_client.BrevoClient() as c:
        tpls = await c.get_templates()
        for b in base:
            t = next((x for x in tpls if (x.get("name") or "").strip().lower() == b["name"].lower()), None)
            out.append({**b, "template_id": t.get("id") if t else None,
                        "is_active": t.get("isActive") if t else None,
                        "updated_at": (t.get("modifiedAt") or t.get("createdAt")) if t else None})
        if lst.get("id"):
            try:
                detail = await c.get_list(lst["id"])
                if isinstance(detail, dict):
                    lst["contacts"] = detail.get("totalSubscribers")
                    if lst["contacts"] is None:
                        lst["contacts"] = detail.get("uniqueSubscribers")
            except Exception:
                lst["contacts"] = None
    return {"configured": True, "enabled": _brevo_avail_enabled(), "list": lst, "templates": out}


@api.get("/brevo/availability-test-events")
async def brevo_avail_test_events(user: dict = Depends(require_superadmin)):
    """Eventi appartenenti a Organizzazioni di tipo Test, per l'invio di email di prova."""
    test_orgs = await db.organizations.find({"type": "test"}, {"_id": 0, "id": 1, "nome": 1}).to_list(500)
    org_map = {o["id"]: o.get("nome") for o in test_orgs}
    if not org_map:
        return {"events": []}
    evs = await db.events.find({"org_id": {"$in": list(org_map.keys())}}, {"_id": 0}).to_list(1000)
    out = [{"id": e["id"], "nome": e.get("nome"), "org_id": e.get("org_id"),
            "org_nome": org_map.get(e.get("org_id")), "data_inizio": e.get("data_inizio"),
            "localita": e.get("localita") or e.get("citta"), "has_logo": bool(e.get("logo_url"))}
           for e in evs]
    out.sort(key=lambda x: (x.get("org_nome") or "", x.get("nome") or ""))
    return {"events": out}


class AvailTestEmail(BaseModel):
    event_id: str
    kind: str = "disponibilita"
    to_email: EmailStr
    lang: Optional[str] = "it"


@api.post("/brevo/availability-test-email")
async def brevo_avail_test_email(body: AvailTestEmail, user: dict = Depends(require_superadmin)):
    """Invia una email di PROVA (manuale, Super Admin) del template master indicato, usando i dati reali
    di un Evento di un'Organizzazione Test (logo incluso). Non attiva alcun automatismo e non dipende
    da BREVO_AVAILABILITY_ENABLED. Usa l'HTML master inline (indipendente dallo stato attivo/bozza del
    template). La BREVO_API_KEY non è mai esposta."""
    if not brevo_client.is_configured():
        return {"ok": False, "configured": False,
                "message": "Brevo non configurato in questo ambiente. L'invio reale è disponibile in produzione."}
    kind = "conferma" if body.kind == "conferma" else "disponibilita"
    event = await db.events.find_one({"id": body.event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Evento non trovato")
    org = await db.organizations.find_one({"id": event.get("org_id")}, {"_id": 0}) or {}
    if org.get("type") != "test":
        raise HTTPException(status_code=400, detail="L'invio di prova è consentito solo su Eventi di Organizzazioni di tipo Test.")
    params = _avail_email_params({"nome": "Mario", "cognome": "Rossi"}, event, org, _event_logo_url(event))
    lang = "en" if (body.lang or "").lower().startswith("en") else "it"
    html = _avail_email_html(kind, lang)
    subject = AVAIL_TPL_SUBJECT[lang][kind]
    for k, v in params.items():
        token = "{{params." + k + "}}"
        html = html.replace(token, str(v or ""))
        subject = subject.replace(token, str(v or ""))
    try:
        async with brevo_client.BrevoClient() as c:
            senders = await c.senders()
            verified = [s for s in senders if s.get("active")]
            pref = next((s for s in verified if "crmevent" in (s.get("email") or "").lower()), None) or (verified[0] if verified else None)
            if not pref:
                raise HTTPException(status_code=400, detail="Nessun mittente verificato in Brevo.")
            sender = {"name": "CRMEvent", "email": pref["email"]}
            res = await c._req("POST", "/smtp/email", json={
                "to": [{"email": str(body.to_email), "name": "Mario Rossi"}],
                "subject": subject, "htmlContent": html, "sender": sender})
        mid = res.get("messageId") if isinstance(res, dict) else None
        return {"ok": True, "configured": True, "message": f"Email di test inviata a {body.to_email}",
                "messageId": mid, "sender": sender["email"], "event": event.get("nome"),
                "kind": kind, "lang": lang, "logo": bool(event.get("logo_url"))}
    except brevo_client.BrevoError as e:
        raise HTTPException(status_code=502, detail=f"Brevo: invio non riuscito (HTTP {e.status})")


@api.get("/brevo/availability-template-preview")
async def brevo_avail_template_preview(event_id: str, kind: str = "disponibilita", lang: str = "it", request: Request = None, user: dict = Depends(require_admin)):
    """Anteprima HTML reale del template master con i dati dinamici dell'Evento indicato."""
    event = await db.events.find_one(oq(user, id=event_id), {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Evento non trovato")
    org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0}) or {}
    base = str(request.base_url).rstrip("/") if request else PUBLIC_SITE_URL
    params = _avail_email_params({"nome": "Mario", "cognome": "Rossi"}, event, org, _event_logo_url(event, base))
    lang_code = "en" if (lang or "").lower().startswith("en") else "it"
    html = _avail_email_html("conferma" if kind == "conferma" else "disponibilita", lang_code)
    for k, v in params.items():
        html = html.replace("{{params." + k + "}}", str(v or ""))
    return Response(content=html, media_type="text/html; charset=utf-8")


@api.get("/public/event-logo/{event_id}")
async def pub_event_logo(event_id: str):
    """Logo pubblico dell'Evento (immagine soltanto) per le email Brevo. Fallback: logo CRMEvent."""
    fallback = RedirectResponse(f"{PUBLIC_SITE_URL}/logo-crmevent-dark.png?v=5")
    event = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not event or not event.get("logo_url"):
        return fallback
    fid = (event["logo_url"] or "").rstrip("/").split("/")[-1]
    rec = await db.files.find_one({"$or": [{"id": fid}, {"public_token": fid}], "is_deleted": False}, {"_id": 0})
    if not rec:
        return fallback
    try:
        data, ctype = await _read_file_rec(rec)
        return Response(content=data, media_type=rec.get("content_type", ctype))
    except Exception:
        return fallback


# ---- Public (no login) ----
@api.get("/public/availability/{code}")
async def pub_avail_info(code: str):
    link = await db.avail_links.find_one({"code": code}, {"_id": 0})
    if not link:
        raise HTTPException(status_code=404, detail="Link non valido")
    event = await db.events.find_one({"id": link["evento_id"], "org_id": link["org_id"]}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Evento non trovato")
    base = {"nome": event.get("nome"), "data_inizio": event.get("data_inizio"),
            "data_fine": event.get("data_fine"), "localita": event.get("localita") or event.get("citta"),
            "has_logo": bool(event.get("logo_url")),
            "data_inizio_allestimento": event.get("data_inizio_allestimento"),
            "data_fine_disallestimento": event.get("data_fine_disallestimento")}
    if not link.get("active"):
        return {"active": False, "event": base}
    settings = await db.settings.find_one({"id": link["org_id"]}, {"_id": 0}) or {}
    attivita = settings.get("ruoli_staff") or default_settings()["ruoli_staff"]
    return {"active": True, "event": base, "days": _avail_days(event),
            "has_allestimento": bool(event.get("data_inizio_allestimento")),
            "has_disallestimento": bool(event.get("data_fine_disallestimento")),
            "attivita_options": attivita}


@api.get("/public/availability/{code}/logo")
async def pub_avail_logo(code: str):
    link = await db.avail_links.find_one({"code": code}, {"_id": 0})
    if not link:
        raise HTTPException(status_code=404, detail="Link non valido")
    event = await db.events.find_one({"id": link["evento_id"], "org_id": link["org_id"]}, {"_id": 0})
    if not event or not event.get("logo_url"):
        raise HTTPException(status_code=404, detail="Logo non disponibile")
    fid = (event["logo_url"] or "").rstrip("/").split("/")[-1]
    rec = await db.files.find_one({"$or": [{"id": fid}, {"public_token": fid}], "is_deleted": False}, {"_id": 0})
    if not rec or rec.get("org_id") not in (None, link["org_id"]):
        raise HTTPException(status_code=404, detail="Logo non disponibile")
    data, ctype = await _read_file_rec(rec)
    return Response(content=data, media_type=rec.get("content_type", ctype))


class PubAvailIn(BaseModel):
    nome: str
    cognome: str
    cellulare: str
    email: EmailStr
    codice_fiscale: Optional[str] = None
    data_nascita: Optional[str] = None
    days: List[dict] = []
    preferenza_attivita: Optional[str] = None
    preferenza_altro: Optional[str] = None
    privacy: bool = False
    marketing_consent: bool = False
    lang: Optional[str] = None


@api.post("/public/availability/{code}")
async def pub_avail_submit(code: str, body: PubAvailIn, request: Request):
    if not _avail_rate_ok(f"ip:{_client_ip(request)}", max_calls=6, window=60):
        raise HTTPException(status_code=429, detail="Troppe richieste. Riprova tra qualche istante.")
    link = await db.avail_links.find_one({"code": code}, {"_id": 0})
    if not link or not link.get("active"):
        raise HTTPException(status_code=410, detail="La raccolta delle disponibilità per questo evento è terminata.")
    event = await db.events.find_one({"id": link["evento_id"], "org_id": link["org_id"]}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Evento non trovato")
    if not body.privacy:
        raise HTTPException(status_code=400, detail="È necessario prendere visione della Privacy Policy")
    if not all((getattr(body, f) or "").strip() for f in ("nome", "cognome", "cellulare")):
        raise HTTPException(status_code=400, detail="Compila tutti i campi obbligatori")
    cf_norm = _cf_normalize(body.codice_fiscale) if body.codice_fiscale else ""
    if cf_norm:
        if not _cf_valid(cf_norm):
            raise HTTPException(status_code=400, detail="Codice Fiscale non valido")
        birth = _cf_birthdate(cf_norm)
        if not birth:
            raise HTTPException(status_code=400, detail="Codice Fiscale non valido: data di nascita non ricavabile")
    else:
        birth = (body.data_nascita or "").strip()[:10]
        if not birth:
            raise HTTPException(status_code=400, detail="Inserisci il Codice Fiscale oppure la Data di nascita")
    day_meta = {d["date"]: d["fase"] for d in _avail_days(event)}
    days_clean = []
    for d in (body.days or []):
        if not (d.get("date") and d.get("disponibile")):
            continue
        if d["date"] not in day_meta:
            continue
        days_clean.append({"date": d["date"], "fase": day_meta[d["date"]],
                           "dalle": (d.get("dalle") or "").strip() or None,
                           "alle": (d.get("alle") or "").strip() or None})
    if not days_clean:
        raise HTTPException(status_code=400, detail="Seleziona almeno una giornata di disponibilità")
    org_id = link["org_id"]
    email = (body.email or "").strip().lower()
    raw_cell = (body.cellulare or "").strip()
    cell = _norm_phone(raw_cell) or raw_cell
    submitted = {"nome": TN.person_name(body.nome.strip()), "cognome": TN.person_name(body.cognome.strip()), "email": email,
                 "cellulare": cell, "data_nascita": birth, "codice_fiscale": cf_norm or None}
    person = await db.persons.find_one({"org_id": org_id, "email": email}, {"_id": 0}) if email else None
    if not person and cell:
        person = await db.persons.find_one({"org_id": org_id, "cellulare": cell}, {"_id": 0})
    if not person and cf_norm:
        person = await db.persons.find_one({"org_id": org_id, "codice_fiscale": cf_norm}, {"_id": 0})
    await SAAS["check_people"](org_id, (person or {}).get("id"), public=True)
    mismatch = {}
    if person:
        fill = {}
        for k in ("email", "cellulare", "data_nascita", "cognome", "codice_fiscale"):
            cur, new = person.get(k), submitted.get(k)
            if new and not cur:
                fill[k] = new
            elif new and cur and str(cur).strip().lower() != str(new).strip().lower():
                mismatch[k] = {"attuale": cur, "inviato": new}
        if fill:
            await db.persons.update_one({"id": person["id"], "org_id": org_id}, {"$set": {**fill, "updated_at": now_iso()}})
        pid = person["id"]
    else:
        pdoc = await _create("persons", {"org_id": org_id, "nome": submitted["nome"], "cognome": submitted["cognome"],
                                         "email": email or None, "cellulare": cell or None,
                                         "data_nascita": submitted["data_nascita"], "codice_fiscale": cf_norm or None,
                                         "tag": ["disponibilita"],
                                         "note": "Inserito automaticamente dalla raccolta disponibilità pubblica"})
        pid = pdoc["id"]
    now = now_iso()
    lang = "en" if (body.lang or "").lower().startswith("en") else "it"
    mk = bool(body.marketing_consent)
    mk_fields = {"marketing_consent": mk,
                 "marketing_consent_ts": now if mk else None,
                 "marketing_source": "raccolta_disponibilita_pubblica" if mk else None}
    existing = await db.availabilities.find_one({"org_id": org_id, "evento_id": event["id"], "persona_id": pid}, {"_id": 0})
    if existing:
        upd = {"days": days_clean, "preferenza_attivita": body.preferenza_attivita or None,
               "preferenza_altro": (body.preferenza_altro or "").strip() or None,
               "submitted": submitted, "privacy_accepted": True, "privacy_ts": now,
               "ip": _client_ip(request), "user_agent": (request.headers.get("user-agent") or "")[:300],
               "compilation_lang": lang, "updated_at": now, **mk_fields}
        if mismatch:
            upd["mismatch"] = {**(existing.get("mismatch") or {}), **mismatch}
            upd["has_mismatch"] = True
        await db.availabilities.update_one({"org_id": org_id, "id": existing["id"]}, {"$set": upd})
        av_id = existing["id"]
    else:
        av_id = new_id()
        await db.availabilities.insert_one({
            "id": av_id, "org_id": org_id, "evento_id": event["id"], "persona_id": pid,
            "nome": submitted["nome"], "cognome": submitted["cognome"], "email": email or None,
            "cellulare": cell or None, "data_nascita": submitted["data_nascita"],
            "ruolo_evento": "da_definire", "stato": "nuova",
            "preferenza_attivita": body.preferenza_attivita or None,
            "preferenza_altro": (body.preferenza_altro or "").strip() or None,
            "days": days_clean, "submitted": submitted,
            "mismatch": mismatch or None, "has_mismatch": bool(mismatch),
            "privacy_accepted": True, "privacy_ts": now, "ip": _client_ip(request),
            "user_agent": (request.headers.get("user-agent") or "")[:300], "code": code,
            "compilation_lang": lang,
            "brevo_status": "pending", "created_at": now, "updated_at": now, **mk_fields})
    # Brevo sync (best-effort, gated): CRMEvent save has priority and is already committed above.
    try:
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0}) or {}
        av_final = await db.availabilities.find_one({"org_id": org_id, "id": av_id}, {"_id": 0})
        tpl = None if av_final.get("availability_email_sent_at") else AVAIL_TPL_CONFERMA_DISP
        res = await _brevo_avail("submit", av_final, event, org.get("nome"), send_template=tpl)
        setf = {"brevo_status": res["status"]}
        if res.get("sent"):
            setf["availability_email_sent_at"] = now
        await db.availabilities.update_one({"org_id": org_id, "id": av_id}, {"$set": setf})
    except Exception as e:
        logger.error(f"brevo avail submit sync failed: {e}")
    return {"ok": True, "event_nome": event.get("nome")}


# ==================== FASE 2 — Modello commerciale per-evento + Listino dinamico ====================
# STEP 1-3 (modello dati, listino DB, Super Admin "Piani e prezzi"). NESSUNA sync Stripe qui.
PRICING_PLANS_LIST = ["starter", "professional", "premium"]
PRICING_TIERS = ["small", "large"]
PRICING_VAT_RATE = 22.0
PRICING_SEED = {
    ("starter", "small"): 49.0, ("professional", "small"): 99.0, ("premium", "small"): 199.0,
    ("starter", "large"): 99.0, ("professional", "large"): 149.0, ("premium", "large"): 199.0,
}
PLAN_RANK = {"free": 0, "starter": 1, "professional": 2, "premium": 3}
PLAN_LABEL = {"starter": "Starter", "professional": "Professional", "premium": "Premium"}
TIER_LABEL = {"small": "Fino a 3 eventi/anno", "large": "Più di 3 eventi/anno"}


def _gross(net: float) -> float:
    return round(float(net) * (1 + PRICING_VAT_RATE / 100.0), 2)


def compute_tier(event_count: int) -> str:
    """Fascia in base al n° eventi nello stesso anno solare: 1-3 → small, dal 4° → large."""
    return "large" if event_count >= 4 else "small"


async def _events_in_year(org_id: str, year: int) -> int:
    return await db.events.count_documents({"org_id": org_id, "data_inizio": {"$regex": f"^{year}-"}})


def _event_effective_plan(event: dict, sub_summary: dict) -> str:
    """Piano effettivo di un evento: durante il trial tutto PREMIUM; altrimenti l'entitlement dell'evento."""
    if sub_summary.get("status") == "trial" and sub_summary.get("access") == "full":
        return "premium"
    ent = (event or {}).get("entitlement") or {}
    return ent.get("plan") or "free"


async def _org_best_plan(org_id: str, sub_summary: dict, year: int) -> str:
    """Gating org-level: miglior piano tra gli eventi ATTIVI dell'anno corrente (trial → premium)."""
    if sub_summary.get("effective_plan") == "premium" and sub_summary.get("status") in ("trial", "active"):
        return "premium"
    best = "free"
    cur = db.events.find({"org_id": org_id, "data_inizio": {"$regex": f"^{year}-"}}, {"_id": 0, "entitlement": 1})
    async for e in cur:
        p = (e.get("entitlement") or {}).get("plan") or "free"
        if PLAN_RANK.get(p, 0) > PLAN_RANK.get(best, 0):
            best = p
    return best


async def _ensure_pricing_seeded():
    """Popola i 6 prezzi iniziali del listino se mancanti (idempotente)."""
    for (plan, fascia), net in PRICING_SEED.items():
        if not await db.pricing_plans.find_one({"plan": plan, "fascia": fascia}):
            await _create("pricing_plans", {
                "plan": plan, "fascia": fascia, "net": net, "vat_rate": PRICING_VAT_RATE,
                "gross": _gross(net), "currency": "EUR", "status": "active", "version": 1,
                "stripe_product_id": None, "stripe_price_id": None, "updated_by": None,
            })


def _pricing_sort_key(p: dict):
    return (PRICING_PLANS_LIST.index(p["plan"]) if p["plan"] in PRICING_PLANS_LIST else 9,
            PRICING_TIERS.index(p["fascia"]) if p["fascia"] in PRICING_TIERS else 9)


@api.get("/pricing")
async def public_pricing():
    """Listino pubblico attivo (per /prezzi e Checkout — fonte di verità DB, nessun hardcoding)."""
    await _ensure_pricing_seeded()
    rows = await db.pricing_plans.find({"status": "active"}, {"_id": 0}).to_list(50)
    rows.sort(key=_pricing_sort_key)
    return {"currency": "EUR", "vat_rate": PRICING_VAT_RATE, "plans": rows}


@api.get("/platform/pricing")
async def platform_pricing(admin: dict = Depends(require_superadmin)):
    await _ensure_pricing_seeded()
    rows = await db.pricing_plans.find({}, {"_id": 0}).to_list(50)
    rows.sort(key=_pricing_sort_key)
    for r in rows:
        r["plan_label"] = PLAN_LABEL.get(r["plan"], r["plan"])
        r["tier_label"] = TIER_LABEL.get(r["fascia"], r["fascia"])
    return {"currency": "EUR", "vat_rate": PRICING_VAT_RATE, "plans": rows}


@api.get("/platform/pricing/history")
async def platform_pricing_history(admin: dict = Depends(require_superadmin)):
    rows = await db.pricing_history.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return rows


# ======================================================================
# SISTEMA A CREDITI — FASE A (fondamenta). Nessun consumo reale attivo.
# Saldo a livello di ORGANIZZAZIONE (condiviso), ledger immutabile,
# catalogo servizi configurabile dal Super Admin, no saldo negativo, idempotenza.
# ======================================================================
SIGNUP_BONUS_CREDITS = 100
CREDIT_UNIT_EUR = 0.50  # valore economico di 1 credito
DEFAULT_LOW_BALANCE_THRESHOLD = 20

# key, name, category, pricing_mode (flat|per_unit|None), unit_label
CREDIT_SERVICES_SEED = [
    ("ai_assistant", "Assistente IA", "ai", "flat", "richiesta"),
    ("ai_content", "Generazione contenuti", "ai", "flat", "richiesta"),
    ("ai_briefing", "Generazione briefing", "ai", "flat", "richiesta"),
    ("ai_analysis", "Analisi completa evento", "ai", "flat", "richiesta"),
    ("ai_checklist", "Generazione checklist / piano operativo", "ai", "flat", "operazione"),
    ("image_generation", "Generazione immagini", "image", "per_unit", "immagine"),
    ("automation_run", "Automazioni", "automation", "flat", "esecuzione"),
    ("newsletter_email", "Newsletter / email", "communication", "per_unit", "destinatario"),
    ("google_calendar", "Google Calendar", "integration", None, None),
    ("video_support", "Assistenza in videochiamata", "support", "flat", "sessione"),
    ("whatsapp_send", "WhatsApp", "communication", "per_unit", "messaggio"),
    ("sms_send", "SMS (futuro)", "communication", "per_unit", "messaggio"),
    ("event_active_period", "Attivazione evento", "event", "flat", "attivazione"),
    ("event_activation", "Attivazione evento", "event", "flat", "attivazione"),
    ("event_maintenance", "Mantenimento evento", "event", "flat", "mese"),
    ("event_pipeline_pro", "Pipeline Evento Pro", "pro", "flat", "evento"),
]
# FASE E: valori iniziali di consumo (applicati UNA SOLA VOLTA quando il servizio non è ancora
# configurato, così le modifiche del Super Admin non vengono mai sovrascritte). NON hardcoded a runtime:
# _credit_service_cost legge sempre dal catalogo DB.
FASE_E_INITIAL = {
    "ai_assistant": {"name": "Assistente IA", "pricing_mode": "flat", "unit_label": "richiesta", "unit_cost": 1},
    "ai_content": {"name": "Generazione contenuti", "pricing_mode": "flat", "unit_label": "richiesta", "unit_cost": 2},
    "ai_briefing": {"name": "Generazione briefing", "pricing_mode": "flat", "unit_label": "richiesta", "unit_cost": 3},
    "ai_analysis": {"name": "Analisi completa evento", "pricing_mode": "flat", "unit_label": "richiesta", "unit_cost": 5},
    "ai_checklist": {"name": "Generazione checklist / piano operativo", "pricing_mode": "flat", "unit_label": "operazione", "unit_cost": 5},
    "image_generation": {"name": "Generazione immagini", "pricing_mode": "per_unit", "unit_label": "immagine", "unit_cost": 5},
    "event_active_period": {"name": "Attivazione evento", "pricing_mode": "flat", "unit_label": "attivazione", "unit_cost": 20, "period_days": None},
    "event_activation": {"name": "Attivazione evento", "pricing_mode": "flat", "unit_label": "attivazione", "unit_cost": 30, "period_days": None},
    "event_maintenance": {"name": "Mantenimento evento", "pricing_mode": "flat", "unit_label": "mese", "unit_cost": 20, "period_days": 30},
    "event_pipeline_pro": {"name": "Pipeline Evento Pro", "pricing_mode": "flat", "unit_label": "evento", "unit_cost": 20, "period_days": None,
                           "description": "Attiva la Pipeline di preparazione dell'evento: autorizzazioni, fornitori, materiali, staff, sicurezza, iscrizioni e tutte le attività necessarie prima dell'evento."},
}
_credits_indexes_done = False

# Servizi realmente collegati a un addebito nel codice (gli altri restano nascosti nel catalogo Super Admin).
LINKED_CREDIT_SERVICES = {"ai_assistant", "ai_briefing", "event_pipeline_pro", "google_calendar", "video_support"}
DISMISSED_EVENT_SERVICES = {"event_active_period", "event_activation", "event_maintenance"}
# Descrizioni informative (verificate sul codice di addebito). Applicate una sola volta: poi modificabili dal Super Admin.
CREDIT_SERVICE_DESCRIPTIONS = {
    "ai_assistant": "Risponde con l'AI alle domande sull'uso di CRMEvent e sui dati della tua organizzazione. Il costo viene scalato per ogni domanda che riceve una risposta utile. Se l'assistente non sa rispondere, oppure la richiesta è un suggerimento di nuova funzione, non viene scalato nulla.",
    "ai_briefing": "Pubblica il briefing operativo dell'evento, generato automaticamente con i dati aggiornati di staff, team, turni, ospitalità e pasti. Il costo viene scalato una sola volta per evento, alla prima pubblicazione. Dopo l'addebito il briefing dello stesso evento può essere aggiornato e ripubblicato in nuove versioni senza ulteriori addebiti.",
    "event_activation": "Rende operativo un evento: staff, team, turni, ospitalità, briefing e tutte le funzioni operative. Il costo viene scalato una sola volta per evento, al momento dell'attivazione, e comprende il primo mese di utilizzo. Dal mese successivo si applica il Mantenimento evento.",
    "event_maintenance": "Mantiene operativo un evento già attivato. Il costo viene scalato in automatico ogni mese di calendario a partire dalla data di attivazione, fino alla data dell'evento: il mese che arriva fino all'evento non viene addebitato di nuovo. Se i crediti non sono sufficienti l'evento viene sospeso; riattivandolo si paga un solo mese di mantenimento e il ciclo riparte.",
    "event_pipeline_pro": "Attiva per un evento la Pipeline di preparazione: autorizzazioni, fornitori, materiali, staff, sicurezza, iscrizioni e tutte le attività da svolgere prima dell'evento. Il costo viene scalato una sola volta per evento, anche quando la Pipeline viene copiata da un'edizione precedente. Dopo l'attivazione modelli, attività e aggiornamenti dello stesso evento sono compresi.",
    "video_support": "Sessione di assistenza dedicata di 30 minuti tramite Google Meet, con possibilità di condividere lo schermo per ricevere supporto nell'utilizzo di CRMEvent.",
    "google_calendar": "Collega CRMEvent a Google Calendar per sincronizzare Attività e Follow-up con il calendario. Il costo viene scalato una sola volta per organizzazione, alla prima attivazione. Dopo l'attivazione la sincronizzazione è compresa senza ulteriori addebiti.",
}


async def _ensure_credits_setup():
    """Crea indici e semina il catalogo servizi (idempotente, lazy)."""
    global _credits_indexes_done
    if not _credits_indexes_done:
        try:
            await db.credit_ledger.create_index([("org_id", 1), ("created_at", -1)])
            await db.credit_ledger.create_index(
                [("org_id", 1), ("idempotency_key", 1)], unique=True,
                partialFilterExpression={"idempotency_key": {"$type": "string"}})
            await db.credit_services.create_index([("key", 1)], unique=True)
        except Exception:
            pass
        _credits_indexes_done = True
    for key, name, cat, mode, unit in CREDIT_SERVICES_SEED:
        if not await db.credit_services.find_one({"key": key}):
            await db.credit_services.insert_one({
                "id": new_id(), "key": key, "name": name, "category": cat,
                "pricing_mode": mode, "unit_label": unit, "unit_cost": None, "min_units": 1,
                "period_days": None, "active": False, "visible": True, "version": 1,
                "created_at": now_iso(), "updated_at": now_iso()})
    # FASE E: applica i costi iniziali SOLO ai servizi non ancora configurati (unit_cost is None).
    for key, cfg in FASE_E_INITIAL.items():
        svc = await db.credit_services.find_one({"key": key})
        if svc and svc.get("unit_cost") is None:
            await db.credit_services.update_one({"key": key}, {"$set": {
                "name": cfg["name"], "pricing_mode": cfg["pricing_mode"], "unit_label": cfg["unit_label"],
                "unit_cost": cfg["unit_cost"], "period_days": cfg.get("period_days"),
                "description": cfg.get("description"),
                "active": True, "consumo_active": True, "updated_at": now_iso()}})
    # FASE E.2b: il vecchio servizio unico 'event_active_period' è sostituito da due servizi distinti
    # event_activation (30, una tantum) + event_maintenance (20, mensile). Dismetti il vecchio.
    # Attivazione/mantenimento evento a crediti dismessi: eventi sempre operativi.
    await db.credit_services.update_many({"key": {"$in": list(DISMISSED_EVENT_SERVICES)}, "visible": {"$ne": False}}, {"$set": {
        "active": False, "consumo_active": False, "visible": False, "updated_at": now_iso()}})
    # Backfill del campo consumo_active (distinto da active=disponibilità). Retrocompat: se assente,
    # un servizio configurato+attivo consumava già -> consumo_active=True. Google Calendar: disponibile
    # ma consumo OFF (gratuito).
    for svc in await db.credit_services.find({"consumo_active": {"$exists": False}}, {"_id": 0}).to_list(200):
        if svc["key"] == "google_calendar":
            upd = {"active": True, "consumo_active": False}
        else:
            derived = bool(svc.get("active") and svc.get("unit_cost") is not None and svc.get("pricing_mode") is not None)
            upd = {"consumo_active": derived}
        upd["updated_at"] = now_iso()
        await db.credit_services.update_one({"key": svc["key"]}, {"$set": upd})
    # Catalogo semplificato (v2, una sola volta): descrizioni complete, Google Calendar a catalogo, briefing a evento.
    for key, text in CREDIT_SERVICE_DESCRIPTIONS.items():
        svc = await db.credit_services.find_one({"key": key, "desc_v2": {"$ne": True}}, {"_id": 0})
        if not svc:
            continue
        upd = {"description": text, "desc_v2": True, "updated_at": now_iso()}
        if key == "ai_assistant":
            upd["name"] = "Assistente CRMEvent"
        if key == "google_calendar" and svc.get("unit_cost") is None:
            upd.update({"unit_cost": GCAL_UNLOCK_COST, "pricing_mode": "flat", "unit_label": "organizzazione",
                        "active": True, "consumo_active": True})
        if key == "ai_briefing":
            upd.update({"unit_label": "evento", "active": True, "consumo_active": True})
            if svc.get("unit_cost") in (None, 3):
                upd["unit_cost"] = 30
        await db.credit_services.update_one({"key": key}, {"$set": upd})


async def _ensure_org_credits(org_id: str) -> dict:
    """Ritorna il sotto-documento credits dell'org, inizializzandolo a zero se assente.
    NB: NON accredita il bonus (quello è gestito da _grant_signup_bonus)."""
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "id": 1, "credits": 1})
    if org is None:
        raise HTTPException(status_code=404, detail="Organizzazione non trovata")
    c = org.get("credits")
    if not c:
        c = {"balance": 0, "reserved": 0, "lifetime_granted": 0, "lifetime_spent": 0,
             "signup_bonus_granted": False, "low_balance_threshold": DEFAULT_LOW_BALANCE_THRESHOLD,
             "low_balance_notified_at": None, "updated_at": now_iso()}
        await db.organizations.update_one(
            {"id": org_id, "$or": [{"credits": {"$exists": False}}, {"credits": None}]},
            {"$set": {"credits": c}})
    return c


async def _apply_credit_movement(org_id, amount, reason_code, type_, *, service_key=None,
                                 quantity=1, unit_cost=None, event_id=None, user_id=None,
                                 idempotency_key=None, note=None):
    """Applica un movimento crediti in modo atomico e immutabile.
    amount > 0 = accredito, amount < 0 = addebito. Blocca il saldo negativo.
    Idempotenza: se idempotency_key è già presente, non riapplica (claim-first)."""
    if amount < 0:
        return None  # sistema a crediti dismesso: nessun addebito
    from pymongo.errors import DuplicateKeyError
    if amount == 0:
        raise HTTPException(status_code=400, detail="Importo nullo non consentito")
    await _ensure_org_credits(org_id)

    ledger_id = None
    if idempotency_key:
        claim = {"id": new_id(), "org_id": org_id, "type": type_, "status": "pending",
                 "amount": amount, "balance_after": None, "reason_code": reason_code,
                 "service_key": service_key, "quantity": quantity, "unit_cost": unit_cost,
                 "event_id": event_id, "user_id": user_id, "idempotency_key": idempotency_key,
                 "note": note, "created_at": now_iso(), "settled_at": None}
        try:
            await db.credit_ledger.insert_one(claim)
            ledger_id = claim["id"]
        except DuplicateKeyError:
            existing = await db.credit_ledger.find_one(
                {"org_id": org_id, "idempotency_key": idempotency_key}, {"_id": 0})
            return existing

    if amount < 0:
        res = await db.organizations.update_one(
            {"id": org_id, "credits.balance": {"$gte": -amount}},
            {"$inc": {"credits.balance": amount, "credits.lifetime_spent": -amount},
             "$set": {"credits.updated_at": now_iso()}})
        if res.modified_count == 0:
            if ledger_id:
                await db.credit_ledger.delete_one({"id": ledger_id})
            org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "credits": 1})
            bal = (org.get("credits") or {}).get("balance", 0)
            raise HTTPException(status_code=402,
                                detail=f"Crediti insufficienti (saldo {bal}, richiesti {-amount})")
    else:
        await db.organizations.update_one(
            {"id": org_id},
            {"$inc": {"credits.balance": amount, "credits.lifetime_granted": amount},
             "$set": {"credits.updated_at": now_iso()}})

    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "credits": 1})
    bal_after = (org.get("credits") or {}).get("balance", 0)

    if ledger_id:
        await db.credit_ledger.update_one(
            {"id": ledger_id},
            {"$set": {"status": "committed", "balance_after": bal_after, "settled_at": now_iso()}})
        return await db.credit_ledger.find_one({"id": ledger_id}, {"_id": 0})

    doc = {"id": new_id(), "org_id": org_id, "type": type_, "status": "committed",
           "amount": amount, "balance_after": bal_after, "reason_code": reason_code,
           "service_key": service_key, "quantity": quantity, "unit_cost": unit_cost,
           "event_id": event_id, "user_id": user_id, "idempotency_key": None,
           "note": note, "created_at": now_iso(), "settled_at": now_iso()}
    await db.credit_ledger.insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}


async def _grant_signup_bonus(org_id: str, org_name: Optional[str] = None):
    """Accredita 100 crediti UNA SOLA VOLTA alla creazione dell'organizzazione."""
    await _ensure_credits_setup()
    await _ensure_org_credits(org_id)
    # Flag atomico anti doppio-bonus + idempotency_key sul movimento.
    res = await db.organizations.update_one(
        {"id": org_id, "credits.signup_bonus_granted": False},
        {"$set": {"credits.signup_bonus_granted": True}})
    if res.modified_count == 0:
        return  # bonus già assegnato
    await _apply_credit_movement(
        org_id, SIGNUP_BONUS_CREDITS, reason_code="signup_bonus", type_="grant",
        idempotency_key=f"signup_bonus:{org_id}", note="Bonus 100 crediti alla registrazione")


def _is_test_or_internal_org(o: dict) -> bool:
    """Org Test/Demo/interne o con nome chiaramente di prova: escluse dalla migrazione bonus."""
    t = (o.get("type") or "").lower()
    if t in ("test", "interna", "demo"):
        return True
    name = (o.get("nome") or "").lower()
    return any(k in name for k in ["test", "demo", "qa", "tab", "sandbox", "prova"])


async def _credits_migration_analysis():
    orgs = await db.organizations.find({}, {"_id": 0, "id": 1, "nome": 1, "type": 1, "status": 1, "credits": 1, "created_at": 1}).to_list(5000)
    eligible, excluded, already = [], [], []
    for o in orgs:
        c = o.get("credits") or {}
        granted = bool(c.get("signup_bonus_granted"))
        bal = c.get("balance", 0) or 0
        row = {"id": o["id"], "nome": o.get("nome"), "type": o.get("type"), "status": o.get("status"),
               "balance": bal, "signup_bonus_granted": granted,
               "projected_balance": bal if granted else bal + SIGNUP_BONUS_CREDITS}
        if granted:
            already.append(row)
        elif _is_test_or_internal_org(o):
            excluded.append(row)
        else:
            eligible.append(row)
    return {"bonus_amount": SIGNUP_BONUS_CREDITS, "total_orgs": len(orgs),
            "eligible_count": len(eligible), "excluded_count": len(excluded),
            "already_granted_count": len(already),
            "total_credits_to_grant": len(eligible) * SIGNUP_BONUS_CREDITS,
            "eligible": eligible, "excluded": excluded, "already_granted": already}


@api.get("/platform/credits/migration-dryrun")
async def credits_migration_dryrun(admin: dict = Depends(require_superadmin)):
    """DRY-RUN (sola lettura): chi riceverebbe il bonus, chi è escluso, saldi attuali e simulati.
    NON esegue alcuna scrittura."""
    return await _credits_migration_analysis()


class CreditsMigrateIn(BaseModel):
    confirm: bool = False
    exclude_ids: List[str] = []


@api.post("/platform/credits/migrate")
async def credits_migrate(body: CreditsMigrateIn, admin: dict = Depends(require_superadmin)):
    """Migrazione una tantum: +100 crediti alle org reali che non hanno mai ricevuto il bonus.
    Idempotente (signup_bonus_granted). Richiede conferma esplicita."""
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Conferma richiesta per eseguire la migrazione")
    analysis = await _credits_migration_analysis()
    granted = []
    for row in analysis["eligible"]:
        if row["id"] in (body.exclude_ids or []):
            continue
        await _grant_signup_bonus(row["id"], row.get("nome"))
        granted.append(row["id"])
    await record_audit(admin, "credits_migration_run", meta={"granted_count": len(granted), "excluded_ids": body.exclude_ids})
    return {"granted_count": len(granted), "granted_ids": granted, "bonus_amount": SIGNUP_BONUS_CREDITS}


# ---------------- API org-side (saldo + storico) ----------------
@api.get("/credits/balance")
async def credits_balance(user: dict = Depends(require_admin)):
    c = await _ensure_org_credits(user["org_id"])
    thr = c.get("low_balance_threshold", DEFAULT_LOW_BALANCE_THRESHOLD)
    return {"balance": c.get("balance", 0), "reserved": c.get("reserved", 0),
            "lifetime_granted": c.get("lifetime_granted", 0),
            "lifetime_spent": c.get("lifetime_spent", 0),
            "low_balance_threshold": thr, "low_balance": c.get("balance", 0) <= thr}


@api.get("/credits/ledger")
async def credits_ledger(user: dict = Depends(require_admin), limit: int = 50, skip: int = 0,
                         type: Optional[str] = None, event_id: Optional[str] = None):
    q = {"org_id": user["org_id"]}
    if type:
        q["type"] = type
    if event_id:
        q["event_id"] = event_id
    limit = max(1, min(limit, 200))
    rows = await db.credit_ledger.find(q, {"_id": 0}).sort("created_at", -1).skip(max(0, skip)).limit(limit).to_list(limit)
    total = await db.credit_ledger.count_documents(q)
    return {"items": rows, "total": total, "skip": skip, "limit": limit}


@api.get("/credits/services")
async def credits_services_public(user: dict = Depends(require_admin)):
    await _ensure_credits_setup()
    rows = await db.credit_services.find({"visible": True}, {"_id": 0}).to_list(100)
    return {"services": rows}


@api.get("/credits/service-costs")
async def credits_service_costs(user: dict = Depends(require_admin)):
    """Riepilogo costi per gli organizzatori: stessi servizi/descrizioni/costi del catalogo Super Admin."""
    await _ensure_credits_setup()
    rows = await db.credit_services.find({"key": {"$in": list(LINKED_CREDIT_SERVICES)}, "visible": {"$ne": False}},
                                         {"_id": 0, "key": 1, "name": 1, "description": 1, "unit_cost": 1, "active": 1, "consumo_active": 1}).to_list(100)
    # L'assistenza in videochiamata compare solo quando il Super Admin la attiva
    rows = [r for r in rows if r["key"] != "video_support" or (r.get("active") and r.get("consumo_active") and r.get("unit_cost") is not None)]
    rows.sort(key=lambda r: (r.get("name") or "").lower())
    return {"services": rows}


# ---------------- API Super Admin (catalogo + gestione org) ----------------
@api.get("/platform/credit-services")
async def platform_credit_services(admin: dict = Depends(require_superadmin)):
    await _ensure_credits_setup()
    rows = await db.credit_services.find({"key": {"$nin": list(DISMISSED_EVENT_SERVICES)}}, {"_id": 0}).to_list(100)
    return {"services": [{**r, "linked": r["key"] in LINKED_CREDIT_SERVICES} for r in rows]}


class CreditServiceUpdateIn(BaseModel):
    name: Optional[str] = None
    active: Optional[bool] = None
    consumo_active: Optional[bool] = None
    visible: Optional[bool] = None
    pricing_mode: Optional[str] = None
    unit_label: Optional[str] = None
    unit_cost: Optional[float] = None
    min_units: Optional[int] = None
    period_days: Optional[int] = None
    description: Optional[str] = None


@api.put("/platform/credit-services/{key}")
async def update_credit_service(key: str, body: CreditServiceUpdateIn, admin: dict = Depends(require_superadmin)):
    await _ensure_credits_setup()
    svc = await db.credit_services.find_one({"key": key}, {"_id": 0})
    if not svc:
        raise HTTPException(status_code=404, detail="Servizio non trovato")
    changes = {}
    if body.unit_cost is not None and (body.unit_cost < 0 or body.unit_cost != int(body.unit_cost)):
        raise HTTPException(status_code=400, detail="Il costo deve essere un numero intero di crediti (0 o superiore)")
    for f in ["name", "active", "consumo_active", "visible", "pricing_mode", "unit_label", "unit_cost", "min_units", "period_days", "description"]:
        v = getattr(body, f)
        if v is not None and v != svc.get(f):
            changes[f] = v
    if not changes:
        return svc
    for f, newv in changes.items():
        await db.credit_service_history.insert_one({
            "id": new_id(), "service_key": key, "field": f, "old_value": svc.get(f),
            "new_value": newv, "changed_by": admin.get("user_id"), "created_at": now_iso()})
    changes["version"] = svc.get("version", 1) + 1
    changes["updated_at"] = now_iso()
    await db.credit_services.update_one({"key": key}, {"$set": changes})
    await record_audit(admin, "credit_service_update", meta={"key": key, "changes": changes})
    return await db.credit_services.find_one({"key": key}, {"_id": 0})


@api.post("/platform/credit-services")
async def create_credit_service(body: dict, admin: dict = Depends(require_superadmin)):
    await _ensure_credits_setup()
    key = (body.get("key") or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="key obbligatoria")
    if await db.credit_services.find_one({"key": key}):
        raise HTTPException(status_code=400, detail="Servizio già esistente")
    doc = {"id": new_id(), "key": key, "name": body.get("name") or key,
           "category": body.get("category"), "pricing_mode": body.get("pricing_mode"),
           "unit_label": body.get("unit_label"), "unit_cost": body.get("unit_cost"),
           "min_units": body.get("min_units", 1), "active": bool(body.get("active", False)),
           "visible": bool(body.get("visible", True)), "version": 1,
           "created_at": now_iso(), "updated_at": now_iso()}
    await db.credit_services.insert_one(doc)
    await record_audit(admin, "credit_service_create", meta={"key": key})
    return {k: v for k, v in doc.items() if k != "_id"}


@api.get("/platform/credit-services/history")
async def credit_services_history(admin: dict = Depends(require_superadmin), key: Optional[str] = None):
    q = {} if not key else {"service_key": key}
    rows = await db.credit_service_history.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return rows


@api.get("/platform/orgs/{org_id}/credits")
async def platform_org_credits(org_id: str, admin: dict = Depends(require_superadmin), limit: int = 50):
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "nome": 1})
    if not org:
        raise HTTPException(status_code=404, detail="Organizzazione non trovata")
    c = await _ensure_org_credits(org_id)
    rows = await db.credit_ledger.find({"org_id": org_id}, {"_id": 0}).sort("created_at", -1).limit(max(1, min(limit, 200))).to_list(200)
    return {"org_id": org_id, "org_name": org.get("nome"), "credits": c, "ledger": rows}


class CreditAdjustIn(BaseModel):
    amount: int
    note: Optional[str] = None
    idempotency_key: Optional[str] = None


@api.post("/platform/orgs/{org_id}/credits/adjust")
async def platform_org_credits_adjust(org_id: str, body: CreditAdjustIn, admin: dict = Depends(require_superadmin)):
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "nome": 1})
    if not org:
        raise HTTPException(status_code=404, detail="Organizzazione non trovata")
    if body.amount == 0:
        raise HTTPException(status_code=400, detail="Importo non valido")
    mv = await _apply_credit_movement(
        org_id, int(body.amount), reason_code="manual_adjustment", type_="adjustment",
        user_id=admin.get("user_id"), idempotency_key=body.idempotency_key, note=body.note)
    await record_audit(admin, "credit_manual_adjustment", org_id=org_id, org_name=org.get("nome"),
                       meta={"amount": body.amount, "note": body.note})
    return {"ok": True, "movement": mv}


@api.get("/platform/orgs-overview")
async def platform_orgs_overview(admin: dict = Depends(require_superadmin)):
    """Elenco organizzazioni con referente Admin e situazione crediti, per la ricerca e la
    gestione del Super Admin. SOLA LETTURA: nessuna modifica a wallet/ledger."""
    orgs = await db.organizations.find({}, {"_id": 0}).sort("created_at", -1).to_list(5000)
    out = []
    for o in orgs:
        owner = await db.users.find_one({"user_id": o.get("owner_user_id")}, {"_id": 0, "password_hash": 0})
        c = o.get("credits") or {}
        out.append({
            "id": o["id"], "nome": o.get("nome"), "type": o.get("type", "cliente"),
            "status": o.get("status", "active"),
            "admin_name": (owner or {}).get("name"),
            "admin_email": (owner or {}).get("email"),
            "admin_phone": (owner or {}).get("telefono") or (owner or {}).get("phone"),
            "balance": c.get("balance", 0),
            "lifetime_spent": c.get("lifetime_spent", 0),
            "lifetime_granted": c.get("lifetime_granted", 0),
        })
    return {"organizations": out}


# ---------------- Catalogo RICARICHE (credit_packages) ----------------
# price, credits_base, credits_bonus, bonus_pct (display)
CREDIT_PACKAGES_SEED = [
    (20, 40, 0, 0), (50, 100, 0, 0), (100, 200, 20, 10),
    (200, 400, 60, 15), (500, 1000, 200, 20), (1000, 2000, 500, 25),
]


async def _ensure_credit_packages_seeded():
    try:
        await db.credit_packages.create_index([("sort", 1)])
    except Exception:
        pass
    if await db.credit_packages.count_documents({}) == 0:
        for i, (price, base, bonus, pct) in enumerate(CREDIT_PACKAGES_SEED):
            await db.credit_packages.insert_one({
                "id": new_id(), "price": price, "credits_base": base, "credits_bonus": bonus,
                "bonus_pct": pct, "credits_total": base + bonus, "active": True, "sort": i + 1,
                "badge": ("Più conveniente" if pct == 25 else (f"+{pct}%" if pct else None)),
                "highlight": pct == 20, "created_at": now_iso(), "updated_at": now_iso()})


@api.get("/credits/packages-public")
async def credits_packages_public_open():
    """Catalogo pubblico dei tagli attivi per la pagina /prezzi (nessuna autenticazione)."""
    await _ensure_credit_packages_seeded()
    rows = await db.credit_packages.find({"active": True}, {"_id": 0}).sort("sort", 1).to_list(100)
    return {"packages": rows, "credit_unit_eur": CREDIT_UNIT_EUR}


@api.get("/credits/packages")
async def credits_packages_public(user: dict = Depends(require_admin)):
    await _ensure_credit_packages_seeded()
    rows = await db.credit_packages.find({"active": True}, {"_id": 0}).sort("sort", 1).to_list(100)
    return {"packages": rows, "credit_unit_eur": CREDIT_UNIT_EUR}


@api.get("/platform/credit-packages")
async def platform_credit_packages(admin: dict = Depends(require_superadmin)):
    await _ensure_credit_packages_seeded()
    rows = await db.credit_packages.find({}, {"_id": 0}).sort("sort", 1).to_list(100)
    return {"packages": rows, "credit_unit_eur": CREDIT_UNIT_EUR}


class CreditPackageIn(BaseModel):
    price: Optional[float] = None
    credits_base: Optional[int] = None
    credits_bonus: Optional[int] = None
    bonus_pct: Optional[float] = None
    active: Optional[bool] = None
    sort: Optional[int] = None
    badge: Optional[str] = None
    highlight: Optional[bool] = None


@api.post("/platform/credit-packages")
async def create_credit_package(body: CreditPackageIn, admin: dict = Depends(require_superadmin)):
    await _ensure_credit_packages_seeded()
    base = body.credits_base or 0
    bonus = body.credits_bonus or 0
    doc = {"id": new_id(), "price": body.price or 0, "credits_base": base, "credits_bonus": bonus,
           "bonus_pct": body.bonus_pct or 0, "credits_total": base + bonus,
           "active": bool(body.active if body.active is not None else True),
           "sort": body.sort or 99, "badge": body.badge, "highlight": bool(body.highlight),
           "created_at": now_iso(), "updated_at": now_iso()}
    await db.credit_packages.insert_one(doc)
    await record_audit(admin, "credit_package_create", meta={"id": doc["id"], "price": doc["price"]})
    return {k: v for k, v in doc.items() if k != "_id"}


@api.put("/platform/credit-packages/{pid}")
async def update_credit_package(pid: str, body: CreditPackageIn, admin: dict = Depends(require_superadmin)):
    pkg = await db.credit_packages.find_one({"id": pid}, {"_id": 0})
    if not pkg:
        raise HTTPException(status_code=404, detail="Taglio non trovato")
    changes = {}
    for f in ["price", "credits_base", "credits_bonus", "bonus_pct", "active", "sort", "badge", "highlight"]:
        v = getattr(body, f)
        if v is not None and v != pkg.get(f):
            changes[f] = v
    if not changes:
        return pkg
    for f, newv in changes.items():
        await db.credit_package_history.insert_one({
            "id": new_id(), "package_id": pid, "field": f, "old_value": pkg.get(f),
            "new_value": newv, "changed_by": admin.get("user_id"), "created_at": now_iso()})
    merged = {**pkg, **changes}
    changes["credits_total"] = (merged.get("credits_base") or 0) + (merged.get("credits_bonus") or 0)
    changes["updated_at"] = now_iso()
    await db.credit_packages.update_one({"id": pid}, {"$set": changes})
    await record_audit(admin, "credit_package_update", meta={"id": pid, "changes": changes})
    return await db.credit_packages.find_one({"id": pid}, {"_id": 0})


@api.get("/platform/credit-packages/history")
async def credit_packages_history(admin: dict = Depends(require_superadmin)):
    rows = await db.credit_package_history.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return rows


# ==================== FASE C · ACQUISTO CREDITI (Stripe TEST) ====================
# Acquisto reale dei crediti: checkout Stripe TEST, accredito SOLO via conferma
# server-side (webhook autorevole), idempotente, snapshot pacchetto, ledger, fattura FIC.
# IVA 22% ESCLUSA applicata via TaxRate manuale (nessun automatic_tax). Nessun consumo attivo.
_credit_purchases_index_done = False


async def _ensure_credit_purchases_setup():
    global _credit_purchases_index_done
    if _credit_purchases_index_done:
        return
    try:
        await db.credit_purchases.create_index([("stripe_session_id", 1)], unique=True)
        await db.credit_purchases.create_index([("org_id", 1), ("created_at", -1)])
    except Exception:
        pass
    _credit_purchases_index_done = True


def _credit_billing_snapshot(org: dict) -> dict:
    b = org.get("billing") or {}
    return {
        "ragione_sociale": b.get("ragione_sociale") or (f"{b.get('nome','')} {b.get('cognome','')}".strip() or org.get("nome")),
        "partita_iva": b.get("partita_iva"), "codice_fiscale": b.get("codice_fiscale"),
        "codice_sdi": b.get("codice_sdi"), "pec": b.get("pec"), "paese": (b.get("paese") or "IT").upper(),
    }


class CreditCheckoutIn(BaseModel):
    package_id: str
    origin_url: str


async def migrate_legacy_orgs_to_trial():
    """Una tantum/idempotente: le org cliente ancora sul modello a crediti passano alla prova GOLD."""
    cfg = await SAAS["get_config"]()
    async for o in db.organizations.find({"saas": {"$exists": False}, "type": {"$in": ["cliente", None]}}, {"_id": 0, "id": 1, "nome": 1}):
        res = await db.organizations.update_one({"id": o["id"], "saas": {"$exists": False}},
                                                {"$set": {"saas": {**subscriptions.trial_doc(cfg), "migrated_from_credits": True}}})
        if res.modified_count:
            logger.info("Org %s migrata dal modello a crediti alla prova", o.get("nome"))


@api.post("/credits/checkout")
async def credits_checkout(body: CreditCheckoutIn, user: dict = Depends(require_admin)):
    raise HTTPException(status_code=410, detail="L'acquisto di crediti non è più disponibile: le funzioni sono incluse negli abbonamenti.")
    """Crea una sessione Stripe Checkout (TEST) per l'acquisto di un pacchetto crediti.
    Prezzo e crediti provengono SEMPRE dal catalogo server-side (mai dal frontend).
    IVA 22% esclusa via TaxRate manuale. I crediti NON vengono accreditati qui:
    l'accredito avviene solo dopo conferma del pagamento (webhook Stripe)."""
    await _ensure_credit_packages_seeded()
    await _ensure_credit_purchases_setup()
    _assert_stripe_ready()
    org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0})
    missing = _billing_missing(org.get("billing") or {})
    if missing:
        raise HTTPException(status_code=400, detail={"code": "billing_incomplete",
            "message": "Completa i dati di fatturazione", "missing": missing})
    pkg = await db.credit_packages.find_one({"id": body.package_id, "active": True}, {"_id": 0})
    if not pkg:
        raise HTTPException(status_code=404, detail="Taglio di ricarica non trovato o non attivo")
    net = round(float(pkg.get("price") or 0), 2)
    if net <= 0:
        raise HTTPException(status_code=400, detail="Prezzo del taglio non configurato")
    base = int(pkg.get("credits_base") or 0)
    bonus = int(pkg.get("credits_bonus") or 0)
    total = base + bonus
    vat = round(net * PRICING_VAT_RATE / 100.0, 2)
    gross = round(net + vat, 2)
    snapshot = {"price": net, "credits_base": base, "credits_bonus": bonus,
                "credits_total": total, "bonus_pct": pkg.get("bonus_pct"), "badge": pkg.get("badge")}
    cust_id = await _ensure_stripe_customer(org, user)
    tax_rate_id = _get_tax_rate_id()
    purchase_id = new_id()
    # Il bonus NON ha valore economico: l'imponibile e l'IVA si basano solo sul prezzo del taglio.
    session = stripe_sdk.checkout.Session.create(
        mode="payment", customer=cust_id,
        managed_payments={"enabled": False},
        line_items=[{"price_data": {"currency": "eur", "unit_amount": int(round(net * 100)),
                     "tax_behavior": "exclusive",
                     "product_data": {"name": f"Ricarica {total} crediti CRMEvent",
                                      "tax_code": "txcd_10103001",
                                      "description": (f"{base} crediti + {bonus} crediti bonus" if bonus else f"{base} crediti")}},
                     "quantity": 1, "tax_rates": [tax_rate_id]}],
        success_url=f"{body.origin_url}/profilo?tab=crediti&credits_checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{body.origin_url}/profilo?tab=crediti&credits_checkout=cancel",
        metadata={"kind": "credit_purchase", "org_id": org["id"], "purchase_id": purchase_id,
                  "package_id": pkg["id"], "credits_base": str(base), "credits_bonus": str(bonus),
                  "credits_total": str(total), "net": str(net), "vat": str(vat), "gross": str(gross)},
        payment_intent_data={"metadata": {"kind": "credit_purchase", "purchase_id": purchase_id, "org_id": org["id"]}},
    )
    doc = {"id": purchase_id, "org_id": org["id"], "user_id": user.get("user_id"),
           "package_id": pkg["id"], "package_snapshot": snapshot,
           "credits_base": base, "credits_bonus": bonus, "credits_total": total,
           "amount_net": net, "amount_vat": vat, "amount_gross": gross,
           "aliquota_iva": PRICING_VAT_RATE, "currency": "eur",
           "stripe_session_id": session.id, "stripe_payment_intent": None,
           "status": "pending", "invoice_id": None, "ledger_id": None,
           "billing_snapshot": _credit_billing_snapshot(org),
           "created_at": now_iso(), "paid_at": None, "updated_at": now_iso()}
    await db.credit_purchases.insert_one(doc)
    return {"checkout_url": session.url, "session_id": session.id,
            "amount_net": net, "amount_vat": vat, "amount_gross": gross,
            "credits_total": total, "credits_base": base, "credits_bonus": bonus}


async def _record_credit_invoice(purchase: dict, sess: dict) -> Optional[str]:
    """Crea (idempotente) un record fattura per la ricarica, compatibile col flusso FIC/simulazione."""
    sid = purchase["stripe_session_id"]
    existing = await db.invoices.find_one({"stripe_session_id": sid, "kind": "credit_recharge"}, {"_id": 0})
    if existing:
        return existing["id"]
    total = purchase["credits_total"]
    doc = {"id": new_id(), "org_id": purchase["org_id"], "kind": "credit_recharge",
           "descrizione": f"Ricarica {total} crediti CRMEvent",
           "credits_base": purchase["credits_base"], "credits_bonus": purchase["credits_bonus"],
           "credits_total": total,
           "stripe_session_id": sid, "stripe_payment_intent": sess.get("payment_intent"),
           "stripe_invoice_id": None, "numero_stripe": None, "data": now_iso(),
           "imponibile": purchase["amount_net"], "aliquota_iva": purchase["aliquota_iva"],
           "importo_iva": purchase["amount_vat"], "iva": purchase["amount_vat"],
           "totale": purchase["amount_gross"], "valuta": purchase.get("currency") or "eur",
           "dati_fiscali_cliente": purchase.get("billing_snapshot") or {},
           "riferimento_stripe": {"stripe_session_id": sid, "payment_intent": sess.get("payment_intent")},
           "payment_status": "paid", "created_at": now_iso(), "updated_at": now_iso(),
           "fic_document_id": None, "fic_numero": None, "fic_data": None,
           "fic_stato_documento": "da_emettere", "fic_stato_sdi": "non_inviato", "fic_pdf_url": None}
    try:
        await db.invoices.insert_one(doc)
    except Exception:
        return (await db.invoices.find_one({"stripe_session_id": sid, "kind": "credit_recharge"}, {"_id": 0}) or {}).get("id")
    return doc["id"]


async def _emit_credit_invoice(inv_id: str):
    """Emissione fattura FIC per una ricarica. NON blocca mai pagamento/accredito e idempotente.
    Rispetta FIC_MODE: 'live' = documento reale; altrimenti dry-run (nessun invio SDI).
    Se FIC non è connesso o fallisce, registra lo stato errore ma non solleva eccezioni."""
    inv = await db.invoices.find_one({"id": inv_id}, {"_id": 0})
    if not inv:
        return
    if inv.get("is_test"):
        return  # Le transazioni TEST non emettono MAI documenti reali su Fatture in Cloud.
    # Anti-duplicato: se un documento esiste già non ricrearlo.
    if inv.get("fic_document_id"):
        await db.invoices.update_one({"id": inv_id}, {"$set": {
            "fic_stato_documento": ("emessa" if FIC_MODE == "live" else "creato_test"),
            "fic_error": None, "updated_at": now_iso()}})
        return
    attempts = int(inv.get("fic_attempts") or 0) + 1
    base_upd = {"fic_attempts": attempts, "fic_last_attempt_at": now_iso(), "fic_mode": FIC_MODE, "updated_at": now_iso()}
    ficdoc = await db.fic_settings.find_one({"provider": "fic"})
    if not fic_configured() or not ficdoc:
        await db.invoices.update_one({"id": inv_id}, {"$set": {**base_upd,
            "fic_stato_documento": "da_emettere",
            "fic_error": "Fatture in Cloud non connesso (OAuth mancante)"}})
        return
    try:
        res = await _fic_issue_document(inv, dry_run=(FIC_MODE != "live"))
        await db.invoices.update_one({"id": inv_id}, {"$set": {**base_upd, "fic_error": None,
            "fic_stato_documento": ("emessa" if FIC_MODE == "live" else "creato_test")}})
        return res
    except HTTPException as e:
        await db.invoices.update_one({"id": inv_id}, {"$set": {**base_upd,
            "fic_stato_documento": "errore_emissione", "fic_error": str(e.detail)[:500]}})
    except Exception as e:  # noqa: BLE001
        await db.invoices.update_one({"id": inv_id}, {"$set": {**base_upd,
            "fic_stato_documento": "errore_emissione", "fic_error": str(e)[:500]}})


async def _activate_credit_purchase_from_session(sess: dict):
    """Accredito crediti SERVER-SIDE da sessione PAGATA. Idempotente per session id.
    Doppia protezione anti-doppione: stato 'paid' del purchase + idempotency_key sul ledger."""
    md = sess.get("metadata") or {}
    if md.get("kind") != "credit_purchase" or sess.get("payment_status") != "paid":
        return
    sid = sess.get("id")
    purchase = await db.credit_purchases.find_one({"stripe_session_id": sid}, {"_id": 0})
    if not purchase or purchase.get("status") == "paid":
        return
    org_id = purchase["org_id"]
    base, bonus, total = purchase["credits_base"], purchase["credits_bonus"], purchase["credits_total"]
    pi = sess.get("payment_intent")
    note = (f"Ricarica {total} crediti ({base} + {bonus} bonus)" if bonus else f"Ricarica {total} crediti")
    mv = await _apply_credit_movement(
        org_id, total, reason_code="purchase", type_="purchase",
        user_id=purchase.get("user_id"), idempotency_key=f"credit_purchase:{sid}", note=note)
    inv_id = await _record_credit_invoice(purchase, sess)
    await db.credit_purchases.update_one(
        {"stripe_session_id": sid},
        {"$set": {"status": "paid", "stripe_payment_intent": pi, "paid_at": now_iso(),
                  "ledger_id": (mv or {}).get("id"), "invoice_id": inv_id, "updated_at": now_iso()}})
    # Emissione fattura FIC: NON blocca MAI pagamento/accredito (già avvenuti). Idempotente.
    try:
        await _emit_credit_invoice(inv_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("Emissione fattura ricarica non riuscita (accredito già effettuato): %s", e)


@api.get("/credits/checkout-confirmation")
async def credits_checkout_confirmation(session_id: str, user: dict = Depends(require_admin)):
    """Verifica SERVER-SIDE (retrieve su Stripe) l'esito e, se pagato, accredita in modo
    idempotente (fallback al webhook, mai fidandosi della sola pagina di ritorno)."""
    try:
        sess = stripe_sdk.checkout.Session.retrieve(session_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Sessione di checkout non trovata")
    purchase = await db.credit_purchases.find_one({"stripe_session_id": session_id}, {"_id": 0})
    if not purchase or purchase.get("org_id") != user["org_id"]:
        raise HTTPException(status_code=403, detail="Sessione non associata all'organizzazione")
    paid = sess.get("payment_status") == "paid"
    if paid:
        await _activate_credit_purchase_from_session(sess)
    c = await _ensure_org_credits(user["org_id"])
    p = await db.credit_purchases.find_one({"stripe_session_id": session_id}, {"_id": 0})
    return {"paid": paid, "status": p.get("status"),
            "credits_total": p.get("credits_total"), "credits_base": p.get("credits_base"),
            "credits_bonus": p.get("credits_bonus"), "amount_net": p.get("amount_net"),
            "amount_vat": p.get("amount_vat"), "amount_gross": p.get("amount_gross"),
            "balance": c.get("balance")}


@api.get("/credits/purchases")
async def credits_purchases(user: dict = Depends(require_admin)):
    await _ensure_credit_purchases_setup()
    rows = await db.credit_purchases.find({"org_id": user["org_id"], "is_test": {"$ne": True}}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"purchases": rows}


@api.get("/platform/integrations/status")
async def platform_integrations_status(admin: dict = Depends(require_superadmin)):
    """Stato integrazioni per il Super Admin. NON espone alcun secret."""
    ficdoc = await db.fic_settings.find_one({"provider": "fic"}, {"_id": 0, "access_token": 0, "refresh_token": 0})
    return {
        "stripe": {"mode": STRIPE_MODE, "config_ok": STRIPE_CONFIG_OK, "errors": STRIPE_CONFIG_ERRORS,
                   "secret_key_set": bool(STRIPE_SECRET_KEY), "publishable_key_set": bool(STRIPE_PUBLISHABLE_KEY),
                   "webhook_secret_set": bool(STRIPE_WEBHOOK_SECRET), "account_id_set": bool(STRIPE_ACCOUNT_ID),
                   "tax_rate_id_set": bool(STRIPE_TAX_RATE_ID)},
        "fic": {"configured": fic_configured(), "connected": bool(ficdoc), "mode": FIC_MODE,
                "company_id_set": bool(await _fic_company_id()),
                "payment_account_set": bool(FIC_PAYMENT_ACCOUNT_ID)},
    }


@api.get("/platform/stripe/live-diagnostics")
async def platform_stripe_live_diagnostics(admin: dict = Depends(require_superadmin)):
    """Diagnostica READ-ONLY dei secret CRMEVENT_STRIPE_*_LIVE. Funziona anche con
    STRIPE_MODE=test (legge i secret LIVE direttamente da env, con client Stripe isolato).
    Solo chiamate NON transazionali (retrieve/list). Non crea/modifica nulla su Stripe.
    Non restituisce mai valori sensibili: solo esiti OK/ERRORE e metadati innocui."""
    def _env(n: str) -> str:
        return (os.environ.get(n) or "").strip()

    sk = _env("CRMEVENT_STRIPE_SECRET_KEY_LIVE")
    pk = _env("CRMEVENT_STRIPE_PUBLISHABLE_KEY_LIVE")
    whsec = _env("CRMEVENT_STRIPE_WEBHOOK_SECRET_LIVE")
    tax_id = _env("CRMEVENT_STRIPE_TAX_RATE_ID_LIVE")
    WEBHOOK_URL = "https://crmevent.it/api/stripe/webhook"

    checks: dict = {}

    def ok(key, detail=""):
        checks[key] = {"status": "OK", "detail": detail}

    def err(key, detail=""):
        checks[key] = {"status": "ERRORE", "detail": detail}

    # 1) Secret Key LIVE — formato/presenza
    if not sk or sk == "placeholder":
        err("secret_key_live", "mancante o placeholder")
    elif not (sk.startswith("sk_live_") or sk.startswith("rk_live_")):
        err("secret_key_live", "formato non LIVE (atteso sk_live_ o rk_live_)")
    else:
        ok("secret_key_live", "formato LIVE valido")

    # 2) Publishable Key LIVE — formato/presenza
    if not pk or pk == "placeholder":
        err("publishable_key_live", "mancante o placeholder")
    elif not pk.startswith("pk_live_"):
        err("publishable_key_live", "formato non LIVE (atteso pk_live_)")
    else:
        ok("publishable_key_live", "formato LIVE valido")

    # 4) Signing Secret — formato/presenza (il valore non viene mai mostrato né confrontato)
    if not whsec or whsec == "placeholder":
        err("signing_secret", "mancante o placeholder")
    elif not whsec.startswith("whsec_"):
        err("signing_secret", "formato non valido (atteso whsec_)")
    else:
        ok("signing_secret", "formato valido")

    # Client Stripe ISOLATO con la secret key LIVE (non tocca stripe_sdk.api_key globale)
    client = None
    if checks["secret_key_live"]["status"] == "OK":
        try:
            client = stripe_sdk.StripeClient(sk)
        except Exception as e:
            err("secret_key_live", f"inizializzazione client fallita: {type(e).__name__}")

    # 2b) Account Stripe LIVE + livemode (NON transazionale)
    if client is None:
        err("account_live", "non verificabile: secret key non valida")
    else:
        try:
            bal = await asyncio.to_thread(client.v1.balance.retrieve)
            if getattr(bal, "livemode", False):
                ok("account_live", "chiave valida, account in modalità LIVE")
            else:
                err("account_live", "chiave valida ma NON in modalità live (livemode=false)")
        except Exception as e:
            err("account_live", f"chiamata Stripe fallita: {type(e).__name__}")

    # 3) Tax Rate LIVE 22% exclusive IT active (NON transazionale)
    if client is None:
        err("tax_rate_live", "non verificabile: secret key non valida")
    elif not tax_id or tax_id == "placeholder":
        err("tax_rate_live", "CRMEVENT_STRIPE_TAX_RATE_ID_LIVE mancante o placeholder")
    else:
        try:
            tr = await asyncio.to_thread(client.v1.tax_rates.retrieve, tax_id)
            problems = []
            if float(getattr(tr, "percentage", 0) or 0) != 22.0:
                problems.append(f"percentage={getattr(tr, 'percentage', None)} (atteso 22)")
            if getattr(tr, "inclusive", None) is not False:
                problems.append("non è exclusive (inclusive!=false)")
            if (getattr(tr, "country", None) or "").upper() != "IT":
                problems.append(f"country={getattr(tr, 'country', None)} (atteso IT)")
            if not getattr(tr, "active", False):
                problems.append("non attivo")
            if not getattr(tr, "livemode", False):
                problems.append("non in modalità live")
            if problems:
                err("tax_rate_live", "; ".join(problems))
            else:
                ok("tax_rate_live", "22% exclusive IT attivo LIVE")
        except Exception as e:
            err("tax_rate_live", f"TaxRate non recuperabile: {type(e).__name__}")

    # 5) Webhook LIVE su crmevent.it con evento checkout.session.completed (NON transazionale)
    if client is None:
        err("webhook_live", "non verificabile: secret key non valida")
    else:
        try:
            eps = await asyncio.to_thread(lambda: list(client.v1.webhook_endpoints.list({"limit": 100}).auto_paging_iter()))
            match = next((e for e in eps if (getattr(e, "url", "") or "") == WEBHOOK_URL), None)
            if match is None:
                err("webhook_live", f"nessun endpoint con url {WEBHOOK_URL}")
            else:
                problems = []
                if getattr(match, "status", None) != "enabled":
                    problems.append(f"status={getattr(match, 'status', None)} (atteso enabled)")
                evts = list(getattr(match, "enabled_events", []) or [])
                if "checkout.session.completed" not in evts and "*" not in evts:
                    problems.append("evento checkout.session.completed non sottoscritto")
                for ev_name in SAAS_WEBHOOK_EVENTS:
                    if ev_name not in evts and "*" not in evts:
                        problems.append(f"evento {ev_name} non sottoscritto (abbonamenti)")
                if not getattr(match, "livemode", False):
                    problems.append("non in modalità live")
                if problems:
                    err("webhook_live", "; ".join(problems))
                else:
                    ok("webhook_live", "endpoint LIVE enabled con checkout.session.completed")
        except Exception as e:
            err("webhook_live", f"WebhookEndpoint.list fallita: {type(e).__name__}")

    ready = all(c["status"] == "OK" for c in checks.values())
    tech_errors = [f"{k}: {v['detail']}" for k, v in checks.items() if v["status"] == "ERRORE"]
    if tech_errors:
        logger.warning("Stripe LIVE diagnostics NON pronta: %s", "; ".join(tech_errors))
    return {
        "stripe_mode": STRIPE_MODE,
        "checks": checks,
        "overall": "PRONTA" if ready else "NON PRONTA",
    }


@api.get("/platform/credit-invoices")
async def platform_credit_invoices(admin: dict = Depends(require_superadmin)):
    """Stato per ricarica: Pagamento / Crediti / Fattura (per il pannello Super Admin)."""
    purchases = await db.credit_purchases.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    out = []
    for p in purchases:
        inv = await db.invoices.find_one({"id": p.get("invoice_id")}, {"_id": 0}) if p.get("invoice_id") else None
        org = await db.organizations.find_one({"id": p["org_id"]}, {"_id": 0, "nome": 1})
        out.append({
            "purchase_id": p["id"], "org_id": p["org_id"], "org_name": (org or {}).get("nome"),
            "created_at": p.get("created_at"), "paid_at": p.get("paid_at"),
            "amount_net": p.get("amount_net"), "amount_vat": p.get("amount_vat"), "amount_gross": p.get("amount_gross"),
            "credits_total": p.get("credits_total"), "payment_status": p.get("status"),
            "credits_granted": bool(p.get("ledger_id")), "invoice_id": p.get("invoice_id"),
            "fic_mode": (inv or {}).get("fic_mode"), "fic_stato": (inv or {}).get("fic_stato_documento") or "da_emettere",
            "fic_numero": (inv or {}).get("fic_numero"), "fic_error": (inv or {}).get("fic_error"),
            "fic_attempts": (inv or {}).get("fic_attempts") or 0,
            "stripe_payment_intent": p.get("stripe_payment_intent"),
            "is_test": bool(p.get("is_test")),
        })
    return {"invoices": out}


@api.post("/platform/invoices/{invoice_id}/simulate")
async def platform_invoice_simulate(invoice_id: str, admin: dict = Depends(require_superadmin)):
    """Simulazione FIC (TEST) da Super Admin su QUALSIASI fattura. Nessuna chiamata a Fatture in Cloud,
    nessun invio SDI, nessun documento reale. Riusa la logica interna condivisa con l'Area Account."""
    inv = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    return await _fic_simulate(inv)


@api.post("/platform/credit-invoices/test")
async def platform_create_test_recharge(body: dict = None, admin: dict = Depends(require_superadmin)):
    """Genera una RICARICA DI TEST (solo DB): nessuna chiamata a Stripe, nessuna a Fatture in Cloud,
    nessun credito reale accreditato, esclusa da fatturato/KPI/report. Serve solo per provare
    la simulazione fattura. Eliminabile dal Super Admin."""
    body = body or {}
    org_id = body.get("org_id")
    org = None
    if org_id:
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        org = await db.organizations.find_one({"billing.ragione_sociale": {"$nin": [None, ""]}}, {"_id": 0}) \
            or await db.organizations.find_one({}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=400, detail="Nessuna organizzazione disponibile per la transazione di test")
    net = round(float(body.get("amount_net") or 20.0), 2)
    total_credits = int(body.get("credits_total") or 100)
    vat = round(net * PRICING_VAT_RATE / 100.0, 2)
    gross = round(net + vat, 2)
    pid = new_id()
    marker = f"TEST-{pid[:10]}"
    inv_doc = {"id": new_id(), "org_id": org["id"], "kind": "credit_recharge", "is_test": True,
               "descrizione": f"Ricarica {total_credits} crediti CRMEvent (TRANSAZIONE TEST)",
               "credits_base": total_credits, "credits_bonus": 0, "credits_total": total_credits,
               "stripe_session_id": marker, "stripe_payment_intent": marker, "stripe_invoice_id": None,
               "numero_stripe": None, "data": now_iso(),
               "imponibile": net, "aliquota_iva": PRICING_VAT_RATE, "importo_iva": vat, "iva": vat,
               "totale": gross, "valuta": "eur",
               "dati_fiscali_cliente": _credit_billing_snapshot(org),
               "riferimento_stripe": {"stripe_session_id": marker, "payment_intent": marker, "test": True},
               "payment_status": "paid", "created_at": now_iso(), "updated_at": now_iso(),
               "fic_document_id": None, "fic_numero": None, "fic_data": None,
               "fic_stato_documento": "da_emettere", "fic_stato_sdi": "non_inviato", "fic_pdf_url": None}
    await db.invoices.insert_one(inv_doc)
    purchase = {"id": pid, "org_id": org["id"], "user_id": admin.get("user_id"), "is_test": True,
                "package_id": None, "package_snapshot": {"price": net, "credits_total": total_credits},
                "credits_base": total_credits, "credits_bonus": 0, "credits_total": total_credits,
                "amount_net": net, "amount_vat": vat, "amount_gross": gross, "aliquota_iva": PRICING_VAT_RATE,
                "currency": "eur", "stripe_session_id": marker, "stripe_payment_intent": marker,
                "status": "paid", "invoice_id": inv_doc["id"], "ledger_id": None,
                "billing_snapshot": _credit_billing_snapshot(org),
                "created_at": now_iso(), "paid_at": now_iso(), "updated_at": now_iso()}
    await db.credit_purchases.insert_one(purchase)
    await record_audit(admin, "test_recharge_created", org_id=org["id"], org_name=org.get("nome"),
                       detail=f"Transazione TEST {total_credits} crediti · {gross}€ (nessun Stripe/FIC/credito reale)")
    return {"ok": True, "purchase_id": pid, "invoice_id": inv_doc["id"], "org_name": org.get("nome")}


@api.delete("/platform/credit-invoices/test/{purchase_id}")
async def platform_delete_test_recharge(purchase_id: str, admin: dict = Depends(require_superadmin)):
    p = await db.credit_purchases.find_one({"id": purchase_id}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Transazione non trovata")
    if not p.get("is_test"):
        raise HTTPException(status_code=400, detail="Solo le transazioni TEST possono essere eliminate")
    if p.get("invoice_id"):
        await db.invoices.delete_one({"id": p["invoice_id"], "is_test": True})
    await db.credit_purchases.delete_one({"id": purchase_id})
    await record_audit(admin, "test_recharge_deleted", org_id=p.get("org_id"),
                       detail="Transazione TEST eliminata")
    return {"ok": True}


@api.post("/platform/invoices/{invoice_id}/retry-emit")
async def retry_emit_invoice(invoice_id: str, admin: dict = Depends(require_superadmin)):
    """Riprova emissione fattura FIC (idempotente, nessun documento duplicato)."""
    inv = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    if inv.get("is_test"):
        raise HTTPException(status_code=400, detail="Transazione TEST: emissione reale non consentita.")
    await _emit_credit_invoice(invoice_id)
    upd = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    await record_audit(admin, "fic_retry_emit", org_id=inv.get("org_id"),
                       detail=f"Stato: {upd.get('fic_stato_documento')}")
    return {"id": invoice_id, "fic_stato_documento": upd.get("fic_stato_documento"),
            "fic_numero": upd.get("fic_numero"), "fic_error": upd.get("fic_error"),
            "fic_attempts": upd.get("fic_attempts")}


# ---------------- Impostazioni crediti org (soglia) ----------------
class CreditSettingsIn(BaseModel):
    low_balance_threshold: Optional[int] = None


@api.put("/credits/settings")
async def credits_settings(body: CreditSettingsIn, user: dict = Depends(require_admin)):
    await _ensure_org_credits(user["org_id"])
    if body.low_balance_threshold is not None:
        await db.organizations.update_one(
            {"id": user["org_id"]},
            {"$set": {"credits.low_balance_threshold": max(0, int(body.low_balance_threshold)),
                      "credits.updated_at": now_iso()}})
    c = await _ensure_org_credits(user["org_id"])
    return {"low_balance_threshold": c.get("low_balance_threshold")}


# ---------------- MOTORE CONSUMO: estimate -> reserve -> settle -> release ----------------
# (predisposto, NON collegato ad alcuna funzione CRMEvent esistente in Fase B)
def _service_consumo_on(svc: dict) -> bool:
    """True se il servizio, oltre a essere disponibile (active), consuma crediti (consumo_active)
    ed è configurato (costo+modalità). Retrocompat: se consumo_active assente, deriva dallo stato.
    Distinzione: active = disponibilità della funzione; consumo_active = se consuma crediti."""
    if not svc or not svc.get("active"):
        return False
    if svc.get("unit_cost") is None or svc.get("pricing_mode") is None:
        return False
    ca = svc.get("consumo_active")
    if ca is None:
        ca = True  # retrocompat: configurato+attivo consumava già
    return bool(ca)


async def _credit_service_cost(service_key, quantity):
    svc = await db.credit_services.find_one({"key": service_key}, {"_id": 0})
    if not svc:
        raise HTTPException(status_code=404, detail="Servizio non trovato")
    consumo_on = _service_consumo_on(svc)
    if svc.get("unit_cost") is None or svc.get("pricing_mode") is None:
        return {"service": svc, "cost": None, "configured": False, "consumo_on": consumo_on, "quantity": int(quantity or 1)}
    q = max(int(quantity or 1), int(svc.get("min_units", 1) or 1))
    cost = svc["unit_cost"] if svc["pricing_mode"] == "flat" else svc["unit_cost"] * q
    return {"service": svc, "cost": int(round(cost)), "configured": True, "consumo_on": consumo_on, "quantity": q}


async def _credits_reserve(org_id, service_key, quantity=1, user_id=None, event_id=None, idempotency_key=None, note=None):
    from pymongo.errors import DuplicateKeyError
    await _assert_org_operational(org_id)
    info = await _credit_service_cost(service_key, quantity)
    if not info["configured"]:
        raise HTTPException(status_code=400, detail="Servizio non configurato per il consumo")
    if not info["service"].get("active"):
        raise HTTPException(status_code=400, detail="Servizio non attivo")
    cost = info["cost"]
    q = info["quantity"]
    await _ensure_org_credits(org_id)
    if idempotency_key:
        existing = await db.credit_ledger.find_one({"org_id": org_id, "idempotency_key": idempotency_key}, {"_id": 0})
        if existing:
            return existing
    doc = {"id": new_id(), "org_id": org_id, "type": "debit", "status": "pending", "amount": -cost,
           "balance_after": None, "reason_code": service_key, "service_key": service_key, "quantity": q,
           "unit_cost": info["service"]["unit_cost"], "event_id": event_id, "user_id": user_id,
           "idempotency_key": idempotency_key, "note": note, "created_at": now_iso(), "settled_at": None}
    try:
        await db.credit_ledger.insert_one(doc)
    except DuplicateKeyError:
        return await db.credit_ledger.find_one({"org_id": org_id, "idempotency_key": idempotency_key}, {"_id": 0})
    res = await db.organizations.update_one(
        {"id": org_id, "credits.balance": {"$gte": cost}},
        {"$inc": {"credits.balance": -cost, "credits.reserved": cost}, "$set": {"credits.updated_at": now_iso()}})
    if res.modified_count == 0:
        await db.credit_ledger.delete_one({"id": doc["id"]})
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "credits": 1})
        bal = (org.get("credits") or {}).get("balance", 0)
        raise HTTPException(status_code=402, detail=f"Crediti insufficienti (saldo {bal}, richiesti {cost})")
    return await db.credit_ledger.find_one({"id": doc["id"]}, {"_id": 0})


async def _credits_settle(reservation_id, actual_cost=None):
    r = await db.credit_ledger.find_one({"id": reservation_id}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="Prenotazione non trovata")
    if r["status"] == "committed":
        return r
    if r["status"] != "pending":
        raise HTTPException(status_code=400, detail="Prenotazione non in stato pending")
    reserved = -r["amount"]
    final = reserved if actual_cost is None else max(0, min(int(actual_cost), reserved))
    refund = reserved - final
    inc = {"credits.reserved": -reserved, "credits.lifetime_spent": final}
    if refund > 0:
        inc["credits.balance"] = refund
    await db.organizations.update_one({"id": r["org_id"]}, {"$inc": inc, "$set": {"credits.updated_at": now_iso()}})
    org = await db.organizations.find_one({"id": r["org_id"]}, {"_id": 0, "credits": 1})
    bal = (org.get("credits") or {}).get("balance", 0)
    await db.credit_ledger.update_one({"id": reservation_id}, {"$set": {"status": "committed", "amount": -final, "balance_after": bal, "settled_at": now_iso()}})
    return await db.credit_ledger.find_one({"id": reservation_id}, {"_id": 0})


async def _credits_release(reservation_id):
    r = await db.credit_ledger.find_one({"id": reservation_id}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="Prenotazione non trovata")
    if r["status"] == "released":
        return r
    if r["status"] != "pending":
        raise HTTPException(status_code=400, detail="Prenotazione non in stato pending")
    reserved = -r["amount"]
    await db.organizations.update_one(
        {"id": r["org_id"]},
        {"$inc": {"credits.balance": reserved, "credits.reserved": -reserved}, "$set": {"credits.updated_at": now_iso()}})
    await db.credit_ledger.update_one({"id": reservation_id}, {"$set": {"status": "released", "settled_at": now_iso()}})
    return await db.credit_ledger.find_one({"id": reservation_id}, {"_id": 0})


class EstimateIn(BaseModel):
    service_key: str
    quantity: int = 1


async def _charge_begin(org_id, service_key, *, user_id=None, event_id=None, idempotency_key=None, note=None):
    """Prenota i crediti SOLO se il servizio è configurato E attivo; altrimenti ritorna None (uso gratuito).
    Se il saldo è insufficiente solleva HTTP 402 e il servizio NON deve essere eseguito.
    Pattern: reservation = await _charge_begin(...); try: <esegui>; _credits_settle(); except: _credits_release()."""
    return None  # sistema a crediti dismesso: servizi inclusi negli abbonamenti
    svc = await db.credit_services.find_one({"key": service_key}, {"_id": 0})
    if not _service_consumo_on(svc) or await SAAS["is_saas"](org_id):
        return None
    return await _credits_reserve(org_id, service_key, 1, user_id=user_id, event_id=event_id,
                                  idempotency_key=idempotency_key, note=note)


class _AiChargeCtl:
    """Controller del consumo crediti AI. settle() addebita (impegno definitivo),
    release() rilascia (nessun addebito). Idempotente: non addebita né rilascia due volte."""
    def __init__(self, reservation):
        self.reservation = reservation
        self._done = False

    @property
    def will_charge(self) -> bool:
        return bool(self.reservation)

    async def settle(self):
        if self.reservation and not self._done:
            if self.reservation.get("status") == "pending":
                await _credits_settle(self.reservation["id"])
            self._done = True

    async def release(self):
        if self.reservation and not self._done:
            if self.reservation.get("status") == "pending":
                await _credits_release(self.reservation["id"])
            self._done = True


@contextlib.asynccontextmanager
async def ai_charge(org_id, service_key, *, user_id=None, event_id=None, idempotency_key=None, note=None):
    """Consumo crediti CENTRALIZZATO per le funzioni AI (riusabile da tutti gli endpoint AI).
    1) legge servizio/costo dal catalogo Super Admin (mai hardcoded);
    2) verifica il saldo e PRENOTA i crediti PRIMA di eseguire l'AI: se insufficiente solleva HTTP 402
       e l'AI NON viene chiamata;
    3) il chiamante invoca ctl.settle() SOLO se l'elaborazione produce un risultato realmente utile;
    4) in caso di errore o risultato non utile i crediti vengono rilasciati (nessun addebito);
    5) idempotente via idempotency_key: lo stesso tentativo non viene mai addebitato due volte.
    Uso:
        async with ai_charge(org_id, "ai_assistant", user_id=..., idempotency_key=...) as ctl:
            result = await <chiamata AI>
            if <risultato utile>: await ctl.settle()
    """
    reservation = await _charge_begin(org_id, service_key, user_id=user_id, event_id=event_id,
                                      idempotency_key=idempotency_key, note=note)
    ctl = _AiChargeCtl(reservation)
    if reservation and reservation.get("status") != "pending":
        ctl._done = True  # retry idempotente: movimento già committed/released, non toccarlo
    try:
        yield ctl
    except Exception:
        await ctl.release()
        raise
    else:
        await ctl.release()  # no-op se già settled; rilascia i crediti se la risposta non è utile


@api.post("/credits/estimate")
async def credits_estimate(body: EstimateIn, user: dict = Depends(require_admin)):
    info = await _credit_service_cost(body.service_key, body.quantity)
    c = await _ensure_org_credits(user["org_id"])
    svc = info["service"]
    will_charge = False  # sistema a crediti dismesso
    cost = info["cost"]
    effective = cost if (will_charge and cost is not None) else 0
    balance = c.get("balance", 0)
    return {"service_key": body.service_key, "quantity": info.get("quantity", body.quantity),
            "cost": cost, "effective_cost": effective, "will_charge": will_charge,
            "configured": info["configured"], "available": bool(svc.get("active")),
            "consumo_active": will_charge, "balance": balance,
            "sufficient": (not will_charge) or (cost is not None and balance >= cost)}


# ==================== FASE E.2 · ATTIVAZIONE EVENTO A CREDITI ====================
# Attivazione evento = 20 crediti UNA TANTUM (dal catalogo). Copre l'evento fino alla sua data.
# Nessun rinnovo periodico. Il PRIMO evento di ogni org è gratuito (bonus benvenuto).
# Stati: preparazione | attivo | concluso (per data). Eventi legacy (credit_state assente) NON bloccati.
from datetime import date as _date, timedelta as _timedelta


import calendar as _calendar


def _add_one_month(d: _date) -> _date:
    y = d.year + (1 if d.month == 12 else 0)
    m = 1 if d.month == 12 else d.month + 1
    last = _calendar.monthrange(y, m)[1]
    return _date(y, m, min(d.day, last))


async def _svc_cfg(key: str) -> dict:
    svc = await db.credit_services.find_one({"key": key}, {"_id": 0})
    cost = int(svc["unit_cost"]) if svc and svc.get("unit_cost") is not None else None
    return {"cost": cost, "active": bool(svc and svc.get("active")), "svc": svc}


async def _event_activation_cfg() -> dict:
    return await _svc_cfg("event_activation")


async def _event_maintenance_cfg() -> dict:
    return await _svc_cfg("event_maintenance")


def _event_end_date(ev: dict) -> Optional[str]:
    return ev.get("data_fine") or ev.get("data_inizio")


def _event_is_past(ev: dict) -> bool:
    end = _event_end_date(ev)
    try:
        return bool(end and _date.fromisoformat(end[:10]) < datetime.now(timezone.utc).date())
    except ValueError:
        return False


def _event_display_state(ev: dict) -> str:
    """Stato mostrato: concluso (data trascorsa) | attivo | sospeso | preparazione.
    Eventi legacy (credit_state assente) sono operativi: mostrati 'attivo'."""
    if _event_is_past(ev):
        return "concluso"
    st = ev.get("credit_state")
    if st in (None, "attivo"):
        return "attivo"
    if st == "sospeso":
        return "sospeso"
    if st == "concluso":
        return "concluso"
    return "preparazione"


async def _is_credit_model_org(org_id: str) -> bool:
    return False  # sistema a crediti dismesso
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "credits": 1})
    return bool(((org or {}).get("credits") or {}).get("signup_bonus_granted"))


async def _assert_org_operational(org_id: str):
    """Guardia GLOBALE saldo minimo: le org sul modello a crediti devono avere saldo > 0 per
    eseguire scritture operative. Saldo 0 = sola consultazione. Le org legacy sono esentate."""
    return  # sistema a crediti dismesso
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "credits": 1})
    c = (org or {}).get("credits") or {}
    if not c.get("signup_bonus_granted"):
        return  # org legacy: non bloccata durante la transizione
    if c.get("balance", 0) <= 0:
        raise HTTPException(status_code=402, detail="Crediti esauriti: ricarica per continuare a usare CRMEvent. I tuoi dati restano consultabili.")


async def _assert_can_create_event(org_id: str):
    """Creare un evento richiede saldo >= 1 (nessun consumo). Org legacy esentate."""
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "credits": 1})
    c = (org or {}).get("credits") or {}
    if not c.get("signup_bonus_granted"):
        return
    if c.get("balance", 0) < 1:
        raise HTTPException(status_code=402, detail="Crediti insufficienti: per creare un nuovo evento devi avere almeno 1 credito disponibile. Il tuo saldo è 0 crediti.")


async def _assert_event_operational(org_id: str, event_id: str):
    """Guardia per-evento: le scritture operative legate a un evento sono consentite solo se
    l'evento è attivato (attivo/concluso) o legacy. Blocca gli eventi 'in preparazione'."""
    return  # attivazione eventi dismessa: tutti gli eventi sono operativi (dati invariati)
    ev = await db.events.find_one({"id": event_id, "org_id": org_id}, {"_id": 0, "credit_state": 1, "nome": 1})
    if not ev:
        return
    st = ev.get("credit_state")
    if st == "preparazione":
        raise HTTPException(status_code=403, detail={
            "code": "event_not_operational", "credit_state": st, "event_id": event_id,
            "message": "Attiva l'evento per gestire le sue funzioni operative."})
    if st == "sospeso":
        raise HTTPException(status_code=403, detail={
            "code": "event_not_operational", "credit_state": st, "event_id": event_id,
            "message": "Evento sospeso per crediti insufficienti. Ricarica e riattiva l'evento per modificarlo."})


async def _charge_event_activation(ev: dict, user_id: Optional[str]) -> dict:
    """Addebita l'attivazione una-tantum (idempotente per evento). 402 se saldo insufficiente.
    Imposta la prima scadenza di mantenimento a +1 mese di calendario."""
    org_id = ev["org_id"]; eid = ev["id"]
    cfg = await _event_activation_cfg()
    if not cfg["active"] or cfg["cost"] is None:
        raise HTTPException(status_code=400, detail="Servizio 'Attivazione evento' non configurato")
    cost = cfg["cost"]
    mv = await _apply_credit_movement(
        org_id, -cost, reason_code="event_activation", type_="debit", service_key="event_activation",
        event_id=eid, user_id=user_id, idempotency_key=f"event_activation:{eid}",
        note=f"Attivazione evento — {ev.get('nome')}")
    now = now_iso()
    next_m = _add_one_month(datetime.now(timezone.utc).date()).isoformat()
    await db.events.update_one({"id": eid, "org_id": org_id}, {"$set": {
        "credit_state": "attivo", "activated_at": now, "activation_cost": cost,
        "next_maintenance_at": next_m, "maint_count": 0, "last_maintenance_at": None,
        "updated_at": now}})
    return mv


async def _charge_event_maintenance(ev: dict, user_id: Optional[str] = None) -> int:
    """Addebita un periodo di mantenimento (idempotente per contatore). 402 se saldo insufficiente.
    Ritorna il nuovo maint_count."""
    org_id = ev["org_id"]; eid = ev["id"]
    cfg = await _event_maintenance_cfg()
    if not cfg["active"] or cfg["cost"] is None:
        raise HTTPException(status_code=400, detail="Servizio 'Mantenimento evento' non configurato")
    cost = cfg["cost"]
    count = int(ev.get("maint_count") or 0) + 1
    await _apply_credit_movement(
        org_id, -cost, reason_code="event_maintenance", type_="debit", service_key="event_maintenance",
        event_id=eid, user_id=user_id, idempotency_key=f"event_maint:{eid}:{count}",
        note=f"Mantenimento evento — {ev.get('nome')}")
    return count


async def _event_credit_status(ev: dict) -> dict:
    act = await _event_activation_cfg()
    mnt = await _event_maintenance_cfg()
    org = await db.organizations.find_one({"id": ev["org_id"]}, {"_id": 0, "credits": 1})
    c = (org or {}).get("credits") or {}
    bal = c.get("balance", 0)
    act_cost = act["cost"]; mnt_cost = mnt["cost"]
    st = ev.get("credit_state") or "preparazione"
    return {"event_id": ev["id"], "nome": ev.get("nome"),
            "credit_state": st, "display_state": _event_display_state(ev),
            "activation_cost": act_cost, "maintenance_cost": mnt_cost, "cost": act_cost,
            "balance": bal, "event_date": _event_end_date(ev),
            "activated_at": ev.get("activated_at"),
            "next_maintenance_at": ev.get("next_maintenance_at"),
            "is_credit_model": bool(c.get("signup_bonus_granted")),
            "sufficient_activation": (act_cost is not None and bal >= act_cost),
            "sufficient_maintenance": (mnt_cost is not None and bal >= mnt_cost),
            "can_reactivate": (st == "sospeso" and mnt_cost is not None and bal >= mnt_cost),
            "low_balance": (bal <= c.get("low_balance_threshold", DEFAULT_LOW_BALANCE_THRESHOLD))}


@api.get("/events/{event_id}/credit-status")
async def event_credit_status(event_id: str, user: dict = Depends(require_admin)):
    ev = await db.events.find_one(oq(user, id=event_id), {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento non trovato")
    return await _event_credit_status(ev)


@api.post("/events/{event_id}/activate")
async def event_activate(event_id: str, user: dict = Depends(require_admin)):
    """Attiva l'evento (−30 crediti una tantum) oppure, se 'sospeso', lo riattiva addebitando solo
    il mantenimento (−20) e facendo ripartire il ciclo mensile. Idempotente sull'attivazione."""
    ev = await db.events.find_one(oq(user, id=event_id), {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento non trovato")
    if await SAAS["is_saas"](user["org_id"]):
        raise HTTPException(status_code=400, detail="Con l'abbonamento gli eventi sono già operativi: nessuna attivazione necessaria")
    st = ev.get("credit_state")
    if st == "attivo":
        return await _event_credit_status(ev)
    if _event_is_past(ev):
        raise HTTPException(status_code=400, detail="La data dell'evento è già trascorsa: nessuna attivazione necessaria")
    if st == "sospeso":
        count = await _charge_event_maintenance(ev, user.get("user_id"))
        now = now_iso()
        next_m = _add_one_month(datetime.now(timezone.utc).date()).isoformat()
        await db.events.update_one({"id": event_id, "org_id": user["org_id"]}, {"$set": {
            "credit_state": "attivo", "next_maintenance_at": next_m, "maint_count": count,
            "last_maintenance_at": now, "updated_at": now}})
        await record_audit(user, "event_reactivate", org_id=user["org_id"], meta={"event_id": event_id})
    else:
        await _charge_event_activation(ev, user.get("user_id"))
        await record_audit(user, "event_activate", org_id=user["org_id"], meta={"event_id": event_id})
    ev = await db.events.find_one(oq(user, id=event_id), {"_id": 0})
    return await _event_credit_status(ev)


MAINT_NOTICE_DAYS = 7


async def _maint_low_balance_notice(ev: dict, due: _date) -> bool:
    """Avviso UNA volta per scadenza agli Admin org se il saldo non copre il prossimo Mantenimento."""
    cfg = await _event_maintenance_cfg()
    if not cfg["active"] or not cfg["cost"]:
        return False
    org = await db.organizations.find_one({"id": ev["org_id"]}, {"_id": 0, "nome": 1, "credits": 1}) or {}
    bal = int(((org.get("credits") or {}).get("balance")) or 0)
    if bal >= cfg["cost"]:
        return False
    await db.events.update_one({"id": ev["id"], "org_id": ev["org_id"]}, {"$set": {"maint_notice_for": due.isoformat()}})
    admins = await db.memberships.find({"org_id": ev["org_id"], "role": "admin_org", "active": True}, {"_id": 0, "user_id": 1}).to_list(50)
    users = await db.users.find({"user_id": {"$in": [a["user_id"] for a in admins]}, "active": {"$ne": False}}, {"_id": 0, "email": 1, "name": 1}).to_list(50)
    due_it = due.strftime("%d/%m/%Y")
    for u in users:
        try:
            await email_utils.send_email(
                to=u["email"], subject=f"Crediti insufficienti per il mantenimento di «{ev.get('nome')}»",
                html=email_utils.link_email(
                    name=u.get("name") or "",
                    intro=(f"Il {due_it} è previsto il Mantenimento mensile dell'evento «{ev.get('nome')}» ({cfg['cost']} crediti), "
                           f"ma il saldo attuale di «{org.get('nome')}» è di {bal} crediti. Ricarica entro quella data per evitare "
                           f"la sospensione dell'evento."),
                    cta_label="Ricarica crediti", url=f"{APP_URL}/profilo?tab=crediti",
                    footer_note="Ricevi questo avviso una sola volta per ogni scadenza di mantenimento."))
        except Exception as e:
            logger.error(f"maint notice email failed: {e}")
    await record_audit({"user_id": "system", "email": "system", "name": "CRMEvent"}, "maint_low_balance_notice",
                       org_id=ev["org_id"], org_name=org.get("nome"), detail=f"{ev.get('nome')} · scadenza {due_it} · saldo {bal}/{cfg['cost']}")
    return True


async def run_event_renewals(now_dt: Optional[datetime] = None) -> dict:
    """Motore MANTENIMENTO (manuale, idempotente, multi-tenant). Per ogni evento 'attivo':
    conclude se la data evento è trascorsa; altrimenti, se è arrivata una scadenza di mantenimento
    (next_maintenance_at <= oggi e < data evento), addebita il mantenimento e sposta la scadenza di
    +1 mese di calendario; se il saldo è insufficiente l'evento passa a 'sospeso'. NESSUN cron collegato."""
    out = {"renewed": [], "suspended": [], "concluded": [], "disabled": True}
    return out  # mantenimento eventi a crediti dismesso: nessun addebito
    now_dt = now_dt or datetime.now(timezone.utc)
    today = now_dt.date(); nowiso = now_dt.isoformat()
    rows = await db.events.find({"credit_state": {"$in": ["attivo", "sospeso"]}}, {"_id": 0}).to_list(5000)
    for ev in rows:
        end = _event_end_date(ev)
        try:
            end_d = _date.fromisoformat(end[:10]) if end else None
        except ValueError:
            end_d = None
        if end_d and end_d <= today:
            await db.events.update_one({"id": ev["id"], "org_id": ev["org_id"]},
                                       {"$set": {"credit_state": "concluso", "next_maintenance_at": None, "updated_at": nowiso}})
            out["concluded"].append(ev["id"]); continue
        if ev.get("credit_state") != "attivo":
            continue
        nm = ev.get("next_maintenance_at")
        if not nm:
            continue
        try:
            nm_d = _date.fromisoformat(nm[:10])
        except ValueError:
            continue
        if nm_d > today:
            if (nm_d - today).days <= MAINT_NOTICE_DAYS and not (end_d and nm_d >= end_d) and ev.get("maint_notice_for") != nm[:10]:
                if await _maint_low_balance_notice(ev, nm_d):
                    out.setdefault("notified", []).append(ev["id"])
            continue
        if end_d and nm_d >= end_d:
            continue  # il periodo in corso copre fino alla data evento: nessun addebito
        try:
            count = await _charge_event_maintenance(ev, None)
            new_nm = _add_one_month(nm_d).isoformat()
            await db.events.update_one({"id": ev["id"], "org_id": ev["org_id"]},
                                       {"$set": {"next_maintenance_at": new_nm, "maint_count": count,
                                                 "last_maintenance_at": nowiso, "updated_at": nowiso}})
            out["renewed"].append(ev["id"])
        except HTTPException as he:
            if he.status_code == 402:
                await db.events.update_one({"id": ev["id"], "org_id": ev["org_id"]},
                                           {"$set": {"credit_state": "sospeso", "updated_at": nowiso}})
                out["suspended"].append(ev["id"])
            else:
                raise
    return out


@api.post("/platform/events/run-renewals")
async def platform_run_event_renewals(admin: dict = Depends(require_superadmin)):
    """Esecuzione manuale (Super Admin). Conclude gli eventi con data trascorsa. Nessun cron attivo."""
    return await run_event_renewals()


# ==================== PIPELINE EVENTO PRO (servizio a crediti) · FASE 1 ====================
PIPELINE_SVC_KEY = "event_pipeline_pro"


class PipelineActivateIn(BaseModel):
    template_key: Optional[str] = None


async def _pipeline_doc(org_id: str, event_id: str):
    return await db.event_pipelines.find_one({"org_id": org_id, "event_id": event_id}, {"_id": 0})


def _event_pipeline_ref_date(ev: dict):
    """Data evento usata per calcolare le scadenze relative (giorno della gara = data_inizio)."""
    d = ev.get("data_inizio") or ev.get("data_fine")
    return d[:10] if d else None


async def _pipeline_status_payload(org_id: str, ev: dict) -> dict:
    cfg = await _svc_cfg(PIPELINE_SVC_KEY)
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "credits": 1})
    bal = ((org or {}).get("credits") or {}).get("balance", 0)
    cost = cfg["cost"]
    p = await _pipeline_doc(org_id, ev["id"])
    active = bool(p and p.get("active"))
    template_key = (p or {}).get("template_key")
    task_count = 0
    if active:
        task_count = await db.pipeline_tasks.count_documents({"org_id": org_id, "event_id": ev["id"]})
    event_ref_date = _event_pipeline_ref_date(ev)
    pipeline_ref_date = (p or {}).get("pipeline_ref_date")
    date_changed = bool(active and template_key and task_count and pipeline_ref_date
                        and event_ref_date and pipeline_ref_date != event_ref_date)
    return {"event_id": ev["id"], "event_name": ev.get("nome"),
            "active": active, "activated_at": (p or {}).get("activated_at"),
            "template_key": template_key, "task_count": task_count,
            "needs_template": bool(active and not template_key),
            "event_ref_date": event_ref_date, "pipeline_ref_date": pipeline_ref_date,
            "date_changed": date_changed,
            "service_active": cfg["active"], "cost": cost, "balance": bal,
            "sufficient": True, "balance_after": None}


@api.get("/events/{event_id}/pipeline/status")
async def pipeline_status(event_id: str, user: dict = Depends(require_admin)):
    ev = await db.events.find_one(oq(user, id=event_id), {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento non trovato")
    return await _pipeline_status_payload(user["org_id"], ev)


@api.post("/events/{event_id}/pipeline/activate")
async def pipeline_activate(event_id: str, body: PipelineActivateIn, user: dict = Depends(require_admin)):
    """Attiva la Pipeline Evento Pro: addebito UNA TANTUM letto dal catalogo (idempotente per evento),
    multi-tenant via oq(). 402 se crediti insufficienti. Lo storico riporta 'Pipeline Evento Pro – [evento]'."""
    org_id = user["org_id"]
    ev = await db.events.find_one(oq(user, id=event_id), {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento non trovato")
    existing = await _pipeline_doc(org_id, event_id)
    if existing and existing.get("active"):
        return await _pipeline_status_payload(org_id, ev)
    cfg = await _svc_cfg(PIPELINE_SVC_KEY)
    if not cfg["active"] or cfg["cost"] is None:
        raise HTTPException(status_code=400, detail="Servizio 'Pipeline Evento Pro' non configurato")
    await _apply_credit_movement(
        org_id, -cfg["cost"], reason_code="event_pipeline_pro", type_="debit", service_key=PIPELINE_SVC_KEY,
        event_id=event_id, user_id=user.get("user_id"), idempotency_key=f"event_pipeline:{event_id}",
        note=f"Pipeline Evento Pro – {ev.get('nome')}")
    now = now_iso()
    if existing:
        await db.event_pipelines.update_one({"org_id": org_id, "event_id": event_id},
                                            {"$set": {"active": True, "activated_at": now,
                                                      "activation_cost": cfg["cost"], "template_key": body.template_key,
                                                      "updated_at": now}})
    else:
        await db.event_pipelines.insert_one({"id": new_id(), "org_id": org_id, "event_id": event_id,
                                             "active": True, "activated_at": now, "activation_cost": cfg["cost"],
                                             "template_key": body.template_key, "created_at": now, "updated_at": now})
    await record_audit(user, "pipeline_activate", org_id=org_id, meta={"event_id": event_id, "cost": cfg["cost"]})
    await _seed_pipeline_categories(org_id, event_id)
    ev = await db.events.find_one(oq(user, id=event_id), {"_id": 0})
    return await _pipeline_status_payload(org_id, ev)


PIPELINE_DEFAULT_CATEGORIES = ["Autorizzazioni", "Percorso", "Allestimenti", "Staff e volontari",
    "Sicurezza", "Iscrizioni", "Materiali", "Comunicazione", "Sponsor e partner", "Merchandising",
    "Logistica", "Post evento"]
PIPELINE_STATI = ["da_fare", "in_corso", "in_attesa", "completata"]
PIPELINE_PRIORITA = ["normale", "importante", "critica"]


async def _seed_pipeline_categories(org_id, event_id):
    if await db.pipeline_categories.count_documents({"org_id": org_id, "event_id": event_id}):
        return
    now = now_iso()
    await db.pipeline_categories.insert_many([
        {"id": new_id(), "org_id": org_id, "event_id": event_id, "name": n, "order": i,
         "created_at": now, "updated_at": now} for i, n in enumerate(PIPELINE_DEFAULT_CATEGORIES)])


def _task_is_late(t) -> bool:
    if t.get("stato") == "completata":
        return False
    sc = t.get("scadenza")
    try:
        return bool(sc and _date.fromisoformat(sc[:10]) < datetime.now(timezone.utc).date())
    except ValueError:
        return False


def _serialize_task(t: dict) -> dict:
    t = {k: v for k, v in t.items() if k != "_id"}
    t["late"] = _task_is_late(t)
    return t


async def _pipeline_stats(org_id, event_id) -> dict:
    rows = await db.pipeline_tasks.find({"org_id": org_id, "event_id": event_id}, {"_id": 0}).to_list(5000)
    total = len(rows)
    completate = sum(1 for t in rows if t.get("stato") == "completata")
    in_ritardo = sum(1 for t in rows if _task_is_late(t))
    critiche = sum(1 for t in rows if t.get("priorita") == "critica" and t.get("stato") != "completata")
    return {"total": total, "completate": completate, "da_fare": total - completate,
            "in_ritardo": in_ritardo, "critiche": critiche,
            "percent": (round(completate / total * 100) if total else 0)}


class PipelineCategoryIn(BaseModel):
    name: str


class PipelineTaskIn(BaseModel):
    titolo: str
    descrizione: Optional[str] = None
    categoria_id: Optional[str] = None
    stato: Optional[str] = "da_fare"
    priorita: Optional[str] = "normale"
    scadenza: Optional[str] = None
    responsabile_id: Optional[str] = None
    azienda_id: Optional[str] = None
    persona_id: Optional[str] = None
    costo_previsto: Optional[float] = None
    costo_effettivo: Optional[float] = None
    note: Optional[str] = None
    allegati: Optional[list] = None
    crm_section: Optional[str] = None


class PipelineTaskUpd(BaseModel):
    titolo: Optional[str] = None
    descrizione: Optional[str] = None
    categoria_id: Optional[str] = None
    stato: Optional[str] = None
    priorita: Optional[str] = None
    scadenza: Optional[str] = None
    responsabile_id: Optional[str] = None
    azienda_id: Optional[str] = None
    persona_id: Optional[str] = None
    costo_previsto: Optional[float] = None
    costo_effettivo: Optional[float] = None
    note: Optional[str] = None
    allegati: Optional[list] = None
    crm_section: Optional[str] = None


@api.get("/events/{event_id}/pipeline/categories")
async def pipeline_categories_list(event_id: str, user: dict = Depends(require_admin)):
    return await db.pipeline_categories.find(oq(user, event_id=event_id), {"_id": 0}).sort("order", 1).to_list(500)


@api.post("/events/{event_id}/pipeline/categories")
async def pipeline_category_create(event_id: str, body: PipelineCategoryIn, user: dict = Depends(require_admin)):
    n = (body.name or "").strip()
    if not n:
        raise HTTPException(status_code=400, detail="Nome categoria obbligatorio")
    cnt = await db.pipeline_categories.count_documents(oq(user, event_id=event_id))
    doc = {"id": new_id(), "org_id": user["org_id"], "event_id": event_id, "name": n, "order": cnt,
           "created_at": now_iso(), "updated_at": now_iso()}
    await db.pipeline_categories.insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}


@api.put("/pipeline/categories/{cat_id}")
async def pipeline_category_update(cat_id: str, body: PipelineCategoryIn, user: dict = Depends(require_admin)):
    r = await db.pipeline_categories.update_one(oq(user, id=cat_id),
                                                {"$set": {"name": (body.name or "").strip(), "updated_at": now_iso()}})
    if not r.matched_count:
        raise HTTPException(status_code=404, detail="Categoria non trovata")
    return {"ok": True}


@api.delete("/pipeline/categories/{cat_id}")
async def pipeline_category_delete(cat_id: str, confirm: bool = False, user: dict = Depends(require_admin)):
    cat = await db.pipeline_categories.find_one(oq(user, id=cat_id), {"_id": 0})
    if not cat:
        raise HTTPException(status_code=404, detail="Categoria non trovata")
    n = await db.pipeline_tasks.count_documents(oq(user, categoria_id=cat_id))
    if n and not confirm:
        raise HTTPException(status_code=409, detail=f"La categoria contiene {n} attività. Conferma l'eliminazione.")
    await db.pipeline_tasks.delete_many(oq(user, categoria_id=cat_id))
    await db.pipeline_categories.delete_one(oq(user, id=cat_id))
    return {"ok": True, "deleted_tasks": n}


@api.get("/events/{event_id}/pipeline/tasks")
async def pipeline_tasks_list(event_id: str, user: dict = Depends(require_admin)):
    rows = await db.pipeline_tasks.find(oq(user, event_id=event_id), {"_id": 0}).sort("created_at", 1).to_list(5000)
    return {"tasks": [_serialize_task(t) for t in rows], "stats": await _pipeline_stats(user["org_id"], event_id)}


@api.post("/events/{event_id}/pipeline/tasks")
async def pipeline_task_create(event_id: str, body: PipelineTaskIn, user: dict = Depends(require_admin)):
    if not (body.titolo or "").strip():
        raise HTTPException(status_code=400, detail="Titolo obbligatorio")
    data = body.model_dump()
    data.update({"id": new_id(), "org_id": user["org_id"], "event_id": event_id,
                 "created_at": now_iso(), "updated_at": now_iso()})
    await db.pipeline_tasks.insert_one(data)
    return _serialize_task(data)


@api.put("/pipeline/tasks/{task_id}")
async def pipeline_task_update(task_id: str, body: PipelineTaskUpd, user: dict = Depends(require_admin)):
    clean = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    clean["updated_at"] = now_iso()
    # Scadenza modificata manualmente → proteggila dai ricalcoli automatici per cambio data.
    if "scadenza" in clean:
        existing = await db.pipeline_tasks.find_one(oq(user, id=task_id), {"_id": 0, "scadenza": 1})
        if existing and (existing.get("scadenza") or None) != (clean.get("scadenza") or None):
            clean["due_date_overridden"] = True
    r = await db.pipeline_tasks.update_one(oq(user, id=task_id), {"$set": clean})
    if not r.matched_count:
        raise HTTPException(status_code=404, detail="Attività non trovata")
    t = await db.pipeline_tasks.find_one(oq(user, id=task_id), {"_id": 0})
    return _serialize_task(t)


@api.delete("/pipeline/tasks/{task_id}")
async def pipeline_task_delete(task_id: str, user: dict = Depends(require_admin)):
    await db.pipeline_tasks.delete_one(oq(user, id=task_id))
    return {"ok": True}


@api.post("/pipeline/tasks/{task_id}/duplicate")
async def pipeline_task_duplicate(task_id: str, user: dict = Depends(require_admin)):
    t = await db.pipeline_tasks.find_one(oq(user, id=task_id), {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Attività non trovata")
    t.update({"id": new_id(), "titolo": f"{t.get('titolo')} (copia)", "stato": "da_fare",
              "created_at": now_iso(), "updated_at": now_iso()})
    await db.pipeline_tasks.insert_one(t)
    return _serialize_task(t)


# =============================================================================
# FASE 3 — Modelli Pipeline (gestiti dal Super Admin) e generazione attività
# =============================================================================
_pipeline_templates_seeded = False


async def _ensure_pipeline_templates():
    """Semina i modelli iniziali (Running, Evento generico) una sola volta, idempotente.
    Le modifiche del Super Admin NON vengono mai sovrascritte."""
    global _pipeline_templates_seeded
    if _pipeline_templates_seeded:
        return
    try:
        await db.pipeline_templates.create_index([("key", 1)], unique=True)
    except Exception:
        pass
    for tpl in pipeline_seed.PIPELINE_TEMPLATES_SEED + pipeline_seed_sports.SPORT_TEMPLATES_SEED:
        if await db.pipeline_templates.find_one({"key": tpl["key"]}):
            continue
        now = now_iso()
        await db.pipeline_templates.insert_one({
            "id": new_id(), "key": tpl["key"], "name": tpl["name"],
            "description": tpl.get("description", ""), "active": True, "order": tpl.get("order", 0),
            "created_at": now, "updated_at": now})
        tasks = []
        for i, t in enumerate(tpl["tasks"]):
            tasks.append({"id": new_id(), "template_key": tpl["key"], "titolo": t["titolo"],
                          "descrizione": t.get("descrizione", ""), "categoria": t["categoria"],
                          "giorni_offset": int(t["giorni_offset"]), "priorita": t.get("priorita", "normale"),
                          "order": i, "active": True, "crm_section": t.get("crm_section"),
                          "created_at": now, "updated_at": now})
        if tasks:
            await db.pipeline_template_tasks.insert_many(tasks)
    _pipeline_templates_seeded = True


def _clean_template(t: dict) -> dict:
    return {k: v for k, v in t.items() if k != "_id"}


class PipelineTemplateIn(BaseModel):
    key: Optional[str] = None
    name: str
    description: Optional[str] = ""
    active: Optional[bool] = True
    order: Optional[int] = 0


class PipelineTemplateUpd(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    active: Optional[bool] = None
    order: Optional[int] = None


class PipelineTemplateTaskIn(BaseModel):
    titolo: str
    descrizione: Optional[str] = ""
    categoria: str
    giorni_offset: int = 0
    priorita: Optional[str] = "normale"
    order: Optional[int] = 0
    active: Optional[bool] = True
    crm_section: Optional[str] = None


class PipelineTemplateTaskUpd(BaseModel):
    titolo: Optional[str] = None
    descrizione: Optional[str] = None
    categoria: Optional[str] = None
    giorni_offset: Optional[int] = None
    priorita: Optional[str] = None
    order: Optional[int] = None
    active: Optional[bool] = None
    crm_section: Optional[str] = None


# -------- Super Admin: gestione modelli ---------------------------------------
@api.get("/platform/pipeline-templates")
async def platform_pipeline_templates(admin: dict = Depends(require_superadmin)):
    await _ensure_pipeline_templates()
    rows = await db.pipeline_templates.find({}, {"_id": 0}).to_list(200)
    rows.sort(key=lambda r: (r.get("name") or "").strip().lower())
    used = set(await db.event_pipelines.distinct("template_key"))
    for r in rows:
        r["in_use"] = r["key"] in used
    counts = {}
    for r in rows:
        counts[r["key"]] = await db.pipeline_template_tasks.count_documents({"template_key": r["key"]})
    for r in rows:
        r["task_count"] = counts.get(r["key"], 0)
    return {"templates": rows}


@api.post("/platform/pipeline-templates")
async def platform_pipeline_template_create(body: PipelineTemplateIn, admin: dict = Depends(require_superadmin)):
    await _ensure_pipeline_templates()
    key = (body.key or body.name or "").strip().lower().replace(" ", "_")
    if not key:
        raise HTTPException(status_code=400, detail="Codice/nome obbligatorio")
    if await db.pipeline_templates.find_one({"key": key}):
        raise HTTPException(status_code=400, detail="Esiste già un modello con questo codice")
    now = now_iso()
    doc = {"id": new_id(), "key": key, "name": (body.name or "").strip(),
           "description": body.description or "", "active": bool(body.active), "order": body.order or 0,
           "created_at": now, "updated_at": now}
    await db.pipeline_templates.insert_one(doc)
    await record_audit(admin, "pipeline_template_create", meta={"key": key})
    return _clean_template(doc)


@api.put("/platform/pipeline-templates/{key}")
async def platform_pipeline_template_update(key: str, body: PipelineTemplateUpd, admin: dict = Depends(require_superadmin)):
    clean = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if not clean:
        raise HTTPException(status_code=400, detail="Nessuna modifica")
    clean["updated_at"] = now_iso()
    r = await db.pipeline_templates.update_one({"key": key}, {"$set": clean})
    if not r.matched_count:
        raise HTTPException(status_code=404, detail="Modello non trovato")
    await record_audit(admin, "pipeline_template_update", meta={"key": key, "changes": clean})
    return _clean_template(await db.pipeline_templates.find_one({"key": key}, {"_id": 0}))


@api.delete("/platform/pipeline-templates/{key}")
async def platform_pipeline_template_delete(key: str, admin: dict = Depends(require_superadmin)):
    if not await db.pipeline_templates.find_one({"key": key}):
        raise HTTPException(status_code=404, detail="Modello non trovato")
    if await db.event_pipelines.find_one({"template_key": key}, {"_id": 1}):
        raise HTTPException(status_code=409, detail="Modello già utilizzato da uno o più eventi: puoi solo disattivarlo")
    await db.pipeline_template_tasks.delete_many({"template_key": key})
    await db.pipeline_templates.delete_one({"key": key})
    await record_audit(admin, "pipeline_template_delete", meta={"key": key})
    return {"ok": True}


@api.get("/platform/pipeline-templates/{key}/tasks")
async def platform_pipeline_template_tasks(key: str, admin: dict = Depends(require_superadmin)):
    tpl = await db.pipeline_templates.find_one({"key": key}, {"_id": 0})
    if not tpl:
        raise HTTPException(status_code=404, detail="Modello non trovato")
    rows = await db.pipeline_template_tasks.find({"template_key": key}, {"_id": 0}).sort("order", 1).to_list(1000)
    return {"template": tpl, "tasks": rows, "categories": pipeline_seed.STANDARD_CATEGORIES}


@api.post("/platform/pipeline-templates/{key}/tasks")
async def platform_pipeline_template_task_create(key: str, body: PipelineTemplateTaskIn, admin: dict = Depends(require_superadmin)):
    if not await db.pipeline_templates.find_one({"key": key}):
        raise HTTPException(status_code=404, detail="Modello non trovato")
    cnt = await db.pipeline_template_tasks.count_documents({"template_key": key})
    now = now_iso()
    doc = {"id": new_id(), "template_key": key, **body.model_dump(),
           "created_at": now, "updated_at": now}
    if not body.order:
        doc["order"] = cnt
    await db.pipeline_template_tasks.insert_one(doc)
    return _clean_template(doc)


@api.put("/platform/pipeline-template-tasks/{task_id}")
async def platform_pipeline_template_task_update(task_id: str, body: PipelineTemplateTaskUpd, admin: dict = Depends(require_superadmin)):
    clean = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    if not clean:
        raise HTTPException(status_code=400, detail="Nessuna modifica")
    clean["updated_at"] = now_iso()
    r = await db.pipeline_template_tasks.update_one({"id": task_id}, {"$set": clean})
    if not r.matched_count:
        raise HTTPException(status_code=404, detail="Attività modello non trovata")
    return _clean_template(await db.pipeline_template_tasks.find_one({"id": task_id}, {"_id": 0}))


@api.delete("/platform/pipeline-template-tasks/{task_id}")
async def platform_pipeline_template_task_delete(task_id: str, admin: dict = Depends(require_superadmin)):
    await db.pipeline_template_tasks.delete_one({"id": task_id})
    return {"ok": True}


# -------- Organizzatore: scelta modello e generazione attività ----------------
@api.get("/events/{event_id}/pipeline/templates")
async def pipeline_templates_for_event(event_id: str, user: dict = Depends(require_admin)):
    """Modelli ATTIVI disponibili per la scelta, con numero di attività che verranno generate."""
    await _ensure_pipeline_templates()
    ev = await db.events.find_one(oq(user, id=event_id), {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento non trovato")
    rows = await db.pipeline_templates.find({"active": True}, {"_id": 0}).to_list(200)
    rows.sort(key=lambda r: (r.get("name") or "").strip().lower())
    out = []
    for r in rows:
        n = await db.pipeline_template_tasks.count_documents({"template_key": r["key"], "active": True})
        out.append({"key": r["key"], "name": r["name"], "description": r.get("description", ""), "task_count": n})
    sug = pipeline_seed_sports.suggest_template(ev.get("tipologia"))
    return {"templates": out, "suggested": sug if any(o["key"] == sug for o in out) else None}


async def _generate_pipeline_from_template(org_id: str, event_id: str, template_key: str, ev: dict) -> int:
    """Genera (o rigenera) le attività della pipeline dal modello. Nessun consumo di crediti.
    Elimina le attività attuali e ricostruisce dalle attività attive del modello."""
    tpl = await db.pipeline_templates.find_one({"key": template_key, "active": True}, {"_id": 0})
    if not tpl:
        raise HTTPException(status_code=404, detail="Modello non trovato o non attivo")
    tmpl_tasks = await db.pipeline_template_tasks.find(
        {"template_key": template_key, "active": True}, {"_id": 0}).sort("order", 1).to_list(2000)
    ref = _event_pipeline_ref_date(ev)
    if not ref:
        raise HTTPException(status_code=400, detail="Imposta prima la data dell'evento")
    ref_date = _date.fromisoformat(ref)
    now = now_iso()
    # Categorie: standard + quelle usate dal modello. Crea quelle mancanti.
    wanted = list(pipeline_seed.STANDARD_CATEGORIES)
    for t in tmpl_tasks:
        if t.get("categoria") and t["categoria"] not in wanted:
            wanted.append(t["categoria"])
    existing_cats = await db.pipeline_categories.find({"org_id": org_id, "event_id": event_id}, {"_id": 0}).to_list(500)
    name_to_id = {c["name"]: c["id"] for c in existing_cats}
    order_base = len(existing_cats)
    for i, name in enumerate(wanted):
        if name not in name_to_id:
            cid = new_id()
            await db.pipeline_categories.insert_one({"id": cid, "org_id": org_id, "event_id": event_id,
                "name": name, "order": order_base + i, "created_at": now, "updated_at": now})
            name_to_id[name] = cid
    # Rigenerazione: elimina attività attuali.
    await db.pipeline_tasks.delete_many({"org_id": org_id, "event_id": event_id})
    docs = []
    for i, t in enumerate(tmpl_tasks):
        due = (ref_date + _timedelta(days=int(t.get("giorni_offset") or 0))).isoformat()
        docs.append({"id": new_id(), "org_id": org_id, "event_id": event_id,
            "titolo": t["titolo"], "descrizione": t.get("descrizione", ""),
            "categoria_id": name_to_id.get(t.get("categoria")), "stato": "da_fare",
            "priorita": t.get("priorita", "normale"), "scadenza": due,
            "giorni_offset": int(t.get("giorni_offset") or 0), "due_date_overridden": False,
            "crm_section": t.get("crm_section"), "responsabile_id": None, "azienda_id": None,
            "persona_id": None, "costo_previsto": None, "costo_effettivo": None, "note": None,
            "created_at": now, "updated_at": now})
    if docs:
        await db.pipeline_tasks.insert_many(docs)
    await db.event_pipelines.update_one({"org_id": org_id, "event_id": event_id},
        {"$set": {"template_key": template_key, "template_applied_at": now,
                  "pipeline_ref_date": ref, "updated_at": now}})
    return len(docs)


class PipelineGenerateIn(BaseModel):
    template_key: str
    confirm: Optional[bool] = False


@api.post("/events/{event_id}/pipeline/generate")
async def pipeline_generate(event_id: str, body: PipelineGenerateIn, user: dict = Depends(require_admin)):
    """Applica un modello e genera le attività. Nessun addebito di crediti.
    Se esistono già attività (cambio modello) serve confirm=true: le attività attuali vengono eliminate."""
    org_id = user["org_id"]
    ev = await db.events.find_one(oq(user, id=event_id), {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento non trovato")
    p = await _pipeline_doc(org_id, event_id)
    if not (p and p.get("active")):
        raise HTTPException(status_code=400, detail="La Pipeline non è attiva per questo evento")
    existing_tasks = await db.pipeline_tasks.count_documents({"org_id": org_id, "event_id": event_id})
    if existing_tasks and not body.confirm:
        raise HTTPException(status_code=409,
            detail="La Pipeline contiene già attività. Confermando, le attività attuali e le personalizzazioni verranno eliminate.")
    n = await _generate_pipeline_from_template(org_id, event_id, body.template_key, ev)
    await record_audit(user, "pipeline_generate", org_id=org_id,
                       meta={"event_id": event_id, "template_key": body.template_key, "tasks": n})
    ev = await db.events.find_one(oq(user, id=event_id), {"_id": 0})
    payload = await _pipeline_status_payload(org_id, ev)
    payload["generated"] = n
    return payload


@api.post("/events/{event_id}/pipeline/recalculate-deadlines")
async def pipeline_recalculate_deadlines(event_id: str, user: dict = Depends(require_admin)):
    """Ricalcola le scadenze sulla nuova data evento mantenendo lo stesso offset relativo.
    Le attività con scadenza modificata manualmente (due_date_overridden) NON vengono toccate."""
    org_id = user["org_id"]
    ev = await db.events.find_one(oq(user, id=event_id), {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento non trovato")
    ref = _event_pipeline_ref_date(ev)
    if not ref:
        raise HTTPException(status_code=400, detail="Imposta prima la data dell'evento")
    ref_date = _date.fromisoformat(ref)
    rows = await db.pipeline_tasks.find({"org_id": org_id, "event_id": event_id}, {"_id": 0}).to_list(5000)
    updated = 0
    for t in rows:
        if t.get("due_date_overridden"):
            continue
        if t.get("giorni_offset") is None:
            continue
        due = (ref_date + _timedelta(days=int(t["giorni_offset"]))).isoformat()
        await db.pipeline_tasks.update_one({"org_id": org_id, "id": t["id"]},
            {"$set": {"scadenza": due, "updated_at": now_iso()}})
        updated += 1
    await db.event_pipelines.update_one({"org_id": org_id, "event_id": event_id},
        {"$set": {"pipeline_ref_date": ref, "updated_at": now_iso()}})
    await record_audit(user, "pipeline_recalc", org_id=org_id, meta={"event_id": event_id, "updated": updated})
    payload = await _pipeline_status_payload(org_id, ev)
    payload["recalculated"] = updated
    return payload


@api.post("/events/{event_id}/pipeline/keep-deadlines")
async def pipeline_keep_deadlines(event_id: str, user: dict = Depends(require_admin)):
    """Mantieni le scadenze attuali: allinea solo la data di riferimento così l'avviso di cambio data sparisce."""
    org_id = user["org_id"]
    ev = await db.events.find_one(oq(user, id=event_id), {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento non trovato")
    await db.event_pipelines.update_one({"org_id": org_id, "event_id": event_id},
        {"$set": {"pipeline_ref_date": _event_pipeline_ref_date(ev), "updated_at": now_iso()}})
    return await _pipeline_status_payload(org_id, ev)


# =============================================================================
# FASE 4 — Collegamenti CRMEvent (conteggi informativi) e duplicazione Pipeline
# =============================================================================
# Mappa crm_section -> dove portare l'organizzatore (il frontend risolve le rotte).
PIPELINE_CRM_SECTIONS = ["staff", "volunteers", "sponsors", "hospitality", "routes", "briefing", "companies", "persons"]


@api.get("/events/{event_id}/pipeline/crm-counts")
async def pipeline_crm_counts(event_id: str, user: dict = Depends(require_admin)):
    """Conteggi informativi dalle sezioni CRMEvent collegate (NON modificano lo stato Pipeline).
    Riutilizza i dati esistenti con semplici count scoped per org+evento."""
    org_id = user["org_id"]
    ev = await db.events.find_one(oq(user, id=event_id), {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento non trovato")
    staff_rows = await db.staff.find(oq(user, evento_id=event_id), {"_id": 0, "categoria": 1}).to_list(10000)
    volontari = sum(1 for s in staff_rows if s.get("categoria") == "volontario")
    staff_n = sum(1 for s in staff_rows if s.get("categoria") in ("staff", "collaboratore"))
    shifts = await db.shifts.find(oq(user, evento_id=event_id), {"_id": 0, "persona_id": 1}).to_list(10000)
    scoperti = sum(1 for s in shifts if not s.get("persona_id"))
    counts = {
        "volunteers": {"count": volontari, "label": "volontari"},
        "staff": {"count": staff_n, "label": "membri staff", "extra": {"turni": len(shifts), "turni_scoperti": scoperti}},
        "sponsors": {"count": await db.deals.count_documents(oq(user, evento_id=event_id)), "label": "sponsor/partner"},
        "hospitality": {"count": await db.lodgings.count_documents(oq(user, evento_id=event_id)), "label": "pernottamenti"},
        "routes": {"count": await db.event_maps.count_documents(oq(user, evento_id=event_id)), "label": "percorsi caricati"},
        "briefing": {"count": await db.briefing_versions.count_documents(oq(user, evento_id=event_id)), "label": "versioni briefing"},
        "companies": {"count": await db.companies.count_documents(oq(user)), "label": "aziende"},
        "persons": {"count": await db.persons.count_documents(oq(user)), "label": "persone"},
    }
    return {"event_id": event_id, "counts": counts}


@api.get("/events/{event_id}/pipeline/duplicatable-sources")
async def pipeline_duplicatable_sources(event_id: str, user: dict = Depends(require_admin)):
    """Eventi della STESSA organizzazione con una Pipeline attiva e almeno un'attività, utilizzabili come origine."""
    org_id = user["org_id"]
    dest = await db.events.find_one(oq(user, id=event_id), {"_id": 0, "id": 1})
    if not dest:
        raise HTTPException(status_code=404, detail="Evento non trovato")
    pipelines = await db.event_pipelines.find({"org_id": org_id, "active": True}, {"_id": 0, "event_id": 1, "template_key": 1}).to_list(2000)
    out = []
    for p in pipelines:
        if p["event_id"] == event_id:
            continue
        n = await db.pipeline_tasks.count_documents({"org_id": org_id, "event_id": p["event_id"]})
        if not n:
            continue
        ev = await db.events.find_one({"org_id": org_id, "id": p["event_id"]}, {"_id": 0, "id": 1, "nome": 1, "data_inizio": 1})
        if not ev:
            continue
        out.append({"event_id": ev["id"], "event_name": ev.get("nome"), "data_inizio": ev.get("data_inizio"),
                    "template_key": p.get("template_key"), "task_count": n})
    out.sort(key=lambda x: (x.get("data_inizio") or ""), reverse=True)
    return {"sources": out}


def _copy_offset(task: dict, src_ref):
    """Offset relativo da usare nella copia. Per attività da modello mantiene l'offset originale
    (anche se la scadenza è stata modificata a mano). Per attività manuali lo deriva da scadenza - data evento origine."""
    off = task.get("giorni_offset")
    if off is not None:
        return int(off)
    sc = task.get("scadenza")
    if sc and src_ref:
        try:
            return (_date.fromisoformat(sc[:10]) - src_ref).days
        except ValueError:
            return None
    return None


class PipelineDuplicateIn(BaseModel):
    source_event_id: str
    confirm: Optional[bool] = False


@api.post("/events/{event_id}/pipeline/duplicate-from")
async def pipeline_duplicate_from(event_id: str, body: PipelineDuplicateIn, user: dict = Depends(require_admin)):
    """Crea la Pipeline della nuova edizione copiando categorie e attività da una Pipeline origine
    della STESSA organizzazione. Scadenze ricalcolate sulla data del nuovo evento con gli offset origine.
    Addebita i crediti SOLO se la Pipeline destinazione non è ancora attiva (idempotente, nessun doppio addebito)."""
    org_id = user["org_id"]
    dest_ev = await db.events.find_one(oq(user, id=event_id), {"_id": 0})
    src_ev = await db.events.find_one(oq(user, id=body.source_event_id), {"_id": 0})
    if not dest_ev or not src_ev:
        raise HTTPException(status_code=404, detail="Evento non trovato")
    if body.source_event_id == event_id:
        raise HTTPException(status_code=400, detail="L'evento origine e destinazione coincidono")
    src_p = await _pipeline_doc(org_id, body.source_event_id)
    if not (src_p and src_p.get("active")):
        raise HTTPException(status_code=400, detail="La Pipeline origine non è attiva")
    src_tasks = await db.pipeline_tasks.find({"org_id": org_id, "event_id": body.source_event_id}, {"_id": 0}).to_list(5000)
    if not src_tasks:
        raise HTTPException(status_code=400, detail="La Pipeline origine non contiene attività")
    dest_ref = _event_pipeline_ref_date(dest_ev)
    if not dest_ref:
        raise HTTPException(status_code=400, detail="Imposta prima la data del nuovo evento")
    dest_ref_date = _date.fromisoformat(dest_ref)
    src_ref = _event_pipeline_ref_date(src_ev)
    src_ref_date = _date.fromisoformat(src_ref) if src_ref else None

    dest_p = await _pipeline_doc(org_id, event_id)
    dest_active = bool(dest_p and dest_p.get("active"))
    existing_tasks = await db.pipeline_tasks.count_documents({"org_id": org_id, "event_id": event_id})
    if existing_tasks and not body.confirm:
        raise HTTPException(status_code=409,
            detail="La Pipeline destinazione contiene già attività. Confermando verranno eliminate e sostituite dalla copia.")

    now = now_iso()
    # Attivazione + addebito SOLO se non già attiva (idempotente via idempotency_key per evento).
    if not dest_active:
        cfg = await _svc_cfg(PIPELINE_SVC_KEY)
        if not cfg["active"] or cfg["cost"] is None:
            raise HTTPException(status_code=400, detail="Servizio 'Pipeline Evento Pro' non configurato")
        await _apply_credit_movement(
            org_id, -cfg["cost"], reason_code="event_pipeline_pro", type_="debit", service_key=PIPELINE_SVC_KEY,
            event_id=event_id, user_id=user.get("user_id"), idempotency_key=f"event_pipeline:{event_id}",
            note=f"Pipeline Evento Pro – {dest_ev.get('nome')}")
        if dest_p:
            await db.event_pipelines.update_one({"org_id": org_id, "event_id": event_id},
                {"$set": {"active": True, "activated_at": now, "activation_cost": cfg["cost"], "updated_at": now}})
        else:
            await db.event_pipelines.insert_one({"id": new_id(), "org_id": org_id, "event_id": event_id,
                "active": True, "activated_at": now, "activation_cost": cfg["cost"], "created_at": now, "updated_at": now})

    # Copia categorie (per nome, crea le mancanti). Mappa nome->id origine e nome->id destinazione.
    src_cats = await db.pipeline_categories.find({"org_id": org_id, "event_id": body.source_event_id}, {"_id": 0}).to_list(500)
    src_cat_name = {c["id"]: c["name"] for c in src_cats}
    dest_cats = await db.pipeline_categories.find({"org_id": org_id, "event_id": event_id}, {"_id": 0}).to_list(500)
    dest_name_to_id = {c["name"]: c["id"] for c in dest_cats}
    order_base = len(dest_cats)
    for i, c in enumerate(sorted(src_cats, key=lambda x: x.get("order", 0))):
        if c["name"] not in dest_name_to_id:
            cid = new_id()
            await db.pipeline_categories.insert_one({"id": cid, "org_id": org_id, "event_id": event_id,
                "name": c["name"], "order": order_base + i, "created_at": now, "updated_at": now})
            dest_name_to_id[c["name"]] = cid

    # Rigenerazione destinazione.
    await db.pipeline_tasks.delete_many({"org_id": org_id, "event_id": event_id})
    docs = []
    for t in src_tasks:
        off = _copy_offset(t, src_ref_date)
        scad = (dest_ref_date + _timedelta(days=off)).isoformat() if off is not None else None
        cat_name = src_cat_name.get(t.get("categoria_id"))
        docs.append({"id": new_id(), "org_id": org_id, "event_id": event_id,
            "titolo": t.get("titolo"), "descrizione": t.get("descrizione"),
            "categoria_id": dest_name_to_id.get(cat_name) if cat_name else None,
            "stato": "da_fare", "priorita": t.get("priorita", "normale"), "scadenza": scad,
            "giorni_offset": off, "due_date_overridden": False, "crm_section": t.get("crm_section"),
            "responsabile_id": t.get("responsabile_id"),
            "azienda_id": t.get("azienda_id"),  # aziende/fornitori sono org-scoped → stessa organizzazione
            "persona_id": None, "costo_previsto": t.get("costo_previsto"),
            "costo_effettivo": None, "note": t.get("note"), "allegati": None,
            "created_at": now, "updated_at": now})
    if docs:
        await db.pipeline_tasks.insert_many(docs)
    await db.event_pipelines.update_one({"org_id": org_id, "event_id": event_id},
        {"$set": {"template_key": src_p.get("template_key"), "pipeline_ref_date": dest_ref,
                  "duplicated_from": body.source_event_id, "updated_at": now}})
    await record_audit(user, "pipeline_duplicate", org_id=org_id,
        meta={"event_id": event_id, "source_event_id": body.source_event_id, "tasks": len(docs), "charged": not dest_active})
    dest_ev = await db.events.find_one(oq(user, id=event_id), {"_id": 0})
    payload = await _pipeline_status_payload(org_id, dest_ev)
    payload["duplicated"] = len(docs)
    payload["charged"] = not dest_active
    return payload


@api.get("/pipeline/attention")
async def pipeline_attention(limit: int = 10, user: dict = Depends(require_admin)):
    """Attività Pipeline che richiedono attenzione su tutti gli eventi con Pipeline ATTIVA dell'organizzazione.
    Mostra: in ritardo, critiche non completate, in scadenza entro 7gg, senza responsabile e in scadenza entro 14gg.
    Esclude le attività completate e le Pipeline non attive. Nessun consumo crediti."""
    org_id = user["org_id"]
    pipelines = await db.event_pipelines.find({"org_id": org_id, "active": True}, {"_id": 0, "event_id": 1}).to_list(5000)
    event_ids = [p["event_id"] for p in pipelines]
    if _ev_ids(user) is not None:
        event_ids = [e for e in event_ids if e in _ev_ids(user)]
    if not event_ids:
        return {"items": [], "total": 0}
    events = await db.events.find({"org_id": org_id, "id": {"$in": event_ids}}, {"_id": 0, "id": 1, "nome": 1}).to_list(5000)
    ev_name = {e["id"]: e.get("nome") for e in events}
    tasks = await db.pipeline_tasks.find(
        {"org_id": org_id, "event_id": {"$in": event_ids}, "stato": {"$ne": "completata"}}, {"_id": 0}).to_list(50000)
    cats = await db.pipeline_categories.find({"org_id": org_id, "event_id": {"$in": event_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(10000)
    cat_name = {c["id"]: c["name"] for c in cats}
    persons = await db.persons.find(oq(user), {"_id": 0, "id": 1, "nome": 1, "cognome": 1}).to_list(50000)
    person_name = {p["id"]: f"{p.get('cognome', '')} {p.get('nome', '')}".strip() for p in persons}
    today = datetime.now(timezone.utc).date()
    out = []
    for t in tasks:
        sc = t.get("scadenza")
        try:
            d = _date.fromisoformat(sc[:10]) if sc else None
        except ValueError:
            d = None
        days = (d - today).days if d else None
        late = bool(d and d < today)
        critica = t.get("priorita") == "critica"
        due7 = bool(days is not None and 0 <= days <= 7)
        unassigned14 = bool(not t.get("responsabile_id") and days is not None and 0 <= days <= 14)
        if not (late or critica or due7 or unassigned14):
            continue
        reasons = []
        if late: reasons.append("late")
        if critica: reasons.append("critica")
        if due7: reasons.append("due_soon")
        if unassigned14: reasons.append("unassigned")
        out.append({"event_id": t["event_id"], "event_name": ev_name.get(t["event_id"]),
                    "task_id": t["id"], "titolo": t.get("titolo"), "priorita": t.get("priorita", "normale"),
                    "scadenza": sc, "late": late, "days_to_due": days,
                    "responsabile_id": t.get("responsabile_id") or None,
                    "responsabile": person_name.get(t.get("responsabile_id")) if t.get("responsabile_id") else None,
                    "categoria": cat_name.get(t.get("categoria_id")), "reasons": reasons,
                    "_bucket": 0 if late else (1 if critica else 2), "_sort": d.isoformat() if d else "9999-12-31"})
    out.sort(key=lambda x: (x["_bucket"], x["_sort"]))
    total = len(out)
    for x in out:
        x.pop("_bucket", None); x.pop("_sort", None)
    return {"items": out[:max(1, limit)], "total": total}





@api.get("/platform/events/migration-dryrun")
async def events_migration_dryrun(admin: dict = Depends(require_superadmin)):
    """DRY-RUN (sola lettura): stato degli eventi esistenti col nuovo modello. Nessuna scrittura."""
    cfg = await _event_activation_cfg()
    evs = await db.events.find({}, {"_id": 0, "id": 1, "nome": 1, "org_id": 1, "data_inizio": 1,
                                    "data_fine": 1, "credit_state": 1}).to_list(5000)
    orgs = {o["id"]: o for o in await db.organizations.find({}, {"_id": 0, "id": 1, "nome": 1, "credits": 1}).to_list(5000)}
    today = datetime.now(timezone.utc).date()
    rows = []
    for ev in evs:
        org = orgs.get(ev.get("org_id")) or {}
        bal = (org.get("credits") or {}).get("balance", 0)
        end = _event_end_date(ev)
        past = bool(end and _date.fromisoformat(end) < today)
        rows.append({"org_id": ev.get("org_id"), "org_nome": org.get("nome"), "event_id": ev["id"],
                     "evento": ev.get("nome"), "data_evento": end, "past": past,
                     "credit_state_attuale": ev.get("credit_state"), "org_balance": bal,
                     "cosa_succederebbe": ("Nessuna azione (già concluso per data)" if past else
                                           "Resterebbe 'in preparazione' finché l'organizzatore non lo attiva manualmente (−%s crediti, una tantum). Nessun addebito automatico." % cfg["cost"])})
    return {"activation_cost": cfg["cost"], "total_events": len(rows),
            "note": "Nessuna attivazione/addebito automatico. Gli eventi esistenti NON vengono migrati.", "events": rows}


class PriceUpdateIn(BaseModel):
    net: float


@api.put("/platform/pricing/{plan}/{fascia}")
async def update_pricing(plan: str, fascia: str, body: PriceUpdateIn, admin: dict = Depends(require_superadmin)):
    if plan not in PRICING_PLANS_LIST or fascia not in PRICING_TIERS:
        raise HTTPException(status_code=400, detail="Piano o fascia non validi")
    new_net = round(float(body.net), 2)
    if new_net <= 0:
        raise HTTPException(status_code=400, detail="Il prezzo netto deve essere maggiore di zero")
    doc = await db.pricing_plans.find_one({"plan": plan, "fascia": fascia}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Prezzo non trovato")
    old_net = doc.get("net")
    # FASE 2 STEP 4: sync Stripe. Ordine sicuro: nuovo Price → verifica → update DB → history → poi archivia vecchio.
    old_price_id = doc.get("stripe_price_id")
    try:
        pid = doc.get("stripe_product_id") or _ensure_stripe_product(plan)
        new_price_id = _create_stripe_price(plan, fascia, new_net, pid)
        if not new_price_id:
            raise RuntimeError("price_id vuoto")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Sincronizzazione Stripe fallita: nessuna modifica applicata al listino ({e})")
    await db.pricing_plans.update_one({"plan": plan, "fascia": fascia}, {"$set": {
        "net": new_net, "gross": _gross(new_net), "version": doc.get("version", 1) + 1,
        "stripe_product_id": pid, "stripe_price_id": new_price_id,
        "updated_at": now_iso(), "updated_by": admin.get("user_id")}})
    await _create("pricing_history", {
        "plan": plan, "fascia": fascia, "old_net": old_net, "new_net": new_net,
        "old_gross": doc.get("gross"), "new_gross": _gross(new_net),
        "old_stripe_price_id": old_price_id, "new_stripe_price_id": new_price_id,
        "changed_by": admin.get("user_id"), "changed_by_email": admin.get("email"),
        "note": "Aggiornamento listino con sync Stripe (nuovo Price attivo, vecchio archiviato)"})
    # Solo DOPO il completamento del DB: archivia il vecchio Price Stripe.
    if old_price_id:
        try:
            stripe_sdk.Price.modify(old_price_id, active=False)
        except Exception:
            pass
    try:
        await record_audit(admin, "pricing_updated", meta={"plan": plan, "fascia": fascia, "old_net": old_net, "new_net": new_net, "new_price_id": new_price_id})
    except Exception:
        pass
    return await db.pricing_plans.find_one({"plan": plan, "fascia": fascia}, {"_id": 0})


@api.post("/platform/phase2/migrate")
async def phase2_migrate(admin: dict = Depends(require_superadmin)):
    """Migrazione non distruttiva: seed listino + account_plan org + back-fill entitlement eventi. Idempotente."""
    await _ensure_pricing_seeded()
    orgs = await db.organizations.find({}, {"_id": 0, "id": 1, "type": 1, "subscription": 1}).to_list(5000)
    org_updates = 0
    org_ap = {}
    for o in orgs:
        sub = o.get("subscription", {}) or {}
        if o.get("type") != "cliente":
            ap = "internal"
        else:
            st = sub.get("status", "trial")
            ap = "trial" if st == "trial" else ("customer" if st == "active" else "free")
        org_ap[o["id"]] = ap
        if sub.get("account_plan") != ap:
            await db.organizations.update_one({"id": o["id"]}, {"$set": {"subscription.account_plan": ap, "updated_at": now_iso()}})
            org_updates += 1
    events = await db.events.find({}, {"_id": 0, "id": 1, "org_id": 1, "data_inizio": 1, "entitlement": 1}).to_list(50000)
    ev_updates = 0
    for e in events:
        if e.get("entitlement"):
            continue
        di = e.get("data_inizio") or ""
        year = int(di[:4]) if di[:4].isdigit() else None
        ap = org_ap.get(e["org_id"])
        plan = "premium" if ap in ("trial", "internal", "customer") else "free"
        ent = {"plan": plan, "source": "trial" if ap == "trial" else "migration", "price_tier": None,
               "year": year, "amount_net": None, "amount_vat": None, "amount_gross": None, "currency": "EUR",
               "stripe_price_id": None, "stripe_payment_ref": None, "invoice_id": None, "purchased_at": None}
        await db.events.update_one({"id": e["id"]}, {"$set": {"entitlement": ent, "updated_at": now_iso()}})
        ev_updates += 1
    return {"ok": True, "pricing_plans": await db.pricing_plans.count_documents({}),
            "org_account_plan_updated": org_updates, "org_total": len(orgs),
            "events_backfilled": ev_updates, "events_total": len(events)}


@api.get("/account/plan-overview")
async def account_plan_overview(user: dict = Depends(require_admin)):
    org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=404, detail="Organizzazione non trovata")
    sub = _sub_summary(org)
    year = datetime.now(timezone.utc).year
    count = await _events_in_year(user["org_id"], year)
    tier = compute_tier(count)
    return {"account_plan": sub.get("account_plan"), "effective_plan": sub.get("effective_plan"),
            "status": sub.get("status"), "days_left": sub.get("days_left"),
            "year": year, "events_in_year": count, "fascia": tier,
            "fascia_label": TIER_LABEL.get(tier)}


# ---- FASE 2 STEP 4: Stripe per-evento (TEST) — Price/Product dinamici, checkout mode=payment, upgrade ----
_TAX_RATE_CACHE = {}


def _get_tax_rate_id():
    if STRIPE_TAX_RATE_ID:
        return STRIPE_TAX_RATE_ID
    if _TAX_RATE_CACHE.get("id"):
        return _TAX_RATE_CACHE["id"]
    for r in stripe_sdk.TaxRate.list(active=True, limit=100).auto_paging_iter():
        if float(r.percentage) == PRICING_VAT_RATE and not r.inclusive:
            _TAX_RATE_CACHE["id"] = r.id
            return r.id
    r = stripe_sdk.TaxRate.create(display_name="IVA", percentage=PRICING_VAT_RATE, inclusive=False, country="IT")
    _TAX_RATE_CACHE["id"] = r.id
    return r.id


def _ensure_stripe_product(plan):
    for p in stripe_sdk.Product.list(active=True, limit=100).auto_paging_iter():
        if p.to_dict().get("metadata", {}).get("emergent_plan") == plan:
            return p.id
    p = stripe_sdk.Product.create(name=f"CRMEvent {PLAN_LABEL.get(plan, plan)}", tax_code="txcd_10103001",
                                  metadata={"managed_by": "emergent", "emergent_plan": plan})
    return p.id


def _create_stripe_price(plan, fascia, net, product_id):
    pr = stripe_sdk.Price.create(product=product_id, unit_amount=int(round(float(net) * 100)), currency="eur",
                                 tax_behavior="exclusive", metadata={"emergent_plan": plan, "emergent_fascia": fascia})
    return pr.id


async def _ensure_pricing_stripe(row):
    if row.get("stripe_price_id"):
        return row["stripe_price_id"]
    pid = row.get("stripe_product_id") or _ensure_stripe_product(row["plan"])
    price_id = _create_stripe_price(row["plan"], row["fascia"], row["net"], pid)
    await db.pricing_plans.update_one({"plan": row["plan"], "fascia": row["fascia"]},
                                      {"$set": {"stripe_product_id": pid, "stripe_price_id": price_id, "updated_at": now_iso()}})
    return price_id


async def _pricing_row(plan, tier):
    return await db.pricing_plans.find_one({"plan": plan, "fascia": tier, "status": "active"}, {"_id": 0})


@api.post("/platform/pricing/stripe-sync-all")
async def pricing_stripe_sync_all(admin: dict = Depends(require_superadmin)):
    await _ensure_pricing_seeded()
    rows = await db.pricing_plans.find({}, {"_id": 0}).to_list(50)
    rows.sort(key=_pricing_sort_key)
    out = []
    for r in rows:
        pid = await _ensure_pricing_stripe(r)
        out.append({"plan": r["plan"], "fascia": r["fascia"], "stripe_price_id": pid})
    return {"ok": True, "prices": out}


class EventCheckoutIn(BaseModel):
    plan: str
    origin_url: str


@api.post("/events/{event_id}/checkout")
async def event_checkout(event_id: str, body: EventCheckoutIn, user: dict = Depends(require_admin)):
    if body.plan not in PRICING_PLANS_LIST:
        raise HTTPException(status_code=400, detail="Piano non valido")
    org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0})
    if not (org.get("billing") or {}).get("paese"):
        raise HTTPException(status_code=400, detail="Completa prima i dati di fatturazione")
    ev = await db.events.find_one(oq(user, id=event_id), {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento non trovato")
    di = ev.get("data_inizio") or ""
    if not di[:4].isdigit():
        raise HTTPException(status_code=400, detail="Imposta prima la data dell'evento")
    year = int(di[:4])
    tier = compute_tier(await _events_in_year(user["org_id"], year))
    row = await _pricing_row(body.plan, tier)
    if not row:
        raise HTTPException(status_code=500, detail="Listino non configurato")
    price_id = await _ensure_pricing_stripe(row)
    cust_id = await _ensure_stripe_customer(org, user)
    session = stripe_sdk.checkout.Session.create(
        mode="payment", customer=cust_id,
        line_items=[{"price": price_id, "quantity": 1}],
        automatic_tax={"enabled": True},
        success_url=f"{body.origin_url}/eventi?purchase=success&session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{body.origin_url}/eventi?purchase=cancel",
        metadata={"kind": "event_purchase", "org_id": org["id"], "event_id": event_id,
                  "plan": body.plan, "tier": tier, "year": str(year),
                  "net": str(row["net"]), "price_id": price_id, "version": str(row.get("version", 1))},
        payment_intent_data={"metadata": {"kind": "event_purchase", "event_id": event_id, "plan": body.plan}},
    )
    return {"checkout_url": session.url, "session_id": session.id, "plan": body.plan, "tier": tier, "net": row["net"]}


class EventUpgradeIn(BaseModel):
    plan: str
    origin_url: str


@api.post("/events/{event_id}/upgrade")
async def event_upgrade(event_id: str, body: EventUpgradeIn, user: dict = Depends(require_admin)):
    if body.plan not in PRICING_PLANS_LIST:
        raise HTTPException(status_code=400, detail="Piano non valido")
    org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0})
    ev = await db.events.find_one(oq(user, id=event_id), {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento non trovato")
    ent = ev.get("entitlement") or {}
    cur_plan = ent.get("plan") or "free"
    if ent.get("source") != "purchased":
        raise HTTPException(status_code=400, detail="L'evento non ha un piano acquistato da aggiornare")
    if PLAN_RANK.get(body.plan, 0) <= PLAN_RANK.get(cur_plan, 0):
        raise HTTPException(status_code=400, detail="Downgrade non consentito")
    tier = ent.get("price_tier") or compute_tier(await _events_in_year(user["org_id"], ent.get("year") or datetime.now(timezone.utc).year))
    row = await _pricing_row(body.plan, tier)
    if not row:
        raise HTTPException(status_code=500, detail="Listino non configurato")
    already = float(ent.get("amount_net") or 0)
    diff = round(float(row["net"]) - already, 2)
    if diff <= 0:
        raise HTTPException(status_code=409, detail=f"Nessun importo dovuto per l'upgrade (destinazione {row['net']}€ ≤ già pagato {already}€). Caso gestito in sicurezza: nessun addebito né rimborso.")
    await _ensure_pricing_stripe(row)
    cust_id = await _ensure_stripe_customer(org, user)
    session = stripe_sdk.checkout.Session.create(
        mode="payment", customer=cust_id,
        line_items=[{"price_data": {"currency": "eur", "unit_amount": int(round(diff * 100)), "tax_behavior": "exclusive",
                     "product_data": {"name": f"Upgrade a {PLAN_LABEL.get(body.plan)} – {ev.get('nome', 'Evento')}", "tax_code": "txcd_10103001"}},
                     "quantity": 1}],
        automatic_tax={"enabled": True},
        success_url=f"{body.origin_url}/eventi?upgrade=success&session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{body.origin_url}/eventi?upgrade=cancel",
        metadata={"kind": "event_upgrade", "org_id": org["id"], "event_id": event_id,
                  "plan": body.plan, "tier": tier, "year": str(ent.get("year") or ""),
                  "net": str(row["net"]), "diff": str(diff), "from_plan": cur_plan,
                  "price_id": row.get("stripe_price_id"), "version": str(row.get("version", 1))},
        payment_intent_data={"metadata": {"kind": "event_upgrade", "event_id": event_id, "plan": body.plan}},
    )
    return {"checkout_url": session.url, "session_id": session.id, "plan": body.plan, "diff": diff}


async def _activate_event_from_session(sess: dict):
    """Attivazione SERVER-SIDE da sessione PAGATA. Idempotente per session id."""
    md = sess.get("metadata") or {}
    if md.get("kind") not in ("event_purchase", "event_upgrade") or sess.get("payment_status") != "paid":
        return
    sid = sess.get("id")
    if await db.event_purchases.find_one({"stripe_session_id": sid}):
        return
    ev = await db.events.find_one({"id": md.get("event_id")}, {"_id": 0})
    if not ev:
        return
    kind = md["kind"]
    plan, tier = md.get("plan"), md.get("tier")
    year = int(md["year"]) if md.get("year", "").isdigit() else (ev.get("entitlement") or {}).get("year")
    net = float(md.get("net") or 0)
    pi = sess.get("payment_intent")
    amount_total = round((sess.get("amount_total") or 0) / 100.0, 2)
    upgrade_paid = float(md["diff"]) if kind == "event_upgrade" and md.get("diff") else None
    vat = round(net * PRICING_VAT_RATE / 100.0, 2)
    gross = round(net + vat, 2)
    version = int(md["version"]) if md.get("version", "").isdigit() else None
    await _create("event_purchases", {
        "event_id": md.get("event_id"), "organization_id": md.get("org_id"), "plan": plan, "price_tier": tier,
        "year": year, "net": net, "vat": vat, "gross": gross, "currency": (sess.get("currency") or "eur"),
        "kind": kind, "from_plan": md.get("from_plan"), "upgrade_amount_paid": upgrade_paid,
        "amount_total_paid": amount_total, "stripe_price_id": md.get("price_id"), "stripe_payment_intent": pi,
        "stripe_session_id": sid, "pricing_plan_version": version, "quantita": 1, "payment_status": "paid"})
    ent = {"plan": plan, "source": "purchased", "price_tier": tier, "year": year,
           "amount_net": net, "amount_vat": vat, "amount_gross": gross, "currency": (sess.get("currency") or "eur"),
           "stripe_price_id": md.get("price_id"), "stripe_payment_ref": pi, "stripe_session_id": sid,
           "invoice_id": None, "purchased_at": now_iso(), "upgrade_amount_paid": upgrade_paid,
           "pricing_plan_version": version}
    await db.events.update_one({"id": md.get("event_id")}, {"$set": {"entitlement": ent, "updated_at": now_iso()}})


@api.get("/event-plans/status")
async def events_plan_status(user: dict = Depends(require_admin)):
    org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0})
    sub = _sub_summary(org)
    trial = sub.get("status") == "trial" and sub.get("access") == "full"
    rows = await db.pricing_plans.find({"status": "active"}, {"_id": 0}).to_list(50)
    price_map = {(r["plan"], r["fascia"]): r["net"] for r in rows}
    evs = await db.events.find(oq(user), {"_id": 0}).sort("data_inizio", -1).to_list(2000)

    def pkg(p, kind, net):
        return {"plan": p, "kind": kind, "net": net, "vat": round(net * PRICING_VAT_RATE / 100, 2), "gross": round(net * (1 + PRICING_VAT_RATE / 100), 2)}

    out = []
    for ev in evs:
        di = ev.get("data_inizio") or ""
        year = int(di[:4]) if di[:4].isdigit() else None
        tier = compute_tier(await _events_in_year(user["org_id"], year)) if year else "small"
        ent = ev.get("entitlement") or {}
        purchased = ent.get("source") == "purchased"
        cur = ent.get("plan") or "free"
        eff = "premium" if trial else (cur if purchased else "free")
        options = []
        if purchased:
            already = float(ent.get("amount_net") or 0)
            ptier = ent.get("price_tier") or tier
            for p in PRICING_PLANS_LIST:
                if PLAN_RANK[p] > PLAN_RANK.get(cur, 0):
                    net = price_map.get((p, ptier))
                    if net is None:
                        continue
                    o = pkg(p, "upgrade", net)
                    o["diff"] = round(net - already, 2)
                    o["already_paid"] = already
                    options.append(o)
        else:
            for p in PRICING_PLANS_LIST:
                net = price_map.get((p, tier))
                if net is not None:
                    options.append(pkg(p, "purchase", net))
        out.append({
            "id": ev["id"], "nome": ev.get("nome"), "data_inizio": ev.get("data_inizio"),
            "current_plan": cur, "effective_plan": eff, "purchased": purchased,
            "readonly": (not trial) and (not purchased),
            "tier": (ent.get("price_tier") if purchased else tier), "year": year,
            "snapshot": ({"plan": ent.get("plan"), "net": ent.get("amount_net"), "gross": ent.get("amount_gross"),
                          "purchased_at": ent.get("purchased_at"), "tier": ent.get("price_tier"), "year": ent.get("year")} if purchased else None),
            "options": options})
    return {"trial": trial, "days_left": sub.get("days_left"), "status": sub.get("status"), "events": out}


@api.get("/event-plans/checkout-confirmation")
async def event_checkout_confirmation(session_id: str, user: dict = Depends(require_admin)):
    try:
        sess = stripe_sdk.checkout.Session.retrieve(session_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Sessione non trovata")
    md = sess.get("metadata") or {}
    if md.get("org_id") != user["org_id"]:
        raise HTTPException(status_code=403, detail="Sessione non associata all'organizzazione")
    paid = sess.get("payment_status") == "paid"
    if paid:
        await _activate_event_from_session(sess)  # attivazione server-side idempotente
    ev = await db.events.find_one({"id": md.get("event_id")}, {"_id": 0})
    return {"paid": paid, "plan": md.get("plan"), "kind": md.get("kind"),
            "event_id": md.get("event_id"), "event_name": (ev or {}).get("nome"),
            "current_plan": ((ev or {}).get("entitlement") or {}).get("plan")}


SAAS.update(subscriptions.build(db, {
    "require_admin": require_admin, "require_org_admin": require_org_admin, "require_superadmin": require_superadmin,
    "record_audit": record_audit, "ensure_customer": _ensure_stripe_customer, "billing_missing": _billing_missing,
    "record_invoice": _record_invoice, "emit_invoice": _emit_saas_invoice, "retry_invoices": _retry_saas_invoices,
    "stripe_mode": STRIPE_MODE, "app_url": APP_URL, "cron_secret": WEBHOOK_CRON_SECRET,
    "on_paid": lambda o, inv: PARTNER["on_subscription_paid"](o, inv)}))
PARTNER = partner_portal.build(db, {"hash_password": hash_password, "verify_password": verify_password, "person_name": TN.person_name,
                                    "require_superadmin": require_superadmin, "record_audit": record_audit, "saas_config": SAAS["get_config"]})
app.include_router(PARTNER["router"])
app.add_event_handler("startup", PARTNER["ensure_indexes"])
app.include_router(api)
app.include_router(SAAS["router"])
async def require_org_member(request: Request, user: dict = Depends(get_current_user)) -> dict:
    org_id, org_role = await _resolve_active_org(request, user)
    return {**user, "org_id": org_id, "org_role": org_role}


app.include_router(demo_slots.build_router(db, require_org_member, require_superadmin, record_audit, APP_URL))
app.include_router(home_widgets.build_router(db, require_admin, get_current_user, SAAS, _resolve_active_org), prefix="/api")
app.include_router(google_login.build_router(db, {"create_access_token": create_access_token, "set_auth_cookie": set_auth_cookie,
                                                   "verify_password": verify_password, "user_payload": user_payload,
                                                   "person_name": TN.person_name, "now_iso": now_iso,
                                                   "partner_identity": PARTNER["google_identity"]}), prefix="/api")
app.include_router(TN.build_router(db, require_superadmin, record_audit))
MKT.update(marketplace.build(db, {
    "require_admin": require_admin, "require_superadmin": require_superadmin, "record_audit": record_audit,
    "ensure_customer": _ensure_stripe_customer, "billing_missing": _billing_missing, "record_invoice": _record_invoice,
    "emit_invoice": _emit_saas_invoice, "stripe_mode": STRIPE_MODE}))
app.include_router(MKT["router"])
app.include_router(news.build_router(db, get_current_user, require_superadmin, record_audit))
app.include_router(video_support.build_router(db, require_admin, require_superadmin, record_audit, {
    "reserve": _credits_reserve, "settle": _credits_settle, "release": _credits_release,
    "ensure_setup": _ensure_credits_setup, "ensure_org": _ensure_org_credits}, SAAS))
app.include_router(brevo_org_lists.build_router(db, require_superadmin, record_audit))
app.add_middleware(CORSMiddleware,
                   allow_origins=[o for o in os.environ.get("CORS_ORIGINS", "").split(",") if o],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
