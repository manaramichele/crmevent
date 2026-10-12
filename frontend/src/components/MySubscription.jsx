import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { CreditCard, Video, Mail, Crown, Check, ReceiptText, Settings2, RefreshCw } from "lucide-react";
import { usePlans, PlanCard, CycleToggle, eur } from "@/components/PlansSection";
import PlanBadge, { BILLING } from "@/components/PlanBadge";
import { UsageBars } from "@/components/UsageMeter";

const d = (s) => (s ? new Date(s).toLocaleDateString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric" }) : "—");
const CYC = { monthly: "Mensile", semester: "6 mesi", yearly: "12 mesi" };
const MODE = { trial: "Prova gratuita", active: "Attivo", past_due: "Pagamento in sospeso", canceled: "Annullato", expired: "Scaduto", suspended: "Sospeso" };
const SUB = { trial: "Prova gratuita", active: "Attivo", expiring: "In scadenza", expired: "Scaduto", suspended: "Sospeso" };
const eurO = (n) => (n || n === 0 ? `€${eur(n)}` : "—");

function Field({ label, value, testid }) {
  return <div><div className="text-xs uppercase text-slate-400 font-medium">{label}</div><div className="text-slate-800 font-medium" data-testid={testid}>{value}</div></div>;
}

function VideoUsage({ v }) {
  if (!v || v.mode !== "plan") return null;
  if (v.support === "email") return <div className="flex items-center gap-2 text-sm" data-testid="sub-video-usage"><Mail className="w-4 h-4 text-[#0ABAB5]" />Assistenza via email</div>;
  if (v.unlimited) return <div className="flex items-center gap-2 text-sm" data-testid="sub-video-usage"><Crown className="w-4 h-4 text-[#D4AF37]" />Videochiamate illimitate – Assistenza prioritaria</div>;
  return <div className="flex items-center gap-2 text-sm" data-testid="sub-video-usage"><Video className="w-4 h-4 text-[#0ABAB5]" />Videochiamate utilizzate: <b>{v.used} di {v.quota}</b>{v.trial ? " (prova)" : " questo mese"}</div>;
}

function Summary({ s, features, action }) {
  const isTrial = s.mode === "trial";
  const free = s.billing === "free";
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 sm:p-6 space-y-5" data-testid="my-subscription-summary">
      <div className="flex items-center justify-between gap-2"><div className="flex items-center gap-2"><CreditCard className="w-4 h-4 text-[#0ABAB5]" /><h2 className="font-semibold text-slate-800">Il mio abbonamento</h2></div>{action}</div>
      <div className="space-y-1.5" data-testid="sub-plan">
        <PlanBadge s={s} testid="sub-plan-badge" />
        <div className="text-sm text-slate-600" data-testid="sub-expiry">{isTrial ? "Fine prova" : "Scadenza"}: <b className="text-slate-800">{s.expires_at ? d(s.expires_at) : "Nessuna scadenza"}</b>{s.days_to_expiry != null && s.expires_at && <span data-testid="sub-days-left"> · {s.days_to_expiry === 0 ? "scade oggi" : `${s.days_to_expiry} giorni rimanenti`}</span>}</div>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
        <Field label="Stato" value={SUB[s.sub_status] || MODE[s.mode] || s.mode} testid="sub-status" />
        <Field label="Condizione economica" value={BILLING[s.billing] || "—"} testid="sub-billing" />
        <Field label="Eventi coperti" value={s.limits?.max_events < 0 ? "Illimitati" : s.limits?.max_events ?? "—"} testid="sub-events-covered" />
        {!free && s.paid_plan && <><Field label="Durata" value={CYC[s.billing_cycle] || "—"} testid="sub-cycle" />
        <Field label="Importo pagato" value={s.price_amount ? `€${eur(s.price_amount)}/${({ yearly: "12 mesi", semester: "6 mesi" })[s.billing_cycle] || "mese"}` : "—"} testid="sub-price" />
        <Field label="Rinnovo automatico" value={s.auto_renew ? "Attivo" : "Disattivato"} testid="sub-autorenew" />
        <Field label="Data attivazione" value={d(s.activated_at)} testid="sub-activated" />
        <Field label="Prossimo rinnovo" value={s.auto_renew && s.next_amount ? `${d(s.next_amount.date)} · ${eurO(s.next_amount.net)} IVA esclusa · ${eurO(s.next_amount.gross)} IVA inclusa${s.next_amount.vat_rate === 0 ? " (IVA 0%)" : ""}` : s.cancel_at_period_end ? `Termina il ${d(s.current_period_end)}` : "—"} testid="sub-renewal" /></>}
        {s.purchased && isTrial && <Field label="Piano acquistato" value={`${s.paid_plan_label} dal ${d(s.trial_end)}`} testid="sub-purchased" />}
      </div>
      {s.pending_change && <p className="text-sm rounded-lg bg-amber-50 text-amber-900 px-3 py-2" data-testid="sub-pending">Dal {d(s.pending_change.effective_at)} passerai a {s.pending_change.plan.toUpperCase()} {CYC[s.pending_change.cycle]?.toLowerCase()}.</p>}
      <UsageBars limits={s.limits} usage={s.usage} />
      <VideoUsage v={s.video} />
      <div>
        <div className="text-xs uppercase text-slate-400 font-medium mb-2">Funzionalità disponibili</div>
        <div className="flex flex-wrap gap-2" data-testid="sub-features">
          {features.filter((f) => s.features.includes(f.key)).map((f) => <span key={f.key} className="inline-flex items-center gap-1 rounded-full bg-[#0ABAB5]/10 px-2.5 py-1 text-xs text-slate-800"><Check className="w-3 h-3 text-[#0ABAB5]" />{f.label}</span>)}
        </div>
      </div>
    </div>
  );
}

function Payments({ rows }) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 sm:p-6" data-testid="sub-payments">
      <div className="flex items-center gap-2 mb-3"><ReceiptText className="w-4 h-4 text-[#0ABAB5]" /><h2 className="font-semibold text-slate-800">Storico abbonamenti e pagamenti</h2></div>
      {!rows?.length ? <p className="text-sm text-slate-500" data-testid="sub-payments-empty">Nessun pagamento registrato.</p> : (
        <div className="divide-y divide-slate-100">{rows.map((p) => (
          <div key={p.id} className="py-2.5 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-sm" data-testid={`sub-payment-${p.id}`}>
            <div className="min-w-0"><div className="font-medium text-slate-800">{p.saas_plan ? `${p.saas_plan.toUpperCase()} · ${CYC[p.saas_cycle] || ""}` : p.descrizione || "Abbonamento CRMEvent"}</div>
              <div className="text-xs text-slate-500">Pagamento {d(p.data)}{p.periodo_inizio ? ` · validità ${d(p.periodo_inizio)} – ${d(p.periodo_fine)}` : ""} · {p.payment_status === "paid" ? "Pagato" : "Non riuscito"}{p.is_test ? " · TEST (nessuna fattura inviata)" : ""}</div></div>
            <div className="flex items-center gap-3 shrink-0"><b>€{eur(p.totale)}</b>
              {p.fic_pdf_url && <a href={p.fic_pdf_url} target="_blank" rel="noreferrer" className="text-xs text-[#0ABAB5] font-semibold" data-testid={`sub-payment-invoice-${p.id}`}>Fattura</a>}
              {p.hosted_invoice_url && <a href={p.hosted_invoice_url} target="_blank" rel="noreferrer" className="text-xs text-[#0ABAB5] font-semibold" data-testid={`sub-payment-receipt-${p.id}`}>Ricevuta</a>}</div>
          </div>
        ))}</div>
      )}
    </div>
  );
}

function RenewDialog({ s, open, onClose, onChange }) {
  if (!open) return null;
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md" data-testid="renew-dialog">
        <DialogHeader><DialogTitle>Rinnovo abbonamento</DialogTitle><DialogDescription>{s.paid_plan_label} · {CYC[s.billing_cycle]}</DialogDescription></DialogHeader>
        <div className="rounded-lg bg-slate-50 border border-slate-200 p-3 text-sm" data-testid="renew-detail">Il rinnovo automatico è attivo: Stripe rinnoverà il piano il <b>{d(s.next_amount?.date || s.current_period_end)}</b> addebitando <b>{eurO(s.next_amount?.gross)}</b> (IVA inclusa). Non serve pagare in anticipo e non perdi nessun giorno già pagato.</div>
        <DialogFooter className="gap-2"><Button variant="outline" onClick={onClose}>Chiudi</Button>
          <Button onClick={onChange} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="renew-change-plan">Cambia durata o piano</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ChangeDialog({ pv, onClose, onConfirm, busy }) {
  if (!pv) return null;
  const up = pv.kind === "upgrade";
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md" data-testid="change-plan-dialog">
        <DialogHeader><DialogTitle>Confermi il cambio piano?</DialogTitle>
          <DialogDescription>{pv.plan.toUpperCase()} {CYC[pv.cycle].toLowerCase()} · €{eur(pv.price)}</DialogDescription></DialogHeader>
        <div className="rounded-lg bg-slate-50 border border-slate-200 p-3 text-sm" data-testid="change-plan-detail">
          {pv.trialing ? "Il cambio è immediato: nessun addebito fino alla fine della prova gratuita."
            : up ? <>Il nuovo piano è attivo subito.{pv.credit > 0 && <> Credito riconosciuto per il periodo già pagato: <b data-testid="change-plan-credit">€{eur(pv.credit)}</b>.</>} Da pagare ora: <b data-testid="change-plan-amount">€{eur(pv.amount_due)}</b>.{pv.new_period_end && <> Nuova scadenza: <b data-testid="change-plan-new-end">{d(pv.new_period_end)}</b>.</>}</>
              : <>Il nuovo piano entrerà in vigore alla scadenza del periodo già pagato ({d(pv.current_period_end)}). I dati dei moduli non inclusi restano conservati.</>}
        </div>
        {pv.over_limits?.length > 0 && <div className="rounded-lg bg-amber-50 border border-amber-200 p-3 text-sm text-amber-900" data-testid="change-plan-over-limits">
          Con il nuovo piano superi i limiti: {pv.over_limits.map((o) => `${o.kind === "events" ? "eventi" : "Staff e Volontari"} ${o.used} su ${o.limit}`).join(", ")}. Nessun dato verrà eliminato, ma non potrai creare nuovi eventi o registrare nuove persone Staff e Volontari finché non rientri nei limiti.
        </div>}
        <DialogFooter className="gap-2"><Button variant="outline" onClick={onClose}>Annulla</Button>
          <Button disabled={busy} onClick={onConfirm} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="change-plan-confirm">{busy ? "Attendi..." : "Conferma"}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

const RANK = ["bronze", "silver", "gold"];
// Piano minimo che contiene l'utilizzo reale (eventi creati + persone Staff/Volontari).
export function recommendPlan(plans, usage) {
  if (!usage) return null;
  const fits = (p) => (p.max_events < 0 || usage.events <= p.max_events) && (p.max_users < 0 || (usage.people ?? 0) <= p.max_users);
  return [...plans].sort((a, b) => RANK.indexOf(a.key) - RANK.indexOf(b.key)).find(fits) || null;
}

function PlanPickerDialog({ open, onClose, s, plans, cycle, setCycle, isCur, choose, busy, requestMode, onRequest, live, title }) {
  const [ack, setAck] = useState(false);
  const rec = recommendPlan(plans.plans, s.usage);
  const curKey = requestMode ? s.paid_plan || s.plan || s.assigned_plan : live ? s.paid_plan : null;
  const needsAck = !requestMode && s.billing === "free";
  // Solo il piano attuale (evidenziato) e i piani superiori.
  const shown = plans.plans.filter((p) => !curKey || RANK.indexOf(p.key) >= RANK.indexOf(curKey));
  const isCurrent = (k) => isCur(k) || k === curKey;
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-5xl max-h-[92vh] overflow-y-auto" data-testid="plan-picker-dialog">
        <DialogHeader><DialogTitle>{title || "Passa a un piano superiore"}</DialogTitle>
          <DialogDescription>{requestMode ? "La tua formula è assegnata dall'amministrazione CRMEvent: invia una richiesta, nessun addebito automatico." : "Prezzi del catalogo attuale. Il nuovo piano si applica solo dopo la tua conferma."} I tuoi dati restano invariati.</DialogDescription></DialogHeader>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          {rec && rec.key !== curKey
            ? <p className="text-sm rounded-lg bg-[#0ABAB5]/10 text-slate-800 px-3 py-2" data-testid="plan-recommendation">Ti consigliamo <b>{rec.label}</b>: è il piano che supporta tutti i tuoi eventi e collaboratori attuali.</p>
            : <p className="text-sm text-slate-500" data-testid="plan-recommendation">{rec ? "Il tuo piano attuale copre già eventi e collaboratori." : ""}</p>}
          <CycleToggle cycle={cycle} setCycle={setCycle} />
        </div>
        {needsAck && <label className="flex items-start gap-2 text-sm rounded-lg bg-amber-50 border border-amber-200 text-amber-900 p-3" data-testid="plan-free-warning">
          <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} className="mt-0.5 accent-[#0ABAB5]" data-testid="plan-free-ack" />
          <span>La tua organizzazione usa una formula gratuita concessa da CRMEvent. Scegliendo un piano passerai a un <b>abbonamento a pagamento</b>: confermo di voler procedere.</span></label>}
        {s.upgrade_request && <p className="text-sm rounded-lg bg-amber-50 border border-amber-200 text-amber-900 px-3 py-2" data-testid="plan-upgrade-pending">Richiesta di upgrade a <b>{s.upgrade_request.plan.toUpperCase()}</b> inviata il {d(s.upgrade_request.at)}: ti contatteremo a breve.</p>}
        <div className="grid gap-4 lg:grid-cols-3">
          {shown.map((p) => (
            <div key={p.key} className="relative">
              {rec?.key === p.key && !isCurrent(p.key) && <span className="absolute -top-2.5 right-3 z-10 rounded-full bg-[#0ABAB5] text-slate-900 text-[11px] font-bold px-2 py-0.5" data-testid={`plan-recommended-${p.key}`}>Consigliato</span>}
              <PlanCard p={p} cycle={cycle} features={plans.features} current={isCurrent(p.key)}
                cta={<Button disabled={busy || isCurrent(p.key) || (needsAck && !ack)} onClick={() => (requestMode ? onRequest(p.key) : choose(p.key))} data-testid={`sub-choose-${p.key}`}
                  className="w-full h-10 bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold">{isCurrent(p.key) ? "Piano attuale" : requestMode ? `Richiedi ${p.label}` : `Passa a ${p.label}`}</Button>} />
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function MySubscription() {
  const { checkAuth } = useAuth();
  const plans = usePlans();
  const [s, setS] = useState(null);
  const [cycle, setCycle] = useState("semester");
  const [pv, setPv] = useState(null);
  const [busy, setBusy] = useState(false);
  const [params, setParams] = useSearchParams();
  const [pickerOpen, setPickerOpen] = useState(params.get("upgrade") === "1");
  const [renewOpen, setRenewOpen] = useState(false);
  const load = useCallback(() => api.get("/saas/me").then(({ data }) => { setS(data); if (data.billing_cycle && data.billing_cycle !== "monthly") setCycle(data.billing_cycle); }).catch(() => {}), []);
  const err = (e) => toast.error(formatApiError(e.response?.data?.detail));

  useEffect(() => {
    const sid = params.get("session_id");
    if (params.get("checkout") === "success" && sid) {
      api.get("/saas/checkout-confirmation", { params: { session_id: sid } }).then(({ data }) => {
        if (data.complete) toast.success("Pagamento confermato. Grazie!");
        else toast.info("Pagamento in elaborazione: l'abbonamento si attiva appena Stripe conferma il pagamento.");
        load(); checkAuth?.();
      }).catch(err).finally(() => setParams({ tab: "abbonamento" }, { replace: true }));
    } else {
      if (params.get("checkout") === "cancel") { toast.warning("Pagamento annullato: nessun addebito effettuato."); setParams({ tab: "abbonamento" }, { replace: true }); }
      load();
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const live = s && s.purchased && ["active", "trialing", "past_due"].includes(s.stripe_status);
  const choose = async (plan) => {
    setBusy(true);
    try {
      if (!live) {
        const { data } = await api.post("/saas/checkout", { plan, cycle, origin_url: window.location.origin });
        window.location.href = data.checkout_url; return;
      }
      const { data } = await api.get("/saas/change-preview", { params: { plan, cycle } }); setPv(data);
    } catch (e) { err(e); } finally { setBusy(false); }
  };
  const confirm = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/saas/change", { plan: pv.plan, cycle: pv.cycle, confirm_amount: pv.amount_due });
      toast.success(data.immediate ? "Piano aggiornato" : "Cambio piano programmato alla prossima scadenza");
      setPv(null); load(); checkAuth?.();
    } catch (e) { err(e); } finally { setBusy(false); }
  };
  const act = async (path, msg) => { try { await api.post(path); toast.success(msg); load(); checkAuth?.(); } catch (e) { err(e); } };
  const portal = async () => { try { const { data } = await api.post("/account/portal", { origin_url: window.location.origin }); window.location.href = data.url; } catch (e) { err(e); } };

  if (!s || !plans) return <p className="text-sm text-slate-400">Caricamento...</p>;
  const closePicker = () => { setPickerOpen(false); if (params.get("upgrade")) { params.delete("upgrade"); setParams(params, { replace: true }); } };
  const isCur = (k) => (live ? s.paid_plan === k && s.billing_cycle === cycle : s.mode !== "trial" && s.plan === k && s.billing === "paid");
  const internal = s.org_type && s.org_type !== "cliente";
  const topPlan = s.mode !== "trial" && (s.paid_plan || s.plan || s.assigned_plan) === "gold";
  const btnCls = "cta-shimmer cta-shimmer-5 h-9 px-4 bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold";
  const everPaid = !!s.paid_plan && s.mode !== "trial";
  const primary = !s.can_manage_billing ? null
    : internal ? (!topPlan && <Button size="sm" onClick={() => setPickerOpen(true)} className={btnCls} data-testid="sub-change-plan"><Settings2 className="w-4 h-4 mr-1.5" />Passa a un piano superiore</Button>)
    : !everPaid ? (!live && <Button size="sm" onClick={() => setPickerOpen(true)} className={btnCls} data-testid="sub-activate"><CreditCard className="w-4 h-4 mr-1.5" />Attiva abbonamento</Button>)
    : <Button size="sm" onClick={() => (!live ? setPickerOpen(true) : s.cancel_at_period_end ? act("/saas/resume", "Rinnovo automatico riattivato: nessun addebito fino alla scadenza") : setRenewOpen(true))} className={btnCls} data-testid="sub-renew"><RefreshCw className="w-4 h-4 mr-1.5" />Rinnova abbonamento</Button>;
  const changeBtn = <div className="flex flex-wrap gap-2">{primary}{!internal && live && !topPlan && s.can_manage_billing && <Button size="sm" variant="outline" onClick={() => setPickerOpen(true)} data-testid="sub-change-plan"><Settings2 className="w-4 h-4 mr-1.5" />Piano superiore</Button>}</div>;
  const request = async (plan) => {
    setBusy(true);
    try { await api.post("/saas/upgrade-request", { plan }); toast.success("Richiesta di upgrade inviata all'amministrazione CRMEvent"); closePicker(); load(); }
    catch (e) { err(e); } finally { setBusy(false); }
  };
  const pickerTitle = internal ? null : !everPaid ? "Attiva abbonamento" : !live ? "Rinnova abbonamento" : "Cambia durata o piano";
  const picker = <PlanPickerDialog open={pickerOpen} onClose={closePicker} s={s} plans={plans} cycle={cycle} setCycle={setCycle} isCur={isCur} requestMode={internal} onRequest={request} live={live} title={pickerTitle} choose={(k) => { closePicker(); choose(k); }} busy={busy} />;
  if (internal) return (
    <div className="space-y-4" data-testid="my-subscription">
      <Summary s={s} features={plans.features} action={changeBtn} />
      <p className="text-sm text-slate-500" data-testid="sub-internal-note">Formula assegnata dall'amministrazione CRMEvent: nessun pagamento richiesto. Puoi richiedere un piano superiore: nessun addebito automatico.</p>
      {picker}
    </div>
  );
  return (
    <div className="space-y-4" data-testid="my-subscription">
      <Summary s={s} features={plans.features} action={changeBtn} />
      <div className="flex flex-wrap gap-2">
        {live && s.can_open_portal && <Button variant="outline" onClick={portal} data-testid="sub-manage"><CreditCard className="w-4 h-4 mr-1.5" />Gestisci abbonamento</Button>}
        {live && s.can_manage_billing && !s.cancel_at_period_end && <Button variant="outline" className="text-red-600" onClick={() => window.confirm("Disattivare il rinnovo automatico? Il piano resta attivo fino alla fine del periodo già pagato.") && act("/saas/cancel", "Rinnovo automatico disattivato")} data-testid="sub-cancel">Disattiva rinnovo automatico</Button>}
        {s.pending_change && s.can_manage_billing && <Button variant="outline" onClick={() => act("/saas/change/cancel-pending", "Cambio programmato annullato")} data-testid="sub-cancel-pending">Annulla cambio programmato</Button>}
      </div>
      {s.can_manage_billing && <Payments rows={s.payments} />}
      {!live && s.trial_active && <p className="text-xs text-slate-500" data-testid="sub-trial-note">Se acquisti ora, il piano pagato parte alla fine della prova ({d(s.trial_end)}): nessun addebito anticipato.</p>}
      {picker}
      <RenewDialog s={s} open={renewOpen} onClose={() => setRenewOpen(false)} onChange={() => { setRenewOpen(false); setPickerOpen(true); }} />
      <ChangeDialog pv={pv} busy={busy} onClose={() => setPv(null)} onConfirm={confirm} />
    </div>
  );
}
