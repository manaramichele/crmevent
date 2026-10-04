"""Idempotent Stripe catalog setup for CRMEvent (test mode).
Creates a single product 'CRMEvent' with two recurring EUR prices:
- crmevent_monthly: 19,90 €/month
- crmevent_yearly: 199 €/year
Run: python setup_stripe.py
"""
import os
from pathlib import Path
from dotenv import load_dotenv
import stripe

load_dotenv(Path(__file__).parent / ".env")
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or "sk_test_emergent"

PRODUCT_KEY = "crmevent_plan"
PRICES = [
    {"lookup_key": "crmevent_monthly", "amount": 1990, "currency": "eur", "interval": "month"},
    {"lookup_key": "crmevent_yearly", "amount": 19900, "currency": "eur", "interval": "year"},
]


def get_or_create_product():
    for p in stripe.Product.list(active=True, limit=100).auto_paging_iter():
        if p.to_dict().get("metadata", {}).get("emergent_product_id") == PRODUCT_KEY:
            return p
    return stripe.Product.create(name="CRMEvent", tax_code="txcd_10103001",
                                 metadata={"managed_by": "emergent", "emergent_product_id": PRODUCT_KEY})


def ensure_price(product, p):
    existing = stripe.Price.list(lookup_keys=[p["lookup_key"]], active=True, limit=1).data
    if existing and (existing[0].unit_amount != p["amount"] or existing[0].currency != p["currency"]):
        stripe.Price.modify(existing[0].id, active=False)
        existing = []
    if not existing:
        stripe.Price.create(product=product.id, unit_amount=p["amount"], currency=p["currency"],
                            lookup_key=p["lookup_key"], transfer_lookup_key=True,
                            recurring={"interval": p["interval"]})
        return "created"
    return "exists"


if __name__ == "__main__":
    prod = get_or_create_product()
    print("product:", prod.id, prod.name)
    for p in PRICES:
        print(p["lookup_key"], ensure_price(prod, p))
    print("done")
