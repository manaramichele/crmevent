import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Picker, longDay } from "@/components/WelcomeDemo";
import { ShieldCheck, AlertTriangle } from "lucide-react";

// Prenotazione demo per conto di un utente: unico backend per modalità assistenza e Super Admin → Prenotazioni demo.
export function OnBehalfDemo({ orgId, onDone, onCancel }) {
  const [ctx, setCtx] = useState(null);
  const [uid, setUid] = useState("");
  const [f, setF] = useState({ telefono: "", note: "", slot_key: null });
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    setCtx(null);
    api.get("/demo/on-behalf/context", { params: orgId ? { org_id: orgId } : {} })
      .then(({ data }) => { setCtx(data); setUid(data.default_user_id || ""); })
      .catch((e) => toast.error(formatApiError(e.response?.data?.detail)));
  }, [orgId]);
  const m = ctx?.members.find((x) => x.user_id === uid);
  useEffect(() => { setF((s) => ({ ...s, telefono: m?.telefono || "" })); }, [m]);
  if (!ctx) return <p className="text-sm text-slate-500" data-testid="onbehalf-loading">Caricamento...</p>;
  const submit = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/demo/on-behalf", { org_id: orgId, user_id: uid, slot_key: f.slot_key, telefono: f.telefono, note: f.note });
      if (data.demo_meet_status === "errore") toast.warning(`Demo confermata, ma il Meet non è stato creato: ${data.demo_meet_error}`, { duration: 10000 });
      else toast.success("Demo prenotata e confermata: il destinatario riceve l'email con il link Meet");
      onDone?.(data);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
      api.get("/demo/on-behalf/context", { params: orgId ? { org_id: orgId } : {} }).then(({ data }) => setCtx(data)).catch(() => {});
    } finally { setBusy(false); }
  };
  return (
    <div className="space-y-4" data-testid="onbehalf-form">
      <div className="rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-sm text-amber-900 flex items-center gap-2" data-testid="onbehalf-banner">
        <ShieldCheck className="w-4 h-4 shrink-0" />Prenotazione per conto di un utente di <strong>{ctx.org.nome}</strong>: la demo viene confermata subito.
      </div>
      {ctx.members.length === 0 ? <p className="text-sm text-slate-500" data-testid="onbehalf-no-members">Nessun utente attivo in questa organizzazione.</p> : (
        <>
          <div>
            <label className="text-sm font-semibold block mb-1" htmlFor="onbehalf-user">Utente destinatario*</label>
            <select id="onbehalf-user" value={uid} onChange={(e) => setUid(e.target.value)} className="w-full h-10 rounded-md border border-slate-200 px-3 text-sm bg-white" data-testid="onbehalf-user-select">
              {ctx.members.map((x) => <option key={x.user_id} value={x.user_id}>{[x.nome, x.cognome].filter(Boolean).join(" ") || x.email} · {x.email}</option>)}
            </select>
          </div>
          <div className="grid sm:grid-cols-2 gap-3">
            <Input value={m?.nome || ""} disabled aria-label="Nome" data-testid="onbehalf-nome" />
            <Input value={m?.cognome || ""} disabled aria-label="Cognome" data-testid="onbehalf-cognome" />
            <Input value={m?.email || ""} disabled aria-label="Email" data-testid="onbehalf-email" />
            <Input value={f.telefono} onChange={(e) => setF({ ...f, telefono: e.target.value })} placeholder="Telefono (facoltativo)" aria-label="Telefono" data-testid="onbehalf-telefono" />
          </div>
          {m?.active_demo && (
            <p className="text-sm text-amber-800 flex items-center gap-1" data-testid="onbehalf-already"><AlertTriangle className="w-4 h-4" />Ha già una demo il {longDay(m.active_demo.demo_slot.slice(0, 10))} alle {m.active_demo.demo_slot.slice(11)}: riprogrammala da Prenotazioni demo.</p>
          )}
          <div>
            <div className="text-sm font-semibold mb-2">Data e ora*</div>
            <Picker slots={ctx.slots} value={f.slot_key} onPick={(k) => setF({ ...f, slot_key: k })} />
            {f.slot_key && <div className="mt-2 rounded-lg bg-[#0ABAB5]/10 px-3 py-2 text-sm capitalize" data-testid="onbehalf-selected">{longDay(f.slot_key.slice(0, 10))} · ore {f.slot_key.slice(11)}</div>}
          </div>
          <Textarea value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} placeholder="Note interne (facoltative)" rows={2} data-testid="onbehalf-note" />
        </>
      )}
      <div className="flex flex-col-reverse sm:flex-row gap-2 sm:justify-end">
        {onCancel && <Button variant="outline" onClick={onCancel} className="h-11" data-testid="onbehalf-cancel">Annulla</Button>}
        <Button disabled={busy || !uid || !f.slot_key || !!m?.active_demo} onClick={submit} className="h-11 bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="onbehalf-confirm">{busy ? "Prenotazione..." : "Conferma prenotazione"}</Button>
      </div>
    </div>
  );
}
