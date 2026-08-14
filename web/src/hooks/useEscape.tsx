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
import { useSuspendedSubtree } from "~/hooks/suspendedSubtree";

export function useEscape(
  onEscape: () => void,
  active?: () => boolean,
): void {
  const suspended = useSuspendedSubtree();
  createEffect(() => {
    // A stepped-out subtree registers nothing (#352). Callers that pass
    // `active` may already gate on their own suspension; callers that pass
    // none — `PopoverCard`, and so every TermCard / ReferenceCard — had no
    // gate at all, and answered Escape from behind the route on screen.
    if (suspended()) return;
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
