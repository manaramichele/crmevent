import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Download, ExternalLink } from "lucide-react";
import api, { API, formatApiError } from "@/lib/api";
import { useAuth } from "@/context/Auth";
import { Button, Field, Input } from "@/components/ui";
import FiscalFields from "@/components/FiscalFields";

export function Materials() {
  const [rows, setRows] = useState(null);
  useEffect(() => { api.get("/partner/materials").then(({ data }) => setRows(data)).catch(() => setRows([])); }, []);
  if (!rows) return <p className="text-slate-400">Caricamento...</p>;
  if (!rows.length) return <p className="text-sm text-slate-500" data-testid="materials-empty">I materiali promozionali saranno disponibili a breve.</p>;
  return (
    <div className="grid sm:grid-cols-2 gap-4" data-testid="materials">
      {rows.map((m) => (
        <div key={m.id} className="rounded-3xl border border-slate-200 bg-white p-5" data-testid={`material-${m.id}`}>
          <h3 className="font-bold">{m.title}</h3>{m.description && <p className="mt-1 text-sm text-slate-600">{m.description}</p>}
          <div className="mt-4 flex gap-2 flex-wrap">
            {m.has_file && <a href={`${API}/partner/materials/${m.id}/file`} data-testid={`material-download-${m.id}`}><Button variant="outline" className="h-10"><Download className="w-4 h-4" />Scarica</Button></a>}
            {m.url && <a href={m.url} target="_blank" rel="noopener noreferrer" data-testid={`material-open-${m.id}`}><Button variant="outline" className="h-10"><ExternalLink className="w-4 h-4" />Apri</Button></a>}
          </div>
        </div>))}
    </div>
  );
}

export function Profile() {
  const { partner, setPartner } = useAuth();
  const [f, setF] = useState(() => ({ ...partner }));
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const save = async (e) => {
    e.preventDefault(); setBusy(true);
    const { nome, cognome, telefono, categoria, soggetto, ragione_sociale, codice_fiscale, partita_iva, regime_fiscale, indirizzo, sito_web, social, iban } = f;
    try { const { data } = await api.patch("/partner/profile", { nome, cognome, telefono, categoria, soggetto, ragione_sociale, codice_fiscale, partita_iva, regime_fiscale, indirizzo, sito_web, social, iban: iban || undefined }); setPartner(data); toast.success("Profilo aggiornato"); }
    catch (err) { toast.error(formatApiError(err.response?.data?.detail)); } finally { setBusy(false); }
  };
  return (
    <form onSubmit={save} className="rounded-3xl border border-slate-200 bg-white p-5 sm:p-6 space-y-4 max-w-2xl" data-testid="profile-form">
      <div className="grid grid-cols-2 gap-3">
        <Field label="Nome"><Input value={f.nome || ""} onChange={(e) => set("nome", e.target.value)} required data-testid="pf-nome" /></Field>
        <Field label="Cognome"><Input value={f.cognome || ""} onChange={(e) => set("cognome", e.target.value)} required data-testid="pf-cognome" /></Field>
      </div>
      <Field label="Email"><Input value={partner.email} disabled /></Field>
      <Field label="Cellulare"><Input value={f.telefono || ""} onChange={(e) => set("telefono", e.target.value)} required data-testid="pf-telefono" /></Field>
      <FiscalFields form={f} set={set} withIban />
      <Button type="submit" disabled={busy} data-testid="profile-save">{busy ? "Salvataggio..." : "Salva profilo"}</Button>
    </form>
  );
}
