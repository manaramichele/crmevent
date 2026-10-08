import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { LifeBuoy, Smartphone, LogOut, Lock } from "lucide-react";

const inFrame = () => { try { return window.self !== window.top; } catch { return true; } };

function useRemaining(expiresAt, onExpire) {
  const [left, setLeft] = useState(() => new Date(expiresAt).getTime() - Date.now());
  useEffect(() => {
    if (!expiresAt) return undefined;
    const t = setInterval(() => {
      const l = new Date(expiresAt).getTime() - Date.now();
      setLeft(l);
      if (l <= 0) { clearInterval(t); onExpire(); }
    }, 1000);
    return () => clearInterval(t);
  }, [expiresAt, onExpire]);
  const s = Math.max(0, Math.floor(left / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function MobilePreview({ open, onOpenChange }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[440px] p-4" data-testid="support-mobile-preview">
        <DialogHeader><DialogTitle>Anteprima mobile</DialogTitle>
          <DialogDescription>Vista smartphone (390px) dell'account in assistenza.</DialogDescription></DialogHeader>
        <div className="mx-auto rounded-[2rem] border-[10px] border-slate-900 overflow-hidden bg-white" style={{ width: 410, maxWidth: "100%" }}>
          <iframe title="Anteprima mobile" src={window.location.pathname + window.location.search} className="block w-full" style={{ height: "min(720px, 70vh)" }} data-testid="support-mobile-iframe" />
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function SupportBanner() {
  const { user, startSupport, stopSupport } = useAuth();
  const [preview, setPreview] = useState(false);
  const sup = user?.support;
  const left = useRemaining(sup?.expires_at, stopSupport);
  if (!sup) return null;
  const framed = inFrame();
  return (
    <div className="bg-amber-400 text-slate-900 border-b border-amber-500 px-3 sm:px-4 py-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-sm" data-testid="support-banner">
      <LifeBuoy className="w-4 h-4 shrink-0" />
      <span className="min-w-0 flex-1 basis-[calc(100%-2rem)] sm:basis-auto leading-snug" data-testid="support-banner-text">
        <b className="font-semibold">Modalità assistenza</b> – Stai visualizzando l'account di <b className="font-semibold">{sup.target_name}</b>
        <span className="text-slate-800"> · {sup.org_name}</span>
        {sup.read_only && <span className="inline-flex items-center gap-1 ml-1 font-semibold" data-testid="support-read-only"><Lock className="w-3.5 h-3.5" />sola lettura</span>}
      </span>
      {!framed && (
        <div className="w-full sm:w-auto flex flex-wrap items-center justify-between sm:justify-end gap-2">
          <span className="text-xs tabular-nums" data-testid="support-remaining">Scade tra {left}</span>
          {(sup.orgs || []).length > 1 && (
            <select className="h-8 rounded-md border border-amber-600 bg-white/80 px-2 text-xs max-w-[10rem]" value={sup.org_id}
              onChange={(e) => startSupport(sup.target_user_id, e.target.value)} data-testid="support-org-select">
              {sup.orgs.map((o) => <option key={o.org_id} value={o.org_id}>{o.nome}</option>)}
            </select>
          )}
          <Button size="sm" variant="outline" className="h-8 bg-white/70 border-amber-600 hidden sm:inline-flex" onClick={() => setPreview(true)} data-testid="support-mobile-btn"><Smartphone className="w-4 h-4 mr-1" />Anteprima mobile</Button>
          <Button size="sm" className="h-8 bg-slate-900 hover:bg-slate-800 text-white" onClick={stopSupport} data-testid="support-exit-btn"><LogOut className="w-4 h-4 mr-1" />Torna a Super Admin</Button>
        </div>
      )}
      {preview && <MobilePreview open={preview} onOpenChange={setPreview} />}
    </div>
  );
}
