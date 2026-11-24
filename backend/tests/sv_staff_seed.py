import sys, uuid, bcrypt, requests
from datetime import datetime, timezone
from pymongo import MongoClient
from dotenv import dotenv_values

env = dotenv_values('/app/backend/.env'); db = MongoClient(env['MONGO_URL'])[env['DB_NAME']]
API = dotenv_values('/app/frontend/.env')['REACT_APP_BACKEND_URL'] + "/api"
ORG, EV, EV2, UID = "org_svtest", "ev_svtest", "ev_svtest2", "user_svtest"
EMAIL, PW = "svtest.admin@example.com", "SvTest2026!"
now = datetime.now(timezone.utc).isoformat()
COLLS = ["organizations", "users", "memberships", "events", "persons", "staff", "availabilities", "shifts", "audit_logs", "audit"]


def clean():
    db.organizations.delete_many({"id": {"$in": [ORG, ORG + "2"]}})
    for c in COLLS[1:]:
        db[c].delete_many({"org_id": {"$in": [ORG, ORG + "2"]}})
    db.users.delete_many({"email": {"$regex": "^svtest\\."}})
    db.memberships.delete_many({"user_id": UID})


def seed():
    clean()
    sub = {"status": "test", "plan": "crmevent", "billing_cycle": None, "trial_start": None, "trial_end": None, "current_period_end": None, "stripe_customer_id": None, "stripe_subscription_id": None}
    db.organizations.insert_one({"id": ORG, "nome": "SV Test Org", "type": "test", "status": "active", "owner_user_id": UID, "subscription": sub, "created_at": now, "updated_at": now})
    db.organizations.insert_one({"id": ORG + "2", "nome": "SV Other Org", "type": "test", "status": "active", "subscription": sub, "created_at": now, "updated_at": now})
    db.users.insert_one({"user_id": UID, "email": EMAIL, "name": "Sv Admin", "nome": "Sv", "cognome": "Admin", "password_hash": bcrypt.hashpw(PW.encode(), bcrypt.gensalt()).decode(),
                         "role": "admin", "auth_provider": "password", "org_id": ORG, "telefono": "+393331112233", "active": True, "accepted_terms_at": now, "created_at": now, "welcome_demo": "done"})
    db.memberships.insert_one({"id": uuid.uuid4().hex, "user_id": UID, "org_id": ORG, "role": "admin_org", "active": True, "permissions": {}, "created_at": now, "updated_at": now})
    for e, n in ((EV, "SV Maratona Test"), (EV2, "SV Altro Evento")):
        db.events.insert_one({"id": e, "org_id": ORG, "nome": n, "data_inizio": "2026-12-13", "data_fine": "2026-12-14", "stato": "attivo", "created_at": now})
    P = [("p1", "Anna", "Verdi", "volontario", "confermato", True), ("p2", "Bruno", "Neri", "volontario", "da_contattare", True), ("p3", "Carla", "Blu", "staff", "rinunciato", True),
         ("p4", "Dario", "Gialli", "staff", "confermato", True), ("p5", "Elena", "Rosa", "volontario", "confermato", False), ("p6", "Fabio", "Viola", "volontario", "disponibile", True)]
    for pid, n, c, cat, st, mail in P:
        db.persons.insert_one({"id": "sv_" + pid, "org_id": ORG, "nome": n, "cognome": c, "email": f"svtest.{pid}@example.com" if mail else None, "ruolo": "Infermiere" if pid == "p1" else None,
                               "gruppo_appartenenza": "ASD Prova" if pid in ("p1", "p4") else None, "invite_status": "non_invitato", "created_at": now})
        db.staff.insert_one({"id": "sv_l_" + pid, "org_id": ORG, "persona_id": "sv_" + pid, "evento_id": EV, "categoria": cat, "stato": st, "ruolo": "Ristoro" if pid == "p1" else None, "created_at": now})
    db.availabilities.insert_one({"id": "sv_av1", "org_id": ORG, "persona_id": "sv_p1", "evento_id": EV, "created_at": now,
                                  "days": [{"date": "2026-12-13", "fasce": [{"id": "mattina", "start": "07:00", "end": "13:00"}]}, {"date": "2026-12-14", "dalle": "08:00", "alle": "12:00"}]})
    db.shifts.insert_one({"id": "sv_shift", "org_id": ORG, "evento_id": EV, "persona_id": "sv_p1", "data": "2026-12-13"})
    db.persons.insert_one({"id": "sv_other", "org_id": ORG + "2", "nome": "Altro", "cognome": "Tenant", "email": "svtest.other@example.com", "created_at": now})
    db.staff.insert_one({"id": "sv_l_other", "org_id": ORG + "2", "persona_id": "sv_other", "evento_id": "x", "categoria": "volontario", "stato": "confermato"})


def ok(c, m):
    print(("PASS " if c else "FAIL ") + m)


def test():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": EMAIL, "password": PW}); assert r.status_code == 200, r.text
    rows = {x["id"]: x for x in s.get(f"{API}/persons-enriched").json()}
    ok(len(rows) == 6 and "sv_other" not in rows, "enriched: only own org")
    ok(rows["sv_p1"]["access_status"] == "email_da_inviare", "access status default")
    ok(rows["sv_p1"]["disponibilita"][0]["testo"] == "13/12 Mattina · 14/12 08:00–12:00", f"disponibilita text {rows['sv_p1']['disponibilita']}")
    ok(s.get(f"{API}/shifts").status_code in (403, 404, 405), "/shifts removed")
    ok(db.shifts.count_documents({"id": "sv_shift"}) == 1, "historic shift kept")
    ok("shifts" not in s.get(f"{API}/persons/sv_p1/detail").json(), "detail without shifts")
    b = s.get(f"{API}/events/{EV}/briefing-live"); ok(b.status_code == 200 and "shifts" not in b.json().get("sections", {}) and "turni_count" not in b.json().get("stats", {}), f"briefing without shifts {b.status_code}")
    d = s.get(f"{API}/dashboard"); ok(d.status_code == 200 and "turni_totali" not in str(d.json()), f"dashboard without turni {d.status_code}")
    pv = s.post(f"{API}/person-invites/access-preview", json={"all_unsent": True, "evento_id": EV}).json()
    ids = {x["id"]: x["reason"] for x in pv["recipients"]}
    ok(pv["to_send"] == 2 and ids == {"sv_p1": None, "sv_p4": None, "sv_p5": "Senza indirizzo email"}, f"all_unsent preview only confirmed {ids}")
    ok("<" in pv["html"] and pv["subject"], "preview html+subject")
    pv = s.post(f"{API}/person-invites/access-preview", json={"person_ids": ["sv_p1", "sv_p2", "sv_p3", "sv_p6", "sv_other"]}).json()
    ids = {x["id"]: x["reason"] for x in pv["recipients"]}
    ok(ids == {"sv_p1": None, "sv_p2": "Partecipazione non confermata", "sv_p3": "Partecipazione non confermata", "sv_p6": "Partecipazione non confermata"}, f"selection preview {ids}")
    r = s.post(f"{API}/person-invites/access-send", json={"person_ids": ["sv_p1", "sv_p2", "sv_other"], "evento_id": EV}).json()
    print("send:", r)
    sent = [x["id"] for x in r["sent"]]
    ok("sv_p2" not in sent and "sv_other" not in sent, "unconfirmed / other tenant never sent")
    p1 = db.persons.find_one({"id": "sv_p1"})
    if sent == ["sv_p1"]:
        ok(p1.get("last_invite_at") and p1["invite_status"] == "invito_inviato", "sent -> status+timestamp")
        r2 = s.post(f"{API}/person-invites/access-send", json={"person_ids": ["sv_p1"], "evento_id": EV}).json()
        ok(not r2["sent"] and r2["skipped"][0]["reason"] == "Email già inviata", f"duplicate blocked {r2['skipped']}")
        r3 = s.post(f"{API}/person-invites/access-preview", json={"person_ids": ["sv_p1"], "resend": True}).json()
        ok(r3["recipients"][0]["reason"] == "Email già inviata nelle ultime 24 ore", "resend within 24h needs force")
        r4 = s.post(f"{API}/person-invites/access-preview", json={"person_ids": ["sv_p1"], "resend": True, "force": True}).json()
        ok(r4["to_send"] == 1, "explicit single resend allowed")
        pv = s.post(f"{API}/person-invites/access-preview", json={"all_unsent": True, "evento_id": EV}).json()
        ok([x["id"] for x in pv["recipients"] if not x["reason"]] == ["sv_p4"], "all_unsent excludes already sent")
        ok({x["id"]: x for x in s.get(f"{API}/persons-enriched").json()}["sv_p1"]["access_status"] == "email_inviata", "access status email_inviata")
    else:
        ok(not p1.get("last_invite_at") and p1["invite_status"] == "non_invitato", "failed send (provider) -> NOT marked as sent")
    db.users.update_one({"person_id": "sv_p1"}, {"$set": {"last_login_at": now}})
    if db.users.find_one({"person_id": "sv_p1"}):
        ok({x["id"]: x for x in s.get(f"{API}/persons-enriched").json()}["sv_p1"]["access_status"] == "accesso_effettuato", "access status accesso_effettuato")


{"seed": seed, "test": test, "clean": clean}[sys.argv[1]]()
print("done", sys.argv[1])
