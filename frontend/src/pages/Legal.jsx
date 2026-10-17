import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Footer from "@/components/Footer";
import api from "@/lib/api";
import { openCookiePreferences } from "@/lib/consent";

const LAST_UPDATED = "17 ottobre 2026";
const CAT_LABEL = { necessary: "Necessari", analytics: "Analitici", marketing: "Marketing" };

function usePrivacyConfig() {
  const [cfg, setCfg] = useState(null);
  useEffect(() => { api.get("/privacy/config").then(({ data }) => setCfg(data)).catch(() => {}); }, []);
  return cfg;
}

function Section({ title, children, id }) {
  return (
    <section className="mt-8 scroll-mt-20" id={id}>
      <h2 className="font-display text-xl font-bold text-slate-900 mb-3">{title}</h2>
      <div className="space-y-3 text-slate-600 leading-relaxed text-sm sm:text-base">{children}</div>
    </section>
  );
}

function PrivacyPolicy() {
  return (
    <>
      <p className="text-slate-600 leading-relaxed">
        La presente informativa descrive le modalità di trattamento dei dati personali degli utenti che
        utilizzano <strong>CRMEvent</strong>, piattaforma SaaS (software-as-a-service) dedicata agli organizzatori
        di eventi per la gestione di organizzazioni, eventi, contatti, aziende, sponsor, staff, volontari, team,
        turni e attività. L'informativa è resa ai sensi del Regolamento (UE) 2016/679 ("GDPR").
      </p>

      <Section title="1. Titolare del trattamento">
        <p>Titolare del trattamento è <strong>Michele Manara</strong> – P. IVA 02671780340.</p>
        <p>Indirizzo: Strada Due Castagne, 39 – 43124 Parma (PR), Italia.</p>
        <p>Email di contatto e privacy: <a href="mailto:support@crmevent.it" className="text-tiffany-active font-semibold hover:underline">support@crmevent.it</a>.</p>
      </Section>

      <Section title="2. Dati raccolti durante la registrazione e l'utilizzo">
        <p>Durante la creazione dell'account e l'uso della piattaforma raccogliamo:</p>
        <ul className="list-disc pl-6 space-y-1">
          <li>dati anagrafici e di contatto (nome, cognome, email, eventuale numero di telefono);</li>
          <li>credenziali di accesso: password (conservata in forma cifrata/hash) oppure identità
              tramite login social <strong>Google (Google OAuth 2.0)</strong>;</li>
          <li>dati dell'account e dell'organizzazione (ruolo, permessi, stato, organizzazione di appartenenza);</li>
          <li>dati di utilizzo e log tecnici generati durante la navigazione (es. azioni compiute nella
              piattaforma, data/ora, identificativi di sessione).</li>
        </ul>
      </Section>

      <Section title="3. Dati dell'account e dell'organizzazione">
        <p>
          Per ogni utente viene creato un account associato a un'organizzazione (l'ente/soggetto che
          organizza gli eventi). Trattiamo i dati dell'account (ruolo, permessi, stato) e i dati
          dell'organizzazione necessari a fornire il servizio e a distinguere gli ambienti di lavoro
          dei diversi clienti, mantenendo la separazione (multi-tenant) tra le diverse organizzazioni.
        </p>
      </Section>

      <Section title="4. Dati inseriti dagli organizzatori in CRMEvent">
        <p>
          Nell'ambito dell'utilizzo del servizio, gli organizzatori inseriscono all'interno di CRMEvent
          dati relativi a terzi (es. persone, contatti, referenti aziendali, sponsor, staff, volontari,
          partecipanti). Rispetto a tali dati, <strong>l'organizzatore agisce come Titolare del trattamento</strong>,
          mentre <strong>CRMEvent agisce come Responsabile del trattamento</strong>, trattando i dati
          esclusivamente per conto dell'organizzatore e secondo le sue istruzioni, nei limiti di quanto
          necessario alla fornitura del servizio. Quando applicabile, le condizioni relative al trattamento
          dei dati per conto degli organizzatori ai sensi dell'art. 28 GDPR sono disponibili su richiesta,
          scrivendo a <a href="mailto:support@crmevent.it" className="text-tiffany-active font-semibold hover:underline">support@crmevent.it</a>.
        </p>
      </Section>

      <Section title="5. Finalità e basi giuridiche del trattamento">
        <ul className="list-disc pl-6 space-y-1">
          <li><strong>Erogazione del servizio</strong> (registrazione, autenticazione, funzionalità CRM e gestione eventi):
              esecuzione del contratto (art. 6.1.b GDPR).</li>
          <li><strong>Comunicazioni di servizio</strong> (email transazionali, notifiche, reset password):
              esecuzione del contratto (art. 6.1.b GDPR).</li>
          <li><strong>Pagamenti e fatturazione</strong>: esecuzione del contratto e obblighi di legge
              (artt. 6.1.b e 6.1.c GDPR).</li>
          <li><strong>Funzionalità di assistenza e di generazione contenuti basate su AI</strong> (vedi sezione 7):
              esecuzione del contratto e/o legittimo interesse (artt. 6.1.b e 6.1.f GDPR).</li>
          <li><strong>Sicurezza, prevenzione abusi e log tecnici</strong>: legittimo interesse (art. 6.1.f GDPR).</li>
          <li><strong>Adempimenti di legge</strong> (fiscali, contabili): obbligo legale (art. 6.1.c GDPR).</li>
          <li><strong>Cookie e strumenti di analisi/marketing</strong>: consenso (art. 6.1.a GDPR) – vedi
              la <Link to="/cookie-policy" className="text-tiffany-active font-semibold hover:underline">Cookie Policy</Link>.</li>
        </ul>
      </Section>

      <Section title="6. Google OAuth e Google Calendar">
        <p>
          CRMEvent utilizza servizi Google per due finalità distinte, che l'utente autorizza separatamente.
        </p>
        <p>
          <strong>Google OAuth 2.0 (accesso/autenticazione).</strong> Se scegli di accedere con Google,
          utilizziamo Google OAuth 2.0 esclusivamente per verificare la tua identità e creare/collegare il
          tuo account. In questo contesto trattiamo le informazioni di base del profilo (ad es. email e nome)
          fornite da Google. Questa funzione non comporta alcun accesso al tuo calendario.
        </p>
        <p>
          <strong>Integrazione Google Calendar (opzionale).</strong> Il collegamento del tuo Google Calendar è
          una funzione opzionale che deve essere autorizzata separatamente dall'utente. Una volta autorizzata,
          l'integrazione consente a CRMEvent di:
        </p>
        <ul className="list-disc pl-6 space-y-1">
          <li>leggere l'elenco dei tuoi calendari per permetterti di scegliere quello su cui operare;</li>
          <li>creare e aggiornare sul calendario selezionato gli eventi e i turni corrispondenti alle attività
              gestite in CRMEvent (titolo, descrizione, luogo, data e orario).</li>
        </ul>
        <p>
          L'accesso avviene solo previa esplicita autorizzazione dell'utente e può essere revocato in qualsiasi
          momento, sia dalle impostazioni di CRMEvent sia dalle impostazioni di sicurezza del proprio account
          Google. CRMEvent non effettua operazioni sul tuo calendario diverse da quelle sopra descritte.
          Il dettaglio completo sul trattamento dei dati Google è riportato nella sezione 6-bis.
        </p>
      </Section>

      <GoogleDataSection />

      <Section title="7. Funzionalità basate su Intelligenza Artificiale">
        <p>
          CRMEvent mette a disposizione alcune funzionalità basate su modelli di Intelligenza Artificiale,
          erogate tramite fornitori terzi.
        </p>
        <ul className="list-disc pl-6 space-y-1">
          <li><strong>Assistente AI di CRMEvent</strong>: per l'elaborazione testuale delle richieste di supporto
              e la generazione delle relative risposte viene utilizzato il servizio LLM di <strong>OpenAI</strong>.
              In base alla domanda posta, oltre al testo della richiesta possono essere trasmessi dati operativi
              dell'organizzazione attiva (ad esempio relativi a eventi, staff, volontari, team, turni, sponsor,
              attività o ospitalità), che possono includere dati personali presenti nell'organizzazione.</li>
          <li><strong>Funzionalità AI del modulo Social</strong>: per la generazione di contenuti testuali viene
              utilizzato il servizio LLM di <strong>OpenAI</strong> e, dove effettivamente impiegato per la
              generazione di immagini/elementi grafici, il servizio <strong>Google Gemini</strong>. I dati
              trasmessi dipendono dai contenuti e dalle informazioni che l'utente inserisce per la specifica
              richiesta.</li>
        </ul>
        <p>
          A seconda della funzione utilizzata e dei contenuti inseriti, i dati trasmessi ai servizi AI possono
          includere informazioni operative e dati personali presenti nell'organizzazione, ad esempio relativi a
          staff, volontari o contatti. Ti invitiamo a <strong>evitare di inserire o sottoporre alle funzionalità
          AI dati personali non necessari, categorie particolari di dati (dati "sensibili") o altre informazioni
          riservate</strong> quando non indispensabili alla funzione richiesta.
        </p>
      </Section>

      <Section title="8. Fornitori e servizi esterni">
        <p>Per erogare il servizio ci avvaliamo dei seguenti fornitori/servizi, ciascuno per le finalità indicate:</p>
        <ul className="list-disc pl-6 space-y-1">
          <li><strong>Google</strong> – autenticazione tramite Google OAuth 2.0 e integrazione opzionale con
              Google Calendar (vedi sezioni 6 e 6-bis; i dati Google non sono condivisi con gli altri fornitori elencati);</li>
          <li><strong>OpenAI</strong> – servizio LLM per l'Assistente AI e per le funzionalità AI testuali del
              modulo Social (vedi sezione 7);</li>
          <li><strong>Google Gemini</strong> – generazione di immagini/elementi grafici nel modulo Social, dove
              effettivamente utilizzato (vedi sezione 7);</li>
          <li><strong>Brevo</strong> – invio di email e comunicazioni, gestione dei relativi contatti, eventi di utilizzo
              dell'account per le comunicazioni di onboarding e, solo previo consenso Marketing, Brevo Tracker;</li>
          <li><strong>Stripe</strong> – gestione dei pagamenti;</li>
          <li><strong>Fatture in Cloud</strong> – emissione e gestione dei documenti di fatturazione;</li>
          <li><strong>Meta/Instagram</strong> – funzionalità di pubblicazione e gestione dei contenuti social;</li>
          <li><strong>Google Analytics 4</strong> – statistiche di utilizzo in forma aggregata, previo consenso
              (vedi <Link to="/cookie-policy" className="text-tiffany-active font-semibold hover:underline">Cookie Policy</Link>);</li>
          <li><strong>Gestione dei consensi cookie</strong> – sistema proprietario di CRMEvent: banner, preferenze e
              registro consensi pseudonimo conservato nel database della piattaforma (nessun fornitore terzo);</li>
          <li><strong>Servizio di object storage</strong> – archiviazione dei file caricati dagli utenti;</li>
          <li><strong>Database MongoDB</strong> – archiviazione dei dati della piattaforma, ospitato
              sull'infrastruttura Aruba;</li>
          <li><strong>Infrastruttura di hosting</strong> – il frontend è erogato tramite Emergent; il backend e il
              database sono ospitati sull'infrastruttura Aruba.</li>
        </ul>
      </Section>

      <Section title="9. Trasferimenti di dati">
        <p>
          Alcuni dei fornitori sopra indicati (in particolare quelli che offrono servizi AI e analitici, come
          Google e OpenAI) possono comportare il trasferimento di dati verso paesi terzi al di fuori dello Spazio
          Economico Europeo. Tali trasferimenti, ove presenti, avvengono sulla base delle garanzie previste dal
          GDPR, quali le Clausole Contrattuali Standard adottate dalla Commissione Europea o altri meccanismi
          idonei previsti dalla normativa applicabile.
        </p>
      </Section>

      <Section title="10. Conservazione dei dati">
        <p>
          I dati vengono conservati per il tempo necessario all'erogazione del servizio e al perseguimento delle
          finalità indicate, nonché per gli eventuali periodi ulteriori previsti dagli obblighi di legge. I documenti
          e i dati soggetti a obblighi amministrativi, contabili e fiscali vengono conservati per i periodi previsti
          dalla normativa applicabile.
        </p>
      </Section>

      <Section title="11. Sicurezza">
        <p>
          Adottiamo misure tecniche e organizzative adeguate a proteggere i dati, tra cui: cifratura/hashing
          delle password, autenticazione basata su token, controllo degli accessi basato sui ruoli (RBAC),
          separazione dei dati tra le diverse organizzazioni (multi-tenant) e trasmissione dei dati tramite
          protocollo HTTPS.
        </p>
      </Section>

      <Section title="12. Diritti degli interessati">
        <p>Ai sensi degli artt. 15-22 GDPR, l'interessato ha diritto di:</p>
        <ul className="list-disc pl-6 space-y-1">
          <li>accedere ai propri dati personali;</li>
          <li>ottenere la rettifica dei dati inesatti o l'integrazione di quelli incompleti;</li>
          <li>ottenere la cancellazione dei dati ("diritto all'oblio");</li>
          <li>ottenere la limitazione del trattamento;</li>
          <li>opporsi al trattamento;</li>
          <li>ottenere la portabilità dei dati;</li>
          <li>revocare il consenso in qualsiasi momento (ove il trattamento sia basato sul consenso);</li>
          <li>proporre reclamo all'Autorità di controllo (in Italia, il Garante per la protezione dei dati personali).</li>
        </ul>
      </Section>

      <Section title="13. Come esercitare i diritti">
        <p>
          Gli utenti registrati possono consultare e modificare i dati del proprio account direttamente
          dall'area Profilo della piattaforma. Per esercitare gli altri diritti (incluse cancellazione,
          limitazione, portabilità e opposizione) è possibile inviare una richiesta al Titolare all'indirizzo
          <a href="mailto:support@crmevent.it" className="text-tiffany-active font-semibold hover:underline"> support@crmevent.it</a>.
          Le richieste relative ai dati inseriti da un organizzatore nel proprio ambiente CRMEvent vanno
          indirizzate all'organizzatore stesso, in qualità di Titolare di tali dati.
        </p>
      </Section>

      <Section title="14. Contatti privacy">
        <p>Per qualsiasi richiesta relativa al trattamento dei dati personali è possibile contattare il
          Titolare: <strong>Michele Manara</strong> – P. IVA 02671780340 – Strada Due Castagne, 39 – 43124
          Parma (PR), Italia – email: <a href="mailto:support@crmevent.it" className="text-tiffany-active font-semibold hover:underline">support@crmevent.it</a>.</p>
      </Section>

      <Section title="15. Modifiche alla presente informativa">
        <p>
          La presente informativa può essere aggiornata nel tempo. Le modifiche saranno pubblicate su questa
          pagina con indicazione della data di ultimo aggiornamento.
        </p>
      </Section>
    </>
  );
}

const A = ({ href, children }) => (
  <a href={href} target="_blank" rel="noopener noreferrer" className="text-tiffany-active font-semibold hover:underline">{children}</a>
);

function GoogleDataSection() {
  return (
    <Section id="google-calendar" title="6-bis. Integrazione Google Calendar e utilizzo dei dati Google">
      <div data-testid="privacy-google-calendar-section" className="space-y-3">
        <p>
          Questa sezione descrive in modo specifico come CRMEvent accede, utilizza, conserva, condivide e cancella i
          dati ottenuti tramite le API di Google (di seguito "dati Google") quando l'utente collega volontariamente il
          proprio account Google Calendar.
        </p>

        <h3 className="font-semibold text-slate-800 pt-2">Dati raccolti</h3>
        <p>Con l'autorizzazione dell'utente, CRMEvent richiede esclusivamente i seguenti permessi (scope) Google:</p>
        <ul className="list-disc pl-6 space-y-1">
          <li><code>openid</code> e <code>userinfo.email</code>: indirizzo email dell'account Google, identificativo
              univoco dell'account Google e stato di verifica dell'email, usati per associare il calendario all'utente CRMEvent;</li>
          <li><code>calendar.readonly</code>: elenco dei calendari dell'utente (identificativo, nome, indicazione del
              calendario principale) e, solo per il calendario utilizzato dal team CRMEvent per demo e assistenza,
              gli intervalli di tempo occupati/liberi (free/busy), senza titoli, descrizioni, partecipanti o altri
              dettagli degli appuntamenti;</li>
          <li><code>calendar.events</code>: creazione, aggiornamento ed eliminazione degli eventi generati da CRMEvent sul
              calendario scelto dall'utente.</li>
        </ul>
        <p>
          CRMEvent <strong>non legge il contenuto degli eventi già presenti</strong> nel calendario dell'utente
          (titoli, descrizioni, partecipanti, allegati) e non accede ad altri servizi Google (es. Gmail, Drive, Contatti).
        </p>

        <h3 className="font-semibold text-slate-800 pt-2">Finalità</h3>
        <p>I dati Google sono utilizzati unicamente per:</p>
        <ul className="list-disc pl-6 space-y-1">
          <li>collegare l'account Google all'account CRMEvent e mostrare all'utente quale account è collegato;</li>
          <li>consentire all'utente di selezionare il calendario su cui operare;</li>
          <li>sincronizzare su richiesta dell'utente eventi, turni, attività e follow-up gestiti in CRMEvent (titolo,
              descrizione, luogo, data e orario), aggiornandoli o rimuovendoli senza creare duplicati;</li>
          <li>per il calendario del team CRMEvent: calcolare le fasce orarie disponibili per prenotare demo e assistenza
              video e creare il relativo appuntamento con link Google Meet, invitando l'utente che ha prenotato.</li>
        </ul>
        <p>I dati Google non sono utilizzati per finalità pubblicitarie, di profilazione o di marketing.</p>

        <h3 className="font-semibold text-slate-800 pt-2">Conservazione e protezione dei token</h3>
        <p>
          Nel database MongoDB di CRMEvent, ospitato sull'infrastruttura Aruba, vengono salvati per ciascun utente
          collegato: email e identificativo dell'account Google, stato di verifica dell'email, calendario selezionato,
          stato e date di collegamento e di ultima sincronizzazione, e i token OAuth (access token e refresh token). Per
          gli eventi sincronizzati vengono salvati solo l'identificativo dell'evento Google, il calendario e il link
          all'evento; per le prenotazioni di demo e assistenza anche il link Google Meet.
        </p>
        <p>
          I token OAuth sono <strong>cifrati con algoritmo AES-256-GCM</strong> prima del salvataggio, con chiave
          conservata separatamente nella configurazione protetta del server; non vengono mai salvati in chiaro, non
          sono registrati nei log e non vengono mai inviati al browser. I dati temporanei della procedura di
          autorizzazione (PKCE) sono monouso e scadono automaticamente dopo 10 minuti. Tutte le comunicazioni avvengono
          tramite HTTPS e l'accesso è limitato al singolo utente che ha effettuato il collegamento.
        </p>

        <h3 className="font-semibold text-slate-800 pt-2">Condivisione, trasferimento e comunicazione dei dati Google</h3>
        <p>
          CRMEvent <strong>non vende, non cede, non noleggia e non condivide i dati Google con terze parti</strong>, né li
          trasferisce a servizi di analisi, pubblicità, email marketing (es. Brevo) o intelligenza artificiale. I dati
          Google sono trattati esclusivamente:
        </p>
        <ul className="list-disc pl-6 space-y-1">
          <li><strong>da Google</strong>, in quanto destinatario delle richieste API necessarie alla funzione (gli eventi
              creati da CRMEvent, inclusi gli eventuali invitati alle demo e assistenze, sono inviati a Google Calendar);</li>
          <li><strong>da Aruba</strong>, quale fornitore di hosting che ospita il backend e il database di CRMEvent in cui
              i dati sono conservati, che agisce come fornitore di infrastruttura per conto di CRMEvent;</li>
          <li><strong>dall'utente stesso</strong>, che visualizza nella propria area i dati del proprio collegamento.
              Il frontend dell'applicazione, erogato tramite Emergent, mostra tali informazioni nel browser dell'utente
              ma non conserva i dati Google né i token.</li>
        </ul>
        <p>
          I dati Google possono inoltre essere comunicati solo se richiesto dalla legge o da un ordine dell'autorità,
          oppure se necessario per la sicurezza del servizio, sempre nei limiti consentiti dalle norme Google.
        </p>

        <h3 className="font-semibold text-slate-800 pt-2">Intelligenza artificiale e machine learning</h3>
        <p>
          I dati Google <strong>non vengono inviati alle funzionalità AI</strong> di CRMEvent (Assistente AI, modulo
          Social, Comunicati stampa) né a fornitori di modelli AI (es. OpenAI, Google Gemini), e non vengono utilizzati
          per sviluppare, migliorare o addestrare modelli di intelligenza artificiale o machine learning generalizzati.
        </p>

        <h3 className="font-semibold text-slate-800 pt-2">Disconnessione, conservazione e cancellazione</h3>
        <ul className="list-disc pl-6 space-y-1">
          <li>Quando l'utente scollega Google Calendar da CRMEvent, il token viene <strong>revocato presso Google</strong> e
              il record del collegamento (token cifrati, email e identificativo Google, calendario selezionato) viene
              <strong> eliminato immediatamente</strong> dal database.</li>
          <li>Se l'utente collega un account Google diverso, il token dell'account precedente viene revocato e sostituito.</li>
          <li>Gli eventi già creati sul calendario dell'utente restano nel suo Google Calendar, dove l'utente può gestirli
              o eliminarli; le singole sincronizzazioni di attività e follow-up possono anche essere rimosse da CRMEvent,
              eliminando l'evento da Google Calendar.</li>
          <li>Con l'eliminazione dell'account CRMEvent vengono cancellati il collegamento Google e i riferimenti agli eventi
              sincronizzati.</li>
          <li>L'utente può revocare l'accesso in qualsiasi momento anche dalle impostazioni di sicurezza del proprio account
              Google (<A href="https://myaccount.google.com/permissions">myaccount.google.com/permissions</A>); in tal caso
              CRMEvent non può più accedere al calendario e chiede di ricollegare l'account.</li>
          <li>Per richiedere la cancellazione di eventuali dati Google residui è possibile scrivere a{" "}
              <a href="mailto:support@crmevent.it" className="text-tiffany-active font-semibold hover:underline">support@crmevent.it</a>.</li>
        </ul>

        <h3 className="font-semibold text-slate-800 pt-2">Conformità alle norme Google (Limited Use)</h3>
        <p>
          L'utilizzo e il trasferimento ad altre applicazioni delle informazioni ricevute dalle API di Google da parte di
          CRMEvent rispettano le{" "}
          <A href="https://developers.google.com/terms/api-services-user-data-policy">Google API Services User Data Policy</A>,
          inclusi i requisiti di Limited Use (utilizzo limitato).
        </p>
      </div>
    </Section>
  );
}

function ServicesTable({ cfg }) {
  if (!cfg) return <p className="text-sm text-slate-400">Caricamento elenco servizi...</p>;
  return (
    <div className="space-y-4" data-testid="cookie-policy-services">
      {["necessary", "analytics", "marketing"].map((cat) => (
        <div key={cat}>
          <h3 className="font-semibold text-slate-800">{CAT_LABEL[cat]}</h3>
          <ul className="mt-2 space-y-2">
            {cfg.services.filter((s) => s.category === cat).map((s) => (
              <li key={s.id} className="border border-slate-200 rounded-lg p-3 text-sm">
                <div><strong>{s.name}</strong> – {s.provider}</div>
                <div className="text-slate-600">{s.purpose_it}</div>
                {s.cookies?.length > 0 && (
                  <ul className="mt-1 list-disc pl-5 text-slate-600">
                    {s.cookies.map((c) => <li key={c.name}><code>{c.name}</code> – {c.duration_it} – {c.description_it}</li>)}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

function CookiePolicy() {
  const cfg = usePrivacyConfig();
  return (
    <>
      <p className="text-slate-600 leading-relaxed">
        La presente Cookie Policy spiega cosa sono i cookie e le tecnologie simili, quali tipologie sono
        utilizzate da <strong>CRMEvent</strong> e come è possibile gestirne le preferenze.
        {cfg && <span className="block text-xs text-slate-400 mt-1" data-testid="cookie-policy-version">Versione {cfg.versions.cookie}</span>}
      </p>

      <Section title="1. Cosa sono i cookie">
        <p>
          I cookie sono piccoli file di testo che i siti web salvano sul dispositivo dell'utente per
          memorizzare informazioni. Tecnologie simili (come il localStorage del browser) sono trattate allo
          stesso modo. Possono essere di prima parte o di terze parti, di sessione o persistenti.
        </p>
      </Section>

      <Section title="2. Categorie utilizzate">
        <ul className="list-disc pl-6 space-y-1">
          <li><strong>Necessari</strong>: indispensabili per autenticazione, sicurezza e memorizzazione delle scelte sui
              cookie. Sono sempre attivi e non richiedono consenso.</li>
          <li><strong>Analitici</strong> (facoltativi): statistiche di utilizzo tramite Google Analytics 4 (IP anonimizzato) e
              analisi tecnica dell'applicazione. Attivati <strong>solo previo consenso</strong>.</li>
          <li><strong>Marketing</strong> (facoltativi): Brevo Tracker, che associa la navigazione al contatto per comunicazioni
              e automazioni email. Attivato <strong>solo previo consenso</strong>.</li>
        </ul>
      </Section>

      <Section title="3. Servizi e cookie utilizzati">
        <ServicesTable cfg={cfg} />
      </Section>

      <Section title="4. Gestione del consenso">
        <p>
          Il consenso è raccolto tramite il banner proprietario di CRMEvent. Nessuna categoria facoltativa è preselezionata,
          lo scorrimento o la chiusura della pagina non valgono come consenso e il rifiuto non limita l'uso della piattaforma.
          Prima della scelta Google Consent Mode v2 è impostato su "negato" (analytics_storage, ad_storage, ad_user_data,
          ad_personalization) e gli script di Google Analytics, dell'analisi applicativa e di Brevo non vengono caricati.
        </p>
        <p>
          Puoi modificare o revocare le tue scelte in qualsiasi momento tramite il link "Preferenze cookie" nel footer, nel menu
          dell'area riservata oppure{" "}
          <button type="button" onClick={openCookiePreferences} className="text-tiffany-active font-semibold hover:underline" data-testid="cookie-policy-open-prefs">da qui</button>.
          In caso di revoca i cookie dei servizi interessati vengono eliminati e il tracciamento si interrompe.
          Il banner viene riproposto dopo 6 mesi o quando pubblichiamo una nuova versione di questa policy, della Privacy Policy o del banner.
        </p>
      </Section>

      <Section title="5. Registro dei consensi">
        <p>
          Per dimostrare il consenso conserviamo, per ogni scelta: un identificativo pseudonimo generato dal browser, l'ID utente
          solo se hai effettuato l'accesso, data e ora, preferenze espresse, versioni di Privacy Policy, Cookie Policy e banner,
          origine della scelta (banner o preferenze), lingua ed eventuale modifica o revoca. Non registriamo indirizzo IP né
          informazioni sul dispositivo. I dati sono accessibili solo agli amministratori della piattaforma e vengono cancellati
          automaticamente dopo 24 mesi.
        </p>
      </Section>

      <Section title="6. Eventi di utilizzo dell'account">
        <p>
          Indipendentemente dai cookie, per gli utenti registrati CRMEvent comunica a Brevo dal proprio server alcuni eventi
          legati all'uso dell'account (registrazione, accesso, inizio prova, primo evento, prima attività, abbonamento) per
          l'invio di comunicazioni di servizio e di onboarding, come descritto nella{" "}
          <Link to="/privacy-policy" className="text-tiffany-active font-semibold hover:underline">Privacy Policy</Link>.
          Questi eventi non usano cookie né tracciano la navigazione.
        </p>
      </Section>

      <Section title="7. Come gestire i cookie dal browser">
        <p>
          È inoltre possibile gestire o disabilitare i cookie dalle impostazioni del browser (Chrome, Firefox, Safari, Edge, ecc.).
          La disabilitazione dei cookie tecnici può compromettere il funzionamento della piattaforma.
        </p>
      </Section>

      <Section title="8. Titolare e aggiornamenti">
        <p>
          Titolare del trattamento: Michele Manara – P. IVA 02671780340 – <a href="mailto:support@crmevent.it" className="text-tiffany-active font-semibold hover:underline">support@crmevent.it</a>.
          La presente Cookie Policy può essere aggiornata; le modifiche sono pubblicate su questa pagina con una nuova versione.
        </p>
      </Section>
    </>
  );
}

function Termini() {
  return (
    <>
      <p className="text-slate-600 leading-relaxed">
        Le presenti Condizioni Generali (di seguito "Termini") disciplinano l'accesso e l'utilizzo della
        piattaforma <strong>CRMEvent</strong> (di seguito il "Servizio"). Utilizzando il Servizio, l'utente
        dichiara di aver letto, compreso e accettato i presenti Termini.
      </p>

      <Section title="1. Oggetto e funzionamento del Servizio">
        <p>
          CRMEvent è una piattaforma SaaS (software-as-a-service) dedicata agli organizzatori di eventi per la
          gestione di organizzazioni, eventi, contatti, aziende, sponsor, staff, volontari, team, turni e
          attività, nonché per l'utilizzo di funzionalità e integrazioni collegate. Il Servizio è fornito in
          modalità "as a service" e accessibile tramite browser.
        </p>
      </Section>

      <Section title="2. Registrazione e account">
        <p>
          Per utilizzare il Servizio è necessario registrare un account, direttamente o tramite accesso con
          Google. L'utente è tenuto a fornire dati veritieri, completi e aggiornati e a mantenere riservate le
          proprie credenziali di accesso. L'utente è responsabile di tutte le attività svolte tramite il proprio
          account ed è tenuto a comunicare tempestivamente qualsiasi uso non autorizzato.
        </p>
      </Section>

      <Section title="3. Utilizzo consentito della piattaforma">
        <p>L'utente si impegna a utilizzare il Servizio nel rispetto della legge e dei presenti Termini. In particolare, è vietato:</p>
        <ul className="list-disc pl-6 space-y-1">
          <li>utilizzare il Servizio per finalità illecite o lesive dei diritti di terzi;</li>
          <li>tentare di accedere ad aree, dati o organizzazioni non di propria competenza;</li>
          <li>compromettere la sicurezza, l'integrità o la disponibilità del Servizio;</li>
          <li>caricare contenuti illeciti, dannosi o che violino diritti di proprietà intellettuale altrui.</li>
        </ul>
      </Section>

      <Section title="4. Responsabilità dell'organizzatore sui dati inseriti">
        <p>
          L'utente/organizzatore è l'unico responsabile dei dati e dei contenuti inseriti nel proprio ambiente
          CRMEvent, inclusi i dati personali relativi a staff, volontari, partecipanti, contatti e altri soggetti.
          L'organizzatore garantisce di avere una base giuridica adeguata per il trattamento di tali dati e si
          impegna a rispettare la normativa applicabile in materia di protezione dei dati personali. Rispetto a
          tali dati, i ruoli di Titolare e Responsabile del trattamento sono disciplinati nella
          <Link to="/privacy-policy" className="text-tiffany-active font-semibold hover:underline"> Privacy Policy</Link>.
        </p>
      </Section>

      <Section title="5. Gestione di staff, volontari, partecipanti e altri soggetti">
        <p>
          Le funzionalità di gestione di staff, volontari, partecipanti e altri soggetti sono messe a disposizione
          affinché l'organizzatore possa organizzare le proprie attività. L'organizzatore è tenuto a informare
          adeguatamente tali soggetti e a trattarne i dati nel rispetto della normativa applicabile.
        </p>
      </Section>

      <Section title="6. Servizi e integrazioni di terze parti">
        <p>
          Il Servizio può integrarsi con servizi di terze parti (ad esempio Google, OpenAI, Google Gemini, Brevo,
          Stripe, Fatture in Cloud, Meta/Instagram). L'utilizzo di tali integrazioni può essere soggetto ai
          termini e alle informative dei rispettivi fornitori. CRMEvent non è responsabile per la disponibilità,
          il funzionamento o le modifiche dei servizi di terze parti. Alcune integrazioni (ad esempio Google
          Calendar) sono opzionali e richiedono un'autorizzazione specifica da parte dell'utente, revocabile in
          qualsiasi momento.
        </p>
      </Section>

      <Section title="7. Abbonamenti e funzionalità a pagamento">
        <p>
          Il Servizio è offerto tramite piani in abbonamento (BRONZE, SILVER e GOLD) ed eventuali servizi
          aggiuntivi a pagamento. Le caratteristiche dei piani e i relativi costi sono quelli indicati sulla piattaforma
          o nella pagina <Link to="/prezzi" className="text-tiffany-active font-semibold hover:underline">Prezzi</Link> al
          momento dell'acquisto o dell'attivazione.
        </p>
      </Section>

      <Section title="8. Pagamenti">
        <p>
          I pagamenti relativi ai piani e ai servizi a pagamento sono gestiti tramite il fornitore di pagamento
          Stripe. L'utente si impegna a fornire dati di pagamento corretti e aggiornati. Gli importi, le modalità e
          la frequenza di addebito sono quelli indicati sulla piattaforma al momento dell'acquisto o
          dell'attivazione.
        </p>
      </Section>

      <Section title="9. Fatturazione">
        <p>
          I documenti di fatturazione relativi agli acquisti effettuati vengono emessi e gestiti tramite il
          servizio Fatture in Cloud, sulla base dei dati forniti dall'utente. L'utente è tenuto a fornire dati di
          fatturazione corretti e completi.
        </p>
      </Section>

      <Section title="10. Disponibilità e interruzioni del Servizio">
        <p>
          CRMEvent si impegna a mantenere il Servizio disponibile e funzionante, ma non garantisce che l'accesso
          sia ininterrotto o privo di errori. Il Servizio può essere temporaneamente sospeso per manutenzione,
          aggiornamenti, cause tecniche o eventi al di fuori del ragionevole controllo del Titolare.
        </p>
      </Section>

      <Section title="11. Proprietà intellettuale">
        <p>
          Il Servizio, il software, i marchi, i loghi e i contenuti messi a disposizione da CRMEvent sono protetti
          dai diritti di proprietà intellettuale e restano di titolarità del Titolare o dei rispettivi aventi
          diritto. I dati e i contenuti inseriti dall'utente restano di titolarità dell'utente/organizzazione.
        </p>
      </Section>

      <Section title="12. Responsabilità dell'utente">
        <p>
          L'utente è responsabile dell'uso che fa del Servizio, dei contenuti e dei dati inseriti e del rispetto
          dei presenti Termini e della normativa applicabile. L'utente manleva CRMEvent da pretese di terzi
          derivanti da un uso del Servizio in violazione dei presenti Termini o della legge.
        </p>
      </Section>

      <Section title="13. Limitazioni di responsabilità">
        <p>
          Nei limiti consentiti dalla normativa applicabile, CRMEvent non è responsabile per danni indiretti,
          perdita di dati, mancati guadagni o interruzioni di attività derivanti dall'uso o dall'impossibilità di
          utilizzare il Servizio, né per il funzionamento dei servizi di terze parti. Resta ferma ogni
          responsabilità che non possa essere esclusa o limitata ai sensi della normativa applicabile.
        </p>
      </Section>

      <Section title="14. Sospensione e chiusura dell'account">
        <p>
          CRMEvent può sospendere o limitare l'accesso al Servizio in caso di violazione dei presenti Termini, di
          uso illecito o di rischio per la sicurezza. L'utente può richiedere la chiusura del proprio account
          secondo le modalità rese disponibili sulla piattaforma o contattando il Titolare. A seguito della
          chiusura, i dati vengono trattati secondo quanto indicato nella
          <Link to="/privacy-policy" className="text-tiffany-active font-semibold hover:underline"> Privacy Policy</Link>.
        </p>
      </Section>

      <Section title="15. Modifiche della piattaforma e dei Termini">
        <p>
          CRMEvent può modificare, aggiornare o evolvere le funzionalità del Servizio. I presenti Termini possono
          essere aggiornati nel tempo; le modifiche saranno pubblicate su questa pagina con indicazione della data
          di ultimo aggiornamento e si applicheranno all'utilizzo successivo del Servizio.
        </p>
      </Section>

      <Section title="16. Privacy e trattamento dei dati">
        <p>
          Il trattamento dei dati personali è disciplinato dalla
          <Link to="/privacy-policy" className="text-tiffany-active font-semibold hover:underline"> Privacy Policy</Link> e,
          per quanto riguarda i cookie, dalla
          <Link to="/cookie-policy" className="text-tiffany-active font-semibold hover:underline"> Cookie Policy</Link>.
        </p>
      </Section>

      <Section title="17. Legge applicabile e contatti">
        <p>
          I presenti Termini sono regolati dalla legge italiana e devono essere interpretati in conformità ad essa,
          fatte salve le disposizioni inderogabili a tutela del consumatore eventualmente applicabili. Per qualsiasi
          richiesta o comunicazione relativa al Servizio è possibile contattare il Titolare: <strong>Michele
          Manara</strong> – P. IVA 02671780340 – Strada Due Castagne, 39 – 43124 Parma (PR), Italia – email:
          <a href="mailto:support@crmevent.it" className="text-tiffany-active font-semibold hover:underline"> support@crmevent.it</a>.
        </p>
      </Section>
    </>
  );
}

const RENDER = { privacy: PrivacyPolicy, cookie: CookiePolicy, termini: Termini };
const TITLES = { privacy: "Privacy Policy", cookie: "Cookie Policy", termini: "Termini e Condizioni" };

export default function Legal({ type }) {
  const Body = RENDER[type] || PrivacyPolicy;
  const title = TITLES[type] || "Informativa";
  return (
    <div className="min-h-screen bg-white flex flex-col" data-testid={`legal-page-${type}`}>
      <header className="border-b border-slate-100 h-16 flex items-center px-6">
        <Link to="/"><img src="/logo-crmevent.png?v=5" alt="CRMEvent" className="h-7 w-auto" /></Link>
      </header>
      <main className="max-w-3xl mx-auto px-6 py-14 flex-1 w-full">
        <h1 className="font-display text-3xl font-bold text-slate-900 mb-2">{title}</h1>
        <p className="text-xs text-slate-400 mb-8">Ultimo aggiornamento: {LAST_UPDATED}</p>
        <Body />
        <div className="mt-12"><Link to="/" className="text-tiffany-active font-semibold hover:underline">← Torna alla home</Link></div>
      </main>
      <Footer />
    </div>
  );
}
