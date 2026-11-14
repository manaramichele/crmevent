"""Event Planner — distinta materiali per progetto (da mappa + rettifiche/manuali/componenti) e riepilogo evento, export XLSX/PDF."""
import io
import math
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

STATUSES = {"da_preparare": "Da preparare", "da_ordinare": "Da ordinare/noleggiare", "ordinato": "Ordinato", "disponibile": "Disponibile", "consegnato": "Consegnato"}
EDIT = ("categoria", "code", "description", "unit", "adjust", "supplier", "notes", "status")


class RowIn(BaseModel):
    categoria: Optional[str] = Field(default=None, max_length=60)
    code: Optional[str] = Field(default=None, max_length=40)
    description: Optional[str] = Field(default=None, max_length=160)
    unit: Optional[str] = Field(default=None, max_length=12)
    adjust: Optional[float] = Field(default=None, ge=-100000, le=100000)
    supplier: Optional[str] = Field(default=None, max_length=80)
    notes: Optional[str] = Field(default=None, max_length=300)
    status: Optional[str] = None


class CompIn(BaseModel):
    description: str = Field(min_length=1, max_length=100)
    qty: float = Field(gt=0, le=10000)
    unit: str = Field(default="pz", max_length=12)
    code: Optional[str] = Field(default=None, max_length=40)


class CompsIn(BaseModel):
    items: list[CompIn] = Field(default_factory=list, max_length=30)


def _hav(a, b):
    r = 6371008.8
    p1, p2 = math.radians(a[1]), math.radians(b[1])
    dp, dl = p2 - p1, math.radians(b[0] - a[0])
    return 2 * r * math.asin(math.sqrt(math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2))


def _code(cat, nome):
    return (re.sub(r"[^A-Z]", "", (cat or "MAT").upper())[:3] + "-" + re.sub(r"[^A-Z0-9]", "", (nome or "").upper())[:12]) or "MAT"


def map_items(features):
    """Oggetti della libreria presenti sulla mappa, raggruppati per categoria + nome (identici = una riga)."""
    out = {}
    for f in features or []:
        p = f.get("properties") or {}
        if not p.get("categoria") or p.get("tipo") == "measure":
            continue
        if p.get("tipo") == "line" and p.get("passo"):
            c = (f.get("geometry") or {}).get("coordinates") or []
            n = math.ceil(sum(_hav(c[i - 1], c[i]) for i in range(1, len(c))) / float(p["passo"])) if len(c) > 1 else 0
        else:
            try:
                n = max(0, int(float(p.get("quantita") or 1)))
            except (TypeError, ValueError):
                n = 1
        key = f"{p['categoria']}|{p.get('nome') or 'Oggetto'}".replace(".", "_")
        it = out.setdefault(key, {"key": key, "categoria": p["categoria"], "nome": p.get("nome") or "Oggetto", "qty": 0})
        it["qty"] += n
    return out


def compute(features, bom):
    bom = bom or {}
    ov, comps = bom.get("rows") or {}, bom.get("components") or {}
    rows = []

    def add(key, base, map_qty, source, parent=None):
        o = ov.get(key) or {}
        adj = float(o.get("adjust") or 0)
        if not map_qty and not adj and source != "manual":
            return
        r = {"key": key, "source": source, "parent": parent, "categoria": o.get("categoria") or base["categoria"], "code": o.get("code") or base["code"],
             "description": o.get("description") or base["description"], "unit": o.get("unit") or base.get("unit") or "pz",
             "map_qty": map_qty, "adjust": adj, "supplier": o.get("supplier") or "", "notes": o.get("notes") or "",
             "status": o.get("status") if o.get("status") in STATUSES else "da_preparare"}
        r["total"] = max(0.0, map_qty + adj)
        rows.append(r)

    items = map_items(features)
    for key in set(items) | {k for k in ov if not k.startswith("m:") and "::" not in k} | {k for k in comps}:
        it = items.get(key) or {"categoria": key.split("|")[0], "nome": key.split("|", 1)[-1], "qty": 0}
        cs = comps.get(key) or []
        if cs:  # tipologia composta: si contano i componenti configurati, non l'oggetto (niente doppi conteggi)
            for c in cs:
                add(f"{key}::{c['id']}", {"categoria": it["categoria"], "code": c.get("code") or _code(it["categoria"], c["description"]),
                                          "description": f"{it['nome']} – {c['description']}", "unit": c.get("unit")}, it["qty"] * float(c["qty"]), "component", key)
        else:
            add(key, {"categoria": it["categoria"], "code": _code(it["categoria"], it["nome"]), "description": it["nome"], "unit": "pz"}, float(it["qty"]), "map")
    for m in bom.get("manual") or []:
        add(f"m:{m['id']}", {"categoria": m.get("categoria") or "Altro", "code": m.get("code") or "", "description": m.get("description") or "Materiale", "unit": m.get("unit")}, 0.0, "manual")
    rows.sort(key=lambda r: (r["categoria"].lower(), r["description"].lower()))
    types = sorted(({"key": k, "categoria": v["categoria"], "nome": v["nome"], "qty": v["qty"]} for k, v in items.items()), key=lambda x: x["key"])
    return rows, types


def _num(x):
    return int(x) if float(x).is_integer() else round(x, 2)


def xlsx(title, sheets):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    wb.remove(wb.active)
    for name, head, data, formula in sheets:
        ws = wb.create_sheet(name[:31])
        ws.append([title])
        ws["A1"].font = Font(bold=True, size=13)
        ws.append(head)
        for c in ws[2]:
            c.font, c.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="0F172A")
        for i, row in enumerate(data, start=3):
            ws.append(row)
            if formula:
                col, f = formula
                ws[f"{col}{i}"] = f.format(r=i)
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = min(48, max(10, *(len(str(c.value or "")) + 2 for c in col[1:])))
        ws.freeze_panes = "A3"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def pdf(logo, ev_name, proj_name, groups, cols, widths):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Image as RLImage, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
                            title=f"Distinta materiali – {proj_name}")
    ss = getSampleStyleSheet()
    small = ss["BodyText"].clone("s", fontSize=8, leading=10)
    story = []
    head = [Paragraph(f"<b>Distinta materiali</b><br/>{ev_name}<br/>{proj_name}<br/><font size=8>{datetime.now(timezone.utc).strftime('%d/%m/%Y')}</font>", ss["BodyText"])]
    if logo:
        try:
            from PIL import Image as PI
            im = PI.open(io.BytesIO(logo))
            h = 16 * mm
            head.append(RLImage(io.BytesIO(logo), width=h * im.width / im.height, height=h))
        except Exception:  # logo non leggibile: PDF senza logo
            pass
    t = Table([head], colWidths=[doc.width * 0.7, doc.width * 0.3])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (1, 0), (1, 0), "RIGHT")]))
    story += [t, Spacer(1, 6 * mm)]
    if not groups:
        story.append(Paragraph("Nessun materiale nella distinta.", ss["BodyText"]))
    for cat, rows in groups:
        story.append(Paragraph(f"<b>{cat}</b>", ss["Heading4"]))
        data = [cols] + [[Paragraph(str(c), small) for c in r] for r in rows]
        tb = Table(data, colWidths=[w * doc.width for w in widths], repeatRows=1)
        tb.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                                ("FONTSIZE", (0, 0), (-1, 0), 8), ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
                                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5F9")]), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story += [tb, Spacer(1, 4 * mm)]
    doc.build(story)
    return buf.getvalue()


def _groups(rows, fn):
    out = {}
    for r in rows:
        out.setdefault(r["categoria"], []).append(fn(r))
    return sorted(out.items(), key=lambda x: x[0].lower())


def _fname(s):
    return re.sub(r"[^A-Za-z0-9_-]+", "-", s).strip("-")[:60] or "distinta"


def attach(r, db, audit, member_dep, admin_dep, project_of, event_of, org_logo):
    async def bom_of(org_id, pid):
        return await db.planner_bom.find_one({"org_id": org_id, "project_id": pid}, {"_id": 0}) or {}

    async def state(org_id, p):
        bom = await bom_of(org_id, p["id"])
        rows, types = compute(p.get("features"), bom)
        return {"rows": rows, "types": types, "components": bom.get("components") or {}, "statuses": STATUSES, "read_only": p.get("read_only", False)}

    @r.get("/projects/{pid}/bom")
    async def get_bom(pid: str, user: dict = Depends(member_dep)):
        return await state(user["org_id"], await project_of(user["org_id"], pid, user, write=False))

    @r.put("/projects/{pid}/bom/rows/{key:path}")
    async def put_row(pid: str, key: str, body: RowIn, admin: dict = Depends(admin_dep)):
        p = await project_of(admin["org_id"], pid, admin)
        data = body.model_dump(exclude_unset=True)
        if "status" in data and data["status"] not in STATUSES:
            raise HTTPException(status_code=400, detail="Stato non valido")
        data = {k: (v.strip() if isinstance(v, str) else v) for k, v in data.items() if k in EDIT}
        bom = await bom_of(admin["org_id"], pid)
        items = map_items(p.get("features"))
        ok = key in items or (key.startswith("m:") and any(m["id"] == key[2:] for m in bom.get("manual") or [])) or \
            ("::" in key and any(c["id"] == key.split("::", 1)[1] for c in (bom.get("components") or {}).get(key.split("::", 1)[0]) or []))
        if not ok:
            raise HTTPException(status_code=404, detail="Materiale non trovato nella distinta")
        await db.planner_bom.update_one({"org_id": admin["org_id"], "project_id": pid},
                                        {"$set": {**{f"rows.{key.replace('.', '_')}.{k}": v for k, v in data.items()}, "updated_at": datetime.now(timezone.utc).isoformat()},
                                         "$setOnInsert": {"org_id": admin["org_id"], "project_id": pid}}, upsert=True)
        return await state(admin["org_id"], p)

    @r.post("/projects/{pid}/bom/manual")
    async def add_manual(pid: str, body: RowIn, admin: dict = Depends(admin_dep)):
        p = await project_of(admin["org_id"], pid, admin)
        mid = uuid.uuid4().hex[:10]
        await db.planner_bom.update_one({"org_id": admin["org_id"], "project_id": pid},
                                        {"$push": {"manual": {"id": mid, "categoria": (body.categoria or "Altro").strip(), "code": body.code or "", "description": (body.description or "Nuovo materiale").strip(), "unit": body.unit or "pz"}},
                                         "$set": {f"rows.m:{mid}": {"adjust": body.adjust or 1, "supplier": body.supplier or "", "notes": body.notes or "", "status": body.status if body.status in STATUSES else "da_preparare"}},
                                         "$setOnInsert": {"org_id": admin["org_id"], "project_id": pid}}, upsert=True)
        return await state(admin["org_id"], p)

    @r.delete("/projects/{pid}/bom/manual/{mid}")
    async def del_manual(pid: str, mid: str, admin: dict = Depends(admin_dep)):
        p = await project_of(admin["org_id"], pid, admin)
        await db.planner_bom.update_one({"org_id": admin["org_id"], "project_id": pid}, {"$pull": {"manual": {"id": mid}}, "$unset": {f"rows.m:{mid}": ""}})
        return await state(admin["org_id"], p)

    @r.put("/projects/{pid}/bom/components/{key:path}")
    async def put_components(pid: str, key: str, body: CompsIn, admin: dict = Depends(admin_dep)):
        p = await project_of(admin["org_id"], pid, admin)
        items = [{"id": uuid.uuid4().hex[:8], **c.model_dump()} for c in body.items]
        k = key.replace(".", "_")
        upd = {"$set": {f"components.{k}": items}} if items else {"$unset": {f"components.{k}": ""}}
        await db.planner_bom.update_one({"org_id": admin["org_id"], "project_id": pid}, {**upd, "$setOnInsert": {"org_id": admin["org_id"], "project_id": pid}}, upsert=True)
        await audit(admin, "planner_bom_components", detail=f"{pid} · {key} · {len(items)}")
        return await state(admin["org_id"], p)

    async def summary(org_id, eid):
        projs = await db.planner_projects.find({"org_id": org_id, "evento_id": eid, "archiviato": {"$ne": True}}, {"_id": 0, "id": 1, "nome": 1, "features": 1}).sort("created_at", 1).to_list(200)
        agg = {}
        for p in projs:
            rows, _ = compute(p.get("features"), await bom_of(org_id, p["id"]))
            for x in rows:
                k = (x["categoria"].lower(), (x["code"] or x["description"]).lower(), x["unit"].lower())
                a = agg.setdefault(k, {"categoria": x["categoria"], "code": x["code"], "description": x["description"], "unit": x["unit"], "total": 0.0, "by_project": {}})
                a["total"] += x["total"]
                a["by_project"][p["id"]] = a["by_project"].get(p["id"], 0) + x["total"]
        rows = sorted((a for a in agg.values() if a["total"] > 0), key=lambda a: (a["categoria"].lower(), a["description"].lower()))
        return {"projects": [{"id": p["id"], "nome": p["nome"]} for p in projs], "rows": rows}

    @r.get("/events/{eid}/bom")
    async def event_bom(eid: str, user: dict = Depends(member_dep)):
        await event_of(user["org_id"], eid, user, write=False)
        return await summary(user["org_id"], eid)

    def _file(data, name, ext, inline=False):
        mt = "application/pdf" if ext == "pdf" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return Response(content=data, media_type=mt, headers={"Content-Disposition": f'{"inline" if inline else "attachment"}; filename="{_fname(name)}.{ext}"'})

    @r.get("/projects/{pid}/bom/export.{ext}")
    async def export_project(pid: str, ext: str, inline: int = 0, user: dict = Depends(member_dep)):
        p = await project_of(user["org_id"], pid, user, write=False)
        ev = await event_of(user["org_id"], p["evento_id"], user, write=False)
        rows = (await state(user["org_id"], p))["rows"]
        if ext == "xlsx":
            head = ["Categoria", "Codice materiale", "Descrizione", "Unità di misura", "Quantità da mappa", "Rettifica manuale", "Quantità totale", "Fornitore", "Note", "Stato"]
            data = [[x["categoria"], x["code"], x["description"], x["unit"], _num(x["map_qty"]), _num(x["adjust"]), None, x["supplier"], x["notes"], STATUSES[x["status"]]] for x in rows]
            return _file(xlsx(f"{ev['nome']} – {p['nome']} – Distinta materiali", [("Distinta", head, data, ("G", "=MAX(0,E{r}+F{r})"))]), f"distinta-{p['nome']}", "xlsx")
        if ext == "pdf":
            g = _groups(rows, lambda x: [x["code"], x["description"], x["unit"], _num(x["total"]), x["supplier"], STATUSES[x["status"]], x["notes"]])
            return _file(pdf(await org_logo(user["org_id"]), ev["nome"], p["nome"], g, ["Codice", "Descrizione", "UM", "Quantità", "Fornitore", "Stato", "Note"],
                             [0.12, 0.28, 0.06, 0.08, 0.14, 0.12, 0.2]), f"distinta-{p['nome']}", "pdf", bool(inline))
        raise HTTPException(status_code=404, detail="Formato non disponibile")

    @r.get("/events/{eid}/bom/export.{ext}")
    async def export_event(eid: str, ext: str, inline: int = 0, user: dict = Depends(member_dep)):
        ev = await event_of(user["org_id"], eid, user, write=False)
        s = await summary(user["org_id"], eid)
        ps = s["projects"]
        if ext == "xlsx":
            head = ["Categoria", "Codice materiale", "Descrizione", "Unità di misura"] + [p["nome"] for p in ps] + ["Totale evento"]
            from openpyxl.utils import get_column_letter
            a, b, t = get_column_letter(5), get_column_letter(4 + len(ps)), get_column_letter(5 + len(ps))
            data = [[x["categoria"], x["code"], x["description"], x["unit"]] + [_num(x["by_project"].get(p["id"], 0)) for p in ps] + [None] for x in s["rows"]]
            return _file(xlsx(f"{ev['nome']} – Riepilogo materiali evento", [("Riepilogo", head, data, (t, f"=SUM({a}{{r}}:{b}{{r}})" if ps else "=0"))]), f"riepilogo-materiali-{ev['nome']}", "xlsx")
        if ext == "pdf":
            g = _groups(s["rows"], lambda x: [x["code"], x["description"], x["unit"], _num(x["total"]),
                                              "; ".join(f"{p['nome']}: {_num(x['by_project'][p['id']])}" for p in ps if x["by_project"].get(p["id"]))])
            return _file(pdf(await org_logo(user["org_id"]), ev["nome"], "Riepilogo materiali evento", g, ["Codice", "Descrizione", "UM", "Totale", "Suddivisione per progetto"],
                             [0.12, 0.3, 0.06, 0.08, 0.44]), f"riepilogo-materiali-{ev['nome']}", "pdf", bool(inline))
        raise HTTPException(status_code=404, detail="Formato non disponibile")

    async def copy(org_id, src, dst):
        b = await bom_of(org_id, src)
        if b:
            b.update({"project_id": dst, "copied_from": src})
            await db.planner_bom.insert_one(b)

    return copy
