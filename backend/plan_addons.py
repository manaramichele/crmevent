"""Moduli annuali aggiunti all'abbonamento principale (es. Gestione Associazione Sportiva): stessa sottoscrizione Stripe, prorata, rinnovo unico."""
import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Optional

import stripe as stripe_sdk
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
ADDON_KEY = "gestione-societa"
ADDON_NAME = "Gestione Associazione Sportiva"
ADDON_NOTE = ("L'importo del primo acquisto viene calcolato automaticamente in base alla scadenza del tuo abbonamento CRMEvent. "
              "Al rinnovo pagherai il prezzo annuale completo insieme al tuo piano principale.")
LIVE = ("active", "past_due")


def _now():
    return datetime.now(timezone.utc)


def _parse(s):
    try:
        d = datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def prorate(price: float, start: datetime, end: datetime, now: datetime) -> dict:
    period = max(1, (end.date() - start.date()).days)
    left = max(0, min(period, math.ceil((end - now).total_seconds() / 86400)))
    return {"period_days": period, "days_left": left, "amount": round(price * left / period, 2)}


class BuyIn(BaseModel):
    confirm_amount: float


def build(db, deps: dict):
    r = APIRouter(prefix="/api")
    require_admin = deps["require_admin"]

    def _billing_admin(user):
        if not (user.get("perm") or {}).get("admin") and user.get("role") != "superadmin":
            raise HTTPException(status_code=403, detail="Solo l'Admin Organizzazione può gestire gli acquisti")

    async def _svc():
        svc = await db.marketplace_services.find_one({"key": ADDON_KEY}, {"_id": 0})
        if not svc:
            raise HTTPException(status_code=404, detail="Modulo non trovato")
        return svc

    async def _purchase(org_id):
        return await db.marketplace_purchases.find_one({"org_id": org_id, "service_id": (await _svc())["id"], "source": "plan_addon",
                                                         "status": {"$in": list(LIVE)}}, {"_id": 0})

    async def _addon_price(svc) -> str:
        mode, cents = deps["stripe_mode"], int(round(float(svc["price"]) * 100))
        cur = (svc.get("stripe_prices") or {}).get(mode) or {}
        if cur.get("price_id") and cur.get("amount_cents") == cents and cur.get("interval") == "year" and cur.get("kind") == "plan_addon":
            return cur["price_id"]
        meta = {"kind": "plan_addon", "service_id": svc["id"], "service_key": ADDON_KEY}
        prod = cur.get("product_id") or stripe_sdk.Product.create(name=f"CRMEvent · {svc['name']}", tax_code="txcd_10103001", metadata=meta).id
        price = stripe_sdk.Price.create(product=prod, currency="eur", unit_amount=cents, recurring={"interval": "year"}, metadata=meta)
        await db.marketplace_services.update_one({"id": svc["id"]}, {"$set": {f"stripe_prices.{mode}": {
            "product_id": prod, "price_id": price.id, "amount_cents": cents, "interval": "year", "kind": "plan_addon", "source": "auto",
            "updated_at": _now().isoformat()}}})
        return price.id

    def _block(s: dict) -> Optional[str]:
        if not s.get("stripe_subscription_id") or not s.get("plan"):
            return "Per acquistare il modulo serve un abbonamento Bronze, Silver o Gold a pagamento."
        if s.get("stripe_status") == "trialing":
            return "Il modulo si può acquistare al termine della prova gratuita, con un abbonamento annuale attivo."
        if s.get("stripe_status") != "active":
            return "L'abbonamento principale non è attivo o ha un pagamento in sospeso."
        if s.get("billing_cycle") != "yearly":
            return "Il modulo è disponibile solo con un abbonamento annuale: passa al piano annuale per acquistarlo."
        if s.get("cancel_at_period_end"):
            return "Il tuo abbonamento principale non si rinnoverà: riattivalo per acquistare il modulo."
        if not (_parse(s.get("current_period_start")) and _parse(s.get("current_period_end"))):
            return "Data di rinnovo dell'abbonamento non disponibile."
        return None

    async def _quote(user, with_stripe: bool) -> dict:
        svc = await _svc()
        org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0, "saas": 1})
        s = (org or {}).get("saas") or {}
        price = float(svc.get("price") or 0)
        out = {"service_id": svc["id"], "name": svc["name"], "annual_price": price, "purchasable": bool(svc.get("purchasable")) and svc.get("status") == "available",
               "note": ADDON_NOTE, "plan": s.get("plan"), "billing_cycle": s.get("billing_cycle"), "renewal_date": s.get("current_period_end"),
               "blocked": _block(s), "purchase": await _purchase(user["org_id"])}
        if out["blocked"]:
            return out
        out.update(prorate(price, _parse(s["current_period_start"]), _parse(s["current_period_end"]), _now()))
        if with_stripe and out["purchasable"] and not out["purchase"]:
            sub = stripe_sdk.Subscription.retrieve(s["stripe_subscription_id"])
            pv = stripe_sdk.Invoice.create_preview(customer=sub["customer"], subscription=sub["id"], subscription_details={
                "items": [{"price": await _addon_price(svc)}], "proration_behavior": "always_invoice"})
            out["amount_due"] = round((pv.get("amount_due") or 0) / 100, 2)
            out["amount_net"] = round((pv.get("subtotal") or 0) / 100, 2)
        return out

    @r.get("/marketplace/plan-addon/quote")
    async def quote(user: dict = Depends(require_admin)):
        await _expire(user["org_id"])
        return await _quote(user, True)

    @r.post("/marketplace/plan-addon/purchase")
    async def purchase(body: BuyIn, user: dict = Depends(require_admin)):
        _billing_admin(user)
        q = await _quote(user, True)
        if not q["purchasable"]:
            raise HTTPException(status_code=400, detail="L'acquisto del modulo non è ancora disponibile")
        if q["purchase"]:
            raise HTTPException(status_code=409, detail="Il modulo è già attivo per la tua organizzazione")
        if q["blocked"]:
            raise HTTPException(status_code=400, detail=q["blocked"])
        if abs(float(body.confirm_amount) - q["amount_due"]) > 0.01:
            raise HTTPException(status_code=409, detail={"code": "amount_changed", "amount_due": q["amount_due"], "message": "L'importo è cambiato: conferma di nuovo"})
        svc = await _svc()
        org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0})
        missing = deps["billing_missing"](org.get("billing") or {})
        if missing:
            raise HTTPException(status_code=400, detail="Completa i dati di fatturazione: " + ", ".join(missing))
        price_id = await _addon_price(svc)
        lock = await db.marketplace_purchases.update_one({"id": f"lock-{user['org_id']}-{ADDON_KEY}"}, {"$setOnInsert": {"at": _now().isoformat()}}, upsert=True)
        if not lock.upserted_id:
            raise HTTPException(status_code=409, detail="Acquisto già in corso")
        try:
            sub = stripe_sdk.Subscription.modify(org["saas"]["stripe_subscription_id"], items=[{"price": price_id}],
                                                 proration_behavior="always_invoice", payment_behavior="error_if_incomplete")
        except stripe_sdk.error.StripeError as e:
            logger.warning(f"plan addon purchase failed: {e}")
            raise HTTPException(status_code=402, detail="Pagamento non riuscito: il modulo non è stato attivato e non è stato addebitato nulla.")
        finally:
            await db.marketplace_purchases.delete_one({"id": f"lock-{user['org_id']}-{ADDON_KEY}"})
        item = next((i for i in sub["items"]["data"] if i["price"]["id"] == price_id), None)
        cpe = sub.get("current_period_end") or (item or {}).get("current_period_end")
        doc = {"id": uuid.uuid4().hex, "org_id": org["id"], "service_id": svc["id"], "service_name": svc["name"], "event_id": None, "status": "active",
               "source": "plan_addon", "stripe_mode": deps["stripe_mode"], "stripe_price_id": price_id, "stripe_subscription_id": sub["id"],
               "stripe_item_id": (item or {}).get("id"), "price": float(svc["price"]), "price_type": "yearly", "first_amount": q["amount_due"],
               "renew": True, "activated_at": _now().isoformat(), "created_by": user["user_id"], "created_at": _now().isoformat(),
               "current_period_end": datetime.fromtimestamp(cpe, timezone.utc).isoformat() if cpe else None,
               "history": [{"at": _now().isoformat(), "status": "active", "by": user.get("email"), "note": f"Prorata {q['amount_due']} €"}]}
        await db.marketplace_purchases.insert_one(dict(doc))
        await deps["record_audit"](user, "plan_addon_purchase", org_id=org["id"], detail=f"{svc['name']} · {q['amount_due']} €")
        return {"ok": True, "purchase": {k: v for k, v in doc.items() if k != "_id"}}

    @r.post("/marketplace/plan-addon/renewal")
    async def set_renewal(renew: bool, user: dict = Depends(require_admin)):
        _billing_admin(user)
        p = await _purchase(user["org_id"])
        if not p:
            raise HTTPException(status_code=404, detail="Modulo non attivo")
        if bool(p.get("renew", True)) == renew:
            return {"ok": True, "renew": renew}
        try:
            if renew:
                sub = stripe_sdk.Subscription.modify(p["stripe_subscription_id"], items=[{"price": p["stripe_price_id"]}], proration_behavior="none")
                item = next((i for i in sub["items"]["data"] if i["price"]["id"] == p["stripe_price_id"]), None)
                upd = {"renew": True, "stripe_item_id": (item or {}).get("id")}
            else:
                stripe_sdk.Subscription.modify(p["stripe_subscription_id"], items=[{"id": p["stripe_item_id"], "deleted": True}], proration_behavior="none")
                upd = {"renew": False}
        except stripe_sdk.error.StripeError as e:
            logger.error(f"plan addon renewal toggle: {e}")
            raise HTTPException(status_code=502, detail="Non è stato possibile aggiornare il rinnovo. Riprova più tardi.")
        await db.marketplace_purchases.update_one({"id": p["id"]}, {"$set": {**upd, "updated_at": _now().isoformat()},
                                                   "$push": {"history": {"at": _now().isoformat(), "status": "active", "by": user.get("email"),
                                                                         "note": "Rinnovo automatico attivato" if renew else "Rinnovo automatico disattivato"}}})
        await deps["record_audit"](user, "plan_addon_renewal", org_id=user["org_id"], detail=f"{p['service_name']} · rinnovo {'attivo' if renew else 'disattivato'}")
        return {"ok": True, "renew": renew}

    async def _expire(org_id: str) -> None:
        await db.marketplace_purchases.update_many({"org_id": org_id, "source": "plan_addon", "renew": False, "status": {"$in": list(LIVE)},
                                                    "current_period_end": {"$lt": _now().isoformat()}},
                                                   {"$set": {"status": "expired", "updated_at": _now().isoformat()}})

    async def sync_from_event(t: str, obj) -> None:
        """Allinea i moduli alla sottoscrizione principale (rinnovo, cambio data, pagamento fallito, annullamento). Non esclusivo."""
        if not t.startswith("customer.subscription."):
            return
        ps = await db.marketplace_purchases.find({"source": "plan_addon", "stripe_subscription_id": obj.get("id"), "status": {"$in": list(LIVE)}}, {"_id": 0}).to_list(20)
        for p in ps:
            st = obj.get("status")
            items = (obj.get("items") or {}).get("data") or []
            item = next((i for i in items if i.get("id") == p.get("stripe_item_id")), None)
            upd = {"updated_at": _now().isoformat()}
            if st == "canceled":
                upd.update(status="canceled", canceled_at=_now().isoformat())
            elif item:
                cpe = obj.get("current_period_end") or item.get("current_period_end")
                if cpe:
                    upd["current_period_end"] = datetime.fromtimestamp(cpe, timezone.utc).isoformat()
                upd["status"] = "past_due" if st in ("past_due", "unpaid") else "active"
            await db.marketplace_purchases.update_one({"id": p["id"]}, {"$set": upd})
            await _expire(p["org_id"])

    async def seed() -> None:
        if await db.schema_meta.find_one({"id": "plan_addon_asd_v1"}):
            return
        await db.marketplace_services.update_one({"key": ADDON_KEY}, {"$set": {
            "name": ADDON_NAME, "price": 99.0, "price_type": "yearly", "billing_method": "plan_addon", "purchasable": False, "billing_note": ADDON_NOTE}})
        await db.schema_meta.insert_one({"id": "plan_addon_asd_v1", "applied_at": _now().isoformat()})

    async def has_active_addon(org_id: str) -> bool:
        return bool(await db.marketplace_purchases.find_one({"org_id": org_id, "source": "plan_addon", "status": {"$in": list(LIVE)}, "renew": {"$ne": False}}, {"_id": 1}))

    return {"router": r, "sync_from_event": sync_from_event, "seed": seed, "has_active_addon": has_active_addon}
