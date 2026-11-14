import { Fragment, useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

const COLS = [["org", "Organizzazione"], ["aziende", "Aziende"], ["referenti", "Referenti collegati"], ["collegamenti_da_creare", "Collegamenti da creare"],
  ["cellulari_da_copiare", "Telefono → Cellulare"], ["n_senza_azienda", "Contatti senza azienda"], ["n_azienda_inesistente", "Azienda non trovata"]];

function Report({ rows }) {
  const [open, setOpen] = useState(null);
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
      <table className="w-full text-sm" data-testid="referenti-report">
        <thead className="bg-slate-50 text-left text-xs text-slate-500"><tr>{COLS.map(([k, l]) => <th key={k} className="px-3 py-2">{l}</th>)}</tr></thead>
        <tbody>{rows.map((r) => (<Fragment key={r.org_id}>
          <tr className="border-t border-slate-100 cursor-pointer hover:bg-slate-50" onClick={() => setOpen(open === r.org_id ? null : r.org_id)} data-testid={`ref-org-${r.org_id}`}>
            {COLS.map(([k]) => <td key={k} className="px-3 py-2">{r[k]}</td>)}</tr>
          {open === r.org_id && <tr key={`${r.org_id}-d`}><td colSpan={COLS.length} className="bg-slate-50 px-3 py-2 text-xs text-slate-600">
            <b>Contatti senza azienda</b> (restano salvati, da associare): {r.senza_azienda.join(", ") || "nessuno"}{r.n_senza_azienda > 50 ? " …" : ""}
            {r.n_azienda_inesistente > 0 && <div className="mt-1"><b>Collegati a un'azienda non più presente:</b> {r.azienda_inesistente.join(", ")}</div>}
          </td></tr>}
        </Fragment>))}</tbody>
      </table>
    </div>
  );
}

export default function PlatformReferenti() {
  const [rows, setRows] = useState(null);
  const [runs, setRuns] = useState([]);
  const [busy, setBusy] = useState(false);
  const load = () => {
    api.get("/admin/referenti-integrazione/anteprima").then(({ data }) => setRows(data.organizzazioni)).catch((e) => toast.error(formatApiError(e.response?.data?.detail)));
    api.get("/admin/referenti-integrazione/esecuzioni").then(({ data }) => setRuns(data)).catch(() => {});
  };
  useEffect(() => { load(); }, []);
  const act = async (url, msg) => {
    if (!window.confirm(msg)) return;
    setBusy(true);
    try { const { data } = await api.post(url); toast.success(`Fatto: ${JSON.stringify(data.collegamenti_creati ?? data.collegamenti_rimossi)} collegamenti, ${data.cellulari_copiati ?? data.cellulari_ripristinati} cellulari`); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  const tot = (k) => (rows || []).reduce((s, r) => s + r[k], 0);
  return (
    <div className="max-w-6xl space-y-6" data-testid="platform-referenti">
      <div><h1 className="font-display text-2xl font-bold">Integrazione referenti nelle Aziende</h1>
        <p className="text-sm text-slate-500">Collega alle aziende i contatti che hanno già un'azienda indicata e copia il Telefono nel Cellulare quando è vuoto. Nessun contatto viene cancellato; ogni esecuzione salva un backup ripristinabile.</p></div>
      {!rows ? <p className="text-sm text-slate-400">Analisi in corso...</p> : <>
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 bg-white p-4 text-sm" data-testid="referenti-totals">
          <span>Collegamenti da creare: <b>{tot("collegamenti_da_creare")}</b></span><span>Cellulari da copiare: <b>{tot("cellulari_da_copiare")}</b></span>
          <span>Contatti senza azienda: <b>{tot("n_senza_azienda")}</b></span>
          <Button className="ml-auto bg-tiffany text-slate-900 hover:bg-tiffany-hover" disabled={busy || !(tot("collegamenti_da_creare") + tot("cellulari_da_copiare"))}
            onClick={() => act("/admin/referenti-integrazione/esegui", "Eseguire l'integrazione su tutte le organizzazioni? Verrà salvato un backup ripristinabile.")} data-testid="referenti-run">Esegui integrazione</Button>
        </div>
        <Report rows={rows} />
      </>}
      <div><h2 className="mb-2 font-display text-lg font-bold">Esecuzioni e ripristino</h2>
        {runs.length === 0 ? <p className="text-sm text-slate-400">Nessuna esecuzione.</p> : runs.map((r) => (
          <div key={r.id} className="mb-2 flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm" data-testid={`ref-run-${r.id}`}>
            <span>{new Date(r.created_at).toLocaleString("it-IT")}</span><span>{r.collegamenti_creati ?? 0} collegamenti · {r.cellulari_copiati ?? 0} cellulari</span>
            <span className="text-xs text-slate-500">{r.stato}</span>
            {r.stato === "completato" && <Button size="sm" variant="outline" className="ml-auto" disabled={busy} onClick={() => act(`/admin/referenti-integrazione/ripristina/${r.id}`, "Ripristinare la situazione precedente a questa esecuzione?")} data-testid={`ref-restore-${r.id}`}>Ripristina</Button>}
          </div>))}
      </div>
    </div>
  );
}
