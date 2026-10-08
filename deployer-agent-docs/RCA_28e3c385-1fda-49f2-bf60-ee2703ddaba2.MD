# RCA — Verifica read-only dati PRODUZIONE CRMEvent (org "MASSIMO GHEZZI")

Deployment: manage-events-12 (crmevent.it / www.crmevent.it) · active run 28e3c385-1fda-49f2-bf60-ee2703ddaba2
Database letto (prod, risolto server-side da MONGO_URL/DB_NAME): **manage-events-12-test_database**
Modalità: SOLA LETTURA. Nessun deploy, nessuna scrittura.

## Sintesi
Nel database di produzione **non esiste alcuna traccia di un pagamento reale** per l'organizzazione "MASSIMO GHEZZI": nessuno Stripe Customer sul documento org, nessun credit_purchase, nessuna invoice, nessuna voce di ledger di tipo acquisto. I crediti presenti (100) sono il solo bonus di registrazione. Inoltre l'intero DB non contiene **nessun** acquisto/fattura reale (is_test=false): tutte le transazioni presenti sono TEST/simulate.

---

## 1. organizations — doc "ghezzi" (case-insensitive su campo `nome`)
- id: `42ef277ddbab4019940a42f25ee4f1ea`
- nome: MASSIMO GHEZZI
- type: cliente
- subscription: status=**trial**, trial_start=2026-10-02T06:37:25Z, trial_end=2026-10-16T06:37:25Z, plan=crmevent, billing_cycle=null, current_period_end=null, **stripe_customer_id=null**, **stripe_subscription_id=null**
- credits: balance=**100**, lifetime_granted=100, lifetime_spent=0, reserved=0, signup_bonus_granted=true  (il modello usa lifetime_granted/lifetime_spent, non lifetime_purchased)
- billing: nessun sotto-oggetto billing con codice_sdi/pec presente sul documento
- status (top-level)=active · created_at=2026-10-02T06:37:25Z

> NB: il campo nome org è `nome` (non `name`); `name` non esiste → la ricerca iniziale su `name` dava 0.

## 2. credit_purchases con org_id=42ef...1ea → **0 documenti**
(Il campo chiave è correttamente `org_id`; la collection contiene dati — verificato con sample. Zero reale.)

## 3. credit_ledger con org_id=42ef...1ea, type='purchase' → **0 documenti**
Totale voci ledger per questo org = **1** (il grant del signup bonus, coerente con balance 100 / lifetime_granted 100). Nessun acquisto.

## 4. invoices con org_id=42ef...1ea → **0 documenti**
Nessuna fattura (reale o test) per questo org.

## 5. event_purchases con org_id=42ef...1ea → **0 documenti**

## 6. Stripe LIVE (status PaymentIntent/Checkout Session, subscription del customer) → NON ESEGUITO
Non dispongo di alcuno strumento per chiamare le API Stripe. Inoltre il documento org non ha stripe_customer_id, e in DB non esistono session/payment_intent reali associati a questo org. **Da verificare direttamente nel cruscotto Stripe LIVE.**

## 7. Fatture in Cloud (per fic_document_id) → NON ESEGUITO
Nessuno strumento per chiamare le API Fatture in Cloud. Inoltre non esiste alcuna invoice per questo org con un fic_document_id. **Da verificare direttamente in Fatture in Cloud.**

## 8. FIC_MODE in produzione = **live**
Confermato via metadata del secret (matches_expected=true per valore "live"). Valore non rivelato, solo confronto.

## 9. Abbonamenti Stripe reali
- org con subscription.stripe_subscription_id valorizzato E status in (active, past_due, trialing) = **0**
- org con QUALSIASI subscription.stripe_subscription_id valorizzato = **0**
→ Non esiste più alcun abbonamento Stripe reale. Tutti i 6 org hanno stripe_subscription_id=null; status presenti: interna, test, trial.

---

## Contesto ambiente / dati (evidenza aggiuntiva)
- Secret CRMEVENT_STRIPE_MODE = **live** (matches_expected=true); FIC_MODE = **live**. (STRIPE_MODE piattaforma Emergent ≠ live, non pertinente ai pagamenti CRMEvent.)
- Nonostante le modalità live, **tutte** le credit_purchases/invoices presenti nel DB sono `is_test=true`, con stripe id `TEST-...`, `fic_simulated=true`, `fic_stato_documento/fic_stato_sdi = "simulato_test"`. Sono residui di flussi TEST, non pagamenti reali.
- Conteggi globali: credit_purchases con is_test=false = **0**; invoices con is_test=false = **0**.

## Conferma sulle ipotesi del richiedente
(a) Stato "Trial" = organizations.subscription.status (modello legacy ad abbonamento). CONFERMATO sui dati: lo status resta "trial" e non c'è nulla nei crediti/acquisti che lo aggiorni. I 6 org mostrano solo status legacy (trial/test/interna) e zero stripe_subscription_id.
(b) In live il doc viene creato su FIC con fic_stato_sdi='non_inviato' e non si chiama /e_invoice/send: **NON confermabile sui dati reali** perché nel DB non esiste alcuna invoice live (fic_mode live) — le uniche invoice presenti sono simulate (fic_stato_sdi="simulato_test"). Serve una fattura live reale per osservare il valore 'non_inviato'.

## Discrepanza da segnalare
Il richiedente riferisce che la schermata Super Admin mostra per GHEZZI "ha uno Stripe Customer" e "Fatturazione=non_inviato". Entrambi NON sono riscontrabili in questo DB di produzione: stripe_customer_id=null e nessuna invoice. Possibili spiegazioni da chiarire col richiedente: (i) la colonna "Stripe Customer"/"Fatturazione" dell'endpoint /api/platform/subscriptions è calcolata da una fonte diversa dal campo org.subscription; (ii) il pagamento/fattura esistono solo lato Stripe/FIC e non sono mai stati persistiti in questo DB (webhook non arrivato/non elaborato); (iii) ciò che il cliente ha visto proviene da un ambiente/DB diverso. Il DB attivo che serve crmevent.it è questo (manage-events-12-test_database).
