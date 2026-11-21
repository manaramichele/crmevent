import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { isOrgAdmin } from "@/lib/perms";
import { Printer, Plus, Users } from "lucide-react";

const fold = (s) => (s || "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
const fsel = "h-10 w-full sm:w-60 rounded-md border border-slate-200 bg-white px-2 text-sm";

async function downloadPdf(body, label) {
  try {
    const res = await api.post("/staff/groups-pdf", body, { responseType: "blob" });
    const url = URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
    const cd = res.headers?.["content-disposition"] || "";
    const a = document.createElement("a");
    a.href = url; a.download = (cd.match(/filename="([^"]+)"/) || [])[1] || `CRMEvent_${label}.pdf`;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
    toast.success("PDF generato");
  } catch (e) {
    let msg = e.response?.data;
    if (msg instanceof Blob) { try { msg = JSON.parse(await msg.text()).detail; } catch { msg = null; } }
    toast.error(formatApiError(msg) || "Stampa non riuscita");
  }
}

function GroupCard({ g, active, onPick }) {
  return (
    <button type="button" onClick={onPick} data-testid={`group-card-${g.name}`}
      className={`text-left rounded-xl border p-4 transition-colors ${active ? "border-tiffany bg-tiffany/10" : "border-slate-200 bg-white hover:border-tiffany/60"}`}>
      <div className="font-semibold text-slate-900 truncate" title={g.name}>{g.name}</div>
      <div className="mt-1 text-sm text-slate-600" data-testid={`group-counts-${g.name}`}><b>{g.total}</b> persone · Staff {g.staff} · Volontari {g.vol}</div>
      <div className="mt-1 text-xs text-slate-400 truncate" title={g.events.join(", ")}>{g.events.length ? g.events.join(", ") : "Nessun evento associato"}</div>
    </button>
  );
}

// Linguetta Gruppi: stessi dati della scheda Volontari, raggruppati per Gruppo di appartenenza (distinto dal Team operativo).
export default function GroupsTab({ rows, events, settings, user, renderTable }) {
  const nav = useNavigate();
  const [ev, setEv] = useState("all");
  const [sel, setSel] = useState("all");
  const inEv = (r) => ev === "all" || (r.eventi_ids || []).includes(ev) || (r.preferenze || []).some((p) => p.evento_id === ev);
  const groups = useMemo(() => {
    const names = new Set([...(settings?.gruppi_appartenenza || []), ...rows.map((r) => r.gruppo_appartenenza).filter(Boolean)]);
    return [...names].sort((a, b) => fold(a).localeCompare(fold(b))).map((name) => {
      const m = rows.filter((r) => r.gruppo_appartenenza === name && inEv(r));
      const asg = (r) => (r.assegnazioni || []).filter((a) => ev === "all" || a.evento_id === ev);
      const evs = [...new Set(m.flatMap((r) => (ev === "all" ? r.eventi_nomi || [] : [events.find((e) => e.id === ev)?.nome].filter(Boolean))))];
      return { name, members: m, total: m.length, events: evs,
        staff: m.filter((r) => asg(r).some((a) => ["staff", "collaboratore"].includes(a.categoria))).length,
        vol: m.filter((r) => asg(r).some((a) => a.categoria === "volontario")).length };
    });
  }, [rows, settings, ev, events]); // eslint-disable-line react-hooks/exhaustive-deps
  const shown = sel === "all" ? groups : groups.filter((g) => g.name === sel);
  const tableRows = shown.flatMap((g) => g.members);
  const evBody = ev === "all" ? null : ev;
  const addLink = isOrgAdmin(user) && (
    <Button variant="outline" size="sm" className="h-10" onClick={() => nav("/impostazioni?lista=gruppi_appartenenza")} data-testid="groups-add-btn"><Plus className="w-4 h-4 mr-1" />Aggiungi gruppo</Button>);
  if (!groups.length) {
    return (
      <div className="bg-white border border-dashed border-slate-300 rounded-xl p-10 text-center space-y-3" data-testid="groups-empty">
        <Users className="w-8 h-8 mx-auto text-slate-300" />
        <p className="text-slate-600">Nessun gruppo di appartenenza presente.</p>
        {addLink}
      </div>
    );
  }
  return (
    <div className="space-y-4" data-testid="groups-tab">
      <div className="flex flex-col sm:flex-row sm:flex-wrap gap-3">
        <select className={fsel} value={ev} onChange={(e) => setEv(e.target.value)} data-testid="groups-event-filter">
          <option value="all">Tutti gli eventi</option>{events.map((e) => <option key={e.id} value={e.id}>{e.nome}</option>)}
        </select>
        <select className={fsel} value={sel} onChange={(e) => setSel(e.target.value)} data-testid="groups-select">
          <option value="all">Tutti i gruppi</option>{groups.map((g) => <option key={g.name} value={g.name}>{g.name}</option>)}
        </select>
        <div className="flex flex-wrap gap-2 sm:ml-auto">
          {sel !== "all" && <Button size="sm" className="h-10 bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" onClick={() => downloadPdf({ evento_id: evBody, gruppo: sel }, "Gruppo")} data-testid="groups-print-one"><Printer className="w-4 h-4 mr-1" />Stampa gruppo</Button>}
          <Button variant="outline" size="sm" className="h-10" onClick={() => downloadPdf({ evento_id: evBody, gruppo: null }, "Gruppi")} data-testid="groups-print-all"><Printer className="w-4 h-4 mr-1" />Stampa tutti i gruppi</Button>
          {addLink}
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3" data-testid="groups-cards">
        {shown.map((g) => <GroupCard key={g.name} g={g} active={sel === g.name} onPick={() => setSel(sel === g.name ? "all" : g.name)} />)}
      </div>
      {renderTable(tableRows, evBody ?? "all")}
    </div>
  );
}
