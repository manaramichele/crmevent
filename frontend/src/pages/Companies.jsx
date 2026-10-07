import { useState, useEffect, useCallback } from "react";
import api, { formatApiError } from "@/lib/api";
import { StatusBadge, PageHeader, PrimaryButton, TextAction, DeleteConfirm } from "@/components/crm";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Plus, Pencil, Trash2, Search, Eye } from "lucide-react";
import { useSort, SortIcon, sortRows } from "@/lib/sortable";
import { toast } from "sonner";
import CompanyDialog from "@/components/CompanyDialog";
import CompanyDetailDialog from "@/components/CompanyDetailDialog";
import { useCan } from "@/lib/perms";

const TIPO_LABEL = { azienda: "Azienda", prospect: "Prospect", fornitore: "Fornitore", sponsor: "Sponsor", partner: "Partner", media: "Media", istituzione: "Istituzione" };
const TIPO_COLOR = { azienda: "tiffany", prospect: "orange", fornitore: "blue", sponsor: "green", partner: "green", media: "blue", istituzione: "gray" };

export default function Companies() {
  const perm = useCan("aziende");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [detailId, setDetailId] = useState(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try { const { data } = await api.get("/companies"); setRows(data); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { reload(); }, [reload]);

  const del = async (r) => { try { await api.delete(`/companies/${r.id}`); await reload(); toast.success("Azienda eliminata"); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };
  const filtered = rows.filter((r) => !q || `${r.nome} ${r.settore || ""} ${r.citta || ""}`.toLowerCase().includes(q.toLowerCase()));
  const { sort, toggle } = useSort({ key: "nome", dir: "asc" });
  const COLS = [
    { key: "nome", label: "Azienda" }, { key: "settore", label: "Settore" }, { key: "citta", label: "Città" },
    { key: "email", label: "Email" }, { key: "tipo", label: "Tipo", sortAccessor: (r) => TIPO_LABEL[r.tipo] || r.tipo || "" },
  ];
  const sorted = sortRows(filtered, sort, COLS);

  return (
    <div className="animate-fade-up">
      <PageHeader title="Aziende" subtitle="Anagrafica unica: sponsor, partner, media, fornitori, prospect e istituzioni"
        action={perm.create ? <PrimaryButton onClick={() => { setEditing(null); setFormOpen(true); }} data-testid="add-company-button"><Plus className="w-4 h-4 mr-1.5" />Aggiungi azienda</PrimaryButton> : null} />
      <div className="mb-4 relative w-full sm:w-72">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
        <Input className="pl-9" placeholder="Cerca aziende..." value={q} onChange={(e) => setQ(e.target.value)} data-testid="search-company-input" />
      </div>
      <div className="md:hidden space-y-2.5" data-testid="companies-mobile-list">
        {loading ? <p className="py-10 text-center text-slate-400 text-sm">Caricamento...</p>
          : sorted.length === 0 ? <p className="py-10 text-center text-slate-400 text-sm">Nessuna azienda trovata.</p>
          : sorted.map((r) => (
            <div key={r.id} className="bg-white border border-slate-200 rounded-xl shadow-sm p-4" data-testid={`company-card-${r.id}`}>
              <div className="flex items-start justify-between gap-2"><span className="font-semibold text-slate-900 break-words">{r.nome}</span><StatusBadge color={TIPO_COLOR[r.tipo] || TIPO_COLOR[String(r.tipo || "").toLowerCase()] || "gray"}>{TIPO_LABEL[r.tipo] || r.tipo || "—"}</StatusBadge></div>
              <div className="mt-1 text-sm text-slate-600">{[r.settore, r.citta].filter(Boolean).join(" · ") || "—"}</div>
              {r.email && <a href={`mailto:${r.email}`} className="text-sm text-slate-600 break-all">{r.email}</a>}
              <div className="mt-3 flex flex-wrap gap-2">
                <TextAction icon={Eye} onClick={() => setDetailId(r.id)} data-testid={`m-open-company-${r.id}`}>Apri</TextAction>
                {perm.edit && <TextAction icon={Pencil} onClick={() => { setEditing(r); setFormOpen(true); }} data-testid={`m-edit-company-${r.id}`}>Modifica</TextAction>}
                {perm.remove && <DeleteConfirm onConfirm={() => del(r)} testid={`m-confirm-delete-company-${r.id}`}><TextAction icon={Trash2} danger data-testid={`m-delete-company-${r.id}`}>Elimina</TextAction></DeleteConfirm>}
              </div>
            </div>
          ))}
      </div>
      <div className="hidden md:block bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-slate-200 bg-slate-50/70">
              {COLS.map((c) => (
                <th key={c.key} onClick={() => toggle(c.key)} data-testid={`sort-${c.key}`} className="text-left font-semibold text-slate-600 px-4 py-3 whitespace-nowrap cursor-pointer select-none group">
                  <span className="inline-flex items-center gap-1">{c.label}<SortIcon active={sort.key === c.key} dir={sort.dir} /></span>
                </th>
              ))}
              <th className="text-right font-semibold text-slate-600 px-4 py-3 whitespace-nowrap">Azioni</th>
            </tr></thead>
            <tbody>
              {loading ? <tr><td colSpan={6} className="px-4 py-10 text-center text-slate-400">Caricamento...</td></tr>
                : sorted.length === 0 ? <tr><td colSpan={6} className="px-4 py-10 text-center text-slate-400">Nessuna azienda trovata.</td></tr>
                : sorted.map((r) => (
                  <tr key={r.id} className="border-b border-slate-100 hover:bg-slate-50/80 transition-colors cursor-pointer" onClick={() => setDetailId(r.id)} data-testid={`company-row-${r.id}`}>
                    <td className="px-4 py-3"><span className="font-medium text-slate-800">{r.nome}</span></td>
                    <td className="px-4 py-3 text-slate-700">{r.settore || "—"}</td>
                    <td className="px-4 py-3 text-slate-700">{r.citta || "—"}</td>
                    <td className="px-4 py-3 text-slate-700">{r.email || "—"}</td>
                    <td className="px-4 py-3"><StatusBadge color={TIPO_COLOR[r.tipo] || TIPO_COLOR[String(r.tipo || "").toLowerCase()] || "gray"}>{TIPO_LABEL[r.tipo] || r.tipo || "—"}</StatusBadge></td>
                    <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center justify-end gap-1">
                        <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-500 hover:text-tiffany-active" onClick={() => { setEditing(r); setFormOpen(true); }} data-testid={`edit-company-${r.id}`}><Pencil className="w-4 h-4" /></Button>
                        <AlertDialog>
                          <AlertDialogTrigger asChild><Button variant="ghost" size="icon" className="h-8 w-8 text-slate-500 hover:text-red-500" data-testid={`delete-company-${r.id}`}><Trash2 className="w-4 h-4" /></Button></AlertDialogTrigger>
                          <AlertDialogContent><AlertDialogHeader><AlertDialogTitle>Confermi l'eliminazione?</AlertDialogTitle><AlertDialogDescription>Questa azione non può essere annullata.</AlertDialogDescription></AlertDialogHeader>
                            <AlertDialogFooter><AlertDialogCancel>Annulla</AlertDialogCancel><AlertDialogAction className="bg-red-500 hover:bg-red-600" onClick={() => del(r)} data-testid={`confirm-delete-company-${r.id}`}>Elimina</AlertDialogAction></AlertDialogFooter></AlertDialogContent>
                        </AlertDialog>
                      </div>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>

      <CompanyDialog open={formOpen} onOpenChange={setFormOpen} initial={editing} onSaved={() => reload()} />
      {detailId && <CompanyDetailDialog companyId={detailId} open={!!detailId} onOpenChange={(o) => !o && setDetailId(null)}
        onChanged={reload} onEdit={(c) => { setDetailId(null); setEditing(c); setFormOpen(true); }} />}
    </div>
  );
}
