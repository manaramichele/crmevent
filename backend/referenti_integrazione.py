"""Integrazione delle anagrafiche nei referenti delle Aziende (Super Admin): anteprima, esecuzione con backup, ripristino.
Solo operazioni additive: crea i collegamenti mancanti azienda-contatto e copia Telefono in Cellulare se vuoto. Nessuna cancellazione di contatti."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException


def build(db, deps: dict):
    r = APIRouter(prefix="/api/admin/referenti-integrazione")
    sa, audit = deps["require_superadmin"], deps["record_audit"]

    async def analyze(oid: str) -> dict:
        companies = {c["id"]: c.get("nome") for c in await db.companies.find({"org_id": oid}, {"_id": 0, "id": 1, "nome": 1}).to_list(50000)}
        persons = await db.persons.find({"org_id": oid}, {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "azienda_id": 1, "telefono": 1, "cellulare": 1}).to_list(100000)
        rels = await db.person_companies.find({"org_id": oid}, {"_id": 0, "person_id": 1, "company_id": 1}).to_list(100000)
        staff_ids = set(await db.staff.distinct("person_id", {"org_id": oid}))
        linked = {(x["person_id"], x["company_id"]) for x in rels if x.get("company_id") in companies}
        by_person = {x["person_id"] for x in rels if x.get("company_id") in companies}
        to_link, phone, orphan_ref, senza = [], [], [], []
        for p in persons:
            az = p.get("azienda_id")
            if az and az in companies and (p["id"], az) not in linked:
                to_link.append((p["id"], az))
            is_ref = p["id"] in by_person or (az in companies if az else False)
            if is_ref and p.get("telefono") and not p.get("cellulare"):
                phone.append(p)
            if az and az not in companies:
                orphan_ref.append(p)
            if not is_ref and p["id"] not in staff_ids:
                senza.append(p)
        nome = lambda p: f"{p.get('cognome') or ''} {p.get('nome') or ''}".strip() or "(senza nome)"
        return {"aziende": len(companies), "referenti": len(by_person | {p["id"] for p in persons if p.get("azienda_id") in companies}),
                "collegamenti_da_creare": to_link, "cellulari_da_copiare": phone,
                "azienda_inesistente": [nome(p) for p in orphan_ref][:50], "n_azienda_inesistente": len(orphan_ref),
                "senza_azienda": [nome(p) for p in senza][:50], "n_senza_azienda": len(senza)}

    async def report():
        out = []
        for o in await db.organizations.find({}, {"_id": 0, "id": 1, "nome": 1}).to_list(5000):
            a = await analyze(o["id"])
            if not (a["aziende"] or a["n_senza_azienda"]):
                continue
            out.append({"org_id": o["id"], "org": o.get("nome"), "aziende": a["aziende"], "referenti": a["referenti"],
                        "collegamenti_da_creare": len(a["collegamenti_da_creare"]), "cellulari_da_copiare": len(a["cellulari_da_copiare"]),
                        "n_azienda_inesistente": a["n_azienda_inesistente"], "azienda_inesistente": a["azienda_inesistente"],
                        "n_senza_azienda": a["n_senza_azienda"], "senza_azienda": a["senza_azienda"]})
        return out

    @r.get("/anteprima")
    async def preview(_: dict = Depends(sa)):
        return {"organizzazioni": await report()}

    @r.post("/esegui")
    async def run(user: dict = Depends(sa)):
        run_id, now = uuid.uuid4().hex, datetime.now(timezone.utc).isoformat()
        backup = {"id": run_id, "created_at": now, "by": user.get("email"), "relazioni_create": [], "cellulari": [], "stato": "in_corso"}
        await db.referenti_integrazione_runs.insert_one(dict(backup))
        tot_rel = tot_tel = 0
        for o in await db.organizations.find({}, {"_id": 0, "id": 1}).to_list(5000):
            a = await analyze(o["id"])
            rel_ids, cells = [], []
            for pid, cid in a["collegamenti_da_creare"]:
                rid = uuid.uuid4().hex
                await db.person_companies.insert_one({"id": rid, "org_id": o["id"], "person_id": pid, "company_id": cid,
                                                      "referente_principale": False, "created_at": now, "origine": "integrazione_referenti"})
                rel_ids.append(rid)
            for p in a["cellulari_da_copiare"]:
                res = await db.persons.update_one({"id": p["id"], "org_id": o["id"], "$or": [{"cellulare": None}, {"cellulare": ""}, {"cellulare": {"$exists": False}}]},
                                                  {"$set": {"cellulare": p["telefono"]}})
                if res.modified_count:
                    cells.append({"id": p["id"], "org_id": o["id"], "prima": p.get("cellulare"), "copiato": p["telefono"]})
            if rel_ids or cells:
                await db.referenti_integrazione_runs.update_one({"id": run_id}, {"$push": {"relazioni_create": {"$each": rel_ids}, "cellulari": {"$each": cells}}})
            tot_rel += len(rel_ids)
            tot_tel += len(cells)
        rep = await report()
        await db.referenti_integrazione_runs.update_one({"id": run_id}, {"$set": {"stato": "completato", "collegamenti_creati": tot_rel, "cellulari_copiati": tot_tel, "report_dopo": rep}})
        await audit(user, "referenti_integrazione", detail=f"run={run_id} collegamenti={tot_rel} cellulari={tot_tel}")
        return {"run_id": run_id, "collegamenti_creati": tot_rel, "cellulari_copiati": tot_tel, "organizzazioni": rep}

    @r.get("/esecuzioni")
    async def runs(_: dict = Depends(sa)):
        return await db.referenti_integrazione_runs.find({}, {"_id": 0, "relazioni_create": 0, "cellulari": 0, "report_dopo": 0}).sort("created_at", -1).to_list(50)

    @r.post("/ripristina/{run_id}")
    async def restore(run_id: str, user: dict = Depends(sa)):
        b = await db.referenti_integrazione_runs.find_one({"id": run_id}, {"_id": 0})
        if not b:
            raise HTTPException(status_code=404, detail="Esecuzione non trovata")
        if b.get("stato") == "ripristinato":
            raise HTTPException(status_code=400, detail="Esecuzione già ripristinata")
        d = await db.person_companies.delete_many({"id": {"$in": b["relazioni_create"]}, "origine": "integrazione_referenti"})
        n = 0
        for c in b["cellulari"]:
            res = await db.persons.update_one({"id": c["id"], "org_id": c["org_id"], "cellulare": c["copiato"]}, {"$set": {"cellulare": c.get("prima")}})
            n += res.modified_count
        await db.referenti_integrazione_runs.update_one({"id": run_id}, {"$set": {"stato": "ripristinato", "ripristinato_at": datetime.now(timezone.utc).isoformat()}})
        await audit(user, "referenti_integrazione_ripristino", detail=f"run={run_id}")
        return {"collegamenti_rimossi": d.deleted_count, "cellulari_ripristinati": n}

    return {"router": r}
