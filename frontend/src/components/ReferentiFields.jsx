import { Plus, Trash2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

export const emptyReferente = () => ({ person_id: null, nome: "", cognome: "", email: "", cellulare: "" });
const FIELDS = [["nome", "Nome"], ["cognome", "Cognome"], ["email", "Email"], ["cellulare", "Cellulare"]];

// Referenti dell'azienda modificabili in linea: solo Nome, Cognome, Email, Cellulare.
export default function ReferentiFields({ refs, setRefs }) {
  const set = (i, k, v) => setRefs((x) => x.map((y, j) => (j === i ? { ...y, [k]: v } : y)));
  const remove = (i) => {
    const r = refs[i];
    if (r.person_id && !window.confirm(`Rimuovere ${[r.nome, r.cognome].filter(Boolean).join(" ") || "questo referente"} dall'azienda? Il contatto resta salvato in CRMEvent.`)) return;
    setRefs((x) => x.filter((_, j) => j !== i));
  };
  return (
    <div className="border-t border-slate-100 pt-3" data-testid="company-referenti">
      <div className="mb-2 text-sm font-semibold text-slate-700">Referente</div>
      <div className="space-y-2">
        {refs.map((r, i) => (
          <div key={r.person_id || `n${i}`} className="relative rounded-lg border border-slate-200 p-2.5 pr-10" data-testid={`company-ref-${i}`}>
            <button type="button" onClick={() => remove(i)} className="absolute right-1.5 top-1.5 rounded-md p-2 text-slate-400 hover:text-red-500" aria-label="Rimuovi referente" data-testid={`company-ref-remove-${i}`}><Trash2 className="h-4 w-4" /></button>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {FIELDS.map(([k, l]) => (
                <Input key={k} placeholder={l} aria-label={l} value={r[k] || ""} onChange={(e) => set(i, k, e.target.value)}
                  type={k === "email" ? "email" : k === "cellulare" ? "tel" : "text"} data-testid={`company-ref-${k}-${i}`} />
              ))}
            </div>
          </div>
        ))}
      </div>
      <Button type="button" size="sm" variant="outline" className="mt-2" onClick={() => setRefs((r) => [...r, emptyReferente()])} data-testid="company-add-referente"><Plus className="mr-1 h-4 w-4" />Aggiungi referente</Button>
    </div>
  );
}
