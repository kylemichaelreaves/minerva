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
  /** Optional accessory row rendered between the textarea and the
   *  hint/send footer — used on the landing for starter-prompt pills. */
  accessory?: JSX.Element;
  /** Optional element rendered inside the sticky wrap, above the input
   *  box — used by the chat composer for the work-scope chip. */
  scopeChip?: JSX.Element;
}

export default function ComposeField(props: ComposeFieldProps) {
  const isLanding = props.variant === "landing";
  const shell = useMobileShellOptional();
  const fallbackMobile = useMobile();
  const isMobile = () => shell?.isMobile() ?? fallbackMobile();
  const wrapClass = isLanding ? "landing-input-wrap" : "composer-wrap";
  const innerClass = isLanding ? "" : "composer";
  const inputClass = isLanding ? "landing-input" : "composer-input";
  const footClass = isLanding ? "landing-input-foot" : "composer-foot";

  // Chat composer placeholder differs on mobile per design 2a:
  // "Reply to Minerva…" reads as a quoted invitation in the cramped
  // mobile context, where "Continue the enquiry…" felt abstract.
  const placeholder = (): string => {
    if (isLanding) return "What would you like to consider?";
    if (props.disabled) return "Awaiting reply…";
    return isMobile() ? "Reply to Minerva…" : "Continue the enquiry…";
  };

  return (
    <div class={wrapClass}>
      {props.scopeChip}
      <div class={innerClass}>
        <textarea
          ref={props.c.setRef}
          class={inputClass}
          placeholder={placeholder()}
          value={props.c.value()}
          disabled={props.disabled}
          onInput={props.c.onInput}
          onKeyDown={props.c.onKeyDown}
          rows={1}
          autofocus={isLanding}
        />
        {props.accessory}
        <div class={footClass}>
          {isLanding ? (
            <>
              <span class="landing-input-hint">{props.hint}</span>
              <button
                class={classnames("send-btn", props.c.sendDisabled() && "disabled")}
                onClick={props.c.send}
              >
                {props.sendLabel} <SendIcon />
              </button>
            </>
          ) : (
            <>
              <div class="left">{props.hint}</div>
              <button
                class={classnames("send-btn", props.c.sendDisabled() && "disabled")}
                onClick={props.c.send}
                disabled={props.disabled}
              >
                {props.sendLabel} <SendIcon />
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
