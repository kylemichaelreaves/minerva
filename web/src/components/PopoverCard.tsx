import { type JSX } from "solid-js";
import { POPOVER_CARD_WIDTH } from "~/utils/popoverPosition";
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
}

export default function PopoverCard(props: PopoverCardProps) {
  const { pos } = usePopoverPosition(() => props.anchor, {
    heightEstimate: props.heightEstimate ?? 400,
  });

  useEscape(() => {
    props.onClose();
  });

  function onCardClick(e: MouseEvent) {
    e.stopPropagation();
  }

  const width = props.width ?? POPOVER_CARD_WIDTH;
  const shellClass = () =>
    `${props.variant}${pos().flipUp ? " flip-up" : ""}${props.class ? ` ${props.class}` : ""}`;

  return (
    <div
      class={shellClass()}
      style={{
        top: `${pos().top}px`,
        left: `${pos().left}px`,
        ...(props.variant === "termcard" ? { width: `${width}px` } : {}),
      }}
      onClick={onCardClick}
      role="dialog"
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
