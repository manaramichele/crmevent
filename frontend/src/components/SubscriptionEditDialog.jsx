import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

const TABS = [["formula", "Formula"], ["date", "Date e rinnovi"], ["stato", "Stato"], ["custom", "Personalizzazioni"], ["storico", "Storico"]];
const PLANS = [["bronze", "BRONZE – €19/mese · 1 evento · 10 utenti"], ["silver", "SILVER – €49/mese · fino a 5 eventi · 30 utenti"], ["gold", "GOLD – €79/mese · eventi e utenti illimitati"]];
const STATUS = [["auto", "Automatico (Stripe / prova)"], ["trial", "Prova gratuita"], ["active", "Attivo"], ["expired", "Scaduto"], ["suspended", "Sospeso"]];
const LABEL = { plan: "Formula", status: "Stato", billing_cycle: "Periodicità", access_start: "Inizio abbonamento", access_end: "Scadenza abbonamento", renewal_date: "Prossimo rinnovo", trial_start: "Inizio prova", trial_end: "Fine prova", comp: "Piano omaggio", max_events: "Limite eventi", max_users: "Limite utenti", notes: "Note interne" };
const END = new Set(["access_end", "renewal_date", "trial_end"]);
const day = (s) => (s ? String(s).slice(0, 10) : "");
const toIso = (k, v) => (v ? `${v}T${END.has(k) ? "23:59:59" : "00:00:00"}Z` : null);
const show = (k, v) => (v === null || v === undefined || v === "" ? "—" : typeof v === "boolean" ? (v ? "Sì" : "No") : END.has(k) || k.endsWith("_start") ? new Date(v).toLocaleDateString("it-IT") : String(v));
const sel = "h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm";
const addDays = (s, n) => { const b = s && new Date(s) > new Date() ? new Date(s) : new Date(); b.setDate(b.getDate() + n); return b.toISOString().slice(0, 10); };

function initial(r) {
  const a = r.admin || {};
  return { plan: a.plan || r.paid_plan || "", status: a.status || "auto", billing_cycle: a.billing_cycle || r.billing_cycle || "", access_start: day(a.access_start || r.current_period_start || r.activated_at),
    access_end: day(a.access_end || r.current_period_end), renewal_date: day(a.renewal_date), trial_start: day(r.trial_start), trial_end: day(r.trial_end), comp: !!a.comp,
    max_events: a.max_events ?? "", max_users: a.max_users ?? "", notes: a.notes || "" };
}
const payload = (f) => ({ ...f, plan: f.plan || null, billing_cycle: f.billing_cycle || null, notes: f.notes || null,
  max_events: f.max_events === "" ? null : Number(f.max_events), max_users: f.max_users === "" ? null : Number(f.max_users),
  ...Object.fromEntries(["access_start", "access_end", "renewal_date", "trial_start", "trial_end"].map((k) => [k, toIso(k, f[k])])) });

function F({ label, children }) { return <label className="block space-y-1 text-xs font-medium text-slate-600">{label}{children}</label>; }

function History({ orgId }) {
  const [h, setH] = useState(null);
  useEffect(() => { api.get(`/platform/saas/orgs/${orgId}/history`).then(({ data }) => setH(data)).catch(() => setH([])); }, [orgId]);
  if (!h) return <p className="text-sm text-slate-400">Caricamento...</p>;
  if (!h.length) return <p className="text-sm text-slate-500" data-testid="sub-history-empty">Nessuna modifica registrata.</p>;
  return (
    <ul className="divide-y divide-slate-100 text-sm max-h-72 overflow-y-auto" data-testid="sub-history">
      {h.map((x) => <li key={x.id} className="py-2"><div className="font-medium">{LABEL[x.field] || x.field}: <span className="text-slate-500">{show(x.field, x.old)}</span> → {show(x.field, x.new)}</div>
        <div className="text-xs text-slate-400">{new Date(x.at).toLocaleString("it-IT")} · {x.admin_email}{x.reason ? ` · ${x.reason}` : ""}</div></li>)}
    </ul>
  );
}

export default function SubscriptionEditDialog({ row, onClose, onSaved }) {
  const [tab, setTab] = useState("formula");
  const [f, setF] = useState(() => initial(row));
  const [reason, setReason] = useState("");
  const [confirm, setConfirm] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));
  const base = initial(row);
  const diff = Object.keys(LABEL).filter((k) => String(base[k] ?? "") !== String(f[k] ?? ""));
  const internal = !!row.type && row.type !== "cliente";
  const statusOpts = internal ? STATUS.filter(([k]) => k !== "trial").map(([k, l]) => [k, k === "auto" ? "Automatico (formula assegnata, senza scadenza se non impostata)" : l]) : STATUS;
  const stripeEnd = row.stripe_status === "active" && row.current_period_end ? day(row.current_period_end) : null;
  const save = async () => {
    setBusy(true);
    try { await api.put(`/platform/saas/orgs/${row.id}/admin`, { ...payload(f), reason }); toast.success("Abbonamento aggiornato"); onSaved(); onClose(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  const fmtF = (k, v) => (END.has(k) || k.endsWith("_start") ? (v ? new Date(v).toLocaleDateString("it-IT") : "—") : show(k, v));
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl w-[calc(100vw-1.5rem)] max-h-[92dvh] overflow-y-auto" data-testid="sub-edit-dialog">
        <DialogTitle className="font-display text-xl">Abbonamento · {row.nome}</DialogTitle>
        <DialogDescription className="text-xs">Gestione accesso CRMEvent. Le modifiche non cambiano addebiti Stripe né fatture.{internal ? " Organizzazione Interna/Test: accesso gratuito, nessuna prova né pagamento." : ""}</DialogDescription>
        <div role="tablist" className="inline-flex max-w-full overflow-x-auto rounded-lg bg-slate-100 p-1 gap-1" data-testid="sub-edit-tabs">
          {TABS.map(([k, l]) => <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)} data-testid={`sub-tab-${k}`}
            className={`h-8 px-3 shrink-0 rounded-md text-sm font-medium transition-[background-color,color,box-shadow] ${tab === k ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-800"}`}>{l}</button>)}
        </div>
        <div className="space-y-3 min-h-[200px]">
          {tab === "formula" && <>
            <F label="Formula"><select value={f.plan} onChange={set("plan")} className={sel} data-testid="sub-plan"><option value="">—</option>{PLANS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></F>
            <F label="Periodicità"><select value={f.billing_cycle} onChange={set("billing_cycle")} className={sel} data-testid="sub-cycle"><option value="">—</option><option value="monthly">Mensile</option><option value="yearly">Annuale</option></select></F>
            <p className="text-xs text-slate-500">La formula si applica quando lo stato è "Attivo". Limiti standard: BRONZE 1 evento/10 utenti, SILVER 5 eventi/30 utenti, GOLD illimitati. Le eccezioni di limite valgono anche durante la prova.</p>
          </>}
          {tab === "date" && <div className="grid sm:grid-cols-2 gap-3">
            {[["access_start", "Inizio abbonamento"], ["access_end", "Scadenza abbonamento"], ["renewal_date", "Prossimo rinnovo (interno)"], ["trial_start", "Inizio prova gratuita"], ["trial_end", "Fine prova gratuita"]].filter(([k]) => !internal || !k.startsWith("trial")).map(([k, l]) =>
              <F key={k} label={l}><Input type="date" value={f[k]} onChange={set(k)} data-testid={`sub-${k}`} /></F>)}
            <div className="sm:col-span-2 rounded-lg bg-slate-50 p-3 text-xs text-slate-600" data-testid="sub-stripe-info">
              {stripeEnd ? <>Prossimo addebito Stripe: <b>{new Date(stripeEnd).toLocaleDateString("it-IT")}</b>{f.access_end && f.access_end !== stripeEnd && <span className="text-amber-700"> · diverso dalla scadenza CRMEvent ({new Date(f.access_end).toLocaleDateString("it-IT")})</span>}</> : "Nessun abbonamento Stripe attivo."}
            </div>
          </div>}
          {tab === "stato" && <>
            <F label="Stato"><select value={f.status} onChange={set("status")} className={sel} data-testid="sub-status">{statusOpts.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></F>
            <p className="text-xs text-slate-500">Prova gratuita: vale fino a "Fine prova". Attivo: accesso con la formula scelta fino alla scadenza. Scaduto/Sospeso: sola consultazione, nessun dato eliminato.</p>
          </>}
          {tab === "custom" && <div className="space-y-3">
            <div className="flex flex-wrap gap-2">
              {[7, 30].map((n) => <Button key={`a${n}`} size="sm" variant="outline" onClick={() => setF((s) => ({ ...s, access_end: addDays(s.access_end, n), status: s.status === "auto" ? "active" : s.status, plan: s.plan || "gold" }))} data-testid={`sub-extend-${n}`}>Proroga gratuita +{n} gg</Button>)}
              {!internal && [7, 14].map((n) => <Button key={`t${n}`} size="sm" variant="outline" onClick={() => setF((s) => ({ ...s, trial_end: addDays(s.trial_end, n) }))} data-testid={`sub-trial-${n}`}>Prova +{n} gg</Button>)}
            </div>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.comp} onChange={(e) => setF((s) => ({ ...s, comp: e.target.checked, status: e.target.checked ? "active" : s.status }))} data-testid="sub-comp" />Piano omaggio (accesso senza addebito)</label>
            <div className="grid grid-cols-2 gap-3">
              <F label="Eccezione limite eventi (-1 = illimitati)"><Input type="number" value={f.max_events} onChange={set("max_events")} placeholder="Standard" data-testid="sub-max-events" /></F>
              <F label="Eccezione limite utenti (-1 = illimitati)"><Input type="number" value={f.max_users} onChange={set("max_users")} placeholder="Standard" data-testid="sub-max-users" /></F>
            </div>
            <F label="Note amministrative interne"><Textarea rows={3} value={f.notes} onChange={set("notes")} data-testid="sub-notes" /></F>
          </div>}
          {tab === "storico" && <History orgId={row.id} />}
        </div>
        {confirm ? (
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 space-y-2" data-testid="sub-confirm">
            <div className="text-sm font-semibold">Riepilogo modifiche</div>
            <ul className="text-xs space-y-0.5">{diff.map((k) => <li key={k}>{LABEL[k]}: <span className="text-slate-500">{fmtF(k, base[k])}</span> → <b>{fmtF(k, f[k])}</b></li>)}</ul>
            <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Motivazione (facoltativa)" data-testid="sub-reason" />
            <div className="flex justify-end gap-2"><Button variant="outline" size="sm" onClick={() => setConfirm(null)} data-testid="sub-confirm-back">Indietro</Button>
              <Button size="sm" onClick={save} disabled={busy} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="sub-confirm-save">{busy ? "Salvataggio..." : "Conferma e salva"}</Button></div>
          </div>
        ) : (
          <div className="flex flex-col-reverse sm:flex-row gap-2 sm:justify-end">
            <Button variant="outline" onClick={onClose} data-testid="sub-cancel">Annulla</Button>
            <Button disabled={!diff.length} onClick={() => setConfirm(true)} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="sub-save">Salva modifiche</Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
