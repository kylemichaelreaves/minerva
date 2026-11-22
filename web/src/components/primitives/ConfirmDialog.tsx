// Modal confirm dialog. Mirrors the design's behavior:
//   * scrim click cancels
//   * Esc cancels
//   * Enter confirms (the danger button is also autofocused)
// Mounted only when `open` is true so the keydown handler isn't bound
// when there's nothing to confirm.

import { Show, createEffect, createSignal } from "solid-js";
import type { JSX } from "@solidjs/web";
import { useDialogFocus } from "~/hooks/useDialogFocus";
import { useEscape } from "~/hooks/useEscape";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ConfirmDialog(props: ConfirmDialogProps): JSX.Element {
  // A signal, not a plain `let`: the dialog mounts behind `<Show>` after the
  // hooks below run, and useDialogFocus tracks the ref to see it arrive.
  const [dialogRef, setDialogRef] = createSignal<HTMLDivElement>();

  // Esc cancels. Enter confirms — but ONLY while focus is inside the
  // dialog. A window-level Enter that fired regardless of focus would
  // delete a conversation on a stray keystroke while the user was
  // typing in a background field (issue #60). useDialogFocus moves
  // focus into the dialog on open, traps Tab, and restores focus on
  // close, so the focus-within check is reliable.
  useEscape(
    () => {
      props.onCancel();
    },
    () => props.open,
  );
  useDialogFocus(dialogRef, () => props.open);
  createEffect(
    () => props.open,
    (open) => {
      if (!open) return;
      const onKey = (e: KeyboardEvent) => {
        if (e.key === "Enter" && dialogRef()?.contains(document.activeElement)) {
          e.preventDefault();
          props.onConfirm();
        }
      };
      window.addEventListener("keydown", onKey);
      return () => {
        window.removeEventListener("keydown", onKey);
      };
    },
  );

  return (
    <Show when={props.open}>
      <div class="dialog-scrim">
        {/* The outside-click dismissal lives on a real button laid over the
            scrim, not on the scrim div itself. As a <div onClick> it was
            mouse-only (typescript:S6848 + typescript:S1082); as a sibling of
            the dialog rather than its parent, it also removes the need for
            the `stopPropagation` shim the dialog used to carry to survive it
            (typescript:S6847 + typescript:S1082). Named "Dismiss" rather than
            "Cancel" so it does not collide with the visible ghost button. */}
        <button
          type="button"
          class="dialog-scrim-hit"
          aria-label="Dismiss"
          onClick={() => {
            props.onCancel();
          }}
        />
        <div
          ref={setDialogRef}
          class="dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby="confirm-dialog-title"
        >
          <div class="dialog-title" id="confirm-dialog-title">
            {props.title}
          </div>
          <div class="dialog-body">{props.message}</div>
          <div class="dialog-actions">
            <button
              class="dialog-btn ghost"
              onClick={() => {
                props.onCancel();
              }}
            >
              {props.cancelLabel ?? "Cancel"}
            </button>
            <button
              class="dialog-btn danger"
              onClick={() => {
                props.onConfirm();
              }}
            >
              {props.confirmLabel ?? "Delete"}
            </button>
          </div>
        </div>
      </div>
    </Show>
  );
}
