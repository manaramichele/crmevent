import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { calApi, err, fmtD, Pill } from "./shared";

const SCOL = { attiva: "#16A34A", in_aggiornamento: "#0ABAB5", errore: "#DC2626", non_disponibile: "#64748B", disabilitata: "#94A3B8" };
const SLBL = { attiva: "Attiva", in_aggiornamento: "In aggiornamento", errore: "Errore", non_disponibile: "Non disponibile", disabilitata: "Disabilitata" };

export function DuplicatesPanel() {
  const [d, setD] = useState(null);
  const load = useCallback(() => api.get(calApi("/duplicates")).then(({ data }) => setD(data)).catch(err), []);
  useEffect(() => { load(); }, [load]);
  const act = async (url, action) => { try { await api.post(calApi(url), { action }); toast.success("Fatto"); load(); } catch (e) { err(e); } };
  if (!d) return null;
  const E = ({ e }) => <div className="text-xs"><b>{e.nome}</b> · {fmtD(e.data_inizio)} · {e.comune || "—"} {e.distanza ? `· ${e.distanza}` : ""}<div className="text-slate-400">Fonti: {(e.sources || []).map((s) => s.source).join(", ")}</div></div>;
  return (
    <div className="space-y-4">
      <div className="bg-white border border-slate-200 rounded-xl p-4" data-testid="cal-duplicates">
        <div className="font-semibold text-sm mb-2">Possibili duplicati ({d.duplicates.length})</div>
        {!d.duplicates.length && <p className="text-xs text-slate-500">Nessuna segnalazione aperta.</p>}
        {d.duplicates.map((x) => (
          <div key={x.id} className="border-t border-slate-100 py-2 grid md:grid-cols-[1fr_1fr_auto] gap-2 items-center" data-testid={`cal-dup-${x.id}`}>
            <E e={x.ev_a} /><E e={x.ev_b} />
            <div className="flex gap-1 flex-wrap"><Pill color="#D97706">{Math.round(x.score * 100)}%</Pill>
              <Button size="sm" variant="outline" onClick={() => act(`/duplicates/${x.id}/resolve`, "merge")} data-testid={`cal-dup-merge-${x.id}`}>Unisci</Button>
              <Button size="sm" variant="outline" onClick={() => act(`/duplicates/${x.id}/resolve`, "separate")} data-testid={`cal-dup-separate-${x.id}`}>Separati</Button>
              <Button size="sm" variant="ghost" onClick={() => act(`/duplicates/${x.id}/resolve`, "ignore")} data-testid={`cal-dup-ignore-${x.id}`}>Ignora</Button></div>
          </div>))}
      </div>
      <div className="bg-white border border-slate-200 rounded-xl p-4" data-testid="cal-conflicts">
        <div className="font-semibold text-sm mb-2">Dati in conflitto tra fonti ({d.conflicts.length})</div>
        {!d.conflicts.length && <p className="text-xs text-slate-500">Nessun conflitto.</p>}
        {d.conflicts.map((c) => (
          <div key={c.id} className="border-t border-slate-100 py-2 flex flex-wrap items-center gap-2 text-xs" data-testid={`cal-conflict-${c.id}`}>
            <b>{c.event_nome}</b> · {c.field === "data_inizio" ? "Data" : "Data fine"}: {fmtD(c.value)} vs {fmtD(c.other)} ({c.source})
            <Button size="sm" variant="outline" onClick={() => act(`/conflicts/${c.id}/resolve`, "keep")}>Mantieni {fmtD(c.value)}</Button>
            <Button size="sm" variant="outline" onClick={() => act(`/conflicts/${c.id}/resolve`, "use_other")}>Usa {fmtD(c.other)}</Button>
          </div>))}
      </div>
    </div>
  );
}

export function SourcesPanel() {
  const [d, setD] = useState(null);
  useEffect(() => { api.get(calApi("/sources")).then(({ data }) => setD(data)).catch(err); }, []);
  if (!d) return <p className="text-sm text-slate-500">Caricamento...</p>;
  return (
    <div className="space-y-4">
      <div className="rounded-xl bg-amber-50 border border-amber-200 p-3 text-xs text-amber-800" data-testid="cal-sources-note">Fase 1: nessuna fonte esterna è collegata. Nella Fase 2 verificherò per ciascuna API, feed, esportazioni e condizioni d'uso; quelle non consentite resteranno "Non disponibile" e si alimentano con l'importazione Excel/CSV.</div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white"><table className="w-full min-w-[760px] text-sm" data-testid="cal-sources-table">
        <thead className="bg-slate-50 text-xs text-slate-500"><tr>{["Fonte", "Disciplina", "Stato", "Accesso", "Eventi collegati", "Ultima sincronizzazione"].map((h) => <th key={h} className="px-3 py-2 text-left">{h}</th>)}</tr></thead>
        <tbody>{d.sources.map((s) => (
          <tr key={s.id} className="border-t border-slate-100" data-testid={`cal-source-${s.id}`}>
            <td className="px-3 py-2 font-medium">{s.nome}{s.url && <div className="text-[11px] text-slate-400">{s.url}</div>}</td><td className="px-3 py-2 text-xs">{s.disciplina}</td>
            <td className="px-3 py-2"><Pill color={SCOL[s.stato]}>{SLBL[s.stato]}</Pill></td><td className="px-3 py-2 text-xs">{s.accesso}</td><td className="px-3 py-2">{s.eventi}</td><td className="px-3 py-2 text-xs">{s.ultima_sync ? fmtD(s.ultima_sync.slice(0, 10)) : "—"}</td>
          </tr>))}</tbody>
      </table></div>
      <div className="bg-white border border-slate-200 rounded-xl p-4 text-xs" data-testid="cal-imports-log"><div className="font-semibold text-sm mb-2">Importazioni recenti</div>
        {!d.imports.length && <p className="text-slate-500">Nessuna importazione.</p>}
        {d.imports.map((i) => <div key={i.id} className="border-t border-slate-100 py-1">{fmtD(i.created_at.slice(0, 10))} · {i.file} · {i.status === "done" ? "completata" : "in corso"} · nuovi {i.result?.created || 0}, collegati {i.result?.linked || 0}, duplicati {i.result?.possible_duplicates || 0}, errori {i.result?.errors || 0}</div>)}
      </div>
      <DuplicatesPanel />
    </div>
  );
}

export function SettingsPanel({ meta, onSaved }) {
  const [s, setS] = useState(meta.settings);
  const save = async () => { try { await api.put(calApi("/settings"), { ...s, giorni_post_evento: Number(s.giorni_post_evento), intervallo_min_giorni: Number(s.intervallo_min_giorni) }); toast.success("Impostazioni salvate"); onSaved(); } catch (e) { err(e); } };
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-3 text-sm max-w-2xl" data-testid="cal-settings">
      <label className="block">Giorni dopo la fine dell'evento per la comunicazione
        <div className="flex gap-2 mt-1">{[7, 10].map((n) => <Button key={n} size="sm" variant={Number(s.giorni_post_evento) === n ? "default" : "outline"} onClick={() => setS({ ...s, giorni_post_evento: n })} data-testid={`cal-set-days-${n}`}>{n} giorni</Button>)}
          <Input type="number" min={1} max={90} value={s.giorni_post_evento} onChange={(e) => setS({ ...s, giorni_post_evento: e.target.value })} className="h-9 w-24" data-testid="cal-set-days" /></div></label>
      <label className="block">Intervallo minimo tra due comunicazioni allo stesso organizzatore (giorni)<Input type="number" min={1} max={365} value={s.intervallo_min_giorni} onChange={(e) => setS({ ...s, intervallo_min_giorni: e.target.value })} className="h-9 w-32 mt-1" data-testid="cal-set-interval" /></label>
      <div className="text-xs text-slate-500 space-y-1">
        <div>Modalità invio: <b>Manuale</b> (l'automatica sarà attivabile solo nella Fase 4).</div>
        <div>Raccolta automatica e orario (03:00 Europe/Rome), lista e template Brevo, mittente: disponibili nelle Fasi 2 e 3.</div>
      </div>
      <Button onClick={save} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="cal-settings-save">Salva impostazioni</Button>
    </div>
  );
}
