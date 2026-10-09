export const eur = (c) => ((c || 0) / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
export const dt = (s) => (s ? new Date(s).toLocaleDateString("it-IT") : "—");
export const P_ST = { pending: ["orange", "In attesa"], approved: ["green", "Approvato"], rejected: ["red", "Rifiutato"], suspended: ["gray", "Sospeso"] };
export const C_ST = { maturata: ["blue", "Maturata"], liquidabile: ["tiffany", "Liquidabile"], in_liquidazione: ["orange", "In liquidazione"], pagata: ["green", "Pagata"], stornata: ["gray", "Stornata"] };
export const CAT = { professionista: "Professionista", influencer: "Influencer", agenzia: "Agenzia", organizzatore: "Organizzatore", societa_sportiva: "Società sportiva", altro: "Altro" };
export const SOG = { privato: "Privato", professionista: "Professionista", azienda: "Azienda" };
export const KIND = { prima_sottoscrizione: "Prima sottoscrizione", rinnovo: "Rinnovo", upgrade: "Upgrade", altro: "Altro" };
export const pname = (p) => `${p?.nome || ""} ${p?.cognome || ""}`.trim() || p?.email;
export const Card = ({ title, children, testid, right }) => (
  <div className="bg-white border border-slate-200 rounded-xl overflow-hidden" data-testid={testid}>
    {title && <div className="flex items-center justify-between gap-2 font-semibold text-slate-900 px-4 py-3 border-b border-slate-100">{title}{right}</div>}
    {children}
  </div>
);
