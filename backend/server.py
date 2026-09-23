from dotenv import load_dotenv
from pathlib import Path
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import re
import uuid
import logging
import secrets
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import List, Optional

import jwt
import bcrypt
import httpx
from fastapi import FastAPI, APIRouter, Request, Response, HTTPException, Depends, UploadFile, File
from fastapi.responses import RedirectResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr

import email_utils
import storage_utils
import gcal_utils

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

ADMIN_ROLES = {"admin", "member"}


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


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Accesso riservato agli amministratori")
    return user


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
            "role": u.get("role", "member"), "picture": u.get("picture", ""),
            "auth_provider": u.get("auth_provider", "password"), "person_id": u.get("person_id")}


@api.post("/auth/register")
async def register(body: RegisterIn, response: Response):
    email = body.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email già registrata")
    uid = f"user_{uuid.uuid4().hex[:12]}"
    await db.users.insert_one({"user_id": uid, "email": email, "name": body.name,
                               "password_hash": hash_password(body.password), "role": "member",
                               "auth_provider": "password", "picture": "", "active": True, "created_at": now_iso()})
    token = create_access_token(uid, email)
    set_auth_cookie(response, "access_token", token, 7 * 24 * 3600)
    u = await db.users.find_one({"user_id": uid}, {"_id": 0})
    return public_user(u)


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
    return public_user(user)


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
                                   "role": "member", "auth_provider": "google", "active": True,
                                   "picture": data.get("picture", ""), "created_at": now_iso()})
    else:
        uid = user["user_id"]
        await db.users.update_one({"user_id": uid}, {"$set": {"picture": data.get("picture", ""), "name": data.get("name", user.get("name"))}})
    session_token = data["session_token"]
    await db.user_sessions.insert_one({"user_id": uid, "session_token": session_token,
                                       "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
                                       "created_at": now_iso()})
    set_auth_cookie(response, "session_token", session_token, 7 * 24 * 3600)
    u = await db.users.find_one({"user_id": uid}, {"_id": 0})
    return public_user(u)


@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return public_user(user)


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
    return public_user(u)


# ---------------- entity models ----------------
class Event(BaseModel):
    nome: str
    edizione: Optional[str] = None
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


def _opt(model):
    class M(model):
        pass
    for name, f in M.model_fields.items():
        f.default = None
        f.default_factory = None
    M.model_rebuild(force=True)
    return M


def crud_routes(path, coll, model):
    upd_model = _opt(model)

    @api.get(f"/{path}", name=f"list_{path}")
    async def _l(evento_id: Optional[str] = None, user: dict = Depends(require_admin)):
        return await _list(coll, {"evento_id": evento_id} if evento_id else {})

    @api.post(f"/{path}", name=f"create_{path}")
    async def _c(body: model, user: dict = Depends(require_admin)):
        return await _create(coll, body.model_dump())

    @api.get(f"/{path}/{{item_id}}", name=f"get_{path}")
    async def _g(item_id: str, user: dict = Depends(require_admin)):
        return await _get(coll, item_id)

    @api.put(f"/{path}/{{item_id}}", name=f"update_{path}")
    async def _u(item_id: str, body: upd_model, user: dict = Depends(require_admin)):
        return await _update(coll, item_id, body.model_dump(exclude_unset=True))

    @api.delete(f"/{path}/{{item_id}}", name=f"delete_{path}")
    async def _d(item_id: str, user: dict = Depends(require_admin)):
        return await _delete(coll, item_id)


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


async def _company_contacts(company_id: str):
    rels = await db.person_companies.find({"company_id": company_id}, {"_id": 0}).to_list(500)
    have = {r["person_id"] for r in rels}
    out = []
    for r in rels:
        p = await db.persons.find_one({"id": r["person_id"]}, {"_id": 0})
        if p:
            out.append({"relation": r, "person": p})
    legacy = await db.persons.find({"azienda_id": company_id}, {"_id": 0}).to_list(500)
    for p in legacy:
        if p["id"] not in have:
            out.append({"relation": {"id": None, "company_id": company_id, "person_id": p["id"],
                                     "qualifica": p.get("ruolo"), "referente_principale": True, "legacy": True},
                        "person": p})
    return out


@api.get("/persons-enriched")
async def persons_enriched(admin: dict = Depends(require_admin)):
    persons = await _list("persons")
    rels = await db.person_companies.find({}, {"_id": 0}).to_list(10000)
    pres = await db.staff.find({}, {"_id": 0}).to_list(10000)
    companies = {c["id"]: c for c in await _list("companies")}
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
    docs = await db.persons.find({"$or": conds}, {"_id": 0}).limit(10).to_list(10)
    return {"matches": docs}


@api.get("/persons/{person_id}/detail")
async def person_detail(person_id: str, admin: dict = Depends(require_admin)):
    p = await _get("persons", person_id)
    rels = await db.person_companies.find({"person_id": person_id}, {"_id": 0}).to_list(200)
    companies = []
    seen = set()
    for r in rels:
        c = await db.companies.find_one({"id": r["company_id"]}, {"_id": 0})
        if c:
            companies.append({"relation": r, "company": c})
            seen.add(r["company_id"])
    if p.get("azienda_id") and p["azienda_id"] not in seen:
        c = await db.companies.find_one({"id": p["azienda_id"]}, {"_id": 0})
        if c:
            companies.append({"relation": {"id": None, "company_id": c["id"], "person_id": person_id,
                                           "qualifica": p.get("ruolo"), "referente_principale": True, "legacy": True},
                              "company": c})
    presences = await db.staff.find({"persona_id": person_id}, {"_id": 0}).to_list(300)
    events = []
    for pr in presences:
        e = await db.events.find_one({"id": pr["evento_id"]}, {"_id": 0})
        events.append({"presence": pr, "event": e})
    tids = {pr.get("team_id") for pr in presences if pr.get("team_id")}
    for t in await db.teams.find({"responsabile_id": person_id}, {"_id": 0}).to_list(100):
        tids.add(t["id"])
    teams = [t for t in [await db.teams.find_one({"id": tid}, {"_id": 0}) for tid in tids] if t]
    shifts = await db.shifts.find({"persona_id": person_id}, {"_id": 0}).to_list(300)
    activities = await db.activities.find({"persona_id": person_id}, {"_id": 0}).to_list(300)
    followups = await db.followups.find({"persona_id": person_id}, {"_id": 0}).to_list(300)
    return {"person": p, "companies": companies, "events": events, "teams": teams,
            "shifts": shifts, "activities": activities, "followups": followups}


@api.get("/companies/{company_id}/detail")
async def company_detail(company_id: str, admin: dict = Depends(require_admin)):
    c = await _get("companies", company_id)
    contacts = await _company_contacts(company_id)
    deals = await db.deals.find({"azienda_id": company_id}, {"_id": 0}).to_list(300)
    events = []
    seen = set()
    for d in deals:
        if d["evento_id"] in seen:
            continue
        seen.add(d["evento_id"])
        e = await db.events.find_one({"id": d["evento_id"]}, {"_id": 0})
        if e:
            events.append({"event": e, "tipo": d.get("tipo"), "fase": d.get("fase")})
    activities = await db.activities.find({"azienda_id": company_id}, {"_id": 0}).to_list(300)
    followups = await db.followups.find({"azienda_id": company_id}, {"_id": 0}).to_list(300)
    return {"company": c, "contacts": contacts, "deals": deals, "events": events,
            "activities": activities, "followups": followups}


@api.get("/companies/{company_id}/contacts")
async def get_company_contacts(company_id: str, admin: dict = Depends(require_admin)):
    return await _company_contacts(company_id)


@api.post("/companies/{company_id}/contacts")
async def add_company_contact(company_id: str, body: ContactIn, admin: dict = Depends(require_admin)):
    await _get("companies", company_id)
    if body.person_id:
        person = await db.persons.find_one({"id": body.person_id}, {"_id": 0})
        if not person:
            raise HTTPException(status_code=404, detail="Persona non trovata")
        pid = body.person_id
    else:
        if not body.nome:
            raise HTTPException(status_code=400, detail="Nome referente obbligatorio")
        person = await _create("persons", {"nome": body.nome, "cognome": body.cognome, "email": body.email,
                                           "telefono": body.telefono, "cellulare": body.cellulare, "ruolo": body.ruolo,
                                           "linkedin": body.linkedin, "azienda_id": company_id, "note": body.note,
                                           "invite_status": "non_invitato"})
        pid = person["id"]
    existing = await db.person_companies.find_one({"person_id": pid, "company_id": company_id})
    rel_data = {"person_id": pid, "company_id": company_id, "qualifica": body.ruolo, "ruolo": body.ruolo,
                "referente_principale": bool(body.referente_principale), "note": body.note}
    if existing:
        rel = await _update("person_companies", existing["id"], rel_data)
    else:
        rel = await _create("person_companies", rel_data)
    if body.referente_principale:
        await db.person_companies.update_many({"company_id": company_id, "id": {"$ne": rel["id"]}},
                                              {"$set": {"referente_principale": False}})
    return {"relation": rel, "person": person}


@api.put("/company-contacts/{rel_id}")
async def update_company_contact(rel_id: str, body: ContactUpdate, admin: dict = Depends(require_admin)):
    rel = await _update("person_companies", rel_id, body.model_dump(exclude_unset=True))
    if body.referente_principale:
        await db.person_companies.update_many({"company_id": rel["company_id"], "id": {"$ne": rel_id}},
                                              {"$set": {"referente_principale": False}})
    return rel


@api.delete("/company-contacts/{rel_id}")
async def delete_company_contact(rel_id: str, admin: dict = Depends(require_admin)):
    return await _delete("person_companies", rel_id)


# ---------------- person invite ----------------
class InviteIn(BaseModel):
    role: str = "volunteer"


class AccessIn(BaseModel):
    enabled: bool


@api.post("/persons/{person_id}/invite")
async def invite_person(person_id: str, body: InviteIn, admin: dict = Depends(require_admin)):
    person = await _get("persons", person_id)
    if not person.get("email"):
        raise HTTPException(status_code=400, detail="La persona non ha un'email")
    role = body.role if body.role in ("staff", "volunteer") else "volunteer"
    email = person["email"].lower()
    token = secrets.token_urlsafe(32)
    existing = await db.users.find_one({"email": email})
    if existing:
        await db.users.update_one({"email": email}, {"$set": {"person_id": person_id, "role": role,
                                                              "activation_token": token, "active": True,
                                                              "activation_expires": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()}})
    else:
        uid = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one({"user_id": uid, "email": email, "name": f"{person['nome']} {person.get('cognome','')}".strip(),
                                   "role": role, "auth_provider": "password", "person_id": person_id, "active": True,
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
    await db.persons.update_one({"id": person_id}, {"$set": {"invite_status": "invito_inviato", "user_role": role}})
    return {"ok": True, "email_sent": sent}


@api.put("/persons/{person_id}/access")
async def set_access(person_id: str, body: AccessIn, admin: dict = Depends(require_admin)):
    u = await db.users.find_one({"person_id": person_id})
    if not u:
        raise HTTPException(status_code=404, detail="Nessun account collegato")
    await db.users.update_one({"person_id": person_id}, {"$set": {"active": body.enabled}})
    await db.persons.update_one({"id": person_id}, {"$set": {"invite_status": "account_attivato" if body.enabled else "accesso_disabilitato"}})
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
    await db.files.insert_one({"id": fid, "storage_path": result["path"], "original_filename": file.filename,
                               "content_type": ctype, "size": result.get("size"), "is_deleted": False, "created_at": now_iso()})
    return {"id": fid, "url": f"/api/files/{fid}", "filename": file.filename}


@api.get("/files/{file_id}")
async def download(file_id: str, user: dict = Depends(get_current_user)):
    rec = await db.files.find_one({"id": file_id, "is_deleted": False}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="File non trovato")
    data, ctype = storage_utils.get_object(rec["storage_path"])
    return Response(content=data, media_type=rec.get("content_type", ctype))


# ---------------- dashboard / search / notifications ----------------
@api.get("/dashboard")
async def dashboard(evento_id: Optional[str] = None, admin: dict = Depends(require_admin)):
    ev_q = {} if not evento_id else {"id": evento_id}
    rel_q = {} if not evento_id else {"evento_id": evento_id}
    events = await db.events.find(ev_q, {"_id": 0}).to_list(5000)
    companies = await db.companies.find({}, {"_id": 0}).to_list(5000)
    persons = await db.persons.find({}, {"_id": 0}).to_list(5000)
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
    fus = await db.followups.find({"stato": {"$ne": "completato"}}, {"_id": 0}).to_list(3000)
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
    results = []
    for e in await db.events.find({"nome": rx}, {"_id": 0}).limit(6).to_list(6):
        results.append({"tipo": "evento", "id": e["id"], "label": e["nome"], "sub": e.get("citta", "")})
    for c in await db.companies.find({"nome": rx}, {"_id": 0}).limit(6).to_list(6):
        results.append({"tipo": "azienda", "id": c["id"], "label": c["nome"], "sub": c.get("settore", "")})
    for p in await db.persons.find({"$or": [{"nome": rx}, {"cognome": rx}, {"email": rx}]}, {"_id": 0}).limit(6).to_list(6):
        results.append({"tipo": "persona", "id": p["id"], "label": f"{p['nome']} {p.get('cognome','')}".strip(), "sub": p.get("ruolo", "")})
    return {"results": results}


# ---------------- settings ----------------
def default_settings():
    return {"id": "global",
            "tipologie_evento": ["Fiera", "Congresso", "Concerto", "Festival", "Conferenza", "Workshop", "Gala"],
            "settori": ["Tecnologia", "Food & Beverage", "Moda", "Automotive", "Finanza", "Media", "No Profit"],
            "ruoli_staff": ["Coordinatore", "Hostess", "Tecnico", "Sicurezza", "Accoglienza", "Logistica"],
            "aree_operative": ["Expo", "Palco", "Ingresso", "Ristoro", "Logistica", "Parcheggi", "Percorso"],
            "livelli_sponsorship": ["Main Sponsor", "Gold", "Silver", "Bronze", "Technical Partner"],
            "fasi_pipeline": ["prospect", "contattato", "proposta_inviata", "in_trattativa", "confermato", "perso"],
            "demo_disabled": False}


@api.get("/settings")
async def get_settings(admin: dict = Depends(require_admin)):
    doc = await db.settings.find_one({"id": "global"}, {"_id": 0})
    if not doc:
        doc = default_settings()
        await db.settings.insert_one(dict(doc))
    return doc


@api.put("/settings")
async def update_settings(body: dict, admin: dict = Depends(require_admin)):
    body.pop("_id", None)
    body["id"] = "global"
    await db.settings.update_one({"id": "global"}, {"$set": body}, upsert=True)
    return await db.settings.find_one({"id": "global"}, {"_id": 0})


USAGE_MAP = {"tipologie_evento": ("events", "tipologia"), "settori": ("companies", "settore"),
             "ruoli_staff": ("staff", "ruolo"), "aree_operative": ("staff", "area"),
             "livelli_sponsorship": ("deals", "livello")}


@api.get("/settings/usage")
async def settings_usage(list: str, value: str, admin: dict = Depends(require_admin)):
    m = USAGE_MAP.get(list)
    if not m:
        return {"count": 0}
    coll, field = m
    count = await db[coll].count_documents({field: value})
    return {"count": count}


# ---------------- Google Calendar ----------------
def _cal_state(user_id: str) -> str:
    return jwt.encode({"uid": user_id, "exp": datetime.now(timezone.utc) + timedelta(minutes=15)}, JWT_SECRET, algorithm=JWT_ALG)


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
    return {"authorization_url": gcal_utils.authorization_url(_cal_state(user["user_id"]))}


@api.get("/oauth/calendar/callback")
async def calendar_callback(code: str = "", state: str = ""):
    try:
        payload = jwt.decode(state, JWT_SECRET, algorithms=[JWT_ALG])
        uid = payload["uid"]
    except jwt.PyJWTError:
        return RedirectResponse(f"{APP_URL}/app?calendar=error")
    tokens = gcal_utils.exchange_code(code)
    if "access_token" not in tokens:
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
async def sync_event(event_id: str, user: dict = Depends(get_current_user)):
    e = await _get("events", event_id)
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
    presences = await db.staff.find({"persona_id": pid}, {"_id": 0}).to_list(500)
    out = []
    for pr in presences:
        ev = await db.events.find_one({"id": pr["evento_id"]}, {"_id": 0})
        if ev:
            out.append({"event": ev, "presence": pr})
    out.sort(key=lambda x: x["event"].get("data_inizio") or "9999")
    return {"events": out}


@api.get("/me/events/{event_id}")
async def my_event_detail(event_id: str, user: dict = Depends(get_current_user)):
    pid = user.get("person_id")
    presence = await db.staff.find_one({"persona_id": pid, "evento_id": event_id}, {"_id": 0})
    if not presence:
        raise HTTPException(status_code=404, detail="Evento non trovato")  # object check
    event = await db.events.find_one({"id": event_id}, {"_id": 0})
    my_shifts = await db.shifts.find({"persona_id": pid, "evento_id": event_id}, {"_id": 0}).to_list(200)
    my_shifts.sort(key=lambda s: (s.get("data") or "", s.get("ora_inizio") or ""))
    team = None
    colleagues = []
    if presence.get("team_id"):
        team = await db.teams.find_one({"id": presence["team_id"]}, {"_id": 0})
        mates = await db.staff.find({"team_id": presence["team_id"], "evento_id": event_id}, {"_id": 0}).to_list(200)
        for m in mates:
            p = await db.persons.find_one({"id": m["persona_id"]}, {"_id": 0})
            if p:
                colleagues.append(_safe_colleague(p, m, team))
    leader = None
    if team and team.get("responsabile_id"):
        lp = await db.persons.find_one({"id": team["responsabile_id"]}, {"_id": 0})
        if lp:
            leader = {"nome": lp.get("nome"), "cognome": lp.get("cognome"), "foto_url": lp.get("foto_url")}
    maps = await db.event_maps.find({"evento_id": event_id}, {"_id": 0}).to_list(200)
    prio = [m for m in maps if m.get("team_id") == presence.get("team_id") or m.get("area") == presence.get("area")]
    others = [m for m in maps if m not in prio]
    return {"event": event, "presence": presence, "shifts": my_shifts, "team": team,
            "team_leader": leader, "colleagues": colleagues, "maps": prio + others}


@api.get("/me/shifts")
async def my_shifts(user: dict = Depends(get_current_user)):
    pid = user.get("person_id")
    if not pid:
        return {"shifts": []}
    s = await db.shifts.find({"persona_id": pid}, {"_id": 0}).to_list(500)
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


class LeadUpdate(BaseModel):
    stato: Optional[str] = None
    note: Optional[str] = None


@api.post("/leads")
async def create_lead(body: Lead):
    if not body.privacy:
        raise HTTPException(status_code=400, detail="È necessario accettare la privacy policy")
    doc = await _create("leads", {**body.model_dump(), "stato": "nuovo", "note": ""})
    try:
        await email_utils.send_email(to=os.environ["ADMIN_EMAIL"], subject="Nuova richiesta demo CRMEvent",
                                     html=email_utils.link_email(name="Michele",
                                                                 intro=f"Nuova richiesta demo da {body.nome} {body.cognome or ''} ({body.organizzazione or '-'}) — email {body.email}, tel {body.telefono or '-'}. Tipologia: {body.tipologia_eventi or '-'}, eventi/anno: {body.eventi_anno or '-'}.",
                                                                 cta_label="Apri CRMEvent", url=f"{APP_URL}/lead",
                                                                 footer_note="Gestisci il lead nella sezione Lead."))
    except Exception as e:
        logger.error(f"lead notify failed: {e}")
    return {"ok": True, "id": doc["id"]}


@api.get("/leads")
async def list_leads(admin: dict = Depends(require_admin)):
    return await _list("leads")


@api.put("/leads/{lead_id}")
async def update_lead(lead_id: str, body: LeadUpdate, admin: dict = Depends(require_admin)):
    return await _update("leads", lead_id, body.model_dump(exclude_unset=True))


@api.delete("/leads/{lead_id}")
async def delete_lead(lead_id: str, admin: dict = Depends(require_admin)):
    return await _delete("leads", lead_id)


# ---------------- admin reset ----------------
OPERATIONAL = ["events", "companies", "persons", "deals", "staff", "teams", "shifts",
               "event_maps", "activities", "followups", "calendar_event_links", "files",
               "calendar_connections", "person_companies"]


@api.post("/admin/reset-data")
async def reset_data(admin: dict = Depends(require_admin)):
    for c in OPERATIONAL:
        await db[c].delete_many({})
    await db.users.delete_many({"role": {"$in": ["staff", "volunteer"]}})
    await db.settings.update_one({"id": "global"}, {"$set": {"demo_disabled": True}}, upsert=True)
    counts = {c: await db[c].count_documents({}) for c in OPERATIONAL}
    return {"ok": True, "counts": counts, "demo_disabled": True}


# ---------------- seed ----------------
async def seed_admin():
    email = os.environ["ADMIN_EMAIL"].lower()
    pw = os.environ["ADMIN_PASSWORD"]
    existing = await db.users.find_one({"email": email})
    if not existing:
        await db.users.insert_one({"user_id": f"user_{uuid.uuid4().hex[:12]}", "email": email, "name": "Michele Manara",
                                   "password_hash": hash_password(pw), "role": "admin", "auth_provider": "password",
                                   "picture": "", "active": True, "created_at": now_iso()})
    else:
        upd = {"role": "admin", "active": True}
        if existing.get("password_hash") and not verify_password(pw, existing["password_hash"]):
            upd["password_hash"] = hash_password(pw)
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


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.user_sessions.create_index("session_token")
    try:
        storage_utils.init_storage()
        logger.info("Storage initialized")
    except Exception as e:
        logger.error(f"Storage init failed: {e}")
    await seed_admin()
    await seed_demo()
    await migrate_person_companies()
    creds = ROOT_DIR.parent / "memory" / "test_credentials.md"
    try:
        creds.write_text(
            f"# Test Credentials\n\n## Admin (email/password)\n- Email: {os.environ['ADMIN_EMAIL']}\n- Password: {os.environ['ADMIN_PASSWORD']}\n- Role: admin\n\n## Roles\n- admin/member: CRM amministrativo\n- staff/volunteer: solo area personale (/area), collegati a una Persona via invito\n\n## Auth endpoints\n- POST /api/auth/register, /api/auth/login, /api/auth/logout\n- POST /api/auth/change-password, /api/auth/forgot-password, /api/auth/reset-password\n- POST /api/auth/activate (invito), /api/auth/session (Google login)\n\n## Notes\n- Google Calendar OAuth requires GOOGLE_CLIENT_ID/SECRET in .env (currently empty).\n- Staff/volunteer users are created via POST /api/persons/{{id}}/invite.\n"
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
