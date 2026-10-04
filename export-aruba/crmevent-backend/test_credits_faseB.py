import asyncio, traceback
import server as s


async def main():
    res = []
    def ok(n, c, e=""):
        res.append((n, bool(c), e))

    oid = "org_tb_engine"
    await s.db.events.delete_many({"org_id": oid})
    await s.db.credit_ledger.delete_many({"org_id": oid})
    await s.db.organizations.delete_many({"id": oid})
    await s._ensure_credits_setup()
    await s._ensure_credit_packages_seeded()

    now = s.now_iso()
    await s.db.organizations.insert_one({"id": oid, "nome": "TB", "type": "cliente", "status": "active",
                                         "subscription": {"status": "trial"}, "created_at": now, "updated_at": now})
    await s._grant_signup_bonus(oid, "TB")
    # attiva un servizio flat da 10 crediti per i test motore
    await s.db.credit_services.update_one({"key": "ai_briefing"}, {"$set": {"active": True, "unit_cost": 10, "pricing_mode": "flat"}})

    # estimate
    est = await s._credit_service_cost("ai_briefing", 1)
    ok("estimate costo=10 configurato", est["cost"] == 10 and est["configured"])

    # reserve -> saldo 90, reserved 10
    r = await s._credits_reserve(oid, "ai_briefing", 1, user_id="u1")
    c = await s._ensure_org_credits(oid)
    ok("reserve: balance 90 reserved 10 pending", c["balance"] == 90 and c["reserved"] == 10 and r["status"] == "pending", f"b={c['balance']} res={c['reserved']}")

    # settle -> committed, reserved 0, spent 10
    st = await s._credits_settle(r["id"])
    c = await s._ensure_org_credits(oid)
    ok("settle: reserved 0 spent 10 committed", c["reserved"] == 0 and c["lifetime_spent"] == 10 and st["status"] == "committed", f"res={c['reserved']} spent={c['lifetime_spent']}")

    # reserve + release -> saldo torna 90
    r2 = await s._credits_reserve(oid, "ai_briefing", 1, user_id="u1")
    rel = await s._credits_release(r2["id"])
    c = await s._ensure_org_credits(oid)
    ok("release: rimborso, reserved 0, released", c["balance"] == 90 and c["reserved"] == 0 and rel["status"] == "released", f"b={c['balance']} res={c['reserved']}")

    # settle idempotente
    st2 = await s._credits_settle(r["id"])
    ok("settle idempotente", st2["status"] == "committed")

    # idempotenza reserve (stessa key -> una sola prenotazione)
    k = "idem_reserve_1"
    a = await s._credits_reserve(oid, "ai_briefing", 1, user_id="u1", idempotency_key=k)
    b = await s._credits_reserve(oid, "ai_briefing", 1, user_id="u1", idempotency_key=k)
    c = await s._ensure_org_credits(oid)
    n = await s.db.credit_ledger.count_documents({"org_id": oid, "idempotency_key": k})
    ok("idempotenza reserve", a["id"] == b["id"] and n == 1, f"n={n}")
    await s._credits_release(a["id"])

    # concorrenza: 20 reserve simultanee da 10 crediti su saldo 90 -> max 9 riescono
    c0 = await s._ensure_org_credits(oid)
    async def try_reserve(i):
        try:
            await s._credits_reserve(oid, "ai_briefing", 1, user_id=f"c{i}")
            return True
        except s.HTTPException:
            return False
    outs = await asyncio.gather(*[try_reserve(i) for i in range(20)])
    succ = sum(outs)
    c = await s._ensure_org_credits(oid)
    ok("concorrenza: nessun negativo", c["balance"] >= 0 and c["balance"] + c["reserved"] == c0["balance"], f"succ={succ} b={c['balance']} res={c['reserved']}")
    ok("concorrenza: esattamente 9 riservate", succ == 9, f"succ={succ} (atteso 9, saldo {c0['balance']}/10)")

    # saldo insufficiente esplicito
    threw = False
    try:
        await s._credits_reserve(oid, "ai_briefing", 999, user_id="u1")
    except s.HTTPException as e:
        threw = e.status_code == 402
    ok("saldo insufficiente -> 402", threw)

    # pacchetti: bonus e totale coerenti
    pkgs = await s.db.credit_packages.find({}, {"_id": 0}).to_list(100)
    tot_ok = all(p["credits_total"] == p["credits_base"] + p["credits_bonus"] for p in pkgs)
    p500 = next((p for p in pkgs if p["price"] == 500), None)
    ok("pacchetti totale=base+bonus", tot_ok and len(pkgs) == 6)
    ok("pacchetto €500 = 2500+500=3000 (+20%)", p500 and p500["credits_total"] == 3000 and p500["bonus_pct"] == 20)

    # reset stato Fase A
    await s.db.credit_services.update_one({"key": "ai_briefing"}, {"$set": {"active": False, "unit_cost": None}})
    await s.db.events.delete_many({"org_id": oid})
    await s.db.credit_ledger.delete_many({"org_id": oid})
    await s.db.organizations.delete_many({"id": oid})

    print("\n===== TEST FASE B (motore + pacchetti) =====")
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
