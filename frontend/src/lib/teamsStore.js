import { useSyncExternalStore, useCallback } from "react";
import api from "@/lib/api";

// Store globale condiviso dell'elenco Team: un'unica sorgente dati per TUTTI i selettori Team.
// Qualsiasi creazione/modifica/eliminazione di un Team chiama invalidateTeams() per
// rifare il fetch e aggiornare in tempo reale ogni dropdown, senza reload della pagina.
let state = { items: [], loaded: false, loading: false, org: null };
const currentOrg = () => localStorage.getItem("acting_org_id") || "";
const listeners = new Set();
const emit = () => listeners.forEach((l) => l());
const setState = (patch) => { state = { ...state, ...patch }; emit(); };

let inflight = null;
export async function fetchTeams() {
  const org = currentOrg();
  if (inflight && inflight.org === org) return inflight;
  setState({ loading: true, org });
  const p = api.get("/teams")
    .then(({ data }) => { if (currentOrg() === org) setState({ items: data, loaded: true, loading: false }); return data; })
    .catch((e) => { if (currentOrg() === org) setState({ loading: false }); throw e; })
    .finally(() => { if (inflight === p) inflight = null; });
  p.org = org;
  inflight = p;
  return p;
}

// Invalida e rifà il fetch: tutti i selettori Team si aggiornano.
export function invalidateTeams() { return fetchTeams(); }

function subscribe(cb) {
  listeners.add(cb);
  if (state.org !== null && state.org !== currentOrg()) {
    state = { items: [], loaded: false, loading: false, org: null };
  }
  if (!state.loaded && !state.loading) fetchTeams().catch(() => {});
  return () => listeners.delete(cb);
}
const EMPTY = { items: [], loaded: false, loading: true, org: null };
function getSnapshot() { return state.org !== null && state.org !== currentOrg() ? EMPTY : state; }

export function useTeams() {
  const s = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  const reload = useCallback(() => fetchTeams(), []);
  return { teams: s.items, loading: s.loading, loaded: s.loaded, reload };
}
