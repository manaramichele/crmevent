"""Copertura oraria Staff / Volontari: calcolata al volo da disponibilità (availabilities.days) e assegnazioni (staff) esistenti."""
import io
import math
import re
import unicodedata
import uuid
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

ROME = ZoneInfo("Europe/Rome")
TIFFANY = "#0ABAB5"
STAFF_CATS = {"staff", "collaboratore"}


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


class ConfigIn(BaseModel):
    yellow_margin_pct: int = Field(ge=0, le=100)


def build(db, deps: dict):
    r = APIRouter(prefix="/api")
    require = deps["require_admin"]
    avail_days = deps["avail_days"]

    async def _yellow(org):
        st = await db.settings.find_one({"id": org}, {"_id": 0, "coverage_yellow_pct": 1}) or {}
        return int(st.get("coverage_yellow_pct", 10))

    async def _load(org, evento_id, mansione=None, team_id=None, gruppo=None, cat="all"):
        """Persone filtrate con intervalli assoluti (minuti) e date senza orario."""
        ev = await db.events.find_one({"org_id": org, "id": evento_id}, {"_id": 0})
        if not ev:
            raise HTTPException(status_code=404, detail="Evento non trovato")
        links = await db.staff.find({"org_id": org, "evento_id": evento_id}, {"_id": 0}).to_list(20000)
        avs = await db.availabilities.find({"org_id": org, "evento_id": evento_id, "persona_id": {"$ne": None}}, {"_id": 0}).to_list(20000)
        latest = {}
        for a in avs:  # la disponibilità più recente sostituisce le precedenti della stessa persona
            k = a["persona_id"]
            if k not in latest or str(a.get("updated_at") or a.get("created_at") or "") > str(latest[k].get("updated_at") or latest[k].get("created_at") or ""):
                latest[k] = a
        pids = {x["persona_id"] for x in links} | set(latest)
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
            if not ls and av:  # solo modulo disponibilità: usa il ruolo dichiarato
                re_ = _fold(av.get("ruolo_evento"))
                cats = {"staff"} if re_.startswith("staff") else ({"volontario"} if re_.startswith("volont") else set())
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
                        "team": ", ".join(sorted({teams[t] for t in tids if t in teams})),
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
        ev, people = await _load(org, evento_id, None, team_id, gruppo, cat)
        needs = {(n["date"], n["fascia"]): int(n["needed"]) for n in await db.coverage_fascia_needs.find({"org_id": org, "evento_id": evento_id}, {"_id": 0}).to_list(5000)}
        shifts = {}
        for s in await db.shifts.find({"org_id": org, "evento_id": evento_id, "persona_id": {"$nin": [None, ""]}}, {"_id": 0, "persona_id": 1, "data": 1, "ora_inizio": 1, "ora_fine": 1}).to_list(20000):
            shifts.setdefault((s["persona_id"], str(s.get("data") or "")[:10]), []).append(s)
        pct, rows = await _yellow(org), []
        for d in avail_days(ev):
            for s in d.get("fasce") or []:
                a, b = _hm(s.get("start")), _hm(s.get("end"))
                if a is not None and b is not None and b <= a:
                    b += 1440
                ppl = []
                for p in people:
                    c = _classify(p, d["date"], s["id"], a, b)
                    if not c:
                        continue
                    tur = [f"{x.get('ora_inizio') or '?'}–{x.get('ora_fine') or '?'}" for x in shifts.get((p["id"], d["date"]), [])
                           if a is None or b is None or _hm(x.get("ora_inizio")) is None or _hm(x.get("ora_fine")) is None
                           or (_hm(x.get("ora_inizio")) < b and (_hm(x.get("ora_fine")) or 1440) > a)]
                    ppl.append({k: p[k] for k in ("id", "nome", "cognome", "gruppo", "mansioni", "preferenza", "team", "categoria")} |
                               {"cov": c[0], "orario": c[1], "legacy": c[2], "changed": c[3], "turni": tur,
                                "assigned": c[0] != "tbc" and bool(p["mansioni"] or p["team"])})
                av = [x for x in ppl if x["cov"] == "complete"]
                n = needs.get((d["date"], s["id"])) or None
                status = None
                if n:
                    status = "red" if len(av) < n else ("yellow" if len(av) < n + max(1, math.ceil(n * pct / 100)) else "green")
                rows.append({"date": d["date"], "fascia": s["id"], "label": FX_LABEL[s["id"]], "start": s.get("start"), "end": s.get("end"),
                             "available": len(av), "partial": sum(x["cov"] == "partial" for x in ppl), "tbc": sum(x["cov"] == "tbc" for x in ppl),
                             "assigned": sum(x["assigned"] for x in ppl), "needed": n, "status": status,
                             "changed": sum(x["changed"] for x in ppl), "people": ppl})
        return ev, rows

    @r.get("/staff-coverage/fasce")
    async def fasce(evento_id: str, team_id: Optional[str] = None, gruppo: Optional[str] = None, cat: str = "all", user: dict = Depends(require)):
        org = user["org_id"]
        ev, rows = await _fasce(org, evento_id, team_id or None, gruppo or None, cat)
        _, allp = await _load(org, evento_id)
        return {"evento": {"id": ev["id"], "nome": ev.get("nome")}, "rows": rows, "legacy": _legacy(allp), "yellow_margin_pct": await _yellow(org)}

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
            ev, rows = await _fasce(org, evento_id, team_id or None, gruppo or None, cat)
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
             Paragraph("Disponibili = copertura completa della fascia; parziali e da verificare sono indicati a parte. Assegnati = disponibili con mansione o team.", sub), Spacer(1, 6)]
    data = [[Paragraph(h, hcell) for h in ("Giorno", "Fascia", "Orario", "Disponibili", "Parziali", "Da verificare", "Assegnati", "Necessari", "Stato")]]
    st = []
    for j, x in enumerate(rows, 1):
        lab, bg = STATUS.get(x["status"], ("—", None))
        data.append([dl(x["date"]), x["label"], f"{x['start'] or '?'}–{x['end'] or '?'}", str(x["available"]), str(x["partial"]), str(x["tbc"]),
                     str(x["assigned"]), str(x["needed"] or "—"), lab])
        if bg:
            st.append(("BACKGROUND", (8, j), (8, j), colors.HexColor(bg)))
    story.append(tbl(data, [W * w for w in (0.12, 0.12, 0.13, 0.1, 0.09, 0.11, 0.1, 0.1, 0.13)], st))
    if names:
        for x in rows:
            if not x["people"]:
                continue
            story.append(Paragraph(f"{dl(x['date'])} · {x['label']} {x['start'] or ''}–{x['end'] or ''} · {x['available']} disponibili", gh))
            d = [[Paragraph(h, hcell) for h in ("Cognome e nome", "Team", "Gruppo", "Mansione", "Disponibilità", "Note")]]
            for p in x["people"]:
                note = ", ".join(filter(None, ["Da aggiornare" if p["legacy"] else "", "Assegnato" if p["assigned"] else "", ("Turno " + ", ".join(p["turni"])) if p["turni"] else ""]))
                d.append([Paragraph(escape(v or "—"), cell) for v in (f"{p['cognome']} {p['nome']}".strip(), p["team"], p["gruppo"], ", ".join(p["mansioni"]),
                                                                         f"{COV[p['cov']]} · {p['orario']}", note)])
            story.append(tbl(d, [W * w for w in (0.22, 0.14, 0.14, 0.16, 0.18, 0.16)]))
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
