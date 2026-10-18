# UI test data for Marketplace Stripe/video UI. Usage: python ui_mkt_setup.py setup | cleanup
import json
import sys
import time
import uuid

import requests
import stripe
from pymongo import MongoClient

BASE = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0].rstrip("/")
API = f"{BASE}/api"
ENV = {k: v.strip().strip('"') for k, v in (l.split("=", 1) for l in open("/app/backend/.env").read().splitlines() if "=" in l)}
DB = MongoClient(ENV["MONGO_URL"])[ENV["DB_NAME"]]
stripe.api_key = ENV["STRIPE_SECRET_KEY"]
F = "/tmp/mkt_ui.json"

if sys.argv[1] == "setup":
    ts = str(int(time.time()))
    sa = requests.Session()
    assert sa.post(f"{API}/auth/login", json={"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"}).status_code == 200
    s = requests.Session()
    email = f"test_mktui_{ts}@example.com"
    r = s.post(f"{API}/auth/register-organization", json={"nome": "Test", "cognome": "UI", "email": email, "password": "Password123!",
                                                          "org_name": f"TEST_MKTUI {ts}", "telefono": "+393471234567", "accept_terms": True})
    assert r.status_code in (200, 201), r.text
    org = s.get(f"{API}/auth/me").json()["org_id"]
    s.put(f"{API}/account/billing", json={"tipo": "azienda", "ragione_sociale": "TEST_UI Srl", "indirizzo": "Via Roma 1", "cap": "20100", "citta": "Milano",
                                          "provincia": "MI", "paese": "IT", "partita_iva": "12345678901", "codice_sdi": "0000000"})
    DB.organizations.update_one({"id": org}, {"$set": {"saas.trial_end": "2020-01-01T00:00:00+00:00"}})
    svcs = {}
    for k, price, pt, extra in [("paid", 9, "monthly", {"video_url": "https://youtu.be/dQw4w9WgXcQ", "video_title": "TEST Tutorial video"}),
                                ("free", 0, "monthly", {}), ("act", 7, "monthly", {"video_url": "https://youtube.com/shorts/abcdefghijk"})]:
        body = {"name": f"TEST_UI_{k}_{ts}", "description": "Servizio di test UI", "category": "Altro", "price": price, "price_type": pt,
                "status": "available", "visible": True, "purchasable": True, "tech_ready": True, "scope": "org", "sort": 1, **extra}
        rr = sa.post(f"{API}/platform/marketplace/services", json=body)
        assert rr.status_code == 200, rr.text
        svcs[k] = rr.json()
    DB.marketplace_purchases.insert_one({"id": uuid.uuid4().hex, "org_id": org, "service_id": svcs["act"]["id"], "service_name": svcs["act"]["name"],
                                         "status": "active", "source": "stripe", "price": 7.0, "price_type": "monthly", "stripe_session_id": "cs_fake",
                                         "stripe_subscription_id": "sub_fake_ui", "activated_at": "2026-01-01T00:00:00+00:00",
                                         "current_period_end": "2026-02-15T00:00:00+00:00", "created_at": "2026-01-01T00:00:00+00:00", "history": []})
    json.dump({"email": email, "org": org, "svcs": {k: {"id": v["id"], "key": v["key"], "name": v["name"]} for k, v in svcs.items()}}, open(F, "w"))
    print(json.dumps(json.load(open(F))))
else:
    st = json.load(open(F))
    ids = [v["id"] for v in st["svcs"].values()]
    for sid in ids:
        for v in ((DB.marketplace_services.find_one({"id": sid}) or {}).get("stripe_prices") or {}).values():
            try:
                stripe.Price.modify(v["price_id"], active=False)
                stripe.Product.modify(v["product_id"], active=False)
            except Exception:
                pass
    for c in DB.list_collection_names():
        if c != "audit_logs":
            DB[c].delete_many({"org_id": st["org"]})
    DB.users.delete_many({"email": st["email"]})
    DB.organizations.delete_many({"id": st["org"]})
    DB.marketplace_services.delete_many({"id": {"$in": ids}})
    DB.marketplace_purchases.delete_many({"service_id": {"$in": ids}})
    print("cleaned")
