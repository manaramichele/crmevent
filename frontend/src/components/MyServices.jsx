import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { ServiceIcon, STATUS, priceLabel } from "@/lib/marketplace";

const d = (s) => (s ? new Date(s).toLocaleDateString("it-IT") : "—");

export default function MyServices() {
  const [rows, setRows] = useState(null);
  useEffect(() => { api.get("/marketplace/my").then(({ data }) => setRows(data)).catch(() => setRows([])); }, []);
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 sm:p-6 max-w-3xl" data-testid="my-services">
      <h2 className="font-semibold text-slate-800">Servizi aggiuntivi</h2>
      <p className="text-xs text-slate-500 mt-0.5 mb-4">Servizi extra del Marketplace acquistati dall'organizzazione, separati dall'abbonamento.</p>
      {!rows ? <p className="text-sm text-slate-400">Caricamento...</p> : !rows.length ? (
        <p className="text-sm text-slate-500" data-testid="my-services-empty">Nessun servizio aggiuntivo attivo. <Link to="/marketplace" className="text-[#088F8A] font-semibold">Scopri il Marketplace</Link></p>
      ) : (
        <div className="divide-y divide-slate-100">{rows.map((p) => (
          <div key={p.id} className="py-3 flex items-center gap-3 text-sm" data-testid={`my-service-${p.id}`}>
            <ServiceIcon s={{ icon: "Package" }} className="w-9 h-9" />
            <div className="flex-1 min-w-0"><div className="font-semibold">{p.service_name}{p.event_name ? ` · ${p.event_name}` : ""}</div>
              <div className="text-xs text-slate-500">{STATUS[p.status]} · {priceLabel(p)} · acquistato il {d(p.activated_at || p.created_at)}{p.current_period_end ? ` · rinnovo ${d(p.current_period_end)}` : ""}</div></div>
            <Link to="/marketplace" className="text-xs font-semibold text-[#088F8A]">Gestisci</Link>
          </div>
        ))}</div>
      )}
    </div>
  );
}
