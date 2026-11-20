#!/usr/bin/env python3
"""CRMEvent - diagnostica SOLA LETTURA isolamento organizzazioni (server Aruba). Nessuna scrittura."""
import argparse
import hashlib
import os
import re
import socket
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

try:
    from pymongo import MongoClient
except ImportError:
    sys.exit("ERRORE: pymongo non disponibile. Attiva il virtualenv del backend (source .venv/bin/activate).")

REF_HASHES = {
    "ed01c2a279ca71873decfbfb02a7e6dc68fc9b1831dea8fb3c35734a5e52cb49": "export Aruba del 04/10/2026 (export-aruba)",
    "073b16fc14746d9960be24448656c827e576e61eba017a1aa8530ba1a07cdb73": "Emergent sviluppo al 20/11/2026",
}
CODE_MARKERS = {
    "Org inesistente -> 404": r"Organizzazione non trovata",
    "Header X-Org-Id letto dal backend": r"X-Org-Id",
    "Filtro oq() per org_id": r"def oq\(",
    "persons-enriched filtra le assegnazioni visibili": r"_link_visible\(admin, x\)",
    "persons-enriched esclude archiviati": r'oq\(admin, archiviato=',
    "Contesto assistenza (support)": r'user\.get\("support"\)',
    "Importazione universale": r"import_batches|importer",
}
MAIN_COLLS = ["events", "staff", "persons", "teams", "shifts", "deals", "companies", "person_companies",
              "memberships", "availabilities", "lodgings", "meals", "invoices", "leads", "iscritti",
              "asd_soci", "contacts", "documents", "briefing_versions", "import_batches", "import_history"]
NOFILTER = {"memberships"}


class ReadOnlyDB:
    """Consente solo operazioni di lettura; qualsiasi scrittura solleva errore."""
    ALLOWED = {"find", "find_one", "count_documents", "distinct", "aggregate", "estimated_document_count"}

    def __init__(self, db):
        self._db = db

    def names(self):
        return self._db.list_collection_names()

    def __getitem__(self, name):
        return ReadOnlyColl(self._db[name])


class ReadOnlyColl:
    def __init__(self, coll):
        self._c = coll

    def __getattr__(self, name):
        if name not in ReadOnlyDB.ALLOWED:
            raise PermissionError(f"Operazione '{name}' vietata: script in sola lettura")
        fn = getattr(self._c, name)
        if name == "aggregate":
            def safe(pipeline, *a, **k):
                if any(("$out" in s or "$merge" in s) for s in pipeline):
                    raise PermissionError("$out/$merge vietati")
                return fn(pipeline, *a, **k)
            return safe
        return fn


def load_env(path):
    env = {}
    if os.path.isfile(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


class R:
    def __init__(self, full):
        self.lines, self.full = [], full

    def h(self, t):
        self.lines += ["", f"## {t}", ""]

    def p(self, t=""):
        self.lines.append(t)

    def table(self, head, rows):
        if not rows:
            self.p("_nessun record_")
            return
        self.p("| " + " | ".join(head) + " |")
        self.p("|" + "---|" * len(head))
        for r in rows:
            self.p("| " + " | ".join("" if c is None else str(c).replace("|", "/") for c in r) + " |")

    def i(self, v):
        if v is None or v == "":
            return "∅ (vuoto)"
        v = str(v)
        return v if self.full else v[:8]


def pseudo(*vals):
    s = "|".join(str(v or "").strip().lower() for v in vals)
    return hashlib.sha256(s.encode()).hexdigest()[:10] if s.strip("|") else None


def code_section(r, backend_dir):
    r.h("1. Versione del backend installata")
    sp = os.path.join(backend_dir, "server.py")
    if not os.path.isfile(sp):
        r.p(f"server.py non trovato in {backend_dir}")
        return
    data = open(sp, encoding="utf-8", errors="replace").read()
    sha = hashlib.sha256(data.encode("utf-8", errors="replace")).hexdigest()
    raw_sha = hashlib.sha256(open(sp, "rb").read()).hexdigest()
    mt = datetime.fromtimestamp(os.path.getmtime(sp), timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    r.p(f"- Cartella backend: `{backend_dir}`")
    r.p(f"- server.py: {data.count(chr(10))} righe, modificato {mt}")
    r.p(f"- SHA-256: `{raw_sha}`")
    r.p(f"- Corrisponde a: **{REF_HASHES.get(raw_sha) or REF_HASHES.get(sha) or 'nessuna versione di riferimento nota (codice diverso)'}**")
    mods = sorted(f for f in os.listdir(backend_dir) if f.endswith(".py"))
    r.p(f"- Moduli .py presenti: {len(mods)}")
    r.table(["Controllo nel codice", "Presente"], [[k, "sì" if re.search(v, data) else "NO"] for k, v in CODE_MARKERS.items()])
    m = re.search(r"async def _resolve_active_org\(.*?\n(?=\S)", data, re.S)
    if m:
        r.p("")
        r.p("Estratto `_resolve_active_org` (logica Org attiva lato server):")
        r.p("```python")
        r.lines += m.group(0).rstrip().splitlines()[:40]
        r.p("```")
    m = re.search(r'@api\.get\("/persons-enriched"\).*?\n(?=@api)', data, re.S)
    if m:
        r.p("Estratto `/persons-enriched` (pagina Staff / Volontari), prime 14 righe:")
        r.p("```python")
        r.lines += m.group(0).splitlines()[:14]
        r.p("```")


def frontend_section(r, fe_dir):
    r.h("2. Frontend installato (tendina gialla Org attiva)")
    if not fe_dir:
        r.p("Cartella frontend non indicata (opzione --frontend-dir). Controllo saltato.")
        return
    js = []
    for root, _, files in os.walk(fe_dir):
        js += [os.path.join(root, f) for f in files if f.endswith(".js") and "node_modules" not in root]
    blob = ""
    for f in js[:400]:
        try:
            blob += open(f, encoding="utf-8", errors="replace").read()
        except OSError:
            pass
    r.p(f"- File JS analizzati: {len(js)}")
    checks = {
        "Legge acting_org_id dal browser": r"acting_org_id",
        "Invia header X-Org-Id": r"X-Org-Id",
        "Tendina popolata da /platform/organizations": r"/platform/organizations",
        "Validazione org memorizzata contro la lista": r"last_org:",
        "Etichetta 'Org attiva'": r"Org attiva",
    }
    r.table(["Controllo nel frontend", "Presente"], [[k, "sì" if re.search(v, blob) else "NO"] for k, v in checks.items()])
    urls = sorted(set(re.findall(r"https?://[a-zA-Z0-9.\-]+(?:\.it|\.com|\.ai|\.app|\.net)(?=[/\"'])", blob)))
    api_like = [u for u in urls if any(x in u for x in ("crmevent", "emergent", "api."))]
    r.p(f"- Indirizzi backend/API trovati nel frontend: {', '.join(api_like) or 'nessuno'}")


def org_section(r, db, orgs):
    r.h("3. Organizzazioni")
    r.p(f"Totale organizzazioni: **{len(orgs)}**")
    r.table(["ID", "Nome", "Stato", "Tipo", "Creata"],
            [[r.i(o.get("id")), o.get("nome") or o.get("name"), o.get("status", "active"), o.get("type", ""), str(o.get("created_at", ""))[:10]]
             for o in sorted(orgs, key=lambda x: str(x.get("created_at", "")))])
    rx = re.compile(r"trento|citt", re.I)
    cands = [o for o in orgs if any(isinstance(v, str) and rx.search(v) for v in o.values())]
    r.p("")
    if cands:
        r.p("**Trento individuata:** " + "; ".join(f"`{o.get('id')}` = {o.get('nome')}" for o in cands) + " (ID completo, necessario per la correzione)")
    else:
        r.p("**Nessuna organizzazione con 'Trento' o 'Città' nel nome in questo database.**")
        for cn in ("users", "memberships", "audit_logs"):
            if cn in db.names():
                n = db[cn].count_documents({"$or": [{"org_name": rx}, {"nome": rx}, {"detail": rx}]})
                r.p(f"- Riferimenti testuali a Trento in `{cn}`: {n}")
    return cands


def trento_section(r, db, trento, orgs_by_id, events_all):
    tid = trento["id"]
    r.h(f"4. Analisi di {trento.get('nome')} (ID {r.i(tid)})")
    cnames = db.names()
    rows = []
    for cn in MAIN_COLLS:
        if cn in cnames and cn not in NOFILTER:
            rows.append([cn, db[cn].count_documents({"org_id": tid})])
    r.table(["Raccolta", "Record con org_id = org analizzata"], rows)

    ev_t = [e for e in events_all if e.get("org_id") == tid]
    r.p("")
    r.p("**Eventi dell'org analizzata:**")
    r.table(["ID evento", "Nome", "org_id", "Organizzatore", "Creato"],
            [[r.i(e["id"]), e.get("nome"), r.i(e.get("org_id")), e.get("organizzatore"), str(e.get("created_at", ""))[:10]] for e in ev_t])

    ev_by_id = {e["id"]: e for e in events_all}
    staff_t = list(db["staff"].find({"org_id": tid}, {"_id": 0}))
    pids = {s.get("persona_id") for s in staff_t}
    persons = {p["id"]: p for p in db["persons"].find({"id": {"$in": list(pids)}}, {"_id": 0, "id": 1, "org_id": 1})}
    anom = []
    for s in staff_t:
        ev = ev_by_id.get(s.get("evento_id"))
        per = persons.get(s.get("persona_id"))
        why = []
        if not ev:
            why.append("evento inesistente")
        elif ev.get("org_id") != tid:
            why.append(f"evento di altra org ({orgs_by_id.get(ev.get('org_id'), {}).get('nome') or 'org ' + r.i(ev.get('org_id'))})")
        if not per:
            why.append("persona inesistente")
        elif per.get("org_id") != tid:
            why.append("persona di altra org/senza org")
        if why:
            anom.append(["staff", r.i(s.get("id")), r.i(tid), r.i(ev.get("org_id") if ev else None),
                         f"{(ev or {}).get('nome', '?')} [{r.i(s.get('evento_id'))}]", "; ".join(why), str(s.get("created_at", ""))[:10]])
    r.p("")
    r.p(f"**Assegnazioni Staff / Volontari dell'org analizzata:** {len(staff_t)} totali, {len(anom)} anomale")
    r.table(["Tipo", "ID record", "Org attuale", "Org dell'evento", "Evento [ID]", "Motivo", "Creato"], anom)

    r.p("")
    r.p("**Simulazione pagina Staff / Volontari dell'org analizzata (stessa logica del backend):**")
    ev_names_t = {e["id"]: e.get("nome") for e in ev_t}
    shown = Counter()
    for s in staff_t:
        n = ev_names_t.get(s.get("evento_id"))
        if n:
            shown[n] += 1
    persons_t = db["persons"].count_documents({"org_id": tid})
    r.p(f"- Persone in anagrafica dell'org analizzata: {persons_t}")
    r.table(["Evento mostrato nella colonna Eventi", "Assegnazioni"], [[k, v] for k, v in shown.most_common()])
    return staff_t


def pisa_section(r, db, events_all, orgs_by_id, tid):
    r.h("5. Eventi 'Maratona di Pisa' / 'Pisa' in tutto il database")
    pisa = [e for e in events_all if re.search(r"pisa", str(e.get("nome", "")), re.I)]
    rows = []
    for e in pisa:
        org = orgs_by_id.get(e.get("org_id"))
        st = list(db["staff"].find({"evento_id": e["id"]}, {"_id": 0, "org_id": 1}))
        by_org = Counter(r.i(s.get("org_id")) for s in st)
        src = ", ".join(f"{k}={r.i(e.get(k))}" for k in ("duplicated_from", "source_event_id", "import_batch_id", "created_by") if e.get(k))
        rows.append([r.i(e["id"]), e.get("nome"), r.i(e.get("org_id")),
                     (org or {}).get("nome") or ("ORG INESISTENTE" if e.get("org_id") else "senza org"),
                     e.get("organizzatore"), str(e.get("created_at", ""))[:10], len(st),
                     ", ".join(f"{k}:{v}" for k, v in by_org.items()), src])
    r.table(["ID evento", "Nome", "org_id", "Org", "Organizzatore", "Creato", "Assegnazioni", "Assegnazioni per org", "Origine"], rows)

    if not tid:
        return
    r.p("")
    r.p("**Persone dell'org analizzata collegate a eventi Pisa (anche di altre org):**")
    pisa_ids = [e["id"] for e in pisa]
    st = list(db["staff"].find({"evento_id": {"$in": pisa_ids}}, {"_id": 0}))
    pid_list = list({s.get("persona_id") for s in st})
    pers = {p["id"]: p for p in db["persons"].find({"id": {"$in": pid_list}}, {"_id": 0, "id": 1, "org_id": 1, "email": 1, "telefono": 1, "nome": 1, "cognome": 1, "created_at": 1, "provenienza": 1})}
    t_pers = list(db["persons"].find({"org_id": tid}, {"_id": 0, "id": 1, "email": 1, "telefono": 1, "nome": 1, "cognome": 1}))
    t_keys = {pseudo(p.get("email")) for p in t_pers if p.get("email")} | {pseudo(p.get("nome"), p.get("cognome")) for p in t_pers}
    rows = []
    for s in st:
        p = pers.get(s.get("persona_id"), {})
        dup = pseudo(p.get("email")) in t_keys or pseudo(p.get("nome"), p.get("cognome")) in t_keys
        if s.get("org_id") == tid or p.get("org_id") == tid or dup:
            rows.append([r.i(s.get("id")), r.i(s.get("org_id")), "P-" + (pseudo(p.get("id")) or "?"), r.i(p.get("org_id")),
                         "sì" if dup and p.get("org_id") != tid else "no", p.get("provenienza") or "", str(p.get("created_at", ""))[:10]])
    r.table(["ID assegnazione", "Org assegnazione", "Persona (pseudonimo)", "Org persona", "Stessa persona già nell'org analizzata", "Provenienza", "Persona creata"], rows)


def hygiene_section(r, db, org_ids):
    r.h("6. Record senza organizzazione o con organizzazione inesistente")
    cnames = db.names()
    rows = []
    for cn in [x for x in MAIN_COLLS + ["users"] if x in cnames]:
        c = db[cn]
        if not c.find_one({"org_id": {"$exists": True}}, {"_id": 1}):
            continue
        total = c.estimated_document_count()
        null = c.count_documents({"$or": [{"org_id": {"$exists": False}}, {"org_id": None}, {"org_id": ""}]})
        bad = c.count_documents({"$and": [{"org_id": {"$exists": True}}, {"org_id": {"$nin": list(org_ids) + [None, "", "__platform__"]}}]})
        if null or bad:
            rows.append([cn, total, null, bad])
    r.table(["Raccolta", "Totale", "Senza org", "Org inesistente"], rows)

    r.p("")
    r.p("**Org inesistenti referenziate (ID e conteggio):**")
    ghost = Counter()
    for cn in ("events", "staff", "persons", "teams", "shifts", "deals", "companies", "memberships"):
        if cn in cnames:
            for d in db[cn].find({"org_id": {"$nin": list(org_ids) + [None, "", "__platform__"]}}, {"_id": 0, "org_id": 1}):
                if d.get("org_id"):
                    ghost[(cn, d["org_id"])] += 1
    r.table(["Raccolta", "org_id inesistente", "Record"], [[c, r.i(o), n] for (c, o), n in ghost.most_common(50)])

    r.p("")
    r.p("**Assegnazioni Staff incoerenti (org assegnazione diversa da org evento o persona):**")
    ev_org = {e["id"]: e.get("org_id") for e in db["events"].find({}, {"_id": 0, "id": 1, "org_id": 1})}
    p_org = {p["id"]: p.get("org_id") for p in db["persons"].find({}, {"_id": 0, "id": 1, "org_id": 1})}
    mism = Counter()
    for s in db["staff"].find({}, {"_id": 0, "org_id": 1, "evento_id": 1, "persona_id": 1}):
        so, eo, po = s.get("org_id"), ev_org.get(s.get("evento_id"), "MANCANTE"), p_org.get(s.get("persona_id"), "MANCANTE")
        if so != eo or so != po:
            mism[(r.i(so), r.i(eo) if eo != "MANCANTE" else eo, r.i(po) if po != "MANCANTE" else po)] += 1
    r.table(["Org assegnazione", "Org evento", "Org persona", "Numero"], [[*k, n] for k, n in mism.most_common(50)])


def audit_section(r, db, tid, pisa_ids):
    r.h("7. Storico: registro attività e importazioni")
    cnames = db.names()
    if "audit_logs" in cnames and tid:
        rows = Counter()
        for a in db["audit_logs"].find({"$or": [{"org_id": tid}, {"detail": {"$regex": "|".join(map(re.escape, pisa_ids or ["@@"]))}}]},
                                      {"_id": 0, "action": 1, "created_at": 1, "at": 1}):
            rows[(a.get("action"), str(a.get("created_at") or a.get("at") or "")[:10])] += 1
        r.table(["Azione", "Data", "Volte"], [[a, d, n] for (a, d), n in sorted(rows.items(), key=lambda x: x[0][1])])
    for cn in [c for c in cnames if "import" in c.lower()]:
        q = {"org_id": tid} if tid else {}
        docs = list(db[cn].find(q, {"_id": 0, "id": 1, "module": 1, "modulo": 1, "created_at": 1, "status": 1, "stats": 1, "evento_id": 1}).limit(50))
        r.p(f"**{cn}** (org analizzata): {len(docs)}")
        r.table(["ID", "Modulo", "Evento", "Stato", "Data"],
                [[r.i(d.get("id")), d.get("module") or d.get("modulo"), r.i(d.get("evento_id")), d.get("status"), str(d.get("created_at", ""))[:16]] for d in docs])
    if "users" in cnames and tid:
        n = db["users"].count_documents({"$or": [{"org_id": tid}, {"active_org_id": tid}]})
        sa = db["users"].count_documents({"role": "superadmin"})
        r.p(f"- Utenti con org principale/attiva = Trento: {n} · Super Admin totali: {sa}")


def main():
    ap = argparse.ArgumentParser(description="Diagnostica CRMEvent in sola lettura")
    ap.add_argument("--backend-dir", required=True, help="cartella del backend installato (contiene server.py e .env)")
    ap.add_argument("--frontend-dir", default="", help="cartella del frontend compilato (build), facoltativa")
    ap.add_argument("--org", default="", help="ID completo di Trento se il nome non viene trovato")
    ap.add_argument("--full-ids", action="store_true", help="mostra gli ID completi (default: primi 8 caratteri)")
    ap.add_argument("--out", default="", help="file report (default /tmp/crmevent_diagnostica_<data>.md)")
    a = ap.parse_args()

    r = R(a.full_ids)
    now = datetime.now(timezone.utc)
    r.p("# CRMEvent - Report diagnostico (sola lettura)")
    r.p(f"Generato: {now.strftime('%Y-%m-%d %H:%M UTC')} · Server: {socket.gethostname()}")
    r.p("Nessun dato personale (nomi, email, telefoni) incluso. Persone indicate con pseudonimo.")
    code_section(r, a.backend_dir)
    frontend_section(r, a.frontend_dir)

    env = {**load_env(os.path.join(a.backend_dir, ".env")), **{k: v for k, v in os.environ.items() if k in ("MONGO_URL", "DB_NAME")}}
    if not env.get("MONGO_URL") or not env.get("DB_NAME"):
        sys.exit("ERRORE: MONGO_URL o DB_NAME non trovati nel .env del backend.")
    host = re.sub(r"^mongodb(\+srv)?://([^@]*@)?", "", env["MONGO_URL"]).split("/")[0].split("?")[0]
    kind = "locale (stesso server)" if re.match(r"^(localhost|127\.0\.0\.1|\[::1\])", host) else "remoto"
    r.h("0. Database utilizzato dal backend")
    r.p(f"- Nome database (DB_NAME): `{env['DB_NAME']}`")
    r.p(f"- Host MongoDB: {kind} (credenziali e indirizzo non mostrati)")

    client = MongoClient(env["MONGO_URL"], serverSelectionTimeoutMS=8000)
    db = ReadOnlyDB(client[env["DB_NAME"]])
    r.p(f"- Raccolte presenti: {len(db.names())}")

    orgs = list(db["organizations"].find({}, {"_id": 0}))
    orgs_by_id = {o["id"]: o for o in orgs if o.get("id")}
    cands = org_section(r, db, orgs)
    trento = orgs_by_id.get(a.org) if a.org else (cands[0] if cands else None)
    events_all = list(db["events"].find({}, {"_id": 0, "id": 1, "nome": 1, "org_id": 1, "organizzatore": 1, "created_at": 1,
                                             "created_by": 1, "duplicated_from": 1, "source_event_id": 1, "import_batch_id": 1}))
    tid = trento["id"] if trento else None
    if trento:
        trento_section(r, db, trento, orgs_by_id, events_all)
    pisa_section(r, db, events_all, orgs_by_id, tid)
    hygiene_section(r, db, set(orgs_by_id))
    audit_section(r, db, tid, [e["id"] for e in events_all if re.search(r"pisa", str(e.get("nome", "")), re.I)])
    client.close()

    out = a.out or f"/tmp/crmevent_diagnostica_{now.strftime('%Y%m%d_%H%M')}.md"
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(r.lines) + "\n")
    print("\n".join(r.lines))
    print(f"\n>>> Report salvato in: {out}")


if __name__ == "__main__":
    main()
