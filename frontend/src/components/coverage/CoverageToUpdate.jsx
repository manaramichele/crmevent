import { useEffect, useState } from "react";
import api from "@/lib/api";
import { AlertTriangle } from "lucide-react";
import { LegacyDialog } from "./CoverageFasceDialogs";

export default function CoverageToUpdate({ params, version, onOpenPerson }) {
  const [list, setList] = useState([]);
  const [open, setOpen] = useState(false);
  const q = { evento_id: params.evento_id, team_id: params.team_id, gruppo: params.gruppo, cat: params.cat };
  useEffect(() => {
    api.get("/staff-coverage/to-update", { params: q }).then(({ data }) => setList(data.people)).catch(() => setList([]));
  }, [params.evento_id, params.team_id, params.gruppo, params.cat, version]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!list.length) return null;
  return (
    <>
      <button type="button" onClick={() => setOpen(true)} className="inline-flex items-center gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-1.5 text-sm text-amber-900 hover:bg-amber-100" data-testid="cov-legacy-indicator">
        <AlertTriangle className="w-4 h-4" />Disponibilità da aggiornare: <b data-testid="cov-legacy-count">{list.length}</b>
      </button>
      <LegacyDialog open={open} list={list} onClose={() => setOpen(false)} onOpenPerson={(pid) => { setOpen(false); onOpenPerson(pid); }} />
    </>
  );
}
