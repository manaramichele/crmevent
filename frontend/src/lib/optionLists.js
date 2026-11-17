import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";

export const ADD_OPTION = "__add_new__";
export const LISTS_CHANGED = "option-lists:changed";

export const activeOptions = (settings, key) => {
  const off = new Set((settings?.disattivati || {})[key] || []);
  return (settings?.[key] || []).filter((v) => !off.has(v));
};

export async function addOption(key, value) {
  const v = (value || "").trim();
  if (!v) return null;
  try {
    const { data } = await api.post(`/settings/lists/${key}/items`, { value: v });
    toast[data.created ? "success" : "info"](data.created ? "Voce aggiunta" : "Voce già presente: selezionata.");
    window.dispatchEvent(new Event(LISTS_CHANGED));
    return data.value;
  } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); return null; }
}
