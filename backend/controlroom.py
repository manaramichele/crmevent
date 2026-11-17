"""Control Room (Fase 1): acquisto per singolo evento a 119 € + IVA via Stripe, attivazione solo dopo pagamento confermato, rimborsi, verifica backend del diritto."""
import uuid
from datetime import datetime, timezone
from typing import Optional

import stripe as stripe_sdk
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import controlroom_ops

PRICE_NET = 119.00
SERVICE_KEY = "control-room"
LINE_NAME = "CONTROL ROOM — 119,00 € / EVENTO"


class CheckoutIn(BaseModel):
    origin_url: str


def _now():
    return datetime.now(timezone.utc).isoformat()


def build(db, deps):
    admin, member, sa = deps["require_admin"], deps["get_current_user"], deps["require_superadmin"]
    r = APIRouter(prefix="/api")

    async def ensure():
        await db.controlroom_purchases.create_index([("org_id", 1), ("event_id", 1)])
        await db.controlroom_purchases.create_index("stripe_session_id", sparse=True)
        for c in ("cr_settings", "cr_sectors", "cr_posts", "cr_resources", "cr_interventions", "cr_log"):
            await db[c].create_index([("org_id", 1), ("event_id", 1)])
        await db.marketplace_services.update_one({"key": SERVICE_KEY}, {"$setOnInsert": {
            "id": uuid.uuid4().hex, "key": SERVICE_KEY, "name": "Control Room", "activation": "controlroom", "billing_method": "stripe", "category": "Logistica",
            "description": "Centrale operativa digitale per coordinare volontari, postazioni, mezzi di soccorso e interventi durante la manifestazione.",
            "icon": "RadioTower", "price": PRICE_NET, "price_type": "per_event", "purchasable": True, "scope": "event", "sort": 7, "status": "available",
            "tech_ready": True, "visible": True, "created_at": _now()}}, upsert=True)
        await db.marketplace_services.update_one({"key": SERVICE_KEY}, {"$set": {"price": PRICE_NET, "price_type": "per_event"}})

    async def is_active(org_id: str, event_id: str) -> bool:
        return bool(await db.controlroom_purchases.find_one({"org_id": org_id, "event_id": event_id, "status": "active"}, {"_id": 1}))

    async def require_active(org_id: str, event_id: str):
        if not await is_active(org_id, event_id):
            raise HTTPException(status_code=402, detail="Control Room non è attiva per questo evento")

    def _pub(p):
        return {k: p.get(k) for k in ("id", "event_id", "event_name", "status", "amount_net", "created_at", "activated_at", "refunded_at", "created_by")} if p else None

    @r.get("/controlroom/events")
    async def events(user: dict = Depends(member)):
        org = user.get("org_id")
        if not org:
            raise HTTPException(status_code=403, detail="Nessuna organizzazione attiva")
        evs = await db.events.find({"org_id": org}, {"_id": 0, "id": 1, "nome": 1, "data_inizio": 1, "citta": 1}).sort("data_inizio", -1).to_list(500)
        act = {p["event_id"]: p for p in await db.controlroom_purchases.find({"org_id": org, "status": {"$in": ["active", "pending"]}}, {"_id": 0}).to_list(1000)}
        return {"price_net": PRICE_NET, "can_purchase": user.get("org_role") in ("admin_org", "superadmin"),
                "events": [{**e, "active": (act.get(e["id"]) or {}).get("status") == "active", "pending": (act.get(e["id"]) or {}).get("status") == "pending"} for e in evs]}

    @r.get("/controlroom/events/{eid}/status")
    async def status(eid: str, user: dict = Depends(member)):
        ev = await db.events.find_one({"id": eid, "org_id": user.get("org_id")}, {"_id": 0, "id": 1, "nome": 1})
        if not ev:
            raise HTTPException(status_code=404, detail="Evento non trovato")
        p = await db.controlroom_purchases.find_one({"org_id": user["org_id"], "event_id": eid, "status": "active"}, {"_id": 0})
        return {"event": ev, "active": bool(p), "purchase": _pub(p)}

    @r.post("/controlroom/events/{eid}/checkout")
    async def checkout(eid: str, body: CheckoutIn, user: dict = Depends(admin)):
        org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0})
        ev = await db.events.find_one({"id": eid, "org_id": org["id"]}, {"_id": 0, "id": 1, "nome": 1})
        if not ev:
            raise HTTPException(status_code=404, detail="Evento non trovato")
        if await is_active(org["id"], eid):
            raise HTTPException(status_code=409, detail="Control Room è già attiva per questo evento")
        missing = deps["billing_missing"](org.get("billing") or {})
        if missing:
            raise HTTPException(status_code=400, detail="Completa i dati di fatturazione: " + ", ".join(missing))
        await db.controlroom_purchases.update_many({"org_id": org["id"], "event_id": eid, "status": "pending"}, {"$set": {"status": "expired", "updated_at": _now()}})
        pid = uuid.uuid4().hex
        md = {"kind": "controlroom", "purchase_id": pid, "org_id": org["id"], "event_id": eid}
        origin = body.origin_url.rstrip("/")
        try:
            sess = stripe_sdk.checkout.Session.create(
                mode="payment", customer=await deps["ensure_customer"](org, user), locale="it", client_reference_id=org["id"], metadata=md,
                payment_intent_data={"metadata": md}, managed_payments={"enabled": False},
                invoice_creation={"enabled": True, "invoice_data": {"metadata": md}}, adaptive_pricing={"enabled": False},
                line_items=[{"price_data": {"currency": "eur", "unit_amount": int(PRICE_NET * 100), "tax_behavior": "exclusive",
                                            "product_data": {"name": LINE_NAME, "tax_code": "txcd_10103001", "description": f"Evento: {ev['nome']}"[:300]}},
                             "quantity": 1, "tax_rates": [deps["tax_rate_id"]()]}],
                success_url=f"{origin}/control-room?event={eid}&session_id={{CHECKOUT_SESSION_ID}}", cancel_url=f"{origin}/control-room?event={eid}&canceled=1")
        except stripe_sdk.error.StripeError as e:
            deps["logger"].error(f"controlroom checkout: {e}")
            raise HTTPException(status_code=502, detail="Non è stato possibile avviare il pagamento. Riprova più tardi.")
        await db.controlroom_purchases.insert_one({"id": pid, "org_id": org["id"], "event_id": eid, "event_name": ev["nome"], "status": "pending", "amount_net": PRICE_NET,
                                                   "stripe_session_id": sess.id, "stripe_mode": deps["stripe_mode"], "created_by": user.get("email"), "created_at": _now(),
                                                   "history": [{"at": _now(), "status": "pending", "by": user.get("email")}]})
        return {"checkout_url": sess.url}

    async def _activate(sess) -> Optional[dict]:
        md = sess.get("metadata") or {}
        p = await db.controlroom_purchases.find_one({"id": md.get("purchase_id")}, {"_id": 0}) if md.get("kind") == "controlroom" else None
        if not p or p["org_id"] != md.get("org_id") or p["event_id"] != md.get("event_id"):
            return None
        if sess.get("status") != "complete" or sess.get("payment_status") != "paid":
            return p
        if await db.controlroom_purchases.find_one({"org_id": p["org_id"], "event_id": p["event_id"], "status": "active", "id": {"$ne": p["id"]}}):
            await db.controlroom_purchases.update_one({"id": p["id"], "status": {"$in": ["pending", "expired"]}}, {"$set": {"status": "duplicate_paid", "payment_intent": sess.get("payment_intent"), "updated_at": _now()}})
            return await db.controlroom_purchases.find_one({"id": p["id"]}, {"_id": 0})
        res = await db.controlroom_purchases.update_one({"id": p["id"], "status": {"$in": ["pending", "expired", "failed"]}},
                                                        {"$set": {"status": "active", "activated_at": _now(), "payment_intent": sess.get("payment_intent"),
                                                                  "amount_total": (sess.get("amount_total") or 0) / 100},
                                                         "$push": {"history": {"at": _now(), "status": "active", "by": "stripe"}}})
        if res.modified_count:
            await deps["audit"]({"user_id": "stripe", "email": "stripe", "role": "system"}, "controlroom_paid", org_id=p["org_id"], detail=f"{p['event_name']} · {PRICE_NET} € + IVA")
        return await db.controlroom_purchases.find_one({"id": p["id"]}, {"_id": 0})

    @r.get("/controlroom/confirmation")
    async def confirmation(session_id: str, user: dict = Depends(member)):
        try:
            sess = stripe_sdk.checkout.Session.retrieve(session_id)
        except stripe_sdk.error.StripeError:
            raise HTTPException(status_code=404, detail="Sessione di pagamento non trovata")
        if (sess.get("metadata") or {}).get("org_id") != user.get("org_id"):
            raise HTTPException(status_code=403, detail="Sessione non associata all'organizzazione")
        return {"status": (await _activate(sess) or {}).get("status")}

    async def handle_webhook(t: str, obj) -> bool:
        if (obj.get("metadata") or {}).get("kind") != "controlroom":
            return False
        if t in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
            await _activate(obj)
        elif t in ("checkout.session.expired", "checkout.session.async_payment_failed"):
            await db.controlroom_purchases.update_one({"id": obj["metadata"].get("purchase_id"), "status": "pending"},
                                                      {"$set": {"status": "failed" if t.endswith("failed") else "expired", "updated_at": _now()}})
        return True

    async def on_refund(charge) -> bool:
        pi = charge.get("payment_intent")
        p = await db.controlroom_purchases.find_one({"payment_intent": pi, "status": {"$in": ["active", "duplicate_paid"]}}, {"_id": 0}) if pi else None
        if not p or not charge.get("refunded"):
            return False
        await db.controlroom_purchases.update_one({"id": p["id"]}, {"$set": {"status": "refunded", "refunded_at": _now()},
                                                                    "$push": {"history": {"at": _now(), "status": "refunded", "by": "stripe"}}})
        await deps["audit"]({"user_id": "stripe", "email": "stripe", "role": "system"}, "controlroom_refunded", org_id=p["org_id"], detail=p["event_name"])
        return True

    @r.get("/platform/controlroom/purchases")
    async def sa_list(_: dict = Depends(sa)):
        return await db.controlroom_purchases.find({}, {"_id": 0, "history": 0}).sort("created_at", -1).to_list(500)

    controlroom_ops.attach(r, db, deps, require_active)

    return {"router": r, "ensure": ensure, "handle_webhook": handle_webhook, "on_refund": on_refund, "require_active": require_active}
