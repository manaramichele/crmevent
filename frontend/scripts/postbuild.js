// Post-build: minifica consent.js, genera HTML statico per le pagine pubbliche (titolo, descrizione, canonical, Schema.org, contenuto leggibile senza JS), sitemap.xml e copie .gz.
const fs = require("fs");
const path = require("path");
const zlib = require("zlib");
const { minify } = require("terser");
const SEO = require("../src/seo/seoPages.json");

const BUILD = process.env.BUILD_PATH ? path.resolve(process.env.BUILD_PATH) : path.join(__dirname, "..", "build");
const SITE = SEO.site;
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const ORG = { "@type": "Organization", "@id": `${SITE}/#org`, name: "CRMEvent", url: `${SITE}/`, logo: `${SITE}/logo-crmevent.png` };
const APP = { "@type": "SoftwareApplication", name: "CRMEvent", applicationCategory: "BusinessApplication", operatingSystem: "Web", url: `${SITE}/`, publisher: { "@id": `${SITE}/#org` },
  description: "Piattaforma web per organizzare eventi sportivi: eventi, staff e volontari, team e turni, sponsor e partner, percorsi, Event Planner ed Event Map." };
const crumbs = (items) => ({ "@type": "BreadcrumbList", itemListElement: items.map(([name, p], i) => ({ "@type": "ListItem", position: i + 1, name, item: `${SITE}${p}` })) });
const faq = (items) => ({ "@type": "FAQPage", mainEntity: items.map((f) => ({ "@type": "Question", name: f.q, acceptedAnswer: { "@type": "Answer", text: f.a } })) });

const VIDEOS = [["/video/event-planner", "Event Planner – Video dimostrativo | CRMEvent", "Guarda come progettare l'evento sulla mappa con Event Planner di CRMEvent."],
  ["/video/event-map", "Event Map – Video dimostrativo | CRMEvent", "Guarda come trasformare la traccia GPX in un video animato con Event Map di CRMEvent."]];
const navHtml = () => `<nav><a href="/">Home</a> · ${SEO.pages.map((p) => `<a href="${p.path}">${esc(p.name)}</a>`).join(" · ")} · <a href="/faq">FAQ</a> · <a href="/prezzi">Prezzi</a> · <a href="/registrati">Prova gratis 14 giorni</a></nav>`;

function body(p) {
  const name = (x) => (x === "/prezzi" ? "Prezzi" : x === "/faq" ? "FAQ" : (SEO.pages.find((q) => q.path === x) || {}).name);
  let h = `<main><h1>${esc(p.h1)}</h1><p>${esc(p.intro)}</p>`;
  if (p.items) h += p.items.map((f) => `<h2>${esc(f.q)}</h2><p>${esc(f.a)}</p>`).join("");
  for (const s of p.sections || []) h += `<h2>${esc(s.h2)}</h2>${s.p ? `<p>${esc(s.p)}</p>` : ""}${s.items ? `<ul>${s.items.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>` : ""}`;
  h += `<p><a href="/registrati">Prova CRMEvent gratis per 14 giorni</a>${p.related ? " · Approfondisci: " + p.related.map((r) => `<a href="${r}">${esc(name(r))}</a>`).join(" · ") : ""}</p></main>`;
  return h + navHtml();
}

function page(tpl, { route, title, description, schema, content }) {
  const url = `${SITE}${route}`;
  let h = tpl.replace(/<title>[^<]*<\/title>/, `<title>${esc(title)}</title>`)
    .replace(/(<meta name="description" content=")[^"]*"/, `$1${esc(description)}"`)
    .replace(/(<meta property="og:title" content=")[^"]*"/, `$1${esc(title)}"`)
    .replace(/(<meta property="og:description" content=")[^"]*"/, `$1${esc(description)}"`)
    .replace(/(<link rel="canonical" href=")[^"]*"/, `$1${url}"`)
    .replace(/(<meta property="og:url" content=")[^"]*"/, `$1${url}"`)
    .replace("</head>", `<script type="application/ld+json">${JSON.stringify({ "@context": "https://schema.org", "@graph": [ORG, APP, ...schema] }).replace(/</g, "\\u003c")}</script></head>`);
  if (content) h = h.replace(/<main>[\s\S]*<\/main>/, content);
  return h;
}

function write(route, html) {
  const dir = path.join(BUILD, route);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, "index.html"), html);
}

(async () => {
  const consent = path.join(BUILD, "consent.js");
  fs.writeFileSync(consent, (await minify(fs.readFileSync(consent, "utf8"), { compress: true, mangle: true })).code);
  const tpl = fs.readFileSync(path.join(BUILD, "index.html"), "utf8");
  fs.writeFileSync(path.join(BUILD, "index.html"), page(tpl, { route: "/", title: "CRMEvent | Il CRM per organizzare eventi", description: tpl.match(/<meta name="description" content="([^"]*)"/)[1], schema: [], content: null }).replace("</main>", `</main>${navHtml()}`));
  const urls = [["/", "1.0"]];
  for (const p of [...SEO.pages, SEO.faq]) {
    const cr = [["Home", "/"], ...(p.group ? [[p.group, p.path]] : []), [p.name, p.path]].filter((c, i, a) => i === a.length - 1 || c[1] !== p.path);
    write(p.path, page(tpl, { route: p.path, title: p.title, description: p.description, schema: [crumbs(cr), ...(p.items ? [faq(p.items)] : [])], content: body(p) }));
    urls.push([p.path, "0.8"]);
  }
  write("/prezzi", page(tpl, { route: "/prezzi", title: "Prezzi e piani CRMEvent | Bronze, Silver e Gold", description: "Confronta i piani Bronze, Silver e Gold di CRMEvent con abbonamento semestrale o annuale. 14 giorni di prova gratuita senza carta di credito.", schema: [crumbs([["Home", "/"], ["Prezzi", "/prezzi"]])], content: null }));
  urls.push(["/prezzi", "0.9"]);
  for (const [route, title, description] of VIDEOS) {
    write(route, page(tpl, { route, title, description, schema: [crumbs([["Home", "/"], [title.split(" –")[0], route]])], content: `<main><h1>${esc(title.split(" |")[0])}</h1><p>${esc(description)}</p></main>${navHtml()}` }));
    urls.push([route, "0.6"]);
  }
  for (const r of ["/privacy-policy", "/cookie-policy", "/termini"]) urls.push([r, "0.3"]);
  const today = new Date().toISOString().slice(0, 10);
  fs.writeFileSync(path.join(BUILD, "sitemap.xml"), `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls.map(([u, pr]) => `  <url><loc>${SITE}${u}</loc><lastmod>${today}</lastmod><priority>${pr}</priority></url>`).join("\n")}\n</urlset>\n`);
  const gz = (p) => fs.writeFileSync(`${p}.gz`, zlib.gzipSync(fs.readFileSync(p), { level: 9 }));
  for (const f of ["consent.js", "index.html", "manifest.webmanifest", "sitemap.xml", "robots.txt"]) if (fs.existsSync(path.join(BUILD, f))) gz(path.join(BUILD, f));
  console.log(`postbuild: ${urls.length} URL in sitemap, pagine statiche generate`);
})();
