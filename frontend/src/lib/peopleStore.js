import { useSyncExternalStore, useCallback } from "react";
import api from "@/lib/api";

// Store globale condiviso di Staff/Volontari e Anagrafiche: un'UNICA sorgente dati per TUTTI
// i selettori (Staff, Team, Team Leader, Turni, Pipeline, ...). Qualsiasi create/update/delete
// persona, assegnazione/rimozione ruolo evento o Team chiama invalidatePeople() per rifare il
// fetch e aggiornare in tempo reale ogni dropdown, senza reload della pagina.
let state = { staff: [], persons: [], loaded: false, loading: false, org: null };
const currentOrg = () => localStorage.getItem("acting_org_id") || "";
const listeners = new Set();
const emit = () => listeners.forEach((l) => l());
const setState = (patch) => { state = { ...state, ...patch }; emit(); };

let inflight = null;
export async function fetchPeople() {
  const org = currentOrg();
  if (inflight && inflight.org === org) return inflight;
  setState({ loading: true, org });
  const p = Promise.all([api.get("/staff"), api.get("/persons-enriched")])
    .then(([s, pr]) => { if (currentOrg() === org) setState({ staff: s.data, persons: pr.data, loaded: true, loading: false }); return state; })
    .catch((e) => { if (currentOrg() === org) setState({ loading: false }); throw e; })
    .finally(() => { if (inflight === p) inflight = null; });
  p.org = org;
  inflight = p;
  return p;
}

// Invalida e rifà il fetch: tutti i selettori Staff/Volontari si aggiornano.
export function invalidatePeople() { return fetchPeople(); }

function subscribe(cb) {
  listeners.add(cb);
  if (state.org !== null && state.org !== currentOrg()) {
    state = { staff: [], persons: [], loaded: false, loading: false, org: null };
  }
  if (!state.loaded && !state.loading) fetchPeople().catch(() => {});
  return () => listeners.delete(cb);
}
const EMPTY = { staff: [], persons: [], loaded: false, loading: true, org: null };
function getSnapshot() { return state.org !== null && state.org !== currentOrg() ? EMPTY : state; }

export function usePeople() {
  const s = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  const reload = useCallback(() => fetchPeople(), []);
  return { staff: s.staff, persons: s.persons, loading: s.loading, loaded: s.loaded, reload };
}
