import { onSettled } from "solid-js";
import type { JSX } from "@solidjs/web";
import { createComposer } from "~/utils/composer";
import ComposeField from "~/components/cards/ComposeField";
import KeyHints from "~/components/cards/KeyHints";
import "~/features/Composer/composer.css";

// The no-break space keeps each label on its key cap's line.
const HINTS = [
  ["Enter", " send"],
  ["⇧ Enter", " new line"],
] as const;

interface ComposerProps {
  onSend: (text: string) => void;
  /** When true, ignore Enter/click and gray-out the controls. The server
   * lock would serialize concurrent requests anyway, but the UX feedback
   * is what users need to see. */
  disabled?: boolean;
  /** Optional work-scope chip rendered in the footer. */
  scopeChip?: JSX.Element;
  /** Focus the textarea as soon as it mounts. Only the landing submit asks:
   *  the question you typed moves into this box, so your next keystroke
   *  should too (and on a phone the keyboard stays up). Sidebar picks and
   *  direct loads leave focus alone. */
  focusOnMount?: boolean;
  /** True while the landing → chat transition runs. */
  entering?: boolean;
}

export default function Composer(props: ComposerProps) {
  const c = createComposer({
    minPx: 28,
    maxPx: 180,
    onSubmit: (text) => {
      props.onSend(text);
    },
    clearOnSend: true,
    isDisabled: () => Boolean(props.disabled),
  });

  let textarea: HTMLTextAreaElement | undefined;
  const field = {
    ...c,
    setRef: (el: HTMLTextAreaElement) => {
      textarea = el;
      c.setRef(el);
    },
  };
  onSettled(() => {
    if (props.focusOnMount) textarea?.focus({ preventScroll: true });
  });

  return (
    <ComposeField
      variant="composer"
      c={field}
      entering={props.entering}
      sendLabel="Send"
      disabled={props.disabled}
      scopeChip={props.scopeChip}
      hint={<KeyHints hints={HINTS} />}
    />
  );
}
