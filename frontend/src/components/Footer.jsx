import { Link } from "react-router-dom";

export default function Footer() {
  return (
    <footer className="bg-slate-900 text-slate-300" data-testid="site-footer">
      <div className="max-w-6xl mx-auto px-6 py-14 grid grid-cols-2 md:grid-cols-4 gap-8">
        <div className="col-span-2 md:col-span-1">
          <img src="/logo-footer-dark.png?v=3" alt="CRMEvent" className="h-10 sm:h-12 w-auto" />
          <p className="text-sm text-slate-400 mt-4 max-w-xs">Il CRM per organizzare eventi: contatti, sponsor, staff, volontari, team, turni e attività.</p>
        </div>
        <div>
          <div className="text-white font-semibold mb-3 text-sm">Prodotto</div>
          <ul className="space-y-2 text-sm">
            <li><a href="/#funzionalita" className="hover:text-white">Funzionalità</a></li>
            <li><Link to="/prezzi" data-testid="footer-pricing-link" className="hover:text-white">Prezzi</Link></li>
            <li><a href="/#staff" className="hover:text-white">Staff & Volontari</a></li>
            <li><a href="/#sponsor" className="hover:text-white">Sponsor</a></li>
            <li><Link to="/login" className="hover:text-white">Accedi</Link></li>
          </ul>
        </div>
        <div>
          <div className="text-white font-semibold mb-3 text-sm">Azienda</div>
          <ul className="space-y-2 text-sm"><li><a href="/#demo" className="hover:text-white">Contatti</a></li></ul>
        </div>
        <div>
          <div className="text-white font-semibold mb-3 text-sm">Legale</div>
          <ul className="space-y-2 text-sm">
            <li><Link to="/privacy-policy" data-testid="footer-privacy-link" className="hover:text-white">Privacy Policy</Link></li>
            <li><Link to="/cookie" data-testid="footer-cookie-link" className="hover:text-white">Cookie Policy</Link></li>
            <li><Link to="/termini" data-testid="footer-terms-link" className="hover:text-white">Termini e Condizioni</Link></li>
          </ul>
        </div>
      </div>
      <div className="border-t border-white/10">
        <div className="max-w-6xl mx-auto px-6 py-5 text-sm text-slate-400" data-testid="footer-legal-line">
          © 2026 <strong className="font-semibold text-slate-300">CRMEvent</strong> – P. IVA 02671780340
        </div>
      </div>
    </footer>
  );
}
