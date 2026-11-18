import { useState } from "react";
import { toast } from "sonner";
import { Plus, Paperclip, FileText } from "lucide-react";
import api from "@/lib/api";
import { EntityDialog, PrimaryButton, SectionCard } from "@/components/crm";
import { AsdTable, StatoBadge, SocioFilter, SEL, apiErr, fmtDate, saveItem, socioField, toOpts, useAsd } from "@/components/asd/asdShared";

const fields = (soci, tipi) => [
  socioField(soci),
  { name: "tipo", label: "Tipo", type: "select", required: true, keepOrder: true, options: toOpts(tipi) },
  { name: "medico", label: "Medico o struttura" },
  { name: "data_rilascio", label: "Data rilascio", type: "date" }, { name: "data_scadenza", label: "Data scadenza", type: "date", required: true },
  { name: "note", label: "Note", type: "textarea", full: true },
];

function FileCell({ r, reload }) {
  const upload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    try { await api.post(`/asd/certificati/${r.id}/file`, fd, { headers: { "Content-Type": "multipart/form-data" } }); toast.success("Certificato allegato"); reload(); } catch (err) { apiErr(err); }
  };
  const open = async () => {
    try { const { data } = await api.get(`/asd/certificati/${r.id}/file`, { responseType: "blob" }); window.open(URL.createObjectURL(data), "_blank", "noopener"); } catch (err) { apiErr(err); }
  };
  return (
    <span className="flex items-center gap-2">
      {r.file_name && <button type="button" onClick={open} className="inline-flex items-center gap-1 text-tiffany-active hover:underline" data-testid={`asd-cert-file-open-${r.id}`}><FileText className="w-3.5 h-3.5" />Apri</button>}
      <label className="inline-flex items-center gap-1 text-slate-500 hover:text-slate-900 cursor-pointer" data-testid={`asd-cert-file-upload-${r.id}`}><Paperclip className="w-3.5 h-3.5" />{r.file_name ? "Sostituisci" : "Allega"}<input type="file" accept="application/pdf,image/*" className="hidden" onChange={upload} data-testid={`asd-cert-file-input-${r.id}`} /></label>
    </span>
  );
}

export function AsdCertificati({ status, soci, onChanged }) {
  const [f, setF] = useState({ socio_id: "", stato: "" });
  const { rows, loading, reload } = useAsd("/asd/certificati", { socio_id: f.socio_id || undefined });
  const [edit, setEdit] = useState(null);
  const done = () => { reload(); onChanged(); };
  const shown = f.stato ? rows.filter((r) => r.stato === f.stato) : rows;
  const cols = [
    ["socio_nome", "Socio", (r) => <span className="font-medium text-slate-900">{r.socio_nome}</span>], ["tipo", "Tipo", (r) => status.options.tipi_cert[r.tipo]],
    ["data_rilascio", "Rilascio", (r) => fmtDate(r.data_rilascio)], ["data_scadenza", "Scadenza", (r) => fmtDate(r.data_scadenza)], ["medico", "Medico/struttura"],
    ["file", "Documento", (r) => <FileCell r={r} reload={reload} />], ["stato", "Stato", (r) => <StatoBadge s={r.stato} testid={`asd-cert-stato-${r.id}`} />],
  ];
  return (
    <SectionCard title={`Certificati Medici (${shown.length})`} action={<PrimaryButton disabled={!soci.length} onClick={() => setEdit({ tipo: "non_agonistico" })} data-testid="asd-cert-new"><Plus className="w-4 h-4 mr-1" />Nuovo certificato</PrimaryButton>}>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mb-4">
        <SocioFilter soci={soci} value={f.socio_id} onChange={(v) => setF({ ...f, socio_id: v })} testid="asd-cert-filter-socio" />
        <select className={SEL} value={f.stato} onChange={(e) => setF({ ...f, stato: e.target.value })} data-testid="asd-cert-filter-stato"><option value="">Tutti gli stati</option><option value="valido">Valido</option><option value="in_scadenza">In scadenza ({status.soon_days} giorni)</option><option value="scaduto">Scaduto</option></select>
      </div>
      <AsdTable cols={cols} rows={shown} loading={loading} testid="asd-cert" onEdit={setEdit} canDelete={status.can_delete}
        onDelete={async (r) => { if (!window.confirm(`Eliminare definitivamente il certificato di ${r.socio_nome}?`)) return; try { await api.delete(`/asd/certificati/${r.id}`); toast.success("Eliminato"); done(); } catch (e) { apiErr(e); } }}
        empty={soci.length ? "Nessun certificato registrato." : "Aggiungi prima un socio in «Soci e Tesserati»."} />
      <p className="text-xs text-slate-500 mt-3">I certificati sono dati sanitari: i file sono visibili solo agli Admin e agli utenti della tua organizzazione e non hanno un link pubblico.</p>
      {edit && <EntityDialog open onOpenChange={(v) => !v && setEdit(null)} title={edit.id ? "Modifica certificato" : "Nuovo certificato"} fields={fields(soci, status.options.tipi_cert)} initial={edit} testid="asd-cert" size="large"
        onSubmit={async (form) => { await saveItem("/asd/certificati", edit, form); done(); }} />}
    </SectionCard>
  );
}
