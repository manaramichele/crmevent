import { Link } from "react-router-dom";
import Footer from "@/components/Footer";

const TODO = <span className="font-semibold text-amber-600">[DA COMPLETARE]</span>;

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
        di eventi per la gestione di contatti, aziende, sponsor, staff, volontari, team, turni e attività.
        L'informativa è resa ai sensi del Regolamento (UE) 2016/679 ("GDPR").
      </p>

      <Section title="1. Titolare del trattamento">
        <p>Titolare del trattamento è <strong>MANARA MICHELE</strong> – P. IVA 02671780340.</p>
        <p>Indirizzo: {TODO}. Email di contatto: {TODO}.</p>
      </Section>

      <Section title="2. Dati raccolti durante la registrazione e l'utilizzo">
        <p>Durante la creazione dell'account e l'uso della piattaforma raccogliamo:</p>
        <ul className="list-disc pl-6 space-y-1">
          <li>dati anagrafici e di contatto (nome, cognome, email, eventuale telefono);</li>
          <li>credenziali di accesso: password (conservata in forma cifrata/hash) oppure identità
              tramite login social <strong>Google (Google OAuth 2.0)</strong>;</li>
          <li>dati di utilizzo e log tecnici generati durante la navigazione (es. azioni compiute nella
              piattaforma, data/ora, identificativi di sessione).</li>
        </ul>
      </Section>

      <Section title="3. Dati dell'account e dell'organizzazione">
        <p>
          Per ogni utente viene creato un account associato a un'organizzazione (l'ente/soggetto che
          organizza gli eventi). Trattiamo i dati dell'account (ruolo, permessi, stato) e i dati
          dell'organizzazione necessari a fornire il servizio e a distinguere gli ambienti di lavoro
          dei diversi clienti.
        </p>
      </Section>

      <Section title="4. Gestione dei dati inseriti dagli organizzatori in CRMEvent">
        <p>
          Nell'ambito dell'utilizzo del servizio, gli organizzatori inseriscono all'interno di CRMEvent
          dati relativi a terzi (es. contatti, referenti aziendali, sponsor, staff e volontari). Rispetto
          a tali dati, <strong>l'organizzatore agisce come Titolare del trattamento</strong>, mentre
          <strong> CRMEvent agisce come Responsabile del trattamento</strong>, trattando i dati
          esclusivamente per conto dell'organizzatore e secondo le sue istruzioni, nei limiti di quanto
          necessario alla fornitura del servizio. La disciplina di dettaglio del rapporto (nomina a
          Responsabile ex art. 28 GDPR) è definita nel relativo accordo sul trattamento dei dati {TODO}.
        </p>
      </Section>

      <Section title="5. Finalità e basi giuridiche del trattamento">
        <ul className="list-disc pl-6 space-y-1">
          <li><strong>Erogazione del servizio</strong> (registrazione, autenticazione, funzionalità CRM):
              esecuzione del contratto (art. 6.1.b GDPR).</li>
          <li><strong>Comunicazioni di servizio</strong> (email transazionali, notifiche, reset password):
              esecuzione del contratto (art. 6.1.b GDPR).</li>
          <li><strong>Sicurezza, prevenzione abusi e log tecnici</strong>: legittimo interesse
              (art. 6.1.f GDPR).</li>
          <li><strong>Assistente virtuale AI</strong> (supporto e generazione di insight/ticket):
              esecuzione del contratto e/o legittimo interesse.</li>
          <li><strong>Adempimenti di legge</strong> (fiscali, contabili): obbligo legale (art. 6.1.c GDPR).</li>
          <li><strong>Eventuali cookie analitici/di marketing</strong>: consenso (art. 6.1.a GDPR) – vedi
              la <Link to="/cookie" className="text-tiffany-active font-semibold hover:underline">Cookie Policy</Link>.</li>
        </ul>
      </Section>

      <Section title="6. Conservazione dei dati">
        <p>
          I dati sono conservati per il tempo necessario a fornire il servizio e ad adempiere agli obblighi
          di legge. In caso di cessazione dell'account, i dati vengono cancellati o resi anonimi entro i
          termini previsti. I periodi di conservazione specifici per ciascuna categoria di dati sono {TODO}.
        </p>
      </Section>

      <Section title="7. Sicurezza">
        <p>
          Adottiamo misure tecniche e organizzative adeguate a proteggere i dati, tra cui: cifratura/hashing
          delle password, autenticazione basata su token, controllo degli accessi basato sui ruoli (RBAC) e
          trasmissione dei dati tramite protocollo HTTPS.
        </p>
      </Section>

      <Section title="8. Fornitori e servizi esterni">
        <p>Per erogare il servizio ci avvaliamo dei seguenti fornitori/servizi:</p>
        <ul className="list-disc pl-6 space-y-1">
          <li><strong>Google</strong> – autenticazione tramite Google OAuth 2.0 e sincronizzazione con
              Google Calendar API;</li>
          <li><strong>OpenAI</strong> – modello GPT-5.4-mini utilizzato per l'assistente virtuale AI;</li>
          <li><strong>Provider di invio email</strong> (Resend) – per l'invio delle email transazionali;</li>
          <li><strong>Database MongoDB</strong> – per l'archiviazione dei dati della piattaforma;</li>
          <li><strong>Servizio di object storage</strong> – per i file caricati dagli utenti;</li>
          <li><strong>Infrastruttura di hosting</strong> – {TODO}.</li>
        </ul>
        <p>Ubicazione dei server / data center: {TODO}.</p>
      </Section>

      <Section title="9. Trasferimenti di dati">
        <p>
          Alcuni dei fornitori sopra indicati (es. Google, OpenAI) possono comportare il trasferimento di
          dati verso paesi terzi al di fuori dello Spazio Economico Europeo. Tali trasferimenti, ove
          presenti, avvengono sulla base di garanzie adeguate ai sensi del GDPR (es. Clausole Contrattuali
          Standard). I dettagli specifici delle garanzie applicate sono {TODO}.
        </p>
      </Section>

      <Section title="10. Diritti degli interessati">
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

      <Section title="11. Come richiedere accesso, modifica o cancellazione dei dati">
        <p>
          Gli utenti registrati possono consultare e modificare i dati del proprio account direttamente
          dall'area Profilo della piattaforma. Per esercitare gli altri diritti (incluse cancellazione,
          limitazione, portabilità e opposizione) è possibile inviare una richiesta al Titolare all'indirizzo
          email di contatto privacy {TODO}. Le richieste relative ai dati inseriti da un organizzatore
          nel proprio ambiente CRMEvent vanno indirizzate all'organizzatore stesso, in qualità di Titolare
          di tali dati.
        </p>
      </Section>

      <Section title="12. Contatti privacy">
        <p>Per qualsiasi richiesta relativa al trattamento dei dati personali è possibile contattare il
          Titolare: <strong>MANARA MICHELE</strong> – P. IVA 02671780340 – email: {TODO}.</p>
      </Section>

      <Section title="13. Modifiche alla presente informativa">
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
          migliorare il servizio. Questi cookie vengono installati <strong>solo previo consenso</strong>.
          I fornitori specifici, le finalità di dettaglio e le durate di conservazione sono {TODO}.
        </p>
      </Section>

      <Section title="4. Cookie di marketing / profilazione">
        <p>
          Utilizzati per mostrare contenuti e comunicazioni promozionali in linea con gli interessi
          dell'utente e per misurare l'efficacia delle campagne. Questi cookie vengono installati
          <strong> solo previo consenso</strong>. I fornitori specifici, le finalità di dettaglio e le durate
          di conservazione sono {TODO}.
        </p>
      </Section>

      <Section title="5. Gestione del consenso">
        <p>
          Per i cookie non tecnici (analitici e di marketing) il consenso viene raccolto e gestito tramite
          un banner/Cookie Management Platform (CMP). L'utente può in ogni momento modificare o revocare le
          proprie preferenze. Lo strumento di gestione del consenso attualmente in uso è {TODO}.
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
        Le presenti condizioni disciplinano l'utilizzo del servizio <strong>CRMEvent</strong>. Il testo
        definitivo e completo dei Termini e Condizioni sarà pubblicato prima dell'attivazione commerciale
        del servizio {TODO}.
      </p>
      <Section title="Titolare del servizio">
        <p><strong>MANARA MICHELE</strong> – P. IVA 02671780340.</p>
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
        <Link to="/"><img src="/logo-crmevent.png?v=2" alt="CRMEvent" className="h-7 w-auto" /></Link>
      </header>
      <main className="max-w-3xl mx-auto px-6 py-14 flex-1 w-full">
        <h1 className="font-display text-3xl font-bold text-slate-900 mb-2">{title}</h1>
        <p className="text-xs text-slate-400 mb-8">Ultimo aggiornamento: {TODO}</p>
        <Body />
        <div className="mt-12"><Link to="/" className="text-tiffany-active font-semibold hover:underline">← Torna alla home</Link></div>
      </main>
      <Footer />
    </div>
  );
}
