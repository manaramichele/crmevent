"""Event Planner · nuoto e triathlon: esportazioni GPX/KML e report boe (coordinate salvate nel progetto, distanze geodetiche)."""
import io
import math
from xml.sax.saxutils import escape

from fastapi import Depends, HTTPException
from fastapi.responses import Response

R = 6371008.8


def dist(a, b) -> float:
    la1, la2 = math.radians(a[1]), math.radians(b[1])
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(math.radians(b[0] - a[0]) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def _routes(features, discipline=None):
    out = []
    for f in features:
        p, g = f.get("properties") or {}, f.get("geometry") or {}
        if g.get("type") == "LineString" and p.get("disciplina") and (not discipline or p.get("disciplina") == discipline):
            out.append(f)
    return out


def buoy_rows(features) -> list:
    routes = {f["properties"]["id"]: f for f in _routes(features)}
    buoys = [f for f in features if (f.get("properties") or {}).get("categoria") == "Boe" and (f.get("geometry") or {}).get("type") == "Point"]

    def key(f):
        p = f["properties"]
        return (p.get("link_route") or "~", p.get("link_idx") if p.get("link_idx") is not None else 10 ** 6, p.get("numero") or 10 ** 6, p.get("nome") or "")
    rows, prev, prog = [], None, 0.0
    for f in sorted(buoys, key=key):
        p, c = f["properties"], f["geometry"]["coordinates"]
        rt = routes.get(p.get("link_route"))
        if rt and p.get("link_idx") is not None:
            pts = rt["geometry"]["coordinates"][: int(p["link_idx"]) + 1]
            prog = sum(dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
            d_prev = prog - rows[-1]["progressiva"] if rows and rows[-1]["route"] == rt["properties"].get("nome") else None
        else:
            d_prev = dist(prev, c) if prev else None
            prog = prog + (d_prev or 0)
        rows.append({"numero": p.get("numero"), "nome": p.get("nome"), "tipologia": p.get("categoria_nome") or p.get("nome"), "colore": p.get("colore"),
                     "lat": round(c[1], 6), "lng": round(c[0], 6), "da_precedente": round(d_prev) if d_prev is not None else None,
                     "progressiva": round(prog), "note": p.get("note") or "", "responsabile": p.get("responsabile") or "",
                     "route": rt["properties"].get("nome") if rt else None})
        prev = c
    return rows


def attach(r, member_dep, project_of):
    @r.get("/projects/{pid}/export/{fmt}")
    async def export(pid: str, fmt: str, pubblico: bool = False, user: dict = Depends(member_dep)):
        pr = await project_of(user["org_id"], pid, user, write=False)
        hidden_layers = {l["id"] for l in pr.get("layers") or [] if not l.get("visibile", True)}
        feats = [f for f in pr.get("features") or [] if not (pubblico and ((f.get("properties") or {}).get("riservato") or (f.get("properties") or {}).get("layer_id") in hidden_layers))]
        name = "".join(ch if ch.isalnum() else "_" for ch in pr.get("nome") or "progetto")
        if fmt == "gpx":
            routes = _routes(feats, "nuoto") or _routes(feats)
            if not routes:
                raise HTTPException(status_code=400, detail="Nessun percorso con disciplina nel progetto: imposta la disciplina del percorso (es. Nuoto)")
            trk = "".join(f"<trk><name>{escape(f['properties'].get('nome') or 'Percorso')}</name><trkseg>" + "".join(f'<trkpt lat="{c[1]:.7f}" lon="{c[0]:.7f}"/>' for c in f["geometry"]["coordinates"]) + "</trkseg></trk>" for f in routes)
            wpt = "".join(f'<wpt lat="{b["lat"]}" lon="{b["lng"]}"><name>{escape(str(b["numero"] or "") + " " + (b["nome"] or ""))}</name></wpt>' for b in buoy_rows(feats))
            body = f'<?xml version="1.0" encoding="UTF-8"?><gpx version="1.1" creator="CRMEvent Event Planner" xmlns="http://www.topografix.com/GPX/1/1">{wpt}{trk}</gpx>'
            return Response(body, media_type="application/gpx+xml", headers={"Content-Disposition": f'attachment; filename="{name}.gpx"'})
        if fmt == "kml":
            pm = []
            for f in _routes(feats):
                coords = " ".join(f"{c[0]:.7f},{c[1]:.7f},0" for c in f["geometry"]["coordinates"])
                pm.append(f"<Placemark><name>{escape(f['properties'].get('nome') or 'Percorso')}</name><description>{escape(f['properties'].get('disciplina') or '')}</description><LineString><coordinates>{coords}</coordinates></LineString></Placemark>")
            for b in buoy_rows(feats):
                pm.append(f"<Placemark><name>{escape(str(b['numero'] or '') + ' ' + (b['nome'] or ''))}</name><description>{escape(b['note'])}</description><Point><coordinates>{b['lng']},{b['lat']},0</coordinates></Point></Placemark>")
            body = f'<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>{escape(pr.get("nome") or "")}</name>{"".join(pm)}</Document></kml>'
            return Response(body, media_type="application/vnd.google-earth.kml+xml", headers={"Content-Disposition": f'attachment; filename="{name}.kml"'})
        rows = buoy_rows(feats)
        head = ["N.", "Nome", "Tipologia", "Colore", "Latitudine", "Longitudine", "Da precedente (m)", "Progressiva (m)", "Note", "Responsabile posizionamento"]
        vals = [[x["numero"] or "", x["nome"] or "", x["tipologia"] or "", x["colore"] or "", x["lat"], x["lng"], "" if x["da_precedente"] is None else x["da_precedente"], x["progressiva"], x["note"], x["responsabile"]] for x in rows]
        if fmt == "boe.xlsx":
            from openpyxl import Workbook
            wb = Workbook()
            ws = wb.active
            ws.title = "Boe"
            ws.append(head)
            for v in vals:
                ws.append(v)
            buf = io.BytesIO()
            wb.save(buf)
            return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="{name}_boe.xlsx"'})
        if fmt == "boe.pdf":
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle
            buf = io.BytesIO()
            ss = getSampleStyleSheet()
            cell = lambda v: Paragraph(escape(str(v)), ss["BodyText"])  # noqa: E731
            t = Table([head] + [[cell(c) for c in v] for v in vals] if vals else [head], repeatRows=1)
            t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0ABAB5")), ("FONTSIZE", (0, 0), (-1, -1), 8),
                                   ("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            SimpleDocTemplate(buf, pagesize=landscape(A4), title=f"Elenco boe {pr.get('nome')}").build([
                Paragraph(f"Elenco boe · {escape(pr.get('nome') or '')}", ss["Title"]), t,
                Paragraph("Distanze geodetiche calcolate dalle coordinate salvate: stima cartografica, non sostituisce la misurazione in acqua.", ss["Italic"])])
            return Response(buf.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}_boe.pdf"'})
        raise HTTPException(status_code=400, detail="Formato non supportato")
