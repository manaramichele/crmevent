import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { calApi, err, SEL, Pill, DISC_LABEL } from "./shared";
import { RecipientsPreview } from "./RecipientsPreview";

const fmtDT = (s) => (s ? new Date(s).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" }) : "—");

export function BrevoSenderSettings() {
  const [st, setSt] = useState(null);
  const [senders, setSenders] = useState(null);
  const [msg, setMsg] = useState("");
  const load = useCallback(() => api.get(calApi("/brevo/status")).then(({ data }) => setSt(data)).catch(err), []);
  useEffect(() => { load(); api.get(calApi("/brevo/senders")).then(({ data }) => setSenders(data.senders)).catch((e) => { setSenders([]); setMsg(e.response?.data?.detail || "Impossibile leggere i mittenti da Brevo"); }); }, [load]);
  const pick = async (id) => { try { await api.put(calApi("/brevo/sender"), { sender_id: Number(id) }); toast.success("Mittente salvato"); load(); } catch (e) { err(e); } };
  if (!st) return null;
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-2 text-sm max-w-2xl" data-testid="cal-brevo-sender">
      <div className="font-semibold">Mittente Brevo</div>
      <select className={`${SEL} w-full`} value={st.sender?.id || ""} onChange={(e) => pick(e.target.value)} disabled={!senders?.length} data-testid="cal-brevo-sender-select">
        <option value="" disabled>{senders ? "Scegli un mittente verificato" : "Caricamento mittenti..."}</option>
        {(senders || []).map((s) => <option key={s.id} value={s.id}>{s.name} &lt;{s.email}&gt;</option>)}
      </select>
      {msg && <p className="text-xs text-amber-700" data-testid="cal-brevo-sender-error">{msg}</p>}
      <p className="text-xs text-slate-500">Sono elencati solo i mittenti attivi e verificati sull'account Brevo di CRMEvent.</p>
    </div>
  );
}

function BrevoStatus({ st, reload }) {
  const [busy, setBusy] = useState(false);
  const sync = async () => {
    setBusy(true);
    try { const { data } = await api.post(calApi("/brevo/list/sync")); toast.success(`Lista aggiornata: +${data.aggiunti} nuovi, ${data.aggiornati} aggiornati, ${data.rimossi} rimossi`); reload(); } catch (e) { err(e); }
    setBusy(false);
  };
  const r = st.last_list_result;
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 text-sm space-y-2" data-testid="cal-brevo-status">
      <div className="flex flex-wrap items-center gap-2"><span className="font-semibold">Brevo</span>
        <Pill color={st.configured ? "#16A34A" : "#DC2626"} testid="cal-brevo-configured">{st.configured ? "Collegato" : "Non configurato"}</Pill>
        <Button size="sm" variant="outline" className="ml-auto" onClick={sync} disabled={busy || !st.configured} data-testid="cal-brevo-list-sync">{busy ? "Aggiornamento..." : "Aggiorna lista organizzatori"}</Button></div>
      <div className="text-xs text-slate-600 space-y-0.5">
        <div>Lista: <b>{st.list_name}</b> {st.list_id ? `(ID ${st.list_id})` : "— verrà creata al primo aggiornamento"}</div>
        <div>Contatti idonei con email: <b data-testid="cal-brevo-idonei">{st.idonei_con_email}</b> · ultimo aggiornamento: {fmtDT(st.last_list_sync)}{r ? ` · +${r.aggiunti} / ${r.aggiornati} aggiornati / ${r.rimossi} rimossi / ${r.disiscritti_brevo} disiscritti su Brevo` : ""}</div>
        <div>Mittente: {st.sender ? <b>{st.sender.name} &lt;{st.sender.email}&gt;</b> : <span className="text-amber-700">da scegliere in Impostazioni</span>}</div>
        <div>Nella lista entrano solo i contatti "Idoneo" non esclusi; chi non è più idoneo viene tolto. I contatti disiscritti non vengono mai reiscritti.</div>
      </div>
    </div>
  );
}

function TemplateEditor({ t, params, hasSender, reload }) {
  const [f, setF] = useState({ nome: t.nome, oggetto: t.oggetto, html: t.html });
  const [show, setShow] = useState(false);
  const save = async () => { try { await api.put(calApi(`/templates/${t.id}`), f); toast.success("Template salvato"); reload(); } catch (e) { err(e); } };
  const push = async () => { try { await api.put(calApi(`/templates/${t.id}`), f); await api.post(calApi(`/templates/${t.id}/brevo`)); toast.success("Template salvato su Brevo"); reload(); } catch (e) { err(e); } };
  const test = async () => { try { const { data } = await api.post(calApi(`/templates/${t.id}/test`), {}); toast.success(`Prova inviata a ${data.to}`); } catch (e) { err(e); } };
  return (
    <div className="border border-slate-200 rounded-xl p-3 space-y-2" data-testid={`cal-template-${t.id}`}>
      <div className="flex flex-wrap items-center gap-2"><b className="text-sm">{t.nome}</b>
        <Pill color={t.brevo_template_id ? "#16A34A" : "#D97706"} testid={`cal-template-state-${t.id}`}>{t.brevo_template_id ? `Su Brevo (ID ${t.brevo_template_id})` : "Non ancora su Brevo"}</Pill>
        {t.synced_at && <span className="text-[11px] text-slate-400">aggiornato su Brevo {fmtDT(t.synced_at)}</span>}</div>
      <Input value={f.nome} onChange={(e) => setF({ ...f, nome: e.target.value })} placeholder="Nome" data-testid={`cal-template-nome-${t.id}`} />
      <Input value={f.oggetto} onChange={(e) => setF({ ...f, oggetto: e.target.value })} placeholder="Oggetto" data-testid={`cal-template-oggetto-${t.id}`} />
      <Textarea rows={6} value={f.html} onChange={(e) => setF({ ...f, html: e.target.value })} className="font-mono text-xs" data-testid={`cal-template-html-${t.id}`} />
      <p className="text-[11px] text-slate-500">Variabili: {params.map((p) => `{{ params.${p} }}`).join(", ")}. Il link {"{{ params.UNSUB_URL }}"} è obbligatorio.</p>
      {show && <div className="border border-slate-200 rounded-lg p-2 bg-slate-50 max-h-72 overflow-auto" data-testid={`cal-template-preview-${t.id}`} dangerouslySetInnerHTML={{ __html: f.html }} />}
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="ghost" onClick={() => setShow(!show)} data-testid={`cal-template-toggle-preview-${t.id}`}>{show ? "Nascondi anteprima" : "Anteprima"}</Button>
        <Button size="sm" variant="outline" onClick={save} data-testid={`cal-template-save-${t.id}`}>Salva</Button>
        <Button size="sm" onClick={push} disabled={!hasSender} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900" data-testid={`cal-template-push-${t.id}`}>Salva su Brevo</Button>
        <Button size="sm" variant="outline" onClick={test} disabled={!t.brevo_template_id} data-testid={`cal-template-test-${t.id}`}>Invia prova a me</Button>
      </div>
    </div>
  );
}

function CampaignBuilder({ meta, templates }) {
  const [f, setF] = useState({ template_id: "post_evento", dal: "", al: "", disciplina: "", regione: "" });
  const [prev, setPrev] = useState(null);
  const set = (k) => (e) => { setF({ ...f, [k]: e.target.value }); setPrev(null); };
  const run = async () => { try { const { data } = await api.post(calApi("/campaigns/preview"), { ...f, dal: f.dal || null, al: f.al || null }); setPrev(data); } catch (e) { err(e); } };
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-3 text-sm" data-testid="cal-campaign-builder">
      <div className="font-semibold">Nuova campagna</div>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        <select className={SEL} value={f.template_id} onChange={set("template_id")} data-testid="cal-campaign-template">{templates.map((t) => <option key={t.id} value={t.id}>{t.nome}</option>)}</select>
        <Input type="date" value={f.dal} onChange={set("dal")} className="h-9" title="Data comunicazione dal" data-testid="cal-campaign-dal" />
        <Input type="date" value={f.al} onChange={set("al")} className="h-9" title="Data comunicazione al" data-testid="cal-campaign-al" />
        <select className={SEL} value={f.disciplina} onChange={set("disciplina")} data-testid="cal-campaign-disciplina"><option value="">Tutte le discipline</option>{Object.keys(meta.discipline).map((d) => <option key={d} value={d}>{DISC_LABEL[d]}</option>)}</select>
        <Input value={f.regione} onChange={set("regione")} placeholder="Regione" className="h-9" data-testid="cal-campaign-regione" />
      </div>
      <p className="text-xs text-slate-500">Eventi confermati o conclusi la cui data di comunicazione (fine evento + giorni impostati) cade nel periodo. Senza date: ultimi 60 giorni fino a oggi.</p>
      <Button onClick={run} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="cal-campaign-preview">Anteprima destinatari</Button>
      {prev && <RecipientsPreview prev={prev} filters={f} onDone={() => setPrev(null)} />}
    </div>
  );
}

export function CampaignsPanel({ meta }) {
  const [st, setSt] = useState(null);
  const [tp, setTp] = useState(null);
  const load = useCallback(() => {
    api.get(calApi("/brevo/status")).then(({ data }) => setSt(data)).catch(err);
    api.get(calApi("/templates")).then(({ data }) => setTp(data)).catch(err);
  }, []);
  useEffect(() => { load(); }, [load]);
  if (!st || !tp) return <p className="text-sm text-slate-500">Caricamento...</p>;
  return (
    <div className="space-y-4" data-testid="cal-campaigns">
      <BrevoStatus st={st} reload={load} />
      <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-3" data-testid="cal-templates"><div className="font-semibold text-sm">Template email</div>
        <div className="grid lg:grid-cols-2 gap-3">{tp.templates.map((t) => <TemplateEditor key={`${t.id}-${t.updated_at || ""}-${t.synced_at || ""}`} t={t} params={tp.params} hasSender={!!st.sender} reload={load} />)}</div></div>
      <CampaignBuilder meta={meta} templates={tp.templates} />
    </div>
  );
}
