import { useState } from "react";
import { Plus } from "lucide-react";
import { Input } from "@/components/ui/input";
import { EntityDialog, PrimaryButton, SectionCard } from "@/components/crm";
import { AsdTable, StatoBadge, SEL, fmtDate, saveItem, deleteItem, toOpts, useAsd } from "@/components/asd/asdShared";

const fields = (o) => [
  { name: "cognome", label: "Cognome", required: true }, { name: "nome", label: "Nome", required: true },
  { name: "codice_fiscale", label: "Codice fiscale" }, { name: "data_nascita", label: "Data di nascita", type: "date" },
  { name: "luogo_nascita", label: "Luogo di nascita" }, { name: "sesso", label: "Sesso", type: "select", options: [{ value: "M", label: "M" }, { value: "F", label: "F" }] },
  { name: "email", label: "Email", type: "email" }, { name: "cellulare", label: "Cellulare" },
  { name: "indirizzo", label: "Indirizzo", full: true },
  { name: "tipo", label: "Tipo", type: "select", required: true, keepOrder: true, options: toOpts(o.tipi_socio) },
  { name: "qualifica", label: "Qualifica", type: "select", keepOrder: true, options: toOpts(o.qualifiche) },
  { name: "numero_socio", label: "Numero socio" }, { name: "data_iscrizione", label: "Data iscrizione", type: "date" },
  { name: "stato", label: "Stato", type: "select", required: true, keepOrder: true, options: toOpts(o.stati_socio) },
  { name: "note", label: "Note", type: "textarea", full: true },
];

export function AsdSoci({ status, onChanged }) {
  const [f, setF] = useState({ q: "", stato: "", tipo: "" });
  const { rows, loading, reload } = useAsd("/asd/soci", f);
  const [edit, setEdit] = useState(null);
  const o = status.options;
  const cols = [
    ["cognome", "Cognome e nome", (r) => <span className="font-medium text-slate-900">{r.cognome} {r.nome}</span>],
    ["tipo", "Tipo", (r) => o.tipi_socio[r.tipo]], ["qualifica", "Qualifica", (r) => o.qualifiche[r.qualifica] || "—"],
    ["codice_fiscale", "Codice fiscale"], ["cellulare", "Cellulare"],
    ["certificato_stato", "Certificato", (r) => <span className="flex flex-col gap-0.5"><StatoBadge s={r.certificato_stato} testid={`asd-socio-cert-${r.id}`} />{r.certificato_scadenza && <span className="text-xs text-slate-500">{fmtDate(r.certificato_scadenza)}</span>}</span>],
    ["quote_da_pagare", "Quote aperte", (r) => r.quote_da_pagare || "—"],
    ["stato", "Stato", (r) => <StatoBadge s={r.stato} />],
  ];
  const done = () => { reload(); onChanged(); };
  return (
    <SectionCard title={`Soci e Tesserati (${rows.length})`} action={<PrimaryButton onClick={() => setEdit({ tipo: "socio", stato: "attivo" })} data-testid="asd-socio-new"><Plus className="w-4 h-4 mr-1" />Nuovo socio</PrimaryButton>}>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mb-4">
        <Input placeholder="Cerca nome, codice fiscale, email, n. socio" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} data-testid="asd-soci-search" />
        <select className={SEL} value={f.tipo} onChange={(e) => setF({ ...f, tipo: e.target.value })} data-testid="asd-soci-filter-tipo"><option value="">Tutti i tipi</option>{Object.entries(o.tipi_socio).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
        <select className={SEL} value={f.stato} onChange={(e) => setF({ ...f, stato: e.target.value })} data-testid="asd-soci-filter-stato"><option value="">Tutti gli stati</option>{Object.entries(o.stati_socio).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
      </div>
      <AsdTable cols={cols} rows={rows} loading={loading} testid="asd-soci" onEdit={setEdit} canDelete={status.can_delete}
        onDelete={(r) => deleteItem("/asd/soci", r, `${r.cognome} ${r.nome}`, done)} empty="Nessun socio registrato. Aggiungi il primo con «Nuovo socio»." />
      {edit && <EntityDialog open onOpenChange={(v) => !v && setEdit(null)} title={edit.id ? "Modifica socio" : "Nuovo socio"} fields={fields(o)} initial={edit} testid="asd-socio" size="large"
        onSubmit={async (form) => { await saveItem("/asd/soci", edit, form); done(); }} />}
    </SectionCard>
  );
}
