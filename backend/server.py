from dotenv import load_dotenv
from pathlib import Path
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import uuid
import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import List, Optional

import jwt
import bcrypt
import httpx
from fastapi import FastAPI, APIRouter, Request, Response, HTTPException, Depends
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

JWT_SECRET = os.environ['JWT_SECRET']
JWT_ALG = "HS256"
EMERGENT_SESSION_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"

app = FastAPI(title="CRMEvent API")
api = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("crmevent")


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
    # try google session token first
    sess = await db.user_sessions.find_one({"session_token": token})
    if sess:
        exp = sess.get("expires_at")
        if isinstance(exp, str):
            exp = datetime.fromisoformat(exp)
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp > datetime.now(timezone.utc):
            return await db.users.find_one({"user_id": sess["user_id"]}, {"_id": 0, "password_hash": 0})
    # try jwt
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
    return user


# ---------------- generic crud ----------------
async def _create(coll: str, data: dict) -> dict:
    doc = {**data, "id": new_id(), "created_at": now_iso(), "updated_at": now_iso()}
    await db[coll].insert_one(doc)
    doc.pop("_id", None)
    return doc


async def _list(coll: str, query: dict = None) -> List[dict]:
    return await db[coll].find(query or {}, {"_id": 0}).sort("created_at", -1).to_list(3000)


async def _get(coll: str, _id: str) -> dict:
    doc = await db[coll].find_one({"id": _id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Elemento non trovato")
    return doc


async def _update(coll: str, _id: str, data: dict) -> dict:
    clean = {k: v for k, v in data.items() if v is not None}
    clean["updated_at"] = now_iso()
    res = await db[coll].update_one({"id": _id}, {"$set": clean})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Elemento non trovato")
    return await _get(coll, _id)


async def _delete(coll: str, _id: str) -> dict:
    await db[coll].delete_one({"id": _id})
    return {"ok": True}


# ---------------- auth models ----------------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    name: str


class LoginIn(BaseModel):
    email: EmailStr
    password: str


# ---------------- auth endpoints ----------------
@api.post("/auth/register")
async def register(body: RegisterIn, response: Response):
    email = body.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email già registrata")
    uid = f"user_{uuid.uuid4().hex[:12]}"
    await db.users.insert_one({
        "user_id": uid, "email": email, "name": body.name,
        "password_hash": hash_password(body.password), "role": "member",
        "auth_provider": "password", "picture": "", "created_at": now_iso(),
    })
    token = create_access_token(uid, email)
    set_auth_cookie(response, "access_token", token, 7 * 24 * 3600)
    return {"user_id": uid, "email": email, "name": body.name, "role": "member", "picture": ""}


@api.post("/auth/login")
async def login(body: LoginIn, response: Response):
    email = body.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or not user.get("password_hash") or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Credenziali non valide")
    token = create_access_token(user["user_id"], email)
    set_auth_cookie(response, "access_token", token, 7 * 24 * 3600)
    return {"user_id": user["user_id"], "email": email, "name": user.get("name"),
            "role": user.get("role", "member"), "picture": user.get("picture", "")}


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
        await db.users.insert_one({
            "user_id": uid, "email": email, "name": data.get("name", email),
            "role": "member", "auth_provider": "google",
            "picture": data.get("picture", ""), "created_at": now_iso(),
        })
    else:
        uid = user["user_id"]
        await db.users.update_one({"user_id": uid},
                                  {"$set": {"picture": data.get("picture", ""), "name": data.get("name", user.get("name"))}})
    session_token = data["session_token"]
    await db.user_sessions.insert_one({
        "user_id": uid, "session_token": session_token,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "created_at": now_iso(),
    })
    set_auth_cookie(response, "session_token", session_token, 7 * 24 * 3600)
    u = await db.users.find_one({"user_id": uid}, {"_id": 0, "password_hash": 0})
    return u


@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user


@api.post("/auth/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if token:
        await db.user_sessions.delete_one({"session_token": token})
    response.delete_cookie("session_token", path="/")
    response.delete_cookie("access_token", path="/")
    return {"ok": True}


# ---------------- entity models ----------------
class Event(BaseModel):
    nome: str
    edizione: Optional[str] = None
    tipologia: Optional[str] = None
    data_inizio: Optional[str] = None
    data_fine: Optional[str] = None
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
    note: Optional[str] = None


class Company(BaseModel):
    nome: str
    settore: Optional[str] = None
    partita_iva: Optional[str] = None
    sito_web: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    citta: Optional[str] = None
    provincia: Optional[str] = None
    regione: Optional[str] = None
    nazione: Optional[str] = "Italia"
    tipo: Optional[str] = "azienda"
    note: Optional[str] = None


class Person(BaseModel):
    nome: str
    cognome: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    ruolo: Optional[str] = None
    azienda_id: Optional[str] = None
    citta: Optional[str] = None
    note: Optional[str] = None


class Deal(BaseModel):  # sponsor & partner relation
    azienda_id: str
    evento_id: str
    tipo: Optional[str] = "sponsor"          # sponsor / partner / fornitore / prospect
    fase: Optional[str] = "prospect"          # pipeline stage
    valore: Optional[float] = 0
    valore_confermato: Optional[float] = 0
    referente_id: Optional[str] = None
    stato: Optional[str] = "aperta"
    note: Optional[str] = None


class StaffMember(BaseModel):
    persona_id: str
    evento_id: str
    categoria: Optional[str] = "staff"        # staff / collaboratore / volontario
    ruolo: Optional[str] = None
    stato: Optional[str] = "invitato"         # invitato / confermato / da_riconfermare / rifiutato
    turno: Optional[str] = None
    turno_coperto: Optional[bool] = True
    note: Optional[str] = None


class Activity(BaseModel):
    titolo: str
    tipo: Optional[str] = "generica"          # chiamata / email / meeting / task
    evento_id: Optional[str] = None
    azienda_id: Optional[str] = None
    persona_id: Optional[str] = None
    data: Optional[str] = None
    stato: Optional[str] = "da_fare"          # da_fare / completata
    note: Optional[str] = None


class Followup(BaseModel):
    titolo: str
    evento_id: Optional[str] = None
    azienda_id: Optional[str] = None
    persona_id: Optional[str] = None
    scadenza: Optional[str] = None
    priorita: Optional[str] = "media"
    stato: Optional[str] = "aperto"           # aperto / completato
    note: Optional[str] = None


def crud_routes(path: str, coll: str, model, update_model):
    @api.get(f"/{path}", name=f"list_{path}")
    async def _l(evento_id: Optional[str] = None, user: dict = Depends(get_current_user)):
        q = {"evento_id": evento_id} if evento_id else {}
        return await _list(coll, q)

    @api.post(f"/{path}", name=f"create_{path}")
    async def _c(body: model, user: dict = Depends(get_current_user)):
        return await _create(coll, body.model_dump())

    @api.get(f"/{path}/{{item_id}}", name=f"get_{path}")
    async def _g(item_id: str, user: dict = Depends(get_current_user)):
        return await _get(coll, item_id)

    @api.put(f"/{path}/{{item_id}}", name=f"update_{path}")
    async def _u(item_id: str, body: update_model, user: dict = Depends(get_current_user)):
        return await _update(coll, item_id, body.model_dump(exclude_unset=True))

    @api.delete(f"/{path}/{{item_id}}", name=f"delete_{path}")
    async def _d(item_id: str, user: dict = Depends(get_current_user)):
        return await _delete(coll, item_id)


class EventU(Event):
    nome: Optional[str] = None
class CompanyU(Company):
    nome: Optional[str] = None
class PersonU(Person):
    nome: Optional[str] = None
class DealU(Deal):
    azienda_id: Optional[str] = None
    evento_id: Optional[str] = None
class StaffU(StaffMember):
    persona_id: Optional[str] = None
    evento_id: Optional[str] = None
class ActivityU(Activity):
    titolo: Optional[str] = None
class FollowupU(Followup):
    titolo: Optional[str] = None


crud_routes("events", "events", Event, EventU)
crud_routes("companies", "companies", Company, CompanyU)
crud_routes("persons", "persons", Person, PersonU)
crud_routes("deals", "deals", Deal, DealU)
crud_routes("staff", "staff", StaffMember, StaffU)
crud_routes("activities", "activities", Activity, ActivityU)
crud_routes("followups", "followups", Followup, FollowupU)


# ---------------- dashboard ----------------
@api.get("/dashboard")
async def dashboard(evento_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    ev_q = {} if not evento_id else {"id": evento_id}
    rel_q = {} if not evento_id else {"evento_id": evento_id}
    events = await db.events.find(ev_q, {"_id": 0}).to_list(3000)
    companies = await db.companies.find({}, {"_id": 0}).to_list(3000)
    persons = await db.persons.find({}, {"_id": 0}).to_list(3000)
    deals = await db.deals.find(rel_q, {"_id": 0}).to_list(3000)
    staff = await db.staff.find(rel_q, {"_id": 0}).to_list(3000)
    activities = await db.activities.find(rel_q, {"_id": 0}).to_list(3000)
    followups = await db.followups.find(rel_q, {"_id": 0}).to_list(3000)

    today = datetime.now(timezone.utc).date().isoformat()

    def is_future(e):
        return (e.get("data_inizio") or "") > today

    eventi_attivi = len([e for e in events if e.get("stato") == "attivo"])
    eventi_prossimi = len([e for e in events if is_future(e) and e.get("stato") != "concluso"])
    eventi_conclusi = len([e for e in events if e.get("stato") == "concluso"])

    prospect = len([c for c in companies if c.get("tipo") == "prospect"]) + \
        len([d for d in deals if d.get("tipo") == "prospect"])
    nuovi_contatti = len([p for p in persons if (p.get("created_at") or "")[:10] >= (datetime.now(timezone.utc).date() - timedelta(days=30)).isoformat()])

    trattative_aperte = len([d for d in deals if d.get("stato") == "aperta" and d.get("fase") not in ("confermato", "perso")])
    proposte_inviate = len([d for d in deals if d.get("fase") == "proposta_inviata"])
    sponsor_confermati = len([d for d in deals if d.get("fase") == "confermato"])
    valore_pipeline = sum(float(d.get("valore") or 0) for d in deals if d.get("fase") != "perso")
    valore_confermato = sum(float(d.get("valore_confermato") or d.get("valore") or 0) for d in deals if d.get("fase") == "confermato")

    fu_oggi = len([f for f in followups if (f.get("scadenza") or "")[:10] == today and f.get("stato") != "completato"])
    fu_scaduti = len([f for f in followups if (f.get("scadenza") or "9999")[:10] < today and f.get("stato") != "completato"])
    fu_completate = len([f for f in followups if f.get("stato") == "completato"])
    att_prossime = len([a for a in activities if a.get("stato") == "da_fare"])
    att_completate = len([a for a in activities if a.get("stato") == "completata"])

    staff_confermati = len([s for s in staff if s.get("categoria") in ("staff", "collaboratore") and s.get("stato") == "confermato"])
    volontari_confermati = len([s for s in staff if s.get("categoria") == "volontario" and s.get("stato") == "confermato"])
    da_riconfermare = len([s for s in staff if s.get("stato") == "da_riconfermare"])
    turni_scoperti = len([s for s in staff if s.get("turno_coperto") is False])

    # pipeline breakdown for chart
    fasi = ["prospect", "contattato", "proposta_inviata", "in_trattativa", "confermato", "perso"]
    pipeline_chart = [{"fase": f, "count": len([d for d in deals if d.get("fase") == f]),
                       "valore": sum(float(d.get("valore") or 0) for d in deals if d.get("fase") == f)} for f in fasi]

    tipi = {}
    for d in deals:
        tipi[d.get("tipo", "sponsor")] = tipi.get(d.get("tipo", "sponsor"), 0) + 1
    tipo_chart = [{"tipo": k, "count": v} for k, v in tipi.items()]

    return {
        "eventi": {"attivi": eventi_attivi, "prossimi": eventi_prossimi, "conclusi": eventi_conclusi, "totali": len(events)},
        "crm": {"aziende": len(companies), "persone": len(persons), "nuovi_contatti": nuovi_contatti, "prospect": prospect},
        "commerciale": {"trattative_aperte": trattative_aperte, "proposte_inviate": proposte_inviate,
                        "sponsor_confermati": sponsor_confermati, "valore_pipeline": valore_pipeline,
                        "valore_confermato": valore_confermato},
        "attivita": {"followup_oggi": fu_oggi, "followup_scaduti": fu_scaduti,
                     "prossime": att_prossime, "completate": att_completate + fu_completate},
        "staff": {"staff_confermati": staff_confermati, "volontari_confermati": volontari_confermati,
                  "da_riconfermare": da_riconfermare, "turni_scoperti": turni_scoperti},
        "pipeline_chart": pipeline_chart,
        "tipo_chart": tipo_chart,
    }


@api.get("/notifications")
async def notifications(user: dict = Depends(get_current_user)):
    today = datetime.now(timezone.utc).date().isoformat()
    fus = await db.followups.find({"stato": {"$ne": "completato"}}, {"_id": 0}).to_list(2000)
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
async def search(q: str, user: dict = Depends(get_current_user)):
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
@api.get("/settings")
async def get_settings(user: dict = Depends(get_current_user)):
    doc = await db.settings.find_one({"id": "global"}, {"_id": 0})
    if not doc:
        doc = default_settings()
        await db.settings.insert_one(doc)
        doc.pop("_id", None)
    return doc


@api.put("/settings")
async def update_settings(body: dict, user: dict = Depends(get_current_user)):
    body["id"] = "global"
    await db.settings.update_one({"id": "global"}, {"$set": body}, upsert=True)
    return await db.settings.find_one({"id": "global"}, {"_id": 0})


def default_settings():
    return {
        "id": "global",
        "tipologie_evento": ["Fiera", "Congresso", "Concerto", "Festival", "Conferenza", "Workshop", "Gala"],
        "settori": ["Tecnologia", "Food & Beverage", "Moda", "Automotive", "Finanza", "Media", "No Profit"],
        "ruoli_staff": ["Coordinatore", "Hostess", "Tecnico", "Sicurezza", "Accoglienza", "Logistica"],
        "fasi_pipeline": ["prospect", "contattato", "proposta_inviata", "in_trattativa", "confermato", "perso"],
    }


# ---------------- seed ----------------
async def seed_admin():
    email = os.environ["ADMIN_EMAIL"].lower()
    pw = os.environ["ADMIN_PASSWORD"]
    existing = await db.users.find_one({"email": email})
    if not existing:
        await db.users.insert_one({
            "user_id": f"user_{uuid.uuid4().hex[:12]}", "email": email, "name": "Michele Manara",
            "password_hash": hash_password(pw), "role": "admin", "auth_provider": "password",
            "picture": "", "created_at": now_iso(),
        })
        logger.info("Admin seeded")
    elif existing.get("password_hash") and not verify_password(pw, existing["password_hash"]):
        await db.users.update_one({"email": email}, {"$set": {"password_hash": hash_password(pw), "role": "admin"}})


async def seed_demo():
    if await db.events.count_documents({}) > 0:
        return
    logger.info("Seeding demo data...")
    await db.settings.update_one({"id": "global"}, {"$set": default_settings()}, upsert=True)

    async def ins(coll, data):
        doc = {**data, "id": new_id(), "created_at": now_iso(), "updated_at": now_iso()}
        await db[coll].insert_one(doc)
        return doc["id"]

    ev1 = await ins("events", {"nome": "Tech Summit Milano", "edizione": "2026", "tipologia": "Congresso",
                               "data_inizio": "2026-09-15", "data_fine": "2026-09-17", "localita": "MiCo Milano",
                               "citta": "Milano", "provincia": "MI", "regione": "Lombardia", "nazione": "Italia",
                               "organizzatore": "CRMEvent Agency", "responsabile": "Michele Manara",
                               "sito_web": "https://techsummit.it", "email": "info@techsummit.it", "telefono": "+39 02 1234567",
                               "partecipanti_previsti": 3500, "budget": 450000, "stato": "attivo",
                               "note": "Evento di punta sul digitale."})
    ev2 = await ins("events", {"nome": "Green Food Festival", "edizione": "2026", "tipologia": "Festival",
                               "data_inizio": "2026-07-04", "data_fine": "2026-07-06", "localita": "Parco Dora",
                               "citta": "Torino", "provincia": "TO", "regione": "Piemonte", "nazione": "Italia",
                               "organizzatore": "CRMEvent Agency", "responsabile": "Laura Bianchi",
                               "sito_web": "https://greenfood.it", "email": "info@greenfood.it", "telefono": "+39 011 987654",
                               "partecipanti_previsti": 12000, "budget": 220000, "stato": "attivo",
                               "note": "Festival del cibo sostenibile."})
    ev3 = await ins("events", {"nome": "Gala della Moda", "edizione": "2025", "tipologia": "Gala",
                               "data_inizio": "2025-11-20", "data_fine": "2025-11-20", "localita": "Palazzo Reale",
                               "citta": "Napoli", "provincia": "NA", "regione": "Campania", "nazione": "Italia",
                               "organizzatore": "CRMEvent Agency", "responsabile": "Marco Rossi",
                               "partecipanti_previsti": 600, "budget": 180000, "stato": "concluso",
                               "note": "Edizione conclusa con successo."})

    comps = []
    comp_data = [
        ("TechNova S.p.A.", "Tecnologia", "prospect"), ("BioGusto Srl", "Food & Beverage", "azienda"),
        ("Moda Italia Group", "Moda", "azienda"), ("AutoDrive Motors", "Automotive", "prospect"),
        ("FinCore Bank", "Finanza", "azienda"), ("MediaWave", "Media", "azienda"),
        ("EcoFuture Onlus", "No Profit", "azienda"), ("Cloudbyte Solutions", "Tecnologia", "prospect"),
    ]
    for nome, sett, tipo in comp_data:
        cid = await ins("companies", {"nome": nome, "settore": sett, "tipo": tipo,
                                      "sito_web": f"https://{nome.split()[0].lower()}.it",
                                      "email": f"info@{nome.split()[0].lower()}.it", "telefono": "+39 02 0000000",
                                      "citta": "Milano", "provincia": "MI", "regione": "Lombardia", "nazione": "Italia"})
        comps.append(cid)

    persons = []
    p_data = [
        ("Giulia", "Ferrari", "Marketing Manager", 0), ("Luca", "Esposito", "CEO", 1),
        ("Sara", "Colombo", "Sponsorship Lead", 2), ("Andrea", "Romano", "Direttore Vendite", 3),
        ("Chiara", "Greco", "Event Manager", 4), ("Matteo", "Bruno", "CFO", 5),
        ("Elena", "Gallo", "Responsabile CSR", 6), ("Davide", "Costa", "CTO", 7),
        ("Francesca", "Rizzo", "Volontaria", None), ("Simone", "Marino", "Tecnico Audio", None),
    ]
    for nome, cognome, ruolo, cidx in p_data:
        pid = await ins("persons", {"nome": nome, "cognome": cognome, "ruolo": ruolo,
                                    "email": f"{nome.lower()}.{cognome.lower()}@mail.it", "telefono": "+39 333 0000000",
                                    "azienda_id": comps[cidx] if cidx is not None else None, "citta": "Milano"})
        persons.append(pid)

    deals_data = [
        (0, ev1, "sponsor", "confermato", 60000, 60000, 0), (1, ev2, "partner", "in_trattativa", 25000, 0, 1),
        (2, ev1, "sponsor", "proposta_inviata", 40000, 0, 2), (3, ev1, "prospect", "contattato", 30000, 0, 3),
        (4, ev1, "sponsor", "confermato", 80000, 80000, 5), (5, ev2, "partner", "proposta_inviata", 15000, 0, 4),
        (7, ev1, "prospect", "prospect", 20000, 0, 7), (6, ev2, "sponsor", "in_trattativa", 12000, 0, 6),
    ]
    for cidx, ev, tipo, fase, val, conf, pidx in deals_data:
        await ins("deals", {"azienda_id": comps[cidx], "evento_id": ev, "tipo": tipo, "fase": fase,
                            "valore": val, "valore_confermato": conf, "referente_id": persons[pidx],
                            "stato": "aperta" if fase not in ("confermato", "perso") else "chiusa"})

    staff_data = [
        (4, ev1, "staff", "Coordinatore", "confermato", "15-17 Sett 09:00-18:00", True),
        (9, ev1, "collaboratore", "Tecnico", "confermato", "15 Sett 07:00-20:00", True),
        (8, ev2, "volontario", "Accoglienza", "confermato", "04 Lug 10:00-16:00", True),
        (8, ev1, "volontario", "Logistica", "da_riconfermare", "16 Sett 08:00-14:00", False),
        (9, ev2, "collaboratore", "Tecnico", "invitato", "05 Lug 09:00-19:00", False),
    ]
    for pidx, ev, cat, ruolo, stato, turno, coperto in staff_data:
        await ins("staff", {"persona_id": persons[pidx], "evento_id": ev, "categoria": cat, "ruolo": ruolo,
                            "stato": stato, "turno": turno, "turno_coperto": coperto})

    today = datetime.now(timezone.utc).date()
    act_data = [
        ("Chiamata sponsor TechNova", "chiamata", ev1, 0, 0, "da_fare"),
        ("Invio proposta Moda Italia", "email", ev1, 2, 2, "completata"),
        ("Meeting logistica festival", "meeting", ev2, None, 4, "da_fare"),
    ]
    for tit, tipo, ev, cidx, pidx, stato in act_data:
        await ins("activities", {"titolo": tit, "tipo": tipo, "evento_id": ev,
                                 "azienda_id": comps[cidx] if cidx is not None else None,
                                 "persona_id": persons[pidx], "data": today.isoformat(), "stato": stato})

    fu_data = [
        ("Ricontattare AutoDrive Motors", ev1, 3, 3, (today - timedelta(days=2)).isoformat(), "alta"),
        ("Follow-up proposta CloudByte", ev1, 7, 7, today.isoformat(), "media"),
        ("Confermare budget BioGusto", ev2, 1, 1, (today + timedelta(days=3)).isoformat(), "media"),
        ("Verifica contratto FinCore", ev1, 4, 5, (today - timedelta(days=1)).isoformat(), "alta"),
    ]
    for tit, ev, cidx, pidx, sc, pr in fu_data:
        await ins("followups", {"titolo": tit, "evento_id": ev, "azienda_id": comps[cidx],
                               "persona_id": persons[pidx], "scadenza": sc, "priorita": pr, "stato": "aperto"})
    logger.info("Demo data seeded")


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.user_sessions.create_index("session_token")
    await seed_admin()
    await seed_demo()
    creds = ROOT_DIR.parent / "memory" / "test_credentials.md"
    try:
        creds.write_text(
            f"# Test Credentials\n\n## Admin (email/password)\n- Email: {os.environ['ADMIN_EMAIL']}\n- Password: {os.environ['ADMIN_PASSWORD']}\n- Role: admin\n\n## Auth endpoints\n- POST /api/auth/register\n- POST /api/auth/login\n- POST /api/auth/session (Google, header X-Session-ID)\n- GET /api/auth/me\n- POST /api/auth/logout\n\n## Google Auth\n- Emergent-managed Google login. Test users created dynamically on first login.\n"
        )
    except Exception as e:
        logger.warning(f"creds write failed: {e}")


@app.on_event("shutdown")
async def shutdown():
    client.close()


app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in os.environ.get("CORS_ORIGINS", "").split(",") if o],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
