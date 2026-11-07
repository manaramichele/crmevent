import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { calApi, err, fmtD, Pill, SEL } from "./shared";

const FS = { verificato: ["Verificato", "#16A34A"], approvato: ["Approvato", "#0A8F8B"], da_verificare: ["Da verificare", "#D97706"],
  data_da_confermare: ["Data da confermare", "#6366F1"], scartato: ["Scartato", "#94A3B8"] };

function FindingRow({ x, reload }) {
  const [edit, setEdit] = useState(false);
  const [f, setF] = useState({ data_inizio: x.data_inizio || "", data_fine: x.data_fine || "", comune: x.comune || "", distanza: x.distanza || "" });
  const act = async (action) => {
    try { await api.post(calApi(`/reverse/findings/${x.id}/review`), { action, ...(action === "approva" ? f : {}) }); toast.success(action === "approva" ? "Evento inserito nel calendario" : "Risultato scartato"); reload(); } catch (e) { err(e); }
  };
  const [l, c] = FS[x.stato] || [x.stato, "#64748B"];
  const open = ["da_verificare", "data_da_confermare"].includes(x.stato);
  return (
    <div className="border border-slate-200 rounded-xl p-3 text-xs space-y-1 bg-white" data-testid={`rv-finding-${x.id}`}>
      <div className="flex flex-wrap items-center gap-2"><b className="text-sm">{x.nome}</b><Pill color={c} testid={`rv-finding-state-${x.id}`}>{l}</Pill>
        <span className="text-slate-500">attendibilità {x.attendibilita}%</span>{x.stato_evento !== "confermata" && <Pill color="#DC2626">{x.stato_evento}</Pill>}</div>
      <div className="text-slate-600">{x.organizzatore || "organizzatore non confermato"} · {x.disciplina} {x.distanza ? `· ${x.distanza}` : ""} · {x.data_inizio ? fmtD(x.data_inizio) : "data da confermare"}{x.data_fine && x.data_fine !== x.data_inizio ? ` – ${fmtD(x.data_fine)}` : ""} · {[x.comune, x.provincia, x.regione].filter(Boolean).join(", ") || "località n.d."} · anno {x.anno || "—"}</div>
      <div>Fonte: {x.fonte_url ? <a href={x.fonte_url} target="_blank" rel="noreferrer" className="underline break-all text-[#0A8F8B]">{x.fonte_url}</a> : "—"}{x.sito_ufficiale && <> · sito ufficiale <span className="break-all">{x.sito_ufficiale}</span></>}</div>
      {x.estratto && <div className="italic text-slate-500">"{x.estratto}"</div>}
      <div className="text-slate-400">Ultima verifica {fmtD(x.verificato_il?.slice(0, 10))} · {x.email}{x.nota ? ` · ${x.nota}` : ""}</div>
      {open && <div className="flex flex-wrap gap-2 pt-1">
        {edit && <><Input type="date" value={f.data_inizio} onChange={(e) => setF({ ...f, data_inizio: e.target.value })} className="h-8 w-36" data-testid={`rv-finding-start-${x.id}`} />
          <Input type="date" value={f.data_fine} onChange={(e) => setF({ ...f, data_fine: e.target.value })} className="h-8 w-36" data-testid={`rv-finding-end-${x.id}`} />
          <Input value={f.comune} onChange={(e) => setF({ ...f, comune: e.target.value })} placeholder="Comune" className="h-8 w-32" />
          <Input value={f.distanza} onChange={(e) => setF({ ...f, distanza: e.target.value })} placeholder="Distanza" className="h-8 w-28" /></>}
        <Button size="sm" variant="ghost" onClick={() => setEdit(!edit)} data-testid={`rv-finding-edit-${x.id}`}>{edit ? "Chiudi modifica" : "Correggi dati"}</Button>
        <Button size="sm" onClick={() => act("approva")} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900" data-testid={`rv-finding-approve-${x.id}`}>Approva e inserisci</Button>
        <Button size="sm" variant="outline" className="text-red-600" onClick={() => act("scarta")} data-testid={`rv-finding-reject-${x.id}`}>Scarta</Button>
      </div>}
    </div>
  );
}

export function FindingsReview({ onChange }) {
  const [stato, setStato] = useState("da_verificare,data_da_confermare");
  const [rows, setRows] = useState(null);
  const load = useCallback(() => api.get(calApi("/reverse/findings"), { params: { stato } }).then(({ data }) => setRows(data.rows)).catch(err), [stato]);
  useEffect(() => { load(); }, [load]);
  const reload = () => { load(); onChange(); };
  return (
    <div className="space-y-3" data-testid="rv-review">
      <div className="flex flex-wrap items-center gap-2"><select className={SEL} value={stato} onChange={(e) => setStato(e.target.value)} data-testid="rv-review-filter">
        <option value="da_verificare,data_da_confermare">Da verificare e date da confermare</option><option value="verificato,approvato">Verificati e approvati</option>
        <option value="scartato">Scartati</option><option value="">Tutti</option></select><span className="text-xs text-slate-500">{rows?.length ?? 0} risultati</span></div>
      {rows && !rows.length && <p className="text-xs text-slate-500">Nessun risultato.</p>}
      {(rows || []).map((x) => <FindingRow key={`${x.id}-${x.stato}`} x={x} reload={reload} />)}
    </div>
  );
}
