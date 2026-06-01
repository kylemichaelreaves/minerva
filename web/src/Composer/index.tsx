import { createComposer } from "~/utils/composer";
import ComposeField from "~/components/ComposeField";
import "~/Composer/composer.css";

interface ComposerProps {
  onSend: (text: string) => void;
  /** When true, ignore Enter/click and gray-out the controls. The server
   * lock would serialize concurrent requests anyway, but the UX feedback
   * is what users need to see. */
  disabled?: boolean;
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

  return (
    <ComposeField
      variant="composer"
      c={c}
      sendLabel="Send"
      disabled={props.disabled}
      hint={
        <>
          <span>
            <span class="kbd">Enter</span> &nbsp;send
          </span>
          <span>
            <span class="kbd">⇧ Enter</span> &nbsp;new line
          </span>
        </>
      }
    />
  );
}
