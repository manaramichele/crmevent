import asyncio, traceback
from datetime import datetime, timezone, timedelta
import server as s


async def main():
    res = []
    def ok(n, c, e=""):
        res.append((n, bool(c), e))

    await s._ensure_credits_setup()
    cfg = await s._event_period_cfg()
    ok("catalogo event_active_period = 20 / 30gg / attivo", cfg["cost"] == 20 and cfg["period_days"] == 30 and cfg["active"], f"{cfg}")

    oid, uid = "org_e2", "u_e2"
    await s.db.credit_ledger.delete_many({"org_id": oid})
    await s.db.events.delete_many({"org_id": oid})
    await s.db.organizations.delete_many({"id": oid})
    await s.db.organizations.insert_one({"id": oid, "nome": "Org E2", "type": "cliente", "status": "active", "created_at": s.now_iso(), "updated_at": s.now_iso()})
    await s._ensure_org_credits(oid)
    await s._apply_credit_movement(oid, 100, reason_code="manual_adjustment", type_="adjustment", note="seed")

    future = (datetime.now(timezone.utc) + timedelta(days=200)).date().isoformat()
    # 1. creazione evento: nessun consumo, stato preparazione
    ev = {"id": "evt_e2_1", "org_id": oid, "nome": "Maratona di Pisa", "data_inizio": future, "credit_state": "preparazione", "created_at": s.now_iso()}
    await s.db.events.insert_one(dict(ev))
    ok("creazione: saldo invariato 100, stato preparazione", (await s._ensure_org_credits(oid))["balance"] == 100)

    # 2. guardia: scrittura operativa bloccata in preparazione
    blocked = False
    try:
        await s._assert_event_operational(oid, "evt_e2_1")
    except s.HTTPException as he:
        blocked = he.status_code == 403
    ok("preparazione: scritture operative bloccate (403)", blocked)

    # 3. attivazione -> -20, attivo, next_renewal +30
    ev = await s.db.events.find_one({"id": "evt_e2_1"}, {"_id": 0})
    await s._charge_event_period(ev, uid, "activate")
    ev = await s.db.events.find_one({"id": "evt_e2_1"}, {"_id": 0})
    ok("attivazione -20 (saldo 80), stato attivo", (await s._ensure_org_credits(oid))["balance"] == 80 and ev["credit_state"] == "attivo")
    ok("attivazione: next_renewal impostato, renewal_count=1, snapshot 20", ev.get("next_renewal_at") and ev["renewal_count"] == 1 and ev["cost_snapshot"] == 20)
    led = await s.db.credit_ledger.find_one({"org_id": oid, "service_key": "event_active_period"}, {"_id": 0})
    ok("ledger: 'Attivazione evento — Maratona di Pisa', -20, event_id", led and led["amount"] == -20 and "Attivazione evento" in led["note"] and led["event_id"] == "evt_e2_1")

    # 4. guardia attivo -> scritture consentite
    allowed = True
    try:
        await s._assert_event_operational(oid, "evt_e2_1")
    except s.HTTPException:
        allowed = False
    ok("attivo: scritture consentite", allowed)

    # 5. rinnovo (forzo next_renewal nel passato) -> -20
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    await s.db.events.update_one({"id": "evt_e2_1"}, {"$set": {"next_renewal_at": past}})
    r = await s.run_event_renewals()
    ok("rinnovo: evt rinnovato, saldo 60", "evt_e2_1" in r["renewed"] and (await s._ensure_org_credits(oid))["balance"] == 60)
    ev = await s.db.events.find_one({"id": "evt_e2_1"}, {"_id": 0})
    ok("rinnovo: renewal_count=2, next_renewal futuro", ev["renewal_count"] == 2 and s._date.fromisoformat(ev["next_renewal_at"][:10]) > datetime.now(timezone.utc).date())

    # 6. idempotenza: stesso periodo non addebita due volte
    dup = await s._apply_credit_movement(oid, -20, reason_code="event_active_period", type_="debit",
                                         service_key="event_active_period", event_id="evt_e2_1",
                                         idempotency_key="event_active:evt_e2_1:2", note="dup")
    ok("idempotenza rinnovo: nessun doppio addebito (saldo resta 60)", (await s._ensure_org_credits(oid))["balance"] == 60)

    # 7. no rinnovo dopo data evento -> concluso
    past_event = {"id": "evt_e2_past", "org_id": oid, "nome": "Evento Passato", "data_inizio": (datetime.now(timezone.utc) - timedelta(days=5)).date().isoformat(),
                  "credit_state": "attivo", "renewal_count": 1, "next_renewal_at": past, "created_at": s.now_iso()}
    await s.db.events.insert_one(dict(past_event))
    r2 = await s.run_event_renewals()
    ok("data evento passata: concluso, nessun addebito", "evt_e2_past" in r2["concluded"] and (await s._ensure_org_credits(oid))["balance"] == 60)

    # 8. saldo insufficiente -> sospeso, nessun addebito parziale
    await s._apply_credit_movement(oid, -(60 - 10), reason_code="manual_adjustment", type_="adjustment", note="drain a 10")  # saldo 10
    ev2 = {"id": "evt_e2_2", "org_id": oid, "nome": "Trail Streghe", "data_inizio": future, "credit_state": "attivo", "renewal_count": 1, "next_renewal_at": past, "created_at": s.now_iso()}
    await s.db.events.insert_one(dict(ev2))
    r3 = await s.run_event_renewals()
    ev2db = await s.db.events.find_one({"id": "evt_e2_2"}, {"_id": 0})
    ok("saldo insufficiente: sospeso, saldo intatto 10, nessun addebito parziale", ev2db["credit_state"] == "sospeso" and (await s._ensure_org_credits(oid))["balance"] == 10)
    ok("saldo mai negativo", (await s._ensure_org_credits(oid))["balance"] >= 0)

    # 9. altri eventi non bloccati: evt_e2_1 resta attivo
    ev1db = await s.db.events.find_one({"id": "evt_e2_1"}, {"_id": 0})
    ok("multi-evento: un evento sospeso non blocca gli altri", ev1db["credit_state"] == "attivo")

    # 10. riattivazione dopo ricarica -> nuovo periodo
    await s._apply_credit_movement(oid, 50, reason_code="purchase", type_="purchase", note="ricarica")  # saldo 60
    ev2db = await s.db.events.find_one({"id": "evt_e2_2"}, {"_id": 0})
    await s._charge_event_period(ev2db, uid, "reactivate")
    ev2db = await s.db.events.find_one({"id": "evt_e2_2"}, {"_id": 0})
    ok("riattivazione: -20 (saldo 40), stato attivo, renewal_count avanzato", (await s._ensure_org_credits(oid))["balance"] == 40 and ev2db["credit_state"] == "attivo" and ev2db["renewal_count"] == 2)

    # 11. servizio avanzato separato (ai_content) non usa il periodo evento
    r4 = await s._charge_begin(oid, "ai_content", user_id=uid, event_id="evt_e2_1")
    await s._credits_settle(r4["id"])
    ok("servizio avanzato separato: -2 (saldo 38)", (await s._ensure_org_credits(oid))["balance"] == 38)

    # 12. modifica costo Super Admin vale per operazioni successive (storico invariato)
    await s.db.credit_services.update_one({"key": "event_active_period"}, {"$set": {"unit_cost": 25}})
    cfg2 = await s._event_period_cfg()
    ok("modifica costo SA: nuovo costo 25 per prossime attivazioni, storico -20 invariato", cfg2["cost"] == 25 and led["amount"] == -20)
    await s.db.credit_services.update_one({"key": "event_active_period"}, {"$set": {"unit_cost": 20}})

    # 13. eventi esistenti (credit_state assente) non bloccati
    await s.db.events.insert_one({"id": "evt_legacy", "org_id": oid, "nome": "Legacy", "data_inizio": future, "created_at": s.now_iso()})
    legacy_ok = True
    try:
        await s._assert_event_operational(oid, "evt_legacy")
    except s.HTTPException:
        legacy_ok = False
    ok("evento legacy (credit_state assente): NON bloccato", legacy_ok)

    # cleanup
    await s.db.credit_ledger.delete_many({"org_id": oid})
    await s.db.events.delete_many({"org_id": oid})
    await s.db.organizations.delete_many({"id": oid})

    print("\n===== TEST FASE E.2 (evento attivo a crediti) =====")
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
