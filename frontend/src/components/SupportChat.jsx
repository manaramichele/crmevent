import { useState, useRef, useEffect } from "react";
import { useLocation } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sparkles, Send, ThumbsUp, ThumbsDown, X, LifeBuoy, Check } from "lucide-react";
import { toast } from "sonner";

const CTX = {
  "/": "Dashboard", "/eventi": "Eventi", "/aziende": "Aziende", "/persone": "Persone",
  "/sponsor": "Sponsor & Partner", "/attivita": "Attività", "/followup": "Follow-up",
  "/lead": "Lead", "/impostazioni": "Impostazioni", "/supporto": "Supporto", "/profilo": "Profilo",
  "/app": "Area personale — I miei eventi",
};

export default function SupportChat({ bottomOffset = false }) {
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [convId, setConvId] = useState(null);
  const scrollRef = useRef(null);
  const pageContext = location.pathname.startsWith("/evento/") ? "Area personale — Dettaglio evento" : (CTX[location.pathname] || "CRMEvent");

  useEffect(() => { if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight; }, [msgs, busy]);

  const send = async () => {
    const question = q.trim();
    if (!question || busy) return;
    setQ("");
    setMsgs((m) => [...m, { role: "user", content: question }]);
    setBusy(true);
    try {
      const { data } = await api.post("/support/chat", { question, conversation_id: convId, page_context: pageContext });
      setConvId(data.conversation_id);
      setMsgs((m) => [...m, { role: "assistant", id: data.message_id, content: data.answer, answered: data.answered, feedback: null }]);
    } catch (e) {
      setMsgs((m) => [...m, { role: "assistant", content: "Si è verificato un errore. Riprova tra poco.", answered: false, error: true }]);
      toast.error(formatApiError(e.response?.data?.detail));
    } finally { setBusy(false); }
  };

  const feedback = async (mid, value, idx) => {
    try {
      await api.post("/support/feedback", { message_id: mid, value });
      setMsgs((m) => m.map((x, i) => i === idx ? { ...x, feedback: value } : x));
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const openTicket = async () => {
    if (!convId) return;
    try { await api.post("/support/ticket", { conversation_id: convId }); toast.success("Richiesta inviata al supporto. Ti risponderemo al più presto."); setMsgs((m) => [...m, { role: "system", content: "✅ Richiesta inviata al supporto." }]); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  return (
    <>
      {!open && (
        <button onClick={() => setOpen(true)} data-testid="support-fab" aria-label="Apri assistente CRMEvent"
          className={`fixed ${bottomOffset ? "bottom-20" : "bottom-5"} right-5 z-50 w-12 h-12 sm:w-[52px] sm:h-[52px] rounded-full bg-slate-900 text-white shadow-xl hover:bg-slate-800 transition-all hover:scale-105 active:scale-95 flex items-center justify-center`}>
          <Sparkles className="w-6 h-6 text-tiffany" />
        </button>
      )}
      {open && (
        <div className="fixed z-50 inset-x-0 bottom-0 sm:inset-x-auto sm:right-5 sm:bottom-5 sm:w-[400px] h-[85vh] sm:h-[600px] sm:max-h-[85vh] bg-white sm:rounded-2xl rounded-t-2xl shadow-2xl border border-slate-200 flex flex-col overflow-hidden animate-fade-up" data-testid="support-panel">
          <div className="bg-slate-900 text-white px-4 py-3 flex items-center gap-3">
            <span className="w-9 h-9 rounded-full bg-tiffany flex items-center justify-center shrink-0"><Sparkles className="w-5 h-5 text-slate-900" /></span>
            <div className="flex-1 min-w-0">
              <div className="font-semibold text-sm">Assistente CRMEvent</div>
              <div className="text-xs text-slate-300">Come posso aiutarti?</div>
            </div>
            <button onClick={() => setOpen(false)} data-testid="support-close" className="w-8 h-8 rounded-lg hover:bg-white/10 flex items-center justify-center"><X className="w-5 h-5" /></button>
          </div>

          <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3 bg-slate-50/60">
            {msgs.length === 0 && (
              <div className="text-sm text-slate-500 space-y-3">
                <p>Ciao! Sono l'assistente di <span className="font-semibold text-slate-700">CRMEvent</span>. Posso aiutarti sull'utilizzo della piattaforma.</p>
                <div className="space-y-1.5">
                  {["Come inserisco uno sponsor?", "Come assegno un volontario a un evento?", "Come creo un turno?"].map((s) => (
                    <button key={s} onClick={() => setQ(s)} className="block w-full text-left text-xs bg-white border border-slate-200 rounded-lg px-3 py-2 hover:border-tiffany hover:bg-tiffany-light/40 transition-colors" data-testid="support-suggestion">{s}</button>
                  ))}
                </div>
              </div>
            )}
            {msgs.map((m, i) => (
              m.role === "system" ? (
                <div key={i} className="text-center text-xs text-emerald-600 font-medium py-1">{m.content}</div>
              ) : (
                <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                  <div className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm whitespace-pre-wrap ${m.role === "user" ? "bg-tiffany text-slate-900 rounded-br-sm" : "bg-white border border-slate-200 text-slate-700 rounded-bl-sm"}`} data-testid={m.role === "assistant" ? "support-answer" : undefined}>
                    {m.content}
                    {m.role === "assistant" && !m.error && (
                      <div className="mt-2 pt-2 border-t border-slate-100 flex items-center gap-3">
                        {m.id && (
                          <div className="flex items-center gap-1.5">
                            <button disabled={!!m.feedback} onClick={() => feedback(m.id, "up", i)} data-testid="support-thumbup" className={`flex items-center gap-1 text-xs ${m.feedback === "up" ? "text-emerald-600 font-semibold" : "text-slate-400 hover:text-emerald-600"}`}><ThumbsUp className="w-3.5 h-3.5" />Utile</button>
                            <button disabled={!!m.feedback} onClick={() => feedback(m.id, "down", i)} data-testid="support-thumbdown" className={`flex items-center gap-1 text-xs ${m.feedback === "down" ? "text-red-500 font-semibold" : "text-slate-400 hover:text-red-500"}`}><ThumbsDown className="w-3.5 h-3.5" />Non utile</button>
                          </div>
                        )}
                        {m.feedback && <span className="text-xs text-slate-400 flex items-center gap-1"><Check className="w-3 h-3" />Grazie</span>}
                      </div>
                    )}
                    {m.role === "assistant" && m.answered === false && !m.error && (
                      <button onClick={openTicket} data-testid="support-ticket-btn" className="mt-2 w-full flex items-center justify-center gap-1.5 text-xs font-semibold bg-slate-900 text-white rounded-lg px-3 py-2 hover:bg-slate-800 transition-colors"><LifeBuoy className="w-3.5 h-3.5" />Invia richiesta al supporto</button>
                    )}
                  </div>
                </div>
              )
            ))}
            {busy && <div className="flex justify-start"><div className="bg-white border border-slate-200 rounded-2xl rounded-bl-sm px-3.5 py-2.5"><span className="flex gap-1"><span className="w-2 h-2 bg-slate-300 rounded-full animate-bounce" /><span className="w-2 h-2 bg-slate-300 rounded-full animate-bounce" style={{ animationDelay: "0.15s" }} /><span className="w-2 h-2 bg-slate-300 rounded-full animate-bounce" style={{ animationDelay: "0.3s" }} /></span></div></div>}
          </div>

          <div className="p-3 border-t border-slate-200 bg-white flex items-end gap-2">
            <Input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
              placeholder="Scrivi la tua domanda..." data-testid="support-input" className="flex-1" />
            <Button onClick={send} disabled={busy || !q.trim()} size="icon" className="bg-tiffany hover:bg-tiffany-hover text-slate-900 shrink-0" data-testid="support-send"><Send className="w-4 h-4" /></Button>
          </div>
        </div>
      )}
    </>
  );
}
