import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";
import { ShieldCheck, Save } from "lucide-react";
import { pErr, dt, TIFFANY_BTN, Field, useLoad } from "@/components/press/pressShared";

function Automation({ ev, cur, canEdit, onSaved }) {
  const [a, setA] = useState({ enabled: false, delay_days: 1, send_time: "10:00", ...(cur || {}) });
  const save = async (patch) => {
    const next = { ...a, ...patch };
    setA(next);
    try { await api.put(`/press/automations/${ev.id}`, { enabled: next.enabled, delay_days: Number(next.delay_days), send_time: next.send_time, media: next.media || [], regioni: next.regioni || [] }); toast.success("Automazione aggiornata"); onSaved(); } catch (e) { pErr(e); }
  };
  return (
    <div className="flex flex-wrap items-center gap-3 px-4 py-3 border-t border-slate-100" data-testid={`press-auto-${ev.id}`}>
      <div className="flex-1 min-w-[180px]"><div className="text-sm font-medium text-slate-800">{ev.nome}</div><div className="text-xs text-slate-500">Fine evento: {(ev.data_fine || ev.data_inizio || "—").slice(0, 10)}</div></div>
      <label className="flex items-center gap-2 text-xs text-slate-600"><Switch disabled={!canEdit} checked={!!a.enabled} onCheckedChange={(v) => save({ enabled: v })} data-testid={`press-auto-toggle-${ev.id}`} />Comunicato post-evento</label>
      <label className="flex items-center gap-1 text-xs text-slate-600">dopo <Input disabled={!canEdit} type="number" min={0} max={30} className="w-16 h-9" value={a.delay_days} onChange={(e) => setA({ ...a, delay_days: e.target.value })} onBlur={() => save({})} /> giorni alle</label>
      <Input disabled={!canEdit} type="time" className="w-28 h-9" value={a.send_time} onChange={(e) => setA({ ...a, send_time: e.target.value })} onBlur={() => save({})} data-testid={`press-auto-time-${ev.id}`} />
    </div>
  );
}

export function PressSettings({ canEdit, events }) {
  const [d, load] = useLoad("/press/settings");
  const [s, setS] = useState(null);
  useEffect(() => { if (d) setS({ sender_name: "", sender_email: "", reply_to: "", referente: "", telefono: "", org_info: "", ...d.settings }); }, [d]);
  if (!d || !s) return <p className="text-sm text-slate-400">Caricamento...</p>;
  const set = (k) => (e) => setS({ ...s, [k]: e.target.value });
  const save = async () => { try { await api.put("/press/settings", s); toast.success("Impostazioni salvate"); load(); } catch (e) { pErr(e); } };
  const verify = async () => { try { const { data } = await api.post("/press/settings/verify-sender"); toast[data.verified ? "success" : "message"](data.message); load(); } catch (e) { pErr(e); } };
  const autos = Object.fromEntries((d.automations || []).map((a) => [a.event_id, a]));
  return (
    <div className="space-y-6" data-testid="press-settings">
      <section className="rounded-2xl border border-slate-200 bg-white p-4 sm:p-5 space-y-3">
        <h3 className="font-semibold text-slate-900">Mittente e referente stampa</h3>
        <div className="grid sm:grid-cols-2 gap-3">
          <Field label="Nome mittente *"><Input disabled={!canEdit} value={s.sender_name} onChange={set("sender_name")} data-testid="press-set-sender-name" /></Field>
          <Field label="Email mittente *" hint="Indirizzo della tua organizzazione, da verificare su Brevo."><Input disabled={!canEdit} value={s.sender_email} onChange={set("sender_email")} data-testid="press-set-sender-email" /></Field>
          <Field label="Email per le risposte"><Input disabled={!canEdit} value={s.reply_to} onChange={set("reply_to")} data-testid="press-set-reply" /></Field>
          <Field label="Referente stampa"><Input disabled={!canEdit} value={s.referente} onChange={set("referente")} data-testid="press-set-referente" /></Field>
          <Field label="Telefono referente"><Input disabled={!canEdit} value={s.telefono} onChange={set("telefono")} data-testid="press-set-telefono" /></Field>
        </div>
        <Field label="Informazioni sull'organizzazione (piè di pagina email)"><Textarea disabled={!canEdit} rows={2} value={s.org_info} onChange={set("org_info")} data-testid="press-set-orginfo" /></Field>
        <div className="flex flex-wrap items-center gap-2">
          {canEdit && <Button onClick={save} className={TIFFANY_BTN} data-testid="press-set-save"><Save className="w-4 h-4 mr-1" />Salva</Button>}
          {canEdit && <Button variant="outline" onClick={verify} data-testid="press-set-verify"><ShieldCheck className="w-4 h-4 mr-1" />Verifica mittente su Brevo</Button>}
          <span className={`text-xs font-semibold ${d.settings.sender_verified ? "text-emerald-700" : "text-amber-700"}`} data-testid="press-set-verified">{d.settings.sender_verified ? "Mittente verificato" : "Mittente non verificato"}</span>
        </div>
        <p className="text-xs text-slate-500" data-testid="press-set-list">Lista Brevo: {d.list?.list_name || "—"} · stato {d.list?.sync_status || "—"} · ultima sincronizzazione {dt(d.list?.last_sync)}</p>
      </section>
      <section className="rounded-2xl border border-slate-200 bg-white overflow-hidden">
        <div className="p-4 sm:p-5"><h3 className="font-semibold text-slate-900">Automazione comunicato post-evento</h3>
          <p className="text-xs text-slate-500 mt-1">Alla conclusione dell'evento CRMEvent prepara una bozza con l'AI e la mette in "Da approvare". L'invio parte solo dopo la tua approvazione; se non approvi entro l'orario previsto, l'invio viene sospeso.</p></div>
        {(events || []).map((ev) => <Automation key={ev.id} ev={ev} cur={autos[ev.id]} canEdit={canEdit} onSaved={load} />)}
      </section>
    </div>
  );
}
