export const ADDONS = {
  "event-planner": {
    product: "planner", name: "Event Planner", slug: "event-planner",
    tagline: "Il tuo evento prende forma, direttamente sulla mappa.",
    description: "Disegna percorsi, organizza spazi, posiziona strutture e coordina le risorse del tuo evento su una mappa reale.",
    video: { mp4: "/media/event-planner-demo.mp4", webm: "/media/event-planner-demo.webm", poster: "/media/event-planner-demo-poster.jpg", vertical: false },
    benefits: ["Gazebo, transenne, arco di arrivo, palco e ristori in scala reale", "Percorsi con distanza calcolata e livelli separati", "Aree sponsor e postazioni volontari sulla stessa mappa", "Cronologia delle modifiche e salvataggio condiviso con il team"],
  },
  "event-map": {
    product: "eventmap", name: "Event Map", slug: "event-map",
    tagline: "Il tuo percorso diventa protagonista.",
    description: "Trasforma la traccia GPX del tuo evento in un video animato, personalizzato con il logo della manifestazione e pronto da condividere sui social.",
    video: { mp4: "/media/event-map-demo.mp4", webm: "/media/event-map-demo.webm", poster: "/media/event-map-demo-poster.jpg", vertical: true },
    benefits: ["Dalla traccia GPX a un video animato del percorso", "Logo e nome della manifestazione in evidenza", "Distanza, partenza e arrivo mostrati automaticamente", "Formato pronto per Instagram, Facebook, TikTok e YouTube"],
  },
};
export const BY_PRODUCT = { planner: ADDONS["event-planner"], eventmap: ADDONS["event-map"] };
export const SOURCE_LABEL = { included: "Incluso nel piano", purchase: "Acquistato", superadmin: "Omaggio CRMEvent", promo: "Promozione", unrestricted: "Incluso" };
export const eur = (n) => Number(n || 0).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
