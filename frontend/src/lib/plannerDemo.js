import api from "@/lib/api";

const KEY = "crmevent_planner_demo";
const TTL = 7 * 24 * 3600 * 1000;

export const trackDemo = (evento, valore) => api.post("/public/planner-demo/track", { evento, valore: valore || null }).catch(() => {});

export function loadDemoProject() {
  try {
    const d = JSON.parse(localStorage.getItem(KEY));
    return d && Date.now() - d.ts < TTL && d.features?.length ? d : null;
  } catch { return null; }
}

export const saveDemoProject = (d) => { try { localStorage.setItem(KEY, JSON.stringify({ ...d, ts: Date.now() })); } catch { /* storage pieno o bloccato */ } };
export const clearDemoProject = () => { try { localStorage.removeItem(KEY); } catch { /* ignora */ } };
