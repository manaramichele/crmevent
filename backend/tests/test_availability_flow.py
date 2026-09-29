import asyncio, os, sys
os.environ.setdefault("DB_NAME", os.environ.get("DB_NAME", "test_database"))
from motor.motor_asyncio import AsyncIOMotorClient
import httpx

MONGO = os.environ["MONGO_URL"]; DBN = os.environ["DB_NAME"]
LOCAL = "http://localhost:8001"
CODE = "TEST_AVAIL_CODE_NOVA_2026"
ORG = "nova_events_test_org"
EV = "nova_run_festival_evt"


async def setup(db):
    await db.availabilities.delete_many({"org_id": ORG})
    await db.avail_links.delete_many({"org_id": ORG})
    await db.persons.delete_many({"org_id": ORG})
    await db.events.delete_many({"org_id": ORG})
    await db.settings.delete_many({"id": ORG})
    await db.organizations.delete_many({"id": ORG})
    await db.organizations.insert_one({"id": ORG, "nome": "Nova Events", "type": "test", "status": "active", "subscription": {"status": "test"}})
    await db.settings.insert_one({"id": ORG, "ruoli_staff": ["Ristoro", "Accoglienza", "Percorso"], "aree_operative": ["Expo"]})
    await db.events.insert_one({"id": EV, "org_id": ORG, "nome": "Nova Run Festival",
                                "data_inizio_allestimento": "2026-12-18", "data_inizio": "2026-12-20",
                                "data_fine": "2026-12-20", "localita": "Milano", "stato": "pianificato"})
    await db.avail_links.insert_one({"id": "lk1", "org_id": ORG, "evento_id": EV, "code": CODE, "active": True, "created_at": "x"})


def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    if not cond:
        globals()["_fail"] = True


async def main():
    db = AsyncIOMotorClient(MONGO)[DBN]
    await setup(db)
    globals()["_fail"] = False
    async with httpx.AsyncClient(base_url=LOCAL, timeout=30) as c:
        # 1. public info
        r = await c.get(f"/api/public/availability/{CODE}")
        j = r.json()
        check("info 200", r.status_code == 200)
        check("info active", j.get("active") is True)
        check("info has_allestimento", j.get("has_allestimento") is True)
        days = j.get("days", [])
        check("3 days (18,19,20)", len(days) == 3)
        check("18 allestimento", days[0]["date"] == "2026-12-18" and days[0]["fase"] == "allestimento")
        check("20 evento", days[2]["date"] == "2026-12-20" and days[2]["fase"] == "evento")
        check("attivita options present", "Ristoro" in (j.get("attivita_options") or []))

        # 2. submit valid CF
        body = {"nome": "Mario", "cognome": "Rossi", "cellulare": "3331112222", "email": "mario.rossi@example.com",
                "codice_fiscale": "rssmra85t10a562s", "days": [
                    {"date": "2026-12-18", "disponibile": True, "dalle": "14:00", "alle": "20:00"},
                    {"date": "2026-12-20", "disponibile": True}],
                "preferenza_attivita": "Ristoro", "privacy": True}
        r = await c.post(f"/api/public/availability/{CODE}", json=body)
        check("submit 200", r.status_code == 200)
        p = await db.persons.find_one({"org_id": ORG, "email": "mario.rossi@example.com"})
        check("person created", p is not None)
        check("birth from CF", p and p.get("data_nascita") == "1985-12-10")
        check("CF stored upper", p and p.get("codice_fiscale") == "RSSMRA85T10A562S")
        a = await db.availabilities.find_one({"org_id": ORG, "persona_id": p["id"]})
        check("availability created", a is not None)
        check("ruolo da_definire", a and a.get("ruolo_evento") == "da_definire")
        check("stato nuova", a and a.get("stato") == "nuova")
        check("2 days saved", a and len(a.get("days", [])) == 2)
        check("privacy logged", a and a.get("privacy_accepted") is True and a.get("ip"))

        # 3. duplicate submit (same email) -> no new person, availability updated with 3 days
        body2 = {**body, "days": [
            {"date": "2026-12-18", "disponibile": True},
            {"date": "2026-12-19", "disponibile": True},
            {"date": "2026-12-20", "disponibile": True}]}
        r = await c.post(f"/api/public/availability/{CODE}", json=body2)
        check("dup submit 200", r.status_code == 200)
        cnt_p = await db.persons.count_documents({"org_id": ORG, "email": "mario.rossi@example.com"})
        check("no duplicate person", cnt_p == 1)
        cnt_a = await db.availabilities.count_documents({"org_id": ORG, "persona_id": p["id"]})
        check("no duplicate availability", cnt_a == 1)
        a2 = await db.availabilities.find_one({"org_id": ORG, "persona_id": p["id"]})
        check("availability updated to 3 days", len(a2.get("days", [])) == 3)

        # 4. invalid CF
        r = await c.post(f"/api/public/availability/{CODE}", json={**body, "email": "x@y.it", "codice_fiscale": "INVALIDCF0000000"})
        check("invalid CF 400", r.status_code == 400)

        # 5. foreign (no CF -> DOB)
        fb = {"nome": "John", "cognome": "Smith", "cellulare": "3339998888", "email": "john@example.com",
              "codice_fiscale": None, "data_nascita": "1990-05-05",
              "days": [{"date": "2026-12-20", "disponibile": True}], "privacy": True}
        r = await c.post(f"/api/public/availability/{CODE}", json=fb)
        check("foreign submit 200", r.status_code == 200)
        pf = await db.persons.find_one({"org_id": ORG, "email": "john@example.com"})
        check("foreign person DOB", pf and pf.get("data_nascita") == "1990-05-05" and not pf.get("codice_fiscale"))

        # 6. privacy required
        r = await c.post(f"/api/public/availability/{CODE}", json={**fb, "email": "z@z.it", "privacy": False})
        check("privacy required 400", r.status_code == 400)

        # 7. deactivate -> 410 on submit, info active False
        await db.avail_links.update_one({"code": CODE}, {"$set": {"active": False}})
        r = await c.post(f"/api/public/availability/{CODE}", json=fb)
        check("deactivated submit 410", r.status_code == 410)
        r = await c.get(f"/api/public/availability/{CODE}")
        check("deactivated info active False", r.json().get("active") is False)

        # 8. bad code 404
        r = await c.get("/api/public/availability/nonexistentcode123")
        check("bad code 404", r.status_code == 404)

    print("\nRESULT:", "FAIL" if globals().get("_fail") else "ALL PASS")
    sys.exit(1 if globals().get("_fail") else 0)


asyncio.run(main())
