// Tiny helper: register a window keydown listener that fires
// `onEscape` whenever the user presses Esc, with Solid mount/cleanup
// wired so the listener disappears with the component. Used by
// transient overlays (TermCard, ConfirmDialog) — anything where Esc
// should dismiss.
//
// The handler calls `preventDefault()` so Esc doesn't also clear a
// focused selection / bubble to a parent overlay. If you need
// modifier behavior or other keys, build it on top of this; the
// helper deliberately stays one job.
//
// `active` is an optional reactive accessor. When provided, the
// listener is registered iff `active()` is truthy. This lets always-
// mounted dialogs (e.g. ConfirmDialog, which lives at App scope and
// gates on `props.open`) avoid intercepting Esc while closed.

import { createEffect, onCleanup } from "solid-js";

export function useEscape(
  onEscape: () => void,
  active?: () => boolean,
): void {
  createEffect(() => {
    if (active && !active()) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.preventDefault();
      onEscape();
    };
    window.addEventListener("keydown", handler);
    onCleanup(() => {
      window.removeEventListener("keydown", handler);
    });
  });
}
