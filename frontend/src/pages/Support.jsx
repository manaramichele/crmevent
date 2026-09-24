import { useState, useEffect, useCallback } from "react";
import api, { formatApiError } from "@/lib/api";
import { EntityManager, StatusBadge, PageHeader, useCollection } from "@/components/crm";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line,
} from "recharts";
import { MessageSquare, BookOpen, HelpCircle, Lightbulb, TrendingUp, Sparkles, BookPlus, ThumbsDown, AlertCircle } from "lucide-react";
import { toast } from "sonner";

const CATS = ["eventi", "persone", "aziende", "sponsor", "partner", "fornitori", "staff", "volontari", "team", "turni", "attivita", "documenti", "briefing", "impostazioni", "account", "altro"];
const catOpts = CATS.map((c) => ({ value: c, label: c.charAt(0).toUpperCase() + c.slice(1) }));
const statoOpts = [{ value: "bozza", label: "Bozza" }, { value: "pubblicato", label: "Pubblicato" }, { value: "archiviato", label: "Archiviato" }];
const frStati = [{ value: "nuova", label: "Nuova" }, { value: "da_valutare", label: "Da valutare" }, { value: "pianificata", label: "Pianificata" }, { value: "in_sviluppo", label: "In sviluppo" }, { value: "completata", label: "Completata" }, { value: "scartata", label: "Scartata" }];
const STATO_COLOR = { pubblicato: "green", bozza: "orange", archiviato: "gray", nuova: "blue", da_valutare: "orange", pianificata: "tiffany", in_sviluppo: "tiffany", completata: "green", scartata: "red" };

function Kpi({ icon: Icon, label, value, color = "tiffany" }) {
  const ring = { tiffany: "text-tiffany-active bg-tiffany-light", green: "text-emerald-600 bg-emerald-50", red: "text-red-500 bg-red-50", blue: "text-sky-600 bg-sky-50", orange: "text-amber-600 bg-amber-50" }[color];
  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-4">
      <div className="flex items-center justify-between"><span className="text-xs font-medium uppercase text-slate-500">{label}</span><span className={`w-8 h-8 rounded-lg flex items-center justify-center ${ring}`}><Icon className="w-4 h-4" /></span></div>
      <div className="mt-2 text-2xl font-bold text-slate-900 font-display">{value}</div>
    </div>
  );
}

// ---------- Conversazioni ----------
function Conversazioni() {
  const [convs, setConvs] = useState([]);
  const [filters, setFilters] = useState({ category: "", feedback: "", resolved: "", q: "" });
  const [detail, setDetail] = useState(null);

  const load = useCallback(async () => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => { if (v) params.append(k, v); });
    try { const { data } = await api.get(`/support/conversations?${params.toString()}`); setConvs(data); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  }, [filters]);
  useEffect(() => { load(); }, [load]);

  const openDetail = async (c) => {
    try { const { data } = await api.get(`/support/conversations/${c.id}`); setDetail(data); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const resolve = async (c, val) => {
    try { await api.put(`/support/conversations/${c.id}/resolve`, { resolved: val }); toast.success(val ? "Segnata come risolta" : "Riaperta"); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  return (
    <div>
      <div className="flex flex-wrap gap-2 mb-4">
        <Input placeholder="Cerca nel testo..." value={filters.q} onChange={(e) => setFilters((f) => ({ ...f, q: e.target.value }))} className="w-full sm:w-56" data-testid="conv-search" />
        <Select value={filters.category || "all"} onValueChange={(v) => setFilters((f) => ({ ...f, category: v === "all" ? "" : v }))}><SelectTrigger className="w-40" data-testid="conv-filter-cat"><SelectValue placeholder="Categoria" /></SelectTrigger><SelectContent><SelectItem value="all">Tutte le categorie</SelectItem>{catOpts.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}</SelectContent></Select>
        <Select value={filters.feedback || "all"} onValueChange={(v) => setFilters((f) => ({ ...f, feedback: v === "all" ? "" : v }))}><SelectTrigger className="w-36"><SelectValue placeholder="Feedback" /></SelectTrigger><SelectContent><SelectItem value="all">Tutti</SelectItem><SelectItem value="up">👍 Utile</SelectItem><SelectItem value="down">👎 Non utile</SelectItem></SelectContent></Select>
        <Select value={filters.resolved || "all"} onValueChange={(v) => setFilters((f) => ({ ...f, resolved: v === "all" ? "" : v }))}><SelectTrigger className="w-36"><SelectValue placeholder="Stato" /></SelectTrigger><SelectContent><SelectItem value="all">Tutte</SelectItem><SelectItem value="false">Non risolte</SelectItem><SelectItem value="true">Risolte</SelectItem></SelectContent></Select>
      </div>
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr className="border-b border-slate-200 bg-slate-50/70">{["Utente", "Domanda", "Categoria", "Sezione", "Stato", "Data"].map((h) => <th key={h} className="text-left font-semibold text-slate-600 px-4 py-3">{h}</th>)}</tr></thead>
          <tbody>
            {convs.length === 0 ? <tr><td colSpan={6} className="px-4 py-10 text-center text-slate-400">Nessuna conversazione.</td></tr>
              : convs.map((c) => (
                <tr key={c.id} className="border-b border-slate-100 hover:bg-slate-50/80 cursor-pointer" onClick={() => openDetail(c)} data-testid={`conv-row-${c.id}`}>
                  <td className="px-4 py-3 text-slate-700">{c.user_email || "—"}</td>
                  <td className="px-4 py-3 text-slate-800 max-w-xs truncate">{c.last_question || "—"}</td>
                  <td className="px-4 py-3">{c.category ? <StatusBadge color="tiffany">{c.category}</StatusBadge> : "—"}</td>
                  <td className="px-4 py-3 text-slate-500">{c.page_context || "—"}</td>
                  <td className="px-4 py-3">{c.stato === "risolta" ? <StatusBadge color="green">Risolta</StatusBadge> : c.stato === "ticket" ? <StatusBadge color="orange">Ticket</StatusBadge> : <StatusBadge color="gray">Aperta</StatusBadge>}</td>
                  <td className="px-4 py-3 text-slate-400 text-xs">{(c.created_at || "").slice(0, 10)}</td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      <Dialog open={!!detail} onOpenChange={(o) => !o && setDetail(null)}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto" data-testid="conv-detail">
          <DialogHeader><DialogTitle className="font-display">Conversazione</DialogTitle><DialogDescription>{detail?.conversation?.user_email} · {detail?.conversation?.page_context || "—"}</DialogDescription></DialogHeader>
          <div className="space-y-3 py-2">
            {detail?.messages?.map((m) => (
              <div key={m.id} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm whitespace-pre-wrap ${m.role === "user" ? "bg-tiffany text-slate-900" : "bg-slate-100 text-slate-700"}`}>
                  {m.content}
                  {m.role === "assistant" && (
                    <div className="mt-1.5 flex items-center gap-2 text-xs text-slate-400">
                      {m.answered === false && <StatusBadge color="red">Senza risposta</StatusBadge>}
                      {m.feedback === "up" && <StatusBadge color="green">👍</StatusBadge>}
                      {m.feedback === "down" && <StatusBadge color="red">👎</StatusBadge>}
                      {m.category && <span>{m.category}</span>}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
          <DialogFooter>
            {detail?.conversation?.stato !== "risolta"
              ? <Button variant="outline" onClick={() => { resolve(detail.conversation, true); setDetail(null); }} data-testid="conv-resolve">Segna come risolta</Button>
              : <Button variant="outline" onClick={() => { resolve(detail.conversation, false); setDetail(null); }}>Riapri</Button>}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ---------- Insights ----------
function Insights() {
  const [d, setD] = useState(null);
  const [kbForm, setKbForm] = useState(null);
  const [saving, setSaving] = useState(false);
  const load = useCallback(async () => { try { const { data } = await api.get("/support/insights"); setD(data); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } }, []);
  useEffect(() => { load(); }, [load]);

  const startKB = (question, answer = "") => setKbForm({ titolo: question.slice(0, 80), categoria: "altro", domanda: question, risposta: answer, parole_chiave: "", stato: "bozza" });
  const genFaq = async (question) => {
    try { const { data } = await api.post("/support/faq/generate", { question }); setKbForm({ titolo: data.domanda?.slice(0, 80) || question, categoria: data.categoria, domanda: data.domanda, risposta: data.risposta, parole_chiave: (data.parole_chiave || []).join(", "), stato: "bozza", _faq: true }); toast.success("Bozza FAQ generata dall'AI"); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const saveKB = async () => {
    setSaving(true);
    try {
      const endpoint = kbForm._faq ? "/support-faq" : "/support-kb";
      const payload = kbForm._faq
        ? { domanda: kbForm.domanda, risposta: kbForm.risposta, categoria: kbForm.categoria, parole_chiave: kbForm.parole_chiave, stato: kbForm.stato, suggested: true }
        : { titolo: kbForm.titolo, categoria: kbForm.categoria, domanda: kbForm.domanda, risposta: kbForm.risposta, parole_chiave: kbForm.parole_chiave, stato: kbForm.stato };
      await api.post(endpoint, payload);
      toast.success(kbForm._faq ? "FAQ creata (in bozza, da approvare)" : "Voce Knowledge Base creata (in bozza)");
      setKbForm(null);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setSaving(false); }
  };

  if (!d) return <div className="py-10 text-center text-slate-400">Caricamento insights...</div>;
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Kpi icon={MessageSquare} label="Domande totali" value={d.domande_totali} />
        <Kpi icon={TrendingUp} label="Utenti attivi" value={d.utenti_attivi} color="blue" />
        <Kpi icon={ThumbsDown} label="% risposte utili" value={`${d.perc_utili}%`} color="green" />
        <Kpi icon={AlertCircle} label="Senza risposta" value={d.domande_senza_risposta} color="red" />
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Kpi icon={ThumbsDown} label="% non utili" value={`${d.perc_non_utili}%`} color="orange" />
        <Kpi icon={HelpCircle} label="Ticket generati" value={d.ticket_generati} color="orange" />
        <Kpi icon={MessageSquare} label="Conversazioni" value={d.conversazioni} />
        <Kpi icon={Lightbulb} label="Categorie attive" value={d.categorie_piu_richieste.length} color="tiffany" />
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <h3 className="font-semibold text-slate-800 mb-3">Categorie più richieste</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={d.categorie_piu_richieste.slice(0, 8)}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="categoria" tick={{ fontSize: 11 }} /><YAxis allowDecimals={false} tick={{ fontSize: 11 }} /><Tooltip /><Bar dataKey="count" fill="#81D8D0" radius={[4, 4, 0, 0]} /></BarChart>
          </ResponsiveContainer>
        </div>
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <h3 className="font-semibold text-slate-800 mb-3">Trend richieste (14 gg)</h3>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={d.trend}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="data" tick={{ fontSize: 10 }} /><YAxis allowDecimals={false} tick={{ fontSize: 11 }} /><Tooltip /><Line type="monotone" dataKey="count" stroke="#0f766e" strokeWidth={2} dot={false} /></LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <h3 className="font-semibold text-slate-800 mb-3 flex items-center gap-2"><AlertCircle className="w-4 h-4 text-red-500" />Domande senza risposta</h3>
          <div className="space-y-2 max-h-72 overflow-y-auto">
            {d.unanswered_list.length === 0 ? <p className="text-sm text-slate-400">Nessuna.</p> : d.unanswered_list.map((u) => (
              <div key={u.message_id} className="flex items-center justify-between gap-2 border border-slate-100 rounded-lg px-3 py-2">
                <span className="text-sm text-slate-700 truncate">{u.content}</span>
                <Button size="sm" variant="outline" className="shrink-0" onClick={() => startKB(u.content)} data-testid="insights-to-kb"><BookPlus className="w-3.5 h-3.5 mr-1" />KB</Button>
              </div>
            ))}
          </div>
        </div>
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <h3 className="font-semibold text-slate-800 mb-3 flex items-center gap-2"><Lightbulb className="w-4 h-4 text-amber-500" />Domande frequenti → FAQ suggerita</h3>
          <div className="space-y-2 max-h-72 overflow-y-auto">
            {d.domande_frequenti.length === 0 ? <p className="text-sm text-slate-400">Nessuna.</p> : d.domande_frequenti.map((f, i) => (
              <div key={i} className="flex items-center justify-between gap-2 border border-slate-100 rounded-lg px-3 py-2">
                <span className="text-sm text-slate-700 truncate">{f.argomento} <span className="text-xs text-slate-400">({f.count})</span></span>
                <Button size="sm" variant="outline" className="shrink-0" onClick={() => genFaq(f.argomento)} data-testid="insights-gen-faq"><Sparkles className="w-3.5 h-3.5 mr-1" />Genera FAQ</Button>
              </div>
            ))}
          </div>
        </div>
      </div>

      {d.negative_list.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <h3 className="font-semibold text-slate-800 mb-3 flex items-center gap-2"><ThumbsDown className="w-4 h-4 text-red-500" />Risposte valutate 👎</h3>
          <div className="space-y-2 max-h-60 overflow-y-auto">
            {d.negative_list.map((n) => (
              <div key={n.message_id} className="flex items-center justify-between gap-2 border border-slate-100 rounded-lg px-3 py-2">
                <span className="text-sm text-slate-700 truncate">{n.question || n.answer}</span>
                <Button size="sm" variant="outline" className="shrink-0" onClick={() => startKB(n.question || "", n.answer)} data-testid="insights-neg-to-kb"><BookPlus className="w-3.5 h-3.5 mr-1" />KB</Button>
              </div>
            ))}
          </div>
        </div>
      )}

      <Dialog open={!!kbForm} onOpenChange={(o) => !o && setKbForm(null)}>
        <DialogContent className="max-w-lg" data-testid="insights-kb-dialog">
          <DialogHeader><DialogTitle className="font-display">{kbForm?._faq ? "Nuova FAQ (bozza)" : "Nuova voce Knowledge Base (bozza)"}</DialogTitle><DialogDescription>Verrà salvata come bozza: nessuna pubblicazione automatica.</DialogDescription></DialogHeader>
          {kbForm && (
            <div className="space-y-3 py-2">
              {!kbForm._faq && <div><Label className="text-xs">Titolo</Label><Input value={kbForm.titolo} onChange={(e) => setKbForm({ ...kbForm, titolo: e.target.value })} /></div>}
              <div><Label className="text-xs">Domanda</Label><Input value={kbForm.domanda} onChange={(e) => setKbForm({ ...kbForm, domanda: e.target.value })} data-testid="kb-domanda" /></div>
              <div><Label className="text-xs">Risposta</Label><Textarea rows={5} value={kbForm.risposta} onChange={(e) => setKbForm({ ...kbForm, risposta: e.target.value })} data-testid="kb-risposta" /></div>
              <div className="grid grid-cols-2 gap-2">
                <div><Label className="text-xs">Categoria</Label><Select value={kbForm.categoria} onValueChange={(v) => setKbForm({ ...kbForm, categoria: v })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{catOpts.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}</SelectContent></Select></div>
                <div><Label className="text-xs">Parole chiave (virgola)</Label><Input value={kbForm.parole_chiave} onChange={(e) => setKbForm({ ...kbForm, parole_chiave: e.target.value })} /></div>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setKbForm(null)}>Annulla</Button>
            <Button className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" onClick={saveKB} disabled={saving} data-testid="kb-save">{saving ? "..." : "Salva bozza"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default function Support() {
  const kbFields = [
    { name: "titolo", label: "Titolo", required: true, full: true },
    { name: "categoria", label: "Categoria", type: "select", options: catOpts },
    { name: "stato", label: "Stato", type: "select", options: statoOpts },
    { name: "domanda", label: "Domanda", full: true },
    { name: "risposta", label: "Risposta", type: "textarea", required: true, full: true },
    { name: "parole_chiave", label: "Parole chiave (separate da virgola)", full: true },
  ];
  const kbCols = [
    { key: "titolo", label: "Titolo", render: (r) => <span className="font-medium text-slate-800">{r.titolo}</span> },
    { key: "categoria", label: "Categoria", render: (r) => r.categoria ? <StatusBadge color="tiffany">{r.categoria}</StatusBadge> : "—" },
    { key: "stato", label: "Stato", render: (r) => <StatusBadge color={STATO_COLOR[r.stato] || "gray"}>{r.stato}</StatusBadge> },
    { key: "updated_at", label: "Aggiornato", render: (r) => (r.updated_at || "").slice(0, 10) },
  ];
  const faqFields = [
    { name: "domanda", label: "Domanda", required: true, full: true },
    { name: "risposta", label: "Risposta", type: "textarea", required: true, full: true },
    { name: "categoria", label: "Categoria", type: "select", options: catOpts },
    { name: "stato", label: "Stato", type: "select", options: statoOpts },
    { name: "parole_chiave", label: "Parole chiave (virgola)", full: true },
  ];
  const faqCols = [
    { key: "domanda", label: "Domanda", render: (r) => <span className="font-medium text-slate-800">{r.domanda}</span> },
    { key: "categoria", label: "Categoria", render: (r) => r.categoria ? <StatusBadge color="tiffany">{r.categoria}</StatusBadge> : "—" },
    { key: "richieste_count", label: "Richieste", render: (r) => r.richieste_count || 0 },
    { key: "suggested", label: "Origine", render: (r) => r.suggested ? <StatusBadge color="orange">AI suggerita</StatusBadge> : <StatusBadge color="gray">Manuale</StatusBadge> },
    { key: "stato", label: "Stato", render: (r) => <StatusBadge color={STATO_COLOR[r.stato] || "gray"}>{r.stato}</StatusBadge> },
  ];
  const frFields = [
    { name: "titolo", label: "Titolo", required: true, full: true },
    { name: "descrizione", label: "Descrizione", type: "textarea", full: true },
    { name: "stato", label: "Stato", type: "select", options: frStati },
  ];
  const frCols = [
    { key: "titolo", label: "Richiesta", render: (r) => <span className="font-medium text-slate-800">{r.titolo}</span> },
    { key: "utenti_count", label: "Utenti", render: (r) => r.utenti_count || 1 },
    { key: "stato", label: "Stato", render: (r) => <StatusBadge color={STATO_COLOR[r.stato] || "gray"}>{(frStati.find((s) => s.value === r.stato) || {}).label || r.stato}</StatusBadge> },
    { key: "ultima_richiesta", label: "Ultima richiesta", render: (r) => (r.ultima_richiesta || r.created_at || "").slice(0, 10) },
  ];

  return (
    <div className="animate-fade-up">
      <PageHeader title="Supporto" subtitle="Assistente AI, knowledge base e analisi delle richieste degli organizzatori" />
      <Tabs defaultValue="conversazioni">
        <TabsList className="mb-4 flex-wrap h-auto">
          <TabsTrigger value="conversazioni" data-testid="stab-conversazioni"><MessageSquare className="w-4 h-4 mr-1" />Conversazioni</TabsTrigger>
          <TabsTrigger value="kb" data-testid="stab-kb"><BookOpen className="w-4 h-4 mr-1" />Knowledge Base</TabsTrigger>
          <TabsTrigger value="faq" data-testid="stab-faq"><HelpCircle className="w-4 h-4 mr-1" />FAQ</TabsTrigger>
          <TabsTrigger value="feature" data-testid="stab-feature"><Lightbulb className="w-4 h-4 mr-1" />Richieste funzionalità</TabsTrigger>
          <TabsTrigger value="insights" data-testid="stab-insights"><TrendingUp className="w-4 h-4 mr-1" />Insights</TabsTrigger>
        </TabsList>
        <TabsContent value="conversazioni"><Conversazioni /></TabsContent>
        <TabsContent value="kb">
          <EntityManager title="Knowledge Base" subtitle="Contenuti usati dall'assistente. Solo lo stato 'Pubblicato' viene usato per rispondere." endpoint="/support-kb"
            fields={kbFields} columns={kbCols} entityLabel="voce" testid="kb" searchKeys={["titolo", "domanda", "categoria"]} filters={[{ name: "stato", label: "Stato", options: statoOpts }, { name: "categoria", label: "Categoria", options: catOpts }]} />
        </TabsContent>
        <TabsContent value="faq">
          <EntityManager title="FAQ" subtitle="Domande frequenti. Le FAQ suggerite dall'AI vanno approvate (impostando lo stato su Pubblicato)." endpoint="/support-faq"
            fields={faqFields} columns={faqCols} entityLabel="FAQ" testid="faq" searchKeys={["domanda", "categoria"]} filters={[{ name: "stato", label: "Stato", options: statoOpts }]} />
        </TabsContent>
        <TabsContent value="feature">
          <EntityManager title="Richieste funzionalità" subtitle="Funzionalità richieste dagli utenti nelle conversazioni — fonte per la roadmap" endpoint="/support-feature-requests"
            fields={frFields} columns={frCols} entityLabel="richiesta" testid="feature" searchKeys={["titolo"]} filters={[{ name: "stato", label: "Stato", options: frStati }]} />
        </TabsContent>
        <TabsContent value="insights"><Insights /></TabsContent>
      </Tabs>
    </div>
  );
}
