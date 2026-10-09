import axios from "axios";

export const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const api = axios.create({ baseURL: API, withCredentials: true });
export default api;

export const eur = (cents) => ((cents || 0) / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
export const eurN = (n) => (n || 0).toLocaleString("it-IT", { style: "currency", currency: "EUR" });

export function formatApiError(detail) {
  if (detail == null) return "Si è verificato un errore. Riprova.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e))).join(" ");
  if (typeof detail.message === "string") return detail.message;
  return String(detail);
}
