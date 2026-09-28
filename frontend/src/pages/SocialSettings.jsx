import { useEffect, useState } from "react";
import api from "@/lib/platformApi";
import { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Instagram, Save, Loader2, Bot, Facebook, Linkedin } from "lucide-react";

const FIELD = "w-full h-11 px-3 rounded-lg border border-slate-200 bg-white focus:border-tiffany focus:ring-2 focus:ring-tiffany/30 outline-none text-sm transition-all";
const AREA = "w-full px-3 py-2 rounded-lg border border-slate-200 bg-white focus:border-tiffany focus:ring-2 focus:ring-tiffany/30 outline-none text-sm transition-all";

const csv = (v) => (Array.isArray(v) ? v.join(", ") : v || "");
const toArr = (s) => (s || "").split(",").map((x) => x.trim()).filter(Boolean);

export default function SocialSettings() {
  const [s, setS] = useState(null);
  const [busy, setBusy] = useState(false);
  const [accounts, setAccounts] = useState([]);

  const load = async () => {
    const [{ data }, acc] = await Promise.all([
      api.get("/social/settings"),
      api.get("/social/accounts"),
    ]);
    setS(data);
    setAccounts(acc.data);
  };
  useEffect(() => { load().catch((e) => toast.error(formatApiError(e?.response?.data?.detail))); }, []);

  const set = (k, v) => setS((p) => ({ ...p, [k]: v }));

  const save = async () => {
    setBusy(true);
    try {
      const payload = {
        brand_name: s.brand_name, description: s.description, website: s.website, target: s.target,
        tone_of_voice: s.tone_of_voice, main_goal: s.main_goal, default_cta: s.default_cta,
        frequency: s.frequency, avoid_info: s.avoid_info, ai_instructions: s.ai_instructions,
        logo_url: s.logo_url,
        preferred_days: toArr(csv(s.preferred_days)), preferred_times: toArr(csv(s.preferred_times)),
        brand_colors: toArr(csv(s.brand_colors)), main_hashtags: toArr(csv(s.main_hashtags)),
      };
      const { data } = await api.put("/social/settings", payload);
      setS(data);
      toast.success("Impostazioni Social salvate");
    } catch (e) { toast.error(formatApiError(e?.response?.data?.detail)); }
    setBusy(false);
  };

  const connectIg = async () => {
    try {
      const { data } = await api.get("/oauth/instagram/start");
      window.location.href = data.authorize_url;
    } catch (e) { toast.error(formatApiError(e?.response?.data?.detail)); }
  };

  const igAccount = accounts.find((a) => a.platform === "instagram");

  const disconnectIg = async () => {
    if (!igAccount || !window.confirm("Scollegare l'account Instagram?")) return;
    try { await api.delete(`/social/accounts/${igAccount.id}`); toast.success("Instagram scollegato"); load(); }
    catch (e) { toast.error(formatApiError(e?.response?.data?.detail)); }
  };

  const refreshIg = async () => {
    if (!igAccount) return;
    try { const { data } = await api.post(`/social/accounts/${igAccount.id}/refresh-token`); toast.success("Token aggiornato"); load(); }
    catch (e) { toast.error(formatApiError(e?.response?.data?.detail)); }
  };

  useEffect(() => {
    const p = new URLSearchParams(window.location.search).get("instagram");
    if (p === "connected") toast.success("Instagram collegato con successo");
    else if (p === "error") toast.error("Collegamento Instagram non riuscito");
    if (p) window.history.replaceState({}, "", window.location.pathname);
  }, []);

  if (!s) return <div className="text-slate-400 py-24 text-center">Caricamento…</div>;

  return (
    <div className="max-w-4xl space-y-6" data-testid="social-settings-page">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Impostazioni Social</h1>
        <p className="text-slate-500 text-sm mt-1">Configura il brand e la voce dell'AI per i contenuti social della tua organizzazione.</p>
      </div>

      {/* Brand */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 space-y-4">
        <h2 className="font-semibold text-slate-800">Brand & Obiettivi</h2>
        <div className="grid sm:grid-cols-2 gap-4">
          <div><label className="text-sm text-slate-600">Nome brand / evento</label><input className={FIELD} data-testid="ss-brand-name" value={s.brand_name || ""} onChange={(e) => set("brand_name", e.target.value)} /></div>
          <div><label className="text-sm text-slate-600">Sito web</label><input className={FIELD} data-testid="ss-website" value={s.website || ""} onChange={(e) => set("website", e.target.value)} /></div>
        </div>
        <div><label className="text-sm text-slate-600">Descrizione</label><textarea rows={2} className={AREA} data-testid="ss-description" value={s.description || ""} onChange={(e) => set("description", e.target.value)} /></div>
        <div className="grid sm:grid-cols-2 gap-4">
          <div><label className="text-sm text-slate-600">Target</label><input className={FIELD} data-testid="ss-target" value={s.target || ""} onChange={(e) => set("target", e.target.value)} placeholder="es. organizzatori di eventi sportivi" /></div>
          <div><label className="text-sm text-slate-600">Tone of voice</label><input className={FIELD} data-testid="ss-tone" value={s.tone_of_voice || ""} onChange={(e) => set("tone_of_voice", e.target.value)} placeholder="es. professionale ma vicino" /></div>
        </div>
        <div className="grid sm:grid-cols-2 gap-4">
          <div><label className="text-sm text-slate-600">Obiettivo principale</label><input className={FIELD} data-testid="ss-goal" value={s.main_goal || ""} onChange={(e) => set("main_goal", e.target.value)} /></div>
          <div><label className="text-sm text-slate-600">CTA predefinita</label><input className={FIELD} data-testid="ss-cta" value={s.default_cta || ""} onChange={(e) => set("default_cta", e.target.value)} placeholder="es. Prova gratis 14 giorni" /></div>
        </div>
      </div>

      {/* Pubblicazione */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 space-y-4">
        <h2 className="font-semibold text-slate-800">Pubblicazione</h2>
        <div className="grid sm:grid-cols-3 gap-4">
          <div><label className="text-sm text-slate-600">Frequenza</label><input className={FIELD} data-testid="ss-frequency" value={s.frequency || ""} onChange={(e) => set("frequency", e.target.value)} placeholder="es. 3 post/settimana" /></div>
          <div><label className="text-sm text-slate-600">Giorni preferiti</label><input className={FIELD} data-testid="ss-days" value={csv(s.preferred_days)} onChange={(e) => set("preferred_days", e.target.value)} placeholder="lun, mer, ven" /></div>
          <div><label className="text-sm text-slate-600">Orari preferiti</label><input className={FIELD} data-testid="ss-times" value={csv(s.preferred_times)} onChange={(e) => set("preferred_times", e.target.value)} placeholder="10:00, 18:00" /></div>
        </div>
      </div>

      {/* Brand identity */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 space-y-4">
        <h2 className="font-semibold text-slate-800">Identità visiva & Hashtag</h2>
        <div className="grid sm:grid-cols-2 gap-4">
          <div><label className="text-sm text-slate-600">Logo (URL)</label><input className={FIELD} data-testid="ss-logo" value={s.logo_url || ""} onChange={(e) => set("logo_url", e.target.value)} /></div>
          <div><label className="text-sm text-slate-600">Colori brand</label><input className={FIELD} data-testid="ss-colors" value={csv(s.brand_colors)} onChange={(e) => set("brand_colors", e.target.value)} placeholder="#0ABAB5, #111827" /></div>
        </div>
        <div><label className="text-sm text-slate-600">Hashtag principali</label><input className={FIELD} data-testid="ss-hashtags" value={csv(s.main_hashtags)} onChange={(e) => set("main_hashtags", e.target.value)} placeholder="#CRMEvent, #eventi" /></div>
      </div>

      {/* AI guidance */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 space-y-4">
        <h2 className="font-semibold text-slate-800 flex items-center gap-2"><Bot className="w-4 h-4 text-tiffany-active" />Istruzioni per l'AI</h2>
        <div><label className="text-sm text-slate-600">Informazioni da evitare</label><textarea rows={2} className={AREA} data-testid="ss-avoid" value={s.avoid_info || ""} onChange={(e) => set("avoid_info", e.target.value)} placeholder="Argomenti, claim o parole da non usare" /></div>
        <div><label className="text-sm text-slate-600">Istruzioni personalizzate</label><textarea rows={3} className={AREA} data-testid="ss-ai-instructions" value={s.ai_instructions || ""} onChange={(e) => set("ai_instructions", e.target.value)} /></div>
      </div>

      <div className="flex justify-end">
        <Button onClick={save} disabled={busy} data-testid="ss-save-btn" className="h-11 px-6 bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold">
          {busy ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Save className="w-4 h-4 mr-2" />}Salva impostazioni
        </Button>
      </div>

      {/* Accounts */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 space-y-4" data-testid="social-accounts-card">
        <h2 className="font-semibold text-slate-800">Account social</h2>
        <p className="text-sm text-slate-500">In questa fase è attivo Instagram (collegamento ufficiale via OAuth Meta). La pubblicazione automatica resta disattivata: i contenuti richiedono sempre l'approvazione. Facebook e LinkedIn arriveranno in seguito.</p>
        <div className="flex items-center gap-3 p-3 rounded-lg border border-slate-200 flex-wrap">
          <Instagram className="w-6 h-6 text-pink-600 shrink-0" />
          {igAccount && igAccount.connected ? (
            <>
              <span className="text-sm font-medium text-slate-800" data-testid="ig-username">@{igAccount.username || igAccount.handle}</span>
              <span className="text-xs px-2 py-1 rounded-full bg-green-100 text-green-700" data-testid="ig-status">Collegato</span>
              <Button variant="outline" onClick={refreshIg} data-testid="ig-refresh-btn">Aggiorna token</Button>
              <Button variant="outline" className="text-red-600" onClick={disconnectIg} data-testid="ig-disconnect-btn">Scollega</Button>
            </>
          ) : (
            <>
              <span className="text-sm text-slate-500 flex-1">Nessun account Instagram collegato</span>
              <Button onClick={connectIg} data-testid="ig-connect-btn" className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold">Collega Instagram</Button>
              {igAccount && <span className="text-xs px-2 py-1 rounded-full bg-amber-100 text-amber-700" data-testid="ig-status">{igAccount.status || "non collegato"}</span>}
            </>
          )}
        </div>
        <div className="flex items-center gap-3 p-3 rounded-lg border border-slate-100 opacity-50">
          <Facebook className="w-6 h-6 text-blue-600" /><span className="text-sm text-slate-500">Facebook — prossimamente</span>
        </div>
        <div className="flex items-center gap-3 p-3 rounded-lg border border-slate-100 opacity-50">
          <Linkedin className="w-6 h-6 text-sky-700" /><span className="text-sm text-slate-500">LinkedIn — prossimamente</span>
        </div>
      </div>

      {/* Autopilot */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 flex items-center justify-between" data-testid="autopilot-card">
        <div>
          <h2 className="font-semibold text-slate-800">Pilota automatico</h2>
          <p className="text-sm text-slate-500">Pubblicazione automatica dei contenuti approvati. Disattivato in questa versione: ogni contenuto richiede sempre l'approvazione manuale.</p>
        </div>
        <span className="text-sm font-bold px-3 py-1.5 rounded-full bg-slate-100 text-slate-500" data-testid="autopilot-state">OFF</span>
      </div>
    </div>
  );
}
