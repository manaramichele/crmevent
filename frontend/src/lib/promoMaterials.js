import api from "@/lib/api";

export const fetchPublicPromo = (slug) => api.get(`/public/promo/${slug}`).then((r) => r.data);
export const fetchPublicPromoList = () => api.get("/public/promo").then((r) => r.data);
export const fmtDate = (iso) => (iso ? new Date(iso).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" }) : "—");
