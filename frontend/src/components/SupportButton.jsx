import { NavLink } from "react-router-dom";
import { Headset } from "lucide-react";

const CLS = "shrink-0 inline-flex items-center justify-center gap-1.5 h-10 w-10 sm:w-auto sm:px-3 rounded-lg bg-[#0ABAB5] text-black text-sm font-semibold whitespace-nowrap shadow-sm transition-[background-color,box-shadow,transform] duration-150 hover:bg-[#09A8A3] hover:shadow active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0ABAB5]/50 focus-visible:ring-offset-1";

export const supportMailto = (user) => {
  const subject = ["Supporto CRMEvent", user?.org_name, user?.name].filter((x) => x && String(x).trim()).join(" – ");
  return `mailto:support@crmevent.it?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent("Buongiorno, vorrei ricevere supporto per CRMEvent.\n\n")}`;
};

export default function SupportButton({ user }) {
  const inner = <><Headset className="w-4 h-4" aria-hidden="true" /><span className="hidden sm:inline">Supporto dedicato</span></>;
  if (user?.saas?.enabled && user.saas.plan === "bronze") {
    return <a href={supportMailto(user)} data-testid="header-assistenza-button" data-mode="email" aria-label="Supporto dedicato" title="Supporto dedicato via email" className={CLS}>{inner}</a>;
  }
  return <NavLink to="/assistenza" data-testid="header-assistenza-button" data-mode="video" aria-label="Supporto dedicato" title="Supporto dedicato" className={CLS}>{inner}</NavLink>;
}
