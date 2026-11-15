import { useEffect, useState } from "react";
import api from "@/lib/api";
import { PromoCard } from "@/components/promo/PromoCard";

export function PromoMaterialsPanel() {
  const [items, setItems] = useState(null);
  const load = () => api.get("/promo-materials").then((r) => setItems(r.data)).catch(() => setItems([]));
  useEffect(() => { load(); }, []);
  return (
    <div className="space-y-4" data-testid="promo-materials-panel">
      <p className="text-sm text-slate-500">Archivio ufficiale dei contenuti commerciali CRMEvent. Ogni raccolta ha video MP4, anteprima JPG 1200×675 cliccabile e newsletter HTML pronta per Brevo. Le pagine video pubbliche mostrano solo i materiali <strong>pubblicati</strong>; nessuna email viene inviata da qui.</p>
      {items === null ? <div className="text-sm text-slate-400" data-testid="promo-loading">Caricamento…</div> : (
        <div className="grid gap-4 xl:grid-cols-2">{items.map((m) => <PromoCard key={m.slug} m={m} onChange={load} />)}</div>
      )}
    </div>
  );
}
