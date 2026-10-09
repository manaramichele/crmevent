import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const api = axios.create({
  baseURL: API,
  withCredentials: true,
});

// Super Admin "active organization" context — sent only when explicitly selected.
// Backend validates it and ignores it for non-superadmin accounts.
api.interceptors.request.use((config) => {
  const org = localStorage.getItem("acting_org_id");
  if (org) config.headers["X-Org-Id"] = org;
  return config;
});

export function formatApiError(detail) {
  if (detail == null) return "Si è verificato un errore. Riprova.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e))).join(" ");
  if (detail && typeof detail.message === "string") return detail.message;
  if (detail && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}

// Evento non operativo (preparazione/sospeso): segnala alla UI per mostrare il prompt di attivazione.
api.interceptors.response.use(
  (r) => r,
  (error) => {
    const d = error?.response?.data?.detail;
    if (error?.response?.status === 403 && d && typeof d === "object" && d.code === "event_not_operational") {
      window.dispatchEvent(new CustomEvent("crmevent:event-not-operational", { detail: d }));
    }
    if (error?.response?.status === 403 && d && typeof d === "object" && d.code === "plan_limit") {
      window.dispatchEvent(new CustomEvent("crmevent:plan-limit", { detail: d }));
    }
    return Promise.reject(error);
  }
);

export default api;
