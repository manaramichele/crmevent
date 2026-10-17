import { useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { toast } from "sonner";
import { AlertTriangle } from "lucide-react";

const DOCS = { privacy: "Privacy Policy", cookie: "Cookie Policy", banner: "Banner cookie" };
const dt = (s) => (s ? new Date(s).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" }) : "—");

export function VersionsPanel({ s, onPublished }) {
  const [doc, setDoc] = useState("cookie");
  const [note, setNote] = useState("");
  const [legal, setLegal] = useState(false);
  const [busy, setBusy] = useState(false);
  const publish = async () => {
    if (!window.confirm(`Pubblicare una nuova versione di "${DOCS[doc]}"? Il banner verrà riproposto a tutti i visitatori.`)) return;
    setBusy(true);
    try {
      const { data } = await api.post("/platform/privacy/publish", { doc, note, legal_review: legal });
      toast.success(`${DOCS[doc]} pubblicata: versione ${data.version}`);
      setNote(""); setLegal(false); onPublished();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    setBusy(false);
  };
  const history = [...(s.history || [])].reverse();
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 sm:p-6 space-y-5" data-testid="privacy-versions">
      <div className="grid sm:grid-cols-3 gap-2">
        {Object.entries(DOCS).map(([k, v]) => (
          <div key={k} className="rounded-lg bg-slate-50 border border-slate-200 p-3" data-testid={`privacy-version-${k}`}>
            <div className="text-xs text-slate-500">{v}</div><div className="font-mono font-semibold text-slate-900">{s.versions[k]}</div>
          </div>
        ))}
      </div>
      <div className="space-y-2 border-t border-slate-100 pt-4">
        <div className="font-semibold text-slate-800">Pubblica nuova versione</div>
        <p className="text-sm text-slate-600">I testi di Privacy Policy e Cookie Policy sono aggiornati nel codice dell'app; pubblica qui la nuova versione dopo il rilascio. Ogni pubblicazione invalida i consensi precedenti e ripropone il banner.</p>
        <div className="flex flex-wrap gap-2">
          {Object.entries(DOCS).map(([k, v]) => <Button key={k} size="sm" variant={doc === k ? "default" : "outline"} onClick={() => setDoc(k)} data-testid={`privacy-publish-doc-${k}`}>{v}</Button>)}
        </div>
        <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Nota sulle modifiche (obbligatoria)" data-testid="privacy-publish-note" />
        <label className="flex items-center gap-2 text-sm text-slate-700"><Checkbox checked={legal} onCheckedChange={(v) => setLegal(!!v)} data-testid="privacy-publish-legal" />Testo verificato da revisione legale</label>
        {!legal && <p className="text-xs text-amber-700 flex items-center gap-1"><AlertTriangle className="w-3 h-3" />Senza revisione legale la versione resta segnalata come "da revisionare".</p>}
        <Button onClick={publish} disabled={busy || note.trim().length < 3} data-testid="privacy-publish-submit">Pubblica versione</Button>
      </div>
      <div className="border-t border-slate-100 pt-4">
        <div className="font-semibold text-slate-800 mb-2">Storico pubblicazioni</div>
        {history.length === 0 ? <p className="text-sm text-slate-400">Nessuna pubblicazione dopo la versione iniziale.</p> : (
          <ul className="space-y-2 text-sm" data-testid="privacy-history">
            {history.map((h, i) => (
              <li key={i} className="border border-slate-200 rounded-lg p-2">
                <span className="font-semibold">{DOCS[h.doc]} {h.version}</span> <span className="text-slate-500">· {dt(h.published_at)} · {h.by}</span>
                <span className={`ml-2 text-xs px-2 py-0.5 rounded-full ${h.legal_review ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-800"}`}>{h.legal_review ? "Revisione legale" : "Da revisionare"}</span>
                <div className="text-slate-600">{h.note}</div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
