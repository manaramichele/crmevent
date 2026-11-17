import { Link } from "react-router-dom";
import { Map as MapIcon, Film, RadioTower, CheckCircle2, CircleOff, Lock } from "lucide-react";
import { SOURCE_LABEL } from "@/components/addons/addonInfo";

export const MODULE_ICON = { planner: MapIcon, eventmap: Film, controlroom: RadioTower };
const d = (s) => (s ? new Date(s).toLocaleDateString("it-IT") : "—");

function limitRows(m) {
  const l = m.limits || {};
  if (m.key === "controlroom") return [["Eventi attivi", l.events_active], ["Acquistati", l.purchased], ["Concessi gratuitamente", l.granted]];
  const rows = [["Eventi inclusi nel piano", `${l.included_used ?? 0}/${l.included ?? 0} usati`], ["Eventi acquistati", l.purchased], ["Eventi concessi", l.granted], ["Attivazioni disponibili", l.available]];
  if (m.key === "eventmap") rows.push(["Crediti video", `${l.videos_used ?? 0}/${l.videos_total ?? 0} usati · ${l.videos_available ?? 0} disponibili`]);
  if (m.key === "planner") rows.push(["Planimetrie salvate", l.planimetrie]);
  return rows;
}

function Info({ label, value, testid }) {
  return <div><div className="text-[11px] uppercase tracking-wider text-slate-400 font-medium">{label}</div><div className="text-sm text-slate-800" data-testid={testid}>{value ?? "—"}</div></div>;
}

export function ModuleCard({ m, children, showOpen = false }) {
  const Icon = MODULE_ICON[m.key] || MapIcon;
  const incl = m.key === "controlroom" ? "Non incluso negli abbonamenti · 119 € + IVA per evento" : m.plan_includes?.length ? m.plan_includes.map((p) => `${p.plan} (${p.events} ${p.events === 1 ? "evento" : "eventi"})`).join(" · ") : "Nessun piano lo include";
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 sm:p-5 space-y-4" data-testid={`module-card-${m.key}`}>
      <div className="flex items-start gap-3">
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${m.active ? "bg-tiffany-light text-tiffany-fg" : "bg-slate-100 text-slate-400"}`}><Icon className="w-5 h-5" /></div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-semibold text-slate-900">{m.name}</h3>
            {m.active
              ? <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-700 bg-emerald-50 rounded-full px-2 py-0.5" data-testid={`module-status-${m.key}`}><CheckCircle2 className="w-3.5 h-3.5" />Attivo</span>
              : <span className="inline-flex items-center gap-1 text-xs font-semibold text-slate-500 bg-slate-100 rounded-full px-2 py-0.5" data-testid={`module-status-${m.key}`}>{m.disabled ? <CircleOff className="w-3.5 h-3.5" /> : <Lock className="w-3.5 h-3.5" />}{m.disabled ? "Disattivato dal Super Admin" : "Non attivo"}</span>}
          </div>
          <p className="text-sm text-slate-500 mt-0.5">{m.description}</p>
        </div>
        {showOpen && m.active && <Link to={m.route} className="text-sm font-semibold text-tiffany-active shrink-0" data-testid={`module-open-${m.key}`}>Apri</Link>}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <Info label="Modalità di attivazione" value={m.mode_labels?.length ? m.mode_labels.join(" · ") : "Nessuna"} testid={`module-modes-${m.key}`} />
        <Info label="Incluso negli abbonamenti" value={incl} testid={`module-plans-${m.key}`} />
        <Info label="Data di attivazione" value={d(m.activated_at)} />
        <Info label="Scadenza" value={m.expires_at ? d(m.expires_at) : m.key === "controlroom" ? "Per singolo evento" : "Nessuna"} />
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-2" data-testid={`module-limits-${m.key}`}>
        {limitRows(m).map(([l, v]) => <div key={l} className="rounded-lg bg-slate-50 px-3 py-2"><div className="text-[11px] text-slate-500">{l}</div><div className="text-sm font-semibold text-slate-800">{v ?? 0}</div></div>)}
      </div>
      {m.events?.length > 0 && (
        <div data-testid={`module-events-${m.key}`}>
          <div className="text-[11px] uppercase tracking-wider text-slate-400 font-medium mb-1.5">Eventi associati</div>
          <div className="flex flex-wrap gap-1.5">{m.events.map((e) => <span key={e.id} className="text-xs rounded-full border border-slate-200 px-2.5 py-1 text-slate-700">{e.nome} · {e.source === "superadmin" ? "Concesso" : SOURCE_LABEL[e.source] || "Attivo"}</span>)}</div>
        </div>
      )}
      {children}
    </div>
  );
}
