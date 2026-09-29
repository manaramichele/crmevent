import { useState, useEffect, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { CheckCircle2, CalendarDays, MapPin, Loader2 } from "lucide-react";
import { toast } from "sonner";

const BACKEND = process.env.REACT_APP_BACKEND_URL;

const PHONE_CCS = [
  ["+39", "🇮🇹 +39"], ["+41", "🇨🇭 +41"], ["+33", "🇫🇷 +33"], ["+49", "🇩🇪 +49"],
  ["+34", "🇪🇸 +34"], ["+44", "🇬🇧 +44"], ["+43", "🇦🇹 +43"], ["+32", "🇧🇪 +32"],
  ["+31", "🇳🇱 +31"], ["+351", "🇵🇹 +351"], ["+30", "🇬🇷 +30"], ["+386", "🇸🇮 +386"],
  ["+385", "🇭🇷 +385"], ["+1", "🇺🇸 +1"],
];
const dmY = (d) => (d ? d.slice(8, 10) + "/" + d.slice(5, 7) + "/" + d.slice(0, 4) : "");
const NONE = "__none__";
const ALTRO = "Altro";

export default function Partecipa() {
  const { code } = useParams();
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
      document.title = `Dai la tua disponibilità · ${data.event?.nome || "CRMEvent"}`;
    } catch { setState("notfound"); }
  }, [code]);
  useEffect(() => { load(); }, [load]);

  const ch = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const toggleDay = (date, on) => setDays((d) => ({ ...d, [date]: { ...(d[date] || {}), disponibile: on } }));
  const setDayTime = (date, k, v) => setDays((d) => ({ ...d, [date]: { ...(d[date] || {}), [k]: v } }));

  const submit = async () => {
    for (const [k, lbl] of [["nome", "Nome"], ["cognome", "Cognome"], ["cellulare", "Cellulare"], ["email", "Email"]]) {
      if (!String(form[k] || "").trim()) { toast.error(`Campo obbligatorio: ${lbl}`); return; }
    }
    if (noCf) {
      if (!form.data_nascita) { toast.error("Inserisci la Data di nascita"); return; }
    } else if ((form.codice_fiscale || "").trim().length !== 16) {
      toast.error("Inserisci un Codice Fiscale valido (16 caratteri)"); return;
    }
    const selDays = Object.entries(days).filter(([, v]) => v.disponibile).map(([date, v]) => ({ date, disponibile: true, dalle: v.dalle || "", alle: v.alle || "" }));
    if (!selDays.length) { toast.error("Seleziona almeno una giornata di disponibilità"); return; }
    if (!privacy) { toast.error("Devi prendere visione della Privacy Policy"); return; }
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
      };
      const res = await fetch(`${BACKEND}/api/public/availability/${code}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) { toast.error(data.detail || "Invio non riuscito. Riprova."); if (res.status === 410) setState("inactive"); return; }
      setState("done");
      window.scrollTo(0, 0);
    } catch { toast.error("Errore di rete. Riprova."); }
    finally { setSubmitting(false); }
  };

  const logoSrc = info?.event?.has_logo ? `${BACKEND}/api/public/availability/${code}/logo` : "/logo-crmevent-dark.png?v=2";

  if (state === "loading") return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50"><Loader2 className="w-6 h-6 animate-spin text-tiffany-active" /></div>
  );

  if (state === "notfound") return (
    <Shell logo="/logo-crmevent-dark.png?v=2">
      <div className="text-center py-8"><h1 className="text-xl font-bold text-slate-900 mb-2">Link non valido</h1>
        <p className="text-slate-500 text-sm">Questo link non è più disponibile. Contatta l'organizzazione dell'evento.</p></div>
    </Shell>
  );

  if (state === "inactive") return (
    <Shell logo={logoSrc} event={info?.event}>
      <div className="text-center py-8"><h1 className="text-xl font-bold text-slate-900 mb-2">Raccolta chiusa</h1>
        <p className="text-slate-500 text-sm" data-testid="partecipa-closed">La raccolta delle disponibilità per questo evento è terminata.</p></div>
    </Shell>
  );

  if (state === "done") return (
    <Shell logo={logoSrc} event={info?.event}>
      <div className="text-center py-8" data-testid="partecipa-thankyou">
        <CheckCircle2 className="w-14 h-14 text-emerald-500 mx-auto mb-3" />
        <h1 className="text-xl font-bold text-slate-900 mb-2">Grazie, disponibilità registrata.</h1>
        <p className="text-slate-500 text-sm">I tuoi dati sono stati inviati all'organizzazione di <strong>{info?.event?.nome}</strong>.</p>
      </div>
    </Shell>
  );

  const ev = info.event;
  return (
    <Shell logo={logoSrc} event={ev}>
      <h1 className="text-2xl font-bold text-slate-900 font-display">Dai la tua disponibilità</h1>
      <p className="text-sm text-slate-500 mt-1.5">Inserisci i tuoi dati e indica i giorni in cui sei disponibile per collaborare all'evento.</p>
      {(info.has_allestimento || info.has_disallestimento) && <p className="text-sm text-amber-700 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2 mt-3">Puoi indicare la tua disponibilità anche nei giorni precedenti e successivi all'evento per le attività di allestimento e disallestimento.</p>}

      <div className="mt-6 space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <F label="Nome" req><Input value={form.nome} onChange={(e) => ch("nome", e.target.value)} data-testid="pf-nome" /></F>
          <F label="Cognome" req><Input value={form.cognome} onChange={(e) => ch("cognome", e.target.value)} data-testid="pf-cognome" /></F>
          <F label="Cellulare" req>
            <div className="flex gap-2">
              <select value={form.prefix} onChange={(e) => ch("prefix", e.target.value)} className="border border-slate-200 rounded-md px-2 py-2 text-sm bg-white w-[112px] shrink-0" data-testid="pf-cellulare-prefix">
                {PHONE_CCS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
              <Input type="tel" inputMode="tel" value={form.cellulare} onChange={(e) => ch("cellulare", e.target.value)} placeholder="333 1234567" className="flex-1 min-w-0" data-testid="pf-cellulare" />
            </div>
          </F>
          <F label="Email" req><Input type="email" inputMode="email" value={form.email} onChange={(e) => ch("email", e.target.value)} data-testid="pf-email" /></F>
          {!noCf
            ? <div className="sm:col-span-2"><F label="Codice Fiscale" req><Input value={form.codice_fiscale} onChange={(e) => ch("codice_fiscale", e.target.value.toUpperCase())} maxLength={16} className="font-mono uppercase" placeholder="es. RSSMRA85T10A562S" data-testid="pf-codice-fiscale" /></F></div>
            : <F label="Data di nascita" req><Input type="date" value={form.data_nascita} onChange={(e) => ch("data_nascita", e.target.value)} data-testid="pf-data-nascita" /></F>}
        </div>
        <label className="flex items-center gap-2.5 cursor-pointer -mt-1">
          <Checkbox checked={noCf} onCheckedChange={(v) => setNoCf(!!v)} data-testid="pf-no-cf" />
          <span className="text-sm text-slate-600">Non ho un Codice Fiscale italiano</span>
        </label>

        <div className="pt-2">
          <h2 className="text-base font-semibold text-slate-800">Quando sei disponibile?</h2>
          <p className="text-xs text-slate-400 mb-3">Seleziona una o più giornate. Gli orari sono facoltativi.</p>
          <div className="space-y-2.5">
            {(info.days || []).map((d) => {
              const on = !!days[d.date]?.disponibile;
              return (
                <div key={d.date} className={`border rounded-xl p-3 transition-colors ${on ? "border-tiffany-border bg-tiffany-light/30" : "border-slate-200"}`} data-testid={`pf-day-${d.date}`}>
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2.5">
                      <Checkbox checked={on} onCheckedChange={(v) => toggleDay(d.date, !!v)} data-testid={`pf-day-check-${d.date}`} />
                      <div>
                        <div className="text-sm font-medium text-slate-800 capitalize">{d.label}</div>
                        {d.descrizione && <div className="text-sm font-semibold text-slate-700" data-testid={`pf-day-desc-${d.date}`}>{d.descrizione}</div>}
                        <span className={`inline-block text-[11px] font-semibold px-2 py-0.5 rounded-full mt-0.5 ${d.fase === "allestimento" ? "bg-amber-100 text-amber-700" : d.fase === "disallestimento" ? "bg-violet-100 text-violet-700" : "bg-sky-100 text-sky-700"}`}>{d.fase === "allestimento" ? "Allestimento" : d.fase === "disallestimento" ? "Disallestimento" : "Evento"}</span>
                      </div>
                    </div>
                  </div>
                  {on && (
                    <div className="grid grid-cols-1 gap-2 mt-3 pl-8" data-testid={`pf-day-times-${d.date}`}>
                      <div>
                        <Label className="block text-[11px] text-slate-400 mb-1">Dalle</Label>
                        <Input type="time" style={{ width: 150, maxWidth: "100%" }} value={days[d.date]?.dalle || ""} onChange={(e) => setDayTime(d.date, "dalle", e.target.value)} data-testid={`pf-day-from-${d.date}`} />
                      </div>
                      <div>
                        <Label className="block text-[11px] text-slate-400 mb-1">Alle</Label>
                        <Input type="time" style={{ width: 150, maxWidth: "100%" }} value={days[d.date]?.alle || ""} onChange={(e) => setDayTime(d.date, "alle", e.target.value)} data-testid={`pf-day-to-${d.date}`} />
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        <F label="Che attività preferiresti svolgere? (facoltativo)">
          <Select value={pref} onValueChange={setPref}>
            <SelectTrigger data-testid="pf-pref"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>Nessuna preferenza</SelectItem>
              {[...(info.attivita_options || [])].sort((a, b) => a.localeCompare(b, "it", { sensitivity: "base" })).map((a) => <SelectItem key={a} value={a}>{a}</SelectItem>)}
              <SelectItem value={ALTRO}>Altro</SelectItem>
            </SelectContent>
          </Select>
        </F>
        {pref === ALTRO && <Input placeholder="Descrivi brevemente" value={prefAltro} onChange={(e) => setPrefAltro(e.target.value)} data-testid="pf-pref-altro" />}

        <label className="flex items-start gap-2.5 pt-2 cursor-pointer">
          <Checkbox checked={privacy} onCheckedChange={(v) => setPrivacy(!!v)} data-testid="pf-privacy" className="mt-0.5" />
          <span className="text-sm text-slate-600">Ho preso visione della <Link to="/privacy-policy" target="_blank" className="text-tiffany-active hover:underline">Privacy Policy</Link>.</span>
        </label>

        <label className="flex items-start gap-2.5 cursor-pointer">
          <Checkbox checked={marketing} onCheckedChange={(v) => setMarketing(!!v)} data-testid="pf-marketing" className="mt-0.5" />
          <span className="text-sm text-slate-600">Desidero ricevere via email aggiornamenti e comunicazioni relative agli eventi. <span className="text-slate-400">(facoltativo)</span></span>
        </label>

        <Button onClick={submit} disabled={submitting} className="w-full bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold h-11 text-base" data-testid="pf-submit">
          {submitting ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Invio in corso...</> : "Invia disponibilità"}
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

function Shell({ logo, event, children }) {
  return (
    <div className="min-h-screen bg-slate-50 pt-6 pb-40 px-4">
      <div className="max-w-lg mx-auto">
        <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
          <div className="p-5 sm:p-7">
            <div className="flex flex-col items-center text-center mb-5">
              <img src={logo} alt="" className="w-[150px] sm:w-[200px] h-auto max-h-28 object-contain" onError={(e) => { e.currentTarget.src = "/logo-crmevent-dark.png?v=2"; }} />
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
