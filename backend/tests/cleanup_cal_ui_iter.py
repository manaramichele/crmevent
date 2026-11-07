# Cleanup of data created by the Calendario Italia UI test run (by explicit names created in this run)
import os, asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

EV_NAMES = ["TEST_UI Corsa Zeta", "TEST_IMP Corri Omega", "TEST_IMP Trail Sigma"]
ORG_NAMES = ["TEST_IMP ASD Omega", "TEST_UI Org Merge"]
IMPORT_FILES = ["TEST_import.csv", "TEST_dup.csv"]


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    evs = await db.cal_events.find({"nome": {"$in": EV_NAMES}}, {"_id": 0, "id": 1, "nome": 1}).to_list(100)
    eids = [e["id"] for e in evs]
    orgs = await db.cal_organizers.find({"nome": {"$in": ORG_NAMES}}, {"_id": 0, "id": 1, "nome": 1}).to_list(100)
    oids = [o["id"] for o in orgs]
    print("events", evs, "orgs", orgs)
    if eids:
        print("dups", (await db.cal_duplicates.delete_many({"$or": [{"a": {"$in": eids}}, {"b": {"$in": eids}}, {"event_a": {"$in": eids}}, {"event_b": {"$in": eids}}]})).deleted_count)
        print("conf", (await db.cal_conflicts.delete_many({"event_id": {"$in": eids}})).deleted_count)
        print("hist", (await db.cal_history.delete_many({"$or": [{"event_id": {"$in": eids}}, {"entity_id": {"$in": eids}}]})).deleted_count)
        print("ev", (await db.cal_events.delete_many({"id": {"$in": eids}})).deleted_count)
    if oids:
        print("ohist", (await db.cal_history.delete_many({"$or": [{"organizer_id": {"$in": oids}}, {"entity_id": {"$in": oids}}]})).deleted_count)
        print("org", (await db.cal_organizers.delete_many({"id": {"$in": oids}})).deleted_count)
    print("imp", (await db.cal_imports.delete_many({"file": {"$in": IMPORT_FILES}})).deleted_count)

asyncio.run(main())
