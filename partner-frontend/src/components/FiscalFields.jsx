import { Field, Input, Select } from "@/components/ui";

export const TIPI = [["privato", "Privato"], ["professionista", "Professionista"], ["azienda", "Azienda"]];

export default function FiscalFields({ form, set }) {
  const ch = (k) => (e) => set(k, e.target.value);
  return (
    <div className="space-y-4" data-testid="fiscal-fields">
      <Field label="Sei un">
        <div className="grid grid-cols-3 gap-2" role="radiogroup">
          {TIPI.map(([k, l]) => (
            <button key={k} type="button" onClick={() => set("tipo", k)} data-testid={`tipo-${k}`} aria-pressed={form.tipo === k}
              className={`h-11 rounded-xl border text-sm font-medium transition-colors ${form.tipo === k ? "border-tiffany bg-tiffany-light text-tiffany-fg" : "border-slate-200 text-slate-600 hover:bg-slate-50"}`}>{l}</button>
          ))}
        </div>
      </Field>
      {form.tipo === "azienda" && <Field label="Ragione sociale"><Input value={form.ragione_sociale || ""} onChange={ch("ragione_sociale")} data-testid="input-ragione-sociale" /></Field>}
      <div className="grid sm:grid-cols-2 gap-4">
        <Field label="Codice fiscale"><Input value={form.codice_fiscale || ""} onChange={ch("codice_fiscale")} data-testid="input-codice-fiscale" /></Field>
        {form.tipo !== "privato" && <Field label="Partita IVA"><Input value={form.partita_iva || ""} onChange={ch("partita_iva")} data-testid="input-partita-iva" required /></Field>}
      </div>
      {form.tipo !== "privato" && (
        <Field label="Il tuo regime fiscale">
          <Select value={form.regime_fiscale || ""} onChange={ch("regime_fiscale")} data-testid="select-regime-partner">
            <option value="">Seleziona</option><option value="forfettario">Forfettario</option><option value="ordinario">Ordinario</option><option value="altro">Altro</option>
          </Select>
        </Field>
      )}
    </div>
  );
}
