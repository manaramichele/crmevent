import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { IdCard, UserPlus, Users } from "lucide-react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/crm";
import { StatoBadge, fmtDate } from "@/components/asd/asdShared";

const CLS = { staff: ["Staff", "blue"], volontario: ["Volontario", "green"], da_classificare: ["Da classificare", "orange"] };
export const SHARED = ["nome", "cognome", "codice_fiscale", "data_nascita", "luogo_nascita", "sesso", "email", "cellulare", "indirizzo", "cap", "citta", "provincia", "nazione", "taglia"];
export const sharedOf = (p) => Object.fromEntries(SHARED.filter((k) => p?.[k]).map((k) => [k, p[k]]));

// Ricerca su tutta l'anagrafica dell'organizzazione: soci, Staff, Volontari, Da classificare e contatti.
export function AsdPeopleResults({ q, onAdd, onOpen, testid = "asd-people" }) {
  const [rows, setRows] = useState(null);
  useEffect(() => {
    if ((q || "").trim().length < 2) { setRows(null); return undefined; }
    const t = setTimeout(() => { api.get("/asd/anagrafica", { params: { q } }).then(({ data }) => setRows(data)).catch(() => setRows([])); }, 300);
    return () => clearTimeout(t);
  }, [q]);
  if (!rows) return null;
  if (!rows.length) return <p className="text-sm text-slate-500 py-2" data-testid={`${testid}-empty`}>Nessuna persona trovata nell'anagrafica dell'organizzazione.</p>;
  return (
    <ul className="divide-y divide-slate-100" data-testid={`${testid}-results`}>
      {rows.map((p) => (
        <li key={p.id} className="py-2.5 flex flex-col sm:flex-row sm:items-center gap-2" data-testid={`${testid}-row-${p.id}`}>
          <div className="flex-1 min-w-0">
            <div className="font-medium text-slate-900">{p.cognome} {p.nome}</div>
            <div className="text-xs text-slate-500 truncate">{[p.codice_fiscale, p.email, p.cellulare].filter(Boolean).join(" · ") || "—"}</div>
            <div className="flex flex-wrap gap-1 mt-1">
              {p.classificazione.map((c) => <StatusBadge key={c} color={CLS[c][1]}>{CLS[c][0]}</StatusBadge>)}
              {p.socio ? <><StatusBadge color="tiffany">Socio{p.socio.numero_socio ? ` n. ${p.socio.numero_socio}` : ""}</StatusBadge><StatoBadge s={p.socio.stato} testid={`${testid}-stato-${p.id}`} /></> : <StatusBadge color="gray">Non socio</StatusBadge>}
            </div>
          </div>
          {p.socio
            ? <Button size="sm" variant="outline" onClick={() => onOpen(p.socio.id)} data-testid={`${testid}-open-${p.id}`}><IdCard className="w-4 h-4 mr-1" />Apri scheda</Button>
            : <Button size="sm" className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" onClick={() => onAdd(p.id)} data-testid={`${testid}-add-${p.id}`}><UserPlus className="w-4 h-4 mr-1" />Persona già presente – Aggiungi come socio</Button>}
        </li>
      ))}
    </ul>
  );
}

// Sezione "Associazione Sportiva" nella scheda Staff / Volontari (visibile solo se il modulo è attivo e il profilo è abilitato).
export function AsdPersonSection({ personId }) {
  const nav = useNavigate();
  const [d, setD] = useState(null);
  useEffect(() => { if (personId) { api.get(`/asd/persona/${personId}`).then(({ data }) => setD(data)).catch(() => setD(null)); } }, [personId]);
  if (!d?.active) return null;
  const s = d.socio, t = d.tesseramento;
  return (
    <section className="rounded-lg border border-slate-200 p-3 space-y-2" data-testid="person-asd-section">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 flex items-center gap-1.5"><Users className="w-3.5 h-3.5" />Associazione Sportiva</h3>
      {s ? (
        <div className="flex flex-col sm:flex-row sm:items-center gap-2">
          <div className="flex-1 text-sm text-slate-700 space-y-1">
            <div className="flex flex-wrap items-center gap-1.5"><StatusBadge color="tiffany">Socio</StatusBadge><StatoBadge s={s.stato} testid="person-asd-stato" />{s.numero_socio && <span data-testid="person-asd-numero">n. {s.numero_socio}</span>}</div>
            <div className="text-xs text-slate-500" data-testid="person-asd-tess">{t ? <>Tessera {t.ente} {t.stagione}{t.numero_tessera ? ` · ${t.numero_tessera}` : ""} · <StatoBadge s={t.stato} />{t.data_scadenza ? ` · scade ${fmtDate(t.data_scadenza)}` : ""}</> : "Nessun tesseramento registrato"}</div>
          </div>
          <Button type="button" size="sm" variant="outline" onClick={() => nav(`/associazione?tab=soci&socio=${s.id}`)} data-testid="person-asd-open">Apri scheda associativa</Button>
        </div>
      ) : (
        <div className="flex flex-col sm:flex-row sm:items-center gap-2">
          <p className="flex-1 text-sm text-slate-500">Non è ancora socio dell'associazione.</p>
          <Button type="button" size="sm" variant="outline" onClick={() => nav(`/associazione?tab=soci&persona=${personId}`)} data-testid="person-asd-add"><UserPlus className="w-4 h-4 mr-1" />Aggiungi come socio</Button>
        </div>
      )}
    </section>
  );
}
