# CRMEvent — Proposta tecnica: Sistema a Crediti

> Stato: **PROPOSTA** (nessuna modifica a backend/Stripe/Fatture in Cloud in questa fase).
> Obiettivo: definire architettura, schema dati, API, flussi UI e piano di migrazione per passare
> dal modello per-evento (Starter/Professional/Premium) al modello a **crediti a livello di organizzazione**.
> Coerente con i pattern già presenti nel codice: documenti Mongo a dict con `id` + `now_iso()`,
> cataloghi configurabili da DB (come `pricing_plans` + `pricing_history` append-only),
> endpoint Super Admin sotto `/api/platform/*`, accesso org via `memberships`.

---

## 1. Principi guida

1. **Saldo a livello di Organizzazione**, condiviso tra tutti gli utenti/membri dell'org (non per-utente).
2. **100 crediti gratuiti** assegnati una sola volta alla creazione dell'organizzazione.
3. **Nessuna scadenza** dei crediti.
4. **Gestione ordinaria gratuita** (0 crediti): CRUD di Eventi, Persone, Sponsor, Turni, Attività, Checklist, Ospitalità, Pasti, Briefing (creazione manuale), ecc.
5. **Consumo solo per servizi avanzati** ("CRMEvent lavora per te"): IA, generazione contenuti/immagini, briefing automatici, newsletter Brevo, WhatsApp, automazioni.
6. **Catalogo servizi configurabile dal Super Admin senza deploy** (costi in crediti modificabili da UI, come già avviene per i prezzi).
7. **Controllo saldo PRIMA dell'esecuzione** + **impossibilità di saldo negativo** (hold/riserva atomica).
8. **Registro movimenti completo e immutabile** (append-only): data, quantità (segno), causale, servizio, evento, utente, riferimenti.
9. **Predisposizione** per acquisto/ricarica crediti e ricarica automatica (senza attivare Stripe ora).
10. **Avvisi saldo basso** configurabili.
11. **Consumi a quantità** (es. N messaggi WhatsApp, N destinatari newsletter): `costo = unit_cost × quantità`.

---

## 2. Architettura generale

- **Ledger a doppia fase (hold → settle)** per garantire "no saldo negativo" anche in concorrenza:
  1. `reserve` (hold): verifica saldo ≥ costo stimato e crea un movimento `pending` che decrementa il saldo disponibile.
  2. esecuzione del servizio esterno (IA/Brevo/WhatsApp…).
  3. `settle`: se ok, il movimento diventa `committed` (con quantità/costo effettivi, eventuale rettifica); se fallisce, `release` (rimborso della riserva).
- **Saldo derivato + cache**: la fonte di verità è il ledger (somma movimenti committed+pending). Manteniamo un contatore cache `organizations.credits.balance` aggiornato transazionalmente per letture veloci; ricostruibile dal ledger in qualsiasi momento (riconciliazione).
- **Atomicità**: aggiornamento saldo via update condizionato MongoDB (`$inc` con filtro `balance >= cost`) → l'operazione fallisce se non c'è saldo, evitando negativi senza lock espliciti. In alternativa transazioni Mongo se disponibili sul cluster.
- **Idempotenza**: ogni operazione di consumo porta un `idempotency_key` (es. `service_key + request_id`) per evitare doppi addebiti su retry.
- **Service layer dedicato** (`credits_service.py`) con funzioni: `get_balance(org_id)`, `reserve(...)`, `settle(...)`, `release(...)`, `grant(...)`, `charge_simple(...)`. Tutti i servizi avanzati passano da qui.
- **Catalogo in DB** (`credit_services`) letto a runtime → modifiche costi/attivazione senza deploy, con storico append-only (`credit_service_history`).

---

## 3. Schema dati (nuove collection)

### 3.1 `organizations.credits` (campo embedded nell'org — cache + config)
```jsonc
"credits": {
  "balance": 100,               // saldo disponibile (cache derivata dal ledger)
  "reserved": 0,                // crediti attualmente in hold (pending)
  "lifetime_granted": 100,      // totale mai accreditato (statistiche)
  "lifetime_spent": 0,          // totale mai consumato
  "signup_bonus_granted": true, // idempotenza bonus iscrizione
  "low_balance_threshold": 20,  // soglia avviso (configurabile org/superadmin)
  "low_balance_notified_at": null,
  "auto_recharge": {            // PREDISPOSIZIONE (non attivo ora)
    "enabled": false,
    "threshold": 10,
    "amount": 100,
    "payment_method_ref": null
  },
  "updated_at": "ISO"
}
```

### 3.2 `credit_ledger` (movimenti — APPEND-ONLY, mai update distruttivo)
```jsonc
{
  "id": "cl_xxx",
  "org_id": "org_xxx",
  "type": "grant | debit | refund | purchase | adjustment",
  "status": "pending | committed | released",  // per il flusso hold/settle
  "amount": -8,                 // segno: + accredito, - consumo
  "balance_after": 92,          // saldo dopo il movimento (solo su committed)
  "reason_code": "ai_briefing | signup_bonus | whatsapp_send | newsletter_send | purchase | manual_adjustment | refund",
  "service_key": "ai_briefing", // null per grant/purchase/adjustment
  "quantity": 1,                // unità (es. n. messaggi/destinatari)
  "unit_cost": 8,               // costo unitario al momento (snapshot)
  "event_id": "ev_xxx",         // evento collegato (se applicabile)
  "user_id": "user_xxx",        // chi ha avviato l'operazione
  "idempotency_key": "ai_briefing:req_123",
  "meta": { "prompt_preview": "...", "provider": "openai", "ref": "..." },
  "note": "Testo libero (per adjustment superadmin)",
  "created_at": "ISO",
  "settled_at": "ISO"           // quando pending→committed/released
}
```
Indici: `{org_id, created_at desc}`, `{idempotency_key}` unique (parziale), `{org_id, status}`.

### 3.3 `credit_services` (CATALOGO — configurabile Super Admin, no deploy)
```jsonc
{
  "id": "svc_xxx",
  "key": "ai_briefing",            // identificativo stabile usato dal codice
  "name": "Generazione briefing IA",
  "category": "ai | communication | image | automation",
  "description": "Genera un briefing operativo per un settore/zona.",
  "pricing_mode": "flat | per_unit",
  "unit_label": "messaggio | destinatario | immagine | richiesta",
  "unit_cost": 8,                  // crediti (per flat = costo per esecuzione; per_unit = costo per unità)
  "min_units": 1,
  "active": true,                  // on/off senza deploy
  "visible": true,                 // mostrato in UI catalogo pubblico Area Account
  "version": 3,                    // incrementa ad ogni modifica prezzo
  "created_at": "ISO",
  "updated_at": "ISO"
}
```

### 3.4 `credit_service_history` (APPEND-ONLY, audit catalogo — come `pricing_history`)
```jsonc
{ "id","service_key","field","old_value","new_value","changed_by","created_at" }
```

### 3.5 `credit_recharge_orders` (PREDISPOSIZIONE acquisto/ricarica — non collegato a Stripe ora)
```jsonc
{
  "id": "cro_xxx", "org_id", "credits": 100, "amount_net": null, "amount_gross": null,
  "currency": "eur", "status": "draft | pending_payment | paid | failed | canceled",
  "provider": "stripe", "provider_ref": null, "invoice_id": null,
  "created_by": "user_xxx", "created_at": "ISO", "paid_at": null
}
```
> Alla conferma pagamento (fase futura) → `grant` sul ledger + `organizations.credits.balance += credits`.

### 3.6 `credit_packages` (PREDISPOSIZIONE listino ricariche — Super Admin, non pubblicato ora)
```jsonc
{ "id","name":"100 crediti","credits":100,"price_net":null,"active":false,"sort":1,"stripe_price_id":null }
```
> Prezzi volutamente `null` finché non decidiamo il listino (come già fatto per i pacchetti 3/5 eventi).

---

## 4. Modello di consumo (hold/settle + quantità)

Sequenza standard per un servizio avanzato (es. invio newsletter a 500 destinatari):
```
1. cost = svc.unit_cost × quantity           (per_unit)  |  cost = svc.unit_cost (flat)
2. reserve(org_id, service_key, quantity, cost, user_id, event_id, idempotency_key)
   - update atomico:  {org_id, credits.balance >= cost} → $inc balance -cost, reserved +cost
   - se 0 documenti aggiornati → HTTP 402 "Crediti insufficienti" (con saldo e costo)
   - crea ledger {type:debit, status:pending, ...}
3. esecuzione servizio esterno
4a. successo → settle(ledger_id, actual_quantity, actual_cost)
     - se actual_cost < cost: rimborsa differenza ($inc balance +(cost-actual), reserved -cost)
     - ledger → committed, balance_after impostato
4b. errore → release(ledger_id)  ($inc balance +cost, reserved -cost; ledger → released)
```
- **No negativo garantito** dal filtro `credits.balance >= cost` nell'update atomico.
- **Quantità**: `per_unit` gestisce WhatsApp (per messaggio) e newsletter (per destinatario); `flat` per singole azioni IA.
- **Idempotenza**: `idempotency_key` unico impedisce doppio addebito su retry/webhook.

---

## 5. API

### 5.1 Org-side (utenti dell'organizzazione)
| Metodo | Endpoint | Descrizione |
|---|---|---|
| GET | `/api/credits/balance` | Saldo, riservato, soglia, stato auto-ricarica |
| GET | `/api/credits/ledger?limit&cursor&type&event_id` | Storico movimenti paginato (Area Account) |
| GET | `/api/credits/services` | Catalogo servizi attivi+visibili con costi correnti |
| POST | `/api/credits/estimate` | Stima costo `{service_key, quantity}` → `{cost, balance, sufficient}` |
| POST | `/api/credits/recharge-orders` | (PREDISPOSTO) crea ordine ricarica `draft` (no pagamento reale ora) |
| PUT | `/api/credits/settings` | Soglia avviso + toggle auto-ricarica (predisposto) |

> Il **consumo** NON è un endpoint pubblico: avviene internamente quando l'utente lancia un servizio avanzato (es. `POST /api/ai/briefing`), che chiama `credits_service.reserve/settle`.

### 5.2 Super Admin (`/api/platform/*`, `require_superadmin`)
| Metodo | Endpoint | Descrizione |
|---|---|---|
| GET | `/api/platform/credit-services` | Elenco catalogo (incl. inattivi) |
| POST | `/api/platform/credit-services` | Crea servizio |
| PUT | `/api/platform/credit-services/{key}` | Modifica costo/attivazione → scrive `credit_service_history` |
| GET | `/api/platform/credit-services/history` | Storico modifiche catalogo |
| GET | `/api/platform/orgs/{org_id}/credits` | Saldo + ledger di una org |
| POST | `/api/platform/orgs/{org_id}/credits/adjust` | Accredito/storno manuale `{amount, note}` (audit) |
| GET | `/api/platform/credit-packages` / PUT | (PREDISPOSTO) listino ricariche |

### 5.3 Internal helper (usato dai servizi)
`credits_service.charge(org_id, service_key, quantity, user_id, event_id, idempotency_key)` → wrapper reserve+settle per servizi sincroni; reserve/settle separati per servizi asincroni (Brevo/WhatsApp con webhook).

---

## 6. Flussi UI

### 6.1 Area Account (org)
- **Card "Crediti CRMEvent"**: saldo grande, badge "Nessuna scadenza", pulsante **Ricarica crediti** (predisposto, per ora apre modale "presto disponibile"), barra verso la soglia di avviso.
- **Storico movimenti**: tabella paginata (Data · Servizio/Causale · Evento · Utente · Quantità · Crediti +/− · Saldo dopo). Filtri per tipo/evento. Export CSV (fase 2).
- **Impostazioni crediti**: soglia avviso saldo basso; toggle "Ricarica automatica" (disabilitato/coming soon).
- **Avviso saldo basso**: banner non bloccante quando `balance ≤ threshold` + (fase email) notifica una-tantum (`low_balance_notified_at` per non spammare).

### 6.2 Punto di consumo (dentro i moduli)
- Ogni azione a consumo mostra **prima dell'esecuzione** un chip "Costa N crediti" e, al click, un dialog di conferma con `estimate` (costo, saldo attuale, saldo risultante).
- Se saldo insufficiente → dialog "Crediti insufficienti" con CTA **Ricarica** (predisposto). Nessun 500: risposta **402** gestita lato UI.

### 6.3 Super Admin — "Servizi e crediti"
- Nuova sezione (accanto a "Piani e prezzi"): tabella catalogo servizi con costo, modalità (flat/per unità), unità, attivo/visibile, versione.
- Editor inline del costo → salva → scrive storico; toggle attivazione senza deploy.
- Vista per-organizzazione: saldo, ledger, pulsante accredito/storno manuale con causale.

---

## 7. Servizi futuri e mappatura nel catalogo

Esempi di voci `credit_services` (costi da definire dal Super Admin, qui indicativi):
| key | name | mode | unit | note |
|---|---|---|---|---|
| `ai_analysis` | Analisi evento IA | flat | richiesta | "cosa manca / priorità" |
| `ai_briefing` | Generazione briefing | flat | richiesta | per settore/zona |
| `ai_content` | Generazione testi/contenuti | flat | richiesta | post, comunicati |
| `image_generation` | Generazione immagini | per_unit | immagine | Nano Banana/GPT image |
| `newsletter_brevo` | Invio newsletter | per_unit | destinatario | integra Brevo esistente |
| `whatsapp_send` | Invio WhatsApp | per_unit | messaggio | quando disponibile |
| `automation_run` | Esecuzione automazione | flat | esecuzione | promemoria/scadenze |

- I servizi già presenti (Brevo funnel, IA/LLM via Emergent key) verranno **wrappati** dal `credits_service` senza cambiarne la logica interna.
- La gestione ordinaria (CRUD) **non** passa mai dal credits_service → nessun consumo.

---

## 8. Controllo saldo, no-negativo, concorrenza

- **Pre-check** con `/estimate` in UI (esperienza) **+** **enforcement** server-side nell'update atomico (sicurezza).
- **Update condizionato** `update_one({org_id, "credits.balance": {"$gte": cost}}, {"$inc": {...}})` → se `modified_count == 0` ⇒ 402. Questo previene negativi anche con richieste simultanee da più utenti della stessa org.
- **Riserve orfane**: job periodico (cron) che rilascia i `pending` più vecchi di X minuti senza settle (timeout esecuzione servizio).
- **Riconciliazione**: comando admin per ricomputare `balance` dal ledger (committed) e confrontare con la cache.

---

## 9. Piano di migrazione (coordinato, per fasi)

> Nessuna cancellazione dati. Passaggio "big-bang controllato" preceduto da doppia scrittura di sola lettura.

**Fase A — Fondazioni (backend, nessun impatto utente)**
- Creare collection/indici, `credits_service.py`, seed catalogo servizi (inattivi o costi 0), bonus 100 crediti in `_create_organization` (idempotente), endpoint `/api/credits/*` e `/api/platform/credit-services`.
- Backfill: assegnare 100 crediti alle organizzazioni esistenti (grant una-tantum con `signup_bonus_granted`), registrando il movimento nel ledger.

**Fase B — UI crediti (non distruttiva)**
- Aggiungere in Area Account la card saldo + storico (in sola lettura), lasciando ancora visibile il modello per-evento. Aggiungere sezione Super Admin "Servizi e crediti".

**Fase C — Attivazione consumo**
- Wrappare i primi servizi avanzati (IA/briefing) con reserve/settle. Costi attivati dal Super Admin.

**Fase D — Sostituzione modello commerciale**
- `/prezzi`: sostituire la pagina per-evento con pagina **Crediti** (come funzionano, catalogo servizi, FAQ; niente prezzi ricarica finché non definiti). Rimuovere `/prezzi` dal routing o redirect → `/crediti`.
- **Area Account**: rimuovere `EventPlanManager` (per-evento) e lo stato trial per-org; il "gating" non è più per-evento ma per-credito sui servizi avanzati. Gli eventi tornano tutti pienamente operativi (gestione gratuita).
- **/demo (DemoPage)**: aggiornare copy — CTA "Prova CRMEvent gratis" → "Inizia gratuitamente"; rimuovere riferimenti a trial 14 giorni/piani; enfatizzare "100 crediti inclusi".
- Deprecare in lettura (non cancellare) le collection `pricing_plans`, `event_purchases`, `events.entitlement`, `organizations.subscription.*`: restano come storico.

**Fase E — Stripe & Fatture in Cloud (solo su autorizzazione)**
- Riadattare il checkout Stripe da "acquisto evento" a **"acquisto pacchetti crediti"** (`credit_recharge_orders` + `credit_packages`); webhook → grant crediti.
- Fatture in Cloud: fattura per ricarica crediti (descrizione "CRMEvent — Ricarica N crediti", IVA 22%). 
- Auto-ricarica: usare `auto_recharge` + metodo di pagamento salvato.

**Rollback**: fino alla Fase D le due logiche coesistono lato dati; si può tornare indietro disabilitando le UI crediti senza perdita dati.

---

## 10. Sicurezza & edge cases
- Solo membri dell'org (`memberships`) leggono saldo/ledger; scritture di consumo solo tramite servizi autenticati.
- Adjustment manuali: solo Super Admin, sempre tracciati nel ledger con `user_id` e `note`.
- Retry/duplicati: protetti da `idempotency_key` unico.
- Cambi di prezzo catalogo: il costo viene **fotografato** (`unit_cost`/`version`) nel movimento → storico coerente anche se il listino cambia.
- Soglia avviso: notifica una-tantum finché il saldo non risale sopra soglia (reset di `low_balance_notified_at`).

---

## 11. Riepilogo requisiti → soluzione
| Requisito utente | Dove è coperto |
|---|---|
| Saldo org condiviso | §3.1 `organizations.credits`, §5.1 |
| 100 crediti alla registrazione | §9 Fase A (hook `_create_organization`, idempotente) |
| Nessuna scadenza | §1.3 (nessun campo TTL) |
| Registro completo movimenti | §3.2 `credit_ledger` (data/quantità/causale/servizio/evento/utente) |
| Gestione ordinaria gratis | §1.4, §7 (CRUD non passa dal service) |
| Consumo solo servizi avanzati | §4, §7 |
| Catalogo configurabile senza deploy | §3.3 `credit_services`, §5.2, §6.3 |
| Controllo saldo prima dell'esecuzione | §4 passo 2, §8 |
| No saldo negativo | §8 update atomico condizionato |
| Storico in Area Account | §6.1 |
| Predisposizione acquisto/ricarica | §3.5/§3.6, §5.1, Fase E |
| Predisposizione auto-ricarica | §3.1 `auto_recharge`, Fase E |
| Avvisi saldo basso | §3.1 soglia, §6.1 |
| Servizi futuri (WhatsApp/Brevo/IA/immagini/automazioni) | §7 |
| Consumi a quantità | §3.3 `per_unit`, §4 |
| Sostituzione /prezzi, Account, /demo | §9 Fase D |
