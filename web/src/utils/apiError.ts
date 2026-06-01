// Shared user-visible error surface for fetch failures.
//
// Most non-chat fetches in the app (conversations list, works list,
// reader range, refs, citation context) previously failed silently to
// `console.warn` — the user saw nothing while the sidebar or reader
// stalled. `apiError(message)` pushes a transient toast onto the
// stack, rendered by `<Toasts />` in App.tsx, so the failure is
// visible without being a modal interruption.
//
// Module-level signal acts as a global event bus. The Solid runtime
// re-evaluates `useToasts()` in any component that reads it whenever
// the stack changes — no context provider needed.

import { createSignal } from "solid-js";

export interface ErrorToast {
  id: number;
  message: string;
}

/** Auto-dismiss timeout. Long enough for the user to read a short
 *  sentence; short enough not to pile up across rapid failures. */
const TOAST_TTL_MS = 6000;

let idCounter = 0;
const [toasts, setToasts] = createSignal<ErrorToast[]>([]);

/** Push a user-visible error toast. The toast auto-dismisses after
 *  TOAST_TTL_MS or when the user clicks the × button. Returns the
 *  toast id so the caller can dismiss it imperatively if needed
 *  (rare — callers typically just fire-and-forget).
 *
 *  Use for fetch failures the user could otherwise miss — sidebar
 *  loads, works lists, refs/review queue, the reader's window load.
 *  The chat handler has its own inline error surface (errorTurn);
 *  this helper is for everything else. */
export function apiError(message: string): number {
  const id = ++idCounter;
  setToasts((cur) => [...cur, { id, message }]);
  // setTimeout (not queueMicrotask) — we genuinely want the toast to
  // sit for several seconds before disappearing.
  window.setTimeout(() => {
    dismissToast(id);
  }, TOAST_TTL_MS);
  return id;
}

export function dismissToast(id: number): void {
  setToasts((cur) => cur.filter((t) => t.id !== id));
}

/** Current toast stack. Use in components that render the toast UI. */
export const useToasts = (): (() => ErrorToast[]) => toasts;

/** Test-only — clear all toasts. Not exported through index; tests
 *  import directly from the module. */
export function _resetToastsForTesting(): void {
  setToasts([]);
  idCounter = 0;
}
