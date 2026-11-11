"""Preferenze volontari: lettura dalla Raccolta disponibilità (per evento), mansione rapida/multipla, recupero retroattivo con anteprima, backup e report."""
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel


def _now():
    return datetime.now(timezone.utc).isoformat()


def pref_label(av: dict) -> Optional[str]:
    p = (av.get("preferenza_attivita") or "").strip()
    if p == "Altro" and (av.get("preferenza_altro") or "").strip():
        return f"Altro: {av['preferenza_altro'].strip()}"
    return p or None


class MansioneIn(BaseModel):
    person_ids: List[str]
    mansione: str
    evento_id: Optional[str] = None


class RunIn(BaseModel):
    org_id: Optional[str] = None


def build(db, deps: dict):
    r = APIRouter(prefix="/api")
    require_admin, require_superadmin, audit = deps["require_admin"], deps["require_superadmin"], deps["record_audit"]

    async def latest_avs(org_id: str, person_ids: Optional[list] = None) -> dict:
        """(persona_id, evento_id) -> risposta più recente (le altre restano nello storico)."""
        q = {"org_id": org_id, **({"persona_id": {"$in": person_ids}} if person_ids is not None else {})}
        out = {}
        async for a in db.availabilities.find(q, {"_id": 0, "id": 1, "persona_id": 1, "evento_id": 1, "preferenza_attivita": 1, "preferenza_altro": 1,
                                                  "stato": 1, "updated_at": 1, "created_at": 1}):
            k = (a.get("persona_id"), a.get("evento_id"))
            if k not in out or (a.get("updated_at") or a.get("created_at") or "") > (out[k].get("updated_at") or out[k].get("created_at") or ""):
                out[k] = a
        return out

    async def prefs_for(org_id: str, person_ids: Optional[list] = None) -> dict:
        evn = {e["id"]: e.get("nome") for e in await db.events.find({"org_id": org_id}, {"_id": 0, "id": 1, "nome": 1}).to_list(5000)}
        out = defaultdict(list)
        for (pid, eid), a in (await latest_avs(org_id, person_ids)).items():
            out[pid].append({"evento_id": eid, "evento_nome": evn.get(eid), "preferenza": pref_label(a), "availability_id": a["id"], "stato": a.get("stato")})
        return out

    @r.post("/persons/mansione-bulk")
    async def mansione_bulk(body: MansioneIn, admin: dict = Depends(require_admin)):
        """Assegna solo la mansione (ruolo operativo). Non crea ruoli, non cambia categoria/team/turni né la preferenza."""
        st = await db.settings.find_one({"id": admin["org_id"]}, {"_id": 0, "ruoli_staff": 1}) or {}
        if body.mansione not in (st.get("ruoli_staff") or []):
            raise HTTPException(status_code=400, detail="Mansione non presente tra i ruoli dell'organizzazione")
        links = persons = 0
        for pid in body.person_ids[:1000]:
            q = {"org_id": admin["org_id"], "persona_id": pid, **({"evento_id": body.evento_id} if body.evento_id else {})}
            res = await db.staff.update_many(q, {"$set": {"ruolo": body.mansione, "updated_at": _now()}})
            if res.matched_count:
                links += res.matched_count
            else:
                persons += (await db.persons.update_one({"org_id": admin["org_id"], "id": pid}, {"$set": {"ruolo": body.mansione, "updated_at": _now()}})).matched_count
        await audit(admin, "persons_mansione_bulk", detail=f"{body.mansione} · {len(body.person_ids)} persone")
        return {"ok": True, "partecipazioni": links, "anagrafiche": persons}

    # ---------- recupero retroattivo (Super Admin) ----------
    async def run(org_id: str, apply: bool, by: str) -> dict:
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "id": 1, "nome": 1, "name": 1})
        if not org:
            raise HTTPException(status_code=404, detail="Organizzazione non trovata")
        evn = {e["id"]: e.get("nome") for e in await db.events.find({"org_id": org_id}, {"_id": 0, "id": 1, "nome": 1}).to_list(5000)}
        persons = {p["id"]: p for p in await db.persons.find({"org_id": org_id}, {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "email": 1, "cellulare": 1}).to_list(100000)}
        by_mail = {(p.get("email") or "").lower(): p["id"] for p in persons.values() if p.get("email")}
        by_cell = {p.get("cellulare"): p["id"] for p in persons.values() if p.get("cellulare")}
        avs = await db.availabilities.find({"org_id": org_id}, {"_id": 0}).to_list(100000)
        rep = {"organizzazione": org.get("nome") or org.get("name"), "org_id": org_id, "disponibilita_esaminate": len(avs), "preferenze_recuperate": 0,
               "preferenze_collegate": 0, "confermati_aggiornati": 0, "classificati_aggiornati": 0, "con_team_o_turni_aggiornati": 0,
               "partecipazioni_gia_corrette": 0, "da_classificare_con_preferenza": 0, "non_recuperabili": [], "anomalie": [],
               "stati": defaultdict(int), "ruolo_evento": defaultdict(int), "simulazione": not apply}
        groups = defaultdict(list)
        for a in avs:
            rep["stati"][a.get("stato") or "nuova"] += 1
            rep["ruolo_evento"][a.get("ruolo_evento") or "da_definire"] += 1
            pid = a.get("persona_id") if a.get("persona_id") in persons else None
            if not pid:
                pid = by_mail.get((a.get("email") or "").lower()) or by_cell.get(a.get("cellulare"))
                rep["anomalie"].append({"tipo": "collegamento persona ricostruito" if pid else "persona non trovata",
                                        "nome": f"{a.get('cognome') or ''} {a.get('nome') or ''}".strip(), "evento": evn.get(a.get("evento_id")), "availability_id": a["id"]})
                if pid and apply:
                    await db.availabilities.update_one({"org_id": org_id, "id": a["id"]}, {"$set": {"persona_id": pid, "persona_id_originale": a.get("persona_id")}})
            if pid:
                groups[(pid, a.get("evento_id"))].append(a)
        run_id = uuid.uuid4().hex
        for (pid, eid), lst in groups.items():
            lst.sort(key=lambda x: x.get("updated_at") or x.get("created_at") or "", reverse=True)
            a = lst[0]
            p = persons[pid]
            name = f"{p.get('cognome') or ''} {p.get('nome') or ''}".strip()
            if len(lst) > 1:
                rep["anomalie"].append({"tipo": f"{len(lst)} risposte per lo stesso evento: usata la più recente", "nome": name, "evento": evn.get(eid)})
            pref = pref_label(a)
            if not pref:
                rep["non_recuperabili"].append({"nome": name, "evento": evn.get(eid), "motivo": "Non indicata nel modulo"})
                continue
            rep["preferenze_recuperate"] += 1
            links = await db.staff.find({"org_id": org_id, "persona_id": pid, "evento_id": eid}, {"_id": 0}).to_list(50)
            if not links:
                rep["preferenze_collegate"] += 1  # mostrata da Raccolta disponibilità sulla persona (Da classificare)
                rep["da_classificare_con_preferenza"] += 1
                continue
            has_shift = await db.shifts.count_documents({"org_id": org_id, "persona_id": pid, "evento_id": eid}) > 0
            for s in links:
                rep["preferenze_collegate"] += 1
                if s.get("preferenza_volontario") == pref and s.get("preferenza_av_id") == a["id"]:
                    rep["partecipazioni_gia_corrette"] += 1
                    continue
                if a.get("stato") == "confermata":
                    rep["confermati_aggiornati"] += 1
                if s.get("categoria") in ("staff", "volontario", "collaboratore"):
                    rep["classificati_aggiornati"] += 1
                if s.get("team_id") or has_shift:
                    rep["con_team_o_turni_aggiornati"] += 1
                if apply:
                    await db.backup_avail_prefs.insert_one({"run_id": run_id, "org_id": org_id, "staff_id": s["id"], "at": _now(),
                                                            "prev": {k: s.get(k) for k in ("preferenza_volontario", "preferenza_av_id", "preferenza_sync_at")}})
                    await db.staff.update_one({"org_id": org_id, "id": s["id"]},
                                              {"$set": {"preferenza_volontario": pref, "preferenza_av_id": a["id"], "preferenza_sync_at": _now()}})
        rep["stati"], rep["ruolo_evento"] = dict(rep["stati"]), dict(rep["ruolo_evento"])
        if apply:
            rep["run_id"] = run_id
            await db.avail_prefs_runs.insert_one({**rep, "id": run_id, "by": by, "at": _now()})
            rep.pop("_id", None)
        return rep

    async def target_orgs(body: RunIn) -> list:
        if body.org_id:
            return [body.org_id]
        return list({x for x in await db.availabilities.distinct("org_id") if x})

    @r.post("/platform/avail-prefs/preview")
    async def preview(body: RunIn, sa: dict = Depends(require_superadmin)):
        return {"reports": [await run(o, False, sa.get("email")) for o in await target_orgs(body)]}

    @r.post("/platform/avail-prefs/apply")
    async def apply(body: RunIn, sa: dict = Depends(require_superadmin)):
        reps = [await run(o, True, sa.get("email")) for o in await target_orgs(body)]
        await audit(sa, "avail_prefs_apply", detail=f"{len(reps)} organizzazioni")
        return {"reports": reps}

    @r.get("/platform/avail-prefs/orgs")
    async def orgs(sa: dict = Depends(require_superadmin)):
        ids = [x for x in await db.availabilities.distinct("org_id") if x]
        out = []
        for o in await db.organizations.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "nome": 1, "name": 1}).to_list(1000):
            out.append({"id": o["id"], "nome": o.get("nome") or o.get("name"), "disponibilita": await db.availabilities.count_documents({"org_id": o["id"]})})
        return {"orgs": sorted(out, key=lambda x: (x["nome"] or "").lower())}

    return {"router": r, "prefs_for": prefs_for}
