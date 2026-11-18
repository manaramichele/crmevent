# Cleanup: removes TEST_Pdf Org (given id) and TEST_PdfX orgs created by test_people_pdf_export.py
import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
ids = ["4081951563e7415f9b38f9ff48e50bc0"] + [o["id"] for o in db.organizations.find({"nome": {"$regex": "^TEST_PdfX "}}, {"id": 1})]
ids += [o["id"] for o in db.organizations.find({"name": {"$regex": "^TEST_PdfX "}}, {"id": 1})]
ids = list(set(ids))
print("orgs:", ids)
for c in db.list_collection_names():
    if c == "organizations":
        continue
    n = db[c].delete_many({"org_id": {"$in": ids}}).deleted_count
    if n:
        print(c, n)
emails = ["test_pdf_1794985461@example.com"]
print("users by email:", db.users.delete_many({"$or": [{"email": {"$in": emails}}, {"email": {"$regex": "^test_pdfx_\\d+@example.com$"}}]}).deleted_count)
print("orgs:", db.organizations.delete_many({"id": {"$in": ids}}).deleted_count)
