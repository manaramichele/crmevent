"""Event Planner / Event Map: eventi inclusi nel piano, attivazioni per evento, acquisti Stripe, omaggi e promozioni Super Admin."""
import copy
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import stripe as stripe_sdk
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

logger = logging.getLogger("addons")
PRODUCTS = {"planner": "Event Planner", "eventmap": "Event Map"}
SLUG = {"planner": "event-planner", "eventmap": "event-map"}
GRANT_SOURCES = ("purchase", "superadmin", "promo")
DEFAULT_CONFIG = {
    "id": "config",
    "planner": {"included": {"bronze": 0, "silver": 1, "gold": 3}, "price": None},
    "eventmap": {"included": {"bronze": 0, "silver": 1, "gold": 3}, "included_videos": 1, "packages": []},
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(d: datetime) -> str:
    return d.isoformat()


def _included_videos(cfg: dict) -> int:
    # ogni evento incluso nel piano ha sempre almeno 1 video
    return max(1, int(cfg.get("included_videos") or 0))


def _valid(g: dict, now: str) -> bool:
    return g.get("status") == "active" and (not g.get("expires_at") or g["expires_at"] > now)


class PackageIn(BaseModel):
    id: Optional[str] = None
    name: str = Field(min_length=2, max_length=80)
    price: Optional[float] = Field(None, ge=0)
    videos: int = Field(ge=0)
    events: int = Field(ge=1)
    validity_days: Optional[int] = Field(None, ge=1)
    formats: list[str] = []
    active: bool = True


class IncludedIn(BaseModel):
    bronze: int = Field(ge=0)
    silver: int = Field(ge=0)
    gold: int = Field(ge=0)


class ConfigIn(BaseModel):
    planner_included: IncludedIn
    planner_price: Optional[float] = Field(None, ge=0)
    eventmap_included: IncludedIn
    eventmap_included_videos: int = Field(ge=1)
    eventmap_packages: list[PackageIn] = []


class CheckoutIn(BaseModel):
    origin_url: str
    event_id: Optional[str] = None
    package_id: Optional[str] = None


class GrantIn(BaseModel):
    product: str
    source: str = "superadmin"
    events_total: int = Field(1, ge=1, le=100)
    videos_total: int = Field(0, ge=0, le=10000)
    package_id: Optional[str] = None
    expires_at: Optional[str] = None
    event_ids: list[str] = []
    note: Optional[str] = Field(None, max_length=300)


def build(db, deps: dict):
    r = APIRouter(prefix="/api")
    admin_dep, sa_dep, audit = deps["require_admin"], deps["require_superadmin"], deps["record_audit"]

    async def ensure():
        await db.addon_activations.create_index([("org_id", 1), ("product", 1), ("event_id", 1)], unique=True)
        await db.addon_grants.create_index([("org_id", 1), ("product", 1), ("status", 1)])
        await db.addon_grants.create_index("stripe_session_id", sparse=True)
        await db.addon_usage.create_index([("org_id", 1), ("product", 1)], unique=True)

    async def get_config() -> dict:
        doc = await db.addon_config.find_one({"id": "config"}, {"_id": 0})
        if not doc:
            await db.addon_config.update_one({"id": "config"}, {"$setOnInsert": copy.deepcopy(DEFAULT_CONFIG)}, upsert=True)
            doc = await db.addon_config.find_one({"id": "config"}, {"_id": 0})
        return doc

    def _product(p: str) -> str:
        if p not in PRODUCTS:
            raise HTTPException(status_code=404, detail="Prodotto non trovato")
        return p

    async def _unrestricted(org_id: str) -> bool:
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "type": 1, "is_demo_official": 1}) or {}
        if org.get("is_demo_official") and org.get("type") == "test":
            return True
        return not (await deps["state_for"](org_id)).get("enabled")

    async def summary(org_id: str, product: str) -> dict:
        """Diritti calcolati a ogni richiesta: upgrade/downgrade si riflettono subito, nessun dato viene cancellato."""
        cfg = (await get_config())[product]
        st = await deps["state_for"](org_id)
        unrestricted = await _unrestricted(org_id)
        plan = st.get("plan") if st.get("mode") in ("active", "past_due") else None
        limit = int((cfg.get("included") or {}).get(plan, 0)) if plan else 0
        now = _iso(_now())
        grants = await db.addon_grants.find({"org_id": org_id, "product": product, "status": {"$ne": "pending"}}, {"_id": 0}).sort("created_at", 1).to_list(500)
        gmap = {g["id"]: g for g in grants}
        acts = await db.addon_activations.find({"org_id": org_id, "product": product}, {"_id": 0}).sort("assigned_at", 1).to_list(2000)
        plan_acts = [a for a in acts if a["grant_id"] == "plan"]
        covered_plan = {a["event_id"] for a in plan_acts[:limit]}
        rows = []
        for a in acts:
            g = gmap.get(a["grant_id"])
            ok = unrestricted or (a["event_id"] in covered_plan if a["grant_id"] == "plan" else bool(g and _valid(g, now)))
            rows.append({**a, "covered": ok, "source": "included" if a["grant_id"] == "plan" else (g or {}).get("source"),
                         "expires_at": (g or {}).get("expires_at")})
        used_by = {}
        for a in acts:
            used_by[a["grant_id"]] = used_by.get(a["grant_id"], 0) + 1
        valid = [g for g in grants if _valid(g, now)]
        out = {"product": product, "name": PRODUCTS[product], "unrestricted": unrestricted, "plan": plan, "plan_label": st.get("plan_label") if plan else None,
               "mode": st.get("mode"), "included": limit, "included_used": min(len(plan_acts), limit), "included_assigned": len(plan_acts),
               "included_free": max(0, limit - len(plan_acts)),
               "purchased": sum(g["events_total"] for g in grants if g["source"] == "purchase" and g.get("activated_at")),
               "granted": sum(g["events_total"] for g in grants if g["source"] in ("superadmin", "promo") and g["status"] != "revoked"),
               "grant_free": sum(max(0, g["events_total"] - used_by.get(g["id"], 0)) for g in valid),
               "activations": rows, "grants": grants,
               "promos": [g for g in valid if g["source"] == "promo"]}
        if product == "eventmap":
            u = await db.addon_usage.find_one({"org_id": org_id, "product": product}, {"_id": 0}) or {}
            out["videos_total"] = _included_videos(cfg) * out["included_used"] + sum(int(g.get("videos_total") or 0) for g in valid)
            out["videos_used"] = int(u.get("videos_used") or 0)
            out["videos_in_progress"] = await db.eventmap_videos.count_documents({"org_id": org_id, "status": {"$in": ["queued", "processing"]}})
            out["videos_available"] = max(0, out["videos_total"] - out["videos_used"] - out["videos_in_progress"])
            out["packages"] = [p for p in cfg.get("packages") or [] if p.get("active")]
        else:
            out["price"] = cfg.get("price")
        return out

    def _required(product: str, s: dict, ev_name: str = "") -> HTTPException:
        what = f"«{ev_name}»" if ev_name else "questo evento"
        return HTTPException(status_code=403, detail={
            "code": "addon_required", "product": product, "slug": SLUG[product],
            "message": f"{PRODUCTS[product]} non è attivo per {what}. Attivalo dal Marketplace per continuare: i dati già creati restano conservati."})

    async def is_covered(org_id: str, product: str, event_id: str) -> bool:
        if await _unrestricted(org_id):
            return True
        s = await summary(org_id, product)
        return any(a["event_id"] == event_id and a["covered"] for a in s["activations"])

    async def require_covered(user: dict, product: str, event_id: str) -> None:
        if user.get("role") == "superadmin" or await is_covered(user["org_id"], product, event_id):
            return
        raise _required(product, {})

    async def _event(org_id: str, eid: str) -> dict:
        ev = await db.events.find_one({"org_id": org_id, "id": eid}, {"_id": 0, "id": 1, "nome": 1, "data_inizio": 1})
        if not ev:
            raise HTTPException(status_code=404, detail="Evento non trovato")
        return ev

    async def _assign(org_id: str, product: str, eid: str, grant_id: str, by: str) -> None:
        doc = {"grant_id": grant_id, "assigned_at": _iso(_now()), "assigned_by": by}
        try:
            await db.addon_activations.update_one({"org_id": org_id, "product": product, "event_id": eid},
                                                  {"$set": doc, "$setOnInsert": {"id": uuid.uuid4().hex, "created_at": doc["assigned_at"]}}, upsert=True)
        except DuplicateKeyError:
            await db.addon_activations.update_one({"org_id": org_id, "product": product, "event_id": eid}, {"$set": doc})

    async def activate(org_id: str, product: str, eid: str, by: str) -> dict:
        ev = await _event(org_id, eid)
        s = await summary(org_id, product)
        cur = next((a for a in s["activations"] if a["event_id"] == eid), None)
        if cur and cur["covered"]:
            raise HTTPException(status_code=400, detail=f"{PRODUCTS[product]} è già attivo per questo evento")
        if s["unrestricted"]:
            await _assign(org_id, product, eid, "unrestricted", by)
            return {"ok": True, "source": "unrestricted"}
        if s["included_free"] > 0:
            prev = cur["grant_id"] if cur else None
            await _assign(org_id, product, eid, "plan", by)
            n = await db.addon_activations.count_documents({"org_id": org_id, "product": product, "grant_id": "plan"})
            if n > s["included"]:  # richiesta concorrente: annulla
                if prev:
                    await db.addon_activations.update_one({"org_id": org_id, "product": product, "event_id": eid}, {"$set": {"grant_id": prev}})
                else:
                    await db.addon_activations.delete_one({"org_id": org_id, "product": product, "event_id": eid})
                raise _required(product, s, ev["nome"])
            return {"ok": True, "source": "included"}
        now = _iso(_now())
        used = {}
        for a in s["activations"]:
            used[a["grant_id"]] = used.get(a["grant_id"], 0) + 1
        for g in sorted([g for g in s["grants"] if _valid(g, now)], key=lambda g: g.get("expires_at") or "9999"):
            if used.get(g["id"], 0) < g["events_total"]:
                await _assign(org_id, product, eid, g["id"], by)
                n = await db.addon_activations.count_documents({"org_id": org_id, "product": product, "grant_id": g["id"]})
                if n <= g["events_total"]:
                    return {"ok": True, "source": g["source"]}
                if cur:
                    await db.addon_activations.update_one({"org_id": org_id, "product": product, "event_id": eid}, {"$set": {"grant_id": cur["grant_id"]}})
                else:
                    await db.addon_activations.delete_one({"org_id": org_id, "product": product, "event_id": eid})
        raise _required(product, s, ev["nome"])

    def _can_buy(user: dict) -> bool:
        p = user.get("perm") or {}
        return user.get("org_role") in ("admin_org", "superadmin") or bool(p.get("admin")) or bool(p.get("marketplace_purchase"))

    async def _events_view(org_id: str, s: dict) -> list:
        acts = {a["event_id"]: a for a in s["activations"]}
        evs = await db.events.find({"org_id": org_id}, {"_id": 0, "id": 1, "nome": 1, "data_inizio": 1}).sort("data_inizio", -1).to_list(500)
        return [{**e, "active": e["id"] in acts and acts[e["id"]]["covered"], "assigned": e["id"] in acts,
                 "source": (acts.get(e["id"]) or {}).get("source"), "expires_at": (acts.get(e["id"]) or {}).get("expires_at")} for e in evs]

    # ---------------- organizzatore ----------------
    @r.get("/addons/{product}")
    async def org_status(product: str, user: dict = Depends(admin_dep)):
        s = await summary(user["org_id"], _product(product))
        return {**{k: v for k, v in s.items() if k not in ("grants", "activations")}, "events": await _events_view(user["org_id"], s),
                "can_purchase": _can_buy(user)}

    @r.post("/addons/{product}/events/{eid}/activate")
    async def org_activate(product: str, eid: str, user: dict = Depends(admin_dep)):
        if not _can_buy(user):
            raise HTTPException(status_code=403, detail="Solo l'Admin Organizzatore può attivare le funzionalità sugli eventi")
        res = await activate(user["org_id"], _product(product), eid, user.get("email"))
        await audit(user, f"addon_{product}_activate", detail=f"{eid} · {res['source']}")
        return res

    @r.get("/addons/eventmap/events/{eid}/video-check")
    async def video_check(eid: str, user: dict = Depends(admin_dep)):
        await _event(user["org_id"], eid)
        s = await summary(user["org_id"], "eventmap")
        on = s["unrestricted"] or any(a["event_id"] == eid and a["covered"] for a in s["activations"])
        avail = s.get("videos_available", 0)
        reason = None if on and (s["unrestricted"] or avail > 0) else ("Event Map non è attivo per questo evento" if not on else "Hai esaurito i video disponibili: acquista un pacchetto nel Marketplace")
        return {"allowed": reason is None, "reason": reason, "videos_available": avail, "videos_used": s.get("videos_used", 0)}

    async def consume_video(org_id: str, eid: str) -> None:
        """Da usare dal generatore Event Map: verifica evento attivo e scala un video (atomico)."""
        s = await summary(org_id, "eventmap")
        if not (s["unrestricted"] or any(a["event_id"] == eid and a["covered"] for a in s["activations"])):
            raise _required("eventmap", s)
        if s["unrestricted"]:
            await db.addon_usage.update_one({"org_id": org_id, "product": "eventmap"}, {"$inc": {"videos_used": 1}}, upsert=True)
            return
        await db.addon_usage.update_one({"org_id": org_id, "product": "eventmap"}, {"$setOnInsert": {"videos_used": 0}}, upsert=True)
        if not await db.addon_usage.find_one_and_update({"org_id": org_id, "product": "eventmap", "videos_used": {"$lt": s["videos_total"]}}, {"$inc": {"videos_used": 1}}):
            raise HTTPException(status_code=403, detail={"code": "addon_videos", "message": "Hai esaurito i video disponibili: acquista un pacchetto Event Map nel Marketplace"})

    @r.post("/addons/{product}/checkout")
    async def checkout(product: str, body: CheckoutIn, user: dict = Depends(admin_dep)):
        product = _product(product)
        if not _can_buy(user):
            raise HTTPException(status_code=403, detail="Non hai il permesso di acquistare servizi Marketplace")
        cfg = (await get_config())[product]
        s = await summary(user["org_id"], product)
        ev = await _event(user["org_id"], body.event_id) if body.event_id else None
        if product == "planner" and not ev:
            raise HTTPException(status_code=400, detail="Seleziona l'evento su cui attivare Event Planner")
        if ev and any(a["event_id"] == ev["id"] and a["covered"] for a in s["activations"]):
            raise HTTPException(status_code=400, detail=f"{PRODUCTS[product]} è già attivo per questo evento: nessun acquisto necessario")
        if ev and (s["included_free"] > 0 or s["grant_free"] > 0):
            raise HTTPException(status_code=400, detail="Hai ancora un'attivazione disponibile: attiva l'evento senza acquistare")
        if product == "planner":
            pkg = {"id": None, "name": "Attivazione per evento", "price": cfg.get("price"), "events": 1, "videos": 0, "validity_days": None}
        else:
            pkg = next((p for p in cfg.get("packages") or [] if p.get("id") == body.package_id and p.get("active")), None)
            if not pkg:
                raise HTTPException(status_code=400, detail="Seleziona un pacchetto Event Map")
        if pkg.get("price") is None or float(pkg["price"]) <= 0:
            raise HTTPException(status_code=400, detail="Prezzo non ancora configurato dal team CRMEvent")
        org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0})
        missing = deps["billing_missing"](org.get("billing") or {})
        if missing:
            raise HTTPException(status_code=400, detail="Completa i dati di fatturazione: " + ", ".join(missing))
        await db.addon_grants.update_many({"org_id": org["id"], "product": product, "status": "pending", "event_id": (ev or {}).get("id")},
                                          {"$set": {"status": "expired", "updated_at": _iso(_now())}})
        gid = uuid.uuid4().hex
        md = {"kind": "addon", "grant_id": gid, "org_id": org["id"], "product": product}
        origin = body.origin_url.rstrip("/")
        name = f"CRMEvent · {PRODUCTS[product]} · {pkg['name']}" + (f" · {ev['nome']}" if ev else "")
        try:
            sess = stripe_sdk.checkout.Session.create(
                customer=await deps["ensure_customer"](org, user), mode="payment", locale="it", client_reference_id=org["id"], metadata=md,
                line_items=[{"quantity": 1, "price_data": {"currency": "eur", "unit_amount": int(round(float(pkg["price"]) * 100)),
                                                           "product_data": {"name": name, "tax_code": "txcd_10103001"}}}],
                invoice_creation={"enabled": True, "invoice_data": {"metadata": md}}, payment_intent_data={"metadata": md},
                success_url=f"{origin}/{SLUG[product]}?session_id={{CHECKOUT_SESSION_ID}}", cancel_url=f"{origin}/{SLUG[product]}?canceled=1")
        except stripe_sdk.error.StripeError as e:
            logger.error(f"addon checkout: {e}")
            raise HTTPException(status_code=502, detail="Non è stato possibile avviare il pagamento. Riprova più tardi.")
        await db.addon_grants.insert_one({
            "id": gid, "org_id": org["id"], "product": product, "source": "purchase", "status": "pending", "events_total": int(pkg["events"]), "formats": pkg.get("formats") or [],
            "videos_total": int(pkg.get("videos") or 0), "validity_days": pkg.get("validity_days"), "package_id": pkg.get("id"), "package_name": pkg["name"],
            "price": float(pkg["price"]), "event_id": (ev or {}).get("id"), "expires_at": None, "stripe_session_id": sess.id, "stripe_mode": deps["stripe_mode"],
            "created_by": user.get("email"), "created_at": _iso(_now()), "history": [{"at": _iso(_now()), "status": "pending", "by": user.get("email")}]})
        return {"checkout_url": sess.url}

    async def _activate_from_session(sess) -> Optional[dict]:
        """Diritto concesso solo dopo pagamento verificato su Stripe. Idempotente."""
        md = sess.get("metadata") or {}
        g = await db.addon_grants.find_one({"id": md.get("grant_id")}, {"_id": 0}) if md.get("kind") == "addon" else None
        if not g or md.get("org_id") != g["org_id"]:
            return None
        if sess.get("status") != "complete" or sess.get("payment_status") not in ("paid", "no_payment_required"):
            return g
        exp = _iso(_now() + timedelta(days=int(g["validity_days"]))) if g.get("validity_days") else None
        res = await db.addon_grants.update_one({"id": g["id"], "status": {"$in": ["pending", "expired"]}},
                                               {"$set": {"status": "active", "activated_at": _iso(_now()), "expires_at": exp},
                                                "$push": {"history": {"at": _iso(_now()), "status": "active", "by": "stripe"}}})
        if res.modified_count:
            await audit({"user_id": "stripe", "email": "stripe", "role": "system"}, f"addon_{g['product']}_paid", org_id=g["org_id"], detail=f"{g.get('package_name')} · {g['price']} €")
            if g.get("event_id"):
                try:
                    await activate(g["org_id"], g["product"], g["event_id"], "stripe")
                except HTTPException:
                    pass
        return await db.addon_grants.find_one({"id": g["id"]}, {"_id": 0})

    @r.get("/addons-checkout/confirmation")
    async def confirmation(session_id: str, user: dict = Depends(admin_dep)):
        sess = stripe_sdk.checkout.Session.retrieve(session_id)
        if (sess.get("metadata") or {}).get("org_id") != user["org_id"]:
            raise HTTPException(status_code=403, detail="Sessione non associata all'organizzazione")
        g = await _activate_from_session(sess)
        return {"status": (g or {}).get("status")}

    async def handle_webhook(t: str, obj) -> bool:
        if (obj.get("metadata") or {}).get("kind") != "addon":
            return False
        if t in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
            await _activate_from_session(obj)
            return True
        if t in ("checkout.session.expired", "checkout.session.async_payment_failed"):
            await db.addon_grants.update_one({"id": obj["metadata"].get("grant_id"), "status": "pending"}, {"$set": {"status": "expired", "updated_at": _iso(_now())}})
            return True
        return t.startswith("checkout.session.") or t.startswith("payment_intent.") or t.startswith("invoice.")

    # ---------------- Super Admin ----------------
    @r.get("/platform/addons/config")
    async def sa_config(admin: dict = Depends(sa_dep)):
        return await get_config()

    @r.put("/platform/addons/config")
    async def sa_put_config(body: ConfigIn, admin: dict = Depends(sa_dep)):
        pk = [{**p.model_dump(), "id": p.id or uuid.uuid4().hex[:10]} for p in body.eventmap_packages]
        await db.addon_config.update_one({"id": "config"}, {"$set": {
            "planner": {"included": body.planner_included.model_dump(), "price": body.planner_price},
            "eventmap": {"included": body.eventmap_included.model_dump(), "included_videos": body.eventmap_included_videos, "packages": pk},
            "updated_at": _iso(_now()), "updated_by": admin.get("email")}}, upsert=True)
        await audit(admin, "addon_config_update", detail=f"planner {body.planner_price} € · {len(pk)} pacchetti Event Map")
        return await get_config()

    @r.get("/platform/addons/orgs")
    async def sa_orgs(admin: dict = Depends(sa_dep)):
        orgs = await db.organizations.find({"type": {"$in": ["cliente", None]}}, {"_id": 0, "id": 1, "nome": 1}).sort("nome", 1).to_list(2000)
        out = []
        for o in orgs:
            p, m = await summary(o["id"], "planner"), await summary(o["id"], "eventmap")
            out.append({"id": o["id"], "nome": o.get("nome"), "plan_label": p["plan_label"], "mode": p["mode"], "unrestricted": p["unrestricted"],
                        "planner": {k: p[k] for k in ("included", "included_used", "purchased", "granted")} | {"active": sum(a["covered"] for a in p["activations"])},
                        "eventmap": {k: m[k] for k in ("included", "included_used", "purchased", "granted", "videos_total", "videos_used")} | {"active": sum(a["covered"] for a in m["activations"])},
                        "promos": len(p["promos"]) + len(m["promos"])})
        return out

    @r.get("/platform/addons/orgs/{org_id}")
    async def sa_org(org_id: str, admin: dict = Depends(sa_dep)):
        if not await db.organizations.find_one({"id": org_id}, {"_id": 1}):
            raise HTTPException(status_code=404, detail="Organizzazione non trovata")
        res = {}
        for prod in PRODUCTS:
            s = await summary(org_id, prod)
            res[prod] = {**{k: v for k, v in s.items() if k != "activations"}, "events": await _events_view(org_id, s)}
        return res

    @r.post("/platform/addons/orgs/{org_id}/grants")
    async def sa_grant(org_id: str, body: GrantIn, admin: dict = Depends(sa_dep)):
        """Omaggio o promozione: nessun checkout Stripe."""
        product = _product(body.product)
        if body.source not in ("superadmin", "promo"):
            raise HTTPException(status_code=400, detail="Origine non valida")
        if body.source == "promo" and not body.expires_at:
            raise HTTPException(status_code=400, detail="Una promozione deve avere una data di scadenza")
        if body.expires_at and body.expires_at <= _iso(_now())[:10]:
            raise HTTPException(status_code=400, detail="La scadenza deve essere futura")
        if not await db.organizations.find_one({"id": org_id}, {"_id": 1}):
            raise HTTPException(status_code=404, detail="Organizzazione non trovata")
        events_total, videos, name, formats = body.events_total, body.videos_total, "Assegnazione manuale", []
        if body.package_id:
            pkg = next((p for p in (await get_config())["eventmap"].get("packages") or [] if p.get("id") == body.package_id), None)
            if not pkg or product != "eventmap":
                raise HTTPException(status_code=400, detail="Pacchetto non trovato")
            events_total, videos, name, formats = int(pkg["events"]), int(pkg["videos"]), pkg["name"], pkg.get("formats") or []
        for eid in body.event_ids:
            await _event(org_id, eid)
        exp = f"{body.expires_at[:10]}T23:59:59+00:00" if body.expires_at else None
        gid = uuid.uuid4().hex
        await db.addon_grants.insert_one({
            "id": gid, "org_id": org_id, "product": product, "source": body.source, "status": "active", "events_total": events_total, "formats": formats,
            "videos_total": videos if product == "eventmap" else 0, "package_id": body.package_id, "package_name": name, "price": 0.0,
            "event_id": None, "expires_at": exp, "note": body.note, "created_by": admin.get("email"), "created_at": _iso(_now()),
            "history": [{"at": _iso(_now()), "status": "active", "by": admin.get("email"), "note": body.note}]})
        done = []
        for eid in body.event_ids[:events_total]:
            s = await summary(org_id, product)
            if not any(a["event_id"] == eid and a["covered"] for a in s["activations"]):
                await _assign(org_id, product, eid, gid, admin.get("email"))
                done.append(eid)
        await audit(admin, f"addon_{product}_grant", org_id=org_id, detail=f"{body.source} · {events_total} eventi · {videos} video · scad. {exp or '—'}")
        return {"id": gid, "activated_events": done}

    @r.post("/platform/addons/grants/{gid}/revoke")
    async def sa_revoke(gid: str, admin: dict = Depends(sa_dep)):
        g = await db.addon_grants.find_one({"id": gid}, {"_id": 0})
        if not g:
            raise HTTPException(status_code=404, detail="Attivazione non trovata")
        if g["source"] not in ("superadmin", "promo") or g["status"] != "active":
            raise HTTPException(status_code=400, detail="Si possono revocare solo omaggi e promozioni attivi: gli acquisti non vengono revocati")
        await db.addon_grants.update_one({"id": gid}, {"$set": {"status": "revoked", "revoked_at": _iso(_now()), "revoked_by": admin.get("email")},
                                                       "$push": {"history": {"at": _iso(_now()), "status": "revoked", "by": admin.get("email")}}})
        await audit(admin, f"addon_{g['product']}_revoke", org_id=g["org_id"], detail=gid)
        return {"ok": True}

    async def public_included():
        c = await get_config()
        return {p: {"included": c[p]["included"]} for p in PRODUCTS} | {"eventmap_included_videos": _included_videos(c["eventmap"])}

    r.add_api_route("/public/addons-included", public_included, methods=["GET"])

    return {"router": r, "ensure": ensure, "handle_webhook": handle_webhook, "require_covered": require_covered,
            "is_covered": is_covered, "consume_video": consume_video, "summary": summary}
