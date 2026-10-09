import { Field, Input, Select } from "@/components/ui";

export const CATEGORIE = [["professionista", "Professionista"], ["influencer", "Influencer"], ["agenzia", "Agenzia"], ["organizzatore", "Organizzatore"], ["societa_sportiva", "Società sportiva"], ["altro", "Altro"]];
export const SOGGETTI = [["privato", "Privato"], ["professionista", "Professionista"], ["azienda", "Azienda"]];

export default function FiscalFields({ form, set, withIban = false }) {
  const ch = (k) => (e) => set(k, e.target.value);
  const a = form.indirizzo || {};
  const setA = (k) => (e) => set("indirizzo", { ...a, [k]: e.target.value });
  const piva = form.soggetto && form.soggetto !== "privato";
  return (
    <div className="space-y-4" data-testid="fiscal-fields">
      <Field label="Tipologia partner">
        <Select value={form.categoria || ""} onChange={ch("categoria")} required data-testid="select-categoria"><option value="">Seleziona</option>{CATEGORIE.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select>
      </Field>
      <Field label="Soggetto fiscale">
        <div className="grid grid-cols-3 gap-2" role="radiogroup">
          {SOGGETTI.map(([k, l]) => (
            <button key={k} type="button" onClick={() => set("soggetto", k)} data-testid={`soggetto-${k}`} aria-pressed={form.soggetto === k}
              className={`h-11 rounded-xl border text-sm font-medium transition-colors ${form.soggetto === k ? "border-tiffany bg-tiffany-light text-tiffany-fg" : "border-slate-200 text-slate-600 hover:bg-slate-50"}`}>{l}</button>
          ))}
        </div>
      </Field>
      <Field label={form.soggetto === "azienda" ? "Ragione sociale" : "Ragione sociale (se presente)"}><Input value={form.ragione_sociale || ""} onChange={ch("ragione_sociale")} required={form.soggetto === "azienda"} data-testid="input-ragione-sociale" /></Field>
      <div className="grid sm:grid-cols-2 gap-4">
        <Field label="Codice fiscale"><Input value={form.codice_fiscale || ""} onChange={ch("codice_fiscale")} data-testid="input-codice-fiscale" /></Field>
        <Field label={piva ? "Partita IVA" : "Partita IVA (se applicabile)"}><Input value={form.partita_iva || ""} onChange={ch("partita_iva")} required={piva} data-testid="input-partita-iva" /></Field>
      </div>
      {piva && <Field label="Il tuo regime fiscale"><Select value={form.regime_fiscale || ""} onChange={ch("regime_fiscale")} data-testid="select-regime-partner"><option value="">Seleziona</option><option value="forfettario">Forfettario</option><option value="ordinario">Ordinario</option><option value="altro">Altro</option></Select></Field>}
      <Field label="Indirizzo fiscale"><Input value={a.via || ""} onChange={setA("via")} placeholder="Via e numero civico" data-testid="input-via" /></Field>
      <div className="grid grid-cols-3 gap-2">
        <Input value={a.cap || ""} onChange={setA("cap")} placeholder="CAP" data-testid="input-cap" />
        <Input value={a.citta || ""} onChange={setA("citta")} placeholder="Città" data-testid="input-citta" />
        <Input value={a.provincia || ""} onChange={setA("provincia")} placeholder="Prov." data-testid="input-provincia" />
      </div>
      <div className="grid sm:grid-cols-2 gap-4">
        <Field label="Sito web"><Input value={form.sito_web || ""} onChange={ch("sito_web")} placeholder="https://" data-testid="input-sito" /></Field>
        <Field label="Canali social"><Input value={form.social || ""} onChange={ch("social")} placeholder="Instagram, LinkedIn, TikTok..." data-testid="input-social" /></Field>
      </div>
      {withIban && <Field label="IBAN per le liquidazioni"><Input value={form.iban || ""} onChange={ch("iban")} placeholder="IT00X0000000000000000000000" data-testid="input-iban" /></Field>}
    </div>
  );
}
