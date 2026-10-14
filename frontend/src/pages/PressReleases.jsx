import { useState } from "react";
import api from "@/lib/api";
import { PageHeader } from "@/components/crm";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Plus, Newspaper, Bell, Download } from "lucide-react";
import { TIPI, StatusPill, dt, TIFFANY_BTN, useLoad } from "@/components/press/pressShared";
import { NewRelease, Editor } from "@/components/press/PressEditor";
import { PressContacts } from "@/components/press/PressContacts";
import { PressSettings } from "@/components/press/PressSettings";

function Report({ id, onClose }) {
  const [d] = useLoad(`/press/releases/${id}/report`);
  const exp = () => {
    const lines = [["Email", "Esito", "Data", "Errore"], ...d.sends.map((s) => [s.email, s.status, s.sent_at || "", s.error || ""])];
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob(["\ufeff" + lines.map((l) => l.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(";")).join("\n")], { type: "text/csv" }));
    a.download = "report-comunicato.csv"; a.click();
  };
  const S = [["requests", "Inviate a Brevo"], ["delivered", "Consegnate"], ["hardBounces", "Respinte (hard)"], ["softBounces", "Respinte (soft)"], ["uniqueOpens", "Aperture"], ["uniqueClicks", "Clic"], ["unsubscribed", "Disiscrizioni"], ["blocked", "Bloccate"]];
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl w-[calc(100vw-1rem)] max-h-[94dvh] overflow-y-auto" data-testid="press-report">
        <DialogTitle>Report invio</DialogTitle>
        {!d ? <p className="text-sm text-slate-400">Caricamento...</p> : (<>
          <p className="text-sm text-slate-600">{d.release.titolo} · inviato {dt(d.release.sent_at)} · destinatari {d.release.recipients_count ?? "—"} · errori {d.release.error_count ?? 0}</p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">{S.map(([k, l]) => <div key={k} className="rounded-xl border border-slate-200 p-3"><div className="text-[11px] text-slate-500">{l}</div><div className="text-lg font-bold" data-testid={`press-report-${k}`}>{d.stats?.[k] ?? "—"}</div></div>)}</div>
          <p className="text-xs text-slate-500">{d.note} I dati provengono da Brevo; "—" indica statistiche non ancora disponibili.</p>
          <Button variant="outline" onClick={exp} data-testid="press-report-export"><Download className="w-4 h-4 mr-1" />Esporta report CSV</Button>
        </>)}
      </DialogContent>
    </Dialog>
  );
}

function Dashboard({ d, canEdit, onNew, onOpen, onReport }) {
  const C = [["Creati", d.total], ["Bozze", d.counts.bozza + d.counts.da_approvare], ["Programmati", d.counts.programmato], ["Inviati", d.counts.inviato], ["Contatti stampa", d.contacts], ["Ultimo invio", dt(d.last_sent_at)]];
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">{C.map(([l, v]) => <div key={l} className="rounded-2xl border border-slate-200 bg-white p-4" data-testid={`press-kpi-${l}`}><div className="text-xs text-slate-500">{l}</div><div className="mt-1 text-xl font-bold text-slate-900">{v}</div></div>)}</div>
      {d.counts.da_approvare > 0 && <div className="rounded-xl bg-amber-50 border border-amber-200 p-3 text-sm text-amber-800" data-testid="press-to-approve"><Bell className="inline w-4 h-4 mr-1" />{d.counts.da_approvare} comunicato/i da approvare.</div>}
      <div className="rounded-2xl border border-slate-200 bg-white overflow-x-auto">
        <table className="w-full min-w-[720px] text-sm" data-testid="press-releases-table">
          <thead className="bg-slate-50 text-xs text-slate-500"><tr>{["Evento", "Titolo", "Tipologia", "Stato", "Data invio", "Azioni"].map((h) => <th key={h} className="px-3 py-2.5 text-left font-semibold">{h}</th>)}</tr></thead>
          <tbody>{!d.releases.length ? <tr><td colSpan={6} className="p-10 text-center text-slate-500" data-testid="press-empty"><Newspaper className="w-8 h-8 mx-auto text-[#0ABAB5] mb-2" />Nessun comunicato.{canEdit && <Button onClick={onNew} variant="link">Crea il primo</Button>}</td></tr> : d.releases.map((r) => (
            <tr key={r.id} className="border-t border-slate-100" data-testid={`press-row-${r.id}`}>
              <td className="px-3 py-2.5">{r.event_name || "—"}</td><td className="px-3 py-2.5 max-w-[260px] truncate">{r.titolo || "—"}</td><td className="px-3 py-2.5 text-xs">{TIPI[r.tipo]}</td>
              <td className="px-3 py-2.5"><StatusPill s={r.status} /></td><td className="px-3 py-2.5 text-xs">{dt(r.sent_at || (r.status === "programmato" ? r.send_at : null))}</td>
              <td className="px-3 py-2.5">{r.status === "inviato" ? <Button size="sm" variant="outline" onClick={() => onReport(r.id)} data-testid={`press-report-${r.id}`}>Report</Button> : <Button size="sm" variant="outline" onClick={() => onOpen(r.id)} data-testid={`press-open-${r.id}`}>{r.status === "annullato" ? "Apri" : "Modifica"}</Button>}</td>
            </tr>))}</tbody>
        </table>
      </div>
    </div>
  );
}

export default function PressReleases() {
  const [st] = useLoad("/press/status");
  const [d, load] = useLoad("/press/dashboard");
  const [events] = useLoad("/press/events");
  const [creating, setCreating] = useState(false);
  const [open, setOpen] = useState(null);
  const [report, setReport] = useState(null);
  if (st && !st.active) return <div data-testid="press-inactive"><PageHeader title="Comunicati stampa" subtitle="Il servizio non è attivo per la tua organizzazione. Richiedilo dal Marketplace." /></div>;
  if (!st || !d) return <p className="p-6 text-sm text-slate-400">Caricamento...</p>;
  const canEdit = st.can_edit;
  return (
    <div data-testid="press-page">
      <PageHeader title="Comunicati stampa" subtitle="Comunicati con l'AI, rubrica media e invii tramite Brevo"
        action={canEdit && <Button onClick={() => setCreating(true)} className={TIFFANY_BTN} data-testid="press-new-button"><Plus className="w-4 h-4 mr-1" />Nuovo comunicato</Button>} />
      <Tabs defaultValue="dashboard">
        <TabsList className="mb-4 flex-wrap h-auto"><TabsTrigger value="dashboard" data-testid="press-tab-dashboard">Dashboard</TabsTrigger><TabsTrigger value="comunicati" data-testid="press-tab-comunicati">Comunicati</TabsTrigger><TabsTrigger value="contatti" data-testid="press-tab-contatti">Contatti stampa</TabsTrigger><TabsTrigger value="impostazioni" data-testid="press-tab-impostazioni">Impostazioni e automazioni</TabsTrigger></TabsList>
        <TabsContent value="dashboard"><Dashboard d={d} canEdit={canEdit} onNew={() => setCreating(true)} onOpen={setOpen} onReport={setReport} /></TabsContent>
        <TabsContent value="comunicati"><Dashboard d={{ ...d, releases: d.releases }} canEdit={canEdit} onNew={() => setCreating(true)} onOpen={setOpen} onReport={setReport} /></TabsContent>
        <TabsContent value="contatti"><PressContacts canEdit={canEdit} /></TabsContent>
        <TabsContent value="impostazioni"><PressSettings canEdit={canEdit} events={events || []} /></TabsContent>
      </Tabs>
      {creating && <NewRelease events={events || []} onClose={() => setCreating(false)} onCreated={(r) => { setCreating(false); load(); setOpen(r.id); }} />}
      {open && <Editor id={open} canEdit={canEdit} onClose={() => { setOpen(null); load(); }} onChanged={load} />}
      {report && <Report id={report} onClose={() => setReport(null)} />}
    </div>
  );
}
