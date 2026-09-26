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
