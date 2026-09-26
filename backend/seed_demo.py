"""Idempotent demo dataset seeder for the CRMEvent "Demo" (type=test) organization.

Safe to run multiple times: every record uses a deterministic id (prefix `demo_`) and is
UPSERTED, so re-runs never create duplicates. Only the Demo org is touched — never any
other organization. When run in production it FINDS the existing Demo org (by name+type)
instead of creating a second one.

Run:  python seed_demo.py           (seed / re-seed)
      python seed_demo.py --wipe    (remove all demo_* records first, then seed)
"""
import asyncio
import os
import sys
import uuid
from datetime import date, datetime, timezone, timedelta

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()
client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]

TODAY = date.today()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def rel(days):
    return (TODAY + timedelta(days=days)).isoformat()


# Fixed event dates (as per requirements)
BCR_D1 = "2026-10-17"   # day before
BCR_D2 = "2026-10-18"   # race day
TRI_DATE = "2027-05-16"
TRAIL_DATE = "2026-04-12"


async def get_or_create_demo_org():
    org = await db.organizations.find_one({"nome": "Demo", "type": "test"}, {"_id": 0})
    if not org:
        org = await db.organizations.find_one({"nome": "Demo"}, {"_id": 0})
    if org:
        if org.get("type") != "test":
            print(f"[!] Org 'Demo' esiste ma type={org.get('type')} (atteso 'test'). Non la modifico.")
        print(f"[=] Uso org Demo esistente: id={org['id']}")
        return org
    now = datetime.now(timezone.utc)
    org = {
        "id": uuid.uuid4().hex, "nome": "Demo", "type": "test", "status": "active",
        "owner_user_id": None,
        "subscription": {"status": "test", "plan": "crmevent", "billing_cycle": None,
                         "trial_start": None, "trial_end": None, "current_period_end": None,
                         "stripe_customer_id": None, "stripe_subscription_id": None},
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    await db.organizations.insert_one(dict(org))
    print(f"[+] Creata org Demo (type=test): id={org['id']}")
    return org


async def upsert(coll, doc, org_id):
    """Upsert by deterministic id, always pinned to the Demo org_id."""
    d = {**doc, "org_id": org_id, "updated_at": now_iso()}
    existing = await db[coll].find_one({"id": d["id"]}, {"_id": 0, "created_at": 1})
    d["created_at"] = (existing or {}).get("created_at") or now_iso()
    await db[coll].update_one({"id": d["id"]}, {"$set": d}, upsert=True)


# ------------------------------------------------------------------ PERSONS
# (idx, nome, cognome, qualifica)
PERSONS = [
    (1, "Luca", "Bianchi", "Coordinatore Generale"),
    (2, "Giulia", "Ferrari", "Responsabile Arrivo"),
    (3, "Marco", "Colombo", "Responsabile Percorso"),
    (4, "Sara", "Ricci", "Responsabile Ristori"),
    (5, "Andrea", "Marino", "Responsabile Expo"),
    (6, "Chiara", "Greco", "Responsabile Segreteria"),
    (7, "Matteo", "Bruno", "Responsabile Logistica"),
    (8, "Francesca", "Gallo", "Speaker"),
    (9, "Davide", "Conti", "Deejay"),
    (10, "Elena", "De Luca", "Fotografo"),
    (11, "Simone", "Mancini", "Fotografo"),
    (12, "Alessia", "Costa", "Addetto percorso"),
    (13, "Federico", "Giordano", "Addetto percorso"),
    (14, "Martina", "Rizzo", "Addetto percorso"),
    (15, "Stefano", "Lombardi", "Addetto ristoro"),
    (16, "Valentina", "Moretti", "Addetto ristoro"),
    (17, "Alberto", "Barbieri", "Addetto ristoro"),
    (18, "Silvia", "Fontana", "Addetto ristoro"),
    (19, "Paolo", "Santoro", "Segreteria"),
    (20, "Ilaria", "Mariani", "Segreteria"),
    (21, "Giorgio", "Rinaldi", "Logistica"),
    (22, "Beatrice", "Caruso", "Logistica"),
    (23, "Nicola", "Ferrara", "Addetto Expo"),
    (24, "Roberta", "Galli", "Addetto Expo"),
    (25, "Antonio", "Martini", "Hostess accoglienza"),
    (26, "Laura", "Leone", "Hostess accoglienza"),
    (27, "Riccardo", "Longo", "Addetto partenza"),
    (28, "Cristina", "Gentile", "Sicurezza"),
    (29, "Fabio", "Martinelli", "Sicurezza"),
    (30, "Serena", "Vitale", "Addetto pacchi gara"),
    (31, "Emanuele", "Serra", "Addetto ristoro"),
    (32, "Monica", "Coppola", "Medico / Assistenza"),
    (33, "Gabriele", "Palumbo", "Volontario jolly"),
    (34, "Debora", "Farina", "Volontario jolly"),
]

# team_slug -> (nome, area, leader_idx, punto_ritrovo)
TEAMS = {
    "partenza": ("Partenza", "Partenza", 1, "Piazza Maggiore - Gazebo START"),
    "arrivo": ("Arrivo", "Arrivo", 2, "Parco della Montagnola - Arco arrivo"),
    "percorso": ("Percorso", "Percorso", 3, "Punto info percorso KM0"),
    "ristori": ("Ristori", "Ristoro", 4, "Magazzino ristori - Via Indipendenza"),
    "expo": ("Expo Village", "Expo", 5, "Tensostruttura Expo - Ingresso"),
    "segreteria": ("Segreteria", "Segreteria", 6, "Gazebo segreteria - Piazza Maggiore"),
    "logistica": ("Logistica", "Logistica", 7, "Deposito materiali - Via Rizzoli"),
}

# person idx -> (team_slug, categoria)
ASSIGN = {
    1: ("partenza", "staff"), 2: ("arrivo", "staff"), 3: ("percorso", "staff"),
    4: ("ristori", "staff"), 5: ("expo", "staff"), 6: ("segreteria", "staff"),
    7: ("logistica", "staff"), 8: ("arrivo", "staff"), 9: ("expo", "staff"),
    10: ("percorso", "staff"), 11: ("arrivo", "staff"), 12: ("percorso", "volontario"),
    13: ("percorso", "volontario"), 14: ("percorso", "volontario"), 15: ("ristori", "volontario"),
    16: ("ristori", "volontario"), 17: ("ristori", "volontario"), 18: ("ristori", "volontario"),
    19: ("segreteria", "staff"), 20: ("segreteria", "volontario"), 21: ("logistica", "staff"),
    22: ("logistica", "volontario"), 23: ("expo", "volontario"), 24: ("expo", "volontario"),
    25: ("partenza", "volontario"), 26: ("partenza", "volontario"), 27: ("partenza", "volontario"),
    28: ("percorso", "staff"), 29: ("arrivo", "staff"), 30: ("expo", "volontario"),
    31: ("ristori", "volontario"), 32: ("arrivo", "staff"), 33: ("logistica", "volontario"),
    34: ("partenza", "volontario"),
}

# Staff arriving the day before (2026-10-17)
ARRIVE_DAY_BEFORE = {1, 2, 3, 4, 5, 6, 7, 8, 9, 19, 21, 32}
STATO_CYCLE = ["confermato", "confermato", "confermato", "da_contattare", "disponibile"]


def pid(i):
    return f"demo_p{i:02d}"


def person_email(nome, cognome):
    base = f"{nome}.{cognome}".lower().replace(" ", "").replace("'", "")
    # strip accents lightly
    for a, b in [("à", "a"), ("è", "e"), ("é", "e"), ("ì", "i"), ("ò", "o"), ("ù", "u")]:
        base = base.replace(a, b)
    return f"{base}@example.com"


# ------------------------------------------------------------------ COMPANIES
# (idx, nome, settore, tipologie)
COMPANIES = [
    (1, "RunPeak Italia", "Sport & Retail", ["sponsor"]),
    (2, "EnerJoy Nutrition", "Food & Beverage", ["sponsor"]),
    (3, "MoveLab", "Tecnologia", ["partner"]),
    (4, "ActiveGear", "Abbigliamento sportivo", ["sponsor"]),
    (5, "EcoCup Solutions", "Sostenibilità", ["fornitore"]),
    (6, "EventSound", "Audio & Luci", ["fornitore"]),
    (7, "PrintWave", "Stampa & Grafica", ["fornitore"]),
    (8, "BolognaFiere Servizi", "Servizi fieristici", ["fornitore"]),
    (9, "TrailFood Catering", "Catering", ["catering", "fornitore"]),
    (10, "Hotel Due Torri", "Ospitalità", ["hotel"]),
    (11, "Ristorante Il Portico", "Ristorazione", ["ristorante"]),
    (12, "MediRun Assistance", "Assistenza medica", ["servizi", "fornitore"]),
    (13, "SecureEvent", "Sicurezza", ["servizi", "fornitore"]),
    (14, "CityBus Transfer", "Trasporti", ["servizi", "fornitore"]),
    (15, "AquaPura", "Beverage", ["sponsor"]),
    (16, "FitWear Italia", "Abbigliamento sportivo", ["sponsor"]),
    (17, "GreenEnergy Bologna", "Energia", ["partner"]),
]


def cid(i):
    return f"demo_co{i:02d}"


# ------------------------------------------------------------------ DEALS
# (idx, co_idx, tipo, fase, valore, valore_confermato, livello, referente_idx)
DEALS = [
    (1, 1, "sponsor", "confermato", 10000, 10000, "Main Sponsor", 5),
    (2, 2, "sponsor", "confermato", 7500, 7500, "Gold", 5),
    (3, 4, "sponsor", "confermato", 5000, 5000, "Silver", 5),
    (4, 15, "sponsor", "in_trattativa", 5000, 0, "Silver", 6),
    (5, 16, "sponsor", "in_trattativa", 3000, 0, "Bronze", 6),
    (6, 3, "partner", "proposta_inviata", 3000, 0, "Technical Partner", 1),
    (7, 17, "partner", "proposta_inviata", 2000, 0, "Technical Partner", 1),
    (8, 6, "fornitore", "contattato", 2000, 0, None, 7),
    (9, 7, "fornitore", "contattato", 2000, 0, None, 7),
    (10, 12, "sponsor", "prospect", 2000, 0, "Bronze", 6),
    (11, 14, "fornitore", "prospect", 1000, 0, None, 7),
    (12, 5, "sponsor", "perso", 4000, 0, "Bronze", 6),
]


def did(i):
    return f"demo_deal_{i:02d}"


# ------------------------------------------------------------------ ACTIVITIES
# (idx, titolo, stato, data_rel_days)   scaduta = stato da_fare + past date
ACTIVITIES = [
    (1, "Autorizzazione Comune di Bologna", "completata", -40),
    (2, "Definizione percorso 21K", "completata", -35),
    (3, "Piano sicurezza e safety", "completata", -30),
    (4, "Ingaggio speaker ufficiale", "completata", -28),
    (5, "Contratto assicurazione evento", "completata", -25),
    (6, "Selezione fornitore cronometraggio", "completata", -20),
    (7, "Apertura iscrizioni online", "completata", -18),
    (8, "Ordine pettorali e chip", "in_corso", 10),
    (9, "Allestimento punti ristoro", "in_corso", 20),
    (10, "Reclutamento volontari per area", "in_corso", 15),
    (11, "Setup Expo Village", "in_corso", 25),
    (12, "Gestione accrediti stampa", "in_corso", 22),
    (13, "Preparazione pacchi gara", "da_fare", 40),
    (14, "Briefing staff pre-gara", "da_fare", 55),
    (15, "Ordine segnaletica percorso", "da_fare", 35),
    (16, "Consegna materiali sponsor", "da_fare", 45),
    (17, "Ordine medaglie finisher", "da_fare", 50),
    (18, "Piano viabilità e transenne", "da_fare", 38),
    (19, "Invio comunicato stampa di lancio", "da_fare", -12),   # scaduta
    (20, "Conferma noleggio impianto audio", "da_fare", -8),     # scaduta
    (21, "Prenotazione hotel giudici di gara", "da_fare", -5),   # scaduta
    (22, "Definizione planimetria Expo", "da_fare", -3),         # scaduta
]


def aid(i):
    return f"demo_act_{i:02d}"


# ------------------------------------------------------------------ FOLLOWUPS
# (idx, titolo, co_idx, scad_rel_days, priorita, stato)
FOLLOWUPS = [
    (1, "Richiamare RunPeak per firma contratto", 1, -10, "alta", "aperto"),   # scaduto
    (2, "Inviare fattura sponsorizzazione EnerJoy", 2, -6, "alta", "aperto"),  # scaduto
    (3, "Sollecito materiali grafici ActiveGear", 4, -3, "media", "aperto"),   # scaduto
    (4, "Call con AquaPura per proposta ristori", 15, 0, "alta", "aperto"),    # oggi
    (5, "Follow-up proposta a FitWear Italia", 16, 5, "media", "aperto"),
    (6, "Definire attivazione partner MoveLab", 3, 8, "media", "aperto"),
    (7, "Preventivo audio EventSound", 6, 12, "bassa", "aperto"),
    (8, "Contratto stampa PrintWave", 7, 15, "media", "aperto"),
    (9, "Rinnovo accordo GreenEnergy", 17, 20, "bassa", "aperto"),
    (10, "Verifica disponibilità CityBus", 14, 18, "bassa", "aperto"),
    (11, "Chiusura accordo assistenza MediRun", 12, 25, "media", "completato"),
]


def fid(i):
    return f"demo_fu_{i:02d}"


# ------------------------------------------------------------------ STRUCTURES
# (idx, nome, tipologia, indirizzo, citta, maps)
STRUCTURES = [
    (1, "Hotel Due Torri", "hotel", "Via San Vitale 12", "Bologna",
     "https://maps.google.com/?q=Hotel+Due+Torri+Bologna"),
    (2, "B&B Il Portico", "bnb", "Via Zamboni 8", "Bologna",
     "https://maps.google.com/?q=Via+Zamboni+8+Bologna"),
    (3, "Ristorante San Luca", "ristorante", "Via Saragozza 45", "Bologna",
     "https://maps.google.com/?q=Ristorante+San+Luca+Bologna"),
    (4, "TrailFood Catering", "catering", "Via Emilia Ponente 100", "Bologna",
     "https://maps.google.com/?q=Via+Emilia+Ponente+100+Bologna"),
]


def sid(i):
    return f"demo_str_{i:02d}"


# ------------------------------------------------------------------ MAPS
MAPS = [
    ("demo_map_01", "Percorso 21K", "percorso", 21.0),
    ("demo_map_02", "Percorso 10K", "percorso", 10.0),
    ("demo_map_03", "Mappa Expo Village", "mappa", None),
]

EV_BCR = "demo_evt_bcr"
EV_TRI = "demo_evt_tri"
EV_TRAIL = "demo_evt_trail"


async def seed(org_id):
    # ---- EVENTS ----
    events = [
        {"id": EV_BCR, "nome": "Bologna City Run 2026", "edizione": "2026", "tipologia": "Running",
         "data_inizio": BCR_D2, "data_fine": BCR_D2, "ora_inizio": "09:00", "ora_fine": "14:00",
         "localita": "Bologna", "citta": "Bologna", "provincia": "BO", "regione": "Emilia-Romagna",
         "nazione": "Italia", "organizzatore": "Demo Sport ASD", "responsabile": "Luca Bianchi",
         "sito_web": "https://bolognacityrun.example.com", "email": "info@bolognacityrun.example.com",
         "telefono": "+39 051 000000", "partecipanti_previsti": 2500, "budget": 120000.0,
         "stato": "attivo",
         "descrizione": "Corsa cittadina su strada con percorsi 21K e 10K nel centro di Bologna.",
         "note": "Ritrovo Piazza Maggiore ore 07:00. Partenza 09:00. Programma: 07:00 apertura Expo/segreteria, "
                 "08:30 riscaldamento con deejay, 09:00 partenza 21K/10K, 11:30 premiazioni, 14:00 chiusura. "
                 "Contatto emergenze: MediRun +39 051 111222."},
        {"id": EV_TRI, "nome": "Sunset Triathlon 2027", "edizione": "2027", "tipologia": "Triathlon",
         "data_inizio": TRI_DATE, "data_fine": TRI_DATE, "ora_inizio": "17:00",
         "localita": "Ravenna", "citta": "Ravenna", "provincia": "RA", "regione": "Emilia-Romagna",
         "nazione": "Italia", "organizzatore": "Demo Sport ASD", "responsabile": "Giulia Ferrari",
         "partecipanti_previsti": 600, "budget": 45000.0, "stato": "pianificato",
         "descrizione": "Triathlon sprint al tramonto sulla riviera ravennate.",
         "note": "Evento in pianificazione."},
        {"id": EV_TRAIL, "nome": "Green Trail Experience 2026", "edizione": "2026", "tipologia": "Trail",
         "data_inizio": TRAIL_DATE, "data_fine": TRAIL_DATE, "ora_inizio": "08:00",
         "localita": "Appennino Bolognese", "citta": "Lizzano in Belvedere", "provincia": "BO",
         "regione": "Emilia-Romagna", "nazione": "Italia", "organizzatore": "Demo Sport ASD",
         "responsabile": "Marco Colombo", "partecipanti_previsti": 800, "budget": 30000.0,
         "stato": "concluso", "descrizione": "Trail running tra i sentieri dell'Appennino.",
         "note": "Evento concluso con successo."},
    ]
    for e in events:
        await upsert("events", e, org_id)

    # ---- PERSONS ----
    for i, nome, cognome, qualifica in PERSONS:
        await upsert("persons", {
            "id": pid(i), "nome": nome, "cognome": cognome,
            "email": person_email(nome, cognome),
            "cellulare": f"+39 3{i:02d} 000{i:04d}", "ruolo": qualifica,
            "citta": "Bologna", "provincia": "BO", "nazione": "Italia",
        }, org_id)

    # ---- TEAMS (BCR) ----
    for slug, (nome, area, leader, ritrovo) in TEAMS.items():
        await upsert("teams", {
            "id": f"demo_team_{slug}", "nome": nome, "evento_id": EV_BCR, "area": area,
            "responsabile_id": pid(leader), "punto_ritrovo": ritrovo,
            "luogo_operativo": f"Area {area} - Bologna City Run",
            "descrizione": f"Team {nome} dell'evento Bologna City Run 2026.",
        }, org_id)

    # ---- STAFF LINKS (BCR) ----
    for idx, (slug, categoria) in ASSIGN.items():
        nome_t, area, leader, ritrovo = TEAMS[slug]
        leader_name = f"{PERSONS[leader-1][1]} {PERSONS[leader-1][2]}"
        arrivo = BCR_D1 if idx in ARRIVE_DAY_BEFORE else BCR_D2
        await upsert("staff", {
            "id": f"demo_staff_bcr_{idx:02d}", "persona_id": pid(idx), "evento_id": EV_BCR,
            "categoria": categoria, "area": area, "ruolo": PERSONS[idx-1][3],
            "team_id": f"demo_team_{slug}",
            "responsabile": leader_name if idx != leader else None,
            "punto_ritrovo": ritrovo, "luogo_operativo": f"Area {area}",
            "data_arrivo": arrivo, "ora_arrivo": "07:00" if arrivo == BCR_D2 else "16:00",
            "data_partenza": BCR_D2, "ora_partenza": "15:00",
            "stato": STATO_CYCLE[idx % len(STATO_CYCLE)],
        }, org_id)

    # A few links on the other two events (realism / relations)
    trail_people = [(1, "staff", "Coordinamento"), (3, "staff", "Responsabile Percorso"),
                    (12, "volontario", "Addetto percorso"), (15, "volontario", "Addetto ristoro"),
                    (10, "staff", "Fotografo")]
    for k, (idx, cat, ruolo) in enumerate(trail_people, 1):
        await upsert("staff", {
            "id": f"demo_staff_trail_{k:02d}", "persona_id": pid(idx), "evento_id": EV_TRAIL,
            "categoria": cat, "ruolo": ruolo, "stato": "confermato",
        }, org_id)
    tri_people = [(2, "staff", "Coordinamento"), (4, "staff", "Responsabile Ristori"),
                  (16, "volontario", "Addetto ristoro")]
    for k, (idx, cat, ruolo) in enumerate(tri_people, 1):
        await upsert("staff", {
            "id": f"demo_staff_tri_{k:02d}", "persona_id": pid(idx), "evento_id": EV_TRI,
            "categoria": cat, "ruolo": ruolo, "stato": "da_contattare",
        }, org_id)

    # ---- SHIFTS (BCR) — day before + race day; leave 2 uncovered ----
    shifts = [
        ("demo_shift_01", BCR_D1, "15:00", "19:00", "Logistica", "logistica", 7, "Allestimento materiali e transenne"),
        ("demo_shift_02", BCR_D1, "15:00", "19:00", "Expo", "expo", 5, "Montaggio Expo Village"),
        ("demo_shift_03", BCR_D1, "16:00", "20:00", "Segreteria", "segreteria", 6, "Preparazione pettorali e pacchi gara"),
        ("demo_shift_04", BCR_D2, "06:00", "10:00", "Partenza", "partenza", 1, "Gestione area partenza"),
        ("demo_shift_05", BCR_D2, "06:00", "10:00", "Partenza", "partenza", 25, "Accoglienza atleti"),
        ("demo_shift_06", BCR_D2, "07:00", "12:00", "Percorso", "percorso", 3, "Presidio KM 5"),
        ("demo_shift_07", BCR_D2, "07:00", "12:00", "Percorso", "percorso", 12, "Presidio KM 10"),
        ("demo_shift_08", BCR_D2, "07:00", "12:00", "Percorso", "percorso", 13, "Presidio KM 15"),
        ("demo_shift_09", BCR_D2, "08:00", "13:00", "Ristoro", "ristori", 4, "Ristoro KM 7"),
        ("demo_shift_10", BCR_D2, "08:00", "13:00", "Ristoro", "ristori", 15, "Ristoro KM 14"),
        ("demo_shift_11", BCR_D2, "09:00", "14:00", "Arrivo", "arrivo", 2, "Gestione area arrivo e ristoro finale"),
        ("demo_shift_12", BCR_D2, "09:00", "14:00", "Arrivo", "arrivo", 8, "Speaker e premiazioni"),
        # Uncovered (persona_id=None) — Demobot must detect these
        ("demo_shift_13", BCR_D2, "06:00", "10:00", "Ristoro", "ristori", None, "Ristoro KM 3 — DA COPRIRE"),
        ("demo_shift_14", BCR_D2, "07:00", "12:00", "Percorso", "percorso", None, "Presidio incrocio Via Rizzoli — DA COPRIRE"),
    ]
    for _id, d, oi, of, area, slug, pidx, note in shifts:
        await upsert("shifts", {
            "id": _id, "evento_id": EV_BCR, "data": d, "ora_inizio": oi, "ora_fine": of,
            "area": area, "team_id": f"demo_team_{slug}",
            "persona_id": pid(pidx) if pidx else None,
            "ruolo": PERSONS[pidx-1][3] if pidx else None,
            "punto_ritrovo": TEAMS[slug][3], "note": note,
        }, org_id)

    # ---- COMPANIES ----
    for i, nome, settore, tipologie in COMPANIES:
        await upsert("companies", {
            "id": cid(i), "nome": nome, "settore": settore, "tipo": "azienda",
            "tipologie": tipologie, "citta": "Bologna", "provincia": "BO", "nazione": "Italia",
            "email": f"info@{nome.lower().replace(' ', '')}.example.com",
        }, org_id)

    # ---- DEALS (BCR pipeline) ----
    for i, coi, tipo, fase, val, valc, liv, refi in DEALS:
        await upsert("deals", {
            "id": did(i), "azienda_id": cid(coi), "evento_id": EV_BCR, "tipo": tipo,
            "fase": fase, "valore": val, "valore_confermato": valc, "livello": liv,
            "referente_id": pid(refi), "stato": "confermato" if fase == "confermato" else ("perso" if fase == "perso" else "aperta"),
        }, org_id)

    # ---- ACTIVITIES ----
    for i, titolo, stato, drel in ACTIVITIES:
        await upsert("activities", {
            "id": aid(i), "titolo": titolo, "tipo": "generica", "evento_id": EV_BCR,
            "data": rel(drel), "stato": stato,
        }, org_id)

    # ---- FOLLOWUPS ----
    for i, titolo, coi, srel, prio, stato in FOLLOWUPS:
        await upsert("followups", {
            "id": fid(i), "titolo": titolo, "evento_id": EV_BCR, "azienda_id": cid(coi),
            "scadenza": rel(srel), "priorita": prio, "stato": stato,
        }, org_id)

    # ---- STRUCTURES ----
    for i, nome, tipologia, indirizzo, citta, maps in STRUCTURES:
        await upsert("structures", {
            "id": sid(i), "nome": nome, "tipologia": tipologia, "indirizzo": indirizzo,
            "citta": citta, "provincia": "BO", "google_maps_url": maps,
            "referente": "Reception", "telefono": "+39 051 999000",
        }, org_id)

    # ---- LODGINGS (BCR) — staff sleeping, arrivals the day before ----
    # (person_idx, struttura_idx, a_carico_di, check_out, tipo_camera, costo)
    lodgings = [
        (1, 1, "organizzazione", BCR_D2, "singola", 90.0),
        (2, 1, "organizzazione", "2026-10-19", "singola", 180.0),
        (3, 1, "organizzazione", BCR_D2, "doppia", 70.0),
        (4, 1, "organizzazione", BCR_D2, "doppia", 70.0),
        (5, 2, "organizzazione", BCR_D2, "singola", 65.0),
        (6, 2, "persona", BCR_D2, "singola", 65.0),
        (7, 2, "persona", BCR_D2, "doppia", 55.0),
        (32, 1, "organizzazione", "2026-10-19", "singola", 180.0),
    ]
    for k, (pidx, stri, carico, cout, camera, costo) in enumerate(lodgings, 1):
        await upsert("lodgings", {
            "id": f"demo_lod_{k:02d}", "evento_id": EV_BCR, "persona_id": pid(pidx),
            "struttura_id": sid(stri), "struttura_nome": STRUCTURES[stri-1][1],
            "tipo_struttura": STRUCTURES[stri-1][2], "indirizzo": STRUCTURES[stri-1][3],
            "check_in": BCR_D1, "check_out": cout, "tipo_camera": camera,
            "a_carico_di": carico, "costo": costo,
            "stato_pagamento": "pagato" if carico == "organizzazione" else "non_pagato",
        }, org_id)

    # ---- MEALS (BCR) — 17 & 18 October ----
    meal_plan = [
        # (person_idx, data, tipo_pasto, struttura_idx, a_carico_di, costo)
        (1, BCR_D1, "cena", 3, "organizzazione", 25.0),
        (2, BCR_D1, "cena", 3, "organizzazione", 25.0),
        (3, BCR_D1, "cena", 3, "organizzazione", 25.0),
        (4, BCR_D1, "cena", 3, "persona", 25.0),
        (1, BCR_D2, "colazione", 1, "organizzazione", 8.0),
        (2, BCR_D2, "colazione", 1, "organizzazione", 8.0),
        (3, BCR_D2, "colazione", 1, "organizzazione", 8.0),
        (4, BCR_D2, "pranzo", 4, "organizzazione", 15.0),
        (5, BCR_D2, "pranzo", 4, "organizzazione", 15.0),
        (15, BCR_D2, "pranzo", 4, "organizzazione", 15.0),
        (16, BCR_D2, "pranzo", 4, "organizzazione", 15.0),
        (8, BCR_D2, "pranzo", 4, "persona", 15.0),
    ]
    for k, (pidx, d, tp, stri, carico, costo) in enumerate(meal_plan, 1):
        await upsert("meals", {
            "id": f"demo_meal_{k:02d}", "evento_id": EV_BCR, "persona_id": pid(pidx),
            "struttura_id": sid(stri), "struttura_nome": STRUCTURES[stri-1][1],
            "data": d, "tipo_pasto": tp, "a_carico_di": carico, "costo": costo,
            "tipologia_servizio": "catering" if stri == 4 else "ristorante",
        }, org_id)

    # ---- MAPS (BCR) ----
    for _id, nome, tipologia, dist in MAPS:
        await upsert("event_maps", {
            "id": _id, "evento_id": EV_BCR, "nome": nome, "tipologia": tipologia,
            "distanza": dist, "google_maps_url": "https://maps.google.com/?q=Bologna+City+Run",
        }, org_id)


async def wipe(org_id):
    colls = ["events", "persons", "teams", "staff", "shifts", "companies", "deals",
             "activities", "followups", "structures", "lodgings", "meals", "event_maps"]
    for c in colls:
        res = await db[c].delete_many({"org_id": org_id, "id": {"$regex": "^demo_"}})
        if res.deleted_count:
            print(f"[-] {c}: rimossi {res.deleted_count} record demo_*")


async def report(org_id):
    colls = ["events", "persons", "teams", "staff", "shifts", "companies", "deals",
             "activities", "followups", "structures", "lodgings", "meals", "event_maps"]
    print("\n=== RIEPILOGO RECORD DEMO (org_id=%s) ===" % org_id)
    for c in colls:
        n = await db[c].count_documents({"org_id": org_id, "id": {"$regex": "^demo_"}})
        print(f"  {c:14s}: {n}")


async def main():
    org = await get_or_create_demo_org()
    org_id = org["id"]
    if "--wipe" in sys.argv:
        await wipe(org_id)
    await seed(org_id)
    await report(org_id)
    print("\n[OK] Seeding Demo completato (idempotente).")


if __name__ == "__main__":
    asyncio.run(main())
