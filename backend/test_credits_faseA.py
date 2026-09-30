import asyncio, traceback
import server as s


async def main():
    results = []
    def ok(name, cond, extra=""):
        results.append((name, bool(cond), extra))

    # cleanup
    for oid in ("org_tc_a", "org_tc_b"):
        await s.db.events.delete_many({"org_id": oid})
        await s.db.credit_ledger.delete_many({"org_id": oid})
        await s.db.organizations.delete_many({"id": oid})

    await s._ensure_credits_setup()

    # 1. creazione org -> 100 crediti (simulo _create_organization via insert + grant)
    now = s.now_iso()
    org = {"id": "org_tc_a", "nome": "TC A", "type": "cliente", "status": "active",
           "owner_user_id": None, "subscription": {"status": "trial"}, "created_at": now, "updated_at": now}
    await s.db.organizations.insert_one(org)
    await s._grant_signup_bonus("org_tc_a", "TC A")
    c = await s._ensure_org_credits("org_tc_a")
    ok("1. creazione org -> 100 crediti", c["balance"] == 100, f"balance={c['balance']}")

    # 2. impossibilita doppio bonus
    await s._grant_signup_bonus("org_tc_a", "TC A")
    c = await s._ensure_org_credits("org_tc_a")
    n_bonus = await s.db.credit_ledger.count_documents({"org_id": "org_tc_a", "reason_code": "signup_bonus"})
    ok("2. no doppio bonus", c["balance"] == 100 and n_bonus == 1, f"balance={c['balance']} bonus_mov={n_bonus}")

    # 3. accredito +50 / addebito -30
    await s._apply_credit_movement("org_tc_a", 50, "manual_adjustment", "adjustment", note="test+50")
    await s._apply_credit_movement("org_tc_a", -30, "ai_briefing", "debit", service_key="ai_briefing")
    c = await s._ensure_org_credits("org_tc_a")
    ok("3. accredito/addebito", c["balance"] == 120, f"balance={c['balance']} (atteso 120)")

    # 4. blocco saldo negativo
    threw = False
    try:
        await s._apply_credit_movement("org_tc_a", -999999, "ai_briefing", "debit")
    except s.HTTPException as e:
        threw = (e.status_code == 402)
    c = await s._ensure_org_credits("org_tc_a")
    ok("4. blocco saldo negativo", threw and c["balance"] == 120, f"threw402={threw} balance={c['balance']}")

    # 5. idempotenza (stessa key applicata una sola volta)
    k = "test_idem_1"
    m1 = await s._apply_credit_movement("org_tc_a", 25, "manual_adjustment", "adjustment", idempotency_key=k)
    m2 = await s._apply_credit_movement("org_tc_a", 25, "manual_adjustment", "adjustment", idempotency_key=k)
    c = await s._ensure_org_credits("org_tc_a")
    n_idem = await s.db.credit_ledger.count_documents({"org_id": "org_tc_a", "idempotency_key": k})
    ok("5. idempotenza", c["balance"] == 145 and n_idem == 1 and m1["id"] == m2["id"], f"balance={c['balance']} mov={n_idem}")

    # 6. isolamento crediti tra org
    org_b = {"id": "org_tc_b", "nome": "TC B", "type": "cliente", "status": "active",
             "owner_user_id": None, "subscription": {"status": "trial"}, "created_at": now, "updated_at": now}
    await s.db.organizations.insert_one(org_b)
    await s._grant_signup_bonus("org_tc_b", "TC B")
    cb = await s._ensure_org_credits("org_tc_b")
    ca = await s._ensure_org_credits("org_tc_a")
    ok("6. isolamento org", cb["balance"] == 100 and ca["balance"] == 145, f"A={ca['balance']} B={cb['balance']}")

    # 7. storico movimenti completo (campi richiesti)
    mv = await s.db.credit_ledger.find_one({"org_id": "org_tc_a", "reason_code": "ai_briefing", "amount": -30}, {"_id": 0})
    fields_ok = mv and all(f in mv for f in ("created_at", "org_id", "user_id", "event_id", "service_key", "amount", "balance_after"))
    ok("7. storico campi movimento", fields_ok, f"mv_keys={sorted(mv.keys()) if mv else None}")

    # 8. catalogo seed 9 servizi, tutti inattivi, google_calendar senza pricing
    svcs = await s.db.credit_services.find({}, {"_id": 0}).to_list(100)
    by = {x["key"]: x for x in svcs}
    seed_ok = len(by) >= 9 and all(not x["active"] for x in svcs)
    gcal = by.get("google_calendar", {})
    gcal_ok = gcal.get("pricing_mode") is None and gcal.get("unit_cost") is None
    ok("8. catalogo 9 servizi inattivi", seed_ok, f"n={len(by)} keys={sorted(by.keys())}")
    ok("8b. google_calendar senza consumo", gcal_ok, f"gcal={gcal.get('pricing_mode')}/{gcal.get('unit_cost')}")

    # cleanup
    for oid in ("org_tc_a", "org_tc_b"):
        await s.db.events.delete_many({"org_id": oid})
        await s.db.credit_ledger.delete_many({"org_id": oid})
        await s.db.organizations.delete_many({"id": oid})

    print("\n===== RISULTATI TEST FASE A (interni) =====")
    allok = True
    for name, cond, extra in results:
        allok = allok and cond
        print(f"[{'PASS' if cond else 'FAIL'}] {name}  {extra}")
    print("=====", "TUTTI PASSATI" if allok else "CI SONO FAIL", "=====")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        traceback.print_exc()
