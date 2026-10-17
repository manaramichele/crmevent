import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Plus, Trash2, Lock } from "lucide-react";

const CARD = "bg-white border border-slate-200 rounded-xl p-4 sm:p-6";
const CATS = { necessary: "Necessari", analytics: "Analitici", marketing: "Marketing" };
const clone = (o) => JSON.parse(JSON.stringify(o));

export function BannerEditor({ s, onSave }) {
  const [banner, setBanner] = useState(clone(s.banner));
  const [cats, setCats] = useState(clone(s.categories));
  useEffect(() => { setBanner(clone(s.banner)); setCats(clone(s.categories)); }, [s]);
  return (
    <div className={`${CARD} space-y-6`} data-testid="privacy-banner-editor">
      <p className="text-sm text-slate-600">I pulsanti "Accetta tutti", "Rifiuta non necessari" e "Personalizza" sono fissi e con pari evidenza; nessuna categoria facoltativa è mai preselezionata. Le modifiche ai testi diventano obbligatorie per tutti solo pubblicando una nuova versione del banner.</p>
      <div className="grid md:grid-cols-2 gap-4">
        {["it", "en"].map((l) => (
          <div key={l} className="space-y-2">
            <div className="text-xs font-semibold uppercase text-slate-500">Banner {l}</div>
            <Input value={banner[l].title} onChange={(e) => setBanner({ ...banner, [l]: { ...banner[l], title: e.target.value } })} data-testid={`privacy-banner-title-${l}`} />
            <Textarea rows={6} value={banner[l].text} onChange={(e) => setBanner({ ...banner, [l]: { ...banner[l], text: e.target.value } })} data-testid={`privacy-banner-text-${l}`} />
          </div>
        ))}
      </div>
      {Object.keys(CATS).map((c) => (
        <div key={c} className="border-t border-slate-100 pt-4">
          <div className="font-semibold text-slate-800 mb-2 flex items-center gap-2">{CATS[c]}{c === "necessary" && <span className="text-xs text-slate-500 flex items-center gap-1"><Lock className="w-3 h-3" />sempre attivi</span>}</div>
          <div className="grid md:grid-cols-2 gap-4">
            {["it", "en"].map((l) => (
              <div key={l} className="space-y-2">
                <Input value={cats[c][l].name} onChange={(e) => setCats({ ...cats, [c]: { ...cats[c], [l]: { ...cats[c][l], name: e.target.value } } })} data-testid={`privacy-cat-${c}-name-${l}`} />
                <Textarea rows={3} value={cats[c][l].description} onChange={(e) => setCats({ ...cats, [c]: { ...cats[c], [l]: { ...cats[c][l], description: e.target.value } } })} data-testid={`privacy-cat-${c}-desc-${l}`} />
              </div>
            ))}
          </div>
        </div>
      ))}
      <Button onClick={() => onSave({ banner, categories: cats })} data-testid="privacy-banner-save">Salva testi</Button>
    </div>
  );
}

const EMPTY = { id: "", name: "", provider: "", category: "analytics", purpose_it: "", purpose_en: "", cookies: [] };

function CookieRows({ svc, set }) {
  const upd = (i, k, v) => set({ ...svc, cookies: svc.cookies.map((c, j) => (j === i ? { ...c, [k]: v } : c)) });
  return (
    <div className="space-y-2">
      {svc.cookies.map((c, i) => (
        <div key={i} className="grid sm:grid-cols-[1fr_1fr_2fr_auto] gap-2">
          <Input placeholder="Nome cookie" value={c.name} onChange={(e) => upd(i, "name", e.target.value)} />
          <Input placeholder="Durata IT" value={c.duration_it} onChange={(e) => { upd(i, "duration_it", e.target.value); }} />
          <Input placeholder="Descrizione IT" value={c.description_it} onChange={(e) => upd(i, "description_it", e.target.value)} />
          <Button variant="ghost" size="icon" onClick={() => set({ ...svc, cookies: svc.cookies.filter((_, j) => j !== i) })} aria-label="Rimuovi cookie"><Trash2 className="w-4 h-4" /></Button>
        </div>
      ))}
      <Button size="sm" variant="outline" onClick={() => set({ ...svc, cookies: [...svc.cookies, { name: "", duration_it: "", duration_en: "", description_it: "", description_en: "" }] })}><Plus className="w-4 h-4 mr-1" />Cookie</Button>
    </div>
  );
}

function ServiceCard({ svc, locked, set, remove }) {
  const f = (k) => (e) => set({ ...svc, [k]: e.target.value });
  return (
    <div className="border border-slate-200 rounded-lg p-3 space-y-2" data-testid={`privacy-service-${svc.id || "new"}`}>
      <div className="grid sm:grid-cols-4 gap-2">
        <Input placeholder="id_servizio" value={svc.id} onChange={f("id")} disabled={!!locked} />
        <Input placeholder="Nome" value={svc.name} onChange={f("name")} />
        <Input placeholder="Fornitore" value={svc.provider} onChange={f("provider")} />
        <select value={svc.category} onChange={f("category")} disabled={!!locked} className="h-9 rounded-md border border-slate-200 px-2 text-sm" data-testid={`privacy-service-cat-${svc.id}`}>
          {Object.entries(CATS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </div>
      <Textarea rows={2} placeholder="Finalità IT" value={svc.purpose_it} onChange={f("purpose_it")} />
      <Textarea rows={2} placeholder="Finalità EN" value={svc.purpose_en} onChange={f("purpose_en")} />
      <CookieRows svc={svc} set={set} />
      <div className="flex justify-end">
        {locked ? <span className="text-xs text-slate-500 flex items-center gap-1"><Lock className="w-3 h-3" />Collegato a uno script reale: categoria bloccata</span>
          : <Button size="sm" variant="ghost" className="text-red-600" onClick={remove}><Trash2 className="w-4 h-4 mr-1" />Rimuovi servizio</Button>}
      </div>
    </div>
  );
}

export function ServicesEditor({ s, onSave }) {
  const [list, setList] = useState(clone(s.services));
  useEffect(() => { setList(clone(s.services)); }, [s]);
  return (
    <div className={`${CARD} space-y-3`} data-testid="privacy-services-editor">
      <p className="text-sm text-slate-600">Elenco mostrato nella finestra "Preferenze cookie" e nella Cookie Policy. Le modifiche sostanziali richiedono la pubblicazione di una nuova versione della Cookie Policy.</p>
      {list.map((svc, i) => (
        <ServiceCard key={i} svc={svc} locked={s.locked_services[svc.id] && s.services.some((x) => x.id === svc.id)}
          set={(v) => setList(list.map((x, j) => (j === i ? v : x)))} remove={() => setList(list.filter((_, j) => j !== i))} />
      ))}
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" onClick={() => setList([...list, clone(EMPTY)])} data-testid="privacy-service-add"><Plus className="w-4 h-4 mr-1" />Aggiungi servizio</Button>
        <Button onClick={() => onSave({ services: list })} data-testid="privacy-services-save">Salva servizi</Button>
      </div>
    </div>
  );
}
