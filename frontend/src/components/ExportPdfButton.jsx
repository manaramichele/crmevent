import { useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { FileDown, Lock } from "lucide-react";
import { toast } from "sonner";

const OPTIONAL = [["telefono", "Telefono"], ["team", "Team"], ["taglia", "Taglia"], ["disp_dal", "Disponibilità dal"], ["disp_al", "Disponibilità al"]];
const TITLES = { staff: ["Elenco Staff", "Staff"], volontari: ["Elenco Volontari", "Volontari"], team: ["Elenco Team", "Team"] };
const prefKey = (s) => `crmevent_pdf_cols_${s}`;
const loadPrefs = (s) => { try { return JSON.parse(sessionStorage.getItem(prefKey(s))) || ["telefono", "team"]; } catch { return ["telefono", "team"]; } };
const fileName = (slug, ev) => `CRMEvent_${slug}_${((ev || "Evento").replace(/(^|\s)\S/g, (c) => c.toUpperCase()).replace(/[^A-Za-z0-9]+/g, "").slice(0, 40) || "Evento")}_${new Date().toLocaleDateString("sv-SE", { timeZone: "Europe/Rome" })}.pdf`;

export default function ExportPdfButton({ section, eventoId, eventName, personIds, teamIds, scopeLabel, testid = `export-pdf-${section}` }) {
  const [open, setOpen] = useState(false);
  const [cols, setCols] = useState(() => loadPrefs(section));
  const [busy, setBusy] = useState(false);
  const [title, slug] = TITLES[section];
  const flip = (k) => setCols((c) => { const n = c.includes(k) ? c.filter((x) => x !== k) : [...c, k]; sessionStorage.setItem(prefKey(section), JSON.stringify(n)); return n; });
  const run = async () => {
    setBusy(true);
    try {
      const res = await api.post("/staff/export-pdf", { section, evento_id: eventoId, person_ids: personIds ?? null, team_ids: teamIds ?? null, columns: cols }, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url; a.download = fileName(slug, eventName); document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 4000);
      toast.success("PDF generato"); setOpen(false);
    } catch (e) {
      let msg = e.response?.data;
      if (msg instanceof Blob) { try { msg = JSON.parse(await msg.text()).detail; } catch { msg = null; } }
      toast.error(formatApiError(msg?.detail || msg) || "Esportazione non riuscita");
    } finally { setBusy(false); }
  };
  return (<>
    <Button type="button" variant="outline" size="sm" className="h-10 shrink-0" onClick={() => setOpen(true)} data-testid={testid}><FileDown className="w-4 h-4 mr-1.5" />Esporta PDF</Button>
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="w-[95vw] max-w-md" data-testid={`${testid}-dialog`}>
        <DialogHeader>
          <DialogTitle className="font-display">{title} · PDF</DialogTitle>
          <DialogDescription>{eventoId ? `${eventName || "Evento"}${scopeLabel ? ` · ${scopeLabel}` : ""}` : "Seleziona prima un evento nei filtri: il PDF riguarda un solo evento."}</DialogDescription>
        </DialogHeader>
        {eventoId && (
          <div className="space-y-3 text-sm">
            <div><div className="text-xs font-semibold text-slate-500 mb-1.5">Colonne sempre presenti</div>
              <div className="flex flex-wrap gap-1.5">{["Cognome", "Nome", "Ruolo"].map((c) => <span key={c} className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600"><Lock className="w-3 h-3" />{c}</span>)}</div></div>
            <div><div className="text-xs font-semibold text-slate-500 mb-1.5">Colonne facoltative</div>
              <div className="grid grid-cols-2 gap-2">{OPTIONAL.map(([k, l]) => (
                <label key={k} className="flex items-center gap-2 cursor-pointer rounded-md border border-slate-200 px-2.5 py-2 hover:bg-slate-50">
                  <input type="checkbox" className="accent-tiffany w-4 h-4" checked={cols.includes(k)} onChange={() => flip(k)} data-testid={`${testid}-col-${k}`} />{l}</label>))}</div></div>
            <p className="text-xs text-slate-400">Vengono esportati i filtri e la ricerca attivi, ordinati per cognome e nome.</p>
          </div>
        )}
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => setOpen(false)} data-testid={`${testid}-cancel`}>Annulla</Button>
          <Button disabled={!eventoId || busy} onClick={run} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid={`${testid}-confirm`}><FileDown className="w-4 h-4 mr-1.5" />{busy ? "Generazione…" : "Scarica PDF"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </>);
}
