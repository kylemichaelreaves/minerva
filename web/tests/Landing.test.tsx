import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@solidjs/testing-library";
import type { JSX } from "solid-js";
import Landing from "~/features/Landing";

function renderLanding(opts: { scopeChip?: JSX.Element } = {}) {
  const onSubmit = vi.fn();
  const onOpenRead = vi.fn();
  const onOpenRefs = vi.fn();
  const onOpenNetwork = vi.fn();
  const onOpenConcordance = vi.fn();
  const utils = render(() => (
    <Landing
      onSubmit={onSubmit}
      onOpenRead={onOpenRead}
      onOpenRefs={onOpenRefs}
      onOpenNetwork={onOpenNetwork}
      onOpenConcordance={onOpenConcordance}
      scopeChip={opts.scopeChip}
    />
  ));
  return {
    onSubmit,
    onOpenRead,
    onOpenRefs,
    onOpenNetwork,
    onOpenConcordance,
    ...utils,
  };
}

describe("<Landing />", () => {
  it("renders the monogram and the composer", () => {
    renderLanding();
    expect(screen.getByAltText("Minerva")).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText(/what would you like to consider/i),
    ).toBeInTheDocument();
  });

  it("offers no starter prompts (#258)", () => {
    // Replaces an assertion on `.landing-starters`, a selector no component
    // has ever rendered — it lived only in landing.css and in that test, so it
    // passed unconditionally while four pills sat on the page under
    // `.landing-pills`. The four are gone; these are the classes that existed.
    const { container } = renderLanding();
    expect(container.querySelector(".landing-pills")).toBeNull();
    expect(container.querySelector(".landing-pill")).toBeNull();
  });

  it("does not tell a mobile user to tap a prompt (#258)", () => {
    // The mobile hint read "tap a prompt · or type" and would have outlived
    // the prompts it referred to — an instruction pointing at nothing, on the
    // one viewport where the pills were the primary affordance.
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query.includes("max-width: 768px"),
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }));

    const { container } = renderLanding();
    const hint = container.querySelector(".landing-mobile-hint");

    expect(hint).not.toBeNull();
    expect(hint?.textContent).not.toMatch(/prompt/i);
  });

  it("names none of the removed prompts", () => {
    // The shapes #258 is about: un-anchored thematic questions, which the
    // retrieval contract is least able to answer well.
    renderLanding();
    for (const gone of ["Ethics", "Ontology", "Method", "Reception"]) {
      expect(screen.queryByText(gone)).toBeNull();
    }
  });

  it("Enter on the textarea calls onSubmit with trimmed value", () => {
    const { onSubmit } = renderLanding();
    const ta = screen.getByPlaceholderText(/what would you like to consider/i);
    fireEvent.input(ta, { target: { value: "  on the good  " } });
    fireEvent.keyDown(ta, { key: "Enter" });
    expect(onSubmit).toHaveBeenCalledWith("on the good");
  });

  it("Shift+Enter is a newline, not a submit", () => {
    const { onSubmit } = renderLanding();
    const ta = screen.getByPlaceholderText(/what would you like to consider/i);
    fireEvent.input(ta, { target: { value: "partial" } });
    fireEvent.keyDown(ta, { key: "Enter", shiftKey: true });
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("Begin button is disabled until the user types", () => {
    renderLanding();
    const btn = screen.getByRole("button", { name: /begin/i });
    expect(btn.classList.contains("disabled")).toBe(true);
    fireEvent.input(screen.getByPlaceholderText(/what would you like/i), {
      target: { value: "x" },
    });
    expect(btn.classList.contains("disabled")).toBe(false);
  });
  describe("the work-scope chip (#350)", () => {
    // Leaving the Reader for the landing used to drop the work: the back
    // arrow could hand it to a conversation, the landing had nowhere to
    // render the chip, and `startFromLanding` cleared the scope on submit.
    // The chip is optional so the cold landing — app start, "New question" —
    // stays the unscoped global entry point it was designed as.
    it("renders a scope chip when one is passed", () => {
      renderLanding({
        scopeChip: <div data-testid="scope-chip">Das Kapital, Band I</div>,
      });
      expect(screen.getByTestId("scope-chip")).toBeInTheDocument();
    });

    it("renders no chip when none is passed", () => {
      renderLanding();
      expect(screen.queryByTestId("scope-chip")).toBeNull();
    });

    it("puts the chip above the input, not below it", () => {
      // `ComposeField` renders `scopeChip` inside the sticky wrap above the
      // box. Asserted by document order so a CSS-only reflow cannot make
      // this pass while the chip reads as belonging to the mode row.
      const { container } = renderLanding({
        scopeChip: <div data-testid="scope-chip">Das Kapital, Band I</div>,
      });
      const chip = screen.getByTestId("scope-chip");
      const input = container.querySelector(".landing-input");
      expect(input).not.toBeNull();
      expect(chip.compareDocumentPosition(input!)).toBe(
        Node.DOCUMENT_POSITION_FOLLOWING,
      );
    });

    it("still submits normally with a chip present", () => {
      const { onSubmit } = renderLanding({
        scopeChip: <div data-testid="scope-chip">Das Kapital, Band I</div>,
      });
      const ta = screen.getByPlaceholderText(/what would you like/i);
      fireEvent.input(ta, { target: { value: "what is the commodity form?" } });
      fireEvent.keyDown(ta, { key: "Enter" });
      expect(onSubmit).toHaveBeenCalledWith("what is the commodity form?");
    });
  });
  // The monogram reveals a tooltip on hover and on keyboard focus
  // (`.landing-monogram:focus-visible + .landing-monogram-tooltip`, in
  // landing.css). It carried `tabindex="0"` on a plain `<div>` with no role
  // and no name, so tabbing onto it announced nothing and the `role="tooltip"`
  // element beside it was orphaned — nothing referenced it. Sonar flagged the
  // tab stop as typescript:S6845; these pin the behaviour, not the markup.
  it("names the monogram tooltip trigger for assistive tech", () => {
    renderLanding();
    expect(screen.getByRole("button", { name: "Minerva" })).toHaveClass(
      "landing-monogram",
    );
  });

  it("points the monogram at the tooltip it reveals", () => {
    const { container } = renderLanding();
    const trigger = screen.getByRole("button", { name: "Minerva" });
    const describedBy = trigger.getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();
    expect(container.querySelector(`#${describedBy}`)).toHaveClass(
      "landing-monogram-tooltip",
    );
  });

  it("keeps the monogram in the tab order", () => {
    const { container } = renderLanding();
    const trigger = container.querySelector<HTMLElement>(".landing-monogram")!;
    trigger.focus();
    expect(document.activeElement).toBe(trigger);
  });
  // Characterization, not a fix: JSX collapses the newline between the two
  // `.kbd` spans, which is what Sonar flags as ambiguous (typescript:S6772).
  // Making the spacing explicit must not move a pixel, so this pins the exact
  // rendered string — including the two non-breaking spaces — across that edit.
  it("renders the desktop key hint with its exact spacing", () => {
    // Set explicitly rather than inherited: the mobile test above assigns
    // `window.matchMedia` with no restore, so every test declared after it
    // runs in mobile mode by default. Filed separately; this test states the
    // viewport it means instead of depending on declaration order.
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }));
    const { container } = renderLanding();
    const kbds = Array.from(container.querySelectorAll(".kbd"));
    expect(kbds.map((k) => k.textContent)).toEqual(["\u21b5", "\u21e7 \u21b5"]);
    expect(kbds[0]?.parentElement?.textContent).toBe(
      "\u21b5 begin\u00a0\u00a0\u21e7 \u21b5 new line",
    );
  });
});
