// XrefMarker — the scholarly-footnote-style gutter glyph that signals
// "this passage references another author." Lives in the 24px right
// gutter of a `.line` row. Clicking it opens a ReferenceCard popover
// anchored to the marker's bounding rect.
//
// Visual states (.reader .xref-pin in reader.css):
//   • default — ink-faint
//   • :hover  — accent
//   • :focus-visible — accent + 1px outline ring at 2px offset
//   • .is-active — accent (persistent while ReferenceCard is open)
//
// No idle animation, no background fill, no border. The component
// owns no state — the parent (Lines.tsx) toggles `.is-active` via
// the `active` prop when the matching ReferenceCard is open.
//
// Faithful port of project/reference-card/ReferenceMarker.html.

import { Show, type JSX } from "solid-js";
import { xrefSuperscript } from "~/utils/xrefMarkerUtils";

export interface XrefMarkerProps {
  /** Total outgoing cross-references on this row. When omitted or 1,
   *  the bare `▸` glyph renders; counts ≥ 2 add a superscript number
   *  (`▸²`, `▸³`, …) styled by `.xref-count`. */
  count?: number;
  /** When true, marker stays in accent — the parent renders this
   *  while the matching ReferenceCard is open. Same color as hover. */
  active?: boolean;
  /** Click handler. Receives the marker's bounding rect so the
   *  caller can anchor the ReferenceCard popover against it. */
  onOpen: (anchor: DOMRect) => void;
}

export function XrefMarker(props: XrefMarkerProps): JSX.Element {
  const handleClick = (e: MouseEvent & { currentTarget: HTMLButtonElement }) => {
    // Keeps the opening click off any bubble-phase handler on the enclosing
    // `.line`.
    //
    // It does NOT protect the card from the outside-click listener, which is
    // what this comment claimed until #356 — twice over. That listener did
    // not exist at all for reference cards (the affordance is new in #356),
    // and the one `PopoverCard` now registers could not be reached from here
    // anyway: it is a capture-phase `mousedown` on `document`, so it runs
    // before this bubble-phase `click` and cannot be stopped from a
    // descendant. The protection comes from the shell's `anchorSelector`
    // ignore predicate, which this component supplies via the `.xref-pin`
    // class below.
    e.stopPropagation();
    props.onOpen(e.currentTarget.getBoundingClientRect());
  };

  return (
    <button
      type="button"
      class={props.active ? "xref-pin is-active" : "xref-pin"}
      aria-label={
        props.count && props.count > 1
          ? `${props.count} cross-references on this passage`
          : "Cross-reference on this passage"
      }
      onClick={handleClick}
    >
      ▸
      <Show when={props.count !== undefined && props.count > 1}>
        <span class="xref-count" aria-hidden="true">
          {xrefSuperscript(props.count!)}
        </span>
      </Show>
    </button>
  );
}
