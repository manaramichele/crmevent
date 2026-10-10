import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { API } from "@/lib/api";
import { Logo } from "@/components/ui";

export function GoogleButton({ label = "Continua con Google" }) {
  const [on, setOn] = useState(false);
  useEffect(() => { api.get("/oauth/google/config").then(({ data }) => setOn(data.provider === "crmevent")).catch(() => {}); }, []);
  if (!on) return null;
  return (
    <>
      <a href={`${API}/oauth/google/start?intent=partner`} data-testid="google-partner-button"
        className="w-full h-11 inline-flex items-center justify-center gap-2 rounded-full border border-slate-300 bg-white text-sm font-semibold hover:bg-slate-50 transition-colors">
        <svg viewBox="0 0 48 48" className="w-4 h-4" aria-hidden="true"><path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9 3.6l6.7-6.7C35.6 2.4 30.2 0 24 0 14.6 0 6.6 5.4 2.7 13.3l7.8 6C12.4 13.6 17.7 9.5 24 9.5z"/><path fill="#4285F4" d="M46.1 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.4c-.5 2.9-2.2 5.3-4.6 6.9l7.4 5.7c4.3-4 6.9-9.9 6.9-17.1z"/><path fill="#FBBC05" d="M10.5 28.7A14.5 14.5 0 0 1 9.5 24c0-1.6.3-3.2.8-4.7l-7.8-6A24 24 0 0 0 0 24c0 3.9.9 7.5 2.6 10.7l7.9-6z"/><path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.4-5.7c-2.1 1.4-4.8 2.3-8.5 2.3-6.3 0-11.6-4.2-13.5-9.9l-7.9 6C6.6 42.6 14.6 48 24 48z"/></svg>{label}
      </a>
      <div className="flex items-center gap-3 text-xs text-slate-400"><span className="h-px flex-1 bg-slate-200" />oppure<span className="h-px flex-1 bg-slate-200" /></div>
    </>
  );
}

export default function AuthShell({ title, subtitle, children }) {
  return (
    <div className="min-h-screen w-full overflow-x-hidden grid grid-cols-1 lg:grid-cols-2" data-testid="auth-shell">
      <aside className="hidden lg:block min-w-0 bg-ink text-white grain" data-testid="auth-aside">
        <div className="sticky top-0 h-screen flex flex-col justify-between gap-8 p-10 xl:p-14 overflow-hidden">
          <Link to="/"><Logo className="text-xl text-white [&>span:last-child]:text-slate-400" /></Link>
          <div className="min-w-0 max-w-lg">
            <h2 className="text-3xl xl:text-4xl font-extrabold leading-tight break-words">Ogni evento organizzato meglio <span className="text-tiffany">parte da un consiglio.</span></h2>
            <p className="mt-4 text-slate-300 break-words">Il 10% per 24 mesi sugli abbonamenti dei clienti che porti su CRMEvent.</p>
          </div>
          <p className="text-xs text-slate-500">partner.crmevent.it</p>
        </div>
      </aside>
      <main className="min-w-0 flex items-start lg:items-center justify-center px-4 py-8 sm:p-10">
        <div className="w-full max-w-md min-w-0 fade-up">
          <Link to="/" className="lg:hidden"><Logo className="text-lg" /></Link>
          <p className="lg:hidden mt-3 text-sm text-slate-600 break-words" data-testid="auth-mobile-intro">Il 10% per 24 mesi sugli abbonamenti dei clienti che porti su CRMEvent.</p>
          <h1 className="mt-6 lg:mt-0 text-3xl font-extrabold tracking-tight break-words">{title}</h1>
          {subtitle && <p className="mt-2 text-sm text-slate-500 break-words">{subtitle}</p>}
          <div className="mt-7 space-y-4">{children}</div>
        </div>
      </main>
    </div>
  );
}
