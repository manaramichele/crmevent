import { useState } from "react";
import { Plus, CheckCircle2 } from "lucide-react";
import { EntityDialog, PrimaryButton, SectionCard } from "@/components/crm";
import { AsdTable, StatoBadge, SocioFilter, SEL, fmtDate, fmtEur, saveItem, deleteItem, socioField, toOpts, today, useAsd } from "@/components/asd/asdShared";

const fields = (soci, metodi) => [
  socioField(soci),
  { name: "descrizione", label: "Descrizione", required: true, full: true, placeholder: "es. Quota associativa 2026" },
  { name: "stagione", label: "Stagione", placeholder: "es. 2026/2027" }, { name: "importo", label: "Importo €", type: "number", required: true },
  { name: "data_scadenza", label: "Scadenza pagamento", type: "date" }, { name: "data_pagamento", label: "Data pagamento (vuota = non pagata)", type: "date" },
  { name: "importo_pagato", label: "Importo pagato €", type: "number" }, { name: "metodo", label: "Metodo di pagamento", type: "select", keepOrder: true, options: toOpts(metodi) },
  { name: "note", label: "Note", type: "textarea", full: true },
];

export function AsdQuote({ status, soci, onChanged }) {
  const [f, setF] = useState({ socio_id: "", stato: "" });
  const { rows, loading, reload } = useAsd("/asd/quote", { socio_id: f.socio_id || undefined });
  const [edit, setEdit] = useState(null);
  const done = () => { reload(); onChanged(); };
  const shown = f.stato ? rows.filter((r) => r.stato === f.stato) : rows;
  const tot = (k) => fmtEur(shown.reduce((s, r) => s + (k === "pagato" ? (r.data_pagamento ? r.importo_pagato || 0 : 0) : (r.data_pagamento ? 0 : r.importo || 0)), 0));
  const cols = [
    ["socio_nome", "Socio", (r) => <span className="font-medium text-slate-900">{r.socio_nome}</span>], ["descrizione", "Descrizione"],
    ["importo", "Importo", (r) => fmtEur(r.importo)], ["data_scadenza", "Scadenza", (r) => fmtDate(r.data_scadenza)],
    ["data_pagamento", "Pagamento", (r) => (r.data_pagamento ? `${fmtDate(r.data_pagamento)} · ${fmtEur(r.importo_pagato)}${r.metodo ? ` · ${status.options.metodi[r.metodo]}` : ""}` : "—")],
    ["stato", "Stato", (r) => <StatoBadge s={r.stato} testid={`asd-quota-stato-${r.id}`} />],
  ];
  const pay = (r) => !r.data_pagamento && <button type="button" onClick={() => setEdit({ ...r, data_pagamento: today(), importo_pagato: r.importo })} className="p-1.5 text-emerald-600 hover:text-emerald-800" title="Registra pagamento" data-testid={`asd-quota-pay-${r.id}`}><CheckCircle2 className="w-4 h-4" /></button>;
  return (
    <SectionCard title={`Quote e Pagamenti (${shown.length})`} action={<PrimaryButton disabled={!soci.length} onClick={() => setEdit({})} data-testid="asd-quota-new"><Plus className="w-4 h-4 mr-1" />Nuova quota</PrimaryButton>}>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mb-3">
        <SocioFilter soci={soci} value={f.socio_id} onChange={(v) => setF({ ...f, socio_id: v })} testid="asd-quote-filter-socio" />
        <select className={SEL} value={f.stato} onChange={(e) => setF({ ...f, stato: e.target.value })} data-testid="asd-quote-filter-stato"><option value="">Tutti gli stati</option><option value="da_pagare">Da pagare</option><option value="scaduta">Scaduta</option><option value="parziale">Pagata in parte</option><option value="pagata">Pagata</option></select>
      </div>
      <div className="flex flex-wrap gap-4 text-sm mb-3" data-testid="asd-quote-totals"><span>Incassato: <b>{tot("pagato")}</b></span><span>Da incassare: <b>{tot("aperto")}</b></span></div>
      <AsdTable cols={cols} rows={shown} loading={loading} testid="asd-quote" onEdit={setEdit} canDelete={status.can_delete} extra={pay}
        onDelete={(r) => deleteItem("/asd/quote", r, `la quota «${r.descrizione}» di ${r.socio_nome}`, done)}
        empty={soci.length ? "Nessuna quota registrata." : "Aggiungi prima un socio in «Soci e Tesserati»."} />
      <p className="text-xs text-slate-500 mt-3">Registro interno dei pagamenti: CRMEvent non incassa queste quote e non emette ricevute fiscali.</p>
      {edit && <EntityDialog open onOpenChange={(v) => !v && setEdit(null)} title={edit.id ? "Modifica quota" : "Nuova quota"} fields={fields(soci, status.options.metodi)} initial={edit} testid="asd-quota" size="large"
        onSubmit={async (form) => { await saveItem("/asd/quote", edit, form); done(); }} />}
    </SectionCard>
  );
}
