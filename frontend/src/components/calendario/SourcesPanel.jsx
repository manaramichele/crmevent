import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { calApi, err, fmtD, Pill } from "./shared";
import { ConnDialog, NewSourceDialog, VerificaDialog } from "./SourceDialogs";

const ECOL = { consentita: "#16A34A", non_consentita: "#DC2626", da_verificare: "#D97706" };
const ELBL = { consentita: "Consentita", non_consentita: "Non consentita", da_verificare: "Da verificare" };
const fmtDT = (s) => (s ? new Date(s).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" }) : "—");

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

function SourceRow({ s, onVerifica, onConn, onSync, onDelete }) {
  const [open, setOpen] = useState(false);
  const v = s.verifica || {};
  const ok = v.esito === "consentita" && s.id !== "manuale";
  return (
    <>
      <tr className="border-t border-slate-100 align-top" data-testid={`cal-source-${s.id}`}>
        <td className="px-3 py-2 font-medium">{s.nome}{s.url && <div className="text-[11px] text-slate-400 break-all">{s.url}</div>}</td>
        <td className="px-3 py-2"><Pill color={ECOL[v.esito]} testid={`cal-source-esito-${s.id}`}>{ELBL[v.esito] || "—"}</Pill>
          <button className="block text-[11px] text-[#0A8F8B] underline mt-1" onClick={() => setOpen(!open)} data-testid={`cal-source-details-${s.id}`}>{open ? "Nascondi" : "Dettagli verifica"}</button></td>
        <td className="px-3 py-2"><Pill color={SCOL[s.stato]} testid={`cal-source-stato-${s.id}`}>{SLBL[s.stato]}</Pill>{s.ultimo_errore && s.stato === "errore" && <div className="text-[11px] text-red-600 mt-1 max-w-[220px]">{s.ultimo_errore}</div>}</td>
        <td className="px-3 py-2">{s.eventi}</td>
        <td className="px-3 py-2 text-xs">{fmtDT(s.ultima_sync)}</td>
        <td className="px-3 py-2">{s.id !== "manuale" && <div className="flex flex-wrap gap-1">
          <Button size="sm" variant="outline" onClick={() => onVerifica(s)} data-testid={`cal-source-verifica-${s.id}`}>Registra verifica</Button>
          {ok && <Button size="sm" variant="outline" onClick={() => onConn(s)} data-testid={`cal-source-conn-${s.id}`}>Collegamento</Button>}
          {ok && s.attiva && s.feed_url && <Button size="sm" onClick={() => onSync(s)} disabled={s.stato === "in_aggiornamento"} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900" data-testid={`cal-source-sync-${s.id}`}>Sincronizza ora</Button>}
          {s.custom && <Button size="sm" variant="ghost" className="text-red-600" onClick={() => onDelete(s)} data-testid={`cal-source-delete-${s.id}`}>Elimina</Button>}
        </div>}</td>
      </tr>
      {open && <tr className="bg-slate-50" data-testid={`cal-source-evidenze-${s.id}`}><td colSpan={6} className="px-3 py-2 text-xs text-slate-600 space-y-1">
        <div>Verificata il {fmtD(v.verificata_il)} · {v.verificata_da}{v.metodo ? ` · Metodo: ${v.metodo}` : ""}</div>
        {(v.evidenze || []).map((e) => <div key={e}>• {e}</div>)}
        {v.prova && <div>Prova: {v.prova}</div>}{v.note && <div>Note: {v.note}</div>}
        {v.esito !== "consentita" && v.come_sbloccare && <div className="text-amber-700">Per collegarla: {v.come_sbloccare}</div>}
      </td></tr>}
    </>
  );
}

export function SourcesPanel() {
  const [d, setD] = useState(null);
  const [dlg, setDlg] = useState(null);
  const load = useCallback(() => api.get(calApi("/sources")).then(({ data }) => setD(data)).catch(err), []);
  useEffect(() => { load(); }, [load]);
  const saved = () => { setDlg(null); load(); };
  const sync = async (s) => { try { await api.post(calApi(`/sources/${s.id}/sync`)); toast.success("Sincronizzazione avviata"); setTimeout(load, 1500); } catch (e) { err(e); } };
  const syncAll = async () => { try { const { data } = await api.post(calApi("/sync")); toast.success(data.fonti ? `Sincronizzazione avviata su ${data.fonti} fonti` : "Nessuna fonte autorizzata attiva da sincronizzare"); setTimeout(load, 1500); } catch (e) { err(e); } };
  const del = async (s) => { if (!window.confirm(`Eliminare la fonte "${s.nome}"? Gli eventi già importati restano nel calendario.`)) return; try { await api.delete(calApi(`/sources/${s.id}`)); toast.success("Fonte eliminata"); load(); } catch (e) { err(e); } };
  if (!d) return <p className="text-sm text-slate-500">Caricamento...</p>;
  const names = Object.fromEntries(d.sources.map((s) => [s.id, s.nome]));
  const active = d.sources.filter((s) => s.id !== "manuale" && ["attiva", "errore", "in_aggiornamento"].includes(s.stato)).length;
  return (
    <div className="space-y-4">
      <div className="rounded-xl bg-amber-50 border border-amber-200 p-3 text-xs text-amber-800" data-testid="cal-sources-note">Verifica accesso completata: nessuna delle fonti indicate (FIDAL, RaceUp, Wedosport, Running Around, FITRI, MyFITRI, Ironman) offre un'API, un feed o un'autorizzazione al riutilizzo automatico, quindi restano <b>scollegate</b> e si alimentano con l'importazione Excel/CSV. Una fonte si collega solo dopo aver registrato una verifica "Consentita" con la prova (accordo, licenza, API ufficiale).</div>
      <div className="flex flex-wrap items-center gap-2 text-xs text-slate-600" data-testid="cal-sync-bar">
        <span>Sincronizzazione automatica alle 03:00 (Europe/Rome): <b data-testid="cal-sync-auto-state">{d.raccolta_automatica ? "attiva" : "disattivata"}</b> · fonti collegate: <b data-testid="cal-sync-active-count">{active}</b> · ultima esecuzione: {fmtDT(d.ultima_sync_automatica)}</span>
        <div className="ml-auto flex gap-2"><Button size="sm" variant="outline" onClick={() => setDlg({ t: "new" })} data-testid="cal-source-add">Aggiungi fonte autorizzata</Button>
          <Button size="sm" onClick={syncAll} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900" data-testid="cal-sync-all">Sincronizza ora</Button></div>
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white"><table className="w-full min-w-[860px] text-sm" data-testid="cal-sources-table">
        <thead className="bg-slate-50 text-xs text-slate-500"><tr>{["Fonte", "Esito verifica", "Stato", "Eventi", "Ultima sincronizzazione", "Azioni"].map((h) => <th key={h} className="px-3 py-2 text-left">{h}</th>)}</tr></thead>
        <tbody>{d.sources.map((s) => <SourceRow key={s.id} s={s} onVerifica={(x) => setDlg({ t: "ver", s: x })} onConn={(x) => setDlg({ t: "conn", s: x })} onSync={sync} onDelete={del} />)}</tbody>
      </table></div>
      <div className="bg-white border border-slate-200 rounded-xl p-4 text-xs" data-testid="cal-imports-log"><div className="font-semibold text-sm mb-2">Importazioni e sincronizzazioni recenti</div>
        {!d.imports.length && <p className="text-slate-500">Nessuna attività.</p>}
        {d.imports.map((i) => <div key={i.id} className="border-t border-slate-100 py-1">{fmtDT(i.created_at)} · {i.kind === "sync" ? `Sincronizzazione ${i.trigger} · ${names[i.source] || i.source}` : i.file} · {i.status === "done" ? "completata" : i.status === "error" ? <span className="text-red-600">errore: {i.error}</span> : "in corso"} · nuovi {i.result?.created || 0}, collegati {i.result?.linked || 0}, duplicati {i.result?.possible_duplicates || 0}, errori {i.result?.errors || 0}</div>)}
      </div>
      <DuplicatesPanel />
      {dlg?.t === "ver" && <VerificaDialog src={dlg.s} onClose={() => setDlg(null)} onSaved={saved} />}
      {dlg?.t === "conn" && <ConnDialog src={dlg.s} onClose={() => setDlg(null)} onSaved={saved} />}
      {dlg?.t === "new" && <NewSourceDialog onClose={() => setDlg(null)} onSaved={saved} />}
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
        <label className="flex items-center gap-2 text-sm text-slate-700"><input type="checkbox" checked={!!s.raccolta_automatica} onChange={(e) => setS({ ...s, raccolta_automatica: e.target.checked })} data-testid="cal-set-auto" />Raccolta automatica ogni notte alle 03:00 (Europe/Rome), solo dalle fonti autorizzate e attive</label>
        <div>Lista e template Brevo, mittente: disponibili nella Fase 3.</div>
      </div>
      <Button onClick={save} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="cal-settings-save">Salva impostazioni</Button>
    </div>
  );
}
