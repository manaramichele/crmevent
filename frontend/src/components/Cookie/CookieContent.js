// Etichette fisse (pulsanti con pari evidenza) e testi di riserva se la configurazione non è raggiungibile.
export const UI = {
  it: {
    accept: "Accetta tutti", reject: "Rifiuta non necessari", customize: "Personalizza", save: "Salva preferenze",
    prefsTitle: "Preferenze cookie", alwaysOn: "Sempre attivi", services: "Servizi e cookie", noCookies: "Nessun cookie sul sito CRMEvent",
    privacy: "Privacy Policy", cookie: "Cookie Policy", provider: "Fornitore", duration: "Durata", close: "Chiudi",
    lang: "Lingua",
  },
  en: {
    accept: "Accept all", reject: "Reject non-essential", customize: "Customise", save: "Save preferences",
    prefsTitle: "Cookie preferences", alwaysOn: "Always active", services: "Services and cookies", noCookies: "No cookies on the CRMEvent site",
    privacy: "Privacy Policy", cookie: "Cookie Policy", provider: "Provider", duration: "Duration", close: "Close",
    lang: "Language",
  },
};

export const FALLBACK = {
  banner: {
    it: { title: "Rispettiamo la tua privacy", text: "CRMEvent usa cookie tecnici necessari. Con il tuo consenso useremmo anche cookie analitici e di marketing. Rifiutare non limita l'uso della piattaforma." },
    en: { title: "We respect your privacy", text: "CRMEvent uses necessary technical cookies. With your consent we would also use analytics and marketing cookies. Rejecting does not limit your use of the platform." },
  },
  categories: {
    necessary: { it: { name: "Necessari", description: "Indispensabili al funzionamento." }, en: { name: "Necessary", description: "Required for the site to work." } },
    analytics: { it: { name: "Analitici", description: "Statistiche aggregate." }, en: { name: "Analytics", description: "Aggregated statistics." } },
    marketing: { it: { name: "Marketing", description: "Comunicazioni più pertinenti." }, en: { name: "Marketing", description: "More relevant communications." } },
  },
  services: [],
  versions: null,
};

export const detectLang = () => ((navigator.language || "it").toLowerCase().startsWith("it") ? "it" : "en");
