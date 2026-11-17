import { useEffect } from "react";
import SEO from "@/seo/seoPages.json";

export const SITE = SEO.site;

const ORG = { "@type": "Organization", "@id": `${SITE}/#org`, name: "CRMEvent", url: `${SITE}/`, logo: `${SITE}/logo-crmevent.png` };
const APP = { "@type": "SoftwareApplication", name: "CRMEvent", applicationCategory: "BusinessApplication", operatingSystem: "Web", url: `${SITE}/`, publisher: { "@id": `${SITE}/#org` },
  description: "Piattaforma web per organizzare eventi sportivi: eventi, staff e volontari, team e turni, sponsor e partner, percorsi, Event Planner ed Event Map." };

export function breadcrumb(items) {
  return { "@type": "BreadcrumbList", itemListElement: items.map(([name, path], i) => ({ "@type": "ListItem", position: i + 1, name, item: `${SITE}${path}` })) };
}

export function faqSchema(items) {
  return { "@type": "FAQPage", mainEntity: items.map((f) => ({ "@type": "Question", name: f.q, acceptedAnswer: { "@type": "Answer", text: f.a } })) };
}

export const baseGraph = (extra = []) => ({ "@context": "https://schema.org", "@graph": [ORG, APP, ...extra] });

function setMeta(sel, attr, val) {
  let el = document.head.querySelector(sel);
  if (!el) { el = document.createElement(sel.startsWith("link") ? "link" : "meta"); document.head.appendChild(el); }
  Object.entries(attr).forEach(([k, v]) => el.setAttribute(k, v));
  if (val !== undefined) el.setAttribute(sel.startsWith("link") ? "href" : "content", val);
}

export function useHead({ title, description, path, schema }) {
  useEffect(() => {
    document.title = title;
    const url = `${SITE}${path === "/" ? "/" : path}`;
    setMeta('meta[name="description"]', { name: "description" }, description);
    setMeta('link[rel="canonical"]', { rel: "canonical" }, url);
    setMeta('meta[property="og:title"]', { property: "og:title" }, title);
    setMeta('meta[property="og:description"]', { property: "og:description" }, description);
    setMeta('meta[property="og:url"]', { property: "og:url" }, url);
    let s = document.getElementById("ld-json");
    if (!s) { s = document.createElement("script"); s.type = "application/ld+json"; s.id = "ld-json"; document.head.appendChild(s); }
    s.textContent = JSON.stringify(schema || baseGraph());
  }, [title, description, path, schema]);
}
