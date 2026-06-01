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
    // Stop the document-level outside-click handler (registered while
    // a ReferenceCard is open) from clearing the parent's selection
    // on the very gesture that opens the card.
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
