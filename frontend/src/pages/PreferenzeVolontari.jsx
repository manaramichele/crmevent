import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

const N = ({ l, v, id }) => <div className="rounded-lg border border-slate-200 bg-white p-3" data-testid={`avp-${id}`}><div className="text-[11px] text-slate-500">{l}</div><div className="text-xl font-semibold">{v}</div></div>;

function Report({ r }) {
  return (
    <div className="space-y-3 rounded-xl border border-slate-200 bg-slate-50/60 p-4" data-testid={`avp-report-${r.org_id}`}>
      <div className="font-semibold">{r.organizzazione} {r.simulazione ? <span className="text-xs text-amber-700">(simulazione: nulla è stato scritto)</span> : <span className="text-xs text-green-700">(aggiornamento eseguito · backup {r.run_id})</span>}</div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <N l="Disponibilità esaminate" v={r.disponibilita_esaminate} id="esaminate" /><N l="Preferenze recuperate" v={r.preferenze_recuperate} id="recuperate" />
        <N l="Preferenze collegate" v={r.preferenze_collegate} id="collegate" /><N l="Partecipazioni già corrette" v={r.partecipazioni_gia_corrette} id="corrette" />
        <N l="Confermati aggiornati" v={r.confermati_aggiornati} id="confermati" /><N l="Classificati aggiornati" v={r.classificati_aggiornati} id="classificati" />
        <N l="Con team o turni aggiornati" v={r.con_team_o_turni_aggiornati} id="teamturni" /><N l="Da classificare con preferenza" v={r.da_classificare_con_preferenza} id="daclass" />
      </div>
      <div className="text-xs text-slate-600">Stati: {Object.entries(r.stati).map(([k, v]) => `${k} ${v}`).join(" · ")} — Ruolo evento: {Object.entries(r.ruolo_evento).map(([k, v]) => `${k} ${v}`).join(" · ")}</div>
      <details className="text-xs"><summary className="cursor-pointer font-medium">Preferenze non recuperabili ({r.non_recuperabili.length})</summary>{r.non_recuperabili.map((x, i) => <div key={i}>{x.nome} · {x.evento} · {x.motivo}</div>)}</details>
      <details className="text-xs"><summary className="cursor-pointer font-medium">Anomalie e collegamenti ({r.anomalie.length})</summary>{r.anomalie.map((x, i) => <div key={i}>{x.tipo} · {x.nome} · {x.evento}</div>)}</details>
      <p className="text-[11px] text-slate-500">Nessuna anagrafica creata; ruoli, categorie, team, turni e conferme non vengono modificati. Le risposte originali restano intatte.</p>
    </div>
  );
}

export default function PreferenzeVolontari() {
  const [orgs, setOrgs] = useState([]);
  const [org, setOrg] = useState("");
  const [reps, setReps] = useState(null);
  const [busy, setBusy] = useState(false);
  const [previewed, setPreviewed] = useState(false);
  useEffect(() => { api.get("/platform/avail-prefs/orgs").then(({ data }) => setOrgs(data.orgs)).catch(() => {}); }, []);
  const go = async (apply) => {
    if (apply && !window.confirm("Eseguire l'aggiornamento? Verrà salvato un backup dei campi modificati.")) return;
    setBusy(true);
    try { const { data } = await api.post(`/platform/avail-prefs/${apply ? "apply" : "preview"}`, { org_id: org || null }); setReps(data.reports); setPreviewed(!apply); toast.success(apply ? "Aggiornamento completato" : "Anteprima pronta"); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    setBusy(false);
  };
  return (
    <div className="space-y-4 p-4 md:p-8" data-testid="avp-page">
      <h1 className="text-2xl font-semibold">Recupero preferenze volontari</h1>
      <p className="text-sm text-slate-600 max-w-3xl">Collega a ogni partecipazione la preferenza che il volontario aveva indicato nel modulo pubblico della Raccolta disponibilità, anche per chi è già confermato, classificato o assegnato a team e turni. Prima esegui l'anteprima, poi l'aggiornamento. È ripetibile senza creare duplicati.</p>
      <div className="flex flex-wrap items-center gap-2">
        <select className="h-10 rounded-md border border-slate-200 bg-white px-2 text-sm" value={org} onChange={(e) => { setOrg(e.target.value); setPreviewed(false); setReps(null); }} data-testid="avp-org">
          <option value="">Tutte le organizzazioni</option>{orgs.map((o) => <option key={o.id} value={o.id}>{o.nome} ({o.disponibilita})</option>)}
        </select>
        <Button variant="outline" onClick={() => go(false)} disabled={busy} data-testid="avp-preview">Anteprima e report</Button>
        <Button onClick={() => go(true)} disabled={busy || !previewed} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="avp-apply">Esegui aggiornamento</Button>
      </div>
      {(reps || []).map((r) => <Report key={r.org_id} r={r} />)}
    </div>
  );
}
