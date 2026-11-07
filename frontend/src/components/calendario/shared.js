import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";

export const DISC_COLOR = { running: "#0ABAB5", trail: "#16A34A", triathlon: "#6366F1" };
export const DISC_LABEL = { running: "Running", trail: "Trail", triathlon: "Triathlon" };
export const STATO_EVENTO = { confermata: "Confermata", da_verificare: "Da verificare", rinviata: "Rinviata", annullata: "Annullata", conclusa: "Conclusa" };
export const STATO_COMM = { da_qualificare: "Da qualificare", contatto_da_verificare: "Contatto da verificare", pronto_campagna: "Pronto per campagna",
  invio_programmato: "Invio programmato", inviato: "Inviato", contattato: "Contattato", interessato: "Interessato", demo_richiesta: "Demo richiesta",
  cliente_acquisito: "Cliente acquisito", escluso: "Escluso" };
export const PRIVACY = { da_verificare: "Da verificare", idoneo: "Idoneo alla comunicazione", non_idoneo: "Non idoneo", disiscritto: "Disiscritto", opposizione: "Opposizione registrata" };
export const SEL = "h-9 rounded-md border border-slate-200 bg-white px-2 text-sm min-w-0";
export const fmtD = (s) => (s ? new Date(`${s}T00:00:00`).toLocaleDateString("it-IT") : "—");
export const err = (e) => toast.error(formatApiError(e.response?.data?.detail));
export const calApi = (path) => `/platform/cal${path}`;

export async function download(path, params, name) {
  try {
    const res = await api.get(calApi(path), { params, responseType: "blob" });
    const url = URL.createObjectURL(res.data);
    const a = document.createElement("a");
    a.href = url; a.download = name; a.click(); URL.revokeObjectURL(url);
  } catch (e) { err(e); }
}

export const Pill = ({ children, color = "#64748B", testid }) => (
  <span className="inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold whitespace-nowrap" style={{ background: `${color}1A`, color }} data-testid={testid}>{children}</span>
);
