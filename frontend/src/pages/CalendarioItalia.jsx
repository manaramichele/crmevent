import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api from "@/lib/api";
import { PageHeader } from "@/components/crm";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { calApi, err } from "@/components/calendario/shared";
import { CalDashboard } from "@/components/calendario/CalDashboard";
import { EventsPanel } from "@/components/calendario/EventsPanel";
import { OrganizersPanel } from "@/components/calendario/OrganizersPanel";
import { SourcesPanel, SettingsPanel } from "@/components/calendario/SourcesPanel";

const TABS = [["dashboard", "Dashboard"], ["calendario", "Calendario nazionale"], ["organizzatori", "Organizzatori"], ["fonti", "Fonti e sincronizzazioni"],
  ["campagne", "Campagne Brevo"], ["storico", "Storico comunicazioni"], ["impostazioni", "Impostazioni"]];

const Soon = ({ id, text }) => <div className="bg-white border border-slate-200 rounded-xl p-6 text-sm text-slate-500" data-testid={`cal-soon-${id}`}>{text}</div>;

export default function CalendarioItalia() {
  const [params, setParams] = useSearchParams();
  const tab = TABS.some(([k]) => k === params.get("tab")) ? params.get("tab") : "dashboard";
  const [meta, setMeta] = useState(null);
  const loadMeta = useCallback(() => api.get(calApi("/meta")).then(({ data }) => setMeta(data)).catch(err), []);
  useEffect(() => { loadMeta(); }, [loadMeta]);
  return (
    <div data-testid="calendario-italia-page">
      <PageHeader title="Calendario Eventi Italia" subtitle="Manifestazioni di running, trail e triathlon e anagrafica unica degli organizzatori. Archivio riservato al Super Admin, separato dai dati dei clienti." />
      <Tabs value={tab} onValueChange={(v) => setParams({ tab: v }, { replace: true })}>
        <TabsList className="mb-4 flex h-auto max-w-full flex-wrap justify-start">{TABS.map(([k, l]) => <TabsTrigger key={k} value={k} data-testid={`cal-tab-${k}`}>{l}</TabsTrigger>)}</TabsList>
        {!meta ? <p className="text-sm text-slate-500">Caricamento...</p> : <>
          <TabsContent value="dashboard"><CalDashboard /></TabsContent>
          <TabsContent value="calendario"><EventsPanel meta={meta} /></TabsContent>
          <TabsContent value="organizzatori"><OrganizersPanel /></TabsContent>
          <TabsContent value="fonti"><SourcesPanel /></TabsContent>
          <TabsContent value="campagne"><Soon id="campagne" text="Fase 3: collegamento alla configurazione Brevo esistente, lista dedicata, template, simulazione dei destinatari e pianificazione a 7/10 giorni. Nessun invio è attivo." /></TabsContent>
          <TabsContent value="storico"><Soon id="storico" text="Fase 3: qui compariranno gli invii (programmati, inviati, consegne, aperture, clic, disiscrizioni). Al momento non è stata inviata alcuna comunicazione." /></TabsContent>
          <TabsContent value="impostazioni"><SettingsPanel meta={meta} onSaved={loadMeta} /></TabsContent>
        </>}
      </Tabs>
    </div>
  );
}
