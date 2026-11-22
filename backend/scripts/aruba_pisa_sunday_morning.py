"""Maratona di Pisa 2026 - aggiunge Domenica 20/12/2026 Mattina ad Addetti ristoro e Pacer.

1) ANTEPRIMA (nessuna scrittura):
   python3 aruba_pisa_sunday_morning.py "<MONGO_URL>" "<DB_NAME>" [--event-id ID]
2) APPLICAZIONE (solo dopo conferma, con il codice stampato dall'anteprima):
   python3 aruba_pisa_sunday_morning.py "<MONGO_URL>" "<DB_NAME>" --event-id ID --apply --token CODICE --actor tua@email
Prima di scrivere salva un backup JSON dei record modificati. Rieseguirlo non crea duplicati."""
import argparse, hashlib, json, re, sys, unicodedata, uuid
from datetime import datetime, timezone
from pymongo import MongoClient

DAY = "2026-12-20"
ap = argparse.ArgumentParser()
ap.add_argument("mongo_url"); ap.add_argument("db_name")
ap.add_argument("--event-id"); ap.add_argument("--apply", action="store_true"); ap.add_argument("--token"); ap.add_argument("--actor")
a = ap.parse_args()
db = MongoClient(a.mongo_url)[a.db_name]
now = lambda: datetime.now(timezone.utc).isoformat()


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z ]+", " ", s).split()


def kind(role):
    w = norm(role)
    j = " ".join(w)
    if any(x.startswith("ristor") for x in w):
        return "ristoro"
    if any(x.startswith("pacer") for x in w) or j in ("pace maker", "pacemaker", "pace makers", "pacemakers", "lepre", "lepri"):
        return "pacer"
    return None


def hm(t):
    try:
        h, m = str(t).split(":")[:2]
        return int(h) * 60 + int(m)
    except Exception:
        return None


def stop(msg):
    print(f"\nSTOP: {msg}\nNessuna modifica eseguita.")
    sys.exit(1)


# --- 1. Evento e organizzazione (per ID) ---
if a.event_id:
    ev = db.events.find_one({"id": a.event_id}, {"_id": 0})
    if not ev:
        stop("evento non trovato con questo ID")
else:
    cand = [e for e in db.events.find({"nome": {"$regex": "pisa", "$options": "i"}}, {"_id": 0})
            if (e.get("data_inizio") or "")[:10] <= DAY <= ((e.get("data_fine_disallestimento") or e.get("data_fine") or e.get("data_inizio") or "")[:10])]
    print("Eventi con 'Pisa' nel nome che comprendono il 20/12/2026:")
    for e in cand:
        o = db.organizations.find_one({"id": e.get("org_id")}, {"_id": 0, "nome": 1}) or {}
        print(f"  ID {e['id']} | {e.get('nome')} | {e.get('data_inizio')} -> {e.get('data_fine')} | org {o.get('nome')} ({e.get('org_id')})")
    if len(cand) != 1:
        stop("evento non identificato con certezza: rilancia con --event-id <ID>")
    ev = cand[0]
org_id = ev.get("org_id")
org = db.organizations.find_one({"id": org_id}, {"_id": 0, "nome": 1})
if not org:
    stop("organizzazione dell'evento non trovata")
if not ((ev.get("data_inizio_allestimento") or ev.get("data_inizio") or "")[:10] <= DAY <= (ev.get("data_fine_disallestimento") or ev.get("data_fine") or ev.get("data_inizio") or "")[:10]):
    stop("il 20/12/2026 non e' un giorno dell'evento")
cfg = ((ev.get("fasce_disponibilita") or {}).get(DAY) or {})
m = cfg.get("mattina") or {}
p = cfg.get("pomeriggio") or {}
if m.get("attiva") is False or not m.get("start") or not m.get("end"):
    stop("fascia Mattina del 20/12 non attiva o senza orari nella scheda evento: configurala prima")
MS, ME = m["start"], m["end"]
PS, PE = (p.get("start"), p.get("end")) if p.get("attiva", True) else (None, None)
print(f"\nEvento: {ev.get('nome')} (ID {ev['id']})\nOrganizzazione: {org.get('nome')} (ID {org_id})\nFascia: Domenica 20/12/2026 Mattina {MS}-{ME}")

# --- 2. Persone con mansione Addetto ristoro / Pacer ---
roles, people = {}, {}
for l in db.staff.find({"org_id": org_id, "evento_id": ev["id"]}, {"_id": 0, "persona_id": 1, "ruolo": 1}):
    r = (l.get("ruolo") or "").strip()
    if r:
        roles[r] = roles.get(r, 0) + 1
    k = kind(r)
    if k and l.get("persona_id"):
        people.setdefault(l["persona_id"], set()).add(k)
print("\nMansioni presenti nell'evento (= incluse):")
for r, n in sorted(roles.items(), key=lambda x: x[0].lower()):
    print(f"  {'[RISTORO]' if kind(r) == 'ristoro' else '[PACER]  ' if kind(r) == 'pacer' else '         '} {r}: {n}")

# --- 3. Analisi disponibilita' ---
plan, already, verify, multi = [], [], [], 0
for pid, kinds in people.items():
    per = db.persons.find_one({"org_id": org_id, "id": pid}, {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "email": 1, "cellulare": 1})
    if not per:
        verify.append((pid, kinds, "anagrafica non trovata")); continue
    label = f"{per.get('cognome') or ''} {(per.get('nome') or ' ')[0]}.".strip()
    avs = list(db.availabilities.find({"org_id": org_id, "evento_id": ev["id"], "persona_id": pid}, {"_id": 0}))
    multi += len(avs) > 1
    cur = max(avs, key=lambda x: str(x.get("updated_at") or x.get("created_at") or "")) if avs else None
    days = list((cur or {}).get("days") or [])
    d = next((x for x in days if x.get("date") == DAY), None)
    slot = {"id": "mattina", "start": MS, "end": ME}
    if not cur:
        plan.append((pid, label, kinds, "nuova disponibilita'", None, [{"date": DAY, "fase": "evento", "fasce": [slot], "dalle": MS, "alle": ME}], None)); continue
    if d is None:
        nd = days + [{"date": DAY, "fase": "evento", "fasce": [slot], "dalle": MS, "alle": ME}]
        plan.append((pid, label, kinds, "aggiunta domenica", cur, sorted(nd, key=lambda x: x.get("date") or ""), None)); continue
    if d.get("disponibile") is False:
        verify.append((pid, kinds, f"{label}: ha dichiarato NON disponibile domenica")); continue
    fs = d.get("fasce") or []
    if fs:
        if any(f.get("id") == "mattina" for f in fs):
            already.append((pid, label, kinds)); continue
        nf = [slot] + [f for f in fs if f.get("id") != "mattina"]
        st = [hm(f.get("start")) for f in nf]
        en = [hm(f.get("end")) for f in nf]
        nd = [{**x, "fasce": nf, "dalle": min(f["start"] for f in nf) if None not in st else None, "alle": max(f["end"] for f in nf) if None not in en else None} if x is d else x for x in days]
        plan.append((pid, label, kinds, "aggiunta Mattina", cur, nd, None)); continue
    x0, x1 = hm(d.get("dalle")), hm(d.get("alle"))
    if x0 is not None and x1 is not None and PS and PE and min(x1, hm(PE)) > max(x0, hm(PS)):
        verify.append((pid, kinds, f"{label}: vecchio orario {d.get('dalle')}-{d.get('alle')} copre anche il pomeriggio, da aggiornare a mano")); continue
    nd = [{"date": DAY, "fase": d.get("fase") or "evento", "fasce": [slot], "dalle": MS, "alle": ME} if x is d else x for x in days]
    plan.append((pid, label, kinds, f"vecchio formato {d.get('dalle') or '?'}-{d.get('alle') or '?'} -> Mattina", cur, nd, d))

cnt = lambda k: sum(k in v for v in people.values())
print(f"\nAddetti ristoro individuati: {cnt('ristoro')}\nPacer individuati: {cnt('pacer')}")
both = [pid for pid, v in people.items() if len(v) == 2]
print(f"In entrambe le categorie: {len(both)}")
print(f"Hanno gia' Domenica mattina: {len(already)}\nDa aggiornare: {len(plan)}\nDa verificare a mano (esclusi): {len(verify)}")
if multi:
    print(f"Persone con piu' registrazioni per l'evento: {multi} (si aggiorna solo la piu' recente, quella usata da CRMEvent)")
print("\nPersone da aggiornare:")
for pid, label, k, what, *_ in sorted(plan, key=lambda x: x[1].lower()):
    print(f"  {label:28} | {'+'.join(sorted(k)):15} | {what} | id {pid[:8]}")
if already:
    print("Gia' con Domenica mattina: " + ", ".join(sorted(x[1] for x in already)))
for _, _, msg in verify:
    print(f"  DA VERIFICARE: {msg}")

token = hashlib.sha1(json.dumps([[x[0], x[3], (x[4] or {}).get("id"), (x[4] or {}).get("updated_at")] for x in sorted(plan, key=lambda x: x[0])] + [ev["id"], MS, ME]).encode()).hexdigest()[:10]
if not a.apply:
    print(f"\nANTEPRIMA: nessuna modifica eseguita. Codice di conferma: {token}")
    sys.exit(0)

# --- 4. Applicazione ---
if a.token != token:
    stop("codice di conferma diverso: i dati sono cambiati dopo l'anteprima, rilancia l'anteprima")
if not a.actor:
    stop("indica --actor <tua email> per l'Audit Log")
bk = f"backup_pisa_domenica_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
json.dump([x[4] for x in plan if x[4]], open(bk, "w"), ensure_ascii=False, indent=1, default=str)
print(f"\nBackup record originali: {bk}")
done = 0
for pid, label, k, what, cur, nd, old in plan:
    t = now()
    if cur:
        upd = {"$set": {"days": nd, "updated_at": t, "days_edited_by": a.actor, "days_edited_at": t}}
        if old:
            upd["$push"] = {"days_history": {**old, "sostituito_il": t, "sostituito_da": a.actor}}
        r = db.availabilities.update_one({"org_id": org_id, "id": cur["id"], "updated_at": cur.get("updated_at")}, upd)
        if not r.modified_count:
            print(f"  SALTATO (record cambiato nel frattempo): {label}"); continue
    else:
        per = db.persons.find_one({"org_id": org_id, "id": pid}, {"_id": 0})
        if db.availabilities.find_one({"org_id": org_id, "evento_id": ev["id"], "persona_id": pid}, {"_id": 1}):
            print(f"  SALTATO (registrazione creata nel frattempo): {label}"); continue
        db.availabilities.insert_one({"id": uuid.uuid4().hex, "org_id": org_id, "evento_id": ev["id"], "persona_id": pid,
                                      "nome": per.get("nome"), "cognome": per.get("cognome"), "email": per.get("email"), "cellulare": per.get("cellulare"),
                                      "ruolo_evento": "staff", "stato": "confermata", "origine": "aggiornamento_massivo", "days": nd, "brevo_status": "skipped",
                                      "days_edited_by": a.actor, "days_edited_at": t, "created_at": t, "updated_at": t})
    db.audit_logs.insert_one({"id": uuid.uuid4().hex, "created_at": t, "actor_email": a.actor, "actor_name": "Script aggiornamento disponibilita'", "actor_role": "script",
                              "scope": "org", "action": "person_availability_edited", "action_label": "Disponibilita' modificata", "org_id": org_id, "org_name": org.get("nome"),
                              "target_name": label, "detail": f"{ev.get('nome')}: Domenica 20/12 Mattina {MS}-{ME} ({what})", "meta": {"persona_id": pid, "evento_id": ev["id"], "bulk": "pisa_domenica_mattina"}})
    done += 1
db.audit_logs.insert_one({"id": uuid.uuid4().hex, "created_at": now(), "actor_email": a.actor, "actor_name": "Script aggiornamento disponibilita'", "actor_role": "script",
                          "scope": "org", "action": "availability_bulk_update", "action_label": "Aggiornamento massivo disponibilita'", "org_id": org_id, "org_name": org.get("nome"),
                          "detail": f"{ev.get('nome')}: Domenica 20/12 Mattina a {done} persone (Addetti ristoro e Pacer)", "meta": {"evento_id": ev["id"], "backup": bk}})
print(f"Aggiornate: {done}")

# --- 5. Controllo finale ---
ok, bad = 0, []
for pid in people:
    avs = list(db.availabilities.find({"org_id": org_id, "evento_id": ev["id"], "persona_id": pid}, {"_id": 0}))
    cur = max(avs, key=lambda x: str(x.get("updated_at") or x.get("created_at") or "")) if avs else None
    ds = [x for x in (cur or {}).get("days") or [] if x.get("date") == DAY]
    if len(ds) == 1 and sum(f.get("id") == "mattina" for f in ds[0].get("fasce") or []) == 1:
        ok += 1
    else:
        bad.append(pid[:8])
print(f"Controllo: {ok}/{len(people)} con Domenica mattina, senza giorni duplicati." + (f" Da controllare: {bad} (inclusi quelli 'da verificare')" if bad else ""))
