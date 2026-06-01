import { Show, type JSX } from "solid-js";
import { Portal } from "solid-js/web";
import { useEscape } from "~/hooks/useEscape";

export interface MobileSheetProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: JSX.Element;
}

export function MobileSheet(props: MobileSheetProps) {
  useEscape(() => {
    if (props.open) props.onClose();
  });

  return (
    <Show when={props.open}>
      <Portal>
        <div class="mobile-sheet-scrim" onClick={() => props.onClose()} />
        <div class="mobile-sheet" role="dialog" aria-modal="true" aria-label={props.title}>
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
