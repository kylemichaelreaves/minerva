import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@solidjs/testing-library";
import Landing from "~/Landing";

function renderLanding() {
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
});
