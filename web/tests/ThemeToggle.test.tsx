/**
 * ThemeToggle must render the shared Icons.tsx glyphs (#200, item 1).
 *
 * `Icons.tsx` exported `SunIcon` / `MoonIcon` whose only consumer was
 * `Icons.stories.tsx`, while `ThemeToggle` hand-rolled its own copies —
 * two sources of truth for the same glyph, one of them dead outside
 * Storybook.
 *
 * These tests compare the toggle's rendered SVG against the exported
 * component's, so they fail on a divergence rather than on a refactor:
 * anyone re-inlining a copy has to make it byte-identical to the shared
 * one, at which point they may as well import it.
 */
import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@solidjs/testing-library";
import { ThemeToggle } from "~/components/shell/ThemeToggle";
import { SunIcon, MoonIcon } from "~/components/primitives/Icons";

afterEach(cleanup);

function svgOf(container: HTMLElement): SVGSVGElement {
  const svg = container.querySelector("svg");
  if (!svg) throw new Error("no <svg> rendered");
  return svg;
}

/** The toggle needs an onToggle; most tests never fire it. */
function noop() {
  /* no-op: click behaviour has its own test */
}

function renderIconMarkup(Icon: typeof SunIcon): string {
  const { container } = render(() => <Icon />);
  return svgOf(container).innerHTML;
}

describe("ThemeToggle variant=icon", () => {
  it("renders the shared SunIcon when the theme is light", () => {
    const expected = renderIconMarkup(SunIcon);
    cleanup();

    const { container } = render(() => (
      <ThemeToggle theme="light" onToggle={noop} variant="icon" />
    ));

    expect(svgOf(container).innerHTML).toBe(expected);
  });

  it("renders the shared MoonIcon when the theme is dark", () => {
    const expected = renderIconMarkup(MoonIcon);
    cleanup();

    const { container } = render(() => (
      <ThemeToggle theme="dark" onToggle={noop} variant="icon" />
    ));

    expect(svgOf(container).innerHTML).toBe(expected);
  });

  it("keeps the accessible label describing the theme it switches TO", () => {
    render(() => <ThemeToggle theme="light" onToggle={noop} variant="icon" />);
    expect(screen.getByLabelText("Switch to dark theme")).toBeTruthy();
  });

  it("marks the glyph aria-hidden so the button's own label is what is read", () => {
    const { container } = render(() => (
      <ThemeToggle theme="light" onToggle={noop} variant="icon" />
    ));
    expect(svgOf(container).getAttribute("aria-hidden")).toBe("true");
  });

  it("fires onToggle when clicked", () => {
    let clicks = 0;
    render(() => (
      <ThemeToggle theme="light" onToggle={() => clicks++} variant="icon" />
    ));
    screen.getByRole("button").click();
    expect(clicks).toBe(1);
  });

  it("keeps the ico-btn class the reader stylesheet sizes the glyph through", () => {
    // `.reader .ico-btn svg { width: 14px; fill: none; stroke: currentColor }`
    // is the only rule that gives the glyph a size, so losing the class
    // would render an unsized SVG rather than an obviously-broken one.
    render(() => <ThemeToggle theme="light" onToggle={noop} variant="icon" />);
    expect(screen.getByRole("button").className).toBe("ico-btn");
  });
});

describe("ThemeToggle other variants", () => {
  it("variant=text keeps its CSS-drawn sun/moon spans, not the SVG icons", () => {
    // The landing toggle draws its glyph in CSS (`.sun` / `.moon`) beside
    // a text label; it is a different design, deliberately not unified.
    const { container } = render(() => (
      <ThemeToggle theme="light" onToggle={noop} variant="text" />
    ));
    expect(container.querySelector("span.sun")).toBeTruthy();
    expect(container.querySelector("svg")).toBeNull();
  });

  // Characterization, not a fix — the same shape as Landing's key-hint test
  // (PR #473). JSX collapses the newline between `<span class="sun" />` and
  // the `&nbsp;light` text node, which is what Sonar flags as ambiguous
  // spacing (typescript:S6772, twice). Making the spacing explicit must not
  // move a pixel, so this pins the exact rendered string — including the
  // non-breaking space — across that edit.
  it("renders variant=text with its exact spacing", () => {
    render(() => <ThemeToggle theme="light" onToggle={noop} variant="text" />);
    expect(screen.getByRole("button").textContent).toBe("\u00a0light");
  });

  it("renders the dark variant=text label with its exact spacing", () => {
    render(() => <ThemeToggle theme="dark" onToggle={noop} variant="text" />);
    expect(screen.getByRole("button").textContent).toBe("\u00a0dark");
  });

  it("variant=cog renders the gear character", () => {
    render(() => <ThemeToggle theme="dark" onToggle={noop} variant="cog" />);
    expect(screen.getByRole("button").textContent).toContain("⚙");
  });
});
