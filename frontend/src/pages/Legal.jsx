import { Link } from "react-router-dom";
import Footer from "@/components/Footer";

const LAST_UPDATED = "Giugno 2026";

function Section({ title, children }) {
  return (
    <section className="mt-8">
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
              la <Link to="/cookie" className="text-tiffany-active font-semibold hover:underline">Cookie Policy</Link>.</li>
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
        </p>
      </Section>

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
              Google Calendar (vedi sezione 6);</li>
          <li><strong>OpenAI</strong> – servizio LLM per l'Assistente AI e per le funzionalità AI testuali del
              modulo Social (vedi sezione 7);</li>
          <li><strong>Google Gemini</strong> – generazione di immagini/elementi grafici nel modulo Social, dove
              effettivamente utilizzato (vedi sezione 7);</li>
          <li><strong>Brevo</strong> – invio di email e comunicazioni e gestione dei relativi contatti;</li>
          <li><strong>Stripe</strong> – gestione dei pagamenti;</li>
          <li><strong>Fatture in Cloud</strong> – emissione e gestione dei documenti di fatturazione;</li>
          <li><strong>Meta/Instagram</strong> – funzionalità di pubblicazione e gestione dei contenuti social;</li>
          <li><strong>Google Analytics 4</strong> – statistiche di utilizzo in forma aggregata, previo consenso
              (vedi <Link to="/cookie" className="text-tiffany-active font-semibold hover:underline">Cookie Policy</Link>);</li>
          <li><strong>Iubenda</strong> – gestione del consenso e delle preferenze sui cookie (Consent Management Platform);</li>
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

function CookiePolicy() {
  return (
    <>
      <p className="text-slate-600 leading-relaxed">
        La presente Cookie Policy spiega cosa sono i cookie e le tecnologie simili, quali tipologie sono
        utilizzate da <strong>CRMEvent</strong> e come è possibile gestirne le preferenze.
      </p>

      <Section title="1. Cosa sono i cookie">
        <p>
          I cookie sono piccoli file di testo che i siti web salvano sul dispositivo dell'utente per
          memorizzare informazioni. Possono essere di prima parte (impostati dal sito) o di terze parti
          (impostati da servizi esterni), e possono avere durata di sessione o persistente.
        </p>
      </Section>

      <Section title="2. Cookie tecnici / necessari">
        <p>
          Sono indispensabili per il funzionamento della piattaforma e non richiedono consenso. Vengono
          utilizzati, ad esempio, per l'autenticazione e il mantenimento della sessione dell'utente
          (cookie di sessione con token). Senza questi cookie il servizio non può funzionare correttamente.
        </p>
      </Section>

      <Section title="3. Cookie analitici">
        <p>
          Utilizzati per raccogliere informazioni aggregate su come gli utenti utilizzano il sito, al fine di
          migliorare il servizio. CRMEvent utilizza <strong>Google Analytics 4</strong> con IP anonimizzato e
          in conformità alla modalità "Consent Mode". Questi cookie vengono installati
          <strong> solo previo consenso</strong> dell'utente.
        </p>
      </Section>

      <Section title="4. Cookie di marketing / profilazione">
        <p>
          Eventuali cookie di marketing o profilazione vengono installati <strong>solo previo consenso</strong>
          dell'utente e servono a misurare l'efficacia delle comunicazioni e a mostrare contenuti in linea con
          gli interessi. L'elenco aggiornato e i dettagli dei singoli strumenti sono sempre consultabili tramite
          lo strumento di gestione del consenso.
        </p>
      </Section>

      <Section title="5. Gestione del consenso">
        <p>
          Per i cookie non tecnici (analitici e di marketing) il consenso viene raccolto e gestito tramite
          lo strumento di gestione del consenso (Consent Management Platform) <strong>Iubenda</strong>, integrato
          con la modalità Google Consent Mode v2. L'utente può in ogni momento modificare o revocare le proprie
          preferenze tramite il link "Preferenze cookie" presente nel footer del sito.
        </p>
      </Section>

      <Section title="6. Come gestire i cookie dal browser">
        <p>
          È inoltre possibile gestire o disabilitare i cookie direttamente dalle impostazioni del proprio
          browser (Chrome, Firefox, Safari, Edge, ecc.). La disabilitazione dei cookie tecnici può tuttavia
          compromettere il corretto funzionamento della piattaforma.
        </p>
      </Section>

      <Section title="7. Aggiornamenti">
        <p>La presente Cookie Policy può essere aggiornata; le modifiche saranno pubblicate su questa pagina.</p>
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
          <Link to="/privacy" className="text-tiffany-active font-semibold hover:underline"> Privacy Policy</Link>.
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

      <Section title="7. Crediti e funzionalità a pagamento">
        <p>
          Alcune funzionalità del Servizio possono richiedere l'utilizzo di crediti o l'adesione a piani/servizi a
          pagamento. Le caratteristiche, i crediti inclusi e i relativi costi sono quelli indicati sulla piattaforma
          o nella pagina <Link to="/prezzi" className="text-tiffany-active font-semibold hover:underline">Prezzi</Link> al
          momento dell'acquisto o dell'attivazione. Il consumo dei crediti avviene secondo quanto indicato nella
          piattaforma in relazione alle singole funzionalità.
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
          <Link to="/privacy" className="text-tiffany-active font-semibold hover:underline"> Privacy Policy</Link>.
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
          <Link to="/privacy" className="text-tiffany-active font-semibold hover:underline"> Privacy Policy</Link> e,
          per quanto riguarda i cookie, dalla
          <Link to="/cookie" className="text-tiffany-active font-semibold hover:underline"> Cookie Policy</Link>.
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
