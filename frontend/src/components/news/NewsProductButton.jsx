import { useNavigate } from "react-router-dom";
import { ArrowRight, Store } from "lucide-react";

// Collegamento notizia → scheda Marketplace (per ID prodotto; nome e chiave letti dal catalogo aggiornato).
export function newsProductAction(p) {
  if (!p) return null;
  if (p.active) return p.route ? { label: "Apri modulo", to: p.route } : { label: "Scopri il modulo", to: `/marketplace?servizio=${encodeURIComponent(p.key)}` };
  return { label: p.purchasable ? "Scopri e acquista" : "Scopri il modulo", to: `/marketplace?servizio=${encodeURIComponent(p.key)}` };
}

export function NewsProductButton({ product, testid, compact = false }) {
  const navigate = useNavigate();
  const a = newsProductAction(product);
  if (!a) return null;
  return (
    <button type="button" onClick={() => navigate(a.to)} title={product.name} data-testid={testid}
      className={`inline-flex items-center gap-1.5 rounded-full border border-slate-900 bg-slate-900 text-white font-semibold hover:bg-slate-700 transition-colors shrink-0 ${compact ? "h-9 px-4 text-sm" : "h-9 px-4 text-sm mt-3"}`}>
      <Store className="w-4 h-4" />{a.label}{!compact && <span className="font-normal text-white/70">· {product.name}</span>}<ArrowRight className="w-3.5 h-3.5" />
    </button>
  );
}
