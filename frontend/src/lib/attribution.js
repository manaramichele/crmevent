import api from "@/lib/api";
import { hasConsent, CHANGE_EVENT } from "@/lib/consent";
import { trackEvent } from "@/lib/analytics";

// Provenienza del primo accesso (referrer/utm) e riconoscimento degli assistenti AI. Salvata solo con consenso analitico.
const KEY = "crmevent_attr";
const VID = "crmevent_vid";
const AI_HOSTS = [[/(^|\.)chatgpt\.com$|(^|\.)chat\.openai\.com$|(^|\.)openai\.com$/, "chatgpt"], [/(^|\.)perplexity\.ai$/, "perplexity"],
  [/(^|\.)gemini\.google\.com$|(^|\.)bard\.google\.com$/, "gemini"], [/(^|\.)copilot\.microsoft\.com$/, "copilot"], [/(^|\.)claude\.ai$/, "claude"]];
const AI_UTM = [[/chatgpt|openai/, "chatgpt"], [/perplexity/, "perplexity"], [/gemini/, "gemini"], [/copilot/, "copilot"], [/claude/, "claude"]];

let current = null;

function detect() {
  const qs = new URLSearchParams(window.location.search);
  let host = "";
  try { host = document.referrer ? new URL(document.referrer).hostname.toLowerCase() : ""; } catch { host = ""; }
  if (host === window.location.hostname) host = "";
  const utm = (qs.get("utm_source") || "").toLowerCase().slice(0, 120);
  const ai = (AI_HOSTS.find(([re]) => re.test(host)) || AI_UTM.find(([re]) => utm && re.test(utm)) || [])[1] || "";
  return { ai, source: ai || utm || host || "diretto", referrer_host: host, landing: window.location.pathname.slice(0, 200), utm_source: utm,
    utm_medium: (qs.get("utm_medium") || "").slice(0, 120), utm_campaign: (qs.get("utm_campaign") || "").slice(0, 120), at: new Date().toISOString() };
}

function persist() {
  if (!hasConsent("analytics")) {
    try { localStorage.removeItem(KEY); localStorage.removeItem(VID); } catch { /* ignore */ }
    return;
  }
  if (!current) return;
  try {
    if (!localStorage.getItem(KEY)) localStorage.setItem(KEY, JSON.stringify(current));
    let vid = localStorage.getItem(VID);
    if (!vid) { vid = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2)); localStorage.setItem(VID, vid); }
    if (sessionStorage.getItem("crmevent_visit_sent")) return;
    sessionStorage.setItem("crmevent_visit_sent", "1");
    const { at, ...body } = current;
    api.post("/public/visit", { visitor_id: vid, ...body }).catch(() => {});
    if (current.ai) trackEvent("ai_assistant_visit", { ai_assistant: current.ai, landing_page: current.landing });
  } catch { /* storage non disponibile */ }
}

export function captureAttribution() {
  current = detect();
  persist();
  window.addEventListener(CHANGE_EVENT, persist);
}

export function getAttribution() {
  if (!hasConsent("analytics")) return null;
  try { const v = JSON.parse(localStorage.getItem(KEY)); if (v) return v; } catch { /* ignore */ }
  return current;
}
