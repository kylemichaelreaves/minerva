import { fireEvent, render, screen } from "@solidjs/testing-library";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AuthorPair, NetworkAuthor } from "~/api/networkApi";
import { ArcPanel } from "~/Network/components/ArcPanel";
import { must } from "./helpers/must";

// "Nobody" is a real matrix author with no entry in the atlas year table.
const authors: NetworkAuthor[] = [
  { name: "Plato", short: "Pl", ord: 100, corpus: "class" },
  { name: "Nobody", short: "No", ord: 150, corpus: "class" },
  { name: "Aristotle", short: "Ar", ord: 200, corpus: "class" },
];
const pairs: AuthorPair[] = [{ src: "Aristotle", tgt: "Plato", n: 40, intra_scrip: false }];

beforeEach(() => {
  // No layout under jsdom: give every element a 700×460 client box so the
  // arc geometry is computed against a real width.
  vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(700);
  vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(460);
});
afterEach(() => {
  vi.restoreAllMocks();
});

function mount(onOpenPair = vi.fn()) {
  const { container } = render(() => (
    <ArcPanel
      authors={authors}
      matrixCells={[]}
      topPairsAll={pairs}
      topPairsNonScrip={pairs}
      topPairsPerAuthor={[]}
      onOpenPair={onOpenPair}
    />
  ));
  return { container, onOpenPair };
}

function arcPaths(container: HTMLElement) {
  return [...container.querySelectorAll('[data-panel="arc"] path')].filter((p) =>
    (p.getAttribute("d") ?? "").includes(" Q "),
  );
}

describe("<ArcPanel /> geometry", () => {
  it("anchors each arc's endpoints at its authors' baseline x positions", () => {
    const { container, onOpenPair } = mount();
    // padL 24, padR 24, w 700, N 3 → x = 24 + 652·i/2 → 24, 350, 676.
    // baseY = padT = 32. One pair, so its half-span is arcMaxR and the
    // dip is the full maxDip (arcH 364 − 32 − 12 = 320) × 0.96.
    const arcs = arcPaths(container);
    expect(arcs).toHaveLength(1);
    const arc = must(arcs[0], "arc path");
    expect(arc.getAttribute("d")).toBe(`M 676 32 Q 350 ${32 + 320 * 0.96} 24 32`);

    fireEvent.click(arc);
    expect(onOpenPair).toHaveBeenCalledWith("Aristotle", "Plato");
  });

  it("labels a baseline year only for authors with a known year", () => {
    const { container } = mount();
    // Zoom to ≥2.6× so every author's label is shown, not just the sparse set.
    const zoomIn = screen.getByRole("button", { name: "Zoom in" });
    for (let i = 0; i < 3; i++) fireEvent.click(zoomIn);

    const shorts = [...container.querySelectorAll('text[font-size="9.5"][text-anchor="middle"]')];
    expect(shorts.map((t) => t.textContent)).toEqual(["Pl", "No", "Ar"]);

    const years = [...container.querySelectorAll('text[font-size="8.5"]')];
    expect(years.map((t) => t.textContent)).toEqual(["380 BC", "340 BC"]);
    // …and each sits at its own author's x, not at Nobody's.
    const xOf = (t: Element) => t.getAttribute("x");
    expect(years.map(xOf)).toEqual([
      xOf(must(shorts[0], "Pl label")),
      xOf(must(shorts[2], "Ar label")),
    ]);
  });
});
