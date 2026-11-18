import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Plus, UserPlus, Users } from "lucide-react";
import api from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { EntityDialog, PrimaryButton, SectionCard } from "@/components/crm";
import { AsdTable, StatoBadge, SEL, fmtDate, saveItem, deleteItem, toOpts, useAsd, apiErr } from "@/components/asd/asdShared";
import { AsdPeopleResults, sharedOf } from "@/components/asd/AsdPeople";
import { AsdSocioStaff } from "@/components/asd/AsdSocioStaff";

const fields = (o) => [
  { name: "cognome", label: "Cognome", required: true }, { name: "nome", label: "Nome", required: true },
  { name: "codice_fiscale", label: "Codice fiscale" }, { name: "data_nascita", label: "Data di nascita", type: "date" },
  { name: "luogo_nascita", label: "Luogo di nascita" }, { name: "sesso", label: "Sesso", type: "select", options: [{ value: "M", label: "M" }, { value: "F", label: "F" }] },
  { name: "email", label: "Email", type: "email" }, { name: "cellulare", label: "Cellulare" },
  { name: "indirizzo", label: "Indirizzo", full: true }, { name: "cap", label: "CAP" }, { name: "citta", label: "Comune" },
  { name: "provincia", label: "Provincia" }, { name: "nazione", label: "Nazione" }, { name: "taglia", label: "Taglia" },
  { name: "tipo", label: "Tipo", type: "select", required: true, keepOrder: true, options: toOpts(o.tipi_socio) },
  { name: "qualifica", label: "Qualifica", type: "select", keepOrder: true, options: toOpts(o.qualifiche) },
  { name: "numero_socio", label: "Numero socio" }, { name: "data_iscrizione", label: "Data iscrizione", type: "date" },
  { name: "stato", label: "Stato", type: "select", required: true, keepOrder: true, options: toOpts(o.stati_socio) },
  { name: "note", label: "Note associative", type: "textarea", full: true },
];
const NEW = { tipo: "socio", stato: "attivo" };

function PickerDialog({ onClose, onAdd, onOpen, onCreate }) {
  const [q, setQ] = useState("");
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="w-[95vw] max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="asd-picker-dialog">
        <DialogHeader><DialogTitle className="font-display">Nuovo socio</DialogTitle>
          <DialogDescription>Cerca prima la persona nell'anagrafica dell'organizzazione (Staff, Volontari, Da classificare, soci) per non crearne un doppione.</DialogDescription></DialogHeader>
        <Input autoFocus placeholder="Nome e cognome, codice fiscale, email, cellulare o n. socio" value={q} onChange={(e) => setQ(e.target.value)} data-testid="asd-picker-search" />
        <AsdPeopleResults q={q} onAdd={onAdd} onOpen={onOpen} testid="asd-picker" />
        <div className="flex justify-end pt-2"><Button variant="outline" onClick={onCreate} data-testid="asd-picker-create"><Plus className="w-4 h-4 mr-1" />Crea nuova persona</Button></div>
      </DialogContent>
    </Dialog>
  );
}

function DupDialog({ dup, onClose, onLink, onForce }) {
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="w-[95vw] max-w-xl" data-testid="asd-dup-dialog">
        <DialogHeader><DialogTitle className="font-display">Persona già presente?</DialogTitle><DialogDescription>{dup.message}</DialogDescription></DialogHeader>
        <ul className="divide-y divide-slate-100">{dup.matches.map((m) => (
          <li key={m.id} className="py-2 flex flex-col sm:flex-row sm:items-center gap-2" data-testid={`asd-dup-row-${m.id}`}>
            <div className="flex-1 text-sm"><b className="font-medium">{m.cognome} {m.nome}</b><div className="text-xs text-slate-500">Stesso {m.campi.map((c) => ({ codice_fiscale: "codice fiscale", email: "email", cellulare: "cellulare" })[c]).join(", ")}{m.socio_id ? " · già socio" : ""}</div></div>
            {!m.socio_id && <Button size="sm" className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" onClick={() => onLink(m.id)} data-testid={`asd-dup-link-${m.id}`}>Collega questa persona</Button>}
          </li>))}</ul>
        {!dup.cf && <div className="flex justify-end"><Button variant="outline" onClick={onForce} data-testid="asd-dup-force">Crea comunque una nuova persona</Button></div>}
      </DialogContent>
    </Dialog>
  );
}

export function AsdSoci({ status, onChanged }) {
  const [params, setParams] = useSearchParams();
  const [f, setF] = useState({ q: "", stato: "", tipo: "" });
  const { rows, loading, reload } = useAsd("/asd/soci", f);
  const [edit, setEdit] = useState(null);
  const [picker, setPicker] = useState(false);
  const [dup, setDup] = useState(null);
  const [staffOf, setStaffOf] = useState(null);
  const o = status.options;
  const done = () => { reload(); onChanged(); };
  const addPerson = async (pid, base = NEW) => {
    try {
      const { data: link } = await api.get(`/asd/persona/${pid}`);
      if (link.socio) { await openSocio(link.socio.id); toast.info("La persona è già socio: ho aperto la sua scheda"); return; }
      const { data } = await api.get(`/persons/${pid}`); setPicker(false); setDup(null); setEdit({ ...base, ...sharedOf(data), persona_id: pid });
    } catch (e) { apiErr(e); }
  };
  const openSocio = (sid) => api.get("/asd/soci").then(({ data }) => { const s = data.find((x) => x.id === sid); setPicker(false); if (s) setEdit(s); }).catch(apiErr);
  useEffect(() => {
    const pid = params.get("persona"), sid = params.get("socio");
    if (pid) addPerson(pid); else if (sid) openSocio(sid);
    if (pid || sid) setParams({ tab: "soci" }, { replace: true });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const submit = async (form, force = false) => {
    try { await saveItem("/asd/soci", edit, force ? { ...form, conferma_nuova: true } : form); done(); setDup(null); }
    catch (e) {
      const d = e.response?.data?.detail;
      if (e.response?.status === 409 && d?.field === "duplicati") { setDup({ ...d, form }); return; }
      throw e;
    }
  };
  const cols = [
    ["cognome", "Cognome e nome", (r) => <span className="font-medium text-slate-900">{r.cognome} {r.nome}</span>],
    ["tipo", "Tipo", (r) => o.tipi_socio[r.tipo]], ["qualifica", "Qualifica", (r) => o.qualifiche[r.qualifica] || "—"],
    ["codice_fiscale", "Codice fiscale"], ["cellulare", "Cellulare"],
    ["certificato_stato", "Certificato", (r) => <span className="flex flex-col gap-0.5"><StatoBadge s={r.certificato_stato} testid={`asd-socio-cert-${r.id}`} />{r.certificato_scadenza && <span className="text-xs text-slate-500">{fmtDate(r.certificato_scadenza)}</span>}</span>],
    ["quote_da_pagare", "Quote aperte", (r) => r.quote_da_pagare || "—"],
    ["stato", "Stato", (r) => <StatoBadge s={r.stato} />],
  ];
  const showSearch = f.q.trim().length >= 2;
  return (
    <SectionCard title={`Soci e Tesserati (${rows.length})`} action={<PrimaryButton onClick={() => setPicker(true)} data-testid="asd-socio-new"><Plus className="w-4 h-4 mr-1" />Nuovo socio</PrimaryButton>}>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mb-4">
        <Input placeholder="Cerca nome, codice fiscale, email, cellulare, n. socio" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} data-testid="asd-soci-search" />
        <select className={SEL} value={f.tipo} onChange={(e) => setF({ ...f, tipo: e.target.value })} data-testid="asd-soci-filter-tipo"><option value="">Tutti i tipi</option>{Object.entries(o.tipi_socio).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
        <select className={SEL} value={f.stato} onChange={(e) => setF({ ...f, stato: e.target.value })} data-testid="asd-soci-filter-stato"><option value="">Tutti gli stati</option>{Object.entries(o.stati_socio).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
      </div>
      {showSearch && (
        <div className="mb-5 rounded-lg border border-slate-200 bg-slate-50/60 px-4 py-3" data-testid="asd-anagrafica-panel">
          <div className="flex items-center justify-between gap-2 mb-1">
            <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">Ricerca anagrafica · tutte le persone dell'organizzazione</div>
            <Button size="sm" variant="ghost" onClick={() => setEdit(NEW)} data-testid="asd-anagrafica-create"><UserPlus className="w-4 h-4 mr-1" />Crea nuova persona</Button>
          </div>
          <p className="text-xs text-slate-500 mb-1">I filtri Tipo e Stato valgono solo per l'elenco soci qui sotto.</p>
          <AsdPeopleResults q={f.q} onAdd={(pid) => addPerson(pid)} onOpen={openSocio} testid="asd-anagrafica" />
        </div>
      )}
      <AsdTable cols={cols} rows={rows} loading={loading} testid="asd-soci" onEdit={setEdit} canDelete={status.can_delete}
        extra={(r) => <button type="button" onClick={() => setStaffOf(r)} className="p-1.5 text-slate-500 hover:text-slate-900" title="Staff e Volontari" data-testid={`asd-soci-staff-${r.id}`}><Users className="w-4 h-4" /></button>}
        onDelete={(r) => deleteItem("/asd/soci", r, `${r.cognome} ${r.nome} dall'elenco soci (l'anagrafica resta in Staff / Volontari)`, done)}
        empty={showSearch ? "Nessun socio corrisponde alla ricerca: controlla la ricerca anagrafica qui sopra." : "Nessun socio registrato. Aggiungi il primo con «Nuovo socio»."} />
      {picker && <PickerDialog onClose={() => setPicker(false)} onAdd={(pid) => addPerson(pid)} onOpen={openSocio} onCreate={() => { setPicker(false); setEdit(NEW); }} />}
      {edit && <EntityDialog open onOpenChange={(v) => !v && setEdit(null)} title={edit.id ? "Modifica socio" : edit.persona_id ? "Aggiungi come socio" : "Nuovo socio · nuova persona"} fields={fields(o)} initial={edit} testid="asd-socio" size="large"
        onSubmit={(form) => submit(form)} />}
      {dup && <DupDialog dup={dup} onClose={() => setDup(null)} onLink={(pid) => addPerson(pid, { ...dup.form, persona_id: undefined })}
        onForce={() => { const form = dup.form; setDup(null); submit(form, true).catch(apiErr); }} />}
      {staffOf && <AsdSocioStaff socio={staffOf} onClose={() => setStaffOf(null)} onChanged={done} />}
    </SectionCard>
  );
}
