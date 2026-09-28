"""One-off (preview): migrate CRMEvent official social data to the platform scope.
Source org = the org whose social_settings.brand_name == 'CRMEvent'. Target = __platform__.
Moves: social_settings, social_posts, social_media, social_ai_generations,
social_publish_logs, social_calendar, social_accounts, and the files referenced by media.
Idempotent-ish: safe to re-run (matches by source org only)."""
from pymongo import MongoClient

PLATFORM = "__platform__"
env = {}
for l in open("/app/backend/.env"):
    if "=" in l and not l.strip().startswith("#"):
        k, v = l.strip().split("=", 1); env[k] = v.strip().strip('"').strip("'")
db = MongoClient(env["MONGO_URL"])[env["DB_NAME"]]

src = db.social_settings.find_one({"brand_name": "CRMEvent"}, {"_id": 0, "org_id": 1})
if not src:
    print("Nessuna org con brand CRMEvent trovata. Stop."); raise SystemExit(0)
SRC = src["org_id"]
print("Source org (CRMEvent):", SRC, "-> target:", PLATFORM)

# Move referenced files first (so downloads keep working under platform scope).
media = list(db.social_media.find({"org_id": SRC}, {"_id": 0, "file_id": 1}))
file_ids = [m["file_id"] for m in media if m.get("file_id")]
rf = db.files.update_many({"org_id": SRC, "id": {"$in": file_ids}}, {"$set": {"org_id": PLATFORM}})
print("files migrati:", rf.modified_count)

for coll in ["social_settings", "social_posts", "social_media", "social_ai_generations",
             "social_publish_logs", "social_calendar", "social_accounts"]:
    r = db[coll].update_many({"org_id": SRC}, {"$set": {"org_id": PLATFORM, "scope": "platform"}})
    print(f"{coll}: {r.modified_count} documenti migrati")

print("\nVERIFICA post-migrazione:")
print("  settings platform brand:", (db.social_settings.find_one({"org_id": PLATFORM}, {"_id": 0, "brand_name": 1}) or {}))
print("  posts platform:", db.social_posts.count_documents({"org_id": PLATFORM}))
print("  media platform:", db.social_media.count_documents({"org_id": PLATFORM}))
print("  october plan org:", (db.social_posts.find_one({"plan_id": "acceeefda6f742b0918448bf53bcd489"}, {"_id": 0, "org_id": 1}) or {}))
print("DONE")
