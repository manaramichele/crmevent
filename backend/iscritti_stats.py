"""Statistiche Elenco Iscritti calcolate dai record presenti (partecipazioni + anagrafiche)."""
from collections import Counter, defaultdict
from datetime import date, timedelta

BANDS = [("Under 25", 0, 24), ("25–34", 25, 34), ("35–44", 35, 44), ("45–54", 45, 54), ("55–64", 55, 64), ("Over 65", 65, 200)]


def _band(age):
    for label, lo, hi in BANDS:
        if lo <= age <= hi:
            return label
    return None


def _d(s):
    try:
        return date.fromisoformat((s or "")[:10])
    except ValueError:
        return None


async def compute(db, org_id: str, f: dict) -> dict:
    q = {"org_id": org_id}
    for k in ("event_id", "edizione_id", "gara", "stato"):
        if f.get(k):
            q[k] = f[k]
    if f.get("anni"):
        q["anno"] = {"$in": f["anni"]}
    parts = await db.iscritti_partecipazioni.find(q, {"_id": 0, "iscritto_id": 1, "edizione_id": 1, "event_id": 1, "anno": 1, "gara": 1, "data_iscrizione": 1}).to_list(300000)
    eds = {e["id"]: e for e in await db.iscritti_edizioni.find({"org_id": org_id}, {"_id": 0}).to_list(2000)}
    evs = {e["id"]: e for e in await db.events.find({"org_id": org_id}, {"_id": 0, "id": 1, "nome": 1, "data_inizio": 1}).to_list(5000)}
    pids = list({p["iscritto_id"] for p in parts})
    people = {x["id"]: x for x in await db.iscritti.find({"org_id": org_id, "id": {"$in": pids}, "anonymized": {"$ne": True}},
                                                         {"_id": 0, "id": 1, "sesso": 1, "data_nascita": 1, "nazionalita": 1}).to_list(300000)}
    # storico completo per evento (ricorrenti = presenti in un'edizione precedente dello stesso evento)
    hist = defaultdict(set)
    async for h in db.iscritti_partecipazioni.find({"org_id": org_id, "iscritto_id": {"$in": pids}}, {"_id": 0, "iscritto_id": 1, "event_id": 1, "anno": 1}):
        hist[(h["iscritto_id"], h["event_id"])].add(h["anno"])
    order = sorted({p["edizione_id"] for p in parts}, key=lambda e: ((eds.get(e) or {}).get("anno", 0), (eds.get(e) or {}).get("edizione", "")))
    multi_event = len({p["event_id"] for p in parts}) > 1

    def label(eid):
        e = eds.get(eid) or {}
        base = f"{e.get('anno', '')} · {e.get('edizione', '')}".strip(" ·")
        return f"{e.get('event_nome', '')} {base}".strip() if multi_event else base

    by = defaultdict(list)
    for p in parts:
        by[p["edizione_id"]].append(p)
    gare = [g for g, _ in Counter(p["gara"] or "—" for p in parts).most_common()]
    naz_all = Counter((people.get(p["iscritto_id"]) or {}).get("nazionalita") or "N/D" for p in parts)
    top_naz = [n for n, _ in naz_all.most_common(8)]
    evolution, distance, gender, ages, nat, newrec, trend = [], [], [], {b[0]: {"fascia": b[0]} for b in BANDS}, {n: {"nazionalita": n} for n in top_naz}, [], {}
    recurring_people, ages_all = set(), []
    mode = f.get("mode") or "days"
    for eid in order:
        rows, e, lb = by[eid], eds.get(eid) or {}, label(eid)
        evolution.append({"label": lb, "anno": e.get("anno"), "n": len(rows)})
        dc = Counter(p["gara"] or "—" for p in rows)
        distance.append({"label": lb, **{g: dc.get(g, 0) for g in gare}})
        sx = Counter(((people.get(p["iscritto_id"]) or {}).get("sesso") or "").upper()[:1] for p in rows)
        tot_s = (sx.get("M", 0) + sx.get("F", 0)) or 1
        gender.append({"label": lb, "Uomini": round(sx.get("M", 0) * 100 / tot_s, 1), "Donne": round(sx.get("F", 0) * 100 / tot_s, 1), "M": sx.get("M", 0), "F": sx.get("F", 0)})
        bc = Counter()
        for p in rows:
            b = _d((people.get(p["iscritto_id"]) or {}).get("data_nascita"))
            if b and e.get("anno"):
                age = e["anno"] - b.year
                ages_all.append(age)
                bc[_band(age)] += 1
        for b in BANDS:
            ages[b[0]][lb] = bc.get(b[0], 0)
        nc = Counter((people.get(p["iscritto_id"]) or {}).get("nazionalita") or "N/D" for p in rows)
        for n in top_naz:
            nat[n][lb] = nc.get(n, 0)
        rec = 0
        for p in rows:
            if any(y < e.get("anno", 0) for y in hist[(p["iscritto_id"], p["event_id"])]):
                rec += 1
                recurring_people.add(p["iscritto_id"])
        newrec.append({"label": lb, "Nuovi": len(rows) - rec, "Ricorrenti": rec})
        ev_day = _d(e.get("data_evento")) or (_d((evs.get(e.get("event_id")) or {}).get("data_inizio")) if str((evs.get(e.get("event_id")) or {}).get("data_inizio", ""))[:4] == str(e.get("anno")) else None) \
            or max((x for x in (_d(p.get("data_iscrizione")) for p in rows) if x), default=None)
        if ev_day:
            cnt = Counter()
            for p in rows:
                d = _d(p.get("data_iscrizione"))
                if d:
                    delta = max(0, (ev_day - d).days)
                    cnt[delta // 30 if mode == "months" else delta] += 1
            trend[lb] = cnt
    if mode == "months":
        maxb = max((max(c) for c in trend.values() if c), default=0)
        steps = list(range(maxb, -1, -1))
        xlab = lambda s: "Mese evento" if s == 0 else f"-{s} mesi"  # noqa: E731
    else:
        maxb = max((max(c) for c in trend.values() if c), default=0)
        steps = sorted(set(list(range(maxb - maxb % 7, -1, -7)) + [0]), reverse=True)
        xlab = lambda s: "Evento" if s == 0 else f"-{s} gg"  # noqa: E731
    trend_rows = []
    for s in steps:
        row = {"x": xlab(s)}
        for lb, c in trend.items():
            row[lb] = sum(v for k, v in c.items() if k >= s)
        trend_rows.append(row)
    labels = [label(e) for e in order]
    var = round((evolution[-1]["n"] - evolution[-2]["n"]) * 100 / evolution[-2]["n"], 1) if len(evolution) > 1 and evolution[-2]["n"] else None
    sx_all = Counter(((people.get(p["iscritto_id"]) or {}).get("sesso") or "").upper()[:1] for p in parts)
    tot_all = (sx_all.get("M", 0) + sx_all.get("F", 0)) or 1
    gc = Counter(p["gara"] for p in parts if p["gara"])
    return {
        "labels": labels, "gare": gare,
        "kpi": {"totale": len(parts), "unici": len(pids), "variazione": var, "variazione_rif": labels[-2:] if len(labels) > 1 else [],
                "ricorrenti": len(recurring_people), "uomini_pct": round(sx_all.get("M", 0) * 100 / tot_all, 1), "donne_pct": round(sx_all.get("F", 0) * 100 / tot_all, 1),
                "eta_media": round(sum(ages_all) / len(ages_all), 1) if ages_all else None, "nazionalita": len([n for n in naz_all if n != "N/D"]),
                "distanza_top": gc.most_common(1)[0][0] if gc else None},
        "evolution": evolution, "distance": distance, "gender": gender, "ages": list(ages.values()),
        "nationalities": list(nat.values()), "new_recurring": newrec, "trend": trend_rows, "trend_mode": mode}
