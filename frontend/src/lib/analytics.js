// GA4 + Google Consent Mode v2 helper for CRMEvent.
// The gtag stub + consent defaults (all denied) are set in public/index.html BEFORE this runs.
// The GA collection script is loaded (in index.html) ONLY on the production host to avoid
// polluting the production property from preview/dev/test environments.
export const GA_ID = "G-PZK7J854DS";
export const CONSENT_KEY = "crmevent_cookie_consent";

const g = (...args) => { if (typeof window !== "undefined" && window.gtag) window.gtag(...args); };

export function readConsent() {
  try { return JSON.parse(localStorage.getItem(CONSENT_KEY)); } catch { return null; }
}

// Push a Consent Mode v2 update. Analytics and Ads are handled as separate categories.
export function applyConsent(c) {
  g("consent", "update", {
    analytics_storage: c.analytics ? "granted" : "denied",
    ad_storage: c.ads ? "granted" : "denied",
    ad_user_data: c.ads ? "granted" : "denied",
    ad_personalization: c.ads ? "granted" : "denied",
  });
}

export function saveConsent(c) {
  const v = { analytics: !!c.analytics, ads: !!c.ads, ts: Date.now() };
  try { localStorage.setItem(CONSENT_KEY, JSON.stringify(v)); } catch {}
  applyConsent(v);
  return v;
}

// SPA page_view. Only send once the user granted analytics (privacy-first).
export function trackPageView(path) {
  const c = readConsent();
  if (!c || !c.analytics) return;
  g("event", "page_view", { page_path: path, page_location: window.location.origin + path, page_title: document.title });
}

// Generic event. Never pass personal data in params — call sites control this.
export function trackEvent(name, params = {}) {
  const c = readConsent();
  if (!c || !c.analytics) return;
  g("event", name, params);
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
