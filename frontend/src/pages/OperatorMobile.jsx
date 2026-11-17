import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import axios from "axios";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { Phone, Siren, ClipboardList, CheckCircle2, MessageSquare, ArrowLeft, WifiOff, MapPin, Camera, Locate } from "lucide-react";
import { ITV_STATES, PRIORITY, ASG, fmtTime, Pill } from "@/components/controlroom/meta";
import { TypeGrid, PriorityPicker } from "@/components/controlroom/ItvNew";

const API = `${process.env.REACT_APP_BACKEND_URL}/api/cr-mobile`;
const OSM = { version: 8, sources: { osm: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, attribution: "© OpenStreetMap" } }, layers: [{ id: "osm", type: "raster", source: "osm" }] };
const err = (e) => e.response?.data?.detail || (e.response ? "Operazione non riuscita" : "Nessuna connessione: operazione NON registrata, riprova");
const Big = ({ children, className = "", ...p }) => <button type="button" className={`flex min-h-[64px] w-full items-center justify-center gap-3 rounded-2xl px-4 text-base font-bold transition-transform active:scale-[0.98] disabled:opacity-50 ${className}`} {...p}>{children}</button>;

function MapPick({ center, value, onPick }) {
  const box = useRef(null);
  useEffect(() => {
    const m = new maplibregl.Map({ container: box.current, style: OSM, center: value || center || [12.5, 42], zoom: value || center ? 15 : 5 });
    let mk = value ? new maplibregl.Marker({ color: "#DC2626" }).setLngLat(value).addTo(m) : null;
    m.on("click", (e) => { const c = [e.lngLat.lng, e.lngLat.lat]; if (!mk) mk = new maplibregl.Marker({ color: "#DC2626" }).addTo(m); mk.setLngLat(c); onPick(c); });
    return () => m.remove();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return <div ref={box} className="h-56 w-full overflow-hidden rounded-xl" data-testid="op-map-pick" />;
}

function Report({ d, post, send, back }) {
  const [v, setV] = useState({ pos_mode: post ? "postazione" : "manuale" });
  const [photo, setPhoto] = useState(null);
  const [busy, setBusy] = useState(false);
  const [gpsMsg, setGpsMsg] = useState("");
  const cid = useRef((crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}${Math.random()}`).replace(/-/g, ""));
  const set = (k, x) => setV((o) => ({ ...o, [k]: x }));
  const gps = () => {
    setGpsMsg("Richiesta posizione…");
    navigator.geolocation?.getCurrentPosition((p) => { setV((o) => ({ ...o, pos_mode: "gps", lng: p.coords.longitude, lat: p.coords.latitude })); setGpsMsg(`Posizione condivisa (±${Math.round(p.coords.accuracy)} m)`); },
      () => setGpsMsg("GPS non autorizzato: scegli un'altra modalità"), { enableHighAccuracy: true, timeout: 10000 });
  };
  const posOk = v.pos_mode === "postazione" ? !!post : v.pos_mode === "manuale" ? !!(v.riferimento || "").trim() : v.lng != null;
  const ok = v.tipologia && (v.descrizione || "").trim() && posOk;
  const submit = async () => {
    if (!ok || busy) return;
    setBusy(true);
    const body = { client_id: cid.current, tipologia: v.tipologia, descrizione: v.descrizione, priorita: v.priorita, pos_mode: v.pos_mode, riferimento: v.riferimento,
      ...(["gps", "mappa"].includes(v.pos_mode) ? { lng: v.lng, lat: v.lat } : {}) };
    await send(body, photo);
    setBusy(false);
  };
  return (
    <div className="space-y-4" data-testid="op-report">
      <button type="button" onClick={back} className="flex items-center gap-1 text-sm text-slate-500"><ArrowLeft className="h-4 w-4" />Indietro</button>
      <h2 className="text-xl font-bold">Invia segnalazione</h2>
      <TypeGrid types={d.itv_types} value={v.tipologia} onPick={(t) => set("tipologia", t.key)} prefix="op-type" />
      {d.operator.can_set_priority && <div><div className="mb-1 text-xs font-semibold text-slate-600">Priorità indicativa</div><PriorityPicker value={v.priorita} onPick={(p) => set("priorita", p)} prefix="op-prio" /></div>}
      <textarea value={v.descrizione || ""} onChange={(e) => set("descrizione", e.target.value)} placeholder="Cosa succede?" className="min-h-[90px] w-full rounded-xl border border-slate-200 p-3 text-base" data-testid="op-report-desc" />
      <div className="space-y-2">
        <div className="text-xs font-semibold text-slate-600">Posizione</div>
        <div className="grid grid-cols-2 gap-2">
          {[["postazione", "La mia postazione", !post], ["gps", "Condividi GPS"], ["mappa", "Punto sulla mappa"], ["manuale", "Riferimento scritto"]].map(([k, l, dis]) => (
            <button key={k} type="button" disabled={dis} onClick={() => { set("pos_mode", k); if (k === "gps") gps(); }} className={`h-12 rounded-xl border text-sm font-semibold disabled:opacity-40 ${v.pos_mode === k ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 bg-white"}`} data-testid={`op-pos-${k}`}>{l}</button>))}
        </div>
        {v.pos_mode === "gps" && <div className="flex items-center gap-1 text-xs text-slate-600" data-testid="op-gps-msg"><Locate className="h-3.5 w-3.5" />{gpsMsg}</div>}
        {v.pos_mode === "mappa" && <MapPick center={post?.lng != null ? [post.lng, post.lat] : null} value={v.lng != null ? [v.lng, v.lat] : null} onPick={(c) => setV((o) => ({ ...o, lng: c[0], lat: c[1] }))} />}
        <input value={v.riferimento || ""} onChange={(e) => set("riferimento", e.target.value)} placeholder="Riferimento (es. km 4, dopo il ponte)" className="h-12 w-full rounded-xl border border-slate-200 px-3 text-base" data-testid="op-report-ref" />
      </div>
      <label className="flex h-12 cursor-pointer items-center justify-center gap-2 rounded-xl border border-dashed border-slate-300 text-sm" data-testid="op-photo-label"><Camera className="h-4 w-4" />{photo ? photo.name : "Fotografia (facoltativa)"}
        <input type="file" accept="image/*" capture="environment" className="hidden" onChange={(e) => setPhoto(e.target.files?.[0] || null)} data-testid="op-photo-input" /></label>
      <Big onClick={submit} disabled={!ok || busy} className="bg-red-600 text-white" data-testid="op-report-submit">{busy ? "Invio in corso…" : "INVIA"}</Big>
    </div>
  );
}

function Mine({ d, act, back, upload }) {
  return (
    <div className="space-y-3" data-testid="op-mine">
      <button type="button" onClick={back} className="flex items-center gap-1 text-sm text-slate-500"><ArrowLeft className="h-4 w-4" />Indietro</button>
      <h2 className="text-xl font-bold">I miei interventi</h2>
      {d.interventions.map((i) => {
        const a = i.my_assignment, active = a && ["non_confermata", "confermata"].includes(a.stato) && !["chiuso", "annullato"].includes(i.stato);
        const t = d.itv_types.find((x) => x.key === i.tipologia);
        return (
          <div key={i.id} className={`space-y-2 rounded-2xl border bg-white p-4 ${i.priorita === "critica" ? "border-red-500 ring-2 ring-red-200" : "border-slate-200"}`} data-testid={`op-itv-${i.codice}`}>
            <div className="flex flex-wrap items-center gap-1.5"><b className="text-lg">{i.codice}</b><Pill c={PRIORITY[i.priorita][2]}>{PRIORITY[i.priorita][0]}</Pill><Pill c={ITV_STATES[i.stato][1]} testid={`op-itv-state-${i.codice}`}>{ITV_STATES[i.stato][0]}</Pill></div>
            <div className="text-sm font-semibold text-slate-600">{t?.label} · {fmtTime(i.created_at)}</div>
            <div>{i.descrizione}</div>
            {i.riferimento && <div className="text-sm text-slate-500"><MapPin className="inline h-3.5 w-3.5" /> {i.riferimento}</div>}
            {i.mine_report && <div className="text-xs text-sky-700">Segnalazione inviata da te · ricevuta dalla centrale alle {fmtTime(i.created_at)}{i.stato !== "segnalato" ? " · presa in carico" : " · in attesa di presa in carico"}</div>}
            {a && <div className="text-xs">Incarico: <Pill c={ASG[a.stato][1]}>{ASG[a.stato][0]}</Pill></div>}
            {active && <div className="grid grid-cols-2 gap-2">
              {(a.stato === "non_confermata" || ["segnalato", "in_attesa"].includes(i.stato)) && <Big onClick={() => act(i, "conferma")} className="col-span-2 bg-emerald-600 text-white" data-testid={`op-act-conferma-${i.codice}`}>CONFERMA PRESA IN CARICO</Big>}
              {(() => {
                const LIN = ["preso_in_carico", "squadra_inviata", "sul_posto", "risolto"], cur = LIN.indexOf(i.stato);
                const nexts = [["partito", "squadra_inviata", "PARTITO", "bg-violet-600 text-white"], ["arrivato", "sul_posto", "ARRIVATO SUL POSTO", "bg-amber-500 text-slate-900"], ["risolto", "risolto", "INTERVENTO RISOLTO", "bg-emerald-100 text-emerald-800"]].filter(([, s]) => LIN.indexOf(s) > cur);
                return nexts.slice(0, 2).map(([k, , l, c]) => <Big key={k} onClick={() => act(i, k)} className={c} data-testid={`op-act-${k}-${i.codice}`}>{l}</Big>);
              })()}
              <Big onClick={() => act(i, "aggiorna", "Scrivi l'aggiornamento")} className="bg-slate-100 text-slate-800" data-testid={`op-act-aggiorna-${i.codice}`}>AGGIORNA</Big>
              {a.stato === "non_confermata" && <button type="button" onClick={() => act(i, "rifiuta", "Motivo del rifiuto (obbligatorio)")} className="col-span-2 text-sm font-semibold text-red-600 underline" data-testid={`op-act-rifiuta-${i.codice}`}>Rifiuta incarico</button>}
              <label className="col-span-2 flex h-11 cursor-pointer items-center justify-center gap-2 rounded-xl border border-dashed border-slate-300 text-sm"><Camera className="h-4 w-4" />Aggiungi foto<input type="file" accept="image/*" capture="environment" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) upload(i, f); }} /></label>
            </div>}
          </div>
        );
      })}
      {!d.interventions.length && <div className="rounded-2xl bg-white p-6 text-center text-slate-400">Nessun intervento assegnato</div>}
    </div>
  );
}

function Msgs({ d, token, reload, back }) {
  const [t, setT] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { axios.post(`${API}/${token}/messages/read`).then(reload).catch(() => {}); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const send = async () => {
    setBusy(true);
    try { await axios.post(`${API}/${token}/messages`, { text: t }); setT(""); reload(); } catch (e) { alert(err(e)); }
    setBusy(false);
  };
  return (
    <div className="space-y-3" data-testid="op-msgs">
      <button type="button" onClick={back} className="flex items-center gap-1 text-sm text-slate-500"><ArrowLeft className="h-4 w-4" />Indietro</button>
      <h2 className="text-xl font-bold">Messaggi</h2>
      <div className="flex gap-2"><input value={t} onChange={(e) => setT(e.target.value)} placeholder="Scrivi alla Control Room" className="h-12 flex-1 rounded-xl border border-slate-200 px-3" data-testid="op-msg-input" />
        <button type="button" disabled={!t.trim() || busy} onClick={send} className="h-12 rounded-xl bg-[#0ABAB5] px-4 font-bold disabled:opacity-50" data-testid="op-msg-send">Invia</button></div>
      {d.messages.map((m) => <div key={m.id} className={`rounded-xl p-3 text-sm ${m.mine ? "ml-8 bg-[#0ABAB5]/10" : "mr-8 bg-white"}`} data-testid="op-msg-row"><div className="text-[11px] text-slate-500">{m.from_name} · {fmtTime(m.at)}{m.mine ? (m.read ? " · letto" : " · inviato") : ""}</div>{m.text}</div>)}
    </div>
  );
}

export default function OperatorMobile() {
  const { token } = useParams();
  const [d, setD] = useState(null);
  const [fatal, setFatal] = useState(null);
  const [offline, setOffline] = useState(false);
  const [view, setView] = useState("home");
  const [toast, setToast] = useState(null);
  const say = (m, bad) => { setToast({ m, bad }); setTimeout(() => setToast(null), 5000); };
  const load = useCallback(async () => {
    try { const r = await axios.get(`${API}/${token}`, { timeout: 10000 }); setD(r.data); setOffline(false); } catch (e) { if (!e.response) setOffline(true); else setFatal(e.response.data?.detail || "Accesso non disponibile"); }
  }, [token]);
  useEffect(() => { load(); const i = setInterval(load, 6000); window.addEventListener("online", load); return () => { clearInterval(i); window.removeEventListener("online", load); }; }, [load]);
  const upload = async (i, f) => {
    const fd = new FormData(); fd.append("file", f);
    try { await axios.post(`${API}/${token}/interventions/${i.id}/photo`, fd); say("Foto inviata"); } catch (e) { say(err(e), true); }
  };
  const act = async (i, action, ask) => {
    let note;
    if (ask) { note = window.prompt(ask)?.trim(); if (!note) return; }
    try { await axios.post(`${API}/${token}/interventions/${i.id}/action`, { action, note }); say("Registrato dalla centrale"); load(); } catch (e) { say(err(e), true); }
  };
  const send = async (body, photo) => {
    try {
      const r = await axios.post(`${API}/${token}/reports`, body);
      if (photo) await upload(r.data, photo);
      say(`Segnalazione ${r.data.codice} registrata alle ${fmtTime(r.data.created_at)} · stato ${ITV_STATES[r.data.stato][0]}`);
      setView("mine"); load();
    } catch (e) { say(err(e), true); }
  };
  const checkin = async () => {
    try { await axios.post(`${API}/${token}/checkin`, { presente: !d.operator.presente }); say(d.operator.presente ? "Uscita registrata" : "Presenza registrata"); load(); } catch (e) { say(err(e), true); }
  };
  if (fatal) return <div className="flex min-h-screen items-center justify-center bg-slate-50 p-6 text-center" data-testid="op-fatal"><div><Siren className="mx-auto h-10 w-10 text-slate-300" /><p className="mt-3 font-semibold">{fatal}</p></div></div>;
  if (!d) return <div className="flex min-h-screen items-center justify-center text-slate-400" data-testid="op-loading">Caricamento…</div>;
  const o = d.operator, mineOpen = d.interventions.filter((i) => i.my_assignment && ["non_confermata", "confermata"].includes(i.my_assignment.stato) && !["chiuso", "annullato"].includes(i.stato)).length;
  return (
    <div className="min-h-screen bg-slate-50 pb-10" data-testid="op-page">
      {offline && <div className="sticky top-0 z-50 flex items-center gap-2 bg-red-600 px-4 py-3 text-sm font-bold text-white" data-testid="op-offline"><WifiOff className="h-4 w-4" />Connessione assente: dati non aggiornati</div>}
      {toast && <div className={`fixed inset-x-3 top-3 z-50 rounded-xl px-4 py-3 text-sm font-semibold text-white shadow-lg ${toast.bad ? "bg-red-600" : "bg-emerald-600"}`} data-testid="op-toast">{toast.m}</div>}
      <div className="bg-slate-900 px-5 pb-5 pt-6 text-white">
        <div className="text-xs uppercase tracking-wider text-[#0ABAB5]">Control Room · {d.event?.nome}</div>
        <div className="mt-1 text-2xl font-bold" data-testid="op-name">{o.nome}</div>
        <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-slate-300">
          <div>Postazione<br /><b className="text-white" data-testid="op-post">{d.post?.nome || "—"}</b></div><div>Settore<br /><b className="text-white">{d.sector?.nome || "—"}</b></div>
          <div>Turno<br /><b className="text-white">{d.shift ? [d.shift.data, d.shift.ora_inizio && `${d.shift.ora_inizio}-${d.shift.ora_fine || ""}`].filter(Boolean).join(" ") : "—"}</b></div>
          <div>Responsabile<br /><b className="text-white">{d.post?.responsabile || d.sector?.responsabile || d.responsabile || "—"}</b></div>
        </div>
        <div className="mt-3 text-xs">Servizio: <b className={o.presente ? "text-emerald-400" : "text-amber-300"} data-testid="op-service">{o.presente ? "IN POSTAZIONE" : "PRESENZA NON CONFERMATA"}</b>{d.unread > 0 && <span className="ml-2 rounded-full bg-red-600 px-2 py-0.5 font-bold" data-testid="op-unread">{d.unread} nuove</span>}</div>
      </div>
      <div className="mx-auto max-w-md space-y-3 p-4">
        {view === "home" && <>
          <Big onClick={checkin} className={o.presente ? "bg-emerald-100 text-emerald-800" : "bg-emerald-600 text-white"} data-testid="op-checkin"><CheckCircle2 className="h-6 w-6" />{o.presente ? "SONO IN POSTAZIONE ✓ (tocca per uscire)" : "SONO IN POSTAZIONE"}</Big>
          <Big onClick={() => setView("report")} className="bg-red-600 text-white" data-testid="op-new-report"><Siren className="h-6 w-6" />INVIA SEGNALAZIONE</Big>
          <Big onClick={() => setView("mine")} className="bg-white text-slate-900 ring-1 ring-slate-200" data-testid="op-mine-btn"><ClipboardList className="h-6 w-6" />I MIEI INTERVENTI{mineOpen > 0 && <span className="rounded-full bg-red-600 px-2 text-sm text-white">{mineOpen}</span>}</Big>
          <Big onClick={() => setView("msgs")} className="bg-white text-slate-900 ring-1 ring-slate-200" data-testid="op-msgs-btn"><MessageSquare className="h-6 w-6" />MESSAGGI</Big>
          {d.centrale_tel ? <a href={`tel:${d.centrale_tel}`} className="flex min-h-[64px] items-center justify-center gap-3 rounded-2xl bg-slate-900 text-base font-bold text-white" data-testid="op-call-cr"><Phone className="h-6 w-6" />CHIAMA CONTROL ROOM</a>
            : <div className="rounded-2xl bg-white p-4 text-center text-sm text-slate-500" data-testid="op-call-cr-missing">Numero Control Room non indicato: usa la radio</div>}
          <p className="text-center text-[11px] text-slate-400">In caso di emergenza sanitaria chiama sempre il 112. Accesso personale valido fino al {new Date(d.expires_at).toLocaleDateString("it-IT")}.</p>
        </>}
        {view === "report" && <Report d={d} post={d.post} send={send} back={() => setView("home")} />}
        {view === "mine" && <Mine d={d} act={act} upload={upload} back={() => setView("home")} />}
        {view === "msgs" && <Msgs d={d} token={token} reload={load} back={() => setView("home")} />}
      </div>
    </div>
  );
}
