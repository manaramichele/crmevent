import { useEffect, useState } from "react";
import api from "@/lib/platformApi";
import { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { CalendarRange } from "lucide-react";

const STATUS_COLORS = {
  draft: "bg-slate-100 text-slate-600", pending_approval: "bg-amber-100 text-amber-700",
  approved: "bg-blue-100 text-blue-700", scheduled: "bg-tiffany-light text-tiffany-fg",
  published: "bg-green-100 text-green-700", error: "bg-red-100 text-red-700",
};

export default function SocialCalendar() {
  const [posts, setPosts] = useState([]);
  const [labels, setLabels] = useState({});

  useEffect(() => {
    (async () => {
      try {
        const [cal, meta] = await Promise.all([api.get("/social/calendar"), api.get("/social/meta")]);
        setPosts(cal.data.posts || []);
        setLabels(meta.data.status_labels || {});
      } catch (e) { toast.error(formatApiError(e?.response?.data?.detail)); }
    })();
  }, []);

  const byDay = {};
  posts.forEach((p) => {
    const d = (p.scheduled_at || "").slice(0, 10);
    if (!d) return;
    (byDay[d] = byDay[d] || []).push(p);
  });
  const days = Object.keys(byDay).sort();

  return (
    <div className="max-w-5xl space-y-6" data-testid="social-calendar-page">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2"><CalendarRange className="w-6 h-6 text-tiffany-active" />Calendario editoriale</h1>
        <p className="text-slate-500 text-sm mt-1">Contenuti programmati e pianificati, ordinati per data.</p>
      </div>

      {days.length === 0 ? (
        <div className="bg-white border border-slate-200 rounded-xl p-12 text-center text-slate-400" data-testid="calendar-empty">
          Nessun contenuto programmato. Genera un piano editoriale dalla sezione Social.
        </div>
      ) : (
        <div className="space-y-4">
          {days.map((d) => (
            <div key={d} className="bg-white border border-slate-200 rounded-xl p-4" data-testid={`calendar-day-${d}`}>
              <div className="text-sm font-semibold text-slate-800 mb-3">{new Date(d).toLocaleDateString("it-IT", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}</div>
              <div className="space-y-2">
                {byDay[d].map((p) => (
                  <div key={p.id} className="flex items-center gap-3 p-3 rounded-lg border border-slate-100 hover:bg-slate-50 transition-colors" data-testid={`calendar-post-${p.id}`}>
                    <span className="text-xs text-slate-400 w-12 shrink-0">{(p.scheduled_at || "").slice(11, 16)}</span>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium text-slate-800 truncate">{p.title || p.topic || "Senza titolo"}</div>
                      <div className="text-xs text-slate-400 truncate">{(p.caption || "").slice(0, 90)}</div>
                    </div>
                    <span className={`text-[11px] px-2 py-1 rounded-full shrink-0 ${STATUS_COLORS[p.status] || "bg-slate-100"}`}>{labels[p.status] || p.status}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
