import { useState } from "react";
import { Plus } from "lucide-react";
import { EntityDialog, PrimaryButton, SectionCard, StatusBadge } from "@/components/crm";
import { AsdTable, StatoBadge, SEL, fmtDate, saveItem, deleteItem, useAsd } from "@/components/asd/asdShared";

const TIPO = { certificato: ["Certificato medico", "red"], tesseramento: ["Tesseramento", "blue"], quota: ["Quota", "tiffany"], adempimento: ["Adempimento", "gray"] };
export const TipoBadge = ({ t }) => <StatusBadge color={TIPO[t][1]}>{TIPO[t][0]}</StatusBadge>;

export function DeadlineList({ rows, testid }) {
  if (!rows.length) return <p className="text-sm text-slate-500 py-4" data-testid={`${testid}-empty`}>Nessuna scadenza nel periodo.</p>;
  return (
    <ul className="divide-y divide-slate-100" data-testid={testid}>{rows.map((x) => (
      <li key={`${x.tipo}-${x.ref_id}`} className="py-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm" data-testid={`${testid}-item-${x.ref_id}`}>
        <span className="w-24 shrink-0 font-semibold text-slate-800">{fmtDate(x.data)}</span><TipoBadge t={x.tipo} />
        <span className="text-slate-800 min-w-0">{x.label}{x.socio_nome && <span className="text-slate-500"> · {x.socio_nome}</span>}</span>
        <span className="ml-auto"><StatoBadge s={x.stato} /></span>
      </li>))}</ul>
  );
}

const fields = [
  { name: "titolo", label: "Adempimento", required: true, full: true, placeholder: "es. Rinnovo affiliazione, Assemblea dei soci, Rendiconto annuale" },
  { name: "data_scadenza", label: "Scadenza", type: "date", required: true },
  { name: "completato", label: "Completato", type: "select", keepOrder: true, options: [{ value: "no", label: "No" }, { value: "si", label: "Sì" }] },
  { name: "note", label: "Note", type: "textarea", full: true },
];

export function AsdScadenze({ status, onChanged }) {
  const [giorni, setGiorni] = useState(60);
  const dl = useAsd("/asd/scadenze", { giorni });
  const ad = useAsd("/asd/adempimenti");
  const [edit, setEdit] = useState(null);
  const done = () => { dl.reload(); ad.reload(); onChanged(); };
  const cols = [["titolo", "Adempimento", (r) => <span className="font-medium text-slate-900">{r.titolo}</span>], ["data_scadenza", "Scadenza", (r) => fmtDate(r.data_scadenza)],
    ["completato", "Stato", (r) => (r.completato ? <StatusBadge color="green">Completato</StatusBadge> : <StatusBadge color="orange">Da fare</StatusBadge>)], ["note", "Note"]];
  return (
    <div className="space-y-5">
      <SectionCard title="Scadenze" action={<select className={SEL} value={giorni} onChange={(e) => setGiorni(Number(e.target.value))} data-testid="asd-scadenze-range">{[30, 60, 90, 180, 365].map((g) => <option key={g} value={g}>Scadute e prossimi {g} giorni</option>)}</select>}>
        <p className="text-xs text-slate-500 mb-2">Certificati medici, tesseramenti e quote non pagate con scadenza, più gli adempimenti della società non completati.</p>
        {dl.loading ? <p className="text-sm text-slate-500">Caricamento…</p> : <DeadlineList rows={dl.rows} testid="asd-scadenze-list" />}
      </SectionCard>
      <SectionCard title="Adempimenti della società" action={<PrimaryButton onClick={() => setEdit({ completato: "no" })} data-testid="asd-adempimento-new"><Plus className="w-4 h-4 mr-1" />Nuovo adempimento</PrimaryButton>}>
        <AsdTable cols={cols} rows={ad.rows} loading={ad.loading} testid="asd-adempimenti" onEdit={(r) => setEdit({ ...r, completato: r.completato ? "si" : "no" })} canDelete={status.can_delete}
          onDelete={(r) => deleteItem("/asd/adempimenti", r, `«${r.titolo}»`, done)} empty="Nessun adempimento. Aggiungi ad esempio il rinnovo dell'affiliazione o l'assemblea annuale." />
        {edit && <EntityDialog open onOpenChange={(v) => !v && setEdit(null)} title={edit.id ? "Modifica adempimento" : "Nuovo adempimento"} fields={fields} initial={edit} testid="asd-adempimento"
          onSubmit={async (form) => { await saveItem("/asd/adempimenti", edit, { ...form, completato: form.completato === "si" }); done(); }} />}
      </SectionCard>
    </div>
  );
}
