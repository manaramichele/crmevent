// GA4 + Google Consent Mode v2 helper for CRMEvent.
// The gtag stub + consent defaults (all denied) are set in public/index.html BEFORE this runs.
// The GA collection script is loaded (in index.html) ONLY on the production host to avoid
// polluting the production property from preview/dev/test environments.
export const GA_ID = "G-PZK7J854DS";

// Consent is managed EXCLUSIVELY by iubenda (Google Consent Mode v2 + preventive blocking),
// loaded first in index.html. We only push page_views/events to gtag; Consent Mode governs
// whether cookies/identifiers are used, so CRMEvent no longer runs a second consent system.
const g = (...args) => { if (typeof window !== "undefined" && window.gtag) window.gtag(...args); };

// SPA page_view. Consent Mode decides cookie usage (cookieless ping when denied).
export function trackPageView(path) {
  g("event", "page_view", { page_path: path, page_location: window.location.origin + path, page_title: document.title });
}

// Generic event. Never pass personal data in params — call sites control this.
export function trackEvent(name, params = {}) {
  g("event", name, params);
}

// Fire an event at most once per dedupKey (survives refresh/revisit). No PII in keys.
export function trackOnce(dedupKey, name, params = {}) {
  const K = "crmevent_ga4_once";
  let seen = [];
  try { seen = JSON.parse(localStorage.getItem(K)) || []; } catch { seen = []; }
  if (seen.includes(dedupKey)) return;
  trackEvent(name, params);
  try { localStorage.setItem(K, JSON.stringify([...seen, dedupKey].slice(-100))); } catch {}
}

// ---------- Stripe subscription funnel (GA4 recommended e-commerce events) ----------
// Plan catalog used to build the `items` array. No personal data ever leaves here.
const PLAN_ITEMS = {
  monthly: { item_id: "crmevent_monthly", item_name: "Piano CRMEvent Mensile", price: 19.9 },
  yearly: { item_id: "crmevent_yearly", item_name: "Piano CRMEvent Annuale", price: 199 },
};
const PURCHASED_KEY = "crmevent_ga4_purchased";

function planItem(billingCycle) {
  const p = PLAN_ITEMS[billingCycle] || PLAN_ITEMS.yearly;
  return { ...p, item_category: "Abbonamento", quantity: 1 };
}

// Fired when the user actually starts the Stripe checkout (before redirect).
export function trackBeginCheckout(billingCycle) {
  const item = planItem(billingCycle);
  trackEvent("begin_checkout", { currency: "EUR", value: item.price, items: [item] });
}

// Fired ONLY after Stripe confirms the payment. Deduplicated by transaction_id so the
// same payment can never produce two `purchase` events (refresh / revisit / re-open).
export function trackPurchaseOnce({ transaction_id, value, currency, billing_cycle }) {
  if (!transaction_id) return;
  let seen = [];
  try { seen = JSON.parse(localStorage.getItem(PURCHASED_KEY)) || []; } catch { seen = []; }
  if (seen.includes(transaction_id)) return;
  trackEvent("purchase", {
    transaction_id,
    value,
    currency: currency || "EUR",
    items: [planItem(billing_cycle)],
  });
  try { localStorage.setItem(PURCHASED_KEY, JSON.stringify([...seen, transaction_id].slice(-50))); } catch {}
}
