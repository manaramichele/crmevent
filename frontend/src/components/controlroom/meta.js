import { Users, CupSoda, Droplets, Ambulance, Cross, Shield, BadgeCheck, LifeBuoy, TrafficCone, Flag, TriangleAlert, Flame, Ban, MapPin, Car, Bike, Siren, Truck, HeartPulse, UserRound } from "lucide-react";

export const ICONS = { Users, CupSoda, Droplets, Ambulance, Cross, Shield, BadgeCheck, LifeBuoy, TrafficCone, Flag, TriangleAlert, Flame, Ban, MapPin, Car, Bike, Siren, Truck, HeartPulse };
export const ICON_NAMES = Object.keys(ICONS);

export const VEHICLE_STYLE = {
  ambulanza: ["Ambulance", "#DC2626"], automedica: ["HeartPulse", "#BE123C"], moto_soccorso: ["Bike", "#E11D48"], auto_org: ["Car", "#0F766E"],
  moto_org: ["Bike", "#0D9488"], protezione_civile: ["LifeBuoy", "#EA580C"], polizia: ["Shield", "#1D4ED8"], polizia_locale: ["BadgeCheck", "#2563EB"], altro: ["Truck", "#475569"],
};
export const resourceIcon = (r) => (r.kind === "mezzo" ? ICONS[(VEHICLE_STYLE[r.tipologia] || VEHICLE_STYLE.altro)[0]] : r.kind === "squadra" ? Users : UserRound);

export const EVENT_STATES = [["preparazione", "IN PREPARAZIONE", "bg-slate-100 text-slate-700"], ["in_corso", "IN CORSO", "bg-emerald-100 text-emerald-800"],
  ["sospeso", "SOSPESO", "bg-amber-100 text-amber-800"], ["terminato", "TERMINATO", "bg-slate-800 text-white"]];
export const RES_STATES = [["disponibile", "DISPONIBILE", "bg-emerald-100 text-emerald-800"], ["impegnato", "IMPEGNATO", "bg-amber-100 text-amber-800"],
  ["fuori_servizio", "FUORI SERVIZIO", "bg-slate-200 text-slate-700"], ["non_raggiungibile", "NON RAGGIUNGIBILE", "bg-red-100 text-red-700"]];
export const PRESIDIO = { non_attiva: ["NON ATTIVA", "bg-slate-100 text-slate-500"], in_attesa: ["IN ATTESA", "bg-amber-50 text-amber-700"],
  presidiata: ["PRESIDIATA", "bg-emerald-100 text-emerald-800"], parziale: ["PARZIALMENTE PRESIDIATA", "bg-orange-100 text-orange-700"], non_presidiata: ["NON PRESIDIATA", "bg-red-100 text-red-700"] };
export const PERSON_TYPES = ["Volontario", "Staff", "Sanitario", "Forze dell'ordine", "Altro"];
export const KINDS = [["persona", "Persona"], ["mezzo", "Mezzo"], ["squadra", "Squadra"]];

export const label = (list, k) => (list.find((x) => x[0] === k) || [k, k, "bg-slate-100 text-slate-600"]);
export const posOf = (r, posts) => {
  if (r.lng != null && r.lat != null) return [r.lng, r.lat];
  const p = posts.find((x) => x.id === r.post_id);
  return p && p.lng != null ? [p.lng, p.lat] : null;
};
export const nameOf = (r) => r.nome || r.codice || "Risorsa";
