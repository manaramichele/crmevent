import { useState } from "react";
import { Play, ExternalLink } from "lucide-react";

export const ytWatchUrl = (id) => `https://www.youtube.com/watch?v=${id}`;

// Player caricato da youtube-nocookie.com solo quando l'utente preme Play (nessuna connessione a YouTube prima del clic)
export function YouTubeTutorial({ id, title, heading = "Scopri come funziona", testid = "mkt-video" }) {
  const [play, setPlay] = useState(false);
  if (!id) return null;
  return (
    <div className="space-y-2" data-testid={testid}>
      <div className="text-sm font-semibold text-slate-900">{heading}</div>
      {title && <div className="text-xs text-slate-500" data-testid={`${testid}-title`}>{title}</div>}
      <div className="relative w-full aspect-video overflow-hidden rounded-xl bg-slate-900">
        {play ? (
          <iframe className="absolute inset-0 h-full w-full" src={`https://www.youtube-nocookie.com/embed/${id}?autoplay=1&rel=0&modestbranding=1`}
            title={title || "Video tutorial CRMEvent"} allow="autoplay; encrypted-media; picture-in-picture; fullscreen" allowFullScreen referrerPolicy="strict-origin-when-cross-origin" data-testid={`${testid}-iframe`} />
        ) : (
          <button type="button" onClick={() => setPlay(true)} data-testid={`${testid}-play`}
            className="group absolute inset-0 flex flex-col items-center justify-center gap-3 bg-gradient-to-br from-slate-800 to-slate-950 text-white">
            <span className="flex h-16 w-16 items-center justify-center rounded-full bg-[#0ABAB5] text-slate-900 shadow-lg transition-transform duration-200 group-hover:scale-110"><Play className="h-7 w-7 translate-x-0.5" fill="currentColor" /></span>
            <span className="px-6 text-center text-[11px] text-slate-300">Premendo Play il video viene caricato da YouTube (modalità privacy avanzata youtube-nocookie.com)</span>
          </button>
        )}
      </div>
      <a href={ytWatchUrl(id)} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-xs font-semibold text-[#088F8A] hover:underline" data-testid={`${testid}-youtube-link`}>
        Guarda su YouTube<ExternalLink className="h-3 w-3" />
      </a>
    </div>
  );
}

// Estrazione ID lato client per l'anteprima (stessa logica del backend)
export const youtubeId = (url) => (String(url || "").match(/(?:youtube(?:-nocookie)?\.com\/(?:watch\?(?:[^#]*&)?v=|embed\/|shorts\/|live\/|v\/)|youtu\.be\/)([A-Za-z0-9_-]{11})/) || [])[1] || null;
