import asyncio, os, uuid, sys
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"), override=True)
import bcrypt
from motor.motor_asyncio import AsyncIOMotorClient
import storage_utils

ORG = "c5efb5a60b8345a1a51cb491e3a69b1e"  # TabTest Org
EVID = "trail-del-lago-test"
NOW = datetime.now(timezone.utc).isoformat()
def nid():
    return uuid.uuid4().hex

async def main():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]

    # clean previous run
    for coll in ["structures", "events", "event_maps", "teams", "shifts", "lodgings", "meals", "staff", "persons", "users", "files"]:
        await db[coll].delete_many({"org_id": ORG, "_seed_staff": True})

    # Structure with Google Maps link + address
    struct_id = nid()
    await db.structures.insert_one({"id": struct_id, "org_id": ORG, "_seed_staff": True,
        "nome": "Hotel Bellavista", "tipologia": "Hotel", "indirizzo": "Via Roma 12", "citta": "Como", "provincia": "CO",
        "telefono": "+39031123456", "referente": "Reception", "google_maps_url": "https://maps.google.com/?q=Hotel+Bellavista+Como",
        "created_at": NOW})

    # Event with logo, day descriptions, note (briefing)
    await db.events.insert_one({"id": EVID, "org_id": ORG, "_seed_staff": True,
        "nome": "Trail del Lago", "logo_url": "https://crmevent.it/logo-crmevent.png",
        "data_inizio": "2026-07-11", "data_fine": "2026-07-12", "ora_inizio": "08:00",
        "localita": "Lungolago", "indirizzo": "Piazza Cavour", "citta": "Como",
        "descrizione": "Trail runcing sul lago di Como. Ritrovo staff ore 7:00.",
        "note": "Portare pettorina e radio. Riunione staff il venerdì sera alle 20:00.",
        "giorni_descrizioni": {"2026-07-11": "Allestimento e prove percorso.", "2026-07-12": "Gara: apertura cancelli 8:00, partenza 9:30."},
        "stato": "pianificato", "created_at": NOW})

    # GPX file stored so /api/files works
    gpx = ("<?xml version=\"1.0\"?>\n<gpx version=\"1.1\" creator=\"CRMEvent\">\n<trk><name>Percorso Gara</name><trkseg>\n"
           "<trkpt lat=\"45.8081\" lon=\"9.0852\"/><trkpt lat=\"45.8100\" lon=\"9.0830\"/>"
           "<trkpt lat=\"45.8125\" lon=\"9.0870\"/><trkpt lat=\"45.8110\" lon=\"9.0910\"/>"
           "<trkpt lat=\"45.8081\" lon=\"9.0852\"/>\n</trkseg></trk></gpx>").encode()
    fid = nid()
    path = f"{storage_utils.APP_NAME}/uploads/seed/{fid}.gpx"
    res = await asyncio.to_thread(storage_utils.put_object, path, gpx, "application/gpx+xml")
    await db.files.insert_one({"id": fid, "org_id": ORG, "_seed_staff": True, "storage_path": res["path"],
        "original_filename": "percorso-gara.gpx", "content_type": "application/gpx+xml", "size": res.get("size"),
        "is_deleted": False, "created_at": NOW})

    # Event map with GPX + Google Maps
    await db.event_maps.insert_one({"id": nid(), "org_id": ORG, "_seed_staff": True, "evento_id": EVID,
        "nome": "Percorso Gara 10km", "tipologia": "Percorso", "descrizione": "Tracciato ufficiale della gara.",
        "gpx_url": f"/api/files/{fid}", "google_maps_url": "https://maps.google.com/?q=Lungolago+Como", "distanza": 10.0,
        "created_at": NOW})

    # Leader person + team
    leader_pid = nid()
    await db.persons.insert_one({"id": leader_pid, "org_id": ORG, "_seed_staff": True,
        "nome": "Luca", "cognome": "Bianchi", "ruolo": "Coordinatore", "created_at": NOW})
    team_id = nid()
    await db.teams.insert_one({"id": team_id, "org_id": ORG, "_seed_staff": True, "evento_id": EVID,
        "nome": "Team Percorso", "area": "Percorso", "responsabile_id": leader_pid,
        "luogo_operativo": "Zona partenza", "punto_ritrovo": "Gazebo staff", "created_at": NOW})
    await db.staff.insert_one({"id": nid(), "org_id": ORG, "_seed_staff": True, "evento_id": EVID,
        "persona_id": leader_pid, "categoria": "staff", "team_id": team_id, "ruolo": "Coordinatore", "stato": "confermato", "created_at": NOW})

    # TEST member person + user
    pid = nid()
    await db.persons.insert_one({"id": pid, "org_id": ORG, "_seed_staff": True,
        "nome": "Marco", "cognome": "Verdi", "email": "staffmember@tabtest.crmevent.it",
        "ruolo": "Volontario percorso", "invite_status": "account_attivato", "created_at": NOW})
    uid = "user_" + nid()[:12]
    await db.users.insert_one({"user_id": uid, "org_id": ORG, "_seed_staff": True,
        "email": "staffmember@tabtest.crmevent.it", "name": "Marco Verdi", "role": "volunteer",
        "auth_provider": "password", "person_id": pid, "active": True,
        "password_hash": bcrypt.hashpw(b"MemberTest2026!", bcrypt.gensalt()).decode(), "created_at": NOW})

    # TEST member presence (incarico)
    await db.staff.insert_one({"id": nid(), "org_id": ORG, "_seed_staff": True, "evento_id": EVID,
        "persona_id": pid, "categoria": "volontario", "team_id": team_id, "ruolo": "Volontario percorso",
        "area": "Percorso", "responsabile": "Luca Bianchi", "punto_ritrovo": "Gazebo staff", "luogo_operativo": "Km 3",
        "note_operative": "Presidio ristoro km 3, controllo passaggio atleti.",
        "data_arrivo": "2026-07-11", "ora_arrivo": "18:00", "data_partenza": "2026-07-12", "ora_partenza": "16:00",
        "stato": "confermato", "created_at": NOW})

    # Shift
    await db.shifts.insert_one({"id": nid(), "org_id": ORG, "_seed_staff": True, "evento_id": EVID,
        "persona_id": pid, "team_id": team_id, "data": "2026-07-12", "ora_inizio": "08:00", "ora_fine": "13:00",
        "ruolo": "Ristoro", "area": "Percorso", "luogo": "Ristoro km 3", "punto_ritrovo": "Gazebo staff",
        "note": "Preparare acqua e sali minerali.", "created_at": NOW})

    # Lodging (with admin/cost fields that MUST be stripped for staff)
    await db.lodgings.insert_one({"id": nid(), "org_id": ORG, "_seed_staff": True, "evento_id": EVID,
        "persona_id": pid, "struttura_id": struct_id, "tipo_struttura": "hotel",
        "check_in": "2026-07-11 18:00", "check_out": "2026-07-12 10:00", "tipo_camera": "doppia",
        "note": "Colazione inclusa.", "note_amministrative": "SECRETO-ADMIN", "costo": 120.0, "stato_pagamento": "pagato",
        "a_carico_di": "organizzazione", "codice_prenotazione": "ABC999", "created_at": NOW})

    # Meal (with cost that must be stripped)
    await db.meals.insert_one({"id": nid(), "org_id": ORG, "_seed_staff": True, "evento_id": EVID,
        "persona_id": pid, "struttura_id": struct_id, "data": "2026-07-12", "tipo_pasto": "pranzo",
        "tipologia_servizio": "Cestino", "orario": "13:30", "note": "Ritirare al gazebo.",
        "costo": 15.0, "note_amministrative": "SECRETO-MEAL", "created_at": NOW})

    # SECOND person with own lodging+meal -> member must NOT see these
    other_pid = nid()
    await db.persons.insert_one({"id": other_pid, "org_id": ORG, "_seed_staff": True,
        "nome": "Sara", "cognome": "Neri", "created_at": NOW})
    await db.staff.insert_one({"id": nid(), "org_id": ORG, "_seed_staff": True, "evento_id": EVID,
        "persona_id": other_pid, "categoria": "volontario", "team_id": team_id, "stato": "confermato", "created_at": NOW})
    await db.lodgings.insert_one({"id": nid(), "org_id": ORG, "_seed_staff": True, "evento_id": EVID,
        "persona_id": other_pid, "struttura_id": struct_id, "check_in": "2026-07-11", "note": "OTHER-LODGING", "created_at": NOW})
    await db.meals.insert_one({"id": nid(), "org_id": ORG, "_seed_staff": True, "evento_id": EVID,
        "persona_id": other_pid, "data": "2026-07-12", "tipo_pasto": "cena", "note": "OTHER-MEAL", "created_at": NOW})

    print("SEED OK")
    print("event_id:", EVID)
    print("member_login:", "staffmember@tabtest.crmevent.it", "/", "MemberTest2026!")
    print("test_person_id:", pid, "other_person_id:", other_pid)

asyncio.run(main())
