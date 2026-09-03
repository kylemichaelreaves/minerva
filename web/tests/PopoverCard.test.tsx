// Dismissal contract of the shared popover shell (#356).
//
// `PopoverCard` is the shell behind both of the Reader's popovers, and before
// #356 it owned two of their three dismissal affordances — Escape and the
// focus trap — while the third, clicking away, was wired per-caller. Only
// `useTermCard` ever wired it, so `ReferenceCard` had no outside-click
// dismissal at all (`useClickOutside` had six consumers and the xref card's
// hook was not one of them). These tests pin the affordance to the shell so a
// third popover inherits it rather than repeating the omission.
//
// The tests render `PopoverCard` directly rather than through either card,
// because the point is that the *shell* answers the click — a card-level test
// cannot distinguish "the shell dismisses" from "this card wired its own".

import { render, fireEvent } from "@solidjs/testing-library";
import { describe, expect, it, vi } from "vitest";
import PopoverCard from "~/components/primitives/PopoverCard";
import { SuspendedSubtreeProvider } from "~/hooks/suspendedSubtree";

const ANCHOR = new DOMRect(100, 200, 20, 16);

/** Stand-in for the element a popover hangs off — `.term-mark` for the term
 *  card, `.xref-pin` for the reference card. Rendered as a sibling of the
 *  shell, which is where both live in the Reader: the marker is inside a
 *  `.line`, the card is a fixed-position child of the Reader root. */
function withAnchor(children: () => unknown) {
  return render(() => (
    <>
      <button class="test-anchor" type="button">
        anchor
      </button>
      {children() as never}
    </>
  ));
}

describe("PopoverCard dismissal", () => {
  it("calls onClose when a click lands outside the card", () => {
    const onClose = vi.fn();
    render(() => (
      <PopoverCard
        variant="refcard"
        anchor={ANCHOR}
        ariaLabel="Cross-reference details"
        anchorSelector=".test-anchor"
        onClose={onClose}
      >
        <div class="body">body</div>
      </PopoverCard>
    ));

    fireEvent.mouseDown(document.body);

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("leaves the card open when the click lands inside it", () => {
    const onClose = vi.fn();
    const { container } = render(() => (
      <PopoverCard
        variant="refcard"
        anchor={ANCHOR}
        ariaLabel="Cross-reference details"
        anchorSelector=".test-anchor"
        onClose={onClose}
      >
        <div class="body">body</div>
      </PopoverCard>
    ));

    fireEvent.mouseDown(container.querySelector(".body")!);

    expect(onClose).not.toHaveBeenCalled();
  });

  it("leaves the card open when the click lands on its own anchor", () => {
    // The gesture that opens a popover is a click on its anchor, which is
    // outside the card by every geometric measure. Without this the card
    // would close on the mousedown half of the click that opened it — and
    // the toggle-to-dismiss gesture both cards implement (a second click on
    // the same marker) would fire close() twice.
    //
    // `XrefMarker`'s own `e.stopPropagation()` cannot supply this: it is on a
    // bubble-phase `click`, and the listener here is a capture-phase
    // `mousedown` on `document`, which runs first.
    const onClose = vi.fn();
    const { container } = withAnchor(() => (
      <PopoverCard
        variant="refcard"
        anchor={ANCHOR}
        ariaLabel="Cross-reference details"
        anchorSelector=".test-anchor"
        onClose={onClose}
      >
        <div class="body">body</div>
      </PopoverCard>
    ));

    fireEvent.mouseDown(container.querySelector(".test-anchor")!);

    expect(onClose).not.toHaveBeenCalled();
  });

  it("dismisses the card from the close control", () => {
    // #358: both cards were `aria-modal="true"` with a real Tab trap
    // (`useDialogFocus`) and no visible way out. Escape and clicking away are
    // both undiscoverable, and the term card's only button rendered in the
    // load-error state. Owned by the shell for the same reason the
    // outside-click listener is (#356): per-caller is how the reference card
    // came to have neither.
    const onClose = vi.fn();
    const { container } = render(() => (
      <PopoverCard
        variant="refcard"
        anchor={ANCHOR}
        ariaLabel="Cross-reference details"
        anchorSelector=".test-anchor"
        onClose={onClose}
      >
        <div class="body">body</div>
      </PopoverCard>
    ));

    fireEvent.click(container.querySelector(".popover-close")!);

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("gives the close control an accessible name", () => {
    // A bare `×` glyph is unlabelled to a screen reader, and this control is
    // the dialog's only visible exit.
    const { container } = render(() => (
      <PopoverCard
        variant="termcard"
        anchor={ANCHOR}
        ariaLabel="Term details"
        anchorSelector=".test-anchor"
        onClose={() => undefined}
      >
        <div class="body">body</div>
      </PopoverCard>
    ));

    expect(
      container.querySelector(".popover-close")?.getAttribute("aria-label"),
    ).toBe("Close");
  });

  it("registers no outside-click listener while its subtree is suspended", () => {
    // #352's constraint, which is why the gate is folded into the `isActive`
    // accessor here rather than into `useClickOutside` itself: a Reader
    // retained behind the concordance must not treat a click on the
    // concordance as "outside the card" and destroy the state #348 keeps it
    // mounted to preserve. `useClickOutside` stays context-free so
    // `components/Select.tsx` — which the concordance renders — is provably
    // unaffected. See `hooks/suspendedSubtree.tsx:26-32`.
    const onClose = vi.fn();
    render(() => (
      <SuspendedSubtreeProvider suspended={() => true}>
        <PopoverCard
          variant="termcard"
          anchor={ANCHOR}
          ariaLabel="Term details"
          anchorSelector=".test-anchor"
          onClose={onClose}
        >
          <div class="body">body</div>
        </PopoverCard>
      </SuspendedSubtreeProvider>
    ));

    fireEvent.mouseDown(document.body);

    expect(onClose).not.toHaveBeenCalled();
  });
});
