import { useAuth } from "@/context/AuthContext";

// Specchio lato UI dei permessi calcolati dal backend (/auth/me → permissions). Il backend resta l'autorità.
export const isOrgAdmin = (u) => !!u && (u.role === "superadmin" || u.org_role === "admin_org");

export const can = (u, section, action = "view") => {
  if (!u) return false;
  if (isOrgAdmin(u)) return true;
  const p = u.permissions;
  if (!p || p.admin) return true;
  return (p.sections?.[section] || []).includes(action);
};

export function useCan(section) {
  const { user } = useAuth();
  return {
    view: can(user, section, "view"), create: can(user, section, "create"),
    edit: can(user, section, "edit"), remove: can(user, section, "delete"),
  };
}
