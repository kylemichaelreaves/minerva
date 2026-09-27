import { type JSX, createSignal } from "solid-js";
import "~/components/primitives/popovercard.css";
import { POPOVER_CARD_WIDTH } from "~/utils/popoverPosition";
import { useClickOutside } from "~/hooks/useClickOutside";
import { useDialogFocus } from "~/hooks/useDialogFocus";
import { useEscape } from "~/hooks/useEscape";
import { usePopoverPosition } from "~/hooks/usePopoverPosition";
import { useSuspendedSubtree } from "~/hooks/suspendedSubtree";

export interface PopoverCardProps {
  anchor: DOMRect;
  /** CSS class prefix: `termcard` or `refcard`. */
  variant: "termcard" | "refcard";
  ariaLabel: string;
  /** Selector for the element this popover hangs off — `.term-mark` for the
   *  term card, `.xref-pin` for the reference card. A click on it is the
   *  gesture that opens or toggles the card, so the outside-click listener
   *  must not count it as outside: the mousedown half of the opening click
   *  would otherwise dismiss the card the click is about to open. Required
   *  rather than optional, so a new popover has to answer "what anchors me?"
   *  instead of silently inheriting a listener that fights its own opener. */
  anchorSelector: string;
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
  const { pos } = usePopoverPosition(
    () => props.anchor,
    () => ({
      heightEstimate: props.heightEstimate ?? 400,
      direction: props.direction ?? "ltr",
    }),
  );

  useEscape(() => {
    props.onClose();
  });
  useDialogFocus(cardRef, () => true);

  // Dismissal by clicking away, owned by the shell rather than the caller
  // (#356). It was wired per-caller until then, and only `useTermCard` ever
  // wired it — so `ReferenceCard`, whose header comment claimed the
  // affordance and whose `XrefMarker` claimed to defend against it, never had
  // it. Owning it here is what stops a third popover repeating that.
  //
  // The suspension gate is folded into `isActive` rather than read inside
  // `useClickOutside`, unlike `useEscape` and `useDialogFocus` which consult
  // the context themselves. `useClickOutside` is shared with
  // `components/Select.tsx`, which the concordance renders and which must stay
  // live while the Reader behind it is suspended, so the hook stays
  // context-free and `Select` stays provably unaffected (#352). The card is
  // only mounted while open, so "mounted and not suspended" is the whole
  // active condition.
  const suspended = useSuspendedSubtree();
  useClickOutside(
    cardRef,
    () => !suspended(),
    () => props.onClose(),
    {
      event: "mousedown",
      capture: true,
      ignore: (target) => (target as Element).closest(props.anchorSelector) != null,
    },
  );

  const width = () => props.width ?? POPOVER_CARD_WIDTH;
  const shellClass = () =>
    `${props.variant}${pos().flipUp ? " flip-up" : ""}${props.class ? ` ${props.class}` : ""}`;

  return (
    <div
      ref={setCardRef}
      class={shellClass()}
      style={{
        top: `${pos().top}px`,
        left: `${pos().left}px`,
        ...(props.variant === "termcard" ? { width: `${width()}px` } : {}),
      }}
      role="dialog"
      aria-modal="true"
      aria-label={props.ariaLabel}
    >
      {/* The dialog's only visible exit (#358). Escape and clicking away both
          work and neither is discoverable, and `useDialogFocus` traps Tab in
          here for as long as the card is open — which is why this belongs in
          the tab sequence rather than being left to each card. First child so
          it is the first focusable the trap lands on. */}
      <button
        type="button"
        class="popover-close"
        aria-label="Close"
        onClick={() => {
          props.onClose();
        }}
      >
        ×
      </button>
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
