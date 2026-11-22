// Shared window-level keyboard navigation for list/queue surfaces.
//
// Two surfaces grew this independently — the concordance KWIC grid
// (Concordance/components/LemmaDetail.tsx) and the curator review
// queue (features/Refs/components/Review.tsx) — each with its own incomplete
// form-element guard (input/textarea only: selects and contenteditable
// regions lost their arrow keys, and Escape fought the mobile filter
// sheet). This hook owns:
//   * the keydown listener lifecycle (added in onSettled, removed by
//     the cleanup it returns);
//   * an editable-target guard (input, textarea, select,
//     contenteditable) that exempts EVERY key;
//   * an activatable-control guard (button, a[href], summary, and the
//     button/link/option roles) that exempts ENTER ONLY: Enter must
//     activate the focused control, not open the list's current item
//     (#702). j/k and the arrows still navigate from a focused control,
//     so a user can toggle a filter chip and keep stepping the list;
//   * an `enabled` accessor so callers can mute navigation while a
//     modal/sheet is open;
//   * the j/k + Arrow (and optionally Left/Right) → next/prev mapping,
//     with Enter/Escape hooks.
//
// `preventDefault` fires only for keys the hook actually handles, so
// unhandled keys keep their browser behavior.

import { onSettled } from "solid-js";

/** True when the keystroke belongs to a form control or editable
 *  region and must not be hijacked for list navigation. */
export function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName.toLowerCase();
  if (tag === "input" || tag === "textarea" || tag === "select") return true;
  // The lib types say boolean, but jsdom leaves isContentEditable
  // undefined at runtime — coerce so callers get a real boolean.
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-type-conversion
  return Boolean(target.isContentEditable);
}

const ACTIVATABLE =
  'button, a[href], summary, [role="button"], [role="link"], [role="option"]';

/** True when Enter on this target should activate a control rather
 *  than be taken as the list's "select" key (#702). Matches the control
 *  itself or any ancestor, so Enter on an icon inside a button is still
 *  Enter on the button. */
export function isActivatableTarget(target: EventTarget | null): boolean {
  return target instanceof Element && target.closest(ACTIVATABLE) !== null;
}

export interface ListKeyboardNavOpts {
  /** Gate: return false to ignore every key — e.g. while a mobile
   *  filter sheet or modal is open (lets Escape reach the sheet). */
  enabled?: () => boolean;
  /** j / ArrowDown (and ArrowRight when `horizontal`). */
  onNext: () => void;
  /** k / ArrowUp (and ArrowLeft when `horizontal`). */
  onPrev: () => void;
  /** Enter. Omit to leave Enter alone. Never fires when the target is
   *  an activatable control (see `isActivatableTarget`). */
  onSelect?: () => void;
  /** Escape. Omit to leave Escape alone. */
  onEscape?: () => void;
  /** Also map ArrowRight/ArrowLeft to next/prev (review-queue style). */
  horizontal?: boolean;
  /** Pre-handler for surface-specific chords (e.g. ⌘↑/⌘↓ scope zoom).
   *  Runs after the guards but before the default mapping — and before
   *  the modifier-key bail-out, so chords can use meta/ctrl. Return
   *  true when handled (the hook then stops). The pre-handler does its
   *  own preventDefault. */
  onKey?: (e: KeyboardEvent) => boolean;
}

export function useListKeyboardNav(opts: ListKeyboardNavOpts): void {
  const onKeydown = (e: KeyboardEvent): void => {
    if (opts.enabled && !opts.enabled()) return;
    if (isEditableTarget(e.target)) return;
    if (opts.onKey?.(e)) return;
    // Modified keystrokes (⌘C, alt-arrows, …) belong to the browser.
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === "j" || e.key === "ArrowDown" || (opts.horizontal && e.key === "ArrowRight")) {
      e.preventDefault();
      opts.onNext();
    } else if (
      e.key === "k" ||
      e.key === "ArrowUp" ||
      (opts.horizontal && e.key === "ArrowLeft")
    ) {
      e.preventDefault();
      opts.onPrev();
    } else if (e.key === "Enter" && opts.onSelect && !isActivatableTarget(e.target)) {
      e.preventDefault();
      opts.onSelect();
    } else if (e.key === "Escape" && opts.onEscape) {
      e.preventDefault();
      opts.onEscape();
    }
  };

  onSettled(() => {
    window.addEventListener("keydown", onKeydown);
    return () => {
      window.removeEventListener("keydown", onKeydown);
    };
  });
}
