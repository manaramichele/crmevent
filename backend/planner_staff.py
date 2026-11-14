"""Event Planner — percorsi da Percorsi Eventi e postazioni Staff/Volontari collegate ai turni (shifts) dell'evento."""
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

import event_routes as EVR
import planner_bom as BOM


class StationIn(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    tipologia: Optional[str] = Field(default=None, max_length=60)
    kind: str = Field(default="generica", pattern="^(team|staff|volontario|generica)$")
    ruolo: Optional[str] = Field(default=None, max_length=80)
    data: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    ora_inizio: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    ora_fine: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    note: Optional[str] = Field(default=None, max_length=500)
    team_id: Optional[str] = None
    persona_ids: List[str] = Field(default_factory=list, max_length=200)
    force: bool = False


def _now():
    return datetime.now(timezone.utc).isoformat()


def _overlap(a, b):
    if not a.get("data") or not b.get("data") or a["data"] != b["data"]:
        return False
    a0, a1, b0, b1 = a.get("ora_inizio") or "00:00", a.get("ora_fine") or "23:59", b.get("ora_inizio") or "00:00", b.get("ora_fine") or "23:59"
    return a0 < b1 and b0 < a1


def attach(r, db, audit, member_dep, admin_dep, project_of, event_of, resolve, read_rec, org_logo):
    async def people(org_id, eid):
        staff = await db.staff.find({"org_id": org_id, "evento_id": eid}, {"_id": 0}).to_list(3000)
        pids = list({s["persona_id"] for s in staff if s.get("persona_id")})
        pers = {p["id"]: p for p in await db.persons.find({"org_id": org_id, "id": {"$in": pids}}, {"_id": 0, "id": 1, "nome": 1, "cognome": 1}).to_list(3000)}
        teams = await db.teams.find({"org_id": org_id, "evento_id": eid}, {"_id": 0, "id": 1, "nome": 1, "responsabile_id": 1, "area": 1}).to_list(500)
        tname = {t["id"]: t["nome"] for t in teams}
        shifts = await db.shifts.find({"org_id": org_id, "evento_id": eid}, {"_id": 0}).to_list(5000)
        out = []
        for s in staff:
            p = pers.get(s.get("persona_id"))
            if not p:
                continue
            out.append({"persona_id": p["id"], "nome": f"{p.get('nome') or ''} {p.get('cognome') or ''}".strip(), "categoria": s.get("categoria") or "staff",
                        "ruolo": s.get("ruolo"), "team_id": s.get("team_id"), "team_nome": tname.get(s.get("team_id")), "stato": s.get("stato"),
                        "disponibilita": " ".join(x for x in (s.get("data_arrivo"), s.get("ora_arrivo"), "–" if s.get("data_partenza") else None, s.get("data_partenza"), s.get("ora_partenza")) if x) or None,
                        "turni": [{"data": x.get("data"), "ora_inizio": x.get("ora_inizio"), "ora_fine": x.get("ora_fine"), "luogo": x.get("luogo") or x.get("area")} for x in shifts if x.get("persona_id") == p["id"]]})
        nm = {x["persona_id"]: x["nome"] for x in out}
        for t in teams:
            t["membri"] = [x for x in out if x["team_id"] == t["id"]]
            t["responsabile"] = nm.get(t.get("responsabile_id")) or (lambda p: f"{p.get('nome', '')} {p.get('cognome', '')}".strip() if p else None)(pers.get(t.get("responsabile_id")))
        return {"teams": teams, "people": sorted(out, key=lambda x: x["nome"].lower())}

    @r.get("/events/{eid}/people")
    async def event_people(eid: str, user: dict = Depends(member_dep)):
        await event_of(user["org_id"], eid, user, write=False)
        return await people(user["org_id"], eid)

    @r.get("/events/{eid}/routes")
    async def event_routes(eid: str, user: dict = Depends(member_dep)):
        await event_of(user["org_id"], eid, user, write=False)
        return {"routes": EVR.public(await EVR.list_routes(db, user["org_id"], eid, resolve))}

    @r.get("/events/{eid}/routes/{map_id}")
    async def route_geometry(eid: str, map_id: str, user: dict = Depends(member_dep)):
        await event_of(user["org_id"], eid, user, write=False)
        rt = next((x for x in await EVR.list_routes(db, user["org_id"], eid, resolve) if x["map_id"] == map_id), None)
        if not rt:
            raise HTTPException(status_code=404, detail="Percorso non trovato in Percorsi Eventi")
        data, _ = await read_rec(rt["_rec"])
        try:
            c = EVR.coords(data, rt["filename"])
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Percorso {rt['format']} non leggibile: {e}")
        return {"map_id": map_id, "nome": rt["nome"], "format": rt["format"], "version": rt["version"], "coordinates": [[p[0], p[1]] for p in c],
                "has_elevation": any(p[2] is not None for p in c)}

    async def station_shifts(org_id, pid):
        out = {}
        for s in await db.shifts.find({"org_id": org_id, "planner_project_id": pid}, {"_id": 0}).to_list(5000):
            out.setdefault(s["planner_station_id"], []).append(s)
        return out

    @r.get("/projects/{pid}/stations")
    async def stations(pid: str, user: dict = Depends(member_dep)):
        await project_of(user["org_id"], pid, user, write=False)
        return {"stations": await station_shifts(user["org_id"], pid)}

    @r.post("/projects/{pid}/stations/{fid}")
    async def save_station(pid: str, fid: str, body: StationIn, admin: dict = Depends(admin_dep)):
        """Collega la postazione ai turni Staff e Volontari: un turno per persona, nessun duplicato, avviso se la persona ha un turno sovrapposto altrove."""
        p = await project_of(admin["org_id"], pid, admin)
        eid, org = p["evento_id"], admin["org_id"]
        ppl = await people(org, eid)
        known = {x["persona_id"] for x in ppl["people"]}
        ids = list(dict.fromkeys(body.persona_ids))
        if any(i not in known for i in ids):
            raise HTTPException(status_code=400, detail="Persona non presente tra lo staff/volontari dell'evento")
        if body.team_id and body.team_id not in {t["id"] for t in ppl["teams"]}:
            raise HTTPException(status_code=400, detail="Team non trovato nell'evento")
        info = {"data": body.data, "ora_inizio": body.ora_inizio, "ora_fine": body.ora_fine}
        others = await db.shifts.find({"org_id": org, "evento_id": eid, "persona_id": {"$in": ids}, "planner_station_id": {"$ne": fid}}, {"_id": 0}).to_list(2000)
        nm = {x["persona_id"]: x["nome"] for x in ppl["people"]}
        conflicts = [{"persona_id": s["persona_id"], "nome": nm.get(s["persona_id"]), "data": s.get("data"), "ora_inizio": s.get("ora_inizio"), "ora_fine": s.get("ora_fine"),
                      "luogo": s.get("luogo") or s.get("area")} for s in others if _overlap(s, info)]
        if conflicts and not body.force:
            raise HTTPException(status_code=409, detail={"code": "staff_conflict", "message": "Alcune persone hanno gi\u00e0 un turno sovrapposto", "conflicts": conflicts})
        fields = {"luogo": body.nome, "area": body.tipologia, "ruolo": body.ruolo, **info, "note": body.note, "team_id": body.team_id,
                  "planner_project_id": pid, "planner_station_id": fid, "updated_at": _now()}
        cur = {s["persona_id"]: s for s in await db.shifts.find({"org_id": org, "planner_project_id": pid, "planner_station_id": fid}, {"_id": 0}).to_list(500)}
        for i in ids:
            if i in cur:
                await db.shifts.update_one({"org_id": org, "id": cur[i]["id"]}, {"$set": fields})
            else:
                await db.shifts.insert_one({"id": uuid.uuid4().hex, "org_id": org, "evento_id": eid, "persona_id": i, "created_at": _now(), "source": "event_planner", **fields})
        gone = [s["id"] for k, s in cur.items() if k not in ids]
        if gone:
            await db.shifts.delete_many({"org_id": org, "id": {"$in": gone}})
        await audit(admin, "planner_station_assign", detail=f"{pid} \u00b7 {body.nome} \u00b7 {len(ids)} persone")
        return {"shifts": await db.shifts.find({"org_id": org, "planner_project_id": pid, "planner_station_id": fid}, {"_id": 0}).to_list(500), "conflicts": conflicts}

    async def cleanup(org_id, pid, features):
        """Postazioni rimosse dal progetto: si eliminano solo i turni creati da Event Planner per quelle postazioni."""
        ids = [f.get("properties", {}).get("id") for f in features or []]
        await db.shifts.delete_many({"org_id": org_id, "planner_project_id": pid, "planner_station_id": {"$nin": ids}})

    async def summary(org_id, eid, pid=None):
        q = {"org_id": org_id, "evento_id": eid, "archiviato": {"$ne": True}, **({"id": pid} if pid else {})}
        projs = await db.planner_projects.find(q, {"_id": 0, "id": 1, "nome": 1, "features": 1}).to_list(200)
        ppl = await people(org_id, eid)
        nm, cat = {x["persona_id"]: x["nome"] for x in ppl["people"]}, {x["persona_id"]: x["categoria"] for x in ppl["people"]}
        tn = {t["id"]: t["nome"] for t in ppl["teams"]}
        shifts = await db.shifts.find({"org_id": org_id, "evento_id": eid, "planner_station_id": {"$exists": True}}, {"_id": 0}).to_list(5000)
        rows, seen = [], set()
        for p in projs:
            for f in p.get("features") or []:
                st = (f.get("properties") or {}).get("station")
                if not st:
                    continue
                sh = [s for s in shifts if s.get("planner_station_id") == f["properties"]["id"] and s["id"] not in seen]
                seen.update(s["id"] for s in sh)
                rows.append({"progetto": p["nome"], "station_id": f["properties"]["id"], "nome": st.get("nome") or f["properties"].get("nome"), "tipologia": st.get("tipologia"),
                             "kind": st.get("kind"), "team": tn.get(st.get("team_id")), "ruolo": (sh[0].get("ruolo") if sh else None) or st.get("ruolo"),
                             "data": (sh[0].get("data") if sh else None) or st.get("data"), "ora_inizio": (sh[0].get("ora_inizio") if sh else None) or st.get("ora_inizio"),
                             "ora_fine": (sh[0].get("ora_fine") if sh else None) or st.get("ora_fine"), "note": st.get("note"),
                             "persone": [{"nome": nm.get(s["persona_id"], "?"), "categoria": cat.get(s["persona_id"])} for s in sh]})
        allsh = await db.shifts.find({"org_id": org_id, "evento_id": eid}, {"_id": 0}).to_list(5000)
        conf = []
        for i, a in enumerate(allsh):
            for b in allsh[i + 1:]:
                if a["persona_id"] == b["persona_id"] and _overlap(a, b) and (a.get("planner_station_id") or b.get("planner_station_id")):
                    conf.append({"nome": nm.get(a["persona_id"], "?"), "data": a.get("data"), "a": f"{a.get('luogo') or a.get('area')} {a.get('ora_inizio') or ''}-{a.get('ora_fine') or ''}",
                                 "b": f"{b.get('luogo') or b.get('area')} {b.get('ora_inizio') or ''}-{b.get('ora_fine') or ''}"})
        pc = [x for r_ in rows for x in r_["persone"]]
        return {"rows": rows, "conflicts": conf, "counts": {"postazioni": len(rows), "coperte": sum(1 for x in rows if x["persone"]), "scoperte": sum(1 for x in rows if not x["persone"]),
                                                            "team": len({x["team"] for x in rows if x["team"]}), "staff": len({x["nome"] for x in pc if x["categoria"] == "staff"}),
                                                            "volontari": len({x["nome"] for x in pc if x["categoria"] == "volontario"})}}

    @r.get("/events/{eid}/assignments")
    async def assignments(eid: str, project: Optional[str] = None, user: dict = Depends(member_dep)):
        await event_of(user["org_id"], eid, user, write=False)
        return await summary(user["org_id"], eid, project)

    @r.get("/events/{eid}/assignments/export.{ext}")
    async def export_assignments(eid: str, ext: str, project: Optional[str] = None, inline: int = 0, user: dict = Depends(member_dep)):
        ev = await event_of(user["org_id"], eid, user, write=False)
        s = await summary(user["org_id"], eid, project)
        orari = lambda x: f"{x['data'] or ''} {x['ora_inizio'] or ''}{'–' + x['ora_fine'] if x['ora_fine'] else ''}".strip()  # noqa: E731
        who = lambda x: ", ".join(filter(None, [x["team"] and f"Team {x['team']}"] + [p["nome"] for p in x["persone"]])) or "Senza assegnazione"  # noqa: E731
        name = f"assegnazioni-{ev['nome']}"
        if ext == "xlsx":
            data = [[x["progetto"], x["nome"], x["tipologia"] or "", who(x), x["ruolo"] or "", x["data"] or "", x["ora_inizio"] or "", x["ora_fine"] or "", x["note"] or ""] for x in s["rows"]]
            out = BOM.xlsx(f"{ev['nome']} \u2013 Riepilogo assegnazioni", [("Assegnazioni", ["Progetto", "Postazione", "Tipologia", "Team / persone", "Ruolo", "Data", "Inizio", "Fine", "Note"], data, None)])
            mt = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        elif ext == "pdf":
            g = BOM._groups([{**x, "categoria": x["progetto"]} for x in s["rows"]], lambda x: [x["nome"], who(x), x["ruolo"] or "", orari(x), x["note"] or ""])
            out = BOM.pdf(await org_logo(user["org_id"]), ev["nome"], "Riepilogo assegnazioni staff e volontari", g, ["Postazione", "Team / persone", "Ruolo", "Orario", "Note"], [0.2, 0.32, 0.13, 0.15, 0.2])
            mt = "application/pdf"
        else:
            raise HTTPException(status_code=404, detail="Formato non disponibile")
        from fastapi.responses import Response
        return Response(content=out, media_type=mt, headers={"Content-Disposition": f'{"inline" if inline else "attachment"}; filename="{BOM._fname(name)}.{ext}"'})

    return cleanup
