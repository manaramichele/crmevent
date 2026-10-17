import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { UI } from "./CookieContent";
import { ChevronDown } from "lucide-react";

const BTN = "flex-1 min-w-[150px] h-11 px-4 rounded-full border-2 border-[#0ABAB5] bg-white text-slate-900 text-sm font-semibold hover:bg-[#0ABAB5] hover:text-white transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0ABAB5] focus-visible:ring-offset-2";

function ServiceRow({ s, lang, t }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="border border-slate-200 rounded-lg" data-testid={`cookie-service-${s.id}`}>
      <button type="button" onClick={() => setOpen(!open)} className="w-full flex items-center justify-between gap-2 px-3 py-2 text-left text-sm" aria-expanded={open}>
        <span><span className="font-semibold text-slate-800">{s.name}</span><span className="text-slate-500"> · {s.provider}</span></span>
        <ChevronDown className={`w-4 h-4 shrink-0 text-slate-400 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="px-3 pb-3 text-xs text-slate-600 space-y-2">
          <p>{lang === "it" ? s.purpose_it : s.purpose_en}</p>
          {s.cookies?.length ? (
            <ul className="space-y-1">
              {s.cookies.map((c) => (
                <li key={c.name} className="bg-slate-50 rounded px-2 py-1"><code className="font-mono text-slate-800">{c.name}</code> · {t.duration}: {lang === "it" ? c.duration_it : c.duration_en}<br />{lang === "it" ? c.description_it : c.description_en}</li>
              ))}
            </ul>
          ) : <p className="italic">{t.noCookies}</p>}
        </div>
      )}
    </li>
  );
}

function Category({ id, cfg, lang, t, checked, onChange }) {
  const c = cfg.categories[id][lang];
  const services = cfg.services.filter((s) => s.category === id);
  return (
    <section className="border-t border-slate-100 pt-4" data-testid={`cookie-category-${id}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold text-slate-900">{c.name}</h3>
          <p className="text-sm text-slate-600 mt-0.5">{c.description}</p>
        </div>
        {id === "necessary"
          ? <span className="text-xs font-semibold text-[#078a86] whitespace-nowrap pt-1" data-testid="cookie-necessary-always-on">{t.alwaysOn}</span>
          : <Switch checked={checked} onCheckedChange={onChange} aria-label={c.name} data-testid={`cookie-toggle-${id}`} className="data-[state=checked]:bg-[#0ABAB5]" />}
      </div>
      {services.length > 0 && <ul className="mt-3 space-y-2">{services.map((s) => <ServiceRow key={s.id} s={s} lang={lang} t={t} />)}</ul>}
    </section>
  );
}

export function CookiePreferences({ open, onOpenChange, cfg, lang, initial, onSave, onAcceptAll, onRejectAll }) {
  const t = UI[lang];
  const [sel, setSel] = useState({ analytics: false, marketing: false });
  useEffect(() => { if (open) { setSel({ analytics: !!initial?.analytics, marketing: !!initial?.marketing }); } }, [open, initial]);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg w-[calc(100vw-1.5rem)] max-h-[90vh] overflow-y-auto rounded-2xl p-5 sm:p-6 z-[10001]" data-testid="cookie-preferences-dialog">
        <DialogHeader>
          <DialogTitle className="text-slate-900">{t.prefsTitle}</DialogTitle>
          <DialogDescription className="text-sm text-slate-600">{cfg.banner[lang].text}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          {["necessary", "analytics", "marketing"].map((id) => (
            <Category key={id} id={id} cfg={cfg} lang={lang} t={t} checked={sel[id]} onChange={(v) => setSel((s) => ({ ...s, [id]: v }))} />
          ))}
        </div>
        <div className="flex flex-wrap gap-2 pt-4 border-t border-slate-100">
          <button type="button" className={BTN} onClick={onAcceptAll} data-testid="cookie-prefs-accept-all">{t.accept}</button>
          <button type="button" className={BTN} onClick={onRejectAll} data-testid="cookie-prefs-reject-all">{t.reject}</button>
          <button type="button" className={BTN} onClick={() => onSave(sel)} data-testid="cookie-prefs-save">{t.save}</button>
        </div>
        <p className="text-xs text-slate-500">
          <a href="/privacy-policy" className="underline hover:text-slate-800">{t.privacy}</a> · <a href="/cookie-policy" className="underline hover:text-slate-800">{t.cookie}</a>
        </p>
      </DialogContent>
    </Dialog>
  );
}

export { BTN };
