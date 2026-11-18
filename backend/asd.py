"""Gestione Associazione Sportiva (Marketplace "gestione-societa"): soci e tesserati, tesseramenti, quote, certificati medici, scadenze.
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
    tipo: str = "socio"
    qualifica: Optional[str] = None
    stato: str = "attivo"
    data_iscrizione: Optional[str] = None
    numero_socio: Optional[str] = None
    note: Optional[str] = None


class TesseramentoIn(BaseModel):
    socio_id: str
    stagione: str
    ente: str
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


class AdempimentoIn(BaseModel):
    titolo: str
    data_scadenza: str
    completato: bool = False
    note: Optional[str] = None


def build(db, deps: dict):
    r = APIRouter(prefix="/api/asd")
    require_member, record_audit, cf_valid = deps["require_member"], deps["record_audit"], deps["cf_valid"]

    async def is_active(org_id: str) -> bool:
        if await db.org_services.find_one({"org_id": org_id, "service": SERVICE_KEY, "active": True}, {"_id": 1}):
            return True
        svc = await db.marketplace_services.find_one({"key": SERVICE_KEY}, {"_id": 0, "id": 1})
        return bool(svc and await db.marketplace_purchases.find_one({"org_id": org_id, "service_id": svc["id"], "status": {"$in": ["active", "past_due"]}}, {"_id": 1}))

    def allowed_role(user: dict) -> bool:
        return user.get("role") not in ("staff", "volunteer", "superadmin") and user.get("org_role") in ("admin_org", "user")

    async def member(user: dict = Depends(require_member)) -> dict:
        if not user.get("org_id") or not allowed_role(user):
            raise HTTPException(status_code=403, detail="Gestione Associazione Sportiva è riservata agli Admin e agli utenti dell'organizzazione")
        if not await is_active(user["org_id"]):
            raise HTTPException(status_code=403, detail="Il modulo Gestione Associazione Sportiva non è attivo per questa organizzazione")
        return user

    async def admin(user: dict = Depends(member)) -> dict:
        if user.get("org_role") != "admin_org":
            raise HTTPException(status_code=403, detail="Eliminazione riservata agli amministratori dell'organizzazione")
        return user

    async def socio_or_400(org_id: str, sid: str) -> dict:
        s = await db.asd_soci.find_one({"org_id": org_id, "id": sid}, {"_id": 0})
        if not s:
            _bad("socio_id", "Socio non trovato in questa organizzazione")
        return s

    async def names(org_id: str) -> dict:
        return {s["id"]: f"{s['cognome']} {s['nome']}" for s in await db.asd_soci.find({"org_id": org_id}, {"_id": 0, "id": 1, "nome": 1, "cognome": 1}).to_list(20000)}

    async def ensure_indexes():
        for c in ("asd_soci", "asd_tesseramenti", "asd_quote", "asd_certificati", "asd_adempimenti"):
            await db[c].create_index([("org_id", 1), ("id", 1)], unique=True)
        await db.asd_soci.create_index([("org_id", 1), ("codice_fiscale", 1)], unique=True, partialFilterExpression={"codice_fiscale": {"$type": "string"}})

    # ---------- validazione ----------
    def clean_socio(b: SocioIn) -> dict:
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
                 cellulare=_s(b.cellulare, 40), indirizzo=_s(b.indirizzo, 300), tipo=_choice("tipo", b.tipo, TIPI_SOCIO, "Tipo", "socio"),
                 qualifica=_choice("qualifica", _s(b.qualifica, 40), QUALIFICHE, "Qualifica"), stato=_choice("stato", b.stato, STATI_SOCIO, "Stato", "attivo"),
                 data_iscrizione=_date("data_iscrizione", b.data_iscrizione, "Data iscrizione"), numero_socio=_s(b.numero_socio, 40), note=_s(b.note, 2000))
        return d

    def clean_tess(b: TesseramentoIn) -> dict:
        d = {"socio_id": b.socio_id, "stagione": _s(b.stagione, 20), "ente": _s(b.ente, 120)}
        if not d["stagione"]:
            _bad("stagione", "Stagione: campo obbligatorio (es. 2026/2027)")
        if not d["ente"]:
            _bad("ente", "Ente o federazione: campo obbligatorio")
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
        return {"active": ok_role and await is_active(user["org_id"]), "can_delete": user.get("org_role") == "admin_org",
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

    crud("/soci", "asd_soci", SocioIn, clean_socio, "socio", linked=False)
    crud("/tesseramenti", "asd_tesseramenti", TesseramentoIn, clean_tess, "tesseramento")
    crud("/quote", "asd_quote", QuotaIn, clean_quota, "quota")
    crud("/certificati", "asd_certificati", CertificatoIn, clean_cert, "certificato")
    crud("/adempimenti", "asd_adempimenti", AdempimentoIn,
         lambda b: {"titolo": _s(b.titolo, 200) or _bad("titolo", "Titolo: campo obbligatorio"),
                    "data_scadenza": _date("data_scadenza", b.data_scadenza, "Data scadenza", True), "completato": bool(b.completato), "note": _s(b.note, 2000)},
         "adempimento", linked=False)

    # ---------- soci ----------
    @r.get("/soci")
    async def list_soci(q: Optional[str] = None, stato: Optional[str] = None, tipo: Optional[str] = None, user: dict = Depends(member)):
        f = {"org_id": user["org_id"]}
        if stato:
            f["stato"] = stato
        if tipo:
            f["tipo"] = tipo
        if q:
            rx = {"$regex": re.escape(q.strip()[:80]), "$options": "i"}
            f["$or"] = [{"nome": rx}, {"cognome": rx}, {"codice_fiscale": rx}, {"email": rx}, {"numero_socio": rx}]
        rows = await db.asd_soci.find(f, {"_id": 0}).sort([("cognome", 1), ("nome", 1)]).to_list(20000)
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
        for t in rows:
            t["stato"] = tess_state(t, today)
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

    return {"router": r, "ensure_indexes": ensure_indexes, "is_active": is_active}
