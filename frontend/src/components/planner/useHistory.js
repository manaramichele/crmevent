import { useCallback, useState } from "react";

// Cronologia annulla/ripristina condivisa da Event Planner e demo pubblica.
export default function useHistory(initial = []) {
  const [state, setState] = useState({ past: [], present: initial, future: [] });
  const set = useCallback((next, transient, before) => setState((s) => (transient ? { ...s, present: next }
    : { past: [...s.past, before || s.present].slice(-100), present: next, future: [] })), []);
  const reset = useCallback((v) => setState({ past: [], present: v, future: [] }), []);
  const undo = () => setState((s) => (s.past.length ? { past: s.past.slice(0, -1), present: s.past[s.past.length - 1], future: [s.present, ...s.future] } : s));
  const redo = () => setState((s) => (s.future.length ? { past: [...s.past, s.present], present: s.future[0], future: s.future.slice(1) } : s));
  return { features: state.present, set, reset, undo, redo, canUndo: state.past.length > 0, canRedo: state.future.length > 0 };
}
