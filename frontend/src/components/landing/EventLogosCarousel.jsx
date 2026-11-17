import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import api from "@/lib/api";

const SPEED = 32;
const reducedMotion = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

function Tile({ l, compact, hidden }) {
  return (
    <div className={`flex shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-slate-50 ${compact ? "h-16 w-32 p-2.5" : "h-24 w-44 p-4"}`} title={hidden ? undefined : l.name} aria-hidden={hidden || undefined}>
      <img src={`${process.env.REACT_APP_BACKEND_URL}${l.src}`} alt={hidden ? "" : l.name} width={320} height={160} loading="lazy" decoding="async" draggable={false}
        className="h-auto max-h-full w-auto max-w-full object-contain select-none" data-testid={hidden ? undefined : `home-logo-${l.id}`} />
    </div>
  );
}

function useAutoScroll(ref, setRef, active) {
  const paused = useRef(false); const resume = useRef(); const pos = useRef(0);
  useEffect(() => {
    if (!active || reducedMotion()) return undefined;
    let raf; let last = performance.now();
    const step = (t) => {
      const el = ref.current; const period = setRef.current?.offsetWidth || 0;
      if (el && period && !paused.current) {
        pos.current += (SPEED * (t - last)) / 1000;
        if (pos.current >= period) pos.current -= period;
        el.scrollLeft = pos.current;
      }
      last = t; raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [active, ref, setRef]);
  const pause = useCallback(() => { paused.current = true; clearTimeout(resume.current); }, []);
  const later = useCallback(() => {
    clearTimeout(resume.current);
    resume.current = setTimeout(() => { const el = ref.current; const period = setRef.current?.offsetWidth || 0; if (el) pos.current = period ? el.scrollLeft % period : el.scrollLeft; paused.current = false; }, 2500);
  }, [ref, setRef]);
  return { pause, later };
}

export function LogoCarousel({ title, logos, compact = false, testid = "home-logos" }) {
  const ref = useRef(null); const setRef = useRef(null);
  const [overflow, setOverflow] = useState(false);
  useEffect(() => {
    const measure = () => setOverflow(!!setRef.current && !!ref.current && setRef.current.scrollWidth > ref.current.clientWidth + 4);
    measure();
    const ro = new ResizeObserver(measure);
    if (ref.current) ro.observe(ref.current);
    return () => ro.disconnect();
  }, [logos.length, compact]);
  const loop = overflow && logos.length > 1;
  const { pause, later } = useAutoScroll(ref, setRef, loop);
  const nudge = (dir) => { pause(); ref.current?.scrollBy({ left: dir * (compact ? 136 : 200) * 2, behavior: "smooth" }); later(); };
  const gap = compact ? "gap-3 pr-3" : "gap-5 pr-5";
  return (
    <div className="relative" data-testid={testid}>
      <h2 className={`text-center font-display font-bold tracking-tight text-slate-900 ${compact ? "mb-5 text-lg" : "mb-10 text-2xl md:text-3xl"}`} data-testid={`${testid}-title`}>{title}</h2>
      <div className="group relative">
        <div ref={ref} className={`flex overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden ${loop ? "" : "justify-center snap-x"}`}
          onPointerEnter={pause} onPointerLeave={later} onTouchStart={pause} onTouchEnd={later} onWheel={() => { pause(); later(); }} onFocus={pause} onBlur={later}
          role="region" aria-label={title} tabIndex={0} data-testid={`${testid}-track`}>
          <div ref={setRef} className={`flex shrink-0 ${gap}`}>{logos.map((l) => <Tile key={l.id} l={l} compact={compact} />)}</div>
          {loop && <div className={`flex shrink-0 ${gap}`}>{logos.map((l) => <Tile key={`d-${l.id}`} l={l} compact={compact} hidden />)}</div>}
        </div>
        {loop && <div className="pointer-events-none absolute inset-y-0 left-0 w-12 bg-gradient-to-r from-white" />}
        {loop && <div className="pointer-events-none absolute inset-y-0 right-0 w-12 bg-gradient-to-l from-white" />}
        {loop && !compact && <>
          <button type="button" onClick={() => nudge(-1)} aria-label="Loghi precedenti" className="absolute left-1 top-1/2 hidden -translate-y-1/2 h-9 w-9 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-600 shadow-sm transition-opacity hover:text-slate-900 md:flex md:opacity-0 md:group-hover:opacity-100 focus:opacity-100" data-testid={`${testid}-prev`}><ChevronLeft className="h-4 w-4" /></button>
          <button type="button" onClick={() => nudge(1)} aria-label="Loghi successivi" className="absolute right-1 top-1/2 hidden -translate-y-1/2 h-9 w-9 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-600 shadow-sm transition-opacity hover:text-slate-900 md:flex md:opacity-0 md:group-hover:opacity-100 focus:opacity-100" data-testid={`${testid}-next`}><ChevronRight className="h-4 w-4" /></button>
        </>}
      </div>
    </div>
  );
}

export default function EventLogosCarousel() {
  const [d, setD] = useState(null);
  useEffect(() => { api.get("/public/home-carousel").then(({ data }) => setD(data)).catch(() => setD(null)); }, []);
  if (!d?.enabled || !d.logos?.length) return null;
  return (
    <section className="border-y border-slate-100 bg-white px-6 py-16" data-testid="home-logos-section">
      <div className="mx-auto max-w-6xl"><LogoCarousel title={d.title} logos={d.logos} /></div>
    </section>
  );
}
