import { useSyncExternalStore, useCallback } from "react";
import api from "@/lib/api";

// Store globale condiviso di Staff/Volontari e Anagrafiche: un'UNICA sorgente dati per TUTTI
// i selettori (Staff, Team, Team Leader, Turni, Pipeline, ...). Qualsiasi create/update/delete
// persona, assegnazione/rimozione ruolo evento o Team chiama invalidatePeople() per rifare il
// fetch e aggiornare in tempo reale ogni dropdown, senza reload della pagina.
let state = { staff: [], persons: [], loaded: false, loading: false };
const listeners = new Set();
const emit = () => listeners.forEach((l) => l());
const setState = (patch) => { state = { ...state, ...patch }; emit(); };

let inflight = null;
export async function fetchPeople() {
  if (inflight) return inflight;
  setState({ loading: true });
  inflight = Promise.all([api.get("/staff"), api.get("/persons-enriched")])
    .then(([s, p]) => { setState({ staff: s.data, persons: p.data, loaded: true, loading: false }); return state; })
    .catch((e) => { setState({ loading: false }); throw e; })
    .finally(() => { inflight = null; });
  return inflight;
}

// Invalida e rifà il fetch: tutti i selettori Staff/Volontari si aggiornano.
export function invalidatePeople() { return fetchPeople(); }

function subscribe(cb) {
  listeners.add(cb);
  if (!state.loaded && !state.loading) fetchPeople();
  return () => listeners.delete(cb);
}
function getSnapshot() { return state; }

export function usePeople() {
  const s = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  const reload = useCallback(() => fetchPeople(), []);
  return { staff: s.staff, persons: s.persons, loading: s.loading, loaded: s.loaded, reload };
}
