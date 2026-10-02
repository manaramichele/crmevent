import { useState } from "react";
import { ArrowUp, ArrowDown, ArrowUpDown } from "lucide-react";

export function useSort(initial = { key: null, dir: "asc" }) {
  const [sort, setSort] = useState(initial);
  const toggle = (key) => setSort((s) => (s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" }));
  return { sort, toggle, setSort };
}

export function SortIcon({ active, dir }) {
  if (!active) return <ArrowUpDown className="w-3 h-3 opacity-0 group-hover:opacity-40" />;
  return dir === "asc" ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />;
}

const isEmpty = (v) => v === null || v === undefined || v === "" || v === "—";

function detectType(v) {
  if (typeof v === "number") return "number";
  if (typeof v === "string") {
    if (/^\d{4}-\d{2}-\d{2}/.test(v)) return "date";
    if (/^-?\s*€?\s*\d+([.,]\d+)?$/.test(v.trim())) return "number";
  }
  return "string";
}

const num = (v) => parseFloat(String(v).replace(/[^0-9.,-]/g, "").replace(",", ".")) || 0;

export function sortRows(rows, sort, columns = []) {
  if (!sort || !sort.key) return rows;
  const col = columns.find((c) => c.key === sort.key) || {};
  const acc = col.sortAccessor || ((r) => r[sort.key]);
  const dir = sort.dir === "asc" ? 1 : -1;
  const PRIO = col.priorityOrder || null;
  const arr = [...rows];
  arr.sort((a, b) => {
    const va = acc(a), vb = acc(b);
    const ea = isEmpty(va), eb = isEmpty(vb);
    if (ea && eb) return 0;
    if (ea) return 1;   // vuoti sempre in fondo
    if (eb) return -1;
    if (PRIO) return (((PRIO[va] ?? 99) - (PRIO[vb] ?? 99))) * dir;
    const t = col.sortType || detectType(va);
    if (t === "number") return (num(va) - num(vb)) * dir;
    if (t === "date") { const d = new Date(va) - new Date(vb); return (isNaN(d) ? String(va).localeCompare(String(vb)) : d) * dir; }
    return String(va).localeCompare(String(vb), "it", { sensitivity: "base" }) * dir;
  });
  return arr;
}
