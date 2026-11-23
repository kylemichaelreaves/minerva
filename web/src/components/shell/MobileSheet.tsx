import { Show, createSignal } from "solid-js";
import type { JSX } from "@solidjs/web";
import { Portal } from "@solidjs/web";
import { useDialogFocus } from "~/hooks/useDialogFocus";
import { useEscape } from "~/hooks/useEscape";

export interface MobileSheetProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: JSX.Element;
}

export function MobileSheet(props: MobileSheetProps) {
  const [dialogRef, setDialogRef] = createSignal<HTMLDivElement>();

  useEscape(
    () => {
      props.onClose();
    },
    () => props.open,
  );
  useDialogFocus(dialogRef, () => props.open);

  return (
    <Show when={props.open}>
      <Portal>
        {/* A real button, not a <div onClick>: the scrim was the only
            pointer-driven dismissal and reached nothing else
            (typescript:S6848 + typescript:S1082). Escape closes the sheet too,
            via useEscape above. */}
        <button
          type="button"
          class="mobile-sheet-scrim"
          aria-label="Dismiss"
          onClick={() => props.onClose()}
        />
        <div
          ref={setDialogRef}
          class="mobile-sheet"
          role="dialog"
          aria-modal="true"
          aria-label={props.title}
        >
          <header class="mobile-sheet-head">
            <h2>{props.title}</h2>
            <button type="button" class="mobile-sheet-close" onClick={() => props.onClose()}>
              Done
            </button>
          </header>
          <div class="mobile-sheet-body">{props.children}</div>
        </div>
      </Portal>
    </Show>
  );
}
