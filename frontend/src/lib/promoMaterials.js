export const PROMO = [
  { slug: "event-planner", name: "Event Planner", title: "EVENT PLANNER", subtitle: "Progetta il tuo evento",
    text: "Disegna l'area del tuo evento su una mappa reale: strutture, percorsi, ristori, sponsor e postazioni dello staff, tutto in scala e condiviso con il team.",
    mp4: "/media/event-planner-demo.mp4", webm: "/media/event-planner-demo.webm", poster: "/media/event-planner-demo-poster.jpg",
    preview: "/media/brevo/event-planner-anteprima.jpg", file: "crmevent-event-planner-demo.mp4" },
  { slug: "event-map", name: "Event Map", title: "EVENT MAP", subtitle: "Il tuo percorso prende vita",
    text: "Trasforma la traccia GPX della gara in un video animato con profilo altimetrico, distanza progressiva e logo dell'evento, pronto per i social.",
    mp4: "/media/event-map-demo-gvt.mp4", webm: null, poster: "/media/event-map-demo-gvt-poster.jpg",
    preview: "/media/brevo/event-map-anteprima.jpg", file: "crmevent-event-map-demo.mp4" },
];

export const promoBySlug = (slug) => PROMO.find((p) => p.slug === slug);
export const absUrl = (path) => `${window.location.origin}${path}`;
export const pageUrl = (p) => absUrl(`/video/${p.slug}`);
export const brevoHtml = (p) => `<a href="${pageUrl(p)}" target="_blank" style="display:block;text-decoration:none;"><img src="${absUrl(p.preview)}" width="600" alt="${p.title} – ${p.subtitle}: guarda il video" style="display:block;width:100%;max-width:600px;height:auto;border:0;border-radius:12px;" /></a>`;
