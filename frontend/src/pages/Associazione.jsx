import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import api from "@/lib/api";
import { PageHeader } from "@/components/crm";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { AsdDashboard } from "@/components/asd/AsdDashboard";
import { AsdSoci } from "@/components/asd/AsdSoci";
import { AsdTesseramenti } from "@/components/asd/AsdTesseramenti";
import { AsdQuote } from "@/components/asd/AsdQuote";
import { AsdCertificati } from "@/components/asd/AsdCertificati";
import { AsdScadenze } from "@/components/asd/AsdScadenze";

const TABS = [["dashboard", "Dashboard Associazione"], ["soci", "Soci e Tesserati"], ["tesseramenti", "Tesseramenti"], ["quote", "Quote e Pagamenti"], ["certificati", "Certificati Medici"], ["scadenze", "Scadenze"]];

export default function Associazione() {
  const [params, setParams] = useSearchParams();
  const tab = TABS.some(([k]) => k === params.get("tab")) ? params.get("tab") : "dashboard";
  const [status, setStatus] = useState(null);
  const [soci, setSoci] = useState([]);
  const [rk, setRk] = useState(0);
  const loadSoci = useCallback(() => api.get("/asd/soci").then(({ data }) => setSoci(data)).catch(() => setSoci([])), []);
  useEffect(() => { api.get("/asd/status").then(({ data }) => setStatus(data)).catch(() => setStatus({ active: false })); }, []);
  useEffect(() => { if (status?.active) { loadSoci(); } }, [status?.active, loadSoci, rk]);
  const go = (k) => setParams({ tab: k });
  const changed = () => setRk((x) => x + 1);

  if (!status) return <p className="text-sm text-slate-500" data-testid="asd-loading">Caricamento…</p>;
  if (!status.active) return (
    <div className="max-w-xl" data-testid="asd-inactive">
      <PageHeader title="Gestione Associazione Sportiva" />
      <p className="text-sm text-slate-600">Il modulo non è attivo per questa organizzazione oppure il tuo profilo non è abilitato. È riservato agli Admin e agli utenti dell'organizzazione che hanno attivato il servizio.</p>
      <Link to="/marketplace" className="inline-flex mt-4 h-10 items-center px-5 rounded-full bg-[#0ABAB5] text-slate-900 font-semibold hover:bg-[#09A8A3]" data-testid="asd-go-marketplace">Vai al Marketplace</Link>
    </div>
  );
  const props = { status, soci, onChanged: changed };
  return (
    <div data-testid="asd-page">
      <PageHeader title="Gestione Associazione Sportiva" subtitle="Soci, tesseramenti, quote, certificati medici e scadenze della tua associazione." />
      <Tabs value={tab} onValueChange={go}>
        <div className="overflow-x-auto -mx-1 px-1 mb-4"><TabsList className="w-max">{TABS.map(([k, l]) => <TabsTrigger key={k} value={k} data-testid={`asd-tab-${k}`}>{l}</TabsTrigger>)}</TabsList></div>
        <TabsContent value="dashboard"><AsdDashboard go={go} refreshKey={rk} /></TabsContent>
        <TabsContent value="soci"><AsdSoci status={status} onChanged={changed} /></TabsContent>
        <TabsContent value="tesseramenti"><AsdTesseramenti {...props} /></TabsContent>
        <TabsContent value="quote"><AsdQuote {...props} /></TabsContent>
        <TabsContent value="certificati"><AsdCertificati {...props} /></TabsContent>
        <TabsContent value="scadenze"><AsdScadenze status={status} onChanged={changed} /></TabsContent>
      </Tabs>
    </div>
  );
}
