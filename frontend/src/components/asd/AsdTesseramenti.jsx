import { useState } from "react";
import { Plus } from "lucide-react";
import { Input } from "@/components/ui/input";
import { EntityDialog, PrimaryButton, SectionCard } from "@/components/crm";
import { AsdTable, StatoBadge, SocioFilter, fmtDate, saveItem, deleteItem, socioField, useAsd } from "@/components/asd/asdShared";
import { EnteSelect } from "@/components/asd/AsdEnti";

const fields = (soci) => [
  socioField(soci),
  { name: "stagione", label: "Stagione", required: true, placeholder: "es. 2026/2027" }, { name: "ente_id", label: "Ente o federazione", required: true, type: "custom", render: (v, set) => <EnteSelect value={v} onChange={set} /> },
  { name: "numero_tessera", label: "Numero tessera" }, { name: "categoria", label: "Categoria" },
  { name: "data_emissione", label: "Data emissione", type: "date" }, { name: "data_scadenza", label: "Data scadenza", type: "date" },
  { name: "annullato", label: "Tesseramento annullato", type: "select", keepOrder: true, options: [{ value: "no", label: "No" }, { value: "si", label: "Sì" }] },
  { name: "note", label: "Note", type: "textarea", full: true },
];

export function AsdTesseramenti({ status, soci, onChanged }) {
  const [f, setF] = useState({ socio_id: "", stagione: "" });
  const { rows, loading, reload } = useAsd("/asd/tesseramenti", { socio_id: f.socio_id || undefined, stagione: f.stagione || undefined });
  const [edit, setEdit] = useState(null);
  const done = () => { reload(); onChanged(); };
  const cols = [
    ["socio_nome", "Socio", (r) => <span className="font-medium text-slate-900">{r.socio_nome}</span>], ["stagione", "Stagione"], ["ente_nome", "Ente", (r) => <span className={r.ente_attivo ? "" : "text-slate-500"} data-testid={`asd-tess-ente-${r.id}`}>{r.ente_nome}{r.ente_attivo ? "" : " (disattivato)"}</span>],
    ["numero_tessera", "N. tessera"], ["categoria", "Categoria"], ["data_scadenza", "Scadenza", (r) => fmtDate(r.data_scadenza)],
    ["stato", "Stato", (r) => <StatoBadge s={r.stato} testid={`asd-tess-stato-${r.id}`} />],
  ];
  return (
    <SectionCard title={`Tesseramenti (${rows.length})`} action={<PrimaryButton disabled={!soci.length} onClick={() => setEdit({ annullato: "no" })} data-testid="asd-tess-new"><Plus className="w-4 h-4 mr-1" />Nuovo tesseramento</PrimaryButton>}>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mb-4">
        <SocioFilter soci={soci} value={f.socio_id} onChange={(v) => setF({ ...f, socio_id: v })} testid="asd-tess-filter-socio" />
        <Input placeholder="Filtra per stagione (es. 2026/2027)" value={f.stagione} onChange={(e) => setF({ ...f, stagione: e.target.value })} data-testid="asd-tess-filter-stagione" />
      </div>
      <AsdTable cols={cols} rows={rows} loading={loading} testid="asd-tess" onEdit={(r) => setEdit({ ...r, annullato: r.annullato ? "si" : "no" })} canDelete={status.can_delete}
        onDelete={(r) => deleteItem("/asd/tesseramenti", r, `il tesseramento ${r.ente_nome} ${r.stagione} di ${r.socio_nome}`, done)}
        empty={soci.length ? "Nessun tesseramento registrato." : "Aggiungi prima un socio in «Soci e Tesserati»."} />
      {edit && <EntityDialog open onOpenChange={(v) => !v && setEdit(null)} title={edit.id ? "Modifica tesseramento" : "Nuovo tesseramento"} fields={fields(soci)} initial={edit} testid="asd-tess" size="large"
        onSubmit={async (form) => { const { ente, ente_nome, ente_attivo, ...rest } = form; await saveItem("/asd/tesseramenti", edit, { ...rest, annullato: form.annullato === "si" }); done(); }} />}
    </SectionCard>
  );
}
