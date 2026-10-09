import OrgMessagesBanner from "@/components/OrgMessagesBanner";
import TodoPanel from "@/components/TodoPanel";
import NotesPanel from "@/components/NotesPanel";

export default function Dashboard() {
  return (
    <div className="animate-fade-up space-y-5" data-testid="dashboard">
      <div>
        <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-slate-900 font-display">Dashboard</h1>
        <p className="text-sm text-slate-500 mt-1">Panoramica delle sezioni a cui hai accesso</p>
      </div>
      <OrgMessagesBanner />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5" data-testid="dashboard-columns">
        <TodoPanel />
        <NotesPanel />
      </div>
    </div>
  );
}
