// Normalizzazione maiuscole anagrafiche (stessa logica di backend/text_normalize.py).
const CONNECTORS = new Set(["di", "del", "della", "dello", "dei", "degli", "delle", "da", "dal", "dalla", "dallo", "dai", "dalle", "e", "ed",
  "a", "al", "alla", "allo", "ai", "agli", "alle", "in", "nel", "nella", "nello", "nei", "nelle", "per", "con", "su",
  "sul", "sulla", "sui", "il", "lo", "la", "i", "gli", "le", "l", "d", "un", "una", "uno", "of", "the", "and",
  "dell", "nell", "all", "dall", "sull", "coll", "quell"]);
const SPLIT = /([-'\u2019])/;
const isSep = (p) => p === "-" || p === "'" || p === "\u2019";
const isUp = (c) => c !== c.toLowerCase() && c === c.toUpperCase();
const letters = (w) => [...w].filter((c) => c.toLowerCase() !== c.toUpperCase());

const cap = (p) => {
  const low = p.toLowerCase();
  if (low.length > 2 && low.startsWith("mc")) return "Mc" + low[2].toUpperCase() + low.slice(3);
  return low.charAt(0).toUpperCase() + low.slice(1);
};
const styled = (w) => {
  const l = letters(w);
  return l.length > 0 && isUp(w[0]) && l.slice(1).some(isUp) && !l.every(isUp);
};

export function personName(s) {
  if (typeof s !== "string" || !s.trim()) return s;
  return s.trim().split(/\s+/).map((w) => (styled(w) ? w : w.split(SPLIT).map((p) => (isSep(p) ? p : cap(p))).join(""))).join(" ");
}

export function businessName(s) {
  if (typeof s !== "string" || !s.trim()) return s;
  return s.trim().split(/\s+/).map((w, wi) => {
    const l = letters(w);
    if (!l.length || /\d/.test(w) || (l.length > 1 && l.every(isUp)) || styled(w)) return w;
    return w.split(SPLIT).map((p, i) => (isSep(p) || !p ? p : CONNECTORS.has(p.toLowerCase()) && !(wi === 0 && i === 0) ? p.toLowerCase() : cap(p))).join("");
  }).join(" ");
}

export const CASE_FN = { person: personName, business: businessName, place: businessName };
export const PLACE_RULES = { citta: "place", regione: "place", nazione: "place" };
export const PERSON_RULES = { nome: "person", cognome: "person", ...PLACE_RULES };
export const COMPANY_RULES = { nome: "business", ...PLACE_RULES };
