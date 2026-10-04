"""READ-ONLY audit of CRMEvent social data. Nothing is written or modified.
Never prints the OAuth token value; only presence + validity signals."""
from pymongo import MongoClient
from datetime import datetime, timezone

PLATFORM = "__platform__"
env = {}
for l in open("/app/backend/.env"):
    if "=" in l and not l.strip().startswith("#"):
        k, v = l.strip().split("=", 1); env[k] = v.strip().strip('"').strip("'")
db = MongoClient(env["MONGO_URL"])[env["DB_NAME"]]

COLLS = ["social_settings", "social_posts", "social_media", "social_ai_generations",
         "social_publish_logs", "social_calendar", "social_accounts"]

def org_name(org_id):
    if org_id == PLATFORM:
        return "Marketing CRMEvent — Piattaforma"
    o = db.organizations.find_one({"id": org_id}, {"_id": 0, "name": 1})
    return (o or {}).get("name", "(sconosciuta)")

print("="*70)
print("AUDIT READ-ONLY — Dati Social CRMEvent")
print("="*70)

# 1) Instagram account @crmevent
print("\n[1] ACCOUNT INSTAGRAM")
ig_accts = list(db.social_accounts.find({"platform": "instagram"}, {"_id": 0}))
if not ig_accts:
    print("  Nessun account Instagram trovato in social_accounts.")
for a in ig_accts:
    uname = a.get("username") or a.get("ig_username") or "(username assente)"
    oid = a.get("org_id")
    tok = a.get("access_token") or a.get("token") or a.get("long_lived_token")
    exp = a.get("token_expires_at") or a.get("expires_at") or a.get("token_expiry")
    print(f"  username: @{uname}")
    print(f"  org_id: {oid}  -> org: {org_name(oid)}")
    print(f"  scope field: {a.get('scope')}")
    print(f"  ig_user_id presente: {bool(a.get('ig_user_id'))}")
    print(f"  TOKEN OAuth presente: {bool(tok)}  (lunghezza: {len(tok) if tok else 0})")
    if exp:
        try:
            exp_dt = exp if isinstance(exp, datetime) else datetime.fromisoformat(str(exp).replace('Z','+00:00'))
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            valid = exp_dt > datetime.now(timezone.utc)
            print(f"  token_expires_at: {exp_dt.isoformat()}  -> {'VALIDO' if valid else 'SCADUTO'}")
        except Exception as e:
            print(f"  token_expires_at (raw): {exp}  (parse err: {e})")
    else:
        print("  token_expires_at: non impostato")
    print(f"  account_status/connected: {a.get('status') or a.get('connected')}")
    print("  ---")

# 2) social_settings brand CRMEvent
print("\n[2] SOCIAL_SETTINGS (brand)")
for s in db.social_settings.find({}, {"_id": 0, "org_id": 1, "brand_name": 1, "autopilot": 1, "autopilot_enabled": 1, "auto_publish": 1}):
    oid = s.get("org_id")
    print(f"  brand_name: {s.get('brand_name')!r}  org_id: {oid} -> {org_name(oid)}")
    print(f"    autopilot: {s.get('autopilot')} | autopilot_enabled: {s.get('autopilot_enabled')} | auto_publish: {s.get('auto_publish')}")

# 3) Counts per collection, grouped by org_id
print("\n[3] CONTEGGI PER COLLEZIONE (per org_id)")
for coll in COLLS:
    total = db[coll].count_documents({})
    print(f"\n  {coll}: TOTALE = {total}")
    pipeline = [{"$group": {"_id": "$org_id", "n": {"$sum": 1}}}, {"$sort": {"n": -1}}]
    for g in db[coll].aggregate(pipeline):
        oid = g["_id"]
        print(f"    - org_id={oid} ({org_name(oid)}): {g['n']}")

# 4) files referenced by social_media (per org)
print("\n[4] FILES referenziati da social_media")
media = list(db.social_media.find({}, {"_id": 0, "org_id": 1, "file_id": 1}))
by_org = {}
for m in media:
    by_org.setdefault(m.get("org_id"), []).append(m.get("file_id"))
for oid, fids in by_org.items():
    fids = [f for f in fids if f]
    n_files = db.files.count_documents({"id": {"$in": fids}}) if fids else 0
    print(f"  org_id={oid} ({org_name(oid)}): media={len(fids)} -> files trovati={n_files}")

# 5) CRMEvent data mixed under non-platform orgs?
print("\n[5] DATI CRMEVENT IN SCOPE ERRATO?")
crm_orgs = set(s["org_id"] for s in db.social_settings.find({"brand_name": "CRMEvent"}, {"_id": 0, "org_id": 1}))
print(f"  org_id con brand_name='CRMEvent': {crm_orgs or '{}'}")
non_platform_crm = [o for o in crm_orgs if o != PLATFORM]
if non_platform_crm:
    print(f"  ⚠ CRMEvent presente sotto org NON-platform: {[(o, org_name(o)) for o in non_platform_crm]}")
else:
    print("  Nessun brand CRMEvent fuori dallo scope platform (in social_settings).")

# Any Instagram @crmevent account outside platform?
for a in ig_accts:
    uname = (a.get("username") or a.get("ig_username") or "").lower()
    if uname == "crmevent" and a.get("org_id") != PLATFORM:
        print(f"  ⚠ Account @crmevent sotto org {a.get('org_id')} ({org_name(a.get('org_id'))}) invece di __platform__")

# What is 'Trio Events' org id + its social footprint
print("\n[6] TRIO EVENTS — impronta social")
trio = db.organizations.find_one({"name": {"$regex": "trio", "$options": "i"}}, {"_id": 0, "id": 1, "name": 1})
if trio:
    tid = trio["id"]
    print(f"  Trio Events org_id: {tid} (name={trio['name']!r})")
    for coll in COLLS:
        print(f"    {coll}: {db[coll].count_documents({'org_id': tid})}")
else:
    print("  Nessuna organizzazione 'Trio Events' trovata.")

print("\n" + "="*70)
print("FINE AUDIT READ-ONLY — nessun dato modificato.")
print("="*70)
