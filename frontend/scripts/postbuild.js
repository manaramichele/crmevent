// Minifica i file statici di public/ non gestiti da webpack (consent.js) e crea le copie .gz per nginx gzip_static.
const fs = require("fs");
const path = require("path");
const zlib = require("zlib");
const { minify } = require("terser");

const BUILD = process.env.BUILD_PATH ? path.resolve(process.env.BUILD_PATH) : path.join(__dirname, "..", "build");

(async () => {
  const consent = path.join(BUILD, "consent.js");
  const out = await minify(fs.readFileSync(consent, "utf8"), { compress: true, mangle: true });
  fs.writeFileSync(consent, out.code);
  for (const f of ["consent.js", "index.html", "manifest.webmanifest", "sitemap.xml", "robots.txt"]) {
    const p = path.join(BUILD, f);
    if (fs.existsSync(p)) fs.writeFileSync(`${p}.gz`, zlib.gzipSync(fs.readFileSync(p), { level: 9 }));
  }
  console.log(`postbuild: consent.js ${out.code.length} B minificato, copie .gz create`);
})();
