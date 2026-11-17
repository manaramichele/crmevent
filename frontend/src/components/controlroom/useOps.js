import { useCallback, useEffect, useRef, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";

// Stato Control Room: caricamento completo + controllo revisione ogni 5 s (aggiornamenti senza ricaricare la pagina).
export function useOps(eid) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [offline, setOffline] = useState(false);
  const rev = useRef(0);
  const base = `/controlroom/events/${eid}/ops`;
  const load = useCallback(async () => {
    try {
      const { data: d } = await api.get(base);
      rev.current = d.rev; setData(d); setOffline(false); setError(null);
    } catch (e) {
      if (!e.response) setOffline(true);
      else setError(formatApiError(e.response.data?.detail));
    }
  }, [base]);
  useEffect(() => {
    setData(null); load();
    const t = setInterval(async () => {
      try {
        const { data: d } = await api.get(`${base}/rev`, { timeout: 8000 });
        setOffline(false);
        if (d.rev !== rev.current) load();
      } catch (e) { if (!e.response) setOffline(true); }
    }, 5000);
    const on = () => load();
    window.addEventListener("online", on);
    return () => { clearInterval(t); window.removeEventListener("online", on); };
  }, [base, load]);
  const call = useCallback(async (method, path, body, ok) => {
    try {
      const { data: d } = await api[method](`${base}${path}`, body);
      if (ok) toast.success(ok);
      await load();
      return d || true;
    } catch (e) {
      if (!e.response) setOffline(true);
      toast.error(formatApiError(e.response?.data?.detail) || "Operazione non riuscita");
      if (e.response?.status === 409) load();
      return null;
    }
  }, [base, load]);
  return { data, error, offline, load, call, base };
}
