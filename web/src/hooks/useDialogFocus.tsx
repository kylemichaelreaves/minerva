// Focus management for modal dialogs: move focus into the dialog on
// open, trap Tab within it, restore the previously-focused element on
// close. Paired with role="dialog" + aria-modal on the shell.

import { createEffect, type Accessor } from "solid-js";
import { useSuspendedSubtree } from "~/hooks/suspendedSubtree";

const FOCUSABLE = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

export function useDialogFocus(
  rootRef: () => HTMLElement | undefined,
  active: Accessor<boolean>,
): void {
  const suspended = useSuspendedSubtree();
  createEffect(
    // Compute resolves the root to manage, or undefined while there is
    // nothing to do; apply (untracked) wires focus and the Tab trap to it and
    // returns the teardown that undoes both. `rootRef` is read here, in the
    // tracking phase, so it must be signal-backed when the element mounts
    // after the hook runs (a dialog behind `<Show>`): a plain `let` read here
    // would return undefined and never re-run.
    (): HTMLElement | undefined => {
      // Nothing while stepped out (#352). The Tab trap is the reason: its
      // shift-Tab guard is `current === first || !root.contains(current)`, and
      // focus during a step-out is on the route that replaced this subtree, so
      // the second disjunct always holds — every shift-Tab out there was
      // cancelled and redirected into a dialog inside a `display: none` subtree,
      // whose elements cannot take focus. Also stops the focus grab on the way
      // back in from stealing the caret off the visible route.
      if (suspended()) return undefined;
      if (!active()) return undefined;
      return rootRef();
    },
    (root) => {
      if (!root) return;

      const previouslyFocused = document.activeElement as HTMLElement | null;

      queueMicrotask(() => {
        const first = root.querySelector<HTMLElement>(FOCUSABLE);
        first?.focus();
      });

      const onKeyDown = (e: KeyboardEvent) => {
        if (e.key !== "Tab") return;
        const focusables = [...root.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
          (el) => !el.hasAttribute("disabled"),
        );
        const first = focusables.at(0);
        const last = focusables.at(-1);
        // Both are undefined together, exactly when the list is empty.
        if (!first || !last) return;
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
      return () => {
        document.removeEventListener("keydown", onKeyDown);
        previouslyFocused?.focus();
      };
    },
  );
}
