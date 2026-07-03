import { type JSX, createSignal } from "solid-js";
import { POPOVER_CARD_WIDTH } from "~/utils/popoverPosition";
import { useDialogFocus } from "~/hooks/useDialogFocus";
import { useEscape } from "~/hooks/useEscape";
import { usePopoverPosition } from "~/hooks/usePopoverPosition";

export interface PopoverCardProps {
  anchor: DOMRect;
  /** CSS class prefix: `termcard` or `refcard`. */
  variant: "termcard" | "refcard";
  ariaLabel: string;
  heightEstimate?: number;
  onClose: () => void;
  children: JSX.Element;
  /** Extra classes on the outer shell (e.g. `is-pending`). */
  class?: string;
  /** Override fixed width (term cards use POPOVER_CARD_WIDTH). */
  width?: number;
  /** Text flow at the anchor — RTL passages need logical-start placement. */
  direction?: "ltr" | "rtl";
}

export default function PopoverCard(props: PopoverCardProps) {
  const [cardRef, setCardRef] = createSignal<HTMLDivElement>();
  const { pos } = usePopoverPosition(() => props.anchor, () => ({
    heightEstimate: props.heightEstimate ?? 400,
    direction: props.direction ?? "ltr",
  }));

  useEscape(() => {
    props.onClose();
  });
  useDialogFocus(cardRef, () => true);

  function onCardClick(e: MouseEvent) {
    e.stopPropagation();
  }

  const width = props.width ?? POPOVER_CARD_WIDTH;
  const shellClass = () =>
    `${props.variant}${pos().flipUp ? " flip-up" : ""}${props.class ? ` ${props.class}` : ""}`;

  return (
    <div
      ref={setCardRef}
      class={shellClass()}
      style={{
        top: `${pos().top}px`,
        left: `${pos().left}px`,
        ...(props.variant === "termcard" ? { width: `${width}px` } : {}),
      }}
      onClick={onCardClick}
      role="dialog"
      aria-modal="true"
      aria-label={props.ariaLabel}
    >
      {props.variant === "termcard" ? (
        <span class="termcard-arrow" aria-hidden="true" />
      ) : (
        <>
          <span class="refcard-arrow-stem" aria-hidden="true" />
          <span class="refcard-arrow-fill" aria-hidden="true" />
        </>
      )}
      {props.children}
    </div>
  );
}
