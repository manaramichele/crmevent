"""Event Planner — Fase B: progetti per evento, livelli, oggetti GeoJSON, salvataggio con controllo versione e cronologia revisioni."""
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import planner_bom

MAX_FEATURES = 5000
MAX_REVISIONS = 30
DEFAULT_LAYERS = ["Percorsi", "Partenza e arrivo", "Strutture", "Ristori", "Sicurezza", "Viabilità", "Staff e volontari", "Sponsor", "Fornitori", "Aree operative"]
COLORS = ["#E11D48", "#0ABAB5", "#2563EB", "#F59E0B", "#DC2626", "#64748B", "#16A34A", "#9333EA", "#EA580C", "#0F766E"]
# Libreria iniziale: (categoria, nome, larghezza m, lunghezza m, colore, tipo) — tipo: box (in scala) | point | line (con passo m)
LIBRARY = [
    ("Strutture", "Gazebo 3×3 m", 3, 3, "#0ABAB5", "box"), ("Strutture", "Gazebo 6×3 m", 6, 3, "#0ABAB5", "box"),
    ("Strutture", "Tensostruttura 10×20 m", 10, 20, "#0F766E", "box"), ("Strutture", "Palco 8×6 m", 8, 6, "#7C3AED", "box"),
    ("Strutture", "Pedana 4×2 m", 4, 2, "#6D28D9", "box"), ("Strutture", "Arco partenza/arrivo 12 m", 12, 1, "#E11D48", "box"),
    ("Strutture", "Container 6×2,5 m", 6, 2.5, "#475569", "box"), ("Strutture", "Tavolo 2×0,8 m", 2, 0.8, "#A16207", "box"),
    ("Strutture", "Sedia", 0.5, 0.5, "#A16207", "box"),
    ("Servizi", "Bagno chimico", 1.2, 1.2, "#2563EB", "box"), ("Servizi", "Bagno accessibile", 1.6, 1.6, "#1D4ED8", "box"),
    ("Servizi", "Punto acqua", 0, 0, "#0284C7", "point"), ("Servizi", "Ristoro", 0, 0, "#F59E0B", "point"),
    ("Servizi", "Deposito borse", 0, 0, "#B45309", "point"), ("Servizi", "Spogliatoi", 0, 0, "#92400E", "point"),
    ("Servizi", "Segreteria", 0, 0, "#0369A1", "point"), ("Servizi", "Area medica", 0, 0, "#DC2626", "point"),
    ("Sicurezza", "Ambulanza", 6, 2.5, "#DC2626", "box"), ("Sicurezza", "Primo soccorso", 0, 0, "#EF4444", "point"),
    ("Sicurezza", "Estintore", 0, 0, "#B91C1C", "point"), ("Sicurezza", "Uscita di emergenza", 0, 0, "#16A34A", "point"),
    ("Sicurezza", "Punto di raccolta", 0, 0, "#15803D", "point"), ("Sicurezza", "Postazione di controllo", 0, 0, "#991B1B", "point"),
    ("Viabilità", "Transenne (2 m)", 2, 0, "#64748B", "line"), ("Viabilità", "Barriera (3 m)", 3, 0, "#334155", "line"),
    ("Viabilità", "Cono", 0, 0, "#F97316", "point"), ("Viabilità", "Cartello", 0, 0, "#EAB308", "point"),
    ("Viabilità", "Parcheggio", 0, 0, "#1E40AF", "point"), ("Viabilità", "Accesso / Varco", 0, 0, "#0EA5E9", "point"),
    ("Viabilità", "Chiusura stradale", 0, 0, "#DC2626", "point"),
    ("Sponsor", "Stand sponsor 3×3 m", 3, 3, "#9333EA", "box"), ("Sponsor", "Bandiera", 0, 0, "#A855F7", "point"),
    ("Sponsor", "Banner (3 m)", 3, 0, "#C026D3", "line"), ("Sponsor", "Arco pubblicitario 8 m", 8, 1, "#7E22CE", "box"),
    ("Staff", "Postazione volontari", 0, 0, "#16A34A", "point"), ("Staff", "Punto controllo percorso", 0, 0, "#22C55E", "point"),
    ("Staff", "Coordinamento", 0, 0, "#15803D", "point"), ("Staff", "Direzione gara", 0, 0, "#166534", "point"),
]


def _now():
    return datetime.now(timezone.utc).isoformat()


class ProjectIn(BaseModel):
    nome: str = Field(min_length=2, max_length=120)
    duplica_da: Optional[str] = None


class ProjectPatch(BaseModel):
    nome: Optional[str] = Field(None, min_length=2, max_length=120)
    archiviato: Optional[bool] = None
    center: Optional[list] = None
    zoom: Optional[float] = None


class SaveIn(BaseModel):
    version: int
    features: list[dict[str, Any]]
    layers: list[dict[str, Any]]


def build(db, deps: dict):
    r = APIRouter(prefix="/api/planner")
    user_dep, admin_dep, audit, covered = deps["get_current_user"], deps["require_admin"], deps["record_audit"], deps["require_covered"]
    member_dep = deps["require_member"]  # letture: org attiva validata dal backend (membership / X-Org-Id Super Admin / assistenza)

    async def event_of(org_id: str, eid: str, user: dict, write: bool = True) -> dict:
        ev = await db.events.find_one({"org_id": org_id, "id": eid}, {"_id": 0, "id": 1, "nome": 1, "luogo": 1, "citta": 1, "data_inizio": 1})
        if not ev:
            raise HTTPException(status_code=404, detail="Evento non trovato")
        try:
            await covered(user, "planner", eid)
            ev["read_only"] = False
        except HTTPException:
            # abbonamento/omaggio scaduto: i progetti già salvati restano consultabili, la modifica è sospesa
            if write or not await db.planner_projects.find_one({"org_id": org_id, "evento_id": eid}, {"_id": 1}):
                raise
            ev["read_only"] = True
        return ev

    async def project_of(org_id: str, pid: str, user: dict, write: bool = True) -> dict:
        p = await db.planner_projects.find_one({"org_id": org_id, "id": pid}, {"_id": 0})
        if not p:
            raise HTTPException(status_code=404, detail="Progetto non trovato")
        p["read_only"] = (await event_of(org_id, p["evento_id"], user, write))["read_only"]
        return p

    bom_copy = planner_bom.attach(r, db, audit, member_dep, admin_dep, project_of, event_of, deps["org_logo"])
    @r.get("/config")
    async def config(user: dict = Depends(user_dep)):
        # Chiave pubblica MapTiler (va limitata ai domini CRMEvent nel pannello MapTiler); mai nel codice frontend.
        return {"maptiler_key": os.environ.get("MAPTILER_API_KEY") or None,
                "library": [{"id": f"lib{i}", "categoria": c, "nome": n, "larghezza": w, "lunghezza": l, "colore": col, "tipo": t}
                            for i, (c, n, w, l, col, t) in enumerate(LIBRARY)]}

    @r.get("/events/{eid}/projects")
    async def projects(eid: str, user: dict = Depends(member_dep)):
        ev = await event_of(user["org_id"], eid, user, write=False)
        rows = await db.planner_projects.find({"org_id": user["org_id"], "evento_id": eid}, {"_id": 0, "features": 0}).sort("created_at", 1).to_list(200)
        return {"evento": ev, "projects": rows}

    @r.post("/events/{eid}/projects")
    async def create(eid: str, body: ProjectIn, admin: dict = Depends(admin_dep)):
        await event_of(admin["org_id"], eid, admin)
        base = await project_of(admin["org_id"], body.duplica_da, admin) if body.duplica_da else None
        layers = base["layers"] if base else [{"id": uuid.uuid4().hex[:8], "nome": n, "colore": COLORS[i], "visibile": True, "bloccato": False, "ordine": i}
                                              for i, n in enumerate(DEFAULT_LAYERS)]
        doc = {"id": uuid.uuid4().hex, "org_id": admin["org_id"], "evento_id": eid, "nome": body.nome, "archiviato": False, "version": 1,
               "layers": layers, "features": (base or {}).get("features") or [], "center": (base or {}).get("center"), "zoom": (base or {}).get("zoom"),
               "created_by": admin.get("email"), "created_at": _now(), "updated_by": admin.get("email"), "updated_at": _now()}
        await db.planner_projects.insert_one({**doc})
        if base:  # la copia ha una distinta propria, indipendente dall'originale
            await bom_copy(admin["org_id"], base["id"], doc["id"])
        await audit(admin, "planner_project_create", detail=f"{eid} · {body.nome}")
        return {k: v for k, v in doc.items() if k != "features"}

    @r.get("/projects/{pid}")
    async def get_project(pid: str, user: dict = Depends(member_dep)):
        return await project_of(user["org_id"], pid, user, write=False)

    @r.patch("/projects/{pid}")
    async def patch(pid: str, body: ProjectPatch, admin: dict = Depends(admin_dep)):
        await project_of(admin["org_id"], pid, admin)
        upd = {k: v for k, v in body.model_dump().items() if v is not None}
        await db.planner_projects.update_one({"org_id": admin["org_id"], "id": pid}, {"$set": {**upd, "updated_at": _now()}})
        return {"ok": True}

    @r.put("/projects/{pid}/content")
    async def save(pid: str, body: SaveIn, admin: dict = Depends(admin_dep)):
        """Salvataggio con controllo versione: se un altro utente ha salvato nel frattempo → 409, nessuna sovrascrittura."""
        if len(body.features) > MAX_FEATURES:
            raise HTTPException(status_code=400, detail=f"Massimo {MAX_FEATURES} oggetti per progetto")
        cur = await project_of(admin["org_id"], pid, admin)
        res = await db.planner_projects.update_one({"org_id": admin["org_id"], "id": pid, "version": body.version},
                                                   {"$set": {"features": body.features, "layers": body.layers, "updated_at": _now(), "updated_by": admin.get("email")},
                                                    "$inc": {"version": 1}})
        if not res.modified_count:
            raise HTTPException(status_code=409, detail=f"Il progetto è stato modificato da {cur.get('updated_by')} alle {cur.get('updated_at', '')[11:16]}: ricarica prima di salvare")
        await db.planner_revisions.insert_one({"id": uuid.uuid4().hex, "org_id": admin["org_id"], "project_id": pid, "version": body.version + 1,
                                               "features": body.features, "layers": body.layers, "by": admin.get("email"), "at": _now(), "n": len(body.features)})
        old = await db.planner_revisions.find({"org_id": admin["org_id"], "project_id": pid}, {"_id": 0, "id": 1}).sort("at", -1).skip(MAX_REVISIONS).to_list(1000)
        if old:
            await db.planner_revisions.delete_many({"id": {"$in": [o["id"] for o in old]}})
        return {"version": body.version + 1}

    @r.get("/projects/{pid}/revisions")
    async def revisions(pid: str, user: dict = Depends(member_dep)):
        await project_of(user["org_id"], pid, user, write=False)
        return {"revisions": await db.planner_revisions.find({"org_id": user["org_id"], "project_id": pid}, {"_id": 0, "features": 0, "layers": 0}).sort("at", -1).to_list(MAX_REVISIONS)}

    @r.post("/projects/{pid}/revisions/{rid}/restore")
    async def restore(pid: str, rid: str, admin: dict = Depends(admin_dep)):
        cur = await project_of(admin["org_id"], pid, admin)
        rev = await db.planner_revisions.find_one({"org_id": admin["org_id"], "project_id": pid, "id": rid}, {"_id": 0})
        if not rev:
            raise HTTPException(status_code=404, detail="Revisione non trovata")
        return await save(pid, SaveIn(version=cur["version"], features=rev["features"], layers=rev["layers"]), admin)

    async def ensure():
        await db.planner_bom.create_index([("org_id", 1), ("project_id", 1)], unique=True)
        await db.planner_projects.create_index([("org_id", 1), ("evento_id", 1)])
        await db.planner_projects.create_index("id", unique=True)
        await db.planner_revisions.create_index([("org_id", 1), ("project_id", 1), ("at", -1)])

    return {"router": r, "ensure": ensure}
