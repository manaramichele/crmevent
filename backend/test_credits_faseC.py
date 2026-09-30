import asyncio, traceback
import server as s


async def main():
    res = []
    def ok(n, c, e=""):
        res.append((n, bool(c), e))

    oidA, oidB = "org_fc_A", "org_fc_B"
    for oid in (oidA, oidB):
        await s.db.credit_ledger.delete_many({"org_id": oid})
        await s.db.credit_purchases.delete_many({"org_id": oid})
        await s.db.invoices.delete_many({"org_id": oid})
        await s.db.organizations.delete_many({"id": oid})
    await s._ensure_credits_setup()
    await s._ensure_credit_packages_seeded()
    await s._ensure_credit_purchases_setup()

    now = s.now_iso()
    for oid in (oidA, oidB):
        await s.db.organizations.insert_one({"id": oid, "nome": f"Org {oid}", "type": "cliente", "status": "active",
            "billing": {"paese": "IT", "ragione_sociale": f"Ragione {oid}", "partita_iva": "01234567890"},
            "subscription": {"status": "trial"}, "created_at": now, "updated_at": now})
        await s._grant_signup_bonus(oid, oid)

    # pacchetto €100 => 500 + 50 bonus = 550
    pkg = await s.db.credit_packages.find_one({"price": 100}, {"_id": 0})
    ok("pacchetto €100 = 550 (500+50)", pkg and pkg["credits_total"] == 550 and pkg["credits_base"] == 500 and pkg["credits_bonus"] == 50)

    net = float(pkg["price"]); base = pkg["credits_base"]; bonus = pkg["credits_bonus"]; total = base + bonus
    vat = round(net * s.PRICING_VAT_RATE / 100.0, 2); gross = round(net + vat, 2)
    ok("IVA 22%: €100 + €22 = €122", vat == 22.0 and gross == 122.0, f"vat={vat} gross={gross}")

    SID = "cs_test_fc_1"; PI = "pi_test_fc_1"
    # simula creazione purchase come farebbe /credits/checkout (con snapshot)
    purchase = {"id": "cp_fc_1", "org_id": oidA, "user_id": "uA", "package_id": pkg["id"],
                "package_snapshot": {"price": net, "credits_base": base, "credits_bonus": bonus,
                                     "credits_total": total, "bonus_pct": pkg.get("bonus_pct")},
                "credits_base": base, "credits_bonus": bonus, "credits_total": total,
                "amount_net": net, "amount_vat": vat, "amount_gross": gross, "aliquota_iva": s.PRICING_VAT_RATE,
                "currency": "eur", "stripe_session_id": SID, "stripe_payment_intent": None, "status": "pending",
                "invoice_id": None, "ledger_id": None,
                "billing_snapshot": s._credit_billing_snapshot(await s.db.organizations.find_one({"id": oidA}, {"_id": 0})),
                "created_at": now, "paid_at": None, "updated_at": now}
    await s.db.credit_purchases.insert_one(dict(purchase))

    fake_sess = {"id": SID, "payment_status": "paid", "payment_intent": PI,
                 "metadata": {"kind": "credit_purchase", "org_id": oidA}}

    bal0 = (await s._ensure_org_credits(oidA))["balance"]
    await s._activate_credit_purchase_from_session(fake_sess)
    bal1 = (await s._ensure_org_credits(oidA))["balance"]
    ok("accredito: saldo 100 -> 650 (+550)", bal0 == 100 and bal1 == 650, f"b0={bal0} b1={bal1}")

    led = await s.db.credit_ledger.find({"org_id": oidA, "reason_code": "purchase"}, {"_id": 0}).to_list(50)
    ok("ledger: 1 movimento purchase +550", len(led) == 1 and led[0]["amount"] == 550 and led[0]["type"] == "purchase", f"n={len(led)}")

    p = await s.db.credit_purchases.find_one({"stripe_session_id": SID}, {"_id": 0})
    ok("purchase: stato paid + PI + ledger_id + invoice_id", p["status"] == "paid" and p["stripe_payment_intent"] == PI and p["ledger_id"] and p["invoice_id"])

    inv = await s.db.invoices.find_one({"id": p["invoice_id"]}, {"_id": 0})
    ok("fattura ricarica: imponibile 100, IVA 22, totale 122", inv and inv["imponibile"] == 100 and inv["importo_iva"] == 22.0 and inv["totale"] == 122.0)
    ok("fattura: descrizione 'Ricarica 550 crediti CRMEvent'", inv["descrizione"] == "Ricarica 550 crediti CRMEvent" and inv["kind"] == "credit_recharge")
    ok("fattura: bonus NON aumenta imponibile/IVA (500 base a €100)", inv["credits_base"] == 500 and inv["credits_bonus"] == 50 and inv["imponibile"] == 100)

    # IDEMPOTENZA: webhook duplicato / retry
    await s._activate_credit_purchase_from_session(fake_sess)
    await s._activate_credit_purchase_from_session(fake_sess)
    bal2 = (await s._ensure_org_credits(oidA))["balance"]
    led2 = await s.db.credit_ledger.count_documents({"org_id": oidA, "reason_code": "purchase"})
    inv2 = await s.db.invoices.count_documents({"org_id": oidA, "kind": "credit_recharge"})
    ok("idempotenza: saldo resta 650 dopo webhook duplicati", bal2 == 650, f"b2={bal2}")
    ok("idempotenza: 1 solo ledger e 1 sola fattura", led2 == 1 and inv2 == 1, f"led={led2} inv={inv2}")

    # SNAPSHOT: modifico il pacchetto dopo l'acquisto -> lo storico resta invariato
    await s.db.credit_packages.update_one({"id": pkg["id"]}, {"$set": {"credits_base": 600, "credits_total": 650}})
    p_after = await s.db.credit_purchases.find_one({"stripe_session_id": SID}, {"_id": 0})
    ok("snapshot: acquisto resta 550 anche dopo modifica pacchetto a 650", p_after["credits_total"] == 550 and p_after["package_snapshot"]["credits_total"] == 550)
    await s.db.credit_packages.update_one({"id": pkg["id"]}, {"$set": {"credits_base": 500, "credits_total": 550}})

    # PAGAMENTO NON RIUSCITO / NON PAGATO: nessun accredito
    SID2 = "cs_test_fc_unpaid"
    await s.db.credit_purchases.insert_one({"id": "cp_fc_2", "org_id": oidA, "user_id": "uA", "package_id": pkg["id"],
        "package_snapshot": {}, "credits_base": 100, "credits_bonus": 0, "credits_total": 100,
        "amount_net": 20.0, "amount_vat": 4.4, "amount_gross": 24.4, "aliquota_iva": 22.0, "currency": "eur",
        "stripe_session_id": SID2, "stripe_payment_intent": None, "status": "pending", "invoice_id": None,
        "ledger_id": None, "billing_snapshot": {}, "created_at": now, "paid_at": None, "updated_at": now})
    await s._activate_credit_purchase_from_session({"id": SID2, "payment_status": "unpaid",
        "metadata": {"kind": "credit_purchase", "org_id": oidA}})
    bal3 = (await s._ensure_org_credits(oidA))["balance"]
    p2 = await s.db.credit_purchases.find_one({"stripe_session_id": SID2}, {"_id": 0})
    ok("pagamento non riuscito: nessun accredito, purchase resta pending", bal3 == 650 and p2["status"] == "pending", f"b3={bal3} st={p2['status']}")

    # MULTI-TENANT: l'accredito di A non tocca B
    balB = (await s._ensure_org_credits(oidB))["balance"]
    ok("isolamento multi-tenant: saldo B invariato (100)", balB == 100, f"balB={balB}")

    # SIMULAZIONE FATTURE IN CLOUD (TEST): nessun invio SDI, riga 'Ricarica ...'
    sim = await s._fic_simulate(inv)
    ok("FIC simulazione: imponibile 100, IVA 22 (22%), totale 122, coerente", sim["imponibile"] == 100 and sim["importo_iva"] == 22.0 and sim["totale"] == 122.0 and sim["coerente"])
    line0 = sim["fic_payload_preview"]["data"]["items_list"][0]
    ok("FIC simulazione: riga 'Ricarica 550 crediti CRMEvent'", line0["name"] == "Ricarica 550 crediti CRMEvent" and line0["net_price"] == 100)

    # cleanup
    for oid in (oidA, oidB):
        await s.db.credit_ledger.delete_many({"org_id": oid})
        await s.db.credit_purchases.delete_many({"org_id": oid})
        await s.db.invoices.delete_many({"org_id": oid})
        await s.db.organizations.delete_many({"id": oid})

    print("\n===== TEST FASE C (acquisto crediti) =====")
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
