"""SOLA LETTURA: verifica registrazioni del modulo pubblico Disponibilità (nessuna scrittura).
Uso sul server Aruba:  python3 aruba_check_registrations.py "<MONGO_URL>" "<DB_NAME>" [YYYY-MM-DD]
La data facoltativa limita ai record creati o aggiornati da quel giorno (es. data dell'ultimo aggiornamento)."""
import sys
from pymongo import MongoClient

url, dbn = sys.argv[1], sys.argv[2]
since = sys.argv[3] if len(sys.argv) > 3 else ""
db = MongoClient(url, readPreference="secondaryPreferred")[dbn]

orgs = {o["id"]: o.get("nome") or o.get("name") or "?" for o in db.organizations.find({}, {"_id": 0, "id": 1, "nome": 1, "name": 1})}
evs = {e["id"]: (e.get("nome") or "?", e.get("org_id")) for e in db.events.find({}, {"_id": 0, "id": 1, "nome": 1, "org_id": 1})}
q = {"$or": [{"created_at": {"$gte": since}}, {"updated_at": {"$gte": since}}]} if since else {}
rows, problems = [], 0
for a in db.availabilities.find(q, {"_id": 0}).sort("updated_at", -1):
    org, eid, pid = a.get("org_id"), a.get("evento_id"), a.get("persona_id")
    reasons = []
    if not org or org not in orgs:
        reasons.append("organizzazione mancante")
    ev = evs.get(eid)
    if not ev:
        reasons.append("evento mancante")
    elif ev[1] != org:
        reasons.append("evento di altra organizzazione")
    if not pid or not db.persons.find_one({"org_id": org, "id": pid}, {"_id": 1}):
        reasons.append("anagrafica mancante")
    link = db.staff.find_one({"org_id": org, "persona_id": pid, "evento_id": eid}, {"_id": 0, "categoria": 1}) if pid else None
    if not link:
        reasons.append("non collegata all'elenco Staff/Volontari")
    days = a.get("days") or []
    if not days:
        reasons.append("nessun giorno salvato")
    fmt = "fasce" if any(d.get("fasce") for d in days) else ("orario libero" if days else "-")
    problems += bool(reasons)
    rows.append((a.get("created_at", "")[:16], a.get("updated_at", "")[:16], a.get("id", "")[:8], (ev or ("?",))[0][:28], orgs.get(org, "?")[:22],
                 (link or {}).get("categoria", "-"), len(days), fmt, "; ".join(reasons) or "OK"))

print(f"{'Creato':16} | {'Aggiornato':16} | {'ID':8} | {'Evento':28} | {'Organizzazione':22} | {'Elenco':15} | Gg | Formato       | Esito")
for r in rows:
    print(f"{r[0]:16} | {r[1]:16} | {r[2]:8} | {r[3]:28} | {r[4]:22} | {r[5]:15} | {r[6]:2} | {r[7]:13} | {r[8]}")
print(f"\nDisponibilità analizzate: {len(rows)} - con anomalie: {problems}")

# Anagrafiche create dal link pubblico ma senza alcuna disponibilità (registrazioni parziali)
pq = {"provenienza.tipo": "link_disponibilita"}
if since:
    pq["provenienza.at"] = {"$gte": since}
part = [p for p in db.persons.find(pq, {"_id": 0, "id": 1, "org_id": 1, "provenienza": 1})
        if not db.availabilities.find_one({"org_id": p.get("org_id"), "persona_id": p["id"]}, {"_id": 1})]
print(f"Anagrafiche dal link pubblico senza disponibilità (parziali): {len(part)}")
for p in part:
    print(f"  {str((p.get('provenienza') or {}).get('at', ''))[:16]} | persona {p['id'][:8]} | {orgs.get(p.get('org_id'), '?')} | evento {evs.get((p.get('provenienza') or {}).get('evento_id'), ('?',))[0]}")

# Collegamenti all'elenco per categoria (dove cercare le persone nell'interfaccia)
agg = db.staff.aggregate([{"$match": {"origine": "link_disponibilita"}}, {"$group": {"_id": "$categoria", "n": {"$sum": 1}}}])
print("Persone arrivate dal link per linguetta:", {x["_id"]: x["n"] for x in agg})
