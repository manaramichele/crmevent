// Dimensioni standard delle modali CRMEvent (desktop adatta al contenuto, mobile quasi full-width).
// small  -> conferme/alert compatte
// medium -> form standard
// large  -> form complessi / schede dettaglio
// table  -> tabelle ed elenchi (fino a ~95vw con cap, per non tagliare colonne/pulsanti)
export const MODAL = {
  small: "w-[95vw] max-w-md",
  medium: "w-[95vw] max-w-2xl",
  large: "w-[95vw] max-w-4xl",
  table: "w-[95vw] max-w-[1400px]",
};

// Altezza che si adatta al contenuto fino a 90vh, poi scroll interno.
export const MODAL_SCROLL = "max-h-[90vh] overflow-y-auto";
// Layout a colonna per modali con tabella: header/filtri fissi, scroll interno sulla tabella.
export const MODAL_TABLE_LAYOUT = "max-h-[90vh] flex flex-col overflow-hidden";
