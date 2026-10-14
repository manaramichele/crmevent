import { useRef, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Plus, Upload, Download, Search, Pencil, Trash2 } from "lucide-react";
import { MEDIA, BASI, pErr, dt, TIFFANY_BTN, SEL, Field, useLoad } from "@/components/press/pressShared";

const EMPTY = { nome: "", cognome: "", email: "", testata: "", tipologia_media: "Quotidiano", citta: "", provincia: "", regione: "", note: "", stato: "attivo", base_giuridica: "legittimo_interesse" };
const STATO = { attivo: ["Attivo", "text-emerald-700"], sospeso: ["Sospeso", "text-amber-700"], opposto: ["Disiscritto / opposizione", "text-red-600"] };

function ContactForm({ c, onClose, onSaved }) {
  const [f, setF] = useState({ ...EMPTY, ...c });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = async () => {
    try { if (c.id) await api.put(`/press/contacts/${c.id}`, f); else await api.post("/press/contacts", f); toast.success("Contatto salvato"); onSaved(); } catch (e) { pErr(e); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-xl w-[calc(100vw-1rem)] max-h-[94dvh] overflow-y-auto" data-testid="press-contact-form">
        <DialogTitle>{c.id ? "Modifica contatto" : "Nuovo contatto stampa"}</DialogTitle>
        <div className="grid sm:grid-cols-2 gap-3">
          {[["nome", "Nome"], ["cognome", "Cognome"], ["email", "Email *"], ["testata", "Testata giornalistica"], ["citta", "Città"], ["provincia", "Provincia"], ["regione", "Regione"]].map(([k, l]) => <Field key={k} label={l}><Input value={f[k] || ""} onChange={set(k)} data-testid={`press-contact-${k}`} /></Field>)}
          <Field label="Tipologia media"><select className={`${SEL} w-full`} value={f.tipologia_media} onChange={set("tipologia_media")} data-testid="press-contact-media">{MEDIA.map((m) => <option key={m}>{m}</option>)}</select></Field>
          <Field label="Base giuridica *"><select className={`${SEL} w-full`} value={f.base_giuridica || ""} onChange={set("base_giuridica")} data-testid="press-contact-basis">{Object.entries(BASI).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
          {f.stato !== "opposto" ? <Field label="Stato"><select className={`${SEL} w-full`} value={f.stato} onChange={set("stato")} data-testid="press-contact-stato"><option value="attivo">Attivo</option><option value="sospeso">Sospeso</option></select></Field>
            : <p className="text-xs text-red-600 self-end">Il contatto si è disiscritto: non può essere riattivato.</p>}
        </div>
        <Field label="Note"><Textarea rows={2} value={f.note || ""} onChange={set("note")} /></Field>
        <Button onClick={save} className={TIFFANY_BTN} data-testid="press-contact-save">Salva</Button>
      </DialogContent>
    </Dialog>
  );
}

function ImportDialog({ onClose, onDone }) {
  const [text, setText] = useState("");
  const [basis, setBasis] = useState("legittimo_interesse");
  const ref = useRef(null);
  const go = async () => {
    try { const { data } = await api.post("/press/contacts/import", { csv_text: text, base_giuridica: basis }); toast.success(`Importati ${data.added} · duplicati ${data.duplicates} · non validi ${data.invalid}`); onDone(); } catch (e) { pErr(e); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-xl w-[calc(100vw-1rem)]" data-testid="press-import-dialog">
        <DialogTitle>Importa contatti da CSV</DialogTitle>
        <DialogDescription>Colonne: nome, cognome, email, testata, tipologia, citta, provincia, regione, note. Separatore ; o ,. Le email già presenti vengono saltate.</DialogDescription>
        <input ref={ref} type="file" accept=".csv,text/csv" className="hidden" onChange={async (e) => { const f = e.target.files?.[0]; if (f) setText(await f.text()); }} data-testid="press-import-file" />
        <Button variant="outline" onClick={() => ref.current?.click()}><Upload className="w-4 h-4 mr-1" />Scegli file CSV</Button>
        <Textarea rows={6} value={text} onChange={(e) => setText(e.target.value)} placeholder="oppure incolla qui il contenuto CSV" data-testid="press-import-text" />
        <Field label="Base giuridica dei contatti importati *" hint="Un indirizzo email pubblico non equivale a un'autorizzazione automatica: indica la base giuridica applicabile."><select className={`${SEL} w-full`} value={basis} onChange={(e) => setBasis(e.target.value)} data-testid="press-import-basis">{Object.entries(BASI).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
        <Button disabled={!text.trim()} onClick={go} className={TIFFANY_BTN} data-testid="press-import-confirm">Importa</Button>
      </DialogContent>
    </Dialog>
  );
}

export function PressContacts({ canEdit }) {
  const [f, setF] = useState({ q: "", media: "", regione: "" });
  const qs = new URLSearchParams(Object.entries(f).filter(([, v]) => v)).toString();
  const [rows, load] = useLoad(`/press/contacts${qs ? `?${qs}` : ""}`);
  const [edit, setEdit] = useState(null);
  const [imp, setImp] = useState(false);
  const del = async (c) => { if (!window.confirm(`Eliminare ${c.email} dalla rubrica?`)) return; try { await api.delete(`/press/contacts/${c.id}`); toast.success("Contatto eliminato"); load(); } catch (e) { pErr(e); } };
  const exp = async () => { try { const { data } = await api.get("/press/contacts/export", { responseType: "blob" }); const a = document.createElement("a"); a.href = URL.createObjectURL(data); a.download = "contatti-stampa.csv"; a.click(); } catch (e) { pErr(e); } };
  return (
    <div data-testid="press-contacts">
      <div className="flex flex-wrap gap-2 mb-4">
        <div className="relative flex-1 min-w-[200px]"><Search className="w-4 h-4 absolute left-3 top-3 text-slate-400" /><Input className="pl-9" placeholder="Cerca nome, email, testata, città" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} data-testid="press-contacts-search" /></div>
        <select className={SEL} value={f.media} onChange={(e) => setF({ ...f, media: e.target.value })} data-testid="press-contacts-filter-media"><option value="">Tutte le tipologie</option>{MEDIA.map((m) => <option key={m}>{m}</option>)}</select>
        <Input className="w-40" placeholder="Regione" value={f.regione} onChange={(e) => setF({ ...f, regione: e.target.value })} data-testid="press-contacts-filter-regione" />
        {canEdit && <Button onClick={() => setEdit({})} className={TIFFANY_BTN} data-testid="press-contact-new"><Plus className="w-4 h-4 mr-1" />Nuovo contatto</Button>}
        {canEdit && <Button variant="outline" onClick={() => setImp(true)} data-testid="press-contact-import"><Upload className="w-4 h-4 mr-1" />Importa CSV</Button>}
        <Button variant="outline" onClick={exp} data-testid="press-contact-export"><Download className="w-4 h-4 mr-1" />Esporta CSV</Button>
      </div>
      <div className="rounded-2xl border border-slate-200 bg-white overflow-x-auto">
        <table className="w-full min-w-[900px] text-sm" data-testid="press-contacts-table">
          <thead className="bg-slate-50 text-xs text-slate-500"><tr>{["Nome", "Email", "Testata", "Tipologia", "Territorio", "Stato", "Brevo", "Inserito", ""].map((h) => <th key={h} className="px-3 py-2.5 text-left font-semibold">{h}</th>)}</tr></thead>
          <tbody>{!rows ? <tr><td colSpan={9} className="p-6 text-slate-400">Caricamento...</td></tr> : !rows.length ? <tr><td colSpan={9} className="p-8 text-center text-slate-500" data-testid="press-contacts-empty">Nessun contatto in rubrica.</td></tr> : rows.map((c) => (
            <tr key={c.id} className="border-t border-slate-100" data-testid={`press-contact-row-${c.email}`}>
              <td className="px-3 py-2">{c.nome} {c.cognome}</td><td className="px-3 py-2">{c.email}</td><td className="px-3 py-2">{c.testata}</td><td className="px-3 py-2 text-xs">{c.tipologia_media}</td>
              <td className="px-3 py-2 text-xs">{[c.citta, c.provincia, c.regione].filter(Boolean).join(" · ")}</td>
              <td className={`px-3 py-2 text-xs font-semibold ${(STATO[c.stato] || STATO.attivo)[1]}`}>{(STATO[c.stato] || STATO.attivo)[0]}</td>
              <td className="px-3 py-2 text-xs text-slate-500" title={c.brevo_error || ""}>{c.brevo_status || "—"}</td><td className="px-3 py-2 text-xs text-slate-500">{dt(c.created_at)}</td>
              <td className="px-3 py-2 whitespace-nowrap">{canEdit && <><Button size="icon" variant="ghost" onClick={() => setEdit(c)} aria-label="Modifica" data-testid={`press-contact-edit-${c.email}`}><Pencil className="w-4 h-4" /></Button><Button size="icon" variant="ghost" onClick={() => del(c)} aria-label="Elimina" data-testid={`press-contact-del-${c.email}`}><Trash2 className="w-4 h-4 text-red-500" /></Button></>}</td>
            </tr>))}</tbody>
        </table>
      </div>
      {edit && <ContactForm c={edit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load(); }} />}
      {imp && <ImportDialog onClose={() => setImp(false)} onDone={() => { setImp(false); load(); }} />}
    </div>
  );
}
