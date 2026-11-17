import { useEffect } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { PublicShell, pageByPath } from "@/components/seo/PublicShell";
import { useHead, baseGraph, breadcrumb, faqSchema } from "@/seo/head";

export default function SeoPage() {
  const { pathname } = useLocation();
  const p = pageByPath(pathname.replace(/\/$/, ""));
  useEffect(() => { window.scrollTo(0, 0); }, [pathname]);
  const isFaq = p && !p.sections;
  const crumbs = p ? [["Home", "/"], ...(p.group ? [[p.group, p.path]] : []), [p.name, p.path]].filter((c, i, a) => i === a.length - 1 || c[1] !== p.path) : [];
  useHead(p ? { title: p.title, description: p.description, path: p.path, schema: baseGraph([breadcrumb(crumbs), ...(isFaq ? [faqSchema(p.items)] : [])]) } : { title: "CRMEvent", description: "", path: "/" });
  if (!p) return <Navigate to="/" replace />;
  return (
    <PublicShell crumbs={crumbs} related={p.related}>
      <h1 className="text-4xl sm:text-5xl font-bold tracking-tight" data-testid="seo-h1">{p.h1}</h1>
      <p className="mt-5 text-base text-slate-600" data-testid="seo-intro">{p.intro}</p>
      {isFaq ? (
        <div className="mt-10 divide-y divide-slate-100" data-testid="faq-list">
          {p.items.map((f, i) => (
            <details key={f.q} className="group py-4" open={i < 3} data-testid={`faq-item-${i}`}>
              <summary className="cursor-pointer list-none text-base font-semibold text-slate-900">{f.q}</summary>
              <p className="mt-2 text-sm text-slate-600">{f.a}</p>
            </details>
          ))}
        </div>
      ) : p.sections.map((s) => (
        <section key={s.h2} className="mt-10">
          <h2 className="text-base md:text-lg font-semibold">{s.h2}</h2>
          {s.p && <p className="mt-3 text-sm sm:text-base text-slate-600">{s.p}</p>}
          {s.items && <ul className="mt-3 list-disc space-y-2 pl-5 text-sm sm:text-base text-slate-600">{s.items.map((it) => <li key={it}>{it}</li>)}</ul>}
        </section>
      ))}
      {p.video && <a href={p.video} className="mt-8 inline-block text-sm font-semibold text-[#088F8A] hover:underline" data-testid="seo-video-link">Guarda il video dimostrativo</a>}
    </PublicShell>
  );
}
