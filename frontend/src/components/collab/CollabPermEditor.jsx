const LEVELS = [["none", "Nessun accesso"], ["view", "Solo visualizzazione"], ["edit", "Visualizzazione e modifica"]];
const ALL = ["view", "create", "edit", "delete"];
export const levelOf = (acts) => (!acts?.length ? "none" : acts.length > 1 ? "edit" : "view");
const actsOf = (lvl) => (lvl === "none" ? [] : lvl === "view" ? ["view"] : ALL);

export const permBody = (v) => ({ sections: v.sections, flags: v.flags });

export function CollabPermEditor({ sections, flags, value, onChange, cap, testid = "collab-perm" }) {
  const capLvl = (k) => (cap ? levelOf(cap.sections?.[k]) : "edit");
  const allowed = (k, lvl) => LEVELS.findIndex(([l]) => l === lvl) <= LEVELS.findIndex(([l]) => l === capLvl(k));
  const setSec = (k, lvl) => onChange({ ...value, sections: { ...value.sections, [k]: actsOf(lvl) } });
  const setFlag = (k, on) => onChange({ ...value, flags: { ...value.flags, [k]: on } });
  return (
    <div className="space-y-4" data-testid={testid}>
      <div className="rounded-lg border border-slate-200 divide-y divide-slate-100">
        {sections.map((s) => (
          <div key={s.key} className="flex flex-col sm:flex-row sm:items-center justify-between gap-1.5 px-3 py-2">
            <span className="text-sm text-slate-700">{s.label}</span>
            <select className="h-9 px-2 rounded-md border border-slate-200 text-sm bg-white sm:w-56" value={levelOf(value.sections?.[s.key])}
              onChange={(e) => setSec(s.key, e.target.value)} data-testid={`${testid}-sec-${s.key}`}>
              {LEVELS.map(([l, lbl]) => <option key={l} value={l} disabled={!allowed(s.key, l)}>{lbl}</option>)}
            </select>
          </div>
        ))}
      </div>
      <div>
        <div className="text-xs font-semibold uppercase text-slate-500 mb-1.5">Permessi delicati</div>
        <div className="grid sm:grid-cols-2 gap-2">
          {Object.entries(flags).map(([k, lbl]) => (
            <label key={k} className={`flex items-center gap-2 text-sm rounded-lg border border-slate-200 px-3 py-2 ${cap && !cap[k] ? "opacity-50" : ""}`}>
              <input type="checkbox" className="accent-tiffany w-4 h-4" checked={!!value.flags?.[k]} disabled={!!cap && !cap[k]}
                onChange={(e) => setFlag(k, e.target.checked)} data-testid={`${testid}-flag-${k}`} />{lbl}
            </label>
          ))}
        </div>
        <p className="text-xs text-slate-400 mt-1.5">Abbonamento, fatturazione, utenti dell'organizzazione e impostazioni restano sempre esclusi per i Collaboratori.</p>
      </div>
    </div>
  );
}

export const fromPerm = (p, flags) => ({ sections: { ...(p?.sections || {}) }, flags: Object.fromEntries(Object.keys(flags).map((k) => [k, !!(p?.flags?.[k] ?? p?.[k])])) });
