"""Gestione Società (Marketplace "gestione-societa"): soci e tesserati, tesseramenti, quote, certificati medici, scadenze, enti e federazioni.
Accesso: solo Admin e utenti dell'organizzazione con il modulo attivo (acquisto o attivazione gratuita). Dati sempre filtrati per org_id."""
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

import storage_utils

SERVICE_KEY = "gestione-societa"
SOON_DAYS = 30
MAX_FILE = 10 * 1024 * 1024
TIPI_SOCIO = {"socio": "Socio", "tesserato": "Tesserato", "socio_tesserato": "Socio e tesserato"}
QUALIFICHE = {"atleta": "Atleta", "tecnico": "Tecnico/Allenatore", "dirigente": "Dirigente", "socio_ordinario": "Socio ordinario", "volontario": "Volontario", "altro": "Altro"}
STATI_SOCIO = {"attivo": "Attivo", "sospeso": "Sospeso", "cessato": "Cessato"}
TIPI_CERT = {"agonistico": "Agonistico", "non_agonistico": "Non agonistico", "altro": "Altro"}
METODI = {"contanti": "Contanti", "bonifico": "Bonifico", "carta": "Carta", "pos": "POS", "altro": "Altro"}
DATE_RX = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAGIC = [(b"%PDF-", "pdf", "application/pdf"), (b"\xff\xd8\xff", "jpg", "image/jpeg"), (b"\x89PNG\r\n\x1a\n", "png", "image/png"),
         (b"GIF8", "gif", "image/gif"), (b"RIFF", "webp", "image/webp")]
EMAIL_RX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Anagrafica unica: questi campi vivono solo in db.persons (condivisi con Staff / Volontari); asd_soci tiene i dati associativi.
SHARED = ("nome", "cognome", "codice_fiscale", "data_nascita", "luogo_nascita", "sesso", "email", "cellulare", "indirizzo", "cap", "citta", "provincia", "nazione", "taglia")
ASSOC = ("tipo", "qualifica", "stato", "data_iscrizione", "numero_socio", "note")
TIPI_ENTE = {"federazione": "Federazione", "eps": "Ente di promozione sportiva", "altro": "Altro organismo"}
ENTI_KEY = "enti_federazioni"  # elenco per organizzazione nel documento settings (Gestione menu a tendina)
ENTI_DEFAULT = [("eps", s, n) for s, n in (
    ("CSI", "Centro Sportivo Italiano"), ("UISP", "Unione Italiana Sport Per tutti"), ("AICS", "Associazione Italiana Cultura Sport"),
    ("ACSI", "Associazione di Cultura Sport e Tempo Libero"), ("ASC", "Attività Sportive Confederate"), ("ASI", "Associazioni Sportive e Sociali Italiane"),
    ("CSEN", "Centro Sportivo Educativo Nazionale"), ("CSAIN", "Centri Sportivi Aziendali e Industriali"), ("ENDAS", "Ente Nazionale Democratico di Azione Sociale"),
    ("MSP Italia", "Movimento Sportivo Popolare Italia"), ("OPES", "Organizzazione Per l'Educazione allo Sport"), ("PGS", "Polisportive Giovanili Salesiane"),
    ("US ACLI", "Unione Sportiva ACLI"))] + [("federazione", s, n) for s, n in (
    ("FIDAL", "Federazione Italiana di Atletica Leggera"), ("FITRI", "Federazione Italiana Triathlon"), ("FIN", "Federazione Italiana Nuoto"),
    ("FCI", "Federazione Ciclistica Italiana"), ("FITP", "Federazione Italiana Tennis e Padel"), ("FIGC", "Federazione Italiana Giuoco Calcio"),
    ("FIP", "Federazione Italiana Pallacanestro"), ("FIPAV", "Federazione Italiana Pallavolo"), ("FISI", "Federazione Italiana Sport Invernali"),
    ("FIS", "Federazione Italiana Scherma"), ("FGI", "Federazione Ginnastica d'Italia"), ("FICK", "Federazione Italiana Canoa Kayak"),
    ("FIC", "Federazione Italiana Canottaggio"))]


def ente_label(e: dict) -> str:
    return f"{e['sigla']} – {e['nome']}" if e.get("nome") else e["sigla"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bad(field: str, message: str):
    raise HTTPException(status_code=400, detail={"field": field, "message": message})


def _s(v, n=200) -> Optional[str]:
    v = (v or "").strip() if isinstance(v, str) else v
    return v[:n] if v else None


def _date(field: str, v: Optional[str], label: str, required: bool = False) -> Optional[str]:
    v = _s(v, 10)
    if not v:
        if required:
            _bad(field, f"{label}: campo obbligatorio")
        return None
    try:
        if not DATE_RX.match(v):
            raise ValueError
        date.fromisoformat(v)
    except ValueError:
        _bad(field, f"{label}: data non valida")
    return v


def _choice(field: str, v: Optional[str], opts: dict, label: str, default: Optional[str] = None) -> Optional[str]:
    v = v or default
    if v is None:
        return None
    if v not in opts:
        _bad(field, f"{label}: valore non previsto")
    return v


def _expiry_state(scad: Optional[str], today: date) -> str:
    if not scad:
        return "senza_scadenza"
    d = date.fromisoformat(scad)
    return "scaduto" if d < today else "in_scadenza" if d <= today + timedelta(days=SOON_DAYS) else "valido"


class SocioIn(BaseModel):
    nome: str
    cognome: str
    codice_fiscale: Optional[str] = None
    data_nascita: Optional[str] = None
    luogo_nascita: Optional[str] = None
    sesso: Optional[str] = None
    email: Optional[str] = None
    cellulare: Optional[str] = None
    indirizzo: Optional[str] = None
    cap: Optional[str] = None
    citta: Optional[str] = None
    provincia: Optional[str] = None
    nazione: Optional[str] = None
    taglia: Optional[str] = None
    persona_id: Optional[str] = None
    conferma_nuova: bool = False
    tipo: str = "socio"
    qualifica: Optional[str] = None
    stato: str = "attivo"
    data_iscrizione: Optional[str] = None
    numero_socio: Optional[str] = None
    note: Optional[str] = None


class TesseramentoIn(BaseModel):
    socio_id: str
    stagione: str
    ente: Optional[str] = None
    ente_id: Optional[str] = None
    numero_tessera: Optional[str] = None
    categoria: Optional[str] = None
    data_emissione: Optional[str] = None
    data_scadenza: Optional[str] = None
    annullato: bool = False
    note: Optional[str] = None


class QuotaIn(BaseModel):
    socio_id: str
    descrizione: str
    stagione: Optional[str] = None
    importo: float
    data_scadenza: Optional[str] = None
    data_pagamento: Optional[str] = None
    importo_pagato: Optional[float] = None
    metodo: Optional[str] = None
    note: Optional[str] = None


class CertificatoIn(BaseModel):
    socio_id: str
    tipo: str = "non_agonistico"
    data_rilascio: Optional[str] = None
    data_scadenza: str
    medico: Optional[str] = None
    note: Optional[str] = None


class EnteIn(BaseModel):
    sigla: str
    nome: Optional[str] = None
    tipo: str = "altro"


class EnteStateIn(BaseModel):
    active: bool


class EnteOrderIn(BaseModel):
    ids: list[str]


class AdempimentoIn(BaseModel):
    titolo: str
    data_scadenza: str
    completato: bool = False
    note: Optional[str] = None


def build(db, deps: dict):
    r = APIRouter(prefix="/api/asd")
    require_member, record_audit, cf_valid = deps["require_member"], deps["record_audit"], deps["cf_valid"]
    normalize, person_scope, link_visible, prefs_for = deps["normalize"], deps["person_scope"], deps["link_visible"], deps["prefs_for"]
    org_settings = deps["org_settings"]

    async def is_active(org_id: str) -> bool:
        if await db.org_services.find_one({"org_id": org_id, "service": SERVICE_KEY, "active": True}, {"_id": 1}):
            return True
        svc = await db.marketplace_services.find_one({"key": SERVICE_KEY}, {"_id": 0, "id": 1})
        return bool(svc and await db.marketplace_purchases.find_one({"org_id": org_id, "service_id": svc["id"], "status": {"$in": ["active", "past_due"]}}, {"_id": 1}))

    def allowed_role(user: dict) -> bool:
        # Super Admin: opera con il proprio ruolo nell'org selezionata (X-Org-Id), senza impersonare utenti.
        if user.get("role") == "superadmin":
            return user.get("org_role") == "superadmin"
        return user.get("role") not in ("staff", "volunteer") and user.get("org_role") in ("admin_org", "user")

    async def member(user: dict = Depends(require_member)) -> dict:
        if not user.get("org_id") or not allowed_role(user):
            raise HTTPException(status_code=403, detail="Gestione Società è riservata agli Admin e agli utenti dell'organizzazione")
        if not await is_active(user["org_id"]):
            raise HTTPException(status_code=403, detail="Il modulo Gestione Società non è attivo per questa organizzazione")
        return user

    async def admin(user: dict = Depends(member)) -> dict:
        if user.get("org_role") not in ("admin_org", "superadmin"):
            raise HTTPException(status_code=403, detail="Eliminazione riservata agli amministratori dell'organizzazione")
        return user

    async def socio_or_400(org_id: str, sid: str) -> dict:
        s = await db.asd_soci.find_one({"org_id": org_id, "id": sid}, {"_id": 0})
        if not s:
            _bad("socio_id", "Socio non trovato in questa organizzazione")
        return s

    async def persons_by_id(org_id: str, ids: list) -> dict:
        return {p["id"]: p for p in await db.persons.find({"org_id": org_id, "id": {"$in": ids}}, {"_id": 0}).to_list(len(ids) + 1)}

    def merge(s: dict, p: Optional[dict]) -> dict:
        p = p or {}
        return {**{k: s.get(k) for k in ("id", "org_id", "persona_id", "created_at", "updated_at", *ASSOC)}, **{k: p.get(k) for k in SHARED}}

    async def names(org_id: str) -> dict:
        soci = await db.asd_soci.find({"org_id": org_id}, {"_id": 0, "id": 1, "persona_id": 1}).to_list(20000)
        ps = await persons_by_id(org_id, [s["persona_id"] for s in soci])
        return {s["id"]: f"{(ps.get(s['persona_id']) or {}).get('cognome') or ''} {(ps.get(s['persona_id']) or {}).get('nome') or ''}".strip() or "—" for s in soci}

    async def migrate_soci():
        """Soci creati prima dell'anagrafica unica: collega a una persona esistente solo se univoca, altrimenti crea la persona. Dati originali conservati."""
        async for s in db.asd_soci.find({"persona_id": {"$exists": False}}, {"_id": 0}):
            org, orig = s["org_id"], {k: s.get(k) for k in SHARED if s.get(k) is not None}
            cand = []
            if orig.get("codice_fiscale"):
                cand = await db.persons.find({"org_id": org, "codice_fiscale": orig["codice_fiscale"]}, {"_id": 0}).to_list(3)
            if not cand and orig.get("email"):
                same = lambda p, k: (p.get(k) or "").strip().lower() == (orig.get(k) or "").strip().lower()  # noqa: E731
                cand = [p for p in await db.persons.find({"org_id": org, "email": {"$regex": f"^{re.escape(orig['email'])}$", "$options": "i"}}, {"_id": 0}).to_list(5)
                        if same(p, "nome") and same(p, "cognome")]
            if len(cand) == 1:
                pid, how = cand[0]["id"], "collegata"
                fill = {k: v for k, v in orig.items() if not cand[0].get(k)}
                if fill:
                    await db.persons.update_one({"org_id": org, "id": pid}, {"$set": {**fill, "updated_at": _now()}})
            else:
                pid, how = uuid.uuid4().hex, "creata"
                await db.persons.insert_one(normalize("persons", {"id": pid, "org_id": org, **orig, "created_at": s.get("created_at") or _now(),
                                                                  "provenienza": {"tipo": "associazione", "at": _now(), "by": "migrazione"}}))
            await db.asd_soci.update_one({"org_id": org, "id": s["id"]}, {"$set": {"persona_id": pid, "anagrafica_originale": orig, "migrazione": {"at": _now(), "persona": how}},
                                                                          "$unset": {k: "" for k in SHARED}})

    async def ensure_indexes():
        for c in ("asd_soci", "asd_tesseramenti", "asd_quote", "asd_certificati", "asd_adempimenti"):
            await db[c].create_index([("org_id", 1), ("id", 1)], unique=True)
        await migrate_soci()
        await db.asd_soci.create_index([("org_id", 1), ("persona_id", 1)], unique=True, partialFilterExpression={"persona_id": {"$type": "string"}})

    # ---------- validazione ----------
    def clean_socio(b: SocioIn) -> tuple:
        d = {"nome": _s(b.nome, 80), "cognome": _s(b.cognome, 80)}
        if not d["nome"]:
            _bad("nome", "Nome: campo obbligatorio")
        if not d["cognome"]:
            _bad("cognome", "Cognome: campo obbligatorio")
        cf = (_s(b.codice_fiscale, 16) or "").upper().replace(" ", "") or None
        if cf and not cf_valid(cf):
            _bad("codice_fiscale", "Codice fiscale non valido")
        email = (_s(b.email, 200) or "").lower() or None
        if email and not EMAIL_RX.match(email):
            _bad("email", "Email non valida")
        d.update(codice_fiscale=cf, email=email, data_nascita=_date("data_nascita", b.data_nascita, "Data di nascita"),
                 luogo_nascita=_s(b.luogo_nascita, 120), sesso=_choice("sesso", _s(b.sesso, 1), {"M": "M", "F": "F"}, "Sesso"),
                 cellulare=_s(b.cellulare, 40), indirizzo=_s(b.indirizzo, 300), cap=_s(b.cap, 10), citta=_s(b.citta, 120), provincia=_s(b.provincia, 40),
                 nazione=_s(b.nazione, 80), taglia=_s(b.taglia, 20))
        a = dict(tipo=_choice("tipo", b.tipo, TIPI_SOCIO, "Tipo", "socio"),
                 qualifica=_choice("qualifica", _s(b.qualifica, 40), QUALIFICHE, "Qualifica"), stato=_choice("stato", b.stato, STATI_SOCIO, "Stato", "attivo"),
                 data_iscrizione=_date("data_iscrizione", b.data_iscrizione, "Data iscrizione"), numero_socio=_s(b.numero_socio, 40), note=_s(b.note, 2000))
        return normalize("persons", {k: v for k, v in d.items() if k in b.model_fields_set or k in ("nome", "cognome")}), a

    def brief(p: dict) -> dict:
        return {k: p.get(k) for k in ("id", "nome", "cognome", "codice_fiscale", "email", "cellulare", "data_nascita")}

    async def matches(org_id: str, d: dict, exclude: Optional[str] = None) -> list:
        """Persone dell'organizzazione con stesso codice fiscale, email o cellulare (nessuna unione automatica)."""
        out = {}
        for k in ("codice_fiscale", "email", "cellulare"):
            if not d.get(k):
                continue
            q = {"org_id": org_id, "archiviato": {"$ne": True}, k: {"$regex": f"^{re.escape(d[k])}$", "$options": "i"} if k == "email" else d[k]}
            if k == "cellulare":
                dg = re.sub(r"\D", "", d[k])[-9:]
                if len(dg) < 6:
                    continue
                q[k] = {"$regex": r"\D*".join(dg) + r"\D*$"}
            if exclude:
                q["id"] = {"$ne": exclude}
            for p in await db.persons.find(q, {"_id": 0}).to_list(5):
                out.setdefault(p["id"], {**brief(p), "campi": []})["campi"].append(k)
        soci = {s["persona_id"]: s["id"] for s in await db.asd_soci.find({"org_id": org_id, "persona_id": {"$in": list(out)}}, {"_id": 0, "id": 1, "persona_id": 1}).to_list(20)}
        return [{**m, "socio_id": soci.get(m["id"])} for m in out.values()]

    async def save_person(org_id: str, pid: str, d: dict):
        conflict = await matches(org_id, d, exclude=pid)
        if conflict:
            k = conflict[0]["campi"][0]
            lab = {"codice_fiscale": "Codice fiscale", "email": "Email", "cellulare": "Cellulare"}[k]
            _bad(k, f"{lab} già presente nell'anagrafica di {conflict[0]['cognome'] or ''} {conflict[0]['nome'] or ''}".strip() + ": modifica il valore per evitare un duplicato")
        await db.persons.update_one({"org_id": org_id, "id": pid}, {"$set": {**d, "updated_at": _now()}})

    # ---------- enti e federazioni (settings dell'organizzazione) ----------
    async def enti(org: str) -> list:
        doc = await org_settings({"org_id": org})
        if ENTI_KEY in doc:
            return doc[ENTI_KEY]
        items = [{"id": re.sub(r"[^a-z0-9]+", "-", s.lower()), "sigla": s, "nome": n, "tipo": t, "active": True, "default": True} for t, s, n in ENTI_DEFAULT]
        # tesseramenti precedenti con ente a testo libero: collega per sigla/denominazione, altrimenti crea la voce (testo originale invariato)
        for txt in await db.asd_tesseramenti.distinct("ente", {"org_id": org, "ente_id": {"$exists": False}}):
            k = (txt or "").strip().lower()
            hit = next((e for e in items if k in (e["sigla"].lower(), e["nome"].lower(), ente_label(e).lower()) or k.split(" ")[0] == e["sigla"].lower()), None)
            if not hit and k:
                hit = {"id": uuid.uuid4().hex[:12], "sigla": txt.strip()[:40], "nome": None, "tipo": "altro", "active": True}
                items.append(hit)
            if hit:
                await db.asd_tesseramenti.update_many({"org_id": org, "ente": txt, "ente_id": {"$exists": False}}, {"$set": {"ente_id": hit["id"]}})
        await db.settings.update_one({"id": org, ENTI_KEY: {"$exists": False}}, {"$set": {ENTI_KEY: items, "updated_at": _now()}})
        return (await db.settings.find_one({"id": org}, {"_id": 0, ENTI_KEY: 1}))[ENTI_KEY]

    async def save_enti(org: str, items: list):
        await db.settings.update_one({"id": org}, {"$set": {ENTI_KEY: items, "updated_at": _now()}})

    def is_manager(user: dict) -> bool:
        return user.get("org_role") in ("admin_org", "superadmin")

    def clean_ente(b: EnteIn, items: list, own: Optional[str] = None) -> dict:
        sigla, nome = _s(b.sigla, 40), _s(b.nome, 160)
        if not sigla:
            _bad("sigla", "Sigla: campo obbligatorio")
        tipo = _choice("tipo", b.tipo, TIPI_ENTE, "Tipologia", "altro")
        for e in items:
            if e["id"] == own:
                continue
            if e["sigla"].lower() == sigla.lower():
                _bad("sigla", f"La sigla {sigla} è già presente ({ente_label(e)})")
            if nome and (e.get("nome") or "").lower() == nome.lower():
                _bad("nome", f"Denominazione già presente ({ente_label(e)})")
        return {"sigla": sigla, "nome": nome, "tipo": tipo}

    @r.get("/enti")
    async def list_enti(user: dict = Depends(member)):
        items = await enti(user["org_id"])
        use = {x["_id"]: x["n"] for x in await db.asd_tesseramenti.aggregate([{"$match": {"org_id": user["org_id"]}}, {"$group": {"_id": "$ente_id", "n": {"$sum": 1}}}]).to_list(1000)}
        return {"items": [{**e, "label": ente_label(e), "usage": use.get(e["id"], 0)} for e in items], "tipi": TIPI_ENTE, "can_manage": is_manager(user)}

    @r.post("/enti")
    async def add_ente(body: EnteIn, user: dict = Depends(member)):
        items = await enti(user["org_id"])
        e = {"id": uuid.uuid4().hex[:12], **clean_ente(body, items), "active": True}
        await save_enti(user["org_id"], items + [e])
        await record_audit(user, "asd_ente_create", org_id=user["org_id"], detail=ente_label(e))
        return {**e, "label": ente_label(e), "usage": 0}

    async def manage_ente(user: dict, eid: str):
        if not is_manager(user):
            raise HTTPException(status_code=403, detail="Solo l'Admin Organizzazione può modificare l'elenco enti e federazioni")
        items = await enti(user["org_id"])
        i = next((n for n, e in enumerate(items) if e["id"] == eid), None)
        if i is None:
            raise HTTPException(status_code=404, detail="Voce non trovata")
        return items, i

    @r.put("/enti/order")
    async def order_enti(body: EnteOrderIn, user: dict = Depends(member)):
        if not is_manager(user):
            raise HTTPException(status_code=403, detail="Solo l'Admin Organizzazione può ordinare l'elenco")
        items = await enti(user["org_id"])
        pos = {eid: n for n, eid in enumerate(body.ids)}
        await save_enti(user["org_id"], sorted(items, key=lambda e: pos.get(e["id"], len(pos))))
        return {"ok": True}

    @r.put("/enti/{eid}")
    async def update_ente(eid: str, body: EnteIn, user: dict = Depends(member)):
        items, i = await manage_ente(user, eid)
        items[i] = {**items[i], **clean_ente(body, items, own=eid)}
        await save_enti(user["org_id"], items)
        await record_audit(user, "asd_ente_update", org_id=user["org_id"], detail=ente_label(items[i]))
        return {**items[i], "label": ente_label(items[i])}

    @r.post("/enti/{eid}/stato")
    async def toggle_ente(eid: str, body: EnteStateIn, user: dict = Depends(member)):
        items, i = await manage_ente(user, eid)
        items[i]["active"] = body.active
        await save_enti(user["org_id"], items)
        return {"ok": True}

    @r.delete("/enti/{eid}")
    async def delete_ente(eid: str, user: dict = Depends(member)):
        items, i = await manage_ente(user, eid)
        if await db.asd_tesseramenti.count_documents({"org_id": user["org_id"], "ente_id": eid}):
            raise HTTPException(status_code=409, detail="Voce usata nei tesseramenti: puoi solo disattivarla")
        await save_enti(user["org_id"], items[:i] + items[i + 1:])
        return {"ok": True}

    async def resolve_ente(org: str, b: TesseramentoIn, current: Optional[str]) -> dict:
        if not b.ente_id:
            _bad("ente_id", "Ente o federazione: campo obbligatorio")
        e = next((x for x in await enti(org) if x["id"] == b.ente_id), None)
        if not e:
            _bad("ente_id", "Ente o federazione non trovato nell'elenco")
        if not e.get("active") and b.ente_id != current:
            _bad("ente_id", f"{ente_label(e)} è disattivato: scegli un'altra voce o riattivalo nelle Impostazioni")
        return {"ente_id": e["id"], "ente": ente_label(e)}

    def clean_tess(b: TesseramentoIn) -> dict:
        d = {"socio_id": b.socio_id, "stagione": _s(b.stagione, 20)}
        if not d["stagione"]:
            _bad("stagione", "Stagione: campo obbligatorio (es. 2026/2027)")
        d.update(numero_tessera=_s(b.numero_tessera, 60), categoria=_s(b.categoria, 80), data_emissione=_date("data_emissione", b.data_emissione, "Data emissione"),
                 data_scadenza=_date("data_scadenza", b.data_scadenza, "Data scadenza"), annullato=bool(b.annullato), note=_s(b.note, 2000))
        if d["data_emissione"] and d["data_scadenza"] and d["data_scadenza"] < d["data_emissione"]:
            _bad("data_scadenza", "La scadenza non può essere precedente all'emissione")
        return d

    def clean_quota(b: QuotaIn) -> dict:
        d = {"socio_id": b.socio_id, "descrizione": _s(b.descrizione, 200), "stagione": _s(b.stagione, 20)}
        if not d["descrizione"]:
            _bad("descrizione", "Descrizione: campo obbligatorio (es. Quota associativa 2026)")
        if b.importo is None or b.importo < 0:
            _bad("importo", "Importo non valido: deve essere uguale o maggiore di 0")
        if b.importo_pagato is not None and b.importo_pagato < 0:
            _bad("importo_pagato", "Importo pagato non valido")
        pag = _date("data_pagamento", b.data_pagamento, "Data pagamento")
        d.update(importo=round(float(b.importo), 2), data_scadenza=_date("data_scadenza", b.data_scadenza, "Data scadenza"), data_pagamento=pag,
                 importo_pagato=round(float(b.importo_pagato if b.importo_pagato is not None else b.importo), 2) if pag else None,
                 metodo=_choice("metodo", _s(b.metodo, 20), METODI, "Metodo di pagamento") if pag else None, note=_s(b.note, 2000))
        return d

    def clean_cert(b: CertificatoIn) -> dict:
        d = {"socio_id": b.socio_id, "tipo": _choice("tipo", b.tipo, TIPI_CERT, "Tipo certificato", "non_agonistico"),
             "data_rilascio": _date("data_rilascio", b.data_rilascio, "Data rilascio"), "data_scadenza": _date("data_scadenza", b.data_scadenza, "Data scadenza", True),
             "medico": _s(b.medico, 200), "note": _s(b.note, 2000)}
        if d["data_rilascio"] and d["data_scadenza"] < d["data_rilascio"]:
            _bad("data_scadenza", "La scadenza non può essere precedente al rilascio")
        return d

    # ---------- arricchimento in lettura ----------
    def quota_state(q: dict, today: date) -> str:
        if q.get("data_pagamento"):
            return "pagata" if (q.get("importo_pagato") or 0) >= (q.get("importo") or 0) else "parziale"
        return "scaduta" if q.get("data_scadenza") and date.fromisoformat(q["data_scadenza"]) < today else "da_pagare"

    def tess_state(t: dict, today: date) -> str:
        return "annullato" if t.get("annullato") else _expiry_state(t.get("data_scadenza"), today)

    def pub(d: dict) -> dict:
        return {k: v for k, v in d.items() if k not in ("_id", "file_path", "file_backend")}

    # ---------- stato ----------
    @r.get("/status")
    async def status(user: dict = Depends(require_member)):
        ok_role = bool(user.get("org_id")) and allowed_role(user)
        return {"active": ok_role and await is_active(user["org_id"]), "can_delete": user.get("org_role") in ("admin_org", "superadmin"),
                "options": {"tipi_socio": TIPI_SOCIO, "qualifiche": QUALIFICHE, "stati_socio": STATI_SOCIO, "tipi_cert": TIPI_CERT, "metodi": METODI}, "soon_days": SOON_DAYS}

    # ---------- CRUD generico ----------
    def crud(path: str, coll: str, model, clean, label: str, linked: bool = True):
        async def create(body: model, user: dict = Depends(member)):
            d = clean(body)
            if linked:
                await socio_or_400(user["org_id"], d["socio_id"])
            doc = {**d, "id": uuid.uuid4().hex, "org_id": user["org_id"], "created_at": _now(), "updated_at": _now(), "created_by": user.get("email")}
            await insert(coll, doc)
            await record_audit(user, f"asd_{label}_create", org_id=user["org_id"], detail=doc["id"])
            return pub(doc)

        async def update(iid: str, body: model, user: dict = Depends(member)):
            d = clean(body)
            if linked:
                await socio_or_400(user["org_id"], d["socio_id"])
            try:
                res = await db[coll].find_one_and_update({"org_id": user["org_id"], "id": iid}, {"$set": {**d, "updated_at": _now(), "updated_by": user.get("email")}},
                                                         projection={"_id": 0}, return_document=True)
            except DuplicateKeyError:
                _bad("codice_fiscale", "Esiste già un socio con questo codice fiscale")
            if not res:
                raise HTTPException(status_code=404, detail="Elemento non trovato")
            await record_audit(user, f"asd_{label}_update", org_id=user["org_id"], detail=iid)
            return pub(res)

        async def delete(iid: str, user: dict = Depends(admin)):
            doc = await db[coll].find_one_and_delete({"org_id": user["org_id"], "id": iid}, projection={"_id": 0})
            if not doc:
                raise HTTPException(status_code=404, detail="Elemento non trovato")
            await record_audit(user, f"asd_{label}_delete", org_id=user["org_id"], detail=iid)
            return {"ok": True}

        r.add_api_route(path, create, methods=["POST"])
        r.add_api_route(f"{path}/{{iid}}", update, methods=["PUT"])
        if coll != "asd_soci" and coll != "asd_certificati":
            r.add_api_route(f"{path}/{{iid}}", delete, methods=["DELETE"])

    async def insert(coll: str, doc: dict):
        try:
            await db[coll].insert_one({**doc})
        except DuplicateKeyError:
            _bad("codice_fiscale", "Esiste già un socio con questo codice fiscale")


    @r.post("/tesseramenti")
    async def create_tess(body: TesseramentoIn, user: dict = Depends(member)):
        d = {**clean_tess(body), **await resolve_ente(user["org_id"], body, None)}
        await socio_or_400(user["org_id"], d["socio_id"])
        doc = {**d, "id": uuid.uuid4().hex, "org_id": user["org_id"], "created_at": _now(), "updated_at": _now(), "created_by": user.get("email")}
        await insert("asd_tesseramenti", doc)
        await record_audit(user, "asd_tesseramento_create", org_id=user["org_id"], detail=doc["id"])
        return pub(doc)

    @r.put("/tesseramenti/{iid}")
    async def update_tess(iid: str, body: TesseramentoIn, user: dict = Depends(member)):
        cur = await db.asd_tesseramenti.find_one({"org_id": user["org_id"], "id": iid}, {"_id": 0, "ente_id": 1})
        if not cur:
            raise HTTPException(status_code=404, detail="Elemento non trovato")
        d = clean_tess(body)
        await socio_or_400(user["org_id"], d["socio_id"])
        if body.ente_id != cur.get("ente_id"):
            d.update(await resolve_ente(user["org_id"], body, cur.get("ente_id")))
        res = await db.asd_tesseramenti.find_one_and_update({"org_id": user["org_id"], "id": iid}, {"$set": {**d, "updated_at": _now(), "updated_by": user.get("email")}},
                                                            projection={"_id": 0}, return_document=True)
        await record_audit(user, "asd_tesseramento_update", org_id=user["org_id"], detail=iid)
        return pub(res)

    @r.delete("/tesseramenti/{iid}")
    async def delete_tess(iid: str, user: dict = Depends(admin)):
        if not await db.asd_tesseramenti.find_one_and_delete({"org_id": user["org_id"], "id": iid}):
            raise HTTPException(status_code=404, detail="Elemento non trovato")
        await record_audit(user, "asd_tesseramento_delete", org_id=user["org_id"], detail=iid)
        return {"ok": True}

    crud("/quote", "asd_quote", QuotaIn, clean_quota, "quota")
    crud("/certificati", "asd_certificati", CertificatoIn, clean_cert, "certificato")
    crud("/adempimenti", "asd_adempimenti", AdempimentoIn,
         lambda b: {"titolo": _s(b.titolo, 200) or _bad("titolo", "Titolo: campo obbligatorio"),
                    "data_scadenza": _date("data_scadenza", b.data_scadenza, "Data scadenza", True), "completato": bool(b.completato), "note": _s(b.note, 2000)},
         "adempimento", linked=False)

    # ---------- soci (anagrafica in db.persons) ----------
    async def scoped_person(user: dict, pid: str) -> dict:
        scope = await person_scope(user)
        p = await db.persons.find_one({"org_id": user["org_id"], "id": pid, "archiviato": {"$ne": True}}, {"_id": 0})
        if not p or (scope is not None and pid not in scope):
            _bad("persona_id", "Persona non trovata in questa organizzazione")
        return p

    @r.post("/soci")
    async def create_socio(body: SocioIn, user: dict = Depends(member)):
        org = user["org_id"]
        d, a = clean_socio(body)
        if body.persona_id:
            await scoped_person(user, body.persona_id)
            ex = await db.asd_soci.find_one({"org_id": org, "persona_id": body.persona_id}, {"_id": 0, "id": 1})
            if ex:
                raise HTTPException(status_code=409, detail={"field": "persona_id", "message": "Questa persona è già registrata come socio", "socio_id": ex["id"]})
            await save_person(org, body.persona_id, d)
            pid, how = body.persona_id, "collegata"
        else:
            m = await matches(org, d)
            if any("codice_fiscale" in x["campi"] for x in m):
                raise HTTPException(status_code=409, detail={"field": "duplicati", "message": "Esiste già una persona con questo codice fiscale: collegala invece di crearne una nuova", "matches": m, "cf": True})
            if m and not body.conferma_nuova:
                raise HTTPException(status_code=409, detail={"field": "duplicati", "message": "Esistono persone con gli stessi dati: verifica se collegarne una", "matches": m, "cf": False})
            pid, how = uuid.uuid4().hex, "creata"
            await db.persons.insert_one({**d, "id": pid, "org_id": org, "created_at": _now(), "provenienza": {"tipo": "associazione", "at": _now(), "by": user.get("email")}})
        doc = {**a, "id": uuid.uuid4().hex, "org_id": org, "persona_id": pid, "created_at": _now(), "updated_at": _now(), "created_by": user.get("email")}
        try:
            await db.asd_soci.insert_one({**doc})
        except DuplicateKeyError:
            raise HTTPException(status_code=409, detail={"field": "persona_id", "message": "Questa persona è già registrata come socio"})
        await record_audit(user, "asd_socio_create", org_id=org, detail=doc["id"], meta={"persona_id": pid, "persona": how})
        return merge(doc, await db.persons.find_one({"org_id": org, "id": pid}, {"_id": 0}))

    @r.put("/soci/{iid}")
    async def update_socio(iid: str, body: SocioIn, user: dict = Depends(member)):
        org = user["org_id"]
        s = await db.asd_soci.find_one({"org_id": org, "id": iid}, {"_id": 0})
        if not s:
            raise HTTPException(status_code=404, detail="Socio non trovato")
        d, a = clean_socio(body)
        await save_person(org, s["persona_id"], d)
        res = await db.asd_soci.find_one_and_update({"org_id": org, "id": iid}, {"$set": {**a, "updated_at": _now(), "updated_by": user.get("email")}}, projection={"_id": 0}, return_document=True)
        await record_audit(user, "asd_socio_update", org_id=org, detail=iid)
        return merge(res, await db.persons.find_one({"org_id": org, "id": s["persona_id"]}, {"_id": 0}))

    @r.get("/anagrafica")
    async def search_people(q: str, user: dict = Depends(member)):
        """Ricerca su tutta l'anagrafica dell'organizzazione (Staff, Volontari, Da classificare, soci), indipendente dai filtri dell'elenco soci."""
        org, q = user["org_id"], (q or "").strip()[:80]
        if len(q) < 2:
            return []
        toks = [re.escape(t) for t in q.split() if t]
        digits = re.sub(r"\D", "", q)
        ors = [{"codice_fiscale": {"$regex": re.escape(q.replace(" ", "")), "$options": "i"}}, {"email": {"$regex": re.escape(q), "$options": "i"}},
               {"$and": [{"$or": [{"nome": {"$regex": t, "$options": "i"}}, {"cognome": {"$regex": t, "$options": "i"}}]} for t in toks]}]
        if len(digits) >= 4:
            ors.append({"cellulare": {"$regex": r"\D*".join(digits)}})
        by_num = await db.asd_soci.distinct("persona_id", {"org_id": org, "numero_socio": {"$regex": re.escape(q), "$options": "i"}})
        if by_num:
            ors.append({"id": {"$in": by_num}})
        f = {"org_id": org, "archiviato": {"$ne": True}, "$or": ors}
        scope = await person_scope(user)
        if scope is not None:
            f["id"] = {"$in": list(scope)}
        people = await db.persons.find(f, {"_id": 0}).sort([("cognome", 1), ("nome", 1)]).to_list(30)
        ids = [p["id"] for p in people]
        soci = {s["persona_id"]: s for s in await db.asd_soci.find({"org_id": org, "persona_id": {"$in": ids}}, {"_id": 0}).to_list(30)}
        cats = {}
        for x in await db.staff.find({"org_id": org, "persona_id": {"$in": ids}}, {"_id": 0, "persona_id": 1, "categoria": 1}).to_list(3000):
            cats.setdefault(x["persona_id"], set()).add("staff" if x.get("categoria") == "collaboratore" else x.get("categoria"))
        out = []
        for p in people:
            s = soci.get(p["id"])
            c = cats.get(p["id"], set())
            out.append({**brief(p), "classificazione": [k for k in ("staff", "volontario", "da_classificare") if k in c],
                        "socio": {k: s.get(k) for k in ("id", "stato", "tipo", "numero_socio")} if s else None})
        return out

    @r.get("/soci/{iid}/staff")
    async def socio_staff(iid: str, user: dict = Depends(member)):
        """Sezione Staff e Volontari della scheda socio: classificazione, eventi, team, mansioni e disponibilità (dati operativi, solo lettura)."""
        org = user["org_id"]
        s = await db.asd_soci.find_one({"org_id": org, "id": iid}, {"_id": 0, "persona_id": 1})
        if not s:
            raise HTTPException(status_code=404, detail="Socio non trovato")
        pid = s["persona_id"]
        links = [x for x in await db.staff.find({"org_id": org, "persona_id": pid}, {"_id": 0}).to_list(500) if link_visible(user, x)]
        evs = {e["id"]: e.get("nome") for e in await db.events.find({"org_id": org, "id": {"$in": [x["evento_id"] for x in links]}}, {"_id": 0, "id": 1, "nome": 1}).to_list(500)}
        tms = {t["id"]: t.get("nome") for t in await db.teams.find({"org_id": org, "id": {"$in": [x.get("team_id") for x in links if x.get("team_id")]}}, {"_id": 0, "id": 1, "nome": 1}).to_list(500)}
        cats = {"staff" if x.get("categoria") == "collaboratore" else x.get("categoria") for x in links}
        prefs = (await prefs_for(org, [pid])).get(pid, [])
        return {"persona_id": pid, "classificazione": [k for k in ("staff", "volontario", "da_classificare") if k in cats],
                "eventi": [{"evento_nome": evs.get(x["evento_id"], "—"), "categoria": x.get("categoria"), "team": tms.get(x.get("team_id")), "mansione": x.get("ruolo")} for x in links],
                "disponibilita": [{"evento_nome": p.get("evento_nome"), "preferenza": p.get("preferenza"), "giorni": [d.get("date") for d in (p.get("days") or [])]} for p in prefs]}

    @r.get("/persona/{pid}")
    async def persona_link(pid: str, user: dict = Depends(require_member)):
        """Sezione Gestione Società nella scheda Staff / Volontari. Nessun dato sanitario esposto."""
        if not (user.get("org_id") and allowed_role(user) and await is_active(user["org_id"])):
            return {"active": False}
        org = user["org_id"]
        s = await db.asd_soci.find_one({"org_id": org, "persona_id": pid}, {"_id": 0})
        if not s:
            return {"active": True, "socio": None}
        today = date.today()
        ts = await db.asd_tesseramenti.find({"org_id": org, "socio_id": s["id"]}, {"_id": 0}).sort([("stagione", -1), ("data_scadenza", -1)]).to_list(1)
        t = ts[0] if ts else None
        if t:
            cur = next((e for e in await enti(org) if e["id"] == t.get("ente_id")), None)
            t["ente"] = ente_label(cur) if cur else t.get("ente")
        return {"active": True, "socio": {k: s.get(k) for k in ("id", "stato", "tipo", "numero_socio", "data_iscrizione")},
                "tesseramento": {**{k: t.get(k) for k in ("stagione", "ente", "numero_tessera", "data_scadenza")}, "stato": tess_state(t, today)} if t else None}

    async def soci_map(user: dict) -> dict:
        if not (user.get("org_id") and allowed_role(user) and await is_active(user["org_id"])):
            return {}
        return {s["persona_id"]: s.get("stato") for s in await db.asd_soci.find({"org_id": user["org_id"]}, {"_id": 0, "persona_id": 1, "stato": 1}).to_list(20000)}

    @r.get("/soci")
    async def list_soci(q: Optional[str] = None, stato: Optional[str] = None, tipo: Optional[str] = None, user: dict = Depends(member)):
        f = {"org_id": user["org_id"]}
        if stato:
            f["stato"] = stato
        if tipo:
            f["tipo"] = tipo
        soci = await db.asd_soci.find(f, {"_id": 0}).to_list(20000)
        ps = await persons_by_id(user["org_id"], [s["persona_id"] for s in soci])
        rows = [merge(s, ps.get(s["persona_id"])) for s in soci]
        if q:
            needle, digits = q.strip().lower()[:80], re.sub(r"\D", "", q)
            def hit(s):
                txt = " ".join(str(s.get(k) or "") for k in ("nome", "cognome", "codice_fiscale", "email", "numero_socio")).lower()
                return all(t in txt for t in needle.split()) or (len(digits) >= 4 and digits in re.sub(r"\D", "", s.get("cellulare") or ""))
            rows = [s for s in rows if hit(s)]
        rows.sort(key=lambda s: ((s.get("cognome") or "").lower(), (s.get("nome") or "").lower()))
        today = date.today()
        ids = [s["id"] for s in rows]
        certs = {}
        for c in await db.asd_certificati.find({"org_id": user["org_id"], "socio_id": {"$in": ids}}, {"_id": 0, "socio_id": 1, "data_scadenza": 1}).to_list(50000):
            if c["data_scadenza"] > certs.get(c["socio_id"], ""):
                certs[c["socio_id"]] = c["data_scadenza"]
        due = {x["_id"]: x["n"] for x in await db.asd_quote.aggregate([{"$match": {"org_id": user["org_id"], "data_pagamento": None}}, {"$group": {"_id": "$socio_id", "n": {"$sum": 1}}}]).to_list(20000)}
        for s in rows:
            s["certificato_scadenza"] = certs.get(s["id"])
            s["certificato_stato"] = _expiry_state(certs.get(s["id"]), today) if certs.get(s["id"]) else "mancante"
            s["quote_da_pagare"] = due.get(s["id"], 0)
        return rows

    @r.delete("/soci/{iid}")
    async def delete_socio(iid: str, user: dict = Depends(admin)):
        s = await db.asd_soci.find_one({"org_id": user["org_id"], "id": iid}, {"_id": 0, "id": 1})
        if not s:
            raise HTTPException(status_code=404, detail="Socio non trovato")
        linked = {c: await db[c].count_documents({"org_id": user["org_id"], "socio_id": iid}) for c in ("asd_tesseramenti", "asd_quote", "asd_certificati")}
        if any(linked.values()):
            raise HTTPException(status_code=409, detail=f"Il socio ha {linked['asd_tesseramenti']} tesseramenti, {linked['asd_quote']} quote e {linked['asd_certificati']} certificati: eliminali prima oppure imposta lo stato «Cessato»")
        await db.asd_soci.delete_one({"org_id": user["org_id"], "id": iid})
        await record_audit(user, "asd_socio_delete", org_id=user["org_id"], detail=iid)
        return {"ok": True}

    # ---------- liste collegate ----------
    async def linked_list(coll: str, user: dict, socio_id: Optional[str], extra: dict, sort):
        f = {"org_id": user["org_id"], **extra}
        if socio_id:
            f["socio_id"] = socio_id
        rows = await db[coll].find(f, {"_id": 0}).sort(sort).to_list(50000)
        n = await names(user["org_id"])
        for x in rows:
            x["socio_nome"] = n.get(x.get("socio_id"), "—")
        return [pub(x) for x in rows]

    @r.get("/tesseramenti")
    async def list_tess(socio_id: Optional[str] = None, stagione: Optional[str] = None, user: dict = Depends(member)):
        rows = await linked_list("asd_tesseramenti", user, socio_id, {"stagione": stagione} if stagione else {}, [("stagione", -1), ("data_scadenza", 1)])
        today = date.today()
        labels = {e["id"]: (ente_label(e), e.get("active")) for e in await enti(user["org_id"])}
        for t in rows:
            t["stato"] = tess_state(t, today)
            lab = labels.get(t.get("ente_id"))
            t["ente_nome"], t["ente_attivo"] = (lab[0], bool(lab[1])) if lab else (t.get("ente"), True)
        return rows

    @r.get("/quote")
    async def list_quote(socio_id: Optional[str] = None, stagione: Optional[str] = None, user: dict = Depends(member)):
        rows = await linked_list("asd_quote", user, socio_id, {"stagione": stagione} if stagione else {}, [("data_scadenza", 1), ("created_at", -1)])
        today = date.today()
        for q in rows:
            q["stato"] = quota_state(q, today)
        return rows

    @r.get("/certificati")
    async def list_cert(socio_id: Optional[str] = None, user: dict = Depends(member)):
        rows = await linked_list("asd_certificati", user, socio_id, {}, [("data_scadenza", 1)])
        today = date.today()
        for c in rows:
            c["stato"] = _expiry_state(c["data_scadenza"], today)
        return rows

    @r.get("/adempimenti")
    async def list_adempimenti(user: dict = Depends(member)):
        return await db.asd_adempimenti.find({"org_id": user["org_id"]}, {"_id": 0}).sort("data_scadenza", 1).to_list(5000)

    # ---------- file certificato (dato sanitario: privato, solo via API autorizzata) ----------
    @r.post("/certificati/{iid}/file")
    async def upload_cert(iid: str, file: UploadFile = File(...), user: dict = Depends(member)):
        c = await db.asd_certificati.find_one({"org_id": user["org_id"], "id": iid}, {"_id": 0, "id": 1})
        if not c:
            raise HTTPException(status_code=404, detail="Certificato non trovato")
        data = await file.read(MAX_FILE + 1)
        if len(data) > MAX_FILE:
            _bad("file", "File troppo grande (max 10 MB)")
        sig = next(((e, c) for m, e, c in MAGIC if data.startswith(m) and (e != "webp" or data[8:12] == b"WEBP")), None)
        if not sig:
            _bad("file", "Formato non supportato: carica un PDF o un'immagine JPG, PNG, WEBP o GIF")
        ext, ct = sig
        saved = storage_utils.save(f"asd/{user['org_id']}/certificati/{iid}_{uuid.uuid4().hex[:8]}.{ext}", data, ct)
        await db.asd_certificati.update_one({"org_id": user["org_id"], "id": iid}, {"$set": {
            "file_path": saved["path"], "file_backend": saved.get("backend"), "file_name": (file.filename or f"certificato.{ext}")[:200], "file_type": ct,
            "file_size": len(data), "updated_at": _now()}})
        await record_audit(user, "asd_certificato_file", org_id=user["org_id"], detail=iid)
        return {"ok": True, "file_name": file.filename}

    @r.get("/certificati/{iid}/file")
    async def get_cert_file(iid: str, user: dict = Depends(member)):
        c = await db.asd_certificati.find_one({"org_id": user["org_id"], "id": iid}, {"_id": 0})
        if not c or not c.get("file_path"):
            raise HTTPException(status_code=404, detail="File non presente")
        data, ct = storage_utils.read(c["file_path"], c.get("file_backend"), c.get("file_type"))
        await record_audit(user, "asd_certificato_file_view", org_id=user["org_id"], detail=iid)
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", c.get("file_name") or "certificato")
        return Response(content=data, media_type=c.get("file_type") or ct, headers={"Content-Disposition": f'inline; filename="{safe}"', "Cache-Control": "no-store",
                                                                                 "X-Content-Type-Options": "nosniff"})

    @r.delete("/certificati/{iid}")
    async def delete_cert(iid: str, user: dict = Depends(admin)):
        c = await db.asd_certificati.find_one_and_delete({"org_id": user["org_id"], "id": iid}, projection={"_id": 0})
        if not c:
            raise HTTPException(status_code=404, detail="Certificato non trovato")
        await record_audit(user, "asd_certificato_delete", org_id=user["org_id"], detail=iid)
        return {"ok": True}

    # ---------- scadenze e dashboard ----------
    async def deadlines(org_id: str, days: int) -> list:
        today, limit = date.today(), (date.today() + timedelta(days=days)).isoformat()
        n = await names(org_id)
        out = []
        for c in await db.asd_certificati.find({"org_id": org_id, "data_scadenza": {"$lte": limit}}, {"_id": 0}).to_list(20000):
            out.append({"tipo": "certificato", "label": f"Certificato medico {TIPI_CERT.get(c['tipo'], '')}".strip(), "socio_id": c["socio_id"], "socio_nome": n.get(c["socio_id"], "—"),
                        "data": c["data_scadenza"], "stato": _expiry_state(c["data_scadenza"], today), "ref_id": c["id"]})
        for t in await db.asd_tesseramenti.find({"org_id": org_id, "annullato": {"$ne": True}, "data_scadenza": {"$ne": None, "$lte": limit}}, {"_id": 0}).to_list(20000):
            out.append({"tipo": "tesseramento", "label": f"Tessera {t['ente']} {t['stagione']}", "socio_id": t["socio_id"], "socio_nome": n.get(t["socio_id"], "—"),
                        "data": t["data_scadenza"], "stato": _expiry_state(t["data_scadenza"], today), "ref_id": t["id"]})
        for q in await db.asd_quote.find({"org_id": org_id, "data_pagamento": None, "data_scadenza": {"$ne": None, "$lte": limit}}, {"_id": 0}).to_list(20000):
            out.append({"tipo": "quota", "label": f"{q['descrizione']} · {q['importo']:.2f} €", "socio_id": q["socio_id"], "socio_nome": n.get(q["socio_id"], "—"),
                        "data": q["data_scadenza"], "stato": _expiry_state(q["data_scadenza"], today), "ref_id": q["id"]})
        for a in await db.asd_adempimenti.find({"org_id": org_id, "completato": False, "data_scadenza": {"$lte": limit}}, {"_id": 0}).to_list(5000):
            out.append({"tipo": "adempimento", "label": a["titolo"], "socio_id": None, "socio_nome": None, "data": a["data_scadenza"],
                        "stato": _expiry_state(a["data_scadenza"], today), "ref_id": a["id"]})
        return sorted(out, key=lambda x: x["data"])

    @r.get("/scadenze")
    async def scadenze(giorni: int = 60, user: dict = Depends(member)):
        return await deadlines(user["org_id"], max(0, min(giorni, 365)))

    @r.get("/dashboard")
    async def dashboard(user: dict = Depends(member)):
        o, today = user["org_id"], date.today()
        soci = await db.asd_soci.find({"org_id": o}, {"_id": 0, "id": 1, "stato": 1, "tipo": 1}).to_list(20000)
        attivi = {s["id"] for s in soci if s.get("stato") == "attivo"}
        quote = await db.asd_quote.find({"org_id": o}, {"_id": 0}).to_list(50000)
        certs = await db.asd_certificati.find({"org_id": o}, {"_id": 0, "socio_id": 1, "data_scadenza": 1}).to_list(50000)
        latest = {}
        for c in certs:
            latest[c["socio_id"]] = max(latest.get(c["socio_id"], ""), c["data_scadenza"])
        cert_st = [_expiry_state(latest[s], today) if s in latest else "mancante" for s in attivi]
        tess = await db.asd_tesseramenti.find({"org_id": o, "annullato": {"$ne": True}}, {"_id": 0, "socio_id": 1, "data_scadenza": 1}).to_list(50000)
        tess_validi = {t["socio_id"] for t in tess if _expiry_state(t.get("data_scadenza"), today) != "scaduto"}
        dl = await deadlines(o, SOON_DAYS)
        return {
            "soci_totali": len(soci), "soci_attivi": len(attivi),
            "tesserati_validi": len(tess_validi & attivi),
            "quote_incassate": round(sum((q.get("importo_pagato") or 0) for q in quote if q.get("data_pagamento")), 2),
            "quote_da_incassare": round(sum(q["importo"] for q in quote if not q.get("data_pagamento")), 2),
            "quote_scadute": sum(1 for q in quote if quota_state(q, today) == "scaduta"),
            "certificati": {k: cert_st.count(k) for k in ("valido", "in_scadenza", "scaduto", "mancante")},
            "scadenze_scadute": sum(1 for x in dl if x["stato"] == "scaduto"),
            "prossime_scadenze": dl[:12],
        }

    return {"router": r, "ensure_indexes": ensure_indexes, "is_active": is_active, "soci_map": soci_map}
