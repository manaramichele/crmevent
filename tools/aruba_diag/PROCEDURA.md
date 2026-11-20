# Diagnostica in sola lettura su Aruba - procedura

Lo script `diagnostica_org_readonly.py` **legge soltanto**: tutte le operazioni sul database passano da un filtro che blocca qualsiasi scrittura, modifica, eliminazione o migrazione. Non riavvia servizi, non tocca file del backend, non esporta il database. Produce un solo file di testo (report) senza nomi, email o telefoni.

## Cosa serve
- Accesso SSH al server Aruba (utente che può leggere la cartella del backend CRMEvent). Non serve root/sudo.
- Il virtualenv del backend già installato (contiene `pymongo`).
- Facoltativo ma consigliato: un utente MongoDB con ruolo **read** sul solo database CRMEvent (vedi in fondo).

## Passaggi
1. Copia lo script sul server (dal tuo computer):
   `scp diagnostica_org_readonly.py UTENTE@IP_SERVER:/tmp/`
   In alternativa crea il file `/tmp/diagnostica_org_readonly.py` sul server e incolla il contenuto.
2. Collegati: `ssh UTENTE@IP_SERVER`
3. Trova la cartella del backend in esecuzione:
   `ps -eo pid,args | grep "uvicorn server:app" | grep -v grep`
   poi `readlink -f /proc/PID/cwd` (PID = primo numero della riga). Indichiamo la cartella come `BACKEND`.
4. (Facoltativo) Trova la cartella del frontend servito da crmevent.it:
   `grep -R "root " /etc/nginx/sites-enabled/ 2>/dev/null`  → cartella `FRONTEND` (quella con `index.html`).
5. Attiva l'ambiente e lancia lo script:
   ```
   cd BACKEND && source .venv/bin/activate
   python /tmp/diagnostica_org_readonly.py --backend-dir BACKEND --frontend-dir FRONTEND
   ```
   Se Trento non viene trovata per nome, aggiungi `--org ID_TRENTO` (ID completo).
6. Il report viene salvato in `/tmp/crmevent_diagnostica_AAAAMMGG_HHMM.md`. Scaricalo:
   `scp UTENTE@IP_SERVER:/tmp/crmevent_diagnostica_*.md .`
   e allegalo in chat (oppure incolla il testo).
7. Rimuovi i file temporanei dal server: `rm /tmp/diagnostica_org_readonly.py /tmp/crmevent_diagnostica_*.md`

Per default gli ID sono abbreviati ai primi 8 caratteri. Solo quando approverai una correzione potrà servire rieseguirlo con `--full-ids`.

## Cosa contiene il report
0. Nome del database usato dal backend (credenziali e indirizzo non mostrati).
1. Versione del backend: impronta SHA-256 di `server.py` confrontata con l'export Aruba del 04/10/2026 e con la versione Emergent attuale; controlli presenti nel codice; estratti della logica Org attiva e della pagina Staff / Volontari.
2. Frontend: come viene popolata la tendina gialla e a quale backend punta.
3. Elenco organizzazioni e ID di A.S.D. Città di Trento.
4. Eventi e assegnazioni Staff / Volontari di Trento, con le assegnazioni incoerenti (evento o persona di un'altra organizzazione) e la simulazione della pagina.
5. Tutti gli eventi "Pisa", a quale organizzazione appartengono e le persone di Trento collegate.
6. Record senza organizzazione o legati a organizzazioni inesistenti nei moduli principali.
7. Registro attività e importazioni collegati a Trento o agli eventi Pisa.

## Utente MongoDB in sola lettura (consigliato)
Se vuoi una garanzia in più, chi gestisce MongoDB può creare un utente con ruolo `read` sul database CRMEvent e lanciare lo script con quella connessione al posto di quella del backend:
`MONGO_URL="mongodb://lettore:PASSWORD@127.0.0.1:27017/?authSource=admin" python /tmp/diagnostica_org_readonly.py --backend-dir BACKEND`
(le variabili d'ambiente hanno la precedenza sul file `.env`; il valore non viene mai stampato).
