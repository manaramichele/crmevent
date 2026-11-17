"""Dati di prova Control Room Fase 2 (org TEST_CR A/B). Uso: python scripts/seed_cr_test.py"""
import asyncio
import os
import uuid
from datetime import datetime, timezone

import httpx
from dotenv import dotenv_values
from motor.motor_asyncio import AsyncIOMotorClient

ENV = dotenv_values("/app/backend/.env")
API = "http://localhost:8001/api"
PWD = "TestCR2026!"
GPX = ('<?xml version="1.0"?><gpx version="1.1" creator="t" xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>'
       + "".join(f'<trkpt lat="{45.4642 + i * 0.0009:.6f}" lon="{9.1900 + i * 0.0006:.6f}"></trkpt>' for i in range(120)) + "</trkseg></trk></gpx>")


async def org(c, tag):
    email = f"test_cr_{tag}@crmevent-test.it"
    r = await c.post(f"{API}/auth/login", json={"email": email, "password": PWD})
    if r.status_code != 200:
        r = await c.post(f"{API}/auth/register-organization", json={"nome": "Test", "cognome": tag.upper(), "email": email, "password": PWD,
                                                                   "org_name": f"TEST_CR Org {tag.upper()}", "accept_terms": True,
                                                                   "telefono": f"+39 333 12345{ord(tag) % 10}{ord(tag) % 7}"})
    r.raise_for_status()
    r = await c.post(f"{API}/auth/login", json={"email": email, "password": PWD})
    c.headers["Authorization"] = f"Bearer {r.cookies.get('access_token')}"
    return email


async def main():
    db = AsyncIOMotorClient(os.environ.get("MONGO_URL") or ENV["MONGO_URL"])[ENV["DB_NAME"]]
    out = {}
    for tag in ("a", "b", "c"):
        async with httpx.AsyncClient(timeout=30) as c:
            email = await org(c, tag)
            u = await db.users.find_one({"email": email}, {"_id": 0})
            oid = u["org_id"]
            ev = await db.events.find_one({"org_id": oid, "nome": f"TEST_CR Gara {tag.upper()}"}, {"_id": 0})
            if not ev and tag != "c":
                r = await c.post(f"{API}/events", json={"nome": f"TEST_CR Gara {tag.upper()}", "data_inizio": "2026-12-06", "citta": "Milano"})
                r.raise_for_status()
                ev = r.json()
                r2 = await c.post(f"{API}/events", json={"nome": f"TEST_CR Non attivo {tag.upper()}", "data_inizio": "2026-12-20"})
                r2.raise_for_status()
                if tag == "a":
                    up = await c.post(f"{API}/upload", files={"file": ("percorso.gpx", GPX.encode(), "application/gpx+xml")})
                    up.raise_for_status()
                    await c.post(f"{API}/maps", json={"evento_id": ev["id"], "nome": "Percorso 10K", "gpx_url": up.json()["url"]})
                    for i, n in enumerate(["Mario", "Lucia", "Paolo", "Giulia"]):
                        p = (await c.post(f"{API}/persons", json={"nome": n, "cognome": "TEST_CR", "cellulare": f"+39 333 000 00{i}"})).json()
                        await c.post(f"{API}/staff", json={"persona_id": p["id"], "evento_id": ev["id"], "categoria": "volontario", "stato": "confermato"})
            if ev:
                await db.controlroom_purchases.update_one({"org_id": oid, "event_id": ev["id"], "status": "active"}, {"$setOnInsert": {
                    "id": uuid.uuid4().hex, "org_id": oid, "event_id": ev["id"], "event_name": ev["nome"], "status": "active", "amount_net": 119.0,
                    "created_by": "seed_test", "created_at": datetime.now(timezone.utc).isoformat(), "activated_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
            out[tag] = (email, oid, (ev or {}).get("id"), u["user_id"])
    # utente C = collaboratore (sola lettura) nell'organizzazione A
    await db.memberships.update_one({"user_id": out["c"][3], "org_id": out["a"][1]}, {"$set": {"user_id": out["c"][3], "org_id": out["a"][1], "role": "collaboratore",
                                                                                         "active": True, "created_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
    for k, v in out.items():
        print(k, v)


asyncio.run(main())
