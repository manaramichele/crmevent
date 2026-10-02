import { useSyncExternalStore, useCallback } from "react";
import api from "@/lib/api";

// Store globale condiviso dell'elenco Team: un'unica sorgente dati per TUTTI i selettori Team.
// Qualsiasi creazione/modifica/eliminazione di un Team chiama invalidateTeams() per
// rifare il fetch e aggiornare in tempo reale ogni dropdown, senza reload della pagina.
let state = { items: [], loaded: false, loading: false };
const listeners = new Set();
const emit = () => listeners.forEach((l) => l());
const setState = (patch) => { state = { ...state, ...patch }; emit(); };

let inflight = null;
export async function fetchTeams() {
  if (inflight) return inflight;
  setState({ loading: true });
  inflight = api.get("/teams")
    .then(({ data }) => { setState({ items: data, loaded: true, loading: false }); return data; })
    .catch((e) => { setState({ loading: false }); throw e; })
    .finally(() => { inflight = null; });
  return inflight;
}

// Invalida e rifà il fetch: tutti i selettori Team si aggiornano.
export function invalidateTeams() { return fetchTeams(); }

function subscribe(cb) {
  listeners.add(cb);
  if (!state.loaded && !state.loading) fetchTeams();
  return () => listeners.delete(cb);
}
function getSnapshot() { return state; }

export function useTeams() {
  const s = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  const reload = useCallback(() => fetchTeams(), []);
  return { teams: s.items, loading: s.loading, loaded: s.loaded, reload };
}
