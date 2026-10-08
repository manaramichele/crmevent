// Regola CRMEvent: persone sempre mostrate come "Cognome Nome" e ordinate per cognome (A–Z). Solo presentazione.
export const personName = (p, fallback = "") =>
  (p ? (`${p.cognome || ""} ${p.nome || ""}`.trim() || p.name || p.email || fallback) : fallback);

export const comparePersons = (a, b) => personName(a).localeCompare(personName(b), "it", { sensitivity: "base" });

export const sortPersons = (list = []) => [...list].sort(comparePersons);

export const personOptions = (list = []) => sortPersons(list).map((p) => ({ value: p.id, label: personName(p) }));
