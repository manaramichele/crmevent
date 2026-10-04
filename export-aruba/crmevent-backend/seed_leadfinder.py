"""Seed the Lead Finder DB with 20 REAL Italian sports events publicly listed on ENDU.
Event-level data (name, sport, city/province, date, ENDU URL) is sourced from ENDU.
Contacts and social profiles are left as 'da_verificare' (NOT invented): they require
consulting the official organizer/event site — reported honestly in the test.
Idempotent: safe to re-run (upsert by ENDU slug / organizer name_key)."""
import re
from datetime import datetime, timezone
from pymongo import MongoClient

PLATFORM = "__platform__"
REGION = {
    "SI": "Toscana", "PI": "Toscana", "LI": "Toscana", "TN": "Trentino-Alto Adige",
    "MI": "Lombardia", "MB": "Lombardia", "VA": "Lombardia", "VR": "Veneto", "TV": "Veneto",
    "NA": "Campania", "UD": "Friuli-Venezia Giulia", "AP": "Marche", "FG": "Puglia",
    "BA": "Puglia", "BI": "Piemonte", "OT": "Sardegna",
}
ENDU = "https://www.endu.net/events/"

# (organizer_name, org_type, [ (event, sport, city, prov, date, slug) ... ])
DATA = [
    ("Adriatic Series", "circuito", [
        ("Adriatic Series - Salaria Run", "Road running", "Ascoli Piceno", "AP", "04/10/2026", "salaria-run"),
        ("Grand Final Adriatic Series - Triathlon Sprint S. Benedetto del Tronto", "Triathlon", "San Benedetto del Tronto", "AP", "11/10/2026", "triathlon-sprint-citta-di-san-benedetto-del-tronto"),
        ("Adriatic Series - Lake Varano Tri - Gargano", "Triathlon", "Ischitella", "FG", "18/10/2026", "lake-varano-tri-113-gargano"),
    ]),
    ("Giro Handbike", "circuito", [
        ("Giro Handbike - Tappa 5", "Road cycling", "Biella", "BI", "04/10/2026", "giro-handbike-tappa-5"),
        ("Giro Handbike - Tappa 7", "Road cycling", "Bari", "BA", "10-11/10/2026", "giro-handbike-tappa-7"),
    ]),
    ("Porto Cervo (serie sportiva)", "circuito", [
        ("Porto Cervo Terra Mare Cup", "Trail", "Porto Cervo", "OT", "10-11/10/2026", "porto-cervo-terra-mare-cup"),
        ("Porto Cervo Trail", "Trail", "Porto Cervo", "OT", "10/10/2026", "porto-cervo-trail"),
        ("Porto Cervo Swim", "Open waters", "Porto Cervo", "OT", "11/10/2026", "porto-cervo-swim"),
    ]),
    ("MontepulcianoRun", "asd", [("MontepulcianoRun", "Road running", "Montepulciano", "SI", "02-04/10/2026", "montepulcianorun")]),
    ("Fiemme Ultra Sky", "asd", [("Fiemme Ultra Sky", "Trail", "Cavalese", "TN", "02-04/10/2026", "fiemme-ultra-sky")]),
    ("Deejay Ten Milano", "evento", [("Deejay Ten Milano", "Road running", "Milano", "MI", "04/10/2026", "deejay-ten-milano-2")]),
    ("PeschieraTRI", "asd", [("PeschieraTRI - MEDIO-OLIMPICO-SPRINT", "Triathlon", "Peschiera del Garda", "VR", "03-04/10/2026", "peschiera-del-garda-triathlon")]),
    ("Monza Half Marathon", "asd", [("Monza Half Marathon", "Road running", "Monza", "MB", "04/10/2026", "monza21-halfmarathon")]),
    ("Pisa Half Marathon", "asd", [("Pisa Half Marathon e VII Pisa Ten", "Road running", "Pisa", "PI", "11/10/2026", "pisa-half-marathon")]),
    ("Neapolis Marathon", "asd", [("Neapolis Marathon", "Road running", "Napoli", "NA", "18/10/2026", "neapolis-marathon")]),
    ("Granfondo Tre Valli Varesine", "asd", [("Granfondo Tre Valli Varesine", "Road cycling", "Varese", "VA", "03-04/10/2026", "granfondo_tre_valli_varesine")]),
    ("Coppa Bernocchi - GP Banco BPM", "asd", [("Coppa Bernocchi - GP Banco BPM", "Road cycling", "Legnano", "VA", "05/10/2026", "coppa-bernocchi-gp-banco-bpm")]),
    ("La Mezza di Treviso", "asd", [("La Mezza di Treviso International Half Marathon", "Road running", "Treviso", "TV", "11/10/2026", "la-mezza-di-treviso-international-half-marathon")]),
    ("Elba Legend Run", "asd", [("Elba Legend Run", "Trail", "Capoliveri", "LI", "04/10/2026", "elba-legend-run")]),
    ("Lignano Triathlon", "asd", [("Lignano Olympic & Sprint Triathlon", "Triathlon", "Lignano Sabbiadoro", "UD", "10-11/10/2026", "lignano-olympic-and-sprint-triathlon")]),
]


def _key(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def run():
    import os
    env = {}
    for l in open(os.path.join(os.path.dirname(__file__), ".env")):
        if "=" in l and not l.strip().startswith("#"):
            k, v = l.strip().split("=", 1); env[k] = v.strip().strip('"').strip("'")
    db = MongoClient(env["MONGO_URL"])[env["DB_NAME"]]
    now = datetime.now(timezone.utc).isoformat()
    n_org = n_ev = 0
    for name, otype, events in DATA:
        src_url = ENDU + events[0][5]
        org = db.lf_organizers.find_one({"org_id": PLATFORM, "name_key": _key(name)})
        if not org:
            oid = re.sub(r"-", "", __import__("uuid").uuid4().hex)
            org = {
                "id": oid, "org_id": PLATFORM, "name": name, "name_key": _key(name),
                "legal_name": None, "org_type": otype, "city": events[0][2], "province": events[0][3],
                "region": REGION.get(events[0][3]), "country": "Italia", "website": None, "web_domain": None,
                "email": None, "emails": [], "phone": None,
                "instagram_url": None, "linkedin_url": None, "facebook_url": None,
                "socials_status": "da_verificare", "status": "da_verificare",
                "source_main": "ENDU", "source_url": src_url,
                "sources": {"name": {"url": src_url}, "location": {"url": src_url}},
                "acquired_at": now, "last_verified_at": None, "created_at": now, "updated_at": now,
            }
            db.lf_organizers.insert_one(org); n_org += 1
        for (ename, sport, city, prov, date, slug) in events:
            eurl = ENDU + slug
            if db.lf_events.find_one({"org_id": PLATFORM, "endu_url": eurl}):
                continue
            db.lf_events.insert_one({
                "id": __import__("uuid").uuid4().hex, "org_id": PLATFORM, "organizer_id": org["id"],
                "name": ename, "sport": sport, "type": None, "date": date,
                "city": city, "province": prov, "region": REGION.get(prov),
                "website": None, "endu_url": eurl,
                "instagram_url": None, "facebook_url": None, "linkedin_url": None,
                "status": "programmato",
                "sources": {"event": {"url": eurl}, "sport": {"url": eurl}, "location": {"url": eurl}, "date": {"url": eurl}},
                "created_at": now, "updated_at": now,
            }); n_ev += 1
    # ensure indexes for dedup lookups
    db.lf_organizers.create_index([("org_id", 1), ("name_key", 1)])
    db.lf_events.create_index([("org_id", 1), ("endu_url", 1)])
    print("organizers:", db.lf_organizers.count_documents({"org_id": PLATFORM}),
          "(+%d) events:" % n_org, db.lf_events.count_documents({"org_id": PLATFORM}), "(+%d)" % n_ev)


if __name__ == "__main__":
    run()
