import { useNavigate } from "react-router-dom";
import { FileSpreadsheet } from "lucide-react";
import { Button } from "@/components/ui/button";

// Accesso unico al sistema di importazione Excel/CSV, preimpostato sul modulo della sezione.
export function ImportLink({ target, label = "Importa Excel/CSV" }) {
  const nav = useNavigate();
  return <Button type="button" variant="outline" onClick={() => nav(`/importazione?target=${target}`)} data-testid={`import-link-${target}`}><FileSpreadsheet className="w-4 h-4 mr-1.5" />{label}</Button>;
}
