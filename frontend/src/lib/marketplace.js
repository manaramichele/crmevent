import { Globe, MonitorSmartphone, Mail, MessageCircle, FileSignature, Warehouse, Package, Sparkles, Megaphone, Camera, Ticket, ShoppingBag } from "lucide-react";

export const MKT_ICONS = { Globe, MonitorSmartphone, Mail, MessageCircle, FileSignature, Warehouse, Package, Sparkles, Megaphone, Camera, Ticket, ShoppingBag };
export const PRICE_TYPES = { one_time: "Una tantum", monthly: "Abbonamento mensile", yearly: "Abbonamento annuale", usage: "A consumo" };
export const STATUS = { coming_soon: "Prossimamente", available: "Disponibile", active: "Attivo", suspended: "Sospeso", past_due: "Pagamento in sospeso", canceled: "Annullato", pending: "In attesa di pagamento" };
export const priceLabel = (s) => {
  if (!s.price) return "Prezzo da definire";
  const p = `€${Number(s.price).toLocaleString("it-IT", { minimumFractionDigits: 2 })}`;
  return { one_time: p, monthly: `${p}/mese`, yearly: `${p}/anno`, usage: `${p}${s.usage_unit ? ` / ${s.usage_unit}` : " a consumo"}` }[s.price_type] || p;
};

export function ServiceIcon({ s, className = "w-12 h-12" }) {
  if (s.image) return <img src={s.image} alt="" className={`${className} rounded-xl object-cover`} />;
  const I = MKT_ICONS[s.icon] || Package;
  return <div className={`${className} rounded-xl bg-[#0ABAB5]/12 flex items-center justify-center shrink-0`} style={{ background: "rgba(10,186,181,0.12)" }}><I className="w-6 h-6 text-[#088F8A]" /></div>;
}
