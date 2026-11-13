"""Demo pubblica Event Planner in homepage: impostazioni Super Admin, configurazione pubblica e conteggi anonimi."""
import os
import re
import time
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from planner import LIBRARY

SCENARIOS = {"running": "Running / maratona"}
EVENTS = {"view", "start", "scenario", "tool", "place", "nudge", "cta_register", "cta_features", "fullscreen", "signup", "import"}
DEFAULTS = {
    "abilitata": True, "scenario_default": "running",
    "titolo": "Progetta il tuo evento direttamente sulla mappa",
    "sottotitolo": "Con Event Planner di CRMEvent puoi disegnare percorsi, posizionare strutture, organizzare gli spazi e pianificare le attività operative del tuo evento. Tutto in modo semplice e visuale.",
    "cta_demo": "Prova Event Planner", "cta_funzioni": "Scopri tutte le funzionalità di CRMEvent", "cta_funzioni_link": "#funzionalita",
    "nudge_titolo": "Hai iniziato a progettare il tuo evento!",
    "nudge_testo": "Registrati a CRMEvent per salvare il tuo progetto e continuare a organizzare il tuo evento con tutti gli strumenti della piattaforma.",
    "nudge_cta": "Registrati e continua", "soglia_interazioni": 4,
}
RATE = 120  # eventi tracciati per IP all'ora


class SettingsIn(BaseModel):
    abilitata: bool
    scenario_default: str
    titolo: str = Field(min_length=3, max_length=140)
    sottotitolo: str = Field(min_length=3, max_length=400)
    cta_demo: str = Field(min_length=2, max_length=60)
    cta_funzioni: str = Field(min_length=2, max_length=80)
    cta_funzioni_link: str = Field(min_length=1, max_length=300)
    nudge_titolo: str = Field(min_length=3, max_length=120)
    nudge_testo: str = Field(min_length=3, max_length=400)
    nudge_cta: str = Field(min_length=2, max_length=60)
    soglia_interazioni: int = Field(ge=1, le=50)


class TrackIn(BaseModel):
    evento: str
    valore: Optional[str] = None


def build(db, deps: dict):
    r = APIRouter(prefix="/api")
    sa, client_ip, audit = deps["require_superadmin"], deps["client_ip"], deps["record_audit"]
    hits: dict = defaultdict(deque)

    async def settings() -> dict:
        doc = await db.planner_demo_settings.find_one({"_id": "main"}, {"_id": 0}) or {}
        return {**DEFAULTS, **doc}

    @r.get("/public/planner-demo")
    async def public_config():
        s = await settings()
        if not s["abilitata"]:
            return {"abilitata": False}
        # Chiave pubblica MapTiler (limitata ai domini CRMEvent nel pannello MapTiler)
        return {**s, "maptiler_key": os.environ.get("MAPTILER_API_KEY") or None, "scenari": SCENARIOS,
                "library": [{"id": f"lib{i}", "categoria": c, "nome": n, "larghezza": w, "lunghezza": l, "colore": col, "tipo": t}
                            for i, (c, n, w, l, col, t) in enumerate(LIBRARY)]}

    @r.post("/public/planner-demo/track")
    async def track(body: TrackIn, request: Request):
        if body.evento not in EVENTS:
            raise HTTPException(status_code=400, detail="Evento non valido")
        valore = (body.valore or "")[:40]
        if valore and not re.fullmatch(r"[\w\- àèéìòù×,./()]+", valore):
            valore = ""
        now = time.time()
        if len(hits) > 5000:
            for k in [k for k, v in hits.items() if not v or v[-1] < now - 3600]:
                hits.pop(k, None)
        q = hits[client_ip(request)]
        while q and q[0] < now - 3600:
            q.popleft()
        if len(q) >= RATE:
            return {"ok": False}
        q.append(now)
        giorno = datetime.now(timezone.utc).date().isoformat()
        await db.planner_demo_stats.update_one({"giorno": giorno, "evento": body.evento, "valore": valore}, {"$inc": {"n": 1}}, upsert=True)
        return {"ok": True}

    @r.get("/planner-demo/settings")
    async def get_settings(_: dict = Depends(sa)):
        return {**(await settings()), "scenari": SCENARIOS}

    @r.put("/planner-demo/settings")
    async def put_settings(body: SettingsIn, user: dict = Depends(sa)):
        if body.scenario_default not in SCENARIOS:
            raise HTTPException(status_code=400, detail="Scenario non disponibile")
        await db.planner_demo_settings.update_one({"_id": "main"}, {"$set": body.model_dump()}, upsert=True)
        await audit(user, "planner_demo_settings", detail=f"abilitata={body.abilitata}")
        return {"ok": True}

    @r.get("/planner-demo/stats")
    async def stats(giorni: int = 30, _: dict = Depends(sa)):
        da = (datetime.now(timezone.utc).date() - timedelta(days=max(1, min(giorni, 365)) - 1)).isoformat()
        rows = await db.planner_demo_stats.find({"giorno": {"$gte": da}}, {"_id": 0}).to_list(20000)
        tot, per = defaultdict(int), defaultdict(lambda: defaultdict(int))
        for x in rows:
            tot[x["evento"]] += x["n"]
            if x.get("valore"):
                per[x["evento"]][x["valore"]] += x["n"]
        return {"da": da, "totali": dict(tot), "dettaglio": {k: dict(v) for k, v in per.items()}}

    async def ensure():
        await db.planner_demo_stats.create_index([("giorno", 1), ("evento", 1), ("valore", 1)], unique=True)

    return {"router": r, "ensure": ensure}
