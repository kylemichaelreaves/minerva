import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent } from "@solidjs/testing-library";
import { createSignal, type JSX } from "solid-js";
import Landing from "~/features/Landing";
import { must } from "./helpers/must";
import type { Phase } from "~/features/LandingTransition/controller";
import type { ReturnPhase } from "~/features/LandingTransition/returnController";

function renderLanding(opts: { scopeChip?: JSX.Element; leaving?: Phase } = {}) {
  const onSubmit = vi.fn();
  const onOpenRead = vi.fn();
  const onOpenRefs = vi.fn();
  const onOpenNetwork = vi.fn();
  const onOpenConcordance = vi.fn();
  const onOpenMetrics = vi.fn();
  const utils = render(() => (
    <Landing
      onSubmit={onSubmit}
      onOpenRead={onOpenRead}
      onOpenRefs={onOpenRefs}
      onOpenNetwork={onOpenNetwork}
      onOpenConcordance={onOpenConcordance}
      onOpenMetrics={onOpenMetrics}
      scopeChip={opts.scopeChip}
      leaving={opts.leaving}
    />
  ));
  return {
    onSubmit,
    onOpenRead,
    onOpenRefs,
    onOpenNetwork,
    onOpenConcordance,
    onOpenMetrics,
    ...utils,
  };
}

describe("<Landing />", () => {
  // `web/tests/setup.ts` installs a desktop `window.matchMedia`
  // (`matches: false`). One test below replaces it to assert the mobile
  // branch, by direct assignment rather than `vi.stubGlobal` — so nothing
  // undoes it, and every test declared after that one used to render in
  // mobile mode without saying so (#476). Restore the shim after each test so
  // the file stops depending on declaration order.
  // `.bind` rather than a bare reference: @typescript-eslint/unbound-method
  // flags capturing a method off its object, and the restore works the same.
  const desktopMatchMedia = window.matchMedia.bind(window);
  afterEach(() => {
    window.matchMedia = desktopMatchMedia;
  });

  it("renders the monogram and the composer", () => {
    renderLanding();
    expect(screen.getByAltText("Minerva")).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/what would you like to consider/i)).toBeInTheDocument();
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

    it("puts the scope pill in the footer, after the input", () => {
      // Asserted by document order and ancestry so a CSS-only reflow cannot
      // make this pass while the pill sits outside the footer.
      const { container } = renderLanding({
        scopeChip: <div data-testid="scope-chip">Das Kapital, Band I</div>,
      });
      const chip = screen.getByTestId("scope-chip");
      const input = container.querySelector(".landing-input");
      expect(input).not.toBeNull();
      expect(input?.compareDocumentPosition(chip)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
      expect(chip.closest(".compose-foot__left")).not.toBeNull();
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
    expect(screen.getByRole("button", { name: "Minerva" })).toHaveClass("landing-monogram");
  });

  it("points the monogram at the tooltip it reveals", () => {
    const { container } = renderLanding();
    const trigger = screen.getByRole("button", { name: "Minerva" });
    const describedBy = trigger.getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();
    expect(container.querySelector(`#${describedBy}`)).toHaveClass("landing-monogram-tooltip");
  });

  it("keeps the monogram in the tab order", () => {
    const { container } = renderLanding();
    const trigger = must(container.querySelector<HTMLElement>(".landing-monogram"));
    trigger.focus();
    expect(document.activeElement).toBe(trigger);
  });
  // Each key sits with its word in one wrapper, as the chat composer's hint
  // does: the footer's left side is a flex row with a 14px gap, so a bare
  // word between the `.kbd` spans became a flex item of its own and the gap
  // pushed it away from its key.
  it("renders the desktop key hint as key + word pairs", () => {
    // No viewport stub of its own: #476's `afterEach` restores the desktop
    // default after the mobile test above, so this inherits it. The explicit
    // stub PR #473 needed here is what that fix removes.
    const { container } = renderLanding();
    const kbds = Array.from(container.querySelectorAll(".kbd"));
    expect(kbds.map((k) => k.textContent)).toEqual(["\u21b5", "\u21e7 \u21b5"]);
    expect(kbds.map((k) => k.parentElement?.textContent)).toEqual([
      "\u21b5 begin",
      "\u21e7 \u21b5 new line",
    ]);
    const row = must(container.querySelector(".compose-foot__left"));
    const bare = Array.from(row.childNodes).filter(
      (n) => n.nodeType === Node.TEXT_NODE && n.textContent?.trim(),
    );
    expect(bare).toEqual([]);
    expect(kbds.every((k) => k.parentElement?.parentElement === row)).toBe(true);
  });

  it("opens the metrics surface from the landing page", () => {
    const { onOpenMetrics } = renderLanding();
    fireEvent.click(screen.getByRole("button", { name: /request timing/i }));
    expect(onOpenMetrics).toHaveBeenCalledTimes(1);
  });

  it("keeps the metrics entry out of the four-column modes grid", () => {
    // The grid is `repeat(4, 1fr)` and its CSS notes the width auto-scales
    // "so adding/removing a CTA doesn't force the 4th onto its own row".
    // A fifth cell is exactly the case that comment designs against, so the
    // metrics entry has to live outside the grid, not inside it.
    const { container } = renderLanding();
    const grid = container.querySelector(".landing-modes");
    expect(grid).not.toBeNull();
    expect(grid?.querySelectorAll(".landing-mode").length).toBe(4);
    expect(grid?.textContent).not.toMatch(/request timing/i);

    const aside = container.querySelector(".landing-modes-aside");
    expect(aside?.textContent).toMatch(/request timing/i);
  });

  describe("leaving for the chat", () => {
    const root = (c: HTMLElement) => must(c.querySelector(".landing"), ".landing");

    it("lifts out: is-leaving, and inert so nothing on it can be clicked or focused", () => {
      const { container } = renderLanding({ leaving: "lift" });
      expect(root(container)).toHaveClass("is-leaving");
      expect(root(container)).toHaveAttribute("inert");
      expect(root(container)).toHaveAttribute("aria-hidden", "true");
    });

    it("fades out under reduced motion", () => {
      const { container } = renderLanding({ leaving: "fade" });
      expect(root(container)).toHaveClass("is-fading");
      expect(root(container)).toHaveAttribute("inert");
    });

    it("comes back empty and focused when a flight is called off", () => {
      // "New conversation" mid-flight reuses this same Landing (it never
      // unmounted), and its composer keeps the sent text by design — without
      // a reset, Enter on the "fresh" landing would re-send the old question.
      const [leaving, setLeaving] = createSignal<Phase | undefined>(undefined);
      render(() => (
        <Landing
          onSubmit={vi.fn()}
          onOpenRead={vi.fn()}
          onOpenRefs={vi.fn()}
          onOpenNetwork={vi.fn()}
          onOpenConcordance={vi.fn()}
          onOpenMetrics={vi.fn()}
          leaving={leaving()}
        />
      ));
      const ta = screen.getByPlaceholderText<HTMLTextAreaElement>(
        /what would you like to consider/i,
      );
      fireEvent.input(ta, { target: { value: "What is Geist?" } });
      setLeaving("lift");
      ta.blur();
      setLeaving(undefined);

      expect(ta.value).toBe("");
      expect(document.activeElement).toBe(ta);
    });

    it("keeps its text and focus when a flight simply finishes", () => {
      const [leaving, setLeaving] = createSignal<Phase | undefined>("lift");
      render(() => (
        <Landing
          onSubmit={vi.fn()}
          onOpenRead={vi.fn()}
          onOpenRefs={vi.fn()}
          onOpenNetwork={vi.fn()}
          onOpenConcordance={vi.fn()}
          onOpenMetrics={vi.fn()}
          leaving={leaving()}
        />
      ));
      const ta = screen.getByPlaceholderText<HTMLTextAreaElement>(
        /what would you like to consider/i,
      );
      fireEvent.input(ta, { target: { value: "What is Geist?" } });
      ta.blur();
      setLeaving("idle");

      expect(ta.value).toBe("What is Geist?");
      expect(document.activeElement).not.toBe(ta);
    });

    it("is an ordinary, interactive landing otherwise", () => {
      for (const leaving of [undefined, "idle"] as const) {
        const { container, unmount } = renderLanding({ leaving });
        expect(root(container)).not.toHaveClass("is-leaving");
        expect(root(container)).not.toHaveClass("is-fading");
        expect(root(container)).not.toHaveAttribute("inert");
        expect(root(container)).not.toHaveAttribute("aria-hidden");
        unmount();
      }
    });
  });

  describe("arriving from the chat (Escape)", () => {
    const root = (c: HTMLElement) => must(c.querySelector(".landing"), ".landing");

    function renderArriving(initial: ReturnPhase | undefined) {
      const [arriving, setArriving] = createSignal<ReturnPhase | undefined>(initial);
      const utils = render(() => (
        <Landing
          onSubmit={vi.fn()}
          onOpenRead={vi.fn()}
          onOpenRefs={vi.fn()}
          onOpenNetwork={vi.fn()}
          onOpenConcordance={vi.fn()}
          onOpenMetrics={vi.fn()}
          arriving={arriving()}
        />
      ));
      return { ...utils, setArriving };
    }

    it("is an inert layer while it arrives, without the page-load fade", () => {
      const { container } = renderArriving("return");
      expect(root(container)).toHaveClass("is-arriving");
      expect(root(container)).not.toHaveClass("fade-in");
      expect(root(container)).toHaveAttribute("inert");
      expect(root(container)).toHaveAttribute("aria-hidden", "true");
    });

    it("fades in under reduced motion", () => {
      const { container } = renderArriving("fade");
      expect(root(container)).toHaveClass("is-arriving-fade");
      expect(root(container)).toHaveAttribute("inert");
    });

    it("takes focus once it has arrived, and never gets the fade back", async () => {
      const scrollTo = vi.spyOn(window, "scrollTo").mockImplementation(() => undefined);
      const { container, setArriving } = renderArriving("return");
      const ta = screen.getByPlaceholderText<HTMLTextAreaElement>(
        /what would you like to consider/i,
      );
      setArriving(undefined);
      await Promise.resolve();

      expect(document.activeElement).toBe(ta);
      expect(scrollTo).toHaveBeenCalledWith(0, 0);
      expect(root(container)).not.toHaveClass("fade-in");
      expect(root(container)).not.toHaveAttribute("inert");
    });

    it("a page-load landing keeps its fade", () => {
      const { container } = renderArriving(undefined);
      expect(root(container)).toHaveClass("fade-in");
      expect(root(container)).not.toHaveClass("is-arriving");
    });
  });
});
