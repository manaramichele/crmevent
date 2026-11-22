const coll = new Intl.Collator("it", { sensitivity: "base", numeric: true });

export const cmpIt = (a, b) => coll.compare(String(a ?? ""), String(b ?? ""));

// Ordine alfabetico italiano (case-insensitive) solo per la visualizzazione delle opzioni.
export const sortIt = (arr, get = (x) => x) => [...(arr || [])].sort((a, b) => cmpIt(get(a), get(b)));
