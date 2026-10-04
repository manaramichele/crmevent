import sys
sys.path.insert(0, "/app/backend")
from server import _derive_amounts, _stripe_vat_cents


def approx(a, b):
    return abs(a - b) <= 0.01


# 1) The reported production bug: stored iva=0 but net/total imply 22% VAT.
a = _derive_amounts({"imponibile": 19.90, "iva": 0.0, "totale": 24.28})
assert approx(a["imponibile"], 19.90), a
assert approx(a["importo_iva"], 4.38), a
assert a["aliquota_iva"] == 22.0, a
assert approx(a["totale"], 24.28), a
assert a["coerente"] is True, a
print("Case 1 (bug repro) OK:", a)

# 2) Stripe modern invoice: tax under total_taxes array, legacy `tax` missing.
inv = {"subtotal": 1990, "total": 2428, "total_taxes": [{"amount": 438}]}
assert _stripe_vat_cents(inv) == 438
print("Case 2 (total_taxes) OK: 438 cents")

# 3) Stripe with no tax info at all -> derive from total - subtotal.
inv2 = {"subtotal": 1990, "total": 2428}
assert _stripe_vat_cents(inv2) is None
print("Case 3 (no tax field) OK: None -> fallback to total-subtotal")

# 4) Coherence guard: already-correct record stays untouched.
a4 = _derive_amounts({"imponibile": 100.0, "importo_iva": 22.0, "totale": 122.0, "aliquota_iva": 22.0})
assert approx(a4["importo_iva"], 22.0) and a4["coerente"], a4
print("Case 4 (already coherent) OK:", a4)

print("\nALL TESTS PASSED")
