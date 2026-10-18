"""Popolamento DEMO di Elenco Iscritti per l'organizzazione "Demo": dati fittizi deterministici (seed fisso), idempotente, mai sincronizzati con Brevo."""
import random
import secrets
import unicodedata
import uuid
from datetime import date, datetime, timedelta, timezone

from pymongo import UpdateOne

SERVICE_KEY = "archivio-iscritti"
EVENT_NAME = "Maratona Demo"
EDITIONS = [(2024, "1ª edizione", 1850, "2024-10-13"), (2025, "2ª edizione", 2640, "2025-10-12"), (2026, "3ª edizione", 3420, "2026-10-11")]
GARE = ["Maratona 42K", "Mezza Maratona 21K", "10K"]
GARE_W = {2024: [30, 46, 24], 2025: [28, 45, 27], 2026: [26, 44, 30]}
FEMALE_P = {2024: 0.33, 2025: 0.36, 2026: 0.39}
RETURN_N = {2025: 610, 2026: 1080}
AGE_BANDS = [((18, 24), 8), ((25, 34), 21), ((35, 44), 27), ((45, 54), 26), ((55, 64), 13), ((65, 78), 5)]
NAZ = [("Italia", 80), ("Germania", 3.5), ("Francia", 3), ("Svizzera", 2.5), ("Regno Unito", 2), ("Spagna", 1.8), ("Austria", 1.4),
       ("Paesi Bassi", 1.2), ("Stati Uniti", 1.1), ("Kenya", 0.9), ("Belgio", 0.9), ("Polonia", 0.8), ("Etiopia", 0.4), ("Brasile", 0.5)]
STATI_W = [("confermata", 93), ("annullata", 3), ("ritirato", 2), ("in_attesa", 2)]
IT_M = ["Marco", "Luca", "Andrea", "Matteo", "Giuseppe", "Francesco", "Alessandro", "Davide", "Simone", "Stefano", "Paolo", "Roberto", "Fabio",
        "Riccardo", "Giovanni", "Antonio", "Daniele", "Federico", "Lorenzo", "Nicola", "Michele", "Emanuele", "Claudio", "Massimo", "Filippo", "Gabriele"]
IT_F = ["Giulia", "Francesca", "Chiara", "Sara", "Valentina", "Laura", "Elena", "Martina", "Alessia", "Silvia", "Federica", "Paola", "Anna",
        "Elisa", "Roberta", "Serena", "Ilaria", "Monica", "Cristina", "Beatrice", "Marta", "Veronica", "Simona", "Giorgia", "Alice", "Barbara"]
IT_S = ["Rossi", "Russo", "Ferrari", "Esposito", "Bianchi", "Romano", "Colombo", "Ricci", "Marino", "Greco", "Bruno", "Gallo", "Conti", "De Luca",
        "Mancini", "Costa", "Giordano", "Rizzo", "Lombardi", "Moretti", "Barbieri", "Fontana", "Santoro", "Mariani", "Rinaldi", "Caruso", "Ferrara",
        "Galli", "Martini", "Leone", "Longo", "Gentile", "Martinelli", "Vitale", "Lombardo", "Serra", "Coppola", "De Santis", "Marchetti", "Parisi"]
FOREIGN = {
    "Germania": (["Lukas", "Jonas", "Felix", "Max", "Tobias"], ["Anna", "Lena", "Laura", "Julia", "Lea"], ["Müller", "Schmidt", "Schneider", "Fischer", "Weber"]),
    "Francia": (["Pierre", "Louis", "Hugo", "Julien", "Nicolas"], ["Camille", "Chloé", "Manon", "Julie", "Léa"], ["Martin", "Bernard", "Dubois", "Moreau", "Laurent"]),
    "Svizzera": (["Luca", "Noah", "Jan", "Reto", "Urs"], ["Mia", "Nina", "Sara", "Laura", "Elena"], ["Meier", "Keller", "Huber", "Brunner", "Gerber"]),
    "Regno Unito": (["James", "Oliver", "Harry", "George", "Jack"], ["Emily", "Olivia", "Sophie", "Grace", "Amelia"], ["Smith", "Jones", "Taylor", "Brown", "Wilson"]),
    "Spagna": (["Javier", "Pablo", "Carlos", "Sergio", "Diego"], ["Lucía", "María", "Paula", "Carmen", "Elena"], ["García", "López", "Sánchez", "Pérez", "Gómez"]),
    "Austria": (["Florian", "Lukas", "David", "Stefan", "Paul"], ["Katharina", "Sophie", "Hannah", "Anna", "Lisa"], ["Gruber", "Huber", "Bauer", "Wagner", "Pichler"]),
    "Paesi Bassi": (["Daan", "Sem", "Lucas", "Bram", "Thijs"], ["Emma", "Julia", "Sanne", "Fleur", "Anouk"], ["de Jong", "Jansen", "de Vries", "Visser", "Bakker"]),
    "Stati Uniti": (["Michael", "John", "David", "Ryan", "Kevin"], ["Jessica", "Ashley", "Sarah", "Emily", "Megan"], ["Johnson", "Miller", "Davis", "Moore", "Clark"]),
    "Kenya": (["Kipchoge", "Daniel", "Wilson", "Geoffrey", "Joseph"], ["Faith", "Mary", "Ruth", "Grace", "Agnes"], ["Kiprop", "Cheruiyot", "Kibet", "Mutai", "Chebet"]),
    "Belgio": (["Thomas", "Arthur", "Lucas", "Wout", "Jens"], ["Marie", "Lotte", "Elise", "Ine", "Sofie"], ["Peeters", "Janssens", "Maes", "Jacobs", "Mertens"]),
    "Polonia": (["Piotr", "Jakub", "Kamil", "Tomasz", "Marcin"], ["Anna", "Katarzyna", "Magda", "Ewa", "Agnieszka"], ["Nowak", "Kowalski", "Wiśniewski", "Lewandowski", "Zieliński"]),
    "Etiopia": (["Kenenisa", "Tadesse", "Abebe", "Haile", "Yomif"], ["Tirunesh", "Almaz", "Meseret", "Genzebe", "Tigist"], ["Bekele", "Gebre", "Tola", "Desisa", "Ayana"]),
    "Brasile": (["João", "Pedro", "Lucas", "Rafael", "Bruno"], ["Ana", "Juliana", "Camila", "Fernanda", "Beatriz"], ["Silva", "Santos", "Oliveira", "Souza", "Lima"]),
}
CLUBS = ["ASD Runners Demo", "Atletica Città Demo", "Podisti del Lago", "G.S. Valle Verde", "Running Team Collina", "ASD Maratoneti Riuniti",
         "Atletica Fiume Azzurro", "Polisportiva Porta Nord", "Team Corsa Libera", "ASD Passo Lungo", "G.P. Torre Antica", "Amatori Atletica Centro",
         "Runners Parco Sud", "ASD Strada e Sentiero", "Atletica Borgo Vecchio", "Club Fondisti Demo", "Trail & Road ASD", "U.S. Ponte Alto"]


def _ascii(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower() if c.isalnum())


def _pick(rng, pairs):
    return rng.choices([p[0] for p in pairs], weights=[p[1] for p in pairs])[0]


def _person(rng, n: int, anno: int) -> dict:
    sesso = "F" if rng.random() < FEMALE_P[anno] else "M"
    naz = _pick(rng, NAZ)
    if naz == "Italia":
        nome, cognome = rng.choice(IT_F if sesso == "F" else IT_M), rng.choice(IT_S)
    else:
        m, f, s = FOREIGN[naz]
        nome, cognome = rng.choice(f if sesso == "F" else m), rng.choice(s)
    lo, hi = _pick(rng, AGE_BANDS)
    age = rng.randint(lo, hi)
    born = date(anno - age, 1, 1) + timedelta(days=rng.randint(0, 364))
    societa = rng.choice(CLUBS) if rng.random() < 0.72 else ""
    return {"nome": nome, "cognome": cognome, "sesso": sesso, "nazionalita": naz, "data_nascita": born.isoformat(),
            "societa": societa, "email": f"{_ascii(nome)}.{_ascii(cognome)}.{n:05d}@example.com",
            "consenso_marketing": rng.random() < 0.46}


def _reg_date(rng, event_day: date) -> str:
    days_before = max(1, int(240 * (rng.random() ** 1.7)))
    return (event_day - timedelta(days=days_before)).isoformat()


def generate():
    """Dataset deterministico: lista persone e partecipazioni (indice persona, anno, gara, stato, data)."""
    rng = random.Random(20240913)
    people, parts, pool = [], [], []
    last_gara = {}
    for anno, _, total, d in EDITIONS:
        day = date.fromisoformat(d)
        chosen = rng.sample(pool, min(RETURN_N.get(anno, 0), len(pool))) if pool else []
        new = [len(people) + i for i in range(total - len(chosen))]
        for i in new:
            people.append(_person(rng, i + 1, anno))
        for i in chosen + new:
            g = last_gara[i] if i in last_gara and rng.random() < 0.7 else rng.choices(GARE, weights=GARE_W[anno])[0]
            last_gara[i] = g
            parts.append((i, anno, g, _pick(rng, STATI_W), _reg_date(rng, day)))
        pool.extend(new)
    return people, parts


async def seed(db, dedup_key) -> dict:
    org = await db.organizations.find_one({"nome": "Demo", "type": "test"}, {"_id": 0, "id": 1, "nome": 1})
    if not org:
        raise ValueError("Organizzazione Demo non trovata")
    oid, now = org["id"], datetime.now(timezone.utc).isoformat()
    await db.org_services.update_one({"org_id": oid, "service": SERVICE_KEY}, {"$set": {"active": True, "updated_at": now, "billing": "attivazione_super_admin"},
                                                                               "$setOnInsert": {"activated_at": now, "activated_by": "demo_seed"}}, upsert=True)
    await db.iscritti_settings.update_one({"org_id": oid}, {"$set": {"demo": True}}, upsert=True)
    ev = await db.events.find_one({"org_id": oid, "nome": EVENT_NAME}, {"_id": 0, "id": 1})
    if not ev:
        ev = {"id": "demo_evt_maratona", "org_id": oid, "nome": EVENT_NAME, "demo": True, "tipologia": "Running", "stato": "attivo",
              "descrizione": "Evento dimostrativo con dati fittizi: maratona cittadina con percorsi 42K, 21K e 10K.",
              "citta": "Città Demo", "localita": "Città Demo", "nazione": "Italia", "edizione": "2026", "data_inizio": EDITIONS[-1][3],
              "data_fine": EDITIONS[-1][3], "ora_inizio": "08:30", "ora_fine": "15:00", "partecipanti_previsti": 3500, "organizzatore": "Demo",
              "entitlement": {"plan": "premium", "source": "demo", "year": EDITIONS[-1][0], "currency": "EUR"}, "created_at": now, "updated_at": now}
        await db.events.update_one({"id": ev["id"]}, {"$setOnInsert": ev}, upsert=True)
    eds = {}
    for anno, label, _, d in EDITIONS:
        await db.iscritti_edizioni.update_one({"org_id": oid, "event_id": ev["id"], "anno": anno, "edizione": label}, {
            "$set": {"gare": GARE, "data_evento": d, "demo": True},
            "$setOnInsert": {"id": uuid.uuid4().hex, "org_id": oid, "event_id": ev["id"], "event_nome": EVENT_NAME, "anno": anno,
                             "edizione": label, "created_at": now, "created_by": "demo_seed"}}, upsert=True)
        eds[anno] = await db.iscritti_edizioni.find_one({"org_id": oid, "event_id": ev["id"], "anno": anno, "edizione": label}, {"_id": 0})
    people, parts = generate()
    ops = []
    for p in people:
        key = dedup_key(p)
        ops.append(UpdateOne({"org_id": oid, "dedup_key": key}, {"$setOnInsert": {
            "id": uuid.uuid4().hex, "org_id": oid, "dedup_key": key, **p, "cellulare": "", "codice_fiscale": "", "numero_tessera": "", "federazione": "",
            "note": "DEMO – dati fittizi", "custom": {}, "demo": True, "consenso_fonte": "DEMO – dati fittizi" if p["consenso_marketing"] else "",
            "consenso_data": "2024-01-01" if p["consenso_marketing"] else "", "unsub_token": secrets.token_urlsafe(24), "consent_history": [],
            "brevo_status": "demo_escluso", "created_at": now, "updated_at": now}}, upsert=True))
    for i in range(0, len(ops), 1000):
        await db.iscritti.bulk_write(ops[i:i + 1000], ordered=False)
    ids = {x["dedup_key"]: x["id"] for x in await db.iscritti.find({"org_id": oid, "demo": True}, {"_id": 0, "id": 1, "dedup_key": 1}).to_list(50000)}
    pid_of = [ids[dedup_key(p)] for p in people]
    ops, last, first = [], {}, {}
    for i, anno, gara, stato, d in parts:
        ed, pid = eds[anno], pid_of[i]
        last[pid] = max(last.get(pid, 0), anno)
        first[pid] = min(first.get(pid, d), d)
        ops.append(UpdateOne({"org_id": oid, "iscritto_id": pid, "edizione_id": ed["id"], "gara": gara}, {"$setOnInsert": {
            "id": uuid.uuid4().hex, "org_id": oid, "iscritto_id": pid, "edizione_id": ed["id"], "event_id": ev["id"], "anno": anno,
            "edizione": ed["edizione"], "gara": gara, "tipologia": "Individuale", "stato": stato, "data_iscrizione": d, "demo": True, "created_at": now}}, upsert=True))
    for i in range(0, len(ops), 1000):
        await db.iscritti_partecipazioni.bulk_write(ops[i:i + 1000], ordered=False)
    lops = [UpdateOne({"id": pid, "$or": [{"last_year": {"$lt": y}}, {"last_year": None}]}, {"$set": {"last_year": y}}) for pid, y in last.items()]
    # data di creazione = prima iscrizione (realistica per i KPI "nuovi")
    lops += [UpdateOne({"id": pid, "demo": True}, {"$set": {"created_at": f"{d}T09:00:00+00:00", "updated_at": f"{d}T09:00:00+00:00"}}) for pid, d in first.items()]
    for i in range(0, len(lops), 1000):
        await db.iscritti.bulk_write(lops[i:i + 1000], ordered=False)
    counts = {str(a): await db.iscritti_partecipazioni.count_documents({"org_id": oid, "edizione_id": eds[a]["id"]}) for a, *_ in EDITIONS}
    return {"org_id": oid, "event_id": ev["id"], "iscritti": await db.iscritti.count_documents({"org_id": oid, "demo": True}),
            "partecipazioni": counts, "totale_partecipazioni": sum(counts.values())}
