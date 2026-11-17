"""Traffico dagli assistenti AI: visite first-party (solo con consenso analitico) e report Super Admin su registrazioni, prove e abbonamenti."""
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

AI = {"chatgpt": "ChatGPT", "perplexity": "Perplexity", "gemini": "Gemini", "copilot": "Copilot", "claude": "Claude"}


def clean_attr(a: Optional[dict]) -> Optional[dict]:
    if not isinstance(a, dict):
        return None
    out = {k: str(a.get(k) or "")[:120] for k in ("source", "ai", "referrer_host", "landing", "utm_source", "utm_medium", "utm_campaign", "at")}
    if out["ai"] not in AI:
        out["ai"] = ""
    return out if any(v for k, v in out.items() if k != "at") else None


class VisitIn(BaseModel):
    visitor_id: str = Field(min_length=8, max_length=64)
    ai: Optional[str] = Field(default="", max_length=20)
    source: Optional[str] = Field(default="", max_length=60)
    referrer_host: Optional[str] = Field(default="", max_length=120)
    landing: Optional[str] = Field(default="", max_length=200)
    utm_source: Optional[str] = Field(default="", max_length=120)
    utm_medium: Optional[str] = Field(default="", max_length=120)
    utm_campaign: Optional[str] = Field(default="", max_length=120)


def build(db, deps):
    sa = deps["require_superadmin"]
    r = APIRouter(prefix="/api")

    @r.post("/public/visit")
    async def visit(body: VisitIn):
        if not re.fullmatch(r"[A-Za-z0-9-]+", body.visitor_id):
            return {"ok": False}
        day = datetime.now(timezone.utc).isoformat()[:10]
        if await db.web_visits.find_one({"visitor_id": body.visitor_id, "day": day}, {"_id": 1}):
            return {"ok": True}
        d = body.model_dump()
        d["ai"] = d["ai"] if d["ai"] in AI else ""
        d["day"] = day
        d.update({"id": uuid.uuid4().hex, "created_at": datetime.now(timezone.utc).isoformat()})
        await db.web_visits.insert_one(d)
        return {"ok": True}

    @r.get("/platform/ai-traffic")
    async def report(days: int = Query(90, ge=1, le=730), _: dict = Depends(sa)):
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        vis = await db.web_visits.aggregate([{"$match": {"created_at": {"$gte": since}}},
                                             {"$group": {"_id": "$ai", "visits": {"$sum": 1}, "visitors": {"$addToSet": "$visitor_id"}}}]).to_list(20)
        orgs = await db.organizations.find({"type": "cliente", "created_at": {"$gte": since}}, {"_id": 0, "attribution": 1, "subscription": 1}).to_list(20000)
        rows = {k: {"ai": k, "name": v, "visits": 0, "visitors": 0, "registrations": 0, "trials": 0, "subscriptions": 0} for k, v in AI.items()}
        other = {"visits": 0, "visitors": 0, "registrations": 0}
        for v in vis:
            t = rows.get(v["_id"]) or other
            t["visits"] += v["visits"]
            t["visitors"] += len(v["visitors"])
        for o in orgs:
            k = (o.get("attribution") or {}).get("ai")
            if k not in rows:
                other["registrations"] += 1
                continue
            st = (o.get("subscription") or {}).get("status")
            rows[k]["registrations"] += 1
            rows[k]["trials"] += st == "trial"
            rows[k]["subscriptions"] += st == "active"
        tot = {f: sum(x[f] for x in rows.values()) for f in ("visits", "visitors", "registrations", "trials", "subscriptions")}
        return {"days": days, "rows": list(rows.values()), "total_ai": tot, "other": other}

    return {"router": r}
