import { useState, useEffect, useCallback } from "react";
import { useParams, useSearchParams, Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { CheckCircle2, CalendarDays, MapPin, Loader2 } from "lucide-react";
import { toast } from "sonner";

const BACKEND = "https://api.crmevent.it";
const CRM_LOGO = "/logo-crmevent.png?v=2";

const PHONE_CCS = [
  ["+39", "🇮🇹 +39"], ["+41", "🇨🇭 +41"], ["+33", "🇫🇷 +33"], ["+49", "🇩🇪 +49"],
  ["+34", "🇪🇸 +34"], ["+44", "🇬🇧 +44"], ["+43", "🇦🇹 +43"], ["+32", "🇧🇪 +32"],
  ["+31", "🇳🇱 +31"], ["+351", "🇵🇹 +351"], ["+30", "🇬🇷 +30"], ["+386", "🇸🇮 +386"],
  ["+385", "🇭🇷 +385"], ["+1", "🇺🇸 +1"],
];
const NONE = "__none__";
const ALTRO = "Altro";

const T = {
  it: {
    docTitle: "Dai la tua disponibilità",
    notfoundTitle: "Link non valido",
    notfoundDesc: "Questo link non è più disponibile. Contatta l'organizzazione dell'evento.",
    closedTitle: "Raccolta chiusa",
    closedDesc: "La raccolta delle disponibilità per questo evento è terminata.",
    thanksTitle: "Grazie, disponibilità registrata.",
    thanksDesc1: "I tuoi dati sono stati inviati all'organizzazione di",
    formTitle: "Dai la tua disponibilità",
    formSubtitle: "Inserisci i tuoi dati e indica i giorni in cui sei disponibile per collaborare all'evento.",
    setupNote: "Puoi indicare la tua disponibilità anche nei giorni precedenti e successivi all'evento per le attività di allestimento e disallestimento.",
    nome: "Nome", cognome: "Cognome", cellulare: "Cellulare", email: "Email",
    cf: "Codice Fiscale", dataNascita: "Data di nascita",
    cfPlaceholder: "es. RSSMRA85T10A562S", cellPlaceholder: "333 1234567",
    noCf: "Non ho un Codice Fiscale italiano",
    whenTitle: "Quando sei disponibile?",
    whenSubtitle: "Seleziona una o più giornate. Gli orari sono facoltativi.",
    phaseSetup: "Allestimento", phaseTeardown: "Disallestimento", phaseEvent: "Evento",
    from: "Dalle", to: "Alle",
    prefLabel: "Che attività preferiresti svolgere? (facoltativo)",
    prefNone: "Nessuna preferenza", prefOther: "Altro", prefOtherPlaceholder: "Descrivi brevemente",
    privacyPre: "Ho preso visione della", privacyLink: "Privacy Policy", privacyPost: ".",
    marketing: "Desidero ricevere via email aggiornamenti e comunicazioni relative agli eventi.",
    optional: "(facoltativo)",
    submit: "Invia disponibilità", submitting: "Invio in corso...",
    reqField: "Campo obbligatorio:",
    errDataNascita: "Inserisci la Data di nascita",
    errCf: "Inserisci un Codice Fiscale valido (16 caratteri)",
    errDay: "Seleziona almeno una giornata di disponibilità",
    errPrivacy: "Devi prendere visione della Privacy Policy",
    errSend: "Invio non riuscito. Riprova.",
    errNet: "Errore di rete. Riprova.",
    poweredBy: "Powered by",
    localeDate: "it-IT",
  },
  en: {
    docTitle: "Share your availability",
    notfoundTitle: "Invalid link",
    notfoundDesc: "This link is no longer available. Please contact the event organizer.",
    closedTitle: "Collection closed",
    closedDesc: "Availability collection for this event has ended.",
    thanksTitle: "Thank you, your availability has been recorded.",
    thanksDesc1: "Your details have been sent to the organizer of",
    formTitle: "Share your availability",
    formSubtitle: "Enter your details and select the days you are available to help with the event.",
    setupNote: "You can also indicate your availability on the days before and after the event, for set-up and tear-down activities.",
    nome: "First name", cognome: "Last name", cellulare: "Mobile", email: "Email",
    cf: "Italian Tax Code (Codice Fiscale)", dataNascita: "Date of birth",
    cfPlaceholder: "e.g. RSSMRA85T10A562S", cellPlaceholder: "333 1234567",
    noCf: "I don't have an Italian Tax Code",
    whenTitle: "When are you available?",
    whenSubtitle: "Select one or more days. Times are optional.",
    phaseSetup: "Set-up", phaseTeardown: "Tear-down", phaseEvent: "Event",
    from: "From", to: "To",
    prefLabel: "What activity would you prefer? (optional)",
    prefNone: "No preference", prefOther: "Other", prefOtherPlaceholder: "Briefly describe",
    privacyPre: "I have read the", privacyLink: "Privacy Policy", privacyPost: ".",
    marketing: "I would like to receive updates and communications about events by email.",
    optional: "(optional)",
    submit: "Submit availability", submitting: "Submitting...",
    reqField: "Required field:",
    errDataNascita: "Please enter your date of birth",
    errCf: "Please enter a valid Tax Code (16 characters)",
    errDay: "Please select at least one available day",
    errPrivacy: "You must read the Privacy Policy",
    errSend: "Submission failed. Please try again.",
    errNet: "Network error. Please try again.",
    poweredBy: "Powered by",
    localeDate: "en-GB",
  },
};

const fmtDay = (date, locale) => {
  try {
    const s = new Date(date + "T00:00:00").toLocaleDateString(locale, { weekday: "long", day: "numeric", month: "long" });
    return s.charAt(0).toUpperCase() + s.slice(1);
  } catch { return date; }
};

export default function Partecipa() {
  const { code } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const [lang, setLangState] = useState(() => ((searchParams.get("lang") || "it").toLowerCase().startsWith("en") ? "en" : "it"));
  const t = (k) => T[lang][k] ?? T.it[k] ?? k;
  const setLang = (l) => {
    setLangState(l);
    const sp = new URLSearchParams(searchParams);
    sp.set("lang", l);
    setSearchParams(sp, { replace: true });
  };

  const [state, setState] = useState("loading"); // loading | notfound | inactive | form | done
  const [info, setInfo] = useState(null);
  const [form, setForm] = useState({ nome: "", cognome: "", cellulare: "", prefix: "+39", email: "", codice_fiscale: "", data_nascita: "" });
  const [noCf, setNoCf] = useState(false);
  const [days, setDays] = useState({});
  const [pref, setPref] = useState(NONE);
  const [prefAltro, setPrefAltro] = useState("");
  const [privacy, setPrivacy] = useState(false);
  const [marketing, setMarketing] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${BACKEND}/api/public/availability/${code}`);
      if (res.status === 404) { setState("notfound"); return; }
      const data = await res.json();
      setInfo(data);
      setState(data.active ? "form" : "inactive");
    } catch { setState("notfound"); }
  }, [code]);
  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    document.title = `${t("docTitle")} · ${info?.event?.nome || "CRMEvent"}`;
  }, [lang, info]); // eslint-disable-line react-hooks/exhaustive-deps

  const ch = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const toggleDay = (date, on) => setDays((d) => ({ ...d, [date]: { ...(d[date] || {}), disponibile: on } }));
  const setDayTime = (date, k, v) => setDays((d) => ({ ...d, [date]: { ...(d[date] || {}), [k]: v } }));

  const submit = async () => {
    for (const [k, lbl] of [["nome", t("nome")], ["cognome", t("cognome")], ["cellulare", t("cellulare")], ["email", t("email")]]) {
      if (!String(form[k] || "").trim()) { toast.error(`${t("reqField")} ${lbl}`); return; }
    }
    if (noCf) {
      if (!form.data_nascita) { toast.error(t("errDataNascita")); return; }
    } else if ((form.codice_fiscale || "").trim().length !== 16) {
      toast.error(t("errCf")); return;
    }
    const selDays = Object.entries(days).filter(([, v]) => v.disponibile).map(([date, v]) => ({ date, disponibile: true, dalle: v.dalle || "", alle: v.alle || "" }));
    if (!selDays.length) { toast.error(t("errDay")); return; }
    if (!privacy) { toast.error(t("errPrivacy")); return; }
    setSubmitting(true);
    try {
      const rawNum = (form.cellulare || "").trim();
      const cellFull = (rawNum.startsWith("+") || rawNum.startsWith("00")) ? rawNum : `${form.prefix || "+39"}${rawNum}`;
      const body = {
        nome: form.nome, cognome: form.cognome, cellulare: cellFull, email: form.email.trim(),
        codice_fiscale: noCf ? null : (form.codice_fiscale || "").trim().toUpperCase(),
        data_nascita: noCf ? form.data_nascita : null,
        days: selDays,
        preferenza_attivita: pref === NONE ? null : pref,
        preferenza_altro: pref === ALTRO ? prefAltro : null,
        privacy: true,
        marketing_consent: marketing,
        lang,
      };
      const res = await fetch(`${BACKEND}/api/public/availability/${code}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) { toast.error(data.detail || t("errSend")); if (res.status === 410) setState("inactive"); return; }
      setState("done");
      window.scrollTo(0, 0);
    } catch { toast.error(t("errNet")); }
    finally { setSubmitting(false); }
  };

  const logoSrc = info?.event?.has_logo ? `${BACKEND}/api/public/availability/${code}/logo` : CRM_LOGO;
  const shellProps = { logo: logoSrc, event: info?.event, lang, setLang };

  if (state === "loading") return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50"><Loader2 className="w-6 h-6 animate-spin text-tiffany-active" /></div>
  );

  if (state === "notfound") return (
    <Shell logo={CRM_LOGO} lang={lang} setLang={setLang}>
      <div className="text-center py-8"><h1 className="text-xl font-bold text-slate-900 mb-2">{t("notfoundTitle")}</h1>
        <p className="text-slate-500 text-sm">{t("notfoundDesc")}</p></div>
    </Shell>
  );

  if (state === "inactive") return (
    <Shell {...shellProps}>
      <div className="text-center py-8"><h1 className="text-xl font-bold text-slate-900 mb-2">{t("closedTitle")}</h1>
        <p className="text-slate-500 text-sm" data-testid="partecipa-closed">{t("closedDesc")}</p></div>
    </Shell>
  );

  if (state === "done") return (
    <Shell {...shellProps}>
      <div className="text-center py-8" data-testid="partecipa-thankyou">
        <CheckCircle2 className="w-14 h-14 text-emerald-500 mx-auto mb-3" />
        <h1 className="text-xl font-bold text-slate-900 mb-2">{t("thanksTitle")}</h1>
        <p className="text-slate-500 text-sm">{t("thanksDesc1")} <strong>{info?.event?.nome}</strong>.</p>
      </div>
    </Shell>
  );

  const ev = info.event;
  return (
    <Shell {...shellProps}>
      <h1 className="text-2xl font-bold text-slate-900 font-display">{t("formTitle")}</h1>
      <p className="text-sm text-slate-500 mt-1.5">{t("formSubtitle")}</p>
      {(info.has_allestimento || info.has_disallestimento) && <p className="text-sm text-amber-700 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2 mt-3">{t("setupNote")}</p>}

      <div className="mt-6 space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <F label={t("nome")} req><Input value={form.nome} onChange={(e) => ch("nome", e.target.value)} data-testid="pf-nome" /></F>
          <F label={t("cognome")} req><Input value={form.cognome} onChange={(e) => ch("cognome", e.target.value)} data-testid="pf-cognome" /></F>
          <F label={t("cellulare")} req>
            <div className="flex gap-2">
              <select value={form.prefix} onChange={(e) => ch("prefix", e.target.value)} className="border border-slate-200 rounded-md px-2 py-2 text-sm bg-white w-[112px] shrink-0" data-testid="pf-cellulare-prefix">
                {PHONE_CCS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
              <Input type="tel" inputMode="tel" value={form.cellulare} onChange={(e) => ch("cellulare", e.target.value)} placeholder={t("cellPlaceholder")} className="flex-1 min-w-0" data-testid="pf-cellulare" />
            </div>
          </F>
          <F label={t("email")} req><Input type="email" inputMode="email" value={form.email} onChange={(e) => ch("email", e.target.value)} data-testid="pf-email" /></F>
          {!noCf
            ? <div className="sm:col-span-2"><F label={t("cf")} req><Input value={form.codice_fiscale} onChange={(e) => ch("codice_fiscale", e.target.value.toUpperCase())} maxLength={16} className="font-mono uppercase" placeholder={t("cfPlaceholder")} data-testid="pf-codice-fiscale" /></F></div>
            : <F label={t("dataNascita")} req><Input type="date" value={form.data_nascita} onChange={(e) => ch("data_nascita", e.target.value)} data-testid="pf-data-nascita" /></F>}
        </div>
        <label className="flex items-center gap-2.5 cursor-pointer -mt-1">
          <Checkbox checked={noCf} onCheckedChange={(v) => setNoCf(!!v)} data-testid="pf-no-cf" />
          <span className="text-sm text-slate-600">{t("noCf")}</span>
        </label>

        <div className="pt-2">
          <h2 className="text-base font-semibold text-slate-800">{t("whenTitle")}</h2>
          <p className="text-xs text-slate-400 mb-3">{t("whenSubtitle")}</p>
          <div className="space-y-2.5">
            {(info.days || []).map((d) => {
              const on = !!days[d.date]?.disponibile;
              const phaseLabel = d.fase === "allestimento" ? t("phaseSetup") : d.fase === "disallestimento" ? t("phaseTeardown") : t("phaseEvent");
              return (
                <div key={d.date} className={`border rounded-xl p-3 transition-colors ${on ? "border-tiffany-border bg-tiffany-light/30" : "border-slate-200"}`} data-testid={`pf-day-${d.date}`}>
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2.5">
                      <Checkbox checked={on} onCheckedChange={(v) => toggleDay(d.date, !!v)} data-testid={`pf-day-check-${d.date}`} />
                      <div>
                        <div className="text-sm font-medium text-slate-800">{fmtDay(d.date, t("localeDate"))}</div>
                        {d.descrizione && <div className="text-sm font-semibold text-slate-700" data-testid={`pf-day-desc-${d.date}`}>{d.descrizione}</div>}
                        <span className={`inline-block text-[11px] font-semibold px-2 py-0.5 rounded-full mt-0.5 ${d.fase === "allestimento" ? "bg-amber-100 text-amber-700" : d.fase === "disallestimento" ? "bg-violet-100 text-violet-700" : "bg-sky-100 text-sky-700"}`}>{phaseLabel}</span>
                      </div>
                    </div>
                  </div>
                  {on && (
                    <div className="grid grid-cols-1 gap-2 mt-3 pl-8" data-testid={`pf-day-times-${d.date}`}>
                      <div>
                        <Label className="block text-[11px] text-slate-400 mb-1">{t("from")}</Label>
                        <Input type="time" style={{ width: 150, maxWidth: "100%" }} value={days[d.date]?.dalle || ""} onChange={(e) => setDayTime(d.date, "dalle", e.target.value)} data-testid={`pf-day-from-${d.date}`} />
                      </div>
                      <div>
                        <Label className="block text-[11px] text-slate-400 mb-1">{t("to")}</Label>
                        <Input type="time" style={{ width: 150, maxWidth: "100%" }} value={days[d.date]?.alle || ""} onChange={(e) => setDayTime(d.date, "alle", e.target.value)} data-testid={`pf-day-to-${d.date}`} />
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        <F label={t("prefLabel")}>
          <Select value={pref} onValueChange={setPref}>
            <SelectTrigger data-testid="pf-pref"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>{t("prefNone")}</SelectItem>
              {[...(info.attivita_options || [])].sort((a, b) => a.localeCompare(b, "it", { sensitivity: "base" })).map((a) => <SelectItem key={a} value={a}>{a}</SelectItem>)}
              <SelectItem value={ALTRO}>{t("prefOther")}</SelectItem>
            </SelectContent>
          </Select>
        </F>
        {pref === ALTRO && <Input placeholder={t("prefOtherPlaceholder")} value={prefAltro} onChange={(e) => setPrefAltro(e.target.value)} data-testid="pf-pref-altro" />}

        <label className="flex items-start gap-2.5 pt-2 cursor-pointer">
          <Checkbox checked={privacy} onCheckedChange={(v) => setPrivacy(!!v)} data-testid="pf-privacy" className="mt-0.5" />
          <span className="text-sm text-slate-600">{t("privacyPre")} <Link to="/privacy-policy" target="_blank" className="text-tiffany-active hover:underline">{t("privacyLink")}</Link>{t("privacyPost")}</span>
        </label>

        <label className="flex items-start gap-2.5 cursor-pointer">
          <Checkbox checked={marketing} onCheckedChange={(v) => setMarketing(!!v)} data-testid="pf-marketing" className="mt-0.5" />
          <span className="text-sm text-slate-600">{t("marketing")} <span className="text-slate-400">{t("optional")}</span></span>
        </label>

        <Button onClick={submit} disabled={submitting} className="w-full bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold h-11 text-base" data-testid="pf-submit">
          {submitting ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />{t("submitting")}</> : t("submit")}
        </Button>
      </div>
    </Shell>
  );
}

function F({ label, req, children }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs font-medium text-slate-600">{label}{req && <span className="text-red-500 ml-0.5">*</span>}</Label>
      {children}
    </div>
  );
}

function LangSwitch({ lang, setLang }) {
  if (!setLang) return null;
  const opt = (code, label) => (
    <button type="button" onClick={() => setLang(code)} data-testid={`lang-${code}`}
      className={`px-2.5 py-1 text-xs font-semibold rounded-md transition-colors ${lang === code ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}>{label}</button>
  );
  return (
    <div className="flex items-center gap-0.5 bg-slate-100 rounded-lg p-0.5" data-testid="lang-switch">
      {opt("it", "Italiano")}{opt("en", "English")}
    </div>
  );
}

function Shell({ logo, event, lang, setLang, children }) {
  const dmY = (d) => (d ? d.slice(8, 10) + "/" + d.slice(5, 7) + "/" + d.slice(0, 4) : "");
  return (
    <div className="min-h-screen bg-slate-50 pt-6 pb-40 px-4">
      <div className="max-w-lg mx-auto">
        {setLang && <div className="flex justify-end mb-3"><LangSwitch lang={lang} setLang={setLang} /></div>}
        <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
          <div className="p-5 sm:p-7">
            <div className="flex flex-col items-center text-center mb-5">
              <img src={logo} alt="CRMEvent" className="w-[150px] sm:w-[200px] h-auto max-h-28 object-contain" onError={(e) => { e.currentTarget.src = CRM_LOGO; }} />
              {event && (
                <div className="mt-4 pb-4 border-b border-slate-100 w-full">
                  <div className="text-lg font-bold text-slate-900">{event.nome}</div>
                  <div className="flex flex-wrap justify-center gap-x-3 gap-y-1 mt-1 text-sm text-slate-500">
                    {event.data_inizio && <span className="inline-flex items-center gap-1"><CalendarDays className="w-3.5 h-3.5" />{dmY(event.data_inizio)}{event.data_fine && event.data_fine !== event.data_inizio ? ` → ${dmY(event.data_fine)}` : ""}</span>}
                    {event.localita && <span className="inline-flex items-center gap-1"><MapPin className="w-3.5 h-3.5" />{event.localita}</span>}
                  </div>
                </div>
              )}
            </div>
            {children}
          </div>
        </div>
        <p className="text-center text-xs text-slate-400 mt-4">Powered by <strong className="text-slate-500">CRMEvent</strong></p>
      </div>
    </div>
  );
}
