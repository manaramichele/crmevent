import { useEffect, useRef, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { MapPin, Search } from "lucide-react";
import { toast } from "sonner";

let statusCache = null;
const newSession = () => (crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2));

export default function AddressAutocomplete({ onSelect }) {
  const [enabled, setEnabled] = useState(statusCache);
  const [q, setQ] = useState("");
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const session = useRef(newSession());
  useEffect(() => {
    if (statusCache === null) { api.get("/anagrafica/places/status").then(({ data }) => { statusCache = data.enabled; setEnabled(data.enabled); }).catch(() => setEnabled(false)); }
  }, []);
  useEffect(() => {
    if (!enabled || q.trim().length < 3) { setItems([]); return undefined; }
    const t = setTimeout(async () => {
      try { const { data } = await api.get("/anagrafica/places/autocomplete", { params: { q, session: session.current } }); setItems(data.suggestions); setOpen(true); }
      catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    }, 300);
    return () => clearTimeout(t);
  }, [q, enabled]);
  const choose = async (s) => {
    setOpen(false); setQ(s.text);
    try { const { data } = await api.get(`/anagrafica/places/${s.place_id}`, { params: { session: session.current } }); onSelect(data); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    session.current = newSession();
  };
  if (enabled === false) return <p className="sm:col-span-2 text-xs text-slate-400" data-testid="address-search-disabled">Ricerca indirizzo Google non attiva: compila i campi manualmente.</p>;
  if (!enabled) return null;
  return (
    <div className="sm:col-span-2 relative" data-testid="address-search">
      <label className="text-xs text-slate-500">Cerca indirizzo (Google Maps)</label>
      <div className="relative mt-1">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
        <Input value={q} onChange={(e) => setQ(e.target.value)} onFocus={() => items.length && setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 200)}
          placeholder="Via, numero civico, città…" className="pl-9 text-sm" data-testid="address-search-input" autoComplete="off" />
      </div>
      {open && items.length > 0 && (
        <ul className="absolute z-50 mt-1 w-full rounded-md border border-slate-200 bg-white shadow-lg max-h-60 overflow-y-auto" data-testid="address-suggestions">
          {items.map((s, i) => (
            <li key={s.place_id}><button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => choose(s)} className="w-full text-left px-3 py-2 text-sm hover:bg-slate-50 flex items-start gap-2" data-testid={`address-suggestion-${i}`}>
              <MapPin className="w-4 h-4 mt-0.5 text-slate-400 shrink-0" />{s.text}</button></li>
          ))}
        </ul>
      )}
      <p className="text-[11px] text-slate-400 mt-1">Dopo la scelta i campi sotto si compilano da soli e restano modificabili.</p>
    </div>
  );
}
