"""Importazione universale Excel/CSV: un solo motore (lettura, abbinamento, duplicati, anteprima, storico, annullamento) con adattatori per modulo.
Super Admin (Org attiva) importa in qualsiasi modulo anche se non attivo: i dati restano nell'organizzazione, il modulo NON viene attivato."""
import csv
import io
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from iscritti import _cell, _date, _norm, _try

MAX_UPLOAD = 8 * 1024 * 1024
MAX_ROWS = 5000
CF_RX = re.compile(r"^[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]$")
P = "persona"


def _now():
    return datetime.now(timezone.utc).isoformat()


def F(key, label, syn="", kind="text", group=None, required=False):
    return {"key": key, "label": label, "syn": [_norm(s) for s in [label, key.replace("_", " "), *[x for x in syn.split("|") if x]]], "type": kind, "group": group, "required": required}


PERSON_FIELDS = [
    F("nome", "Nome", "first name|name|nome proprio", group=P, required=True), F("cognome", "Cognome", "last name|surname", group=P),
    F("codice_fiscale", "Codice fiscale", "cf|cod fisc|codice fisc|tax code|c f", group=P), F("data_nascita", "Data di nascita", "nascita|data nasc|nato il|birth date|dob", "date", P),
    F("luogo_nascita", "Luogo di nascita", "luogo nasc|nato a|comune nascita", group=P), F("sesso", "Sesso", "genere|gender|m f", group=P),
    F("email", "Email", "e mail|mail|posta elettronica", "email", P), F("cellulare", "Cellulare", "cell|mobile|telefono cellulare|cel|whatsapp", "phone", P),
    F("telefono", "Telefono", "tel|telefono fisso|phone", "phone", P), F("indirizzo", "Indirizzo", "via|address|residenza", group=P), F("cap", "CAP", "codice postale|zip", group=P),
    F("citta", "Comune", "citta|città|localita|city", group=P), F("provincia", "Provincia", "prov|pr", group=P), F("nazione", "Nazione", "paese|stato|country", group=P),
    F("taglia", "Taglia", "taglia maglia|size|t shirt", group=P),
]
STAFF_FIELDS = [
    F("categoria", "Classificazione", "staff volontario|tipo|ruolo staff|classificazione"), F("evento", "Evento", "event|manifestazione|gara"),
    F("team", "Team", "squadra|gruppo"), F("ruolo", "Mansione", "mansione|ruolo|incarico|compito"), F("area", "Area operativa", "area|settore operativo"),
    F("preferenza", "Preferenza attività", "preferenza|attivita preferita|disponibile per"), F("disponibilita", "Disponibilità", "disponibile|giorni|turni disponibili"),
    F("note_operative", "Note operative", "note|annotazioni"),
]
SOCI_FIELDS = [
    F("numero_socio", "Numero socio", "n socio|num socio|matricola"), F("data_iscrizione", "Data iscrizione", "iscrizione|iscritto il|data adesione", "date"),
    F("stato_socio", "Stato socio", "stato"), F("tipo_socio", "Tipo socio", "tipo|categoria socio"),
    F("ente", "Federazione o ente", "federazione|ente|eps|ente promozione"), F("stagione", "Stagione sportiva", "stagione|anno sportivo|season"),
    F("numero_tessera", "Numero tessera", "tessera|n tessera|cartellino"), F("categoria_tessera", "Categoria tesseramento", "categoria|cat"),
    F("data_scadenza_tessera", "Scadenza tessera", "scadenza tesseramento|validita tessera", "date"),
    F("quota_descrizione", "Quota: descrizione", "quota|causale"), F("quota_importo", "Quota: importo", "importo|importo quota|euro", "number"),
    F("quota_scadenza", "Quota: scadenza", "scadenza quota|scadenza pagamento", "date"), F("quota_data_pagamento", "Quota: data pagamento", "pagato il|data pagamento", "date"),
    F("quota_importo_pagato", "Quota: importo pagato", "pagato|versato", "number"), F("quota_metodo", "Quota: metodo", "metodo pagamento|modalita"),
]
COMPANY_FIELDS = [
    F("nome", "Ragione sociale", "azienda|nome azienda|denominazione|ditta|societa|company", required=True), F("partita_iva", "Partita IVA", "p iva|piva|vat|p iva cf"),
    F("settore", "Settore", "categoria|attivita"), F("email", "Email", "e mail|mail|pec", "email"), F("telefono", "Telefono", "tel|phone", "phone"),
    F("sito_web", "Sito web", "sito|web|url|website"), F("indirizzo", "Indirizzo", "via|address|sede"), F("cap", "CAP", "zip"), F("citta", "Comune", "citta|città|city"),
    F("provincia", "Provincia", "prov"), F("regione", "Regione"), F("nazione", "Nazione", "paese|country"), F("note", "Note"),
]
SPONSOR_FIELDS = [
    F("azienda", "Azienda", "sponsor|partner|ragione sociale|nome azienda", required=True), F("partita_iva", "Partita IVA", "piva|p iva"),
    F("email", "Email azienda", "mail|e mail", "email"), F("evento", "Evento", "event|manifestazione"), F("tipo", "Tipo", "tipologia|sponsor partner"),
    F("fase", "Fase trattativa", "fase|stato trattativa"), F("livello", "Livello", "livello sponsorship|pacchetto"), F("valore", "Valore previsto", "valore|importo|budget", "number"),
    F("valore_confermato", "Valore confermato", "confermato|incassato", "number"), F("referente", "Referente", "contatto|referente email"), F("note", "Note"),
]
LODGING_FIELDS = [
    F("persona", "Persona (nome e cognome)", "ospite|nominativo|nome cognome|persona", required=True), F("email", "Email persona", "mail", "email"),
    F("evento", "Evento", "event"), F("struttura_nome", "Struttura", "hotel|albergo|struttura ricettiva"), F("check_in", "Check-in", "arrivo|dal", "date"),
    F("check_out", "Check-out", "partenza|al", "date"), F("tipo_camera", "Tipo camera", "camera|tipologia camera"), F("numero_camera", "Numero camera", "n camera|stanza"),
    F("costo", "Costo", "prezzo|importo", "number"), F("note", "Note"),
]
MEAL_FIELDS = [
    F("persona", "Persona (nome e cognome)", "ospite|nominativo|nome cognome|persona", required=True), F("email", "Email persona", "mail", "email"),
    F("evento", "Evento", "event"), F("tipo_pasto", "Tipo pasto", "pasto|colazione pranzo cena"), F("data_inizio", "Data", "giorno|data pasto|dal", "date"),
    F("data_fine", "Fino al", "al|data fine", "date"), F("struttura_nome", "Ristorante / struttura", "ristorante|luogo pasto"), F("orario", "Orario", "ora"),
    F("costo", "Costo", "prezzo|importo", "number"), F("note", "Note"),
]
PIPELINE_FIELDS = [
    F("titolo", "Titolo attività", "attivita|attività|task|scheda|cosa fare|titolo|todo", required=True), F("descrizione", "Descrizione", "dettaglio|descr"),
    F("fase", "Fase / Categoria", "fase|categoria|colonna|area|stage"), F("stato", "Stato", "status|avanzamento"), F("priorita", "Priorità", "priority|urgenza"),
    F("responsabile", "Responsabile", "assegnato a|referente|owner|incaricato|chi"), F("scadenza", "Data scadenza", "scadenza|entro il|deadline|due date|data limite", "date"),
    F("evento", "Evento / Pipeline", "pipeline|evento|event|progetto"), F("azienda", "Azienda collegata", "organizzazione|fornitore|sponsor"),
    F("contatto", "Contatto", "persona|contatto email"), F("costo_previsto", "Costo previsto", "budget|preventivo", "number"),
    F("costo_effettivo", "Costo effettivo", "speso|consuntivo", "number"), F("note", "Note"), F("codice_esterno", "Codice esterno", "id|codice|riferimento|ref"),
]
TARGETS = {
    "persone": {"label": "Staff / Volontari", "fields": PERSON_FIELDS + STAFF_FIELDS, "module": None},
    "soci": {"label": "Gestione Società · Soci e Tesserati", "fields": PERSON_FIELDS + SOCI_FIELDS, "module": "gestione-societa"},
    "aziende": {"label": "Aziende", "fields": COMPANY_FIELDS, "module": None},
    "sponsor": {"label": "Sponsor & Partner", "fields": SPONSOR_FIELDS, "module": None},
    "pernottamenti": {"label": "Ospitalità · Pernottamenti", "fields": LODGING_FIELDS, "module": None},
    "pasti": {"label": "Ospitalità · Pasti", "fields": MEAL_FIELDS, "module": None},
    "pipeline": {"label": "Pipeline", "fields": PIPELINE_FIELDS, "module": "pipeline"},
}
STATI_PIPE = {"da fare": "da_fare", "todo": "da_fare", "da iniziare": "da_fare", "aperta": "da_fare", "in corso": "in_corso", "in lavorazione": "in_corso", "doing": "in_corso",
              "in attesa": "in_attesa", "sospesa": "in_attesa", "bloccata": "in_attesa", "completata": "completata", "completato": "completata", "fatto": "completata",
              "terminato": "completata", "done": "completata", "chiusa": "completata"}
PRIO = {"normale": "normale", "bassa": "normale", "media": "importante", "importante": "importante", "alta": "importante", "critica": "critica", "urgente": "critica"}
CAT_STAFF = {"staff": "staff", "collaboratore": "collaboratore", "volontario": "volontario", "volontari": "volontario", "da classificare": "da_classificare"}


class ParseIn(BaseModel):
    sheet: Optional[str] = None
    header_row: int = 1
    layout: str = "rows"  # rows | columns (pipeline: colonne = fasi)


class PlanIn(ParseIn):
    target: str
    mapping: dict = {}
    mode: str = "both"  # new | update | both
    options: dict = {}


class ConfigIn(BaseModel):
    name: str
    target: str
    mapping: dict = {}
    options: dict = {}
    globale: bool = False


def suggest(columns: list, fields: list) -> dict:
    out, used = {}, set()
    for col in columns:
        n = _norm(col)
        hit = next((f["key"] for f in fields if f["key"] not in used and n in f["syn"]), None)
        hit = hit or next((f["key"] for f in fields if f["key"] not in used and any(len(s) > 3 and (s in n or n in s) for s in f["syn"] if n)), None)
        out[col] = hit or ""
        if hit:
            used.add(hit)
    return out


def read_book(data: bytes, ext: str) -> list:
    """Tutti i fogli come [{name, rows}] (righe grezze, intestazione inclusa)."""
    if ext == "csv":
        text = next((data.decode(e) for e in ("utf-8-sig", "cp1252", "latin-1") if _try(data, e)), data.decode("latin-1"))
        try:
            dialect = csv.Sniffer().sniff(text[:5000], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        sep = getattr(dialect, "delimiter", ",")
        return [{"name": "CSV", "sep": sep, "rows": [r for r in csv.reader(io.StringIO(text), dialect) if any(c.strip() for c in r)][:MAX_ROWS + 50]}]
    if ext == "xlsx":
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        return [{"name": ws.title, "rows": [[_cell(c) for c in r] for r in ws.iter_rows(values_only=True) if any(_cell(c) for c in r)][:MAX_ROWS + 50]} for ws in wb.worksheets]
    import xlrd
    wb = xlrd.open_workbook(file_contents=data)
    out = []
    for sh in wb.sheets():
        rows = []
        for i in range(sh.nrows):
            r = [xlrd.xldate_as_datetime(c.value, wb.datemode).strftime("%Y-%m-%d") if c.ctype == 3 else _cell(c.value) for c in sh.row(i)]
            if any(r):
                rows.append(r)
        out.append({"name": sh.name, "rows": rows[:MAX_ROWS + 50]})
    return out


def table(sheet: dict, header_row: int, layout: str = "rows"):
    rows = sheet["rows"][max(header_row, 1) - 1:]
    if not rows:
        return [], []
    cols, seen = [], {}
    for i, c in enumerate(rows[0]):
        c = (str(c) or "").strip() or f"Colonna {i + 1}"
        seen[c] = seen.get(c, 0) + 1
        cols.append(c if seen[c] == 1 else f"{c} ({seen[c]})")
    data = [[(str(r[i]) if i < len(r) else "").strip() for i in range(len(cols))] for r in rows[1:]]
    if layout == "columns":  # formato B: ogni colonna \u00e8 una fase, ogni cella un'attivit\u00e0
        data = [[cell, col] for r in data for col, cell in zip(cols, r) if cell]
        cols = ["Attività", "Fase"]
    return cols, data[:MAX_ROWS]


def digits(v) -> str:
    return re.sub(r"\D", "", v or "")[-9:]


def build(db, deps: dict):
    r = APIRouter(prefix="/imports")
    require_admin, record_audit, normalize, asd_mod = deps["require_admin"], deps["record_audit"], deps["normalize"], deps["asd"]
    seed_categories = deps["seed_pipeline_categories"]

    def is_super(u: dict) -> bool:
        return u.get("role") == "superadmin"

    async def admin(user: dict = Depends(require_admin)):
        if user.get("platform_scope") or not user.get("org_id"):
            raise HTTPException(status_code=400, detail="Seleziona prima l'organizzazione dalla tendina Org attiva")
        if user.get("org_role") not in ("admin_org", "superadmin") and not (user.get("perm") or {}).get("admin", True):
            raise HTTPException(status_code=403, detail="Importazione riservata agli amministratori dell'organizzazione")
        return user

    async def module_state(org: str) -> dict:
        pipe = await db.event_pipelines.count_documents({"org_id": org, "active": True})
        return {"gestione-societa": await asd_mod["is_active"](org), "pipeline": pipe > 0}

    async def has_data(org: str, t: str) -> bool:
        coll = {"soci": "asd_soci", "pipeline": "pipeline_tasks", "persone": "staff", "aziende": "companies", "sponsor": "deals", "pernottamenti": "lodgings", "pasti": "meals"}[t]
        return bool(await db[coll].find_one({"org_id": org}, {"_id": 1}))

    async def allowed(user: dict, t: str):
        if t not in TARGETS:
            raise HTTPException(status_code=400, detail="Modulo di destinazione non valido")
        m = TARGETS[t]["module"]
        if m == "gestione-societa" and not is_super(user) and not (await module_state(user["org_id"]))[m]:
            raise HTTPException(status_code=403, detail="Il modulo Gestione Società non è attivo per questa organizzazione")

    # ---------- abbinamenti di riferimento (eventi, persone, aziende) ----------
    async def lookups(org: str) -> dict:
        evs = await db.events.find({"org_id": org}, {"_id": 0, "id": 1, "nome": 1, "edizione": 1, "data_inizio": 1}).to_list(2000)
        people = await db.persons.find({"org_id": org, "archiviato": {"$ne": True}}, {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "email": 1}).to_list(50000)
        return {"events": evs, "people": people}

    def match_event(v: str, evs: list, fixed: dict):
        if not v:
            return None
        if v in fixed:
            return fixed[v] or None
        n = _norm(v)
        exact = [e for e in evs if _norm(e["nome"]) == n or _norm(f"{e['nome']} {e.get('edizione') or ''}") == n]
        return exact[0]["id"] if len(exact) == 1 else None  # nomi simili: mai collegare in automatico

    def match_person_name(v: str, people: list, fixed: dict):
        if not v:
            return None
        if v in fixed:
            return fixed[v] or None
        n = _norm(v)
        hits = [p for p in people if n and (n == _norm(p.get("email")) or n in (_norm(f"{p.get('nome')} {p.get('cognome') or ''}"), _norm(f"{p.get('cognome') or ''} {p.get('nome')}")))]
        return hits[0]["id"] if len(hits) == 1 else None

    # ---------- parsing ----------
    def records(cols: list, data: list, mapping: dict, fields: list, first_row: int = 2) -> list:
        kinds = {f["key"]: f["type"] for f in fields}
        out = []
        for i, row in enumerate(data):
            rec, errs = {}, []
            for col, val in zip(cols, row):
                k = mapping.get(col)
                if not k or not val:
                    continue
                t = kinds.get(k)
                if t == "date":
                    d = _date(val)
                    if not d:
                        errs.append(f"{col}: data non valida ({val})")
                        continue
                    val = d
                elif t == "number":
                    raw = val.replace("€", "").replace(" ", "").strip()
                    if "," in raw:
                        raw = raw.replace(".", "").replace(",", ".")
                    elif re.match(r"^\d{1,3}(\.\d{3})+$", raw):
                        raw = raw.replace(".", "")
                    try:
                        val = float(raw)
                    except ValueError:
                        errs.append(f"{col}: numero non valido ({val})")
                        continue
                elif t == "email":
                    val = val.strip().lower()
                    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", val):
                        errs.append(f"{col}: email non valida ({val})")
                        continue
                elif k == "codice_fiscale":
                    val = val.replace(" ", "").upper()
                rec[k] = val
            for f in fields:
                if f["required"] and not rec.get(f["key"]):
                    errs.append(f"{f['label']}: campo obbligatorio")
            out.append({"row": i + first_row, "data": rec, "errors": errs})
        return out

    # ---------- persone: regole duplicati condivise (Staff / Volontari e Gestione Società) ----------
    async def person_match(org: str, d: dict) -> tuple:
        strong = {}
        if d.get("codice_fiscale") and CF_RX.match(d["codice_fiscale"]):
            strong["codice fiscale"] = await db.persons.distinct("id", {"org_id": org, "codice_fiscale": d["codice_fiscale"]})
        if d.get("email"):
            strong["email"] = await db.persons.distinct("id", {"org_id": org, "email": {"$regex": f"^{re.escape(d['email'])}$", "$options": "i"}})
        if len(digits(d.get("cellulare"))) >= 8:
            strong["cellulare"] = await db.persons.distinct("id", {"org_id": org, "cellulare": {"$regex": r"\D*".join(digits(d["cellulare"])) + r"\D*$"}})
        ids = {i for v in strong.values() for i in v}
        if len(ids) == 1:
            return "esistente", ids.pop(), ""
        if len(ids) > 1:
            return "conflitto", None, "i dati corrispondono a persone diverse (" + ", ".join(k for k, v in strong.items() if v) + ")"
        if d.get("nome") and d.get("cognome") and d.get("data_nascita"):
            q = {"org_id": org, "nome": {"$regex": f"^{re.escape(d['nome'])}$", "$options": "i"}, "cognome": {"$regex": f"^{re.escape(d['cognome'])}$", "$options": "i"}, "data_nascita": d["data_nascita"]}
            if await db.persons.count_documents(q):
                return "possibile_duplicato", None, "stesso nome, cognome e data di nascita: verifica e collega a mano"
        return "nuovo", None, ""

    PERSON_KEYS = [f["key"] for f in PERSON_FIELDS]

    def file_key(d: dict) -> Optional[str]:
        for k in ("codice_fiscale", "email"):
            if d.get(k):
                return f"{k}:{d[k].lower()}"
        if digits(d.get("cellulare")):
            return "cell:" + digits(d["cellulare"])
        return None

    # ---------- piano (anteprima = stesso calcolo dell'esecuzione) ----------
    async def plan(user: dict, job: dict, body: PlanIn) -> dict:
        org, t = user["org_id"], body.target
        fields, opts = TARGETS[t]["fields"], body.options or {}
        sheets = opts.get("sheets") if t == "pipeline" and opts.get("sheets") else [{"sheet": body.sheet, "event_id": opts.get("event_id")}]
        lk = await lookups(org)
        ev_fix, resp_fix = opts.get("eventi") or {}, opts.get("responsabili") or {}
        items, seen, task_cache = [], set(), {}
        active_pipes = set(await db.event_pipelines.distinct("event_id", {"org_id": org, "active": True})) if t == "pipeline" else set()
        for sh in sheets:
            sheet = next((s for s in job["sheets"] if s["name"] == (sh.get("sheet") or job["sheets"][0]["name"])), None)
            if not sheet:
                raise HTTPException(status_code=400, detail=f"Foglio non trovato: {sh.get('sheet')}")
            cols, data = table(sheet, body.header_row, body.layout)
            mapping = {"Attività": "titolo", "Fase": "fase"} if body.layout == "columns" else body.mapping
            for rec in records(cols, data, mapping, fields, (max(body.header_row, 1) + 1) if body.layout != "columns" else 2):
                rec["sheet"] = sheet["name"]
                d = rec["data"]
                if t in ("persone", "pipeline", "sponsor", "pernottamenti", "pasti"):
                    eid = match_event(d.get("evento"), lk["events"], ev_fix) or sh.get("event_id") or opts.get("event_id")
                    if d.get("evento") and not match_event(d.get("evento"), lk["events"], ev_fix) and not sh.get("event_id") and not opts.get("event_id"):
                        rec["errors"].append(f"Evento non riconosciuto: {d['evento']} (abbinalo a mano)")
                    rec["event_id"] = eid
                    if t in ("pipeline", "sponsor", "pernottamenti", "pasti") and not eid:
                        rec["errors"].append("Evento di destinazione mancante")
                    if t == "pipeline" and eid and not is_super(user) and eid not in active_pipes:
                        rec["errors"].append("Pipeline non attiva su questo evento: attivala prima di importare")
                if rec["errors"]:
                    rec["status"], rec["message"] = "errore", "; ".join(rec["errors"])
                else:
                    await classify(org, t, rec, lk, resp_fix, opts, seen, body.mode, task_cache)
                items.append(rec)
        cnt = {k: sum(1 for x in items if x["status"] == k) for k in ("nuovo", "esistente", "possibile_duplicato", "conflitto", "duplicato_file", "errore", "escluso")}
        act = {"crea": sum(1 for x in items if x.get("action") == "crea"), "aggiorna": sum(1 for x in items if x.get("action") == "aggiorna"),
               "ignora": sum(1 for x in items if x.get("action") in (None, "ignora"))}
        excluded = [c for c, k in (body.mapping or {}).items() if not k] if body.layout != "columns" else []
        out = {"rows": len(items), "counts": cnt, "actions": act, "excluded": excluded, "items": items}
        if t == "pipeline":
            out["pipeline"] = await pipeline_summary(org, items, opts, lk)
        return out

    async def classify(org, t, rec, lk, resp_fix, opts, seen, mode, task_cache):
        d = rec["data"]
        if t in ("persone", "soci"):
            fk = file_key(d)
            if fk and fk in seen:
                rec.update(status="duplicato_file", message="Persona ripetuta nel file: riga ignorata")
                return
            if fk:
                seen.add(fk)
            st, pid, msg = await person_match(org, d)
            rec.update(status=st, message=msg, persona_id=pid)
            if t == "soci" and pid and await db.asd_soci.find_one({"org_id": org, "persona_id": pid}, {"_id": 1}):
                rec["socio_esistente"] = True
        elif t == "aziende" or t == "sponsor":
            nome = d.get("nome") or d.get("azienda")
            q = [{"partita_iva": d["partita_iva"]}] if d.get("partita_iva") else []
            q.append({"nome": {"$regex": f"^{re.escape(nome.strip())}$", "$options": "i"}})
            hits = await db.companies.distinct("id", {"org_id": org, "$or": q})
            rec["azienda_id"] = hits[0] if len(hits) == 1 else None
            if t == "aziende":
                rec.update(status="nuovo" if not hits else "esistente" if len(hits) == 1 else "conflitto", message="" if len(hits) < 2 else "più aziende corrispondenti")
            else:
                deal = rec["azienda_id"] and await db.deals.find_one({"org_id": org, "azienda_id": rec["azienda_id"], "evento_id": rec["event_id"], "tipo": d.get("tipo") or "sponsor"}, {"_id": 0, "id": 1})
                rec["deal_id"] = deal["id"] if deal else None
                rec.update(status="esistente" if deal else ("conflitto" if len(hits) > 1 else "nuovo"), message="più aziende corrispondenti" if len(hits) > 1 else "")
                rec["referente_id"] = match_person_name(d.get("referente"), lk["people"], {})
        elif t in ("pernottamenti", "pasti"):
            pid = match_person_name(d.get("email") or d.get("persona"), lk["people"], {}) or match_person_name(d.get("persona"), lk["people"], {})
            if not pid:
                rec.update(status="errore", message=f"Persona non trovata in anagrafica: {d.get('persona')} (importala prima in Staff / Volontari)")
                return
            rec["persona_id"] = pid
            if t == "pernottamenti":
                q = {"org_id": org, "persona_id": pid, "evento_id": rec["event_id"], "check_in": d.get("check_in")}
                ex = await db.lodgings.find_one(q, {"_id": 0, "id": 1})
            else:
                ex = await db.meals.find_one({"org_id": org, "persona_id": pid, "evento_id": rec["event_id"], "tipo_pasto": d.get("tipo_pasto"), "data_inizio": d.get("data_inizio")}, {"_id": 0, "id": 1})
            rec["record_id"] = ex["id"] if ex else None
            rec.update(status="esistente" if ex else "nuovo", message="")
        elif t == "pipeline":
            fase = d.get("fase") or ""
            fm = (opts.get("fasi") or {}).get(fase) if fase else None
            if fm and fm.get("action") == "skip":
                rec.update(status="escluso", message=f"Fase esclusa dall'importazione: {fase}", action="ignora")
                return
            rec["categoria_nome"] = (fm or {}).get("name") or fase or None
            rec["responsabile_id"] = match_person_name(d.get("responsabile"), lk["people"], resp_fix)
            if d.get("responsabile") and not rec["responsabile_id"]:
                rec["avviso"] = f"Responsabile non trovato: {d['responsabile']}"
            ex = None
            if d.get("codice_esterno"):
                ex = await db.pipeline_tasks.find_one({"org_id": org, "event_id": rec["event_id"], "import_ref": d["codice_esterno"]}, {"_id": 0})
            if not ex:
                if rec["event_id"] not in task_cache:
                    task_cache[rec["event_id"]] = {}
                    for y in await db.pipeline_tasks.find({"org_id": org, "event_id": rec["event_id"]}, {"_id": 0}).to_list(10000):
                        task_cache[rec["event_id"]].setdefault(_norm(y.get("titolo")), y)
                ex = task_cache[rec["event_id"]].get(_norm(d.get("titolo")))
            fk = f"{rec['event_id']}:{_norm(d.get('titolo'))}:{_norm(rec['categoria_nome'])}"
            if fk in seen:
                rec.update(status="duplicato_file", message="Attività ripetuta nel file", action="ignora")
                return
            seen.add(fk)
            rec["record_id"] = ex["id"] if ex else None
            modified = ex and ex.get("imported_at") and ex.get("updated_at", "") > ex["imported_at"]
            if ex and (modified or not ex.get("imported_at")) and not opts.get("sovrascrivi_modificate"):
                rec.update(status="conflitto", message="Attività già presente e modificata dagli utenti: conferma la sovrascrittura per aggiornarla")
            else:
                rec.update(status="esistente" if ex else "nuovo", message="")
        st = rec["status"]
        rec["action"] = rec.get("action") or ("crea" if st == "nuovo" and mode in ("new", "both") else "aggiorna" if st == "esistente" and mode in ("update", "both") else "ignora")
        if t == "soci" and st == "esistente" and mode == "new" and not rec.get("socio_esistente"):
            rec["action"] = "collega"  # persona gi\u00e0 in anagrafica: diventa socio senza duplicarla

    async def pipeline_summary(org, items, opts, lk) -> dict:
        evs = {e["id"]: e["nome"] for e in lk["events"]}
        by_cat, by_ev, cat_new, known = {}, {}, set(), {}
        for x in items:
            if x.get("action") not in ("crea", "aggiorna"):
                continue
            c = x.get("categoria_nome") or "Senza fase"
            by_cat[c] = by_cat.get(c, 0) + 1
            by_ev[evs.get(x["event_id"], "?")] = by_ev.get(evs.get(x["event_id"], "?"), 0) + 1
            if x["event_id"] not in known:
                known[x["event_id"]] = {_norm(n) for n in await db.pipeline_categories.distinct("name", {"org_id": org, "event_id": x["event_id"]})}
            if x.get("categoria_nome") and _norm(x["categoria_nome"]) not in known[x["event_id"]]:
                cat_new.add(x["categoria_nome"])
        active = {p["event_id"] for p in await db.event_pipelines.find({"org_id": org, "active": True}, {"_id": 0, "event_id": 1}).to_list(2000)}
        ev_ids = {x["event_id"] for x in items if x.get("event_id")}
        return {"schede_per_fase": by_cat, "schede_per_evento": by_ev, "fasi_da_creare": sorted(cat_new),
                "responsabili_collegati": sum(1 for x in items if x.get("responsabile_id")), "responsabili_non_trovati": sorted({x["data"]["responsabile"] for x in items if x.get("avviso")}),
                "eventi_senza_pipeline_attiva": [evs.get(e, e) for e in ev_ids if e not in active]}

    # ---------- esecuzione ----------
    async def apply(user: dict, job: dict, body: PlanIn, p: dict) -> dict:
        org, t, now, jid = user["org_id"], body.target, _now(), job["id"]
        created, updated, skipped, errors = {}, 0, 0, []
        extra = {"pipeline_attivate": 0, "fasi_create": 0, "schede": 0, "collegamenti": 0}
        mark = {"import_job_id": jid, "imported_at": now}

        def add(coll, i):
            created.setdefault(coll, []).append(i)

        async def upsert_person(x) -> str:
            d = {k: x["data"][k] for k in PERSON_KEYS if x["data"].get(k)}
            if x.get("persona_id"):
                if x["action"] == "aggiorna" and d:
                    await db.persons.update_one({"org_id": org, "id": x["persona_id"]}, {"$set": {**normalize("persons", d), "updated_at": now}})
                return x["persona_id"]
            pid = uuid.uuid4().hex
            await db.persons.insert_one({**normalize("persons", d), "id": pid, "org_id": org, "created_at": now, "updated_at": now, **mark,
                                         "provenienza": {"tipo": "importazione", "at": now, "by": user.get("email"), "file": job["filename"]}})
            add("persons", pid)
            return pid

        teams = {}
        cats = {}
        enti = await asd_mod["enti"](org) if t == "soci" else []
        for x in p["items"]:
            if x.get("action") not in ("crea", "aggiorna", "collega"):
                skipped += 1
                if x["status"] in ("errore", "conflitto", "possibile_duplicato", "duplicato_file", "escluso"):
                    errors.append({"foglio": x["sheet"], "riga": x["row"], "stato": x["status"], "messaggio": x.get("message")})
                continue
            d = x["data"]
            try:
                if t == "persone":
                    pid = await upsert_person(x)
                    if x.get("event_id"):
                        cat = CAT_STAFF.get(_norm(d.get("categoria")), "da_classificare")
                        team_id = None
                        if d.get("team"):
                            key = (x["event_id"], _norm(d["team"]))
                            if key not in teams:
                                tm = await db.teams.find_one({"org_id": org, "evento_id": x["event_id"], "nome": {"$regex": f"^{re.escape(d['team'])}$", "$options": "i"}}, {"_id": 0, "id": 1})
                                if not tm:
                                    tm = {"id": uuid.uuid4().hex}
                                    await db.teams.insert_one({"id": tm["id"], "org_id": org, "evento_id": x["event_id"], "nome": d["team"], "created_at": now, **mark})
                                    add("teams", tm["id"])
                                teams[key] = tm["id"]
                            team_id = teams[key]
                        link = {k: v for k, v in {"ruolo": d.get("ruolo"), "area": d.get("area"), "preferenza": d.get("preferenza"), "team_id": team_id,
                                                  "note_operative": " · ".join(v for v in (d.get("note_operative"), d.get("disponibilita") and f"Disponibilità: {d['disponibilita']}") if v) or None}.items() if v}
                        ex = await db.staff.find_one({"org_id": org, "persona_id": pid, "evento_id": x["event_id"]}, {"_id": 0, "id": 1})
                        if ex:
                            if x["action"] == "aggiorna" and link:
                                await db.staff.update_one({"org_id": org, "id": ex["id"]}, {"$set": {**link, "updated_at": now}})
                        else:
                            sid = uuid.uuid4().hex
                            await db.staff.insert_one({"id": sid, "org_id": org, "persona_id": pid, "evento_id": x["event_id"], "categoria": cat, "stato": "da_contattare",
                                                       **link, "created_at": now, "updated_at": now, **mark})
                            add("staff", sid)
                            extra["collegamenti"] += 1
                elif t == "soci":
                    pid = await upsert_person(x)
                    s = await db.asd_soci.find_one({"org_id": org, "persona_id": pid}, {"_id": 0, "id": 1})
                    assoc = {k: v for k, v in {"numero_socio": d.get("numero_socio"), "data_iscrizione": d.get("data_iscrizione"),
                                               "stato": (_norm(d.get("stato_socio")).replace(" ", "_") or None), "tipo": (_norm(d.get("tipo_socio")) or None)}.items() if v}
                    if assoc.get("stato") not in (None, "attivo", "sospeso", "cessato"):
                        assoc.pop("stato")
                    if assoc.get("tipo") not in (None, "socio", "tesserato", "socio_tesserato"):
                        assoc.pop("tipo")
                    if s:
                        sid = s["id"]
                        if x["action"] == "aggiorna" and assoc:
                            await db.asd_soci.update_one({"org_id": org, "id": sid}, {"$set": {**assoc, "updated_at": now}})
                    else:
                        sid = uuid.uuid4().hex
                        await db.asd_soci.insert_one({"tipo": "socio", "stato": "attivo", **assoc, "id": sid, "org_id": org, "persona_id": pid, "created_at": now, "updated_at": now, **mark})
                        add("asd_soci", sid)
                    if d.get("stagione") and d.get("ente"):
                        k = _norm(d["ente"])
                        e = next((e for e in enti if k in (_norm(e["sigla"]), _norm(e.get("nome")), _norm(asd_mod["ente_label"](e))) or k.split(" ")[0] == _norm(e["sigla"])), None)
                        if not e:
                            errors.append({"foglio": x["sheet"], "riga": x["row"], "stato": "avviso", "messaggio": f"Ente non in elenco: {d['ente']} (tesseramento non creato, aggiungilo in Impostazioni)"})
                        elif not await db.asd_tesseramenti.find_one({"org_id": org, "socio_id": sid, "stagione": d["stagione"], "ente_id": e["id"]}, {"_id": 1}):
                            tid = uuid.uuid4().hex
                            await db.asd_tesseramenti.insert_one({"id": tid, "org_id": org, "socio_id": sid, "stagione": d["stagione"][:20], "ente_id": e["id"], "ente": asd_mod["ente_label"](e),
                                                                  "numero_tessera": d.get("numero_tessera"), "categoria": d.get("categoria_tessera"), "data_scadenza": d.get("data_scadenza_tessera"),
                                                                  "annullato": False, "created_at": now, "updated_at": now, **mark})
                            add("asd_tesseramenti", tid)
                    if d.get("quota_importo") is not None and (d.get("quota_descrizione") or d.get("stagione")):
                        desc = d.get("quota_descrizione") or f"Quota {d['stagione']}"
                        if not await db.asd_quote.find_one({"org_id": org, "socio_id": sid, "descrizione": desc, "stagione": d.get("stagione")}, {"_id": 1}):
                            qid = uuid.uuid4().hex
                            await db.asd_quote.insert_one({"id": qid, "org_id": org, "socio_id": sid, "descrizione": desc[:200], "stagione": d.get("stagione"), "importo": d["quota_importo"],
                                                           "data_scadenza": d.get("quota_scadenza"), "data_pagamento": d.get("quota_data_pagamento"),
                                                           "importo_pagato": d.get("quota_importo_pagato") if d.get("quota_importo_pagato") is not None else (d["quota_importo"] if d.get("quota_data_pagamento") else None),
                                                           "metodo": d.get("quota_metodo"), "created_at": now, "updated_at": now, **mark})
                            add("asd_quote", qid)
                elif t in ("aziende", "sponsor"):
                    cd = {k: d[k] for k in ("partita_iva", "settore", "email", "telefono", "sito_web", "indirizzo", "cap", "citta", "provincia", "regione", "nazione", "note") if d.get(k) and (t == "aziende" or k in ("partita_iva", "email"))}
                    cid = x.get("azienda_id")
                    if cid and t == "aziende" and x["action"] == "aggiorna" and cd:
                        await db.companies.update_one({"org_id": org, "id": cid}, {"$set": {**cd, "updated_at": now}})
                    if not cid:
                        cid = uuid.uuid4().hex
                        await db.companies.insert_one({"nazione": "Italia", "tipo": "sponsor" if t == "sponsor" else "azienda", **cd, "nome": d.get("nome") or d.get("azienda"),
                                                       "id": cid, "org_id": org, "created_at": now, "updated_at": now, **mark})
                        add("companies", cid)
                    if t == "sponsor":
                        dd = {k: v for k, v in {"fase": d.get("fase") and _norm(d["fase"]).replace(" ", "_"), "livello": d.get("livello"), "valore": d.get("valore"),
                                                "valore_confermato": d.get("valore_confermato"), "referente_id": x.get("referente_id"), "note": d.get("note")}.items() if v not in (None, "")}
                        if x.get("deal_id"):
                            if x["action"] == "aggiorna" and dd:
                                await db.deals.update_one({"org_id": org, "id": x["deal_id"]}, {"$set": {**dd, "updated_at": now}})
                        else:
                            did = uuid.uuid4().hex
                            await db.deals.insert_one({"fase": "prospect", "stato": "aperta", "valore": 0, "valore_confermato": 0, **dd, "tipo": d.get("tipo") or "sponsor",
                                                       "azienda_id": cid, "evento_id": x["event_id"], "id": did, "org_id": org, "created_at": now, "updated_at": now, **mark})
                            add("deals", did)
                elif t in ("pernottamenti", "pasti"):
                    coll = "lodgings" if t == "pernottamenti" else "meals"
                    keys = [f["key"] for f in (LODGING_FIELDS if t == "pernottamenti" else MEAL_FIELDS) if f["key"] not in ("persona", "email", "evento")]
                    dd = {k: d[k] for k in keys if d.get(k) not in (None, "")}
                    if x.get("record_id"):
                        if x["action"] == "aggiorna" and dd:
                            await db[coll].update_one({"org_id": org, "id": x["record_id"]}, {"$set": {**dd, "updated_at": now}})
                    else:
                        rid = uuid.uuid4().hex
                        await db[coll].insert_one({**dd, "persona_id": x["persona_id"], "evento_id": x["event_id"], "id": rid, "org_id": org, "created_at": now, "updated_at": now, **mark})
                        add(coll, rid)
                elif t == "pipeline":
                    eid = x["event_id"]
                    if not await db.pipeline_categories.count_documents({"org_id": org, "event_id": eid}):
                        await seed_categories(org, eid)  # stesse categorie iniziali dell'attivazione, tracciate per l'annullamento
                        await db.pipeline_categories.update_many({"org_id": org, "event_id": eid}, {"$set": {**mark, "updated_at": now}})
                        for cid0 in await db.pipeline_categories.distinct("id", {"org_id": org, "event_id": eid}):
                            add("pipeline_categories", cid0)
                    cat_id = None
                    if x.get("categoria_nome"):
                        ck = (eid, _norm(x["categoria_nome"]))
                        if ck not in cats:
                            c = await db.pipeline_categories.find_one({"org_id": org, "event_id": eid, "name": {"$regex": f"^{re.escape(x['categoria_nome'])}$", "$options": "i"}}, {"_id": 0, "id": 1})
                            if not c:
                                c = {"id": uuid.uuid4().hex}
                                order = await db.pipeline_categories.count_documents({"org_id": org, "event_id": eid})
                                await db.pipeline_categories.insert_one({"id": c["id"], "org_id": org, "event_id": eid, "name": x["categoria_nome"][:80], "order": order,
                                                                         "created_at": now, "updated_at": now, **mark})
                                add("pipeline_categories", c["id"])
                                extra["fasi_create"] += 1
                            cats[ck] = c["id"]
                        cat_id = cats[ck]
                    task = {k: v for k, v in {"titolo": d.get("titolo", "")[:300], "descrizione": d.get("descrizione"), "categoria_id": cat_id,
                                              "stato": STATI_PIPE.get(_norm(d.get("stato"))), "priorita": PRIO.get(_norm(d.get("priorita"))), "scadenza": d.get("scadenza"),
                                              "responsabile_id": x.get("responsabile_id"), "costo_previsto": d.get("costo_previsto"), "costo_effettivo": d.get("costo_effettivo"),
                                              "note": d.get("note"), "import_ref": d.get("codice_esterno")}.items() if v not in (None, "")}
                    if d.get("azienda"):
                        az = await db.companies.distinct("id", {"org_id": org, "nome": {"$regex": f"^{re.escape(d['azienda'])}$", "$options": "i"}})
                        if len(az) == 1:
                            task["azienda_id"] = az[0]
                    if d.get("contatto"):
                        task["persona_id"] = match_person_name(d["contatto"], (await lookups(org))["people"], {}) or None
                    if x.get("record_id"):
                        await db.pipeline_tasks.update_one({"org_id": org, "id": x["record_id"]}, {"$set": {**task, "updated_at": now, "imported_at": now}})
                    else:
                        tid = uuid.uuid4().hex
                        await db.pipeline_tasks.insert_one({"stato": "da_fare", "priorita": "normale", **task, "id": tid, "org_id": org, "event_id": eid,
                                                            "created_at": now, "updated_at": now, **mark})
                        add("pipeline_tasks", tid)
                    extra["schede"] += 1
                    extra["collegamenti"] += int(bool(task.get("responsabile_id"))) + int(bool(task.get("azienda_id"))) + int(bool(task.get("persona_id")))
                if x["action"] == "aggiorna":
                    updated += 1
            except HTTPException as e:
                errors.append({"foglio": x["sheet"], "riga": x["row"], "stato": "errore", "messaggio": str(e.detail)})
        n_created = sum(1 for x in p["items"] if x.get("action") in ("crea", "collega"))
        return {"creati": n_created, "aggiornati": updated, "ignorati": skipped, "errori": errors, "creati_per_collezione": {k: len(v) for k, v in created.items()},
                "refs": created, "pipeline": extra if t == "pipeline" else None}

    # ---------- API ----------
    @r.get("/targets")
    async def targets(user: dict = Depends(admin)):
        st = await module_state(user["org_id"])
        out = []
        for k, v in TARGETS.items():
            m = v["module"]
            active = True if m is None else st[m]
            if not active and not is_super(user) and m == "gestione-societa":
                continue
            out.append({"key": k, "label": v["label"], "module": m, "active": active, "has_data": await has_data(user["org_id"], k),
                        "fields": [{x: f[x] for x in ("key", "label", "type", "group", "required")} for f in v["fields"]]})
        org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0, "nome": 1, "name": 1})
        return {"org": {"id": user["org_id"], "nome": (org or {}).get("nome") or (org or {}).get("name")}, "superadmin": is_super(user), "targets": out,
                "events": (await lookups(user["org_id"]))["events"]}

    @r.post("/upload")
    async def upload(file: UploadFile = File(...), user: dict = Depends(admin)):
        ext = (file.filename or "").rsplit(".", 1)[-1].lower()
        if ext not in ("xlsx", "xls", "csv"):
            raise HTTPException(status_code=400, detail="Formato non supportato: carica un file XLSX, XLS o CSV")
        data = await file.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            raise HTTPException(status_code=400, detail="File troppo grande (massimo 8 MB)")
        try:
            sheets = [s for s in read_book(data, ext) if s["rows"]]
        except Exception:
            raise HTTPException(status_code=400, detail="Impossibile leggere il file: verifica che non sia protetto o danneggiato")
        if not sheets:
            raise HTTPException(status_code=400, detail="Il file non contiene dati")
        job = {"id": uuid.uuid4().hex, "org_id": user["org_id"], "user_id": user["user_id"], "user_email": user.get("email"), "superadmin": is_super(user),
               "filename": (file.filename or "file")[:200], "ext": ext, "sheets": sheets, "status": "caricato", "created_at": _now()}
        await db.import_jobs.insert_one(dict(job))
        return {"id": job["id"], "filename": job["filename"], "sheets": [{"name": s["name"], "rows": len(s["rows"]), "sep": s.get("sep")} for s in sheets]}

    async def get_job(user: dict, jid: str) -> dict:
        j = await db.import_jobs.find_one({"id": jid, "org_id": user["org_id"]}, {"_id": 0})
        if not j:
            raise HTTPException(status_code=404, detail="Importazione non trovata")
        return j

    @r.post("/jobs/{jid}/read")
    async def read(jid: str, body: ParseIn, target: str = "persone", user: dict = Depends(admin)):
        j = await get_job(user, jid)
        sheet = next((s for s in j["sheets"] if s["name"] == (body.sheet or j["sheets"][0]["name"])), None)
        if not sheet:
            raise HTTPException(status_code=400, detail="Foglio non trovato")
        cols, data = table(sheet, body.header_row, body.layout)
        fields = TARGETS.get(target, TARGETS["persone"])["fields"]
        mapping = {"Attività": "titolo", "Fase": "fase"} if body.layout == "columns" else suggest(cols, fields)
        out = {"columns": cols, "preview": data[:20], "total": len(data), "suggested": mapping, "raw_top": sheet["rows"][:6]}
        if target == "pipeline":
            fvals, rvals, evals = set(), set(), set()
            for s in j["sheets"]:  # fasi, responsabili ed eventi di tutti i fogli (formato C)
                c2, d2 = (cols, data) if s is sheet else table(s, body.header_row, body.layout)
                m2 = mapping if s is sheet else ({"Attività": "titolo", "Fase": "fase"} if body.layout == "columns" else suggest(c2, fields))
                for key, acc in (("fase", fvals), ("responsabile", rvals), ("evento", evals)):
                    c = next((c for c, k in m2.items() if k == key), None)
                    if c:
                        acc.update(r[c2.index(c)] for r in d2 if r[c2.index(c)])
            vals = lambda acc: sorted(acc)[:200]  # noqa: E731
            lk = await lookups(user["org_id"])
            cats = sorted(set(await db.pipeline_categories.distinct("name", {"org_id": user["org_id"]})))
            out["pipeline"] = {"fasi": vals(fvals), "categorie_esistenti": cats,
                               "responsabili": [{"valore": v, "persona_id": match_person_name(v, lk["people"], {})} for v in vals(rvals)],
                               "eventi": [{"valore": v, "event_id": match_event(v, lk["events"], {})} for v in vals(evals)],
                               "fogli": [{"sheet": s["name"], "event_id": match_event(s["name"], lk["events"], {})} for s in j["sheets"]]}
        return out

    def trim(p: dict) -> dict:
        return {**{k: v for k, v in p.items() if k != "items"}, "items": [{k: x.get(k) for k in ("sheet", "row", "status", "action", "message", "avviso", "data")} for x in p["items"][:300]]}

    @r.post("/jobs/{jid}/preview")
    async def preview(jid: str, body: PlanIn, user: dict = Depends(admin)):
        await allowed(user, body.target)
        return trim(await plan(user, await get_job(user, jid), body))

    @r.post("/jobs/{jid}/run")
    async def run(jid: str, body: PlanIn, user: dict = Depends(admin)):
        await allowed(user, body.target)
        j = await get_job(user, jid)
        if j["status"] != "caricato":
            raise HTTPException(status_code=409, detail="Questo file è già stato importato: caricalo di nuovo per una nuova importazione")
        lock = await db.import_jobs.update_one({"id": jid, "status": "caricato"}, {"$set": {"status": "in_corso"}})
        if not lock.modified_count:
            raise HTTPException(status_code=409, detail="Importazione già in corso")
        try:
            res = await apply(user, j, body, await plan(user, j, body))
        except Exception:
            await db.import_jobs.update_one({"id": jid}, {"$set": {"status": "caricato"}})
            raise
        st = await module_state(user["org_id"])
        m = TARGETS[body.target]["module"]
        upd = {"status": "importato", "target": body.target, "mode": body.mode, "mapping": body.mapping, "options": body.options, "sheet": body.sheet,
               "config_name": (body.options or {}).get("config_name"), "result": {k: v for k, v in res.items() if k != "refs"}, "refs": res["refs"],
               "module_active": True if m is None else st[m], "ran_at": _now(), "ran_by": user.get("email"), "sheets": []}
        await db.import_jobs.update_one({"id": jid}, {"$set": upd})
        await record_audit(user, "import_run", org_id=user["org_id"], detail=f"{body.target}: {j['filename']}", meta={k: res[k] for k in ("creati", "aggiornati", "ignorati")})
        return {k: v for k, v in res.items() if k != "refs"}

    @r.get("/history")
    async def history(user: dict = Depends(admin)):
        rows = await db.import_jobs.find({"org_id": user["org_id"], "status": {"$in": ["importato", "annullato"]}}, {"_id": 0, "sheets": 0, "refs": 0, "mapping": 0}).sort("ran_at", -1).to_list(200)
        return [{**x, "label": TARGETS.get(x.get("target"), {}).get("label")} for x in rows]

    @r.get("/jobs/{jid}/errors.csv")
    async def errors_csv(jid: str, user: dict = Depends(admin)):
        j = await get_job(user, jid)
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(["Foglio", "Riga", "Stato", "Messaggio"])
        for e in (j.get("result") or {}).get("errori", []):
            w.writerow([e.get("foglio"), e.get("riga"), e.get("stato"), e.get("messaggio")])
        return StreamingResponse(io.BytesIO(("\ufeff" + buf.getvalue()).encode()), media_type="text/csv",
                                 headers={"Content-Disposition": f'attachment; filename="errori-importazione-{jid[:8]}.csv"'})

    @r.post("/jobs/{jid}/undo")
    async def undo(jid: str, user: dict = Depends(admin)):
        """Annullamento controllato: rimuove solo i record creati da questa importazione e non modificati dopo; gli aggiornamenti restano."""
        j = await get_job(user, jid)
        if j["status"] != "importato":
            raise HTTPException(status_code=409, detail="Importazione non annullabile")
        removed, kept = 0, 0
        org = user["org_id"]
        for coll in ("asd_quote", "asd_tesseramenti", "asd_soci", "staff", "teams", "deals", "lodgings", "meals", "pipeline_tasks", "pipeline_categories", "companies", "persons"):
            for rid in (j.get("refs") or {}).get(coll, []):
                doc = await db[coll].find_one({"org_id": org, "id": rid}, {"_id": 0, "updated_at": 1, "imported_at": 1})
                if not doc:
                    continue
                touched = (doc.get("updated_at") or "") > (doc.get("imported_at") or "")
                used = False
                if coll == "persons":
                    used = any([await db.staff.find_one({"org_id": org, "persona_id": rid}, {"_id": 1}), await db.asd_soci.find_one({"org_id": org, "persona_id": rid}, {"_id": 1}),
                                await db.deals.find_one({"org_id": org, "referente_id": rid}, {"_id": 1}), await db.lodgings.find_one({"org_id": org, "persona_id": rid}, {"_id": 1})])
                elif coll == "pipeline_categories":
                    used = bool(await db.pipeline_tasks.find_one({"org_id": org, "categoria_id": rid}, {"_id": 1}))
                elif coll == "companies":
                    used = bool(await db.deals.find_one({"org_id": org, "azienda_id": rid}, {"_id": 1}))
                elif coll == "asd_soci":
                    used = bool(await db.asd_tesseramenti.find_one({"org_id": org, "socio_id": rid}, {"_id": 1}) or await db.asd_quote.find_one({"org_id": org, "socio_id": rid}, {"_id": 1}))
                if touched or used:
                    kept += 1
                    continue
                await db[coll].delete_one({"org_id": org, "id": rid})
                removed += 1
        await db.import_jobs.update_one({"id": jid}, {"$set": {"status": "annullato", "undone_at": _now(), "undone_by": user.get("email"), "undo": {"rimossi": removed, "mantenuti": kept}}})
        await record_audit(user, "import_undo", org_id=org, detail=jid, meta={"rimossi": removed, "mantenuti": kept})
        return {"rimossi": removed, "mantenuti": kept}

    @r.get("/templates/{target}")
    async def template(target: str, user: dict = Depends(admin)):
        await allowed(user, target)
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = TARGETS[target]["label"][:30].replace("/", "-").replace("·", "-")
        ws.append([f["label"] for f in TARGETS[target]["fields"]])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 headers={"Content-Disposition": f'attachment; filename="modello-importazione-{target}.xlsx"'})

    # ---------- configurazioni salvate ----------
    @r.get("/configs")
    async def list_configs(target: Optional[str] = None, user: dict = Depends(admin)):
        q = {"$or": [{"org_id": user["org_id"]}, {"org_id": None}]}
        if target:
            q["target"] = target
        return await db.import_configs.find(q, {"_id": 0}).sort("name", 1).to_list(500)

    def clean_cfg(b: ConfigIn, user: dict) -> dict:
        if not b.name.strip() or b.target not in TARGETS:
            raise HTTPException(status_code=400, detail="Nome e modulo della configurazione sono obbligatori")
        if b.globale and not is_super(user):
            raise HTTPException(status_code=403, detail="Solo il Super Admin crea configurazioni condivise")
        opts = {k: v for k, v in (b.options or {}).items() if k in ("layout", "header_row", "mode", "fasi")}
        return {"name": b.name.strip()[:120], "target": b.target, "mapping": b.mapping, "options": opts, "org_id": None if b.globale else user["org_id"]}

    @r.post("/configs")
    async def add_config(body: ConfigIn, user: dict = Depends(admin)):
        doc = {**clean_cfg(body, user), "id": uuid.uuid4().hex, "created_at": _now(), "created_by": user.get("email")}
        await db.import_configs.insert_one(dict(doc))
        return doc

    async def own_cfg(user: dict, cid: str) -> dict:
        c = await db.import_configs.find_one({"id": cid, "$or": [{"org_id": user["org_id"]}, {"org_id": None}]}, {"_id": 0})
        if not c:
            raise HTTPException(status_code=404, detail="Configurazione non trovata")
        if c["org_id"] is None and not is_super(user):
            raise HTTPException(status_code=403, detail="Configurazione condivisa: modificabile solo dal Super Admin")
        return c

    @r.put("/configs/{cid}")
    async def edit_config(cid: str, body: ConfigIn, user: dict = Depends(admin)):
        await own_cfg(user, cid)
        d = clean_cfg(body, user)
        await db.import_configs.update_one({"id": cid}, {"$set": {**d, "updated_at": _now()}})
        return {"ok": True}

    @r.delete("/configs/{cid}")
    async def del_config(cid: str, user: dict = Depends(admin)):
        await own_cfg(user, cid)
        await db.import_configs.delete_one({"id": cid})
        return {"ok": True}

    async def ensure_indexes():
        await db.import_jobs.create_index([("org_id", 1), ("ran_at", -1)])
        await db.import_configs.create_index([("org_id", 1), ("target", 1)])
        await db.pipeline_tasks.create_index([("org_id", 1), ("event_id", 1), ("import_ref", 1)])

    return {"router": r, "ensure_indexes": ensure_indexes}
