import { useCallback } from "react";

// Ref callback: abilita lo scroll con rotellina/trackpad su un contenitore scrollabile
// anche quando è dentro un Popover portalizzato in una modale (react-remove-scroll
// altrimenti blocca gli eventi wheel esterni all'area bloccata).
export function useWheelScroll() {
  return useCallback((node) => {
    if (!node || node.__wheelBound) return;
    node.__wheelBound = true;
    node.addEventListener(
      "wheel",
      (e) => {
        if (node.scrollHeight <= node.clientHeight) return; // niente da scrollare
        e.preventDefault();
        e.stopPropagation();
        const delta = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaMode === 2 ? e.deltaY * node.clientHeight : e.deltaY;
        node.scrollTop += delta;
      },
      { passive: false }
    );
  }, []);
}
