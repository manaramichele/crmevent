"""Copertura oraria Staff / Volontari: calcolata al volo da disponibilità (availabilities.days) e assegnazioni (staff) esistenti."""
import hashlib
import io
import json
import math
import re
import unicodedata
import uuid
from datetime import date, datetime, timedelta
from typing import List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

ROME = ZoneInfo("Europe/Rome")
TIFFANY = "#0ABAB5"
STAFF_CATS = {"staff", "collaboratore"}
CONFIRMED_CATS = STAFF_CATS | {"volontario"}


def _fold(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def _hm(s):
    m = re.match(r"^\s*(\d{1,2})[:.](\d{2})", str(s or ""))
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    return h * 60 + mi if 0 <= h <= 24 and 0 <= mi < 60 else None


def _d(s):
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _abs(day: date, minutes: int) -> int:
    return day.toordinal() * 1440 + minutes


def _fmt(m: int) -> str:
    m %= 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def _merge(iv):
    out = []
    for a, b in sorted(iv):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


class NeedIn(BaseModel):
    evento_id: str
    mansione: str = Field(min_length=1, max_length=80)
    date: str
    start: str
    end: str
    needed: int = Field(ge=1, le=10000)


class FasciaNeedIn(BaseModel):
    evento_id: str
    date: str = Field(min_length=10, max_length=10)
    fascia: str = Field(pattern="^(mattina|pomeriggio)$")
    needed: int = Field(ge=0, le=10000)


FX_LABEL = {"mattina": "Mattina", "pomeriggio": "Pomeriggio"}


class TeamNeedIn(BaseModel):
    evento_id: str
    date: str = Field(min_length=10, max_length=10)
    fascia: str = Field(pattern="^(mattina|pomeriggio)$")
    team_id: str
    needed: int = Field(ge=0, le=10000)


class AssignIn(BaseModel):
    evento_id: str
    date: str = Field(min_length=10, max_length=10)
    fascia: str = Field(pattern="^(mattina|pomeriggio)$")
    team_id: str
    persona_id: str
    force: bool = False


class BulkFasciaIn(BaseModel):
    evento_id: str
    date: str = Field(min_length=10, max_length=10)
    fascia: str = Field(pattern="^(mattina|pomeriggio)$")
    team_ids: List[str] = Field(min_length=1, max_length=200)
    token: Optional[str] = None


class ConfigIn(BaseModel):
    yellow_margin_pct: int = Field(ge=0, le=100)


def build(db, deps: dict):
    r = APIRouter(prefix="/api")
    require = deps["require_admin"]
    avail_days = deps["avail_days"]
    record_audit = deps["record_audit"]

    async def _yellow(org):
        st = await db.settings.find_one({"id": org}, {"_id": 0, "coverage_yellow_pct": 1}) or {}
        return int(st.get("coverage_yellow_pct", 10))

    async def _load(org, evento_id, mansione=None, team_id=None, gruppo=None, cat="all"):
        """Persone filtrate con intervalli assoluti (minuti) e date senza orario."""
        ev = await db.events.find_one({"org_id": org, "id": evento_id}, {"_id": 0})
        if not ev:
            raise HTTPException(status_code=404, detail="Evento non trovato")
        links = [x for x in await db.staff.find({"org_id": org, "evento_id": evento_id}, {"_id": 0}).to_list(20000)
                 if x.get("categoria") in CONFIRMED_CATS and x.get("stato") == "confermato"]  # solo Staff/Volontari confermati per QUESTO evento
        conf = {x["persona_id"] for x in links if x.get("persona_id")}
        avs = await db.availabilities.find({"org_id": org, "evento_id": evento_id, "persona_id": {"$in": list(conf)}}, {"_id": 0}).to_list(20000)
        latest = {}
        for a in avs:  # la disponibilità più recente sostituisce le precedenti della stessa persona
            k = a["persona_id"]
            if k not in latest or str(a.get("updated_at") or a.get("created_at") or "") > str(latest[k].get("updated_at") or latest[k].get("created_at") or ""):
                latest[k] = a
        pids = conf
        persons = {p["id"]: p for p in await db.persons.find({"org_id": org, "id": {"$in": list(pids)}, "archiviato": {"$ne": True}},
                                                              {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "cellulare": 1, "taglia": 1, "gruppo_appartenenza": 1}).to_list(20000)}
        teams = {t["id"]: t.get("nome") for t in await db.teams.find({"org_id": org, "evento_id": evento_id}, {"_id": 0, "id": 1, "nome": 1}).to_list(2000)}
        by_p = {}
        for x in links:
            by_p.setdefault(x["persona_id"], []).append(x)
        out = []
        for pid, p in persons.items():
            ls, av = by_p.get(pid, []), latest.get(pid)
            cats = {x.get("categoria") for x in ls}
            roles = sorted({x["ruolo"] for x in ls if x.get("ruolo")})
            pref = (av or {}).get("preferenza_attivita") or next((x.get("preferenza") for x in ls if x.get("preferenza")), None)
            tids = {x.get("team_id") for x in ls if x.get("team_id")}
            if cat == "staff" and not cats & STAFF_CATS:
                continue
            if cat == "volontari" and "volontario" not in cats:
                continue
            if mansione and mansione not in roles and pref != mansione:
                continue
            if team_id and team_id not in tids:
                continue
            if gruppo and p.get("gruppo_appartenenza") != gruppo:
                continue
            iv, tbc = [], set()
            for dd in (av or {}).get("days") or []:
                day = _d(dd.get("date"))
                if not day or dd.get("disponibile") is False:
                    continue
                fs = dd.get("fasce") or []
                if fs:
                    for fz in fs:
                        a, b = _hm(fz.get("start")), _hm(fz.get("end"))
                        if a is None or b is None:
                            tbc.add(day.isoformat())
                        else:
                            iv.append((_abs(day, a), _abs(day, b if b > a else b + 1440)))
                    continue
                a, b = _hm(dd.get("dalle")), _hm(dd.get("alle"))
                if a is None or b is None:
                    tbc.add(day.isoformat())
                    continue
                if b <= a:  # attraversa la mezzanotte
                    b += 1440
                iv.append((_abs(day, a), _abs(day, b)))
            if not av:  # Staff senza modulo: usa arrivo/partenza dell'assegnazione se completi
                for x in ls:
                    d1, d2, a, b = _d(x.get("data_arrivo")), _d(x.get("data_partenza")) or _d(x.get("data_arrivo")), _hm(x.get("ora_arrivo")), _hm(x.get("ora_partenza"))
                    if d1 and d2 and a is not None and b is not None and _abs(d2, b) > _abs(d1, a):
                        iv.append((_abs(d1, a), _abs(d2, b)))
                    elif d1:
                        tbc.add(d1.isoformat())
            pdays = {dd.get("date"): dd for dd in (av or {}).get("days") or [] if dd.get("date") and dd.get("disponibile") is not False}
            out.append({"has_av": bool(av), "days": pdays, "id": pid, "nome": p.get("nome") or "", "cognome": p.get("cognome") or "", "cellulare": p.get("cellulare") or "",
                        "taglia": p.get("taglia") or "", "gruppo": p.get("gruppo_appartenenza") or "", "mansioni": roles, "preferenza": pref,
                        "team": ", ".join(sorted({teams[t] for t in tids if t in teams})), "team_ids": sorted(tids),
                        "categoria": "Staff" if cats & STAFF_CATS else ("Volontario" if "volontario" in cats else "Da classificare"),
                        "assigned": bool(roles if not mansione else mansione in roles), "iv": _merge(iv), "tbc": tbc})
        out.sort(key=lambda x: (_fold(x["cognome"]), _fold(x["nome"])))
        return ev, out

    def _slots(day: date, people, step, lo=None, hi=None):
        d0 = _abs(day, 0)
        if lo is None:
            pts = [max(a, d0) - d0 for p in people for a, b in p["iv"] if a < d0 + 1440 and b > d0] + \
                  [min(b, d0 + 1440) - d0 for p in people for a, b in p["iv"] if a < d0 + 1440 and b > d0]
            lo, hi = (min(pts) // 60 * 60, min(1440, math.ceil(max(pts) / 60) * 60)) if pts else (480, 1200)
        res = []
        for s in range(lo, hi, step):
            a, b = d0 + s, d0 + s + step
            full, part = [], []
            for p in people:
                ov = sum(max(0, min(b, y) - max(a, x)) for x, y in p["iv"])
                if ov >= step:
                    full.append(p["id"])
                elif ov > 0:
                    part.append(p["id"])
            res.append({"start": _fmt(s), "end": _fmt(s + step) if s + step < 1440 else "24:00", "s": s, "full": full, "partial": part})
        return res

    async def _needs(org, evento_id, mansione=None):
        q = {"org_id": org, "evento_id": evento_id}
        if mansione:
            q["mansione"] = mansione
        return await db.coverage_needs.find(q, {"_id": 0}).to_list(5000)

    def _apply_needs(day_iso, slots, needs, people, pct, step):
        assigned = {p["id"] for p in people if p["assigned"]}
        for sl in slots:
            n = 0
            for nd in needs:
                if nd["date"] != day_iso:
                    continue
                a, b = _hm(nd["start"]), _hm(nd["end"])
                b = 1440 if b == 0 else b
                if a is not None and b is not None and a < sl["s"] + step and b > sl["s"]:
                    n += int(nd["needed"])
            avail = len(sl["full"]) + len(sl["partial"])
            sl["available"] = avail
            sl["assigned"] = len([i for i in sl["full"] + sl["partial"] if i in assigned])
            sl["needed"] = n or None
            if n:
                margin = max(1, math.ceil(n * pct / 100))
                sl["status"] = "red" if avail < n else ("yellow" if avail < n + margin else "green")
            else:
                sl["status"] = None
        return slots

    async def _day(org, evento_id, day_iso, step, mansione, team_id, gruppo, cat):
        if step not in (15, 30, 60):
            raise HTTPException(status_code=400, detail="Intervallo non valido")
        day = _d(day_iso)
        if not day:
            raise HTTPException(status_code=400, detail="Data non valida")
        ev, people = await _load(org, evento_id, mansione, team_id, gruppo, cat)
        slots = _apply_needs(day_iso, _slots(day, people, step), await _needs(org, evento_id, mansione), people, await _yellow(org), step)
        d0 = _abs(day, 0)
        today = [p for p in people if any(a < d0 + 1440 and b > d0 for a, b in p["iv"])]
        tbc = [p for p in people if day_iso in p["tbc"] and p not in today]
        counts = [s["available"] for s in slots]
        best = max(slots, key=lambda s: s["available"]) if slots else None
        worst = min(slots, key=lambda s: s["available"]) if slots else None
        pmap = {}
        for p in today + tbc:
            ivs = [f"{_fmt(a - d0) if a >= d0 else '(giorno prima) ' + _fmt(a)}–{_fmt(b - d0) if b <= d0 + 1440 else _fmt(b) + ' (giorno dopo)'}" for a, b in p["iv"] if a < d0 + 1440 and b > d0]
            pmap[p["id"]] = {k: p[k] for k in ("id", "nome", "cognome", "cellulare", "taglia", "gruppo", "mansioni", "preferenza", "team", "categoria", "assigned")}
            pmap[p["id"]]["orario"] = ", ".join(ivs) or "Orario da confermare"
        return ev, {"evento": {"id": ev["id"], "nome": ev.get("nome")}, "date": day_iso, "step": step, "slots": slots, "people": pmap,
                    "tbc": [p["id"] for p in tbc],
                    "kpis": {"day_people": len(today), "max": max(counts) if counts else 0, "min": min(counts) if counts else 0,
                             "best": f"{best['start']}–{best['end']}" if best else None, "worst": f"{worst['start']}–{worst['end']}" if worst else None,
                             "tbc": len(tbc)}}

    def _event_days(ev, people):
        ds = {d for p in people for a, b in p["iv"] for d in range(a // 1440, (b - 1) // 1440 + 1)}
        ds = {date.fromordinal(x).isoformat() for x in ds} | {d for p in people for d in p["tbc"]}
        s, e = _d(ev.get("data_inizio")), _d(ev.get("data_fine")) or _d(ev.get("data_inizio"))
        if s and e and 0 <= (e - s).days <= 31:
            ds |= {(s + timedelta(days=i)).isoformat() for i in range((e - s).days + 1)}
        return sorted(ds)[:31]

    @r.get("/staff-coverage")
    async def coverage(evento_id: str, date: Optional[str] = None, step: int = 60, mansione: Optional[str] = None, team_id: Optional[str] = None,
                       gruppo: Optional[str] = None, cat: str = "all", user: dict = Depends(require)):
        org = user["org_id"]
        if not date:
            ev, people = await _load(org, evento_id)
            days = _event_days(ev, people)
            date = days[0] if days else datetime.now(ROME).date().isoformat()
        ev, out = await _day(org, evento_id, date, step, mansione or None, team_id or None, gruppo or None, cat)
        _, allp = await _load(org, evento_id)
        out["days"] = _event_days(ev, allp)
        out["mansioni"] = sorted({m for p in allp for m in p["mansioni"]} | {p["preferenza"] for p in allp if p["preferenza"]} |
                                 {n["mansione"] for n in await _needs(org, evento_id)}, key=_fold)
        out["yellow_margin_pct"] = await _yellow(org)
        return out

    @r.get("/staff-coverage/matrix")
    async def matrix(evento_id: str, step: int = 60, mansione: Optional[str] = None, team_id: Optional[str] = None,
                     gruppo: Optional[str] = None, cat: str = "all", user: dict = Depends(require)):
        org = user["org_id"]
        if step not in (15, 30, 60):
            raise HTTPException(status_code=400, detail="Intervallo non valido")
        ev, people = await _load(org, evento_id, mansione or None, team_id or None, gruppo or None, cat)
        days = _event_days(ev, people)
        per = {d: _slots(_d(d), people, step) for d in days}
        lo = min((s[0]["s"] for s in per.values() if s), default=480)
        hi = max((s[-1]["s"] + step for s in per.values() if s), default=1200)
        rows = []
        cols = {d: _slots(_d(d), people, step, lo, hi) for d in days}
        for i, s in enumerate(range(lo, hi, step)):
            rows.append({"start": _fmt(s), "end": _fmt(s + step) if s + step < 1440 else "24:00",
                         "cells": [len(cols[d][i]["full"]) + len(cols[d][i]["partial"]) for d in days]})
        return {"days": days, "rows": rows, "tbc": {d: sum(1 for p in people if d in p["tbc"]) for d in days}}

    def _classify(p, iso, fid, a, b):
        """(copertura, orario mostrato, vecchio formato, orari fascia cambiati) oppure None."""
        if p["has_av"]:
            dd = p["days"].get(iso)
            if not dd:
                return None
            fs = dd.get("fasce") or []
            if fs:
                hit = next((x for x in fs if x.get("id") == fid), None)
                if not hit:
                    return None
                changed = a is not None and b is not None and (_hm(hit.get("start")), _hm(hit.get("end"))) != (a, b)
                return "complete", (f"{hit.get('start')}–{hit.get('end')}" if hit.get("start") and hit.get("end") else FX_LABEL[fid]), False, changed
            x, y = _hm(dd.get("dalle")), _hm(dd.get("alle"))
            orig = f"{dd.get('dalle') or '?'}–{dd.get('alle') or '?'}" if (dd.get("dalle") or dd.get("alle")) else "Orario non indicato"
            if x is None or y is None or a is None or b is None:
                return "tbc", orig, True, False
            if y <= x:
                y += 1440
            if min(b, y) - max(a, x) <= 0:
                return None
            return ("complete" if x <= a and y >= b else "partial"), orig, True, False
        if a is None or b is None:
            return ("tbc", "Orario da confermare", False, False) if iso in p["tbc"] else None
        d0 = _abs(_d(iso), 0)
        ov = sum(max(0, min(d0 + b, y) - max(d0 + a, x)) for x, y in p["iv"])
        if ov >= b - a:
            return "complete", "Da assegnazione", False, False
        if ov > 0:
            ivs = [f"{_fmt(max(x, d0 + a) - d0)}–{_fmt(min(y, d0 + b) - d0)}" for x, y in p["iv"] if min(y, d0 + b) > max(x, d0 + a)]
            return "partial", ", ".join(ivs), False, False
        return ("tbc", "Orario da confermare", False, False) if iso in p["tbc"] else None

    def _legacy(people):
        out = []
        for p in people:
            ds = [{"date": iso, "orario": f"{dd.get('dalle') or '?'}–{dd.get('alle') or '?'}" if (dd.get("dalle") or dd.get("alle")) else "Orario non indicato"}
                  for iso, dd in sorted(p["days"].items()) if not dd.get("fasce")]
            if ds:
                out.append({"id": p["id"], "nome": p["nome"], "cognome": p["cognome"], "categoria": p["categoria"], "days": ds})
        return out

    async def _fasce(org, evento_id, team_id=None, gruppo=None, cat="all"):
        """Copertura per giorno × fascia × Team: disponibili (confermati del team), assegnati (coverage_assignments), necessari, mancanti."""
        ev, people = await _load(org, evento_id, None, None, gruppo, cat)
        all_teams = sorted(await db.teams.find({"org_id": org, "evento_id": evento_id}, {"_id": 0, "id": 1, "nome": 1}).to_list(2000), key=lambda t: _fold(t.get("nome")))
        tname = {t["id"]: t.get("nome") or "" for t in all_teams}
        teams = [t for t in all_teams if not team_id or t["id"] == team_id]
        needs = {(n["date"], n["fascia"], n["team_id"]): int(n["needed"]) for n in await db.coverage_team_needs.find({"org_id": org, "evento_id": evento_id}, {"_id": 0}).to_list(20000)}
        asg = {(x["date"], x["fascia"], x["persona_id"]): x for x in await db.coverage_assignments.find({"org_id": org, "evento_id": evento_id}, {"_id": 0}).to_list(50000)}
        pmap = {p["id"]: p for p in people}
        rows = []
        for d in avail_days(ev):
            for s in d.get("fasce") or []:
                a, b = _hm(s.get("start")), _hm(s.get("end"))
                if a is not None and b is not None and b <= a:
                    b += 1440
                for t in teams:
                    ppl = []
                    for p in people:
                        if t["id"] not in p["team_ids"]:
                            continue
                        c = _classify(p, d["date"], s["id"], a, b) or ("none", "Non disponibile", False, False)
                        x = asg.get((d["date"], s["id"], p["id"]))
                        mine = bool(x and x["team_id"] == t["id"])
                        ppl.append({k: p[k] for k in ("id", "nome", "cognome", "gruppo", "mansioni", "categoria")} |
                                   {"cov": c[0], "orario": c[1], "legacy": c[2], "changed": c[3], "assigned": mine, "forced": bool(mine and x.get("forced")),
                                    "assigned_other": tname.get(x["team_id"], "altro team") if x and not mine else None})
                    orphans = sum(1 for (dd, ff, pid), x in asg.items() if dd == d["date"] and ff == s["id"] and x["team_id"] == t["id"]
                                  and (pid not in pmap or t["id"] not in pmap[pid]["team_ids"]))
                    n = needs.get((d["date"], s["id"], t["id"])) or None
                    nas = sum(x["assigned"] for x in ppl)
                    rows.append({"date": d["date"], "fascia": s["id"], "label": FX_LABEL[s["id"]], "start": s.get("start"), "end": s.get("end"),
                                 "team_id": t["id"], "team": t.get("nome") or "", "available": sum(x["cov"] == "complete" for x in ppl),
                                 "partial": sum(x["cov"] == "partial" for x in ppl), "tbc": sum(x["cov"] == "tbc" for x in ppl), "assigned": nas,
                                 "needed": n, "missing": max(0, n - nas) if n else None, "status": ("green" if nas >= n else "red") if n else None,
                                 "orphans": orphans, "changed": sum(x["changed"] for x in ppl),
                                 "people": sorted(ppl, key=lambda x: (_fold(x["cognome"]), _fold(x["nome"])))})
        return ev, rows, all_teams

    @r.get("/staff-coverage/fasce")
    async def fasce(evento_id: str, team_id: Optional[str] = None, gruppo: Optional[str] = None, cat: str = "all", user: dict = Depends(require)):
        org = user["org_id"]
        ev, rows, teams = await _fasce(org, evento_id, team_id or None, gruppo or None, cat)
        _, allp = await _load(org, evento_id)
        q = {"org_id": org, "evento_id": evento_id}
        warn = {"mansione_needs": await db.coverage_needs.count_documents(q), "fascia_needs": await db.coverage_fascia_needs.count_documents(q),
                "no_team": [{"id": p["id"], "nome": p["nome"], "cognome": p["cognome"], "mansioni": p["mansioni"]} for p in allp if not p["team_ids"]]}
        return {"evento": {"id": ev["id"], "nome": ev.get("nome")}, "rows": rows, "teams": teams, "legacy": _legacy(allp), "warnings": warn}

    async def _slot_check(org, evento_id, date_, fascia, team_id):
        ev = await db.events.find_one({"org_id": org, "id": evento_id}, {"_id": 0})
        if not ev:
            raise HTTPException(status_code=404, detail="Evento non trovato")
        if not await db.teams.find_one({"org_id": org, "evento_id": evento_id, "id": team_id}, {"_id": 1}):
            raise HTTPException(status_code=404, detail="Team non trovato per questo evento")
        day = next((d for d in avail_days(ev) if d["date"] == date_), None)
        sl = next((s for s in (day or {}).get("fasce") or [] if s["id"] == fascia), None)
        if not sl:
            raise HTTPException(status_code=400, detail="Fascia non attiva in questo giorno")
        return ev, sl

    @r.put("/staff-coverage/team-needs")
    async def team_need_put(body: TeamNeedIn, user: dict = Depends(require)):
        org = user["org_id"]
        await _slot_check(org, body.evento_id, body.date, body.fascia, body.team_id)
        q = {"org_id": org, "evento_id": body.evento_id, "date": body.date, "fascia": body.fascia, "team_id": body.team_id}
        if body.needed:
            await db.coverage_team_needs.update_one(q, {"$set": {**q, "needed": body.needed, "updated_at": datetime.now(ROME).isoformat()}}, upsert=True)
        else:
            await db.coverage_team_needs.delete_one(q)
        return {"ok": True, "needed": body.needed or None}

    @r.post("/staff-coverage/assign")
    async def assign(body: AssignIn, user: dict = Depends(require)):
        org = user["org_id"]
        ev, sl = await _slot_check(org, body.evento_id, body.date, body.fascia, body.team_id)
        _, people = await _load(org, body.evento_id)
        p = next((x for x in people if x["id"] == body.persona_id), None)
        if not p:
            raise HTTPException(status_code=400, detail="Solo Staff e Volontari confermati per l'evento possono essere assegnati")
        if body.team_id not in p["team_ids"]:
            raise HTTPException(status_code=400, detail="La persona non fa parte di questo Team")
        a, b = _hm(sl.get("start")), _hm(sl.get("end"))
        if a is not None and b is not None and b <= a:
            b += 1440
        c = _classify(p, body.date, body.fascia, a, b)
        q = {"org_id": org, "evento_id": body.evento_id, "date": body.date, "fascia": body.fascia, "persona_id": body.persona_id}
        cur = await db.coverage_assignments.find_one(q, {"_id": 0})
        if not body.force:
            if cur and cur["team_id"] != body.team_id:
                t = await db.teams.find_one({"org_id": org, "id": cur["team_id"]}, {"_id": 0, "nome": 1}) or {}
                raise HTTPException(status_code=409, detail={"code": "other_team", "message": f"Già assegnata al Team {t.get('nome') or '?'} in questa fascia: confermi lo spostamento?"})
            if not c or c[0] != "complete":
                why = {"partial": f"copre solo in parte la fascia ({c[1]})" if c else "", "tbc": "orario da verificare"}.get(c[0] if c else "", "non ha dichiarato disponibilità per questa fascia")
                raise HTTPException(status_code=409, detail={"code": "availability", "message": f"{p['cognome']} {p['nome']} {why}: assegnare comunque?"})
        now = datetime.now(ROME).isoformat()
        await db.coverage_assignments.update_one(q, {"$set": {**q, "team_id": body.team_id, "forced": not (c and c[0] == "complete"), "updated_at": now, "updated_by": user.get("email")},
                                                     "$setOnInsert": {"id": uuid.uuid4().hex, "created_at": now}}, upsert=True)
        return {"ok": True}

    @r.delete("/staff-coverage/assign")
    async def unassign(evento_id: str, date: str, fascia: str, persona_id: str, user: dict = Depends(require)):
        res = await db.coverage_assignments.delete_one({"org_id": user["org_id"], "evento_id": evento_id, "date": date, "fascia": fascia, "persona_id": persona_id})
        return {"ok": True, "removed": res.deleted_count}

    @r.put("/staff-coverage/fascia-needs")
    async def fascia_need_put(body: FasciaNeedIn, user: dict = Depends(require)):
        org = user["org_id"]
        if not await db.events.find_one({"org_id": org, "id": body.evento_id}, {"_id": 1}):
            raise HTTPException(status_code=404, detail="Evento non trovato")
        if not _d(body.date):
            raise HTTPException(status_code=400, detail="Data non valida")
        q = {"org_id": org, "evento_id": body.evento_id, "date": body.date, "fascia": body.fascia}
        if body.needed:
            await db.coverage_fascia_needs.update_one(q, {"$set": {**q, "needed": body.needed, "updated_at": datetime.now(ROME).isoformat()}}, upsert=True)
        else:
            await db.coverage_fascia_needs.delete_one(q)
        return {"ok": True, "needed": body.needed or None}

    @r.get("/staff-coverage/needs")
    async def needs_list(evento_id: str, user: dict = Depends(require)):
        return sorted(await _needs(user["org_id"], evento_id), key=lambda n: (n["date"], n["start"], _fold(n["mansione"])))

    @r.post("/staff-coverage/needs")
    async def needs_add(body: NeedIn, user: dict = Depends(require)):
        org = user["org_id"]
        if not await db.events.find_one({"org_id": org, "id": body.evento_id}, {"_id": 1}):
            raise HTTPException(status_code=404, detail="Evento non trovato")
        a, b = _hm(body.start), _hm(body.end)
        if not _d(body.date) or a is None or b is None or (b <= a and b != 0):
            raise HTTPException(status_code=400, detail="Data o orario non validi")
        doc = {"id": uuid.uuid4().hex, "org_id": org, **body.model_dump(), "mansione": body.mansione.strip(), "created_at": datetime.now(ROME).isoformat()}
        await db.coverage_needs.insert_one(doc)
        doc.pop("_id", None)
        return doc

    @r.delete("/staff-coverage/needs/{nid}")
    async def needs_del(nid: str, user: dict = Depends(require)):
        res = await db.coverage_needs.delete_one({"org_id": user["org_id"], "id": nid})
        if not res.deleted_count:
            raise HTTPException(status_code=404, detail="Fabbisogno non trovato")
        return {"ok": True}

    @r.put("/staff-coverage/config")
    async def config_put(body: ConfigIn, user: dict = Depends(require)):
        await db.settings.update_one({"id": user["org_id"]}, {"$set": {"coverage_yellow_pct": body.yellow_margin_pct}}, upsert=True)
        return {"yellow_margin_pct": body.yellow_margin_pct}

    @r.get("/staff-coverage/export")
    async def export(evento_id: str, kind: str = "pdf", date: Optional[str] = None, step: int = 60, mansione: Optional[str] = None,
                     team_id: Optional[str] = None, gruppo: Optional[str] = None, cat: str = "all", mode: str = "summary", user: dict = Depends(require)):
        org = user["org_id"]
        o = await db.organizations.find_one({"id": org}, {"_id": 0, "nome": 1}) or {}
        if kind == "xlsx":
            ev, people = await _load(org, evento_id, mansione or None, team_id or None, gruppo or None, cat)
            data = _xlsx(ev, people)
            return Response(content=data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            headers={"Content-Disposition": f'attachment; filename="CRMEvent_Disponibilita_{_slug(ev.get("nome"))}.xlsx"'})
        if mode in ("fasce", "fasce_names"):
            ev, rows, _ = await _fasce(org, evento_id, team_id or None, gruppo or None, cat)
            if date:
                rows = [x for x in rows if x["date"] == date]
            pdf = _pdf_fasce(ev, o.get("nome") or "", rows, names=(mode == "fasce_names"))
            return Response(content=pdf, media_type="application/pdf",
                            headers={"Content-Disposition": f'attachment; filename="CRMEvent_Fasce_{_slug(ev.get("nome"))}.pdf"'})
        if not date:
            raise HTTPException(status_code=400, detail="Seleziona una data")
        sections = []
        if mode == "by_mansione":
            base = await coverage(evento_id, date, step, None, team_id, gruppo, cat, user)
            for m in base["mansioni"]:
                ev, d = await _day(org, evento_id, date, step, m, team_id or None, gruppo or None, cat)
                sections.append((m, d))
        else:
            ev, d = await _day(org, evento_id, date, step, mansione or None, team_id or None, gruppo or None, cat)
            sections.append((mansione or "Tutte le mansioni", d))
        ev = await db.events.find_one({"org_id": org, "id": evento_id}, {"_id": 0})
        pdf = _pdf(ev, o.get("nome") or "", date, sections, names=(mode == "names"))
        return Response(content=pdf, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="CRMEvent_Copertura_{_slug(ev.get("nome"))}_{date}.pdf"'})

    async def _bulk_plan(org, body):
        ev = await db.events.find_one({"org_id": org, "id": body.evento_id}, {"_id": 0})
        if not ev:
            raise HTTPException(status_code=404, detail="Evento non trovato")
        day = next((d for d in avail_days(ev) if d["date"] == body.date), None)
        if not day:
            raise HTTPException(status_code=400, detail="Il giorno non appartiene all'evento")
        slots = {s["id"]: s for s in day.get("fasce") or []}
        sl = slots.get(body.fascia)
        if not sl or not sl.get("start") or not sl.get("end"):
            raise HTTPException(status_code=400, detail=f"{FX_LABEL[body.fascia]} non attiva o senza orari in questo giorno: configurala nella scheda evento")
        other = slots.get("pomeriggio" if body.fascia == "mattina" else "mattina")
        tn = {t["id"]: t.get("nome") or "" for t in await db.teams.find({"org_id": org, "evento_id": ev["id"], "id": {"$in": body.team_ids}}, {"_id": 0, "id": 1, "nome": 1}).to_list(500)}
        if not tn:
            raise HTTPException(status_code=400, detail="Seleziona almeno un Team dell'evento")
        people = {}
        for l in await db.staff.find({"org_id": org, "evento_id": ev["id"], "team_id": {"$in": list(tn)}}, {"_id": 0, "persona_id": 1, "team_id": 1, "categoria": 1, "stato": 1}).to_list(20000):
            if l.get("persona_id") and l.get("categoria") in CONFIRMED_CATS and l.get("stato") == "confermato":
                people.setdefault(l["persona_id"], set()).add(tn[l["team_id"]])
        pers = {p["id"]: p for p in await db.persons.find({"org_id": org, "id": {"$in": list(people)}}, {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "email": 1, "cellulare": 1}).to_list(20000)}
        avs = {}
        for a in await db.availabilities.find({"org_id": org, "evento_id": ev["id"], "persona_id": {"$in": list(people)}}, {"_id": 0}).to_list(50000):
            c = avs.get(a["persona_id"])
            if not c or str(a.get("updated_at") or a.get("created_at") or "") > str(c.get("updated_at") or c.get("created_at") or ""):
                avs[a["persona_id"]] = a
        slot = {"id": sl["id"], "start": sl["start"], "end": sl["end"]}
        items = []
        for pid, ms in people.items():
            p = pers.get(pid)
            if not p:
                continue
            it = {"id": pid, "nome": p.get("nome") or "", "cognome": p.get("cognome") or "", "teams": sorted(ms)}
            cur = avs.get(pid)
            days = list((cur or {}).get("days") or [])
            d = next((x for x in days if x.get("date") == body.date), None)
            new_day = {"date": body.date, "fase": day["fase"], "fasce": [slot], "dalle": sl["start"], "alle": sl["end"]}
            if not cur:
                it.update(action="create", label="Nuova disponibilità", days=[new_day])
            elif d is None:
                it.update(action="update", label="Aggiunto il giorno", days=sorted(days + [new_day], key=lambda x: x.get("date") or ""))
            elif d.get("disponibile") is False:
                it.update(action="skip", label="Ha dichiarato di non essere disponibile in questo giorno")
            elif d.get("fasce"):
                if any(f.get("id") == body.fascia for f in d["fasce"]):
                    it.update(action="already", label="Ha già questa fascia")
                else:
                    nf = sorted([slot] + list(d["fasce"]), key=lambda f: 0 if f.get("id") == "mattina" else 1)
                    st, en = [f.get("start") for f in nf], [f.get("end") for f in nf]
                    nd = {**d, "fasce": nf, "dalle": min(st) if all(st) else None, "alle": max(en) if all(en) else None}
                    it.update(action="update", label=f"Aggiunta {FX_LABEL[body.fascia]}", days=[nd if x is d else x for x in days])
            else:
                x0, x1 = _hm(d.get("dalle")), _hm(d.get("alle"))
                o0, o1 = (_hm(other.get("start")), _hm(other.get("end"))) if other else (None, None)
                orig = f"{d.get('dalle') or '?'}–{d.get('alle') or '?'}"
                if None not in (x0, x1, o0, o1) and min(x1 if x1 > x0 else x1 + 1440, o1) > max(x0, o0):
                    it.update(action="skip", label=f"Vecchio orario {orig} copre anche l'altra fascia: aggiorna dalla scheda")
                else:
                    it.update(action="update", label=f"Vecchio orario {orig} → {FX_LABEL[body.fascia]}", days=[new_day if x is d else x for x in days], legacy=d)
            it["av_id"], it["av_upd"] = (cur or {}).get("id"), (cur or {}).get("updated_at")
            items.append(it)
        items.sort(key=lambda x: (x["cognome"].lower(), x["nome"].lower()))
        tok = hashlib.sha1(json.dumps([[x["id"], x["action"], x["av_id"], x["av_upd"]] for x in items] + [body.date, body.fascia, slot["start"], slot["end"]], default=str).encode()).hexdigest()[:12]
        return ev, slot, items, tok

    def _bulk_out(ev, slot, items, tok, body):
        cnt = {k: sum(x["action"] == k for x in items) for k in ("create", "update", "already", "skip")}
        return {"evento": ev.get("nome"), "date": body.date, "fascia": body.fascia, "label": FX_LABEL[body.fascia], "start": slot["start"], "end": slot["end"],
                "token": tok, "total": len(items), "to_update": cnt["create"] + cnt["update"], "already": cnt["already"], "skipped": cnt["skip"],
                "people": [{k: x.get(k) for k in ("id", "nome", "cognome", "teams", "action", "label")} for x in items]}

    @r.post("/staff-coverage/bulk-fascia/preview")
    async def bulk_preview(body: BulkFasciaIn, user: dict = Depends(require)):
        ev, slot, items, tok = await _bulk_plan(user["org_id"], body)
        return _bulk_out(ev, slot, items, tok, body)

    @r.post("/staff-coverage/bulk-fascia/apply")
    async def bulk_apply(body: BulkFasciaIn, user: dict = Depends(require)):
        org = user["org_id"]
        ev, slot, items, tok = await _bulk_plan(org, body)
        if body.token != tok:
            raise HTTPException(status_code=409, detail="I dati sono cambiati dopo l'anteprima: ripeti l'anteprima")
        done, now = 0, datetime.now(ROME).isoformat()
        for x in items:
            if x["action"] == "update":
                upd = {"$set": {"days": x["days"], "updated_at": now, "days_edited_by": user.get("email"), "days_edited_at": now}}
                if x.get("legacy"):
                    upd["$push"] = {"days_history": {**x["legacy"], "sostituito_il": now, "sostituito_da": user.get("email")}}
                res = await db.availabilities.update_one({"org_id": org, "id": x["av_id"], "updated_at": x["av_upd"]}, upd)
                done += res.modified_count
            elif x["action"] == "create":
                if await db.availabilities.find_one({"org_id": org, "evento_id": ev["id"], "persona_id": x["id"]}, {"_id": 1}):
                    continue
                p = await db.persons.find_one({"org_id": org, "id": x["id"]}, {"_id": 0, "nome": 1, "cognome": 1, "email": 1, "cellulare": 1, "data_nascita": 1}) or {}
                await db.availabilities.insert_one({"id": uuid.uuid4().hex, "org_id": org, "evento_id": ev["id"], "persona_id": x["id"], **p,
                                                    "ruolo_evento": "staff", "stato": "confermata", "origine": "assegnazione_massiva", "days": x["days"], "brevo_status": "skipped",
                                                    "days_edited_by": user.get("email"), "days_edited_at": now, "created_at": now, "updated_at": now})
                done += 1
        await record_audit(user, "availability_bulk_update", org_id=org,
                           detail=f"{ev.get('nome')}: {FX_LABEL[body.fascia]} {slot['start']}–{slot['end']} del {body.date} a {done} persone (Team: {', '.join(sorted({t for x in items for t in x['teams']}))})",
                           meta={"evento_id": ev["id"], "date": body.date, "fascia": body.fascia, "team_ids": body.team_ids, "persone": [x["id"] for x in items if x["action"] in ("create", "update")]})
        return {"ok": True, "updated": done}

    return {"router": r}


def _slug(s):
    return re.sub(r"[^A-Za-z0-9]+", "", s or "Evento")[:40] or "Evento"


def _pdf_fasce(ev, org_name, rows, names=False):
    from xml.sax.saxutils import escape
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    ss = getSampleStyleSheet()
    W = A4[0] - 28 * mm
    cell = ss["BodyText"].clone("fcell", fontSize=8.5, leading=10.5)
    hcell = cell.clone("fhcell", textColor=colors.white, fontName="Helvetica-Bold")
    sub = ss["BodyText"].clone("fsub", fontSize=9, leading=12, textColor=colors.HexColor("#475569"))
    gh = ss["Heading3"].clone("fgh", spaceBefore=8, spaceAfter=4)
    gen = datetime.now(ROME).strftime("%d/%m/%Y %H:%M")
    STATUS = {"green": ("Sufficiente", "#DCFCE7"), "yellow": ("Al limite", "#FEF9C3"), "red": ("Insufficiente", "#FEE2E2")}
    COV = {"complete": "Completa", "partial": "Parziale", "tbc": "Da verificare"}
    GG = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"]
    dl = lambda iso: f"{GG[_d(iso).weekday()]} {_d(iso).strftime('%d/%m')}"

    def tbl(data, widths, styles=()):
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(TIFFANY)), ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
                               ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3), *styles]))
        return t

    def footer(c, d):
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.HexColor("#64748B"))
        c.drawString(14 * mm, 8 * mm, f"CRMEvent · Copertura per fasce · {ev.get('nome') or ''} · generato il {gen}")
        c.drawRightString(A4[0] - 14 * mm, 8 * mm, f"Pagina {d.page}")

    story = [Paragraph("Copertura per fasce" + (" · elenco nominativo" if names else ""), ss["Title"].clone("fh1", alignment=0, fontSize=16, leading=20)),
             Paragraph(f"<b>{escape(ev.get('nome') or '')}</b>" + (f" · {escape(org_name)}" if org_name else ""), ss["BodyText"]),
             Paragraph("Per Team: Disponibili = confermati del Team che coprono l'intera fascia; Assegnati = persone assegnate al Team nella fascia; Mancanti = Necessari - Assegnati.", sub), Spacer(1, 6)]
    data = [[Paragraph(h, hcell) for h in ("Giorno", "Fascia", "Orario", "Team", "Disponibili", "Assegnati", "Necessari", "Mancanti")]]
    st = []
    for j, x in enumerate(rows, 1):
        data.append([dl(x["date"]), x["label"], f"{x['start'] or '?'}–{x['end'] or '?'}", Paragraph(escape(x["team"]), cell), str(x["available"]),
                     str(x["assigned"]), str(x["needed"] or "—"), str(x["missing"]) if x["missing"] is not None else "—"])
        if x["status"]:
            st.append(("BACKGROUND", (7, j), (7, j), colors.HexColor(STATUS[x["status"]][1])))
    story.append(tbl(data, [W * w for w in (0.12, 0.11, 0.12, 0.21, 0.11, 0.11, 0.11, 0.11)], st))
    if names:
        for x in rows:
            ppl = [p for p in x["people"] if p["assigned"] or p["cov"] != "none"]
            if not ppl:
                continue
            story.append(Paragraph(f"{dl(x['date'])} · {x['label']} {x['start'] or ''}–{x['end'] or ''} · {escape(x['team'])} · {x['assigned']} assegnati", gh))
            d = [[Paragraph(h, hcell) for h in ("Cognome e nome", "Gruppo", "Disponibilità", "Assegnazione", "Note")]]
            for p in ppl:
                note = ", ".join(filter(None, ["Da aggiornare" if p["legacy"] else "", "Fuori disponibilità" if p["forced"] else "", f"Assegnato a {p['assigned_other']}" if p["assigned_other"] else ""]))
                d.append([Paragraph(escape(v or "—"), cell) for v in (f"{p['cognome']} {p['nome']}".strip(), p["gruppo"], f"{COV.get(p['cov'], 'Non disponibile')} · {p['orario']}",
                                                                         "Assegnato" if p["assigned"] else "—", note)])
            story.append(tbl(d, [W * w for w in (0.26, 0.16, 0.24, 0.14, 0.2)]))
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=16 * mm,
                      title=f"Copertura per fasce · {ev.get('nome') or ''}", author="CRMEvent").build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


def _xlsx(ev, people):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = "Disponibilità"
    ws.append(["Cognome", "Nome", "Cellulare", "Classificazione", "Mansione", "Attività preferita", "Gruppo di appartenenza", "Team", "Taglia",
               "Data inizio", "Ora inizio", "Data fine", "Ora fine", "Note"])
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=TIFFANY[1:])
    for p in people:
        base = [p["cognome"], p["nome"], p["cellulare"], p["categoria"], ", ".join(p["mansioni"]), p["preferenza"] or "", p["gruppo"], p["team"], p["taglia"]]
        for a, b in p["iv"]:
            ws.append(base + [date.fromordinal(a // 1440).strftime("%d/%m/%Y"), _fmt(a), date.fromordinal((b - 1) // 1440).strftime("%d/%m/%Y"), _fmt(b) if b % 1440 else "24:00", ""])
        for d in sorted(p["tbc"]):
            ws.append(base + [_d(d).strftime("%d/%m/%Y"), "", "", "", "Orario da confermare"])
        if not p["iv"] and not p["tbc"]:
            ws.append(base + ["", "", "", "", "Nessuna disponibilità indicata"])
    for col, w in zip("ABCDEFGHIJKLMN", (18, 16, 15, 15, 22, 22, 24, 18, 8, 12, 9, 12, 9, 26)):
        ws.column_dimensions[col].width = w
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _pdf(ev, org_name, day_iso, sections, names=False):
    from xml.sax.saxutils import escape
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak

    ss = getSampleStyleSheet()
    W = A4[0] - 28 * mm
    cell = ss["BodyText"].clone("ccell", fontSize=8.5, leading=10.5)
    hcell = cell.clone("chcell", textColor=colors.white, fontName="Helvetica-Bold")
    sub = ss["BodyText"].clone("csub", fontSize=9, leading=12, textColor=colors.HexColor("#475569"))
    h1 = ss["Title"].clone("ch1", alignment=0, fontSize=16, leading=20, spaceAfter=2)
    gh = ss["Heading3"].clone("cgh", spaceBefore=6, spaceAfter=4)
    gen = datetime.now(ROME).strftime("%d/%m/%Y %H:%M")
    dlab = _d(day_iso).strftime("%d/%m/%Y")
    STATUS = {"green": ("Sufficiente", "#DCFCE7"), "yellow": ("Al limite", "#FEF9C3"), "red": ("Insufficiente", "#FEE2E2")}

    def footer(c, d):
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.HexColor("#64748B"))
        c.drawString(14 * mm, 8 * mm, f"CRMEvent · Copertura oraria · {ev.get('nome') or ''} · {dlab} · generato il {gen}")
        c.drawRightString(A4[0] - 14 * mm, 8 * mm, f"Pagina {d.page}")

    def tbl(data, widths, styles=()):
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(TIFFANY)), ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
                               ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3), *styles]))
        return t

    story = [Paragraph("Copertura oraria" + (" · elenco nominativo" if names else ""), h1),
             Paragraph(f"<b>{escape(ev.get('nome') or '')}</b>" + (f" · {escape(org_name)}" if org_name else "") + f" · {dlab}", ss["BodyText"]),
             Paragraph(f"Generato il {gen}. Disponibili = dichiarati (intera fascia + parziale); Assegnati = disponibili con mansione assegnata; Necessari = fabbisogno impostato.", sub),
             Spacer(1, 6)]
    for i, (label, d) in enumerate(sections):
        if i:
            story.append(PageBreak() if names else Spacer(1, 10))
        k = d["kpis"]
        story.append(Paragraph(f"Mansione: {escape(label)}", gh))
        story.append(Paragraph(f"Persone disponibili nel giorno: <b>{k['day_people']}</b> · Max contemporanei: <b>{k['max']}</b> · Min: <b>{k['min']}</b> · "
                               f"Orario da confermare: <b>{k['tbc']}</b>", sub))
        if names:
            for sl in d["slots"]:
                ids = sl["full"] + sl["partial"]
                if not ids:
                    continue
                story.append(Paragraph(f"{sl['start']}–{sl['end']} · {len(ids)} disponibili", gh))
                data = [[Paragraph(h, hcell) for h in ("Cognome", "Nome", "Mansione", "Gruppo", "Orario", "")]]
                for pid in sorted(ids, key=lambda x: (_fold(d["people"][x]["cognome"]), _fold(d["people"][x]["nome"]))):
                    p = d["people"][pid]
                    data.append([Paragraph(escape(v or "—"), cell) for v in (p["cognome"], p["nome"], ", ".join(p["mansioni"]) or (p["preferenza"] and f"Pref.: {p['preferenza']}"),
                                                                             p["gruppo"], p["orario"], "parziale" if pid in sl["partial"] else "")])
                story.append(tbl(data, [W * 0.18, W * 0.15, W * 0.2, W * 0.17, W * 0.2, W * 0.1]))
            continue
        data = [[Paragraph(h, hcell) for h in ("Fascia", "Disponibili", "di cui parziali", "Assegnati", "Necessari", "Stato")]]
        st = []
        for j, sl in enumerate(d["slots"], 1):
            lab, bg = STATUS.get(sl["status"], ("—", None))
            data.append([Paragraph(f"{sl['start']}–{sl['end']}", cell), str(sl["available"]), str(len(sl["partial"])), str(sl["assigned"]),
                         str(sl["needed"] or "—"), lab])
            if bg:
                st.append(("BACKGROUND", (5, j), (5, j), colors.HexColor(bg)))
        story.append(tbl(data, [W * 0.2, W * 0.16, W * 0.16, W * 0.16, W * 0.16, W * 0.16], st))
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=16 * mm,
                      title=f"Copertura oraria · {ev.get('nome') or ''}", author="CRMEvent").build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
