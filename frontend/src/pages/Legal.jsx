import { Link } from "react-router-dom";

const CONTENT = {
  privacy: { title: "Privacy Policy", body: "Questa informativa descrive il trattamento dei dati personali raccolti tramite CRMEvent. Il testo definitivo sarà fornito prima della commercializzazione. Per informazioni scrivi a privacy@crmevent.it." },
  cookie: { title: "Cookie Policy", body: "CRMEvent utilizza esclusivamente cookie tecnici necessari al funzionamento della piattaforma. Eventuali cookie analitici o di marketing verranno introdotti solo previo consenso, tramite una futura Cookie Management Platform." },
  termini: { title: "Termini e Condizioni", body: "Condizioni di utilizzo del servizio CRMEvent. Il testo definitivo sarà pubblicato prima dell'attivazione commerciale del servizio." },
};

export default function Legal({ type }) {
  const c = CONTENT[type] || CONTENT.privacy;
  return (
    <div className="min-h-screen bg-white">
      <header className="border-b border-slate-100 h-16 flex items-center px-6">
        <Link to="/"><img src="/logo-crmevent.png" alt="crmevent" className="h-7 w-auto" /></Link>
      </header>
      <main className="max-w-3xl mx-auto px-6 py-16">
        <h1 className="font-display text-3xl font-bold text-slate-900 mb-6">{c.title}</h1>
        <p className="text-slate-600 leading-relaxed">{c.body}</p>
        <div className="mt-10"><Link to="/" className="text-tiffany-active font-semibold hover:underline">← Torna alla home</Link></div>
      </main>
    </div>
  );
}
