import asyncio, traceback
import server as s


async def main():
    res = []
    def ok(n, c, e=""):
        res.append((n, bool(c), e))

    await s._ensure_credits_setup()

    # 1. Catalogo configurato coi costi richiesti + attivo
    want = {"ai_assistant": 1, "ai_content": 2, "ai_briefing": 3, "ai_analysis": 5, "ai_checklist": 5, "image_generation": 5}
    for k, cost in want.items():
        svc = await s.db.credit_services.find_one({"key": k}, {"_id": 0})
        ok(f"catalogo {k} = {cost} crediti, attivo", svc and svc["unit_cost"] == cost and svc["active"], f"got {svc and svc.get('unit_cost')} active={svc and svc.get('active')}")
    # Google Calendar: presente, costo/consumo disattivato
    gc = await s.db.credit_services.find_one({"key": "google_calendar"}, {"_id": 0})
    ok("google_calendar presente, consumo disattivato (unit_cost None)", gc and gc.get("unit_cost") is None)
    # Non attivi: newsletter/whatsapp/sms/automation
    for k in ("newsletter_email", "whatsapp_send", "sms_send", "automation_run"):
        svc = await s.db.credit_services.find_one({"key": k}, {"_id": 0})
        ok(f"{k} NON attivo/consumo off", svc and (not svc.get("active") or svc.get("unit_cost") is None))

    # setup org di test
    oid, uid, oid2 = "org_fe_A", "user_fe", "org_fe_B"
    for o in (oid, oid2):
        await s.db.credit_ledger.delete_many({"org_id": o})
        await s.db.organizations.delete_many({"id": o})
        await s.db.organizations.insert_one({"id": o, "nome": f"Org {o}", "type": "cliente", "status": "active", "created_at": s.now_iso(), "updated_at": s.now_iso()})
        await s._ensure_org_credits(o)
    await s._apply_credit_movement(oid, 10, reason_code="manual_adjustment", type_="adjustment", note="seed")
    await s._apply_credit_movement(oid2, 10, reason_code="manual_adjustment", type_="adjustment", note="seed")

    bal0 = (await s._ensure_org_credits(oid))["balance"]

    # 2. reserve -> settle (successo) su ai_content (2)
    r = await s._charge_begin(oid, "ai_content", user_id=uid, event_id="evt1")
    ok("reserve ai_content crea pending -2", r and r["status"] == "pending" and r["amount"] == -2)
    balR = (await s._ensure_org_credits(oid))["balance"]
    ok("dopo reserve saldo scende (10->8) e reserved=2", balR == bal0 - 2)
    await s._credits_settle(r["id"])
    balS = (await s._ensure_org_credits(oid))["balance"]
    led = await s.db.credit_ledger.find_one({"id": r["id"]}, {"_id": 0})
    ok("settle commit: saldo 8, ledger committed -2, event_id+user_id", balS == 8 and led["status"] == "committed" and led["event_id"] == "evt1" and led["user_id"] == uid)

    # 3. reserve -> release (errore): nessun addebito
    r2 = await s._charge_begin(oid, "ai_content", user_id=uid)
    await s._credits_release(r2["id"])
    balRel = (await s._ensure_org_credits(oid))["balance"]
    led2 = await s.db.credit_ledger.find_one({"id": r2["id"]}, {"_id": 0})
    ok("release: saldo torna 8, ledger released (nessun addebito)", balRel == 8 and led2["status"] == "released")

    # 4. saldo insufficiente -> 402, nessuna esecuzione
    # porto il saldo a 3 e provo ai_analysis (5)
    await s._apply_credit_movement(oid, -(balRel - 3), reason_code="manual_adjustment", type_="adjustment", note="set 3")
    insufficient = False
    try:
        await s._charge_begin(oid, "ai_analysis", user_id=uid)
    except s.HTTPException as he:
        insufficient = (he.status_code == 402)
    ok("saldo insufficiente -> HTTP 402, servizio non eseguito", insufficient)
    ok("saldo invariato dopo 402 (resta 3)", (await s._ensure_org_credits(oid))["balance"] == 3)

    # 5. idempotenza (doppia richiesta con stessa key)
    await s._apply_credit_movement(oid, 20, reason_code="manual_adjustment", type_="adjustment", note="top up")  # saldo 23
    k = "idem-test-1"
    a = await s._charge_begin(oid, "ai_briefing", user_id=uid, idempotency_key=k)
    b = await s._charge_begin(oid, "ai_briefing", user_id=uid, idempotency_key=k)
    ok("idempotenza: stessa key -> stessa prenotazione", a["id"] == b["id"])
    await s._credits_settle(a["id"])
    cnt = await s.db.credit_ledger.count_documents({"org_id": oid, "idempotency_key": k})
    ok("idempotenza: un solo movimento in ledger", cnt == 1)

    # 6. servizio disattivato -> _charge_begin ritorna None (gratis), nessun addebito
    balBefore = (await s._ensure_org_credits(oid))["balance"]
    none_res = await s._charge_begin(oid, "whatsapp_send", user_id=uid)
    ok("servizio non attivo -> gratis (None), nessun addebito", none_res is None and (await s._ensure_org_credits(oid))["balance"] == balBefore)
    gc_res = await s._charge_begin(oid, "google_calendar", user_id=uid)
    ok("google_calendar -> gratis (None)", gc_res is None)

    # 7. isolamento multi-tenant
    ok("isolamento: saldo org B invariato (10)", (await s._ensure_org_credits(oid2))["balance"] == 10)

    # 8. modifica costo dal Super Admin vale per operazioni successive
    await s.db.credit_services.update_one({"key": "ai_content"}, {"$set": {"unit_cost": 4, "updated_at": s.now_iso()}})
    info = await s._credit_service_cost("ai_content", 1)
    ok("modifica costo Super Admin: nuova op costa 4", info["cost"] == 4 and led["amount"] == -2)  # storico precedente resta -2
    await s.db.credit_services.update_one({"key": "ai_content"}, {"$set": {"unit_cost": 2, "updated_at": s.now_iso()}})

    # cleanup
    for o in (oid, oid2):
        await s.db.credit_ledger.delete_many({"org_id": o})
        await s.db.organizations.delete_many({"id": o})

    print("\n===== TEST FASE E (consumo crediti) =====")
    allok = True
    for n, c_, e in res:
        allok = allok and c_
        print(f"[{'PASS' if c_ else 'FAIL'}] {n}  {e}")
    print("=====", "TUTTI PASSATI" if allok else "CI SONO FAIL", "=====")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        traceback.print_exc()
