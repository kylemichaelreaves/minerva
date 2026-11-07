import { type JSX } from "solid-js";
import { classnames } from "~/utils/util";
import { SendIcon } from "~/components/primitives/Icons";
import type { ComposerState } from "~/utils/composer";
import { useMobileShellOptional } from "~/components/shell/MobileShellContext";
import { useMobile } from "~/hooks/useMobile";

export interface ComposeFieldProps {
  variant: "landing" | "composer";
  c: ComposerState;
  sendLabel: string;
  hint: JSX.Element;
  disabled?: boolean;
  /** Optional work-scope pill, rendered at the start of the footer. */
  scopeChip?: JSX.Element;
  /** True while the landing → chat transition runs (chat composer only). */
  entering?: boolean;
}

export default function ComposeField(props: ComposeFieldProps) {
  const isLanding = () => props.variant === "landing";
  const shell = useMobileShellOptional();
  const fallbackMobile = useMobile();
  const isMobile = () => shell?.isMobile() ?? fallbackMobile();
  const wrapClass = () =>
    classnames(
      isLanding() ? "landing-input-wrap compose-card" : "composer-wrap",
      props.entering && "lt-entering",
    );
  const cardClass = () => (isLanding() ? undefined : "composer compose-card");
  const inputClass = () =>
    isLanding() ? "landing-input compose-input" : "composer-input compose-input";

  // Chat composer placeholder differs on mobile per design 2a:
  // "Reply to Minerva…" reads as a quoted invitation in the cramped
  // mobile context, where "Continue the enquiry…" felt abstract.
  const placeholder = (): string => {
    if (isLanding()) return "What would you like to consider?";
    if (props.disabled) return "Awaiting reply…";
    return isMobile() ? "Reply to Minerva…" : "Continue the enquiry…";
  };

  // One footer for both variants: scope pill + hint on the left, send on
  // the right. The landing wrap is itself the card; the chat card sits
  // inside the sticky `.composer-wrap`.
  const body = (
    <>
      <textarea
        ref={props.c.setRef}
        class={inputClass()}
        placeholder={placeholder()}
        value={props.c.value()}
        disabled={props.disabled}
        onInput={(e) => props.c.onInput(e)}
        onKeyDown={(e) => props.c.onKeyDown(e)}
        rows={1}
        autofocus={isLanding()}
      />
      <div class={classnames("compose-foot", isLanding() ? "landing-input-foot" : "composer-foot")}>
        <div class="compose-foot__left">
          {props.scopeChip}
          {props.hint}
        </div>
        <button
          class={classnames("compose-send", props.c.sendDisabled() && "disabled")}
          onClick={props.c.send}
          disabled={props.disabled}
        >
          {props.sendLabel} <SendIcon />
        </button>
      </div>
    </>
  );

  return (
    <div class={wrapClass()}>{isLanding() ? body : <div class={cardClass()}>{body}</div>}</div>
  );
}
