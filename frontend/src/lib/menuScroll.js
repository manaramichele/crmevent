// Menu portalizzati dentro una modale: la modale blocca lo scroll fuori dalla sua area (react-remove-scroll
// ascolta touchmove/wheel su document). Fermando la propagazione qui il menu scorre col dito/rotellina,
// mentre la pagina sotto resta bloccata.
export const isolateScroll = {
  onTouchMove: (e) => e.stopPropagation(),
  onWheel: (e) => e.stopPropagation(),
};

export const MENU_SCROLL = "overscroll-contain touch-pan-y [-webkit-overflow-scrolling:touch]";
