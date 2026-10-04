# CRMEvent Backend — Report modifiche versione portabile (Aruba)

Data: giugno 2026
Copia di lavoro: `/app/export-aruba/crmevent-backend/` (la **produzione Emergent NON è stata toccata**).
Nessun deploy effettuato.

---

## 1. Object Storage — `storage_utils.py`
**Prima:** Object Storage Emergent via HTTP verso `integrations.emergentagent.com/objstore`,
autenticazione con `EMERGENT_LLM_KEY`.
**Dopo:** storage **S3-compatibile** tramite **boto3** (già in `requirements.txt`).
- Interfaccia pubblica **invariata**: `put_object(path, data, content_type)` e `get_object(path)`.
- `put_object` restituisce `{"path": <path>, "size": <int>}` → compatibile con gli usi in `server.py`
  (`result["path"]`, `result.get("size")`).
- `get_object` restituisce `(bytes, content_type)` → invariato.
- Costante `APP_NAME = "crmevent"` mantenuta (usata da `server.py` per il prefisso dei path).
- **Nessun fallback** a `integrations.emergentagent.com`.
- Nuove variabili: `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_BUCKET`, `S3_REGION`.

## 2. LLM — `social_ai.py`, `support_service.py`, `social_creative.py`
**Prima:** `from emergentintegrations.llm.chat import LlmChat, UserMessage` + `EMERGENT_LLM_KEY`.
**Dopo:** **SDK OpenAI ufficiale** (`openai==1.99.9`, già presente) con client `AsyncOpenAI`.
- `social_ai.py` e `support_service.py`: helper `_run()` ora usa
  `client.chat.completions.create(model=OPENAI_MODEL, messages=[system, user])`.
  Prompt di sistema, strutture JSON, parsing (`_parse_json`) e **tutti i fallback invariati**
  (ora la guardia controlla `OPENAI_API_KEY` invece di `EMERGENT_LLM_KEY`).
- `social_creative.py` → `generate_background()`: generazione immagini via **OpenAI Images**
  (`client.images.generate`, modello `SOCIAL_IMAGE_MODEL`, default `gpt-image-1`). Rimosso l'import
  Emergent e il ramo Gemire. Fallback `raise` preservato (il chiamante gestisce l'assenza di sfondo).
  Nota: `generate_background` non è attualmente richiamato da `server.py` (funzione predisposta).
- Nuove variabili: `OPENAI_API_KEY`, `OPENAI_MODEL` (+ opzionali `SOCIAL_IMAGE_PROVIDER`, `SOCIAL_IMAGE_MODEL`).

## 3. Dipendenze — `requirements.txt`
Rimosse:
- `emergentintegrations==0.2.1`
- `litellm @ https://customer-assets.emergentagent.com/.../litellm-1.80.0-py3-none-any.whl` (wheel privata Emergent;
  nessun riferimento diretto a `litellm` nel codice → rimovibile in sicurezza).
Mantenute e usate dalla versione portabile: `openai==1.99.9`, `boto3==1.43.99`, `botocore==1.43.99`.

## 4. Verifica assenza dipendenze Emergent (runtime)
| Verifica | Esito |
|---|---|
| `emergentintegrations` nei `.py` | ✅ Nessun riferimento |
| `EMERGENT_LLM_KEY` nei `.py` | ✅ Nessun riferimento (solo commento in `storage_utils.py`) |
| `integrations.emergentagent.com` runtime | ✅ Assente dal percorso attivo. Resta SOLO come costante nel ramo email `managed` di `email_utils.py`, **non raggiunto** con `EMAIL_PROVIDER=brevo` |
| `EMERGENT_EMAIL_KEY` con `EMAIL_PROVIDER=brevo` | ✅ Non usato a runtime (ramo `managed` dormiente) |
| `litellm` / wheel privata | ✅ Rimossa da requirements |
| Repository/asset privati Emergent | ✅ Rimossi da requirements |

Nota: `email_utils.py` NON è stato modificato (vincolo: non toccare la logica Brevo/email). Il provider
`managed` resta disponibile come opzione ma inattivo con Brevo. Per eliminare del tutto quel residuo
testuale, in futuro si può rimuovere il ramo `managed`; non necessario per il funzionamento su Aruba.

## 5. Ambiti NON toccati (come richiesto)
Stripe, Fatture in Cloud, Brevo, Google, Meta/Instagram, autenticazione JWT e logica applicativa
di `server.py`: **invariati**.

## 6. Verifiche eseguite
- `py_compile` dei 4 moduli portati: **OK**.
- Import dei 4 moduli con env fittizie: **OK** (client OpenAI `None` senza chiave → fallback attivi;
  default immagini `openai` / `gpt-image-1`).
- `grep` residui Emergent: **OK** (vedi tabella §4).
- `pytest tests/test_email_provider_routing.py`: **8/8 passati** (selezione provider email, incl. Brevo).
- Gli altri test della suite sono integration test che richiedono MongoDB/HTTP server live
  (`MONGO_URL`, `REACT_APP_BACKEND_URL`): non eseguibili offline nella copia e non pertinenti al porting.

## 7. Prima dell'avvio su Aruba
1. Copiare `.env.example` → `.env` e compilare (in particolare S3_* e OPENAI_*).
2. `pip install -r requirements.txt` (NON serve più l'indice privato Emergent).
3. Migrare gli oggetti esistenti dall'Object Storage Emergent al bucket S3 (stessi `storage_path`).
4. Impostare `EMAIL_PROVIDER=brevo`.
5. Avviare con `start.sh` (Uvicorn) dietro Nginx + SSL su `api.crmevent.it`.
