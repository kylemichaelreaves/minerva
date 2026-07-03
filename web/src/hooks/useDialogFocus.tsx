// Focus management for modal dialogs: move focus into the dialog on
// open, trap Tab within it, restore the previously-focused element on
// close. Paired with role="dialog" + aria-modal on the shell.

import { createEffect, onCleanup, type Accessor } from "solid-js";

const FOCUSABLE =
  'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

export function useDialogFocus(
  rootRef: () => HTMLElement | undefined,
  active: Accessor<boolean>,
): void {
  createEffect(() => {
    if (!active()) return;
    const root = rootRef();
    if (!root) return;

    const previouslyFocused = document.activeElement as HTMLElement | null;

    queueMicrotask(() => {
      const first = root.querySelector<HTMLElement>(FOCUSABLE);
      first?.focus();
    });

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;
      const focusables = [
        ...root.querySelectorAll<HTMLElement>(FOCUSABLE),
      ].filter((el) => !el.hasAttribute("disabled"));
      if (focusables.length === 0) return;
      const first = focusables[0]!;
      const last = focusables[focusables.length - 1]!;
      const current = document.activeElement;
      if (e.shiftKey) {
        if (current === first || !root.contains(current)) {
          e.preventDefault();
          last.focus();
        }
      } else if (current === last) {
        e.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    onCleanup(() => {
      document.removeEventListener("keydown", onKeyDown);
      previouslyFocused?.focus?.();
    });
  });
}
