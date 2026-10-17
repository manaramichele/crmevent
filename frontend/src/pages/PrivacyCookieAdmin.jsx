import { useEffect, useState } from "react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Cookie } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { ConsentStats, ConsentRegistry } from "@/components/privacy/ConsentData";
import { BannerEditor, ServicesEditor } from "@/components/privacy/SettingsEditors";
import { VersionsPanel } from "@/components/privacy/VersionsPanel";

export default function PrivacyCookieAdmin() {
  const [s, setS] = useState(null);
  const load = () => api.get("/platform/privacy/settings").then(({ data }) => setS(data)).catch((e) => toast.error(formatApiError(e.response?.data?.detail)));
  useEffect(() => { load(); }, []);
  const save = async (patch) => {
    try {
      const { data } = await api.put("/platform/privacy/settings", { banner: s.banner, categories: s.categories, services: s.services, ...patch });
      setS(data);
      toast.success("Impostazioni salvate");
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  return (
    <div className="max-w-6xl space-y-6" data-testid="privacy-cookie-admin">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2"><Cookie className="w-6 h-6 text-[#0ABAB5]" />Privacy e Cookie</h1>
        <p className="text-slate-500 text-sm mt-1">Banner proprietario, servizi censiti, versioni dei documenti e registro consensi (conservazione {s ? Math.round(s.retention_days / 30) : 24} mesi).</p>
      </div>
      <Tabs defaultValue="stats">
        <TabsList className="flex-wrap h-auto">
          <TabsTrigger value="stats" data-testid="privacy-tab-stats">Statistiche</TabsTrigger>
          <TabsTrigger value="registry" data-testid="privacy-tab-registry">Registro consensi</TabsTrigger>
          <TabsTrigger value="banner" data-testid="privacy-tab-banner">Banner e categorie</TabsTrigger>
          <TabsTrigger value="services" data-testid="privacy-tab-services">Servizi e cookie</TabsTrigger>
          <TabsTrigger value="versions" data-testid="privacy-tab-versions">Versioni documenti</TabsTrigger>
        </TabsList>
        <TabsContent value="stats"><ConsentStats /></TabsContent>
        <TabsContent value="registry"><ConsentRegistry /></TabsContent>
        <TabsContent value="banner">{s && <BannerEditor s={s} onSave={save} />}</TabsContent>
        <TabsContent value="services">{s && <ServicesEditor s={s} onSave={save} />}</TabsContent>
        <TabsContent value="versions">{s && <VersionsPanel s={s} onPublished={load} />}</TabsContent>
      </Tabs>
    </div>
  );
}
