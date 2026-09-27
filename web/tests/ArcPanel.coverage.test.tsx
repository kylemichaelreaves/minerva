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
  return [...container.querySelectorAll<SVGPathElement>('[data-panel="arc"] path.net-arc')];
}

/** Baseline tick x for each author, in axis order. */
function tickX(container: HTMLElement): Map<string, number> {
  const out = new Map<string, number>();
  for (const g of container.querySelectorAll(".net-arc-label")) {
    const name = g.querySelector("text")?.textContent ?? "";
    out.set(name, Number(g.querySelector("line")?.getAttribute("x1")));
  }
  return out;
}

/** The outline's vertices, as [x, y] pairs. */
function vertices(d: string): number[][] {
  return d
    .replace(/[MZ]/g, "")
    .split("L")
    .map((pt) => pt.split(",").map(Number));
}

describe("<ArcPanel /> geometry", () => {
  it("anchors each arc's endpoints at its authors' baseline x positions", () => {
    const { container, onOpenPair } = mount();
    const x = tickX(container);
    const arcs = arcPaths(container);
    expect(arcs).toHaveLength(1);
    const arc = must(arcs[0], "arc path");
    // The tapered outline runs out along one edge (citing → cited) and back
    // along the other: vertex 0 is at the citing end, vertex n/2 − 1 at the
    // cited end, both on the baseline (y = 112) within half a stroke.
    const pts = vertices(arc.getAttribute("d") ?? "");
    const citing = must(pts[0], "first vertex");
    const cited = must(pts[pts.length / 2 - 1], "cited-end vertex");
    expect(Math.abs((citing[0] ?? 0) - (x.get("Ar") ?? NaN))).toBeLessThan(1);
    expect(Math.abs((cited[0] ?? 0) - (x.get("Pl") ?? NaN))).toBeLessThan(4);
    expect(Math.abs((citing[1] ?? 0) - 112)).toBeLessThan(1);

    fireEvent.click(arc);
    expect(onOpenPair).toHaveBeenCalledWith("Aristotle", "Plato");
  });

  it("places an author with no known year between its neighbours and never shows a year for it", () => {
    const { container } = mount();
    const x = tickX(container);
    expect([...x.keys()]).toEqual(["Pl", "No", "Ar"]);
    const [pl, no, ar] = [x.get("Pl") ?? 0, x.get("No") ?? 0, x.get("Ar") ?? 0];
    expect(no).toBeGreaterThan(pl);
    expect(no).toBeLessThan(ar);

    fireEvent.mouseEnter(screen.getByRole("button", { name: "Nobody: show citations" }));
    const detail = container.querySelector(".net-arc-detail")?.textContent ?? "";
    expect(detail).toMatch(/^Nobody(?! ·)/);
    fireEvent.mouseEnter(screen.getByRole("button", { name: "Plato: show citations" }));
    expect(container.querySelector(".net-arc-detail")?.textContent).toContain("Plato · 380 BC");
  });
});
