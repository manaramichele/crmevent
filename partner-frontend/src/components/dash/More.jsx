import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Copy, Download, ExternalLink } from "lucide-react";
import api, { API, formatApiError } from "@/lib/api";
import { useAuth } from "@/context/Auth";
import { Button, Field, Input } from "@/components/ui";
import FiscalFields from "@/components/FiscalFields";

const CATS = { generale: "Generale", instagram: "Instagram", facebook: "Facebook", linkedin: "LinkedIn", whatsapp: "WhatsApp", email: "Email" };
export const fillLink = (t, link) => (t || "").split("[LINK PERSONALE DEL PARTNER]").join(link || "");

async function copyText(t) {
  try { await navigator.clipboard.writeText(t); }
  catch { const a = document.createElement("textarea"); a.value = t; document.body.appendChild(a); a.select(); document.execCommand("copy"); a.remove(); }
  toast.success("Testo copiato con il tuo link personale");
}

export function Materials() {
  const { partner } = useAuth();
  const [rows, setRows] = useState(null);
  const [cat, setCat] = useState("");
  useEffect(() => { api.get("/partner/materials").then(({ data }) => setRows(data)).catch(() => setRows([])); }, []);
  if (!rows) return <p className="text-slate-400">Caricamento...</p>;
  if (!rows.length) return <p className="text-sm text-slate-500" data-testid="materials-empty">I materiali promozionali saranno disponibili a breve.</p>;
  const cats = [...new Set(rows.map((m) => m.category || "generale"))];
  const shown = rows.filter((m) => !cat || (m.category || "generale") === cat);
  const chip = (k, l) => <button key={k || "all"} type="button" onClick={() => setCat(k)} data-testid={`materials-filter-${k || "all"}`} className={`h-8 px-3 rounded-full text-sm border transition-colors ${cat === k ? "bg-tiffany border-tiffany text-ink" : "border-slate-200 text-slate-600 hover:border-tiffany"}`}>{l}</button>;
  return (
    <div className="space-y-4">
    {cats.length > 1 && <div className="flex flex-wrap gap-2" data-testid="materials-filters">{chip("", "Tutti")}{cats.map((k) => chip(k, CATS[k] || k))}</div>}
    <div className="grid sm:grid-cols-2 gap-4" data-testid="materials">
      {shown.map((m) => (
        <div key={m.id} className={`rounded-3xl border border-slate-200 bg-white p-5 min-w-0 ${m.kind === "text" ? "sm:col-span-2" : ""}`} data-testid={`material-${m.id}`}>
          <div className="text-xs font-semibold uppercase tracking-wide text-tiffany-fg">{CATS[m.category] || "Generale"}{m.kind === "text" && " · Testo promozionale"}</div>
          <h3 className="font-bold mt-1">{m.title}</h3>{m.description && <p className="mt-1 text-sm text-slate-600">{m.description}</p>}
          {m.kind === "text" && <div className="mt-3 rounded-2xl bg-slate-50 border border-slate-100 p-4 text-sm leading-relaxed whitespace-pre-wrap break-words max-h-96 overflow-auto" data-testid={`material-text-${m.id}`}>{fillLink(m.text, partner?.referral_link)}</div>}
          <div className="mt-4 flex gap-2 flex-wrap">
            {m.kind === "text" && <Button onClick={() => copyText(fillLink(m.text, partner?.referral_link))} className="h-10" data-testid={`material-copy-${m.id}`}><Copy className="w-4 h-4" />Copia testo</Button>}
            {m.has_file && <a href={`${API}/partner/materials/${m.id}/file`} data-testid={`material-download-${m.id}`}><Button variant="outline" className="h-10"><Download className="w-4 h-4" />Scarica</Button></a>}
            {m.url && <a href={m.url} target="_blank" rel="noopener noreferrer" data-testid={`material-open-${m.id}`}><Button variant="outline" className="h-10"><ExternalLink className="w-4 h-4" />Apri</Button></a>}
          </div>
        </div>))}
    </div>
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
