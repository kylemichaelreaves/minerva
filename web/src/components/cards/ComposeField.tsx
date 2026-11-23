import type { JSX } from "@solidjs/web";
import { classnames } from "~/utils/util";
import { SendIcon } from "~/components/primitives/Icons";
import type { ComposerState } from "~/utils/composer";
import { useIsMobile } from "~/components/shell/MobileShellContext";
import { LANDING_LANG, LANDING_PROMPT } from "~/components/cards/landingPrompts";
import "~/components/cards/composeCard.css";

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
  const isMobile = useIsMobile();
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
    if (isLanding()) return LANDING_PROMPT;
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
        // The landing prompt may be French or German, so screen readers
        // need its language. Only while empty: `lang` also sets the
        // spellcheck language for whatever the user types.
        lang={isLanding() && !props.c.value() ? LANDING_LANG : undefined}
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
          onClick={() => props.c.send()}
          disabled={props.disabled}
          aria-label={props.sendLabel}
        >
          <span class="compose-send__label">{props.sendLabel}</span> <SendIcon />
        </button>
      </div>
    </>
  );

  return (
    <div class={wrapClass()}>{isLanding() ? body : <div class={cardClass()}>{body}</div>}</div>
  );
}
