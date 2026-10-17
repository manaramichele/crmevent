// Consent Manager proprietario CRMEvent: stato locale, registro server, applicazione a GA4/PostHog/Brevo (index.html).
import api from "@/lib/api";

const KEY = "crmevent_consent";
const MAX_AGE = 180 * 86400000;
export const CHANGE_EVENT = "crmevent-consent-change";
export const OPEN_EVENT = "open-cookie-preferences";

const COOKIE_PREFIX = { analytics: [/^_ga/, /^_gid$/, /^ph_/], marketing: [/^sib_/, /^brevo/, /^_brevo/] };
const STORAGE_PREFIX = { analytics: [/^ph_/, /^crmevent_ref$/], marketing: [/^sib/, /^brevo/i] };

export function getStored() {
  try { return JSON.parse(localStorage.getItem(KEY)); } catch { return null; }
}

export function isValid(stored, versions) {
  if (!stored?.choices || !stored.ts || Date.now() - stored.ts > MAX_AGE) return false;
  if (!versions) return true;
  return ["privacy", "cookie", "banner"].every((k) => stored.versions?.[k] === versions[k]);
}

export function hasConsent(cat) {
  const s = getStored();
  return !!(s && Date.now() - s.ts < MAX_AGE && s.choices?.[cat]);
}

export const openCookiePreferences = () => window.dispatchEvent(new Event(OPEN_EVENT));

function uuid() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  return "10000000-1000-4000-8000-100000000000".replace(/[018]/g, (c) => (c ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (c / 4)))).toString(16));
}

function purge(cat) {
  const host = window.location.hostname;
  const parts = host.split(".");
  const domains = ["", host, `.${host}`, parts.length > 2 ? `.${parts.slice(-2).join(".")}` : null].filter((d) => d !== null);
  document.cookie.split("; ").map((c) => c.split("=")[0]).filter((n) => COOKIE_PREFIX[cat].some((re) => re.test(n))).forEach((n) => {
    domains.forEach((d) => { document.cookie = `${n}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/${d ? `; domain=${d}` : ""}`; });
  });
  try {
    Object.keys(localStorage).filter((k) => STORAGE_PREFIX[cat].some((re) => re.test(k))).forEach((k) => localStorage.removeItem(k));
  } catch {}
}

export async function saveConsent({ analytics, marketing }, action, source, lang, versions) {
  const prev = getStored();
  const choices = { necessary: true, analytics: !!analytics, marketing: !!marketing };
  const next = { id: prev?.id || uuid(), choices, ts: Date.now(), versions };
  try { localStorage.setItem(KEY, JSON.stringify(next)); } catch {}
  try { await api.post("/privacy/consents", { consent_id: next.id, analytics: choices.analytics, marketing: choices.marketing, action, source, lang, versions }); } catch {}
  const revoked = ["analytics", "marketing"].filter((c) => prev?.choices?.[c] && !choices[c]);
  if (revoked.length) {
    if (window.__crmApplyConsent) window.__crmApplyConsent(choices);
    if (revoked.includes("analytics") && window.posthog?.opt_out_capturing) {
      try { window.posthog.opt_out_capturing(); window.posthog.reset?.(); window.posthog.set_config?.({ persistence: "memory", disable_persistence: true }); } catch {}
    }
    revoked.forEach(purge);
    window.location.reload(); // gli script già caricati vengono scaricati solo ricaricando la pagina
    return next;
  }
  if (window.__crmApplyConsent) window.__crmApplyConsent(choices);
  window.dispatchEvent(new CustomEvent(CHANGE_EVENT, { detail: choices }));
  return next;
}
