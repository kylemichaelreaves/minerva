// Modal confirm dialog. Mirrors the design's behavior:
//   * scrim click cancels
//   * Esc cancels
//   * Enter confirms (the danger button is also autofocused)
// Mounted only when `open` is true so the keydown handler isn't bound
// when there's nothing to confirm.

import { Show, createEffect, onCleanup } from "solid-js";
import type { JSX } from "solid-js";
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
  // Esc and Enter both fire only while open. Esc is delegated to the
  // shared useEscape helper; Enter stays inline because dialog-confirm
  // is the only place we want that key, and folding it into a
  // generic helper isn't worth the indirection.
  useEscape(
    () => {
      props.onCancel();
    },
    () => props.open,
  );
  createEffect(() => {
    if (!props.open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Enter") {
        e.preventDefault();
        props.onConfirm();
      }
    };
    window.addEventListener("keydown", onKey);
    onCleanup(() => {
      window.removeEventListener("keydown", onKey);
    });
  });

  return (
    <Show when={props.open}>
      <div
        class="dialog-scrim"
        onClick={() => {
          props.onCancel();
        }}
      >
        <div
          class="dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby="confirm-dialog-title"
          onClick={(e) => {
            e.stopPropagation();
          }}
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
              ref={(el) => {
                queueMicrotask(() => {
                  el.focus();
                });
              }}
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
