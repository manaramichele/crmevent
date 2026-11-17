"""Control Room (Fase 4): report finale evento in PDF ed Excel."""
import io
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException
from fastapi.responses import Response

from controlroom_itv import DEFAULT_ITV_TYPES

ROME = ZoneInfo("Europe/Rome")
CLOSED = {"chiuso", "annullato"}
LIGHT = {"bassa": "Verde", "media": "Giallo", "alta": "Rosso", "critica": "Rosso"}


def _t(iso, fmt="%d/%m %H:%M"):
    return datetime.fromisoformat(iso).astimezone(ROME).strftime(fmt) if iso else "—"


def _mins(a, b):
    return round((datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds() / 60, 1) if a and b else None


def _avg(v):
    v = [x for x in v if x is not None]
    return round(sum(v) / len(v), 1) if v else None


def attach(r, db, deps, H):
    ctx, q = H["ctx"], H["q"]
    base = "/controlroom/events/{event_id}/ops"

    async def collect(u, eid):
        ev, pm = await ctx(u, eid)
        if pm["role"] != "responsabile":
            raise HTTPException(status_code=403, detail="Report riservato al Responsabile Control Room")
        s = await db.cr_settings.find_one(q(u, eid), {"_id": 0}) or {}
        types = {t["key"]: t["label"] for t in (s.get("itv_types") or DEFAULT_ITV_TYPES)}
        posts = await db.cr_posts.find(q(u, eid), {"_id": 0}).sort("km", 1).to_list(2000)
        res = await db.cr_resources.find(q(u, eid), {"_id": 0}).to_list(5000)
        pers = {p["id"]: p for p in await db.persons.find({"org_id": u["org_id"], "id": {"$in": [x["persona_id"] for x in res if x.get("persona_id")]}}, {"_id": 0, "id": 1, "nome": 1, "cognome": 1}).to_list(5000)}
        for x in res:
            p = pers.get(x.get("persona_id"))
            if p:
                x["nome"] = f"{p.get('nome') or ''} {p.get('cognome') or ''}".strip()
        sectors = {x["id"]: x["nome"] for x in await db.cr_sectors.find(q(u, eid), {"_id": 0, "id": 1, "nome": 1}).to_list(500)}
        itv = await db.cr_interventions.find(q(u, eid), {"_id": 0, "history": 0}).sort("numero", 1).to_list(5000)
        diary = await db.cr_diary.find(q(u, eid), {"_id": 0}).sort("at", 1).to_list(20000)
        logo = None
        full = await db.events.find_one({"org_id": u["org_id"], "id": eid}, {"_id": 0, "logo_url": 1})
        if (full or {}).get("logo_url"):
            try:
                rec = await deps["resolve_attachment"](full["logo_url"], u["org_id"])
                logo = (await deps["read_file_rec"](rec))[0] if rec else None
            except Exception:
                logo = None
        pmap = {p["id"]: p["nome"] for p in posts}
        rows = [{"codice": i["codice"], "apertura": _t(i["created_at"]), "tipologia": types.get(i["tipologia"], i["tipologia"]), "priorita": i["priorita"],
                 "semaforo": f"{i['priorita']} ({LIGHT[i['priorita']]})", "stato": i["stato"].replace("_", " "), "posizione": " · ".join(str(v) for v in (pmap.get(i.get("post_id") or i.get("post_vicina_id")), i.get("km") is not None and f"km {i['km']}", i.get("riferimento")) if v),
                 "squadre": ", ".join(a["label"] or "" for a in i.get("assignments") or [] if a["stato"] != "revocata"), "presa_min": _mins(i["created_at"], i.get("t_presa")),
                 "risoluzione_min": _mins(i["created_at"], i.get("t_risoluzione")), "descrizione": i["descrizione"], "operatore": i.get("created_by_name")} for i in itv]
        return {"ev": ev, "logo": logo, "posts": posts, "res": res, "sectors": sectors, "itv": itv, "rows": rows, "diary": diary, "types": types,
                "by_type": Counter(types.get(i["tipologia"], i["tipologia"]) for i in itv), "open": [x for x, i in zip(rows, itv) if i["stato"] not in CLOSED],
                "critical": [x for x in rows if x["priorita"] in ("alta", "critica")], "avg_presa": _avg([x["presa_min"] for x in rows]), "avg_ris": _avg([x["risoluzione_min"] for x in rows])}

    def fname(d, ext):
        return f"report-control-room-{''.join(c if c.isalnum() else '-' for c in d['ev']['nome'].lower())[:40]}.{ext}"

    @r.get(base + "/report.pdf")
    async def report_pdf(event_id: str, u: dict = Depends(deps["require_admin"])):
        d = await collect(u, event_id)
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        ss = getSampleStyleSheet()
        sm = ss["BodyText"].clone("sm", fontSize=7.5, leading=9)
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm, bottomMargin=14 * mm, title=f"Report Control Room · {d['ev']['nome']}")
        W = A4[0] - 28 * mm

        def tbl(head, body, widths):
            t = Table([[Paragraph(f"<b>{h}</b>", sm) for h in head]] + [[Paragraph(str(c if c not in (None, "") else "—"), sm) for c in row] for row in body] if body else [[Paragraph("Nessun dato", sm)]],
                      colWidths=[W * w for w in widths] if body else [W], repeatRows=1)
            t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E6F7F6")), ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            return t
        st = []
        title = [Paragraph(f"<b>Report Control Room</b><br/>{d['ev']['nome']}", ss["Title"]), Paragraph(f"Data evento: {d['ev'].get('data_inizio') or '—'} · Generato il {datetime.now(ROME).strftime('%d/%m/%Y %H:%M')}", ss["BodyText"])]
        if d["logo"]:
            try:
                st.append(Table([[Image(io.BytesIO(d["logo"]), width=28 * mm, height=28 * mm, kind="proportional"), title]], colWidths=[32 * mm, W - 32 * mm], style=[("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
            except Exception:
                st += title
        else:
            st += title
        ppl = [x for x in d["res"] if x["kind"] == "persona"]
        summ = [["Postazioni", len(d["posts"])], ["Personale coinvolto", len(ppl)], ["Squadre e mezzi", len(d["res"]) - len(ppl)], ["Interventi totali", len(d["itv"])],
                ["Interventi rimasti aperti", len(d["open"])], ["Criticità (rosse)", len(d["critical"])], ["Tempo medio presa in carico (min)", d["avg_presa"] or "—"], ["Tempo medio risoluzione (min)", d["avg_ris"] or "—"]]
        h2 = ss["Heading2"]
        st += [Spacer(1, 6), Paragraph("Riepilogo", h2), tbl(["Voce", "Valore"], summ, [0.6, 0.4]),
               Paragraph("Segnalazioni per categoria", h2), tbl(["Categoria", "Numero"], sorted(d["by_type"].items(), key=lambda x: -x[1]), [0.7, 0.3]),
               Paragraph("Postazioni", h2), tbl(["Postazione", "Codice", "Settore", "Km", "Previsti", "Responsabile"], [[p["nome"], p.get("codice"), d["sectors"].get(p.get("sector_id")), p.get("km"), p.get("previsti"), p.get("responsabile")] for p in d["posts"]], [0.28, 0.12, 0.2, 0.08, 0.1, 0.22]),
               Paragraph("Personale e mezzi", h2), tbl(["Nome", "Tipo", "Postazione", "Presente"], [[x.get("nome") or x.get("codice"), x.get("tipologia") or x["kind"], next((p["nome"] for p in d["posts"] if p["id"] == x.get("post_id")), None), "sì" if x.get("presente") else "no"] for x in d["res"]], [0.35, 0.2, 0.3, 0.15]),
               Paragraph("Criticità principali", h2), tbl(["Codice", "Ora", "Tipologia", "Priorità", "Descrizione"], [[x["codice"], x["apertura"], x["tipologia"], f"{x['priorita']} ({x['semaforo']})", x["descrizione"]] for x in d["critical"]], [0.1, 0.12, 0.18, 0.15, 0.45]),
               Paragraph("Interventi effettuati", h2), tbl(["Codice", "Apertura", "Tipologia", "Priorità", "Stato", "Squadre", "Presa (min)", "Risol. (min)"], [[x["codice"], x["apertura"], x["tipologia"], x["semaforo"], x["stato"], x["squadre"], x["presa_min"], x["risoluzione_min"]] for x in d["rows"]], [0.09, 0.11, 0.17, 0.09, 0.13, 0.21, 0.1, 0.1]),
               Paragraph("Interventi rimasti aperti", h2), tbl(["Codice", "Apertura", "Tipologia", "Stato", "Descrizione"], [[x["codice"], x["apertura"], x["tipologia"], x["stato"], x["descrizione"]] for x in d["open"]], [0.1, 0.12, 0.2, 0.15, 0.43]),
               Paragraph("Cronologia delle attività", h2), tbl(["Data e ora", "Tipo", "Intervento", "Operatore", "Descrizione"], [[_t(x["at"], "%d/%m %H:%M:%S"), x["type"], x.get("codice"), x.get("by_name"), x["text"]] for x in d["diary"]], [0.14, 0.12, 0.1, 0.16, 0.48])]
        doc.build(st)
        return Response(content=buf.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{fname(d, "pdf")}"'})

    @r.get(base + "/report.xlsx")
    async def report_xlsx(event_id: str, u: dict = Depends(deps["require_admin"])):
        d = await collect(u, event_id)
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        wb = Workbook()
        sheets = {"Riepilogo": (["Voce", "Valore"], [["Evento", d["ev"]["nome"]], ["Data", d["ev"].get("data_inizio")], ["Postazioni", len(d["posts"])], ["Personale", sum(1 for x in d["res"] if x["kind"] == "persona")],
                                                    ["Interventi", len(d["itv"])], ["Aperti", len(d["open"])], ["Criticità rosse", len(d["critical"])], ["Media presa in carico (min)", d["avg_presa"]], ["Media risoluzione (min)", d["avg_ris"]]]
                                + [[f"Categoria: {k}", v] for k, v in d["by_type"].items()]),
                  "Postazioni": (["Postazione", "Codice", "Settore", "Km", "Previsti", "Responsabile"], [[p["nome"], p.get("codice"), d["sectors"].get(p.get("sector_id")), p.get("km"), p.get("previsti"), p.get("responsabile")] for p in d["posts"]]),
                  "Personale": (["Nome", "Tipo", "Tipologia", "Stato", "Presente"], [[x.get("nome") or x.get("codice"), x["kind"], x.get("tipologia"), x["stato"], "sì" if x.get("presente") else "no"] for x in d["res"]]),
                  "Interventi": (["Codice", "Apertura", "Tipologia", "Priorità", "Semaforo", "Stato", "Posizione", "Squadre", "Presa in carico (min)", "Risoluzione (min)", "Operatore", "Descrizione"],
                                 [[x[k] for k in ("codice", "apertura", "tipologia", "priorita", "semaforo", "stato", "posizione", "squadre", "presa_min", "risoluzione_min", "operatore", "descrizione")] for x in d["rows"]]),
                  "Cronologia": (["Data e ora", "Tipo", "Intervento", "Operatore", "Descrizione"], [[_t(x["at"], "%d/%m/%Y %H:%M:%S"), x["type"], x.get("codice"), x.get("by_name"), x["text"]] for x in d["diary"]])}
        for i, (name, (head, rows)) in enumerate(sheets.items()):
            ws = wb.active if i == 0 else wb.create_sheet()
            ws.title = name
            ws.append(head)
            for c in ws[1]:
                c.font, c.fill = Font(bold=True), PatternFill("solid", fgColor="E6F7F6")
            for row in rows:
                ws.append(row)
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = min(60, max(10, *(len(str(c.value or "")) for c in col)))
        buf = io.BytesIO()
        wb.save(buf)
        return Response(content=buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="{fname(d, "xlsx")}"'})
