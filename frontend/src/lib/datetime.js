// Timezone helpers pinned to Europe/Rome (CRMEvent Social scheduling).
// Storage stays UTC ISO (backend unchanged); the UI always reasons in Rome wall time.
export const ROME_TZ = "Europe/Rome";

function partsInRome(date) {
  const dtf = new Intl.DateTimeFormat("en-CA", {
    timeZone: ROME_TZ, year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  });
  const p = dtf.formatToParts(date).reduce((a, x) => { a[x.type] = x.value; return a; }, {});
  const hour = p.hour === "24" ? "00" : p.hour;
  return { year: +p.year, month: +p.month, day: +p.day, hour: +hour, minute: +p.minute, second: +p.second };
}

// Milliseconds Rome is ahead of UTC at the given instant (handles DST).
function romeOffsetMs(date) {
  const r = partsInRome(date);
  const asUTC = Date.UTC(r.year, r.month - 1, r.day, r.hour, r.minute, r.second);
  return asUTC - date.getTime();
}

const pad = (n) => String(n).padStart(2, "0");

// UTC ISO -> { date: "YYYY-MM-DD", time: "HH:mm" } in Rome wall time.
export function utcIsoToRomeParts(iso) {
  if (!iso) return { date: "", time: "" };
  const r = partsInRome(new Date(iso));
  return { date: `${r.year}-${pad(r.month)}-${pad(r.day)}`, time: `${pad(r.hour)}:${pad(r.minute)}` };
}

// Rome wall time ("YYYY-MM-DD", "HH:mm") -> UTC ISO string.
export function romePartsToUtcIso(dateStr, timeStr) {
  if (!dateStr || !timeStr) return "";
  const [y, m, d] = dateStr.split("-").map(Number);
  const [hh, mm] = timeStr.split(":").map(Number);
  const naiveUTC = Date.UTC(y, m - 1, d, hh, mm, 0);
  const offset = romeOffsetMs(new Date(naiveUTC));
  return new Date(naiveUTC - offset).toISOString();
}

// "GG/MM/AAAA – HH:mm" in Rome.
export function formatRome(iso) {
  if (!iso) return "";
  const { date, time } = utcIsoToRomeParts(iso);
  const [y, m, d] = date.split("-");
  return `${d}/${m}/${y} – ${time}`;
}

// "GG/MM/AAAA" from a Rome date string "YYYY-MM-DD".
export function formatRomeDate(dateStr) {
  if (!dateStr) return "";
  const [y, m, d] = dateStr.split("-");
  return `${d}/${m}/${y}`;
}

// Current { date, time } in Rome (used as min to block past selections).
export function nowRomeParts() {
  const r = partsInRome(new Date());
  return { date: `${r.year}-${pad(r.month)}-${pad(r.day)}`, time: `${pad(r.hour)}:${pad(r.minute)}` };
}
