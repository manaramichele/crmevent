import { useAuth } from "@/context/AuthContext";

// Specchio lato UI dei permessi calcolati dal backend (/auth/me → permissions). Il backend resta l'autorità.
export const isOrgAdmin = (u) => !!u && (u.role === "superadmin" || u.org_role === "admin_org");

// Nomina Team Leader: lettura dei propri Team garantita; modifica componenti / turni solo con i flag dedicati.
const tlCan = (u, section, action) => {
  if (!(u.led_team_ids || []).length) return false;
  const tl = u.permissions?.team_leader || {};
  if (["staff", "teams", "turni", "dashboard"].includes(section) && action === "view") return true;
  if (section === "staff" && (action === "edit" || action === "delete")) return !!tl.edit_members;
  if (section === "turni") return !!tl.manage_shifts;
  return false;
};

// "teams" e "turni" sono sotto-aree della sezione Staff
export const can = (u, section, action = "view") => {
  if (!u) return false;
  if (isOrgAdmin(u)) return true;
  const p = u.permissions;
  if (!p || p.admin) return true;
  const sec = section === "teams" || section === "turni" ? "staff" : section;
  return (p.sections?.[sec] || []).includes(action) || tlCan(u, section, action);
};

export const canSendInvites = (u) => !!u && (isOrgAdmin(u) || !!u.permissions?.admin || !!u.permissions?.send_invites);

export function useCan(section) {
  const { user } = useAuth();
  return {
    view: can(user, section, "view"), create: can(user, section, "create"),
    edit: can(user, section, "edit"), remove: can(user, section, "delete"),
  };
}
