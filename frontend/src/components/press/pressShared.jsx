import { useCallback, useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";

export const PRESS_STATUS = {
  bozza: ["Bozza", "bg-slate-100 text-slate-700"], da_approvare: ["Da approvare", "bg-amber-100 text-amber-800"],
  programmato: ["Programmato", "bg-sky-100 text-sky-800"], in_invio: ["In invio", "bg-violet-100 text-violet-800"],
  inviato: ["Inviato", "bg-emerald-100 text-emerald-800"], errore: ["Errore", "bg-red-100 text-red-700"],
  annullato: ["Annullato", "bg-slate-200 text-slate-500"], generazione: ["In preparazione", "bg-slate-100 text-slate-600"],
};
export const TIPI = { presentazione: "Presentazione evento", pre_evento: "Pre-evento", post_evento: "Post-evento" };
export const MEDIA = ["Quotidiano", "Quotidiano online", "Rivista", "Radio", "Televisione", "Blog", "Agenzia stampa", "Altro"];
export const BASI = { legittimo_interesse: "Legittimo interesse (rapporti con i media)", consenso: "Consenso espresso", richiesta: "Richiesta del giornalista", altro: "Altra base giuridica documentata" };
export const pErr = (e) => toast.error(formatApiError(e.response?.data?.detail) || "Operazione non riuscita");
export const dt = (s) => (s ? new Date(s).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—");
export const TIFFANY_BTN = "bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold";
export const SEL = "h-10 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-700 min-w-0";

export function StatusPill({ s, testid }) {
  const [l, c] = PRESS_STATUS[s] || PRESS_STATUS.bozza;
  return <span className={`inline-flex items-center h-6 px-2.5 rounded-full text-xs font-semibold whitespace-nowrap ${c}`} data-testid={testid}>{l}</span>;
}

export function useLoad(url, deps = []) {
  const [data, setData] = useState(null);
  const load = useCallback(() => api.get(url).then(({ data: d }) => setData(d)).catch(pErr), [url]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [load, ...deps]); // eslint-disable-line react-hooks/exhaustive-deps
  return [data, load, setData];
}

export function Field({ label, children, hint }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-xs font-medium text-slate-600">{label}</span>
      {children}
      {hint && <span className="block text-[11px] text-slate-400">{hint}</span>}
    </label>
  );
}
