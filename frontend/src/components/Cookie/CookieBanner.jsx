import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { getStored, isValid, saveConsent, OPEN_EVENT } from "@/lib/consent";
import { CookiePreferences, BTN } from "./CookiePreferences";
import { UI, FALLBACK, detectLang } from "./CookieContent";

// Banner proprietario: nessuna categoria preselezionata, nessun consenso implicito, non blocca l'uso del sito.
export default function CookieBanner() {
  const [cfg, setCfg] = useState(null);
  const [show, setShow] = useState(false);
  const [prefs, setPrefs] = useState(false);
  const [source, setSource] = useState("banner");
  const [lang, setLang] = useState(detectLang);
  const t = UI[lang];

  useEffect(() => {
    api.get("/privacy/config")
      .then(({ data }) => { setCfg(data); setShow(!isValid(getStored(), data.versions)); })
      .catch(() => { setCfg(FALLBACK); setShow(!isValid(getStored(), null)); });
  }, []);

  useEffect(() => {
    const open = () => { setSource("footer"); setPrefs(true); };
    window.addEventListener(OPEN_EVENT, open);
    return () => window.removeEventListener(OPEN_EVENT, open);
  }, []);

  const save = useCallback(async (choices, action, src) => {
    setPrefs(false);
    setShow(false);
    await saveConsent(choices, action, src, lang, cfg?.versions || {});
  }, [cfg, lang]);

  if (!cfg) return null;
  const b = cfg.banner[lang];
  const src = prefs ? (show ? "preferences" : source) : "banner";
  return (
    <>
      {show && !prefs && (
        <div role="dialog" aria-modal="false" aria-labelledby="cookie-banner-title" data-testid="cookie-banner"
          className="fixed z-[10000] bottom-0 inset-x-0 sm:bottom-4 sm:left-4 sm:right-auto sm:max-w-[440px] bg-white sm:rounded-2xl border-t-4 sm:border-t-0 sm:border-l-4 border-[#0ABAB5] shadow-[0_12px_40px_rgba(15,23,42,0.18)] p-5 animate-in slide-in-from-bottom-4 fade-in duration-300">
          <div className="flex items-center justify-between gap-3 mb-3">
            <img src="/logo-crmevent.png?v=5" alt="CRMEvent" className="h-8 w-auto" />
            <div className="flex rounded-full border border-slate-200 p-0.5 text-xs" role="group" aria-label={t.lang} data-testid="cookie-lang-switch">
              {["it", "en"].map((l) => (
                <button key={l} type="button" onClick={() => setLang(l)} aria-pressed={lang === l} data-testid={`cookie-lang-${l}`}
                  className={`px-2.5 py-0.5 rounded-full font-semibold uppercase transition-colors ${lang === l ? "bg-[#0ABAB5] text-white" : "text-slate-500 hover:text-slate-900"}`}>{l}</button>
              ))}
            </div>
          </div>
          <h2 id="cookie-banner-title" className="font-semibold text-slate-900 text-base">{b.title}</h2>
          <p className="text-sm text-slate-600 mt-1.5 leading-relaxed" data-testid="cookie-banner-text">{b.text}</p>
          <p className="text-xs text-slate-500 mt-2">
            <a href="/privacy-policy" className="underline hover:text-slate-800" data-testid="cookie-banner-privacy-link">{t.privacy}</a> · <a href="/cookie-policy" className="underline hover:text-slate-800" data-testid="cookie-banner-cookie-link">{t.cookie}</a>
          </p>
          <div className="grid grid-cols-1 gap-2 mt-4">
            <button type="button" className={BTN} onClick={() => save({ analytics: true, marketing: true }, "accept_all", "banner")} data-testid="cookie-accept-all">{t.accept}</button>
            <button type="button" className={BTN} onClick={() => save({ analytics: false, marketing: false }, "reject_all", "banner")} data-testid="cookie-reject-all">{t.reject}</button>
            <button type="button" className={BTN} onClick={() => { setSource("preferences"); setPrefs(true); }} data-testid="cookie-customize">{t.customize}</button>
          </div>
        </div>
      )}
      <CookiePreferences open={prefs} onOpenChange={setPrefs} cfg={cfg} lang={lang} initial={getStored()?.choices}
        onSave={(sel) => save(sel, "custom", src)}
        onAcceptAll={() => save({ analytics: true, marketing: true }, "accept_all", src)}
        onRejectAll={() => save({ analytics: false, marketing: false }, "reject_all", src)} />
    </>
  );
}
