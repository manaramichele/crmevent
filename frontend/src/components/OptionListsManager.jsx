import { useCallback, useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { LISTS_CHANGED } from "@/lib/optionLists";
import { SectionCard } from "@/components/crm";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ArrowUp, ArrowDown, Pencil, Trash2, Check, X, Plus, EyeOff, Eye, ListChecks } from "lucide-react";
import { toast } from "sonner";
import { EntiSettings } from "@/components/asd/AsdEnti";

const err = (e) => toast.error(formatApiError(e.response?.data?.detail));

function ListCard({ list, params, canManage, reload }) {
  const [val, setVal] = useState("");
  const [edit, setEdit] = useState(null);
  const items = list.items;
  const k = list.key;
  const put = async (next) => {
    try { await api.put(`/settings/lists/${k}`, { items: next.map((i) => i.value), disattivati: next.filter((i) => !i.active).map((i) => i.value) }, { params }); window.dispatchEvent(new Event(LISTS_CHANGED)); reload(); }
    catch (e) { err(e); }
  };
  const add = async () => {
    if (!val.trim()) return;
    try { await api.post(`/settings/lists/${k}/items`, { value: val }, { params }); setVal(""); toast.success("Voce aggiunta"); window.dispatchEvent(new Event(LISTS_CHANGED)); reload(); } catch (e) { err(e); }
  };
  const rename = async () => {
    try { const { data } = await api.post(`/settings/lists/${k}/rename`, { old: edit.old, new: edit.value }, { params }); toast.success(data.records_updated ? `Rinominata (${data.records_updated} record aggiornati)` : "Rinominata"); setEdit(null); window.dispatchEvent(new Event(LISTS_CHANGED)); reload(); }
    catch (e) { err(e); }
  };
  const move = (i, d) => { const n = [...items]; [n[i], n[i + d]] = [n[i + d], n[i]]; put(n); };
  const toggle = (i) => put(items.map((x, j) => (j === i ? { ...x, active: !x.active } : x)));
  const remove = (i) => { if (window.confirm(`Eliminare "${items[i].value}"?`)) put(items.filter((_, j) => j !== i)); };
  const ib = "h-7 w-7 inline-flex items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 disabled:opacity-30";
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4" data-testid={`optlist-${k}`}>
      <div className="flex items-center justify-between gap-2 mb-2"><h4 className="text-sm font-semibold text-slate-800">{list.label}</h4><span className="text-xs text-slate-400">{items.length} voci</span></div>
      <ul className="divide-y divide-slate-100">
        {items.map((it, i) => (
          <li key={it.value} className="flex items-center gap-1.5 py-1.5" data-testid={`optlist-${k}-item-${i}`}>
            {edit?.old === it.value ? (<>
              <Input autoFocus value={edit.value} onChange={(e) => setEdit({ ...edit, value: e.target.value })} onKeyDown={(e) => e.key === "Enter" && rename()} className="h-8 text-sm" data-testid={`optlist-${k}-rename-input`} />
              <button className={ib} onClick={rename} data-testid={`optlist-${k}-rename-save`}><Check className="w-4 h-4 text-emerald-600" /></button>
              <button className={ib} onClick={() => setEdit(null)}><X className="w-4 h-4" /></button>
            </>) : (<>
              <span className={`flex-1 min-w-0 truncate text-sm ${it.active ? "text-slate-800" : "text-slate-400 line-through"}`}>{it.value}</span>
              {it.usage > 0 && <span className="text-[11px] text-slate-400 whitespace-nowrap" title="Record che usano questa voce">{it.usage} in uso</span>}
              {!it.active && <span className="text-[11px] font-semibold text-amber-700 bg-amber-50 rounded px-1.5">Disattivata</span>}
              {canManage && (<>
                <button className={ib} disabled={i === 0} onClick={() => move(i, -1)} title="Sposta su" data-testid={`optlist-${k}-up-${i}`}><ArrowUp className="w-3.5 h-3.5" /></button>
                <button className={ib} disabled={i === items.length - 1} onClick={() => move(i, 1)} title="Sposta giù" data-testid={`optlist-${k}-down-${i}`}><ArrowDown className="w-3.5 h-3.5" /></button>
                <button className={ib} onClick={() => setEdit({ old: it.value, value: it.value })} title="Rinomina" data-testid={`optlist-${k}-rename-${i}`}><Pencil className="w-3.5 h-3.5" /></button>
                {it.usage > 0
                  ? <button className={ib} onClick={() => toggle(i)} title={it.active ? "Disattiva (voce in uso)" : "Riattiva"} data-testid={`optlist-${k}-toggle-${i}`}>{it.active ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}</button>
                  : <>{!it.active && <button className={ib} onClick={() => toggle(i)} title="Riattiva" data-testid={`optlist-${k}-toggle-${i}`}><Eye className="w-3.5 h-3.5" /></button>}
                    <button className={`${ib} hover:text-red-500`} onClick={() => remove(i)} title="Elimina" data-testid={`optlist-${k}-delete-${i}`}><Trash2 className="w-3.5 h-3.5" /></button></>}
              </>)}
            </>)}
          </li>
        ))}
      </ul>
      <div className="flex gap-2 mt-2">
        <Input value={val} onChange={(e) => setVal(e.target.value)} onKeyDown={(e) => e.key === "Enter" && add()} placeholder="Nuova voce" className="h-9 text-sm" data-testid={`optlist-${k}-add-input`} />
        <Button variant="outline" size="sm" onClick={add} className="h-9 shrink-0" data-testid={`optlist-${k}-add`}><Plus className="w-4 h-4 mr-1" />Aggiungi</Button>
      </div>
    </div>
  );
}

export default function OptionListsManager({ platform = false }) {
  const [d, setD] = useState(null);
  const [asdOn, setAsdOn] = useState(false);
  useEffect(() => { if (!platform) { api.get("/asd/status").then(({ data }) => setAsdOn(!!data.active)).catch(() => setAsdOn(false)); } }, [platform]);
  const params = platform ? { scope: "platform" } : undefined;
  const reload = useCallback(() => api.get("/settings/lists", { params: platform ? { scope: "platform" } : undefined }).then(({ data }) => setD(data)).catch(err), [platform]);
  useEffect(() => { reload(); }, [reload]);
  if (!d) return <div className="text-slate-400 text-sm">Caricamento elenchi…</div>;
  const groups = [...new Set(d.lists.map((l) => l.group))];
  return (
    <SectionCard title={<span className="inline-flex items-center gap-2"><ListChecks className="w-4 h-4 text-tiffany-active" />Gestione menu a tendina{platform ? " · valori predefiniti piattaforma" : ""}</span>}>
      <p className="text-sm text-slate-500 mb-4" data-testid="optlists-intro">{platform ? "Valori di partenza per le nuove organizzazioni. Ogni organizzazione gestisce poi i propri elenchi." : "Un'unica fonte per tutti i menu a tendina dell'organizzazione. Le voci in uso non si eliminano: si disattivano e restano nei record storici."}</p>
      <div className="space-y-6">
        {groups.map((g) => (
          <div key={g} data-testid={`optgroup-${g}`}>
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">{g}</h3>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">{d.lists.filter((l) => l.group === g).map((l) => <ListCard key={l.key} list={l} params={params} canManage={d.can_manage} reload={reload} />)}</div>
          </div>
        ))}
        {asdOn && <div data-testid="optgroup-gestione-societa">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">Gestione Società</h3>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3"><EntiSettings /></div>
        </div>}
        {!platform && <div><h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">Altre sezioni</h3>
          <ul className="text-sm text-slate-500 space-y-1" data-testid="optlists-technical">{Object.entries(d.technical).map(([s, t]) => <li key={s}><b className="font-medium text-slate-700">{s}:</b> {t}</li>)}</ul></div>}
      </div>
    </SectionCard>
  );
}
