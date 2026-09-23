import { useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { EntityManager, StatusBadge, useCollection, FileUpload } from "@/components/crm";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { UserPlus } from "lucide-react";

const INV = { non_invitato: "gray", invito_inviato: "orange", account_attivato: "green", accesso_disabilitato: "red" };
const INV_LABEL = { non_invitato: "Non invitato", invito_inviato: "Invito inviato", account_attivato: "Attivato", accesso_disabilitato: "Disabilitato" };

function InviteDialog({ person, open, onOpenChange, onDone }) {
  const [role, setRole] = useState("volunteer");
  const [busy, setBusy] = useState(false);
  const status = person?.invite_status || "non_invitato";
  const invite = async () => {
    setBusy(true);
    try { const { data } = await api.post(`/persons/${person.id}/invite`, { role }); toast.success(data.email_sent ? "Invito inviato via email" : "Invito creato (email non inviata)"); onDone(); onOpenChange(false); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  const toggle = async (enabled) => {
    try { await api.put(`/persons/${person.id}/access`, { enabled }); toast.success(enabled ? "Accesso riattivato" : "Accesso disabilitato"); onDone(); onOpenChange(false); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="invite-dialog">
        <DialogHeader><DialogTitle className="font-display">Invita su CRMEvent</DialogTitle>
          <DialogDescription>{person?.nome} {person?.cognome} — {person?.email || "nessuna email"}</DialogDescription></DialogHeader>
        <div className="space-y-3 py-2">
          <div className="flex items-center gap-2"><span className="text-sm text-slate-500">Stato attuale:</span><StatusBadge color={INV[status]}>{INV_LABEL[status]}</StatusBadge></div>
          <div className="space-y-1.5"><Label className="text-xs">Ruolo accesso</Label>
            <Select value={role} onValueChange={setRole}><SelectTrigger data-testid="invite-role"><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="volunteer">Volontario</SelectItem><SelectItem value="staff">Staff</SelectItem></SelectContent></Select>
          </div>
        </div>
        <DialogFooter className="flex-col sm:flex-row gap-2">
          {status === "account_attivato" && <Button variant="outline" onClick={() => toggle(false)} data-testid="disable-access">Disabilita accesso</Button>}
          {status === "accesso_disabilitato" && <Button variant="outline" onClick={() => toggle(true)} data-testid="enable-access">Riattiva accesso</Button>}
          <Button onClick={invite} disabled={busy || !person?.email} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="send-invite">{busy ? "..." : status === "non_invitato" ? "Invia invito" : "Reinvia invito"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function Persons() {
  const { items: companies, loading } = useCollection("/companies");
  const [invite, setInvite] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);
  if (loading) return <div className="text-slate-400">Caricamento...</div>;
  const companyOpts = companies.map((c) => ({ value: c.id, label: c.nome }));

  const fields = [
    { name: "nome", label: "Nome", required: true },
    { name: "cognome", label: "Cognome" },
    { name: "ruolo", label: "Ruolo / Qualifica" },
    { name: "email", label: "Email", type: "email" },
    { name: "telefono", label: "Telefono", type: "tel" },
    { name: "azienda_id", label: "Azienda", type: "select", options: companyOpts },
    { name: "citta", label: "Città" },
    { name: "note", label: "Note", type: "textarea", full: true },
  ];
  const columns = [
    { key: "nome", label: "Nome", render: (r) => <span className="font-medium text-slate-800">{r.nome} {r.cognome}</span> },
    { key: "ruolo", label: "Ruolo" },
    { key: "email", label: "Email" },
    { key: "azienda_id", label: "Azienda", render: (r) => companies.find((c) => c.id === r.azienda_id)?.nome || "—" },
    { key: "invite_status", label: "Accesso", render: (r) => <StatusBadge color={INV[r.invite_status || "non_invitato"]}>{INV_LABEL[r.invite_status || "non_invitato"]}</StatusBadge> },
  ];
  const rowActions = (row) => (
    <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-500 hover:text-tiffany-active" title="Invita su CRMEvent" onClick={() => setInvite(row)} data-testid={`invite-${row.id}`}><UserPlus className="w-4 h-4" /></Button>
  );

  return (
    <>
      <EntityManager key={refreshKey} title="Persone" subtitle="Contatti, referenti, staff e volontari" endpoint="/persons"
        fields={fields} columns={columns} entityLabel="persona" testid="person" searchKeys={["nome", "cognome", "email", "ruolo"]} rowActions={rowActions} />
      {invite && <InviteDialog person={invite} open={!!invite} onOpenChange={(o) => !o && setInvite(null)} onDone={() => setRefreshKey((k) => k + 1)} />}
    </>
  );
}
