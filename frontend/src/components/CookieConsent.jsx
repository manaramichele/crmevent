import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { readConsent, saveConsent, applyConsent } from "@/lib/analytics";
import { Cookie } from "lucide-react";

// First-party cookie consent banner wired to Google Consent Mode v2.
// "Solo necessari" is as easy as "Accetta tutti". Choice persisted in localStorage.
export default function CookieConsent() {
  const [open, setOpen] = useState(false);
  const [prefs, setPrefs] = useState(false);
  const [analytics, setAnalytics] = useState(false);

  useEffect(() => {
    const c = readConsent();
    if (c) { applyConsent(c); setAnalytics(!!c.analytics); }
    else setOpen(true);
    const openPrefs = () => { const cur = readConsent(); setAnalytics(!!cur?.analytics); setPrefs(true); setOpen(true); };
    window.addEventListener("open-cookie-preferences", openPrefs);
    return () => window.removeEventListener("open-cookie-preferences", openPrefs);
  }, []);

  const choose = useCallback((c) => { saveConsent(c); setOpen(false); setPrefs(false); }, []);
  if (!open) return null;

  return (
    <div className="fixed inset-x-0 bottom-0 z-[200] p-3 sm:p-4" data-testid="cookie-banner">
      <div className="mx-auto max-w-3xl bg-white border border-slate-200 rounded-2xl shadow-xl p-5">
        <div className="flex items-start gap-3">
          <span className="w-9 h-9 rounded-lg bg-tiffany-light text-tiffany-fg flex items-center justify-center shrink-0"><Cookie className="w-5 h-5" /></span>
          <div className="min-w-0 flex-1">
            <div className="font-semibold text-slate-900">Rispettiamo la tua privacy</div>
            <p className="text-sm text-slate-500 mt-1">
              Usiamo cookie tecnici necessari e, con il tuo consenso, cookie di analisi (Google Analytics) per migliorare CRMEvent. Puoi accettare, rifiutare o scegliere. Dettagli nella <Link to="/cookie" className="text-tiffany-active underline">Cookie Policy</Link>.
            </p>

            {prefs && (
              <div className="mt-3 space-y-2" data-testid="cookie-prefs">
                <label className="flex items-center justify-between gap-3 p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                  <span className="text-sm"><span className="font-medium text-slate-800">Necessari</span><span className="block text-xs text-slate-400">Sempre attivi — indispensabili al funzionamento.</span></span>
                  <input type="checkbox" checked disabled className="accent-tiffany" />
                </label>
                <label className="flex items-center justify-between gap-3 p-2.5 rounded-lg bg-slate-50 border border-slate-100 cursor-pointer">
                  <span className="text-sm"><span className="font-medium text-slate-800">Analisi (Google Analytics)</span><span className="block text-xs text-slate-400">Statistiche anonime di utilizzo.</span></span>
                  <input type="checkbox" checked={analytics} onChange={(e) => setAnalytics(e.target.checked)} data-testid="cookie-pref-analytics" className="accent-tiffany w-4 h-4" />
                </label>
              </div>
            )}

            <div className="mt-4 flex flex-col sm:flex-row gap-2">
              {!prefs ? (
                <>
                  <button onClick={() => choose({ analytics: true, ads: false })} data-testid="cookie-accept-all" className="h-10 px-4 rounded-lg bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold text-sm order-1">Accetta tutti</button>
                  <button onClick={() => choose({ analytics: false, ads: false })} data-testid="cookie-reject" className="h-10 px-4 rounded-lg border border-slate-300 hover:bg-slate-50 text-slate-700 font-semibold text-sm order-2">Solo necessari</button>
                  <button onClick={() => setPrefs(true)} data-testid="cookie-manage" className="h-10 px-4 rounded-lg text-slate-500 hover:text-slate-800 text-sm order-3 sm:ml-auto">Gestisci preferenze</button>
                </>
              ) : (
                <>
                  <button onClick={() => choose({ analytics, ads: false })} data-testid="cookie-save-prefs" className="h-10 px-4 rounded-lg bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold text-sm">Salva preferenze</button>
                  <button onClick={() => choose({ analytics: false, ads: false })} data-testid="cookie-reject-2" className="h-10 px-4 rounded-lg border border-slate-300 hover:bg-slate-50 text-slate-700 font-semibold text-sm">Solo necessari</button>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
