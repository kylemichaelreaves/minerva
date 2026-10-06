import { fireEvent, render, screen } from "@solidjs/testing-library";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ArcPanel } from "~/Network/components/ArcPanel";
import type { AuthorPair, MatrixCell, NetworkAuthor } from "~/api/networkApi";

// Names chosen from ATLAS_AUTHORS so they carry real years; Pythagoras
// is not on the atlas and gets an interpolated one.
const authors: NetworkAuthor[] = [
  { name: "Homer", short: "Homer", ord: 100, corpus: "class" },
  { name: "Pythagoras", short: "Pythagoras", ord: 230, corpus: "class" },
  { name: "Plato", short: "Plato", ord: 400, corpus: "class" },
  { name: "Vulgate", short: "Vulgate", ord: 520, corpus: "scrip" },
  { name: "Sacy", short: "Sacy", ord: 750, corpus: "scrip" },
  { name: "Nietzsche", short: "Nietzsche", ord: 935, corpus: "mod" },
];
const cells: MatrixCell[] = [
  { r: 2, c: 0, n: 77 }, // Plato → Homer
  { r: 5, c: 2, n: 222 }, // Nietzsche → Plato
  { r: 5, c: 1, n: 3 }, // Nietzsche → Pythagoras
  { r: 4, c: 3, n: 40 }, // Sacy → Vulgate (intra-scripture)
];
const pair = (src: string, tgt: string, n: number, intra_scrip = false): AuthorPair => ({
  src,
  tgt,
  n,
  intra_scrip,
});
const nonScrip = [pair("Nietzsche", "Plato", 222), pair("Plato", "Homer", 77)];

function setup() {
  const onOpenPair = vi.fn();
  const view = render(() => (
    <ArcPanel
      authors={authors}
      matrixCells={cells}
      topPairsAll={[pair("Nietzsche", "Plato", 222), pair("Sacy", "Vulgate", 40, true)]}
      topPairsNonScrip={nonScrip}
      topPairsPerAuthor={[pair("Nietzsche", "Pythagoras", 3)]}
      onOpenPair={onOpenPair}
    />
  ));
  const label = (name: string) => screen.getByRole("button", { name: `${name}: show citations` });
  const detail = () => view.container.querySelector(".net-arc-detail")?.textContent ?? "";
  const arcs = () => [...view.container.querySelectorAll<SVGPathElement>("path.net-arc")];
  return { ...view, onOpenPair, label, detail, arcs };
}

describe("<ArcPanel />", () => {
  beforeEach(() => {
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(640);
    vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(320);
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("rests on the top pairs, with intra-scripture pairs hidden", () => {
    const { detail, arcs } = setup();
    expect(screen.getByText("Chronological arc diagram")).toBeTruthy();
    expect(detail()).toContain("Top pairs — intra-scripture hidden");
    expect(detail()).toContain("Nietzsche → Plato");
    expect(arcs()).toHaveLength(3); // two volume pairs + Nietzsche's per-author top
  });

  it("shows intra-scripture pairs when the toggle is off", () => {
    const { detail, arcs } = setup();
    fireEvent.click(screen.getByRole("button", { name: /Hide intra-scripture/ }));
    expect(detail()).not.toContain("intra-scripture hidden");
    const fills = arcs().map((a) => a.getAttribute("fill"));
    expect(fills).toContain("var(--net-terra)");
  });

  it("orders labels by year and draws era brackets", () => {
    const { container } = setup();
    const names = [...container.querySelectorAll(".net-arc-label text")].map((t) => t.textContent);
    expect(names).toEqual(["Homer", "Pythagoras", "Plato", "Vulgate", "Sacy", "Nietzsche"]);
    // Archaic, Classical, Late Antiquity, Early Modern, Modern: 3 lines each.
    expect(container.querySelectorAll(".net-arc-eras line")).toHaveLength(15);
    expect(container.querySelector(".net-arc-eras")?.textContent).toContain("ARCHAIC");
    expect(container.querySelectorAll(".net-arc-break").length).toBeGreaterThan(0);
  });

  it("focuses an author on click: direction colours, lists, and a clear button", () => {
    const { label, detail, arcs, container } = setup();
    fireEvent.click(label("Plato"));
    expect(label("Plato").getAttribute("aria-pressed")).toBe("true");
    expect(detail()).toContain("Plato · 380 BC · reaches back furthest to Homer (420 yrs)");
    expect(detail()).toContain("Cites");
    expect(detail()).toContain("Cited by");
    expect(detail()).toContain("Nietzsche1880 CE");
    const fills = arcs().map((a) => a.getAttribute("fill"));
    expect(fills.sort()).toEqual(["var(--net-arc-in)", "var(--net-arc-out)"]);
    expect(container.querySelector(".net-arc-legend")?.textContent).toContain("cites Plato");

    fireEvent.click(screen.getByRole("button", { name: "Clear ✕" }));
    expect(detail()).toContain("Top pairs");
  });

  it("shows every pair of the focused author, not only the top-N ones", () => {
    const { label, detail } = setup();
    fireEvent.click(label("Nietzsche"));
    expect(detail()).toContain("Pythagoras");
    // Pythagoras's year is interpolated, so it is not shown…
    expect(detail()).not.toMatch(/Pythagoras\d+ (BC|CE)/);
    // …and cannot be the furthest dated reach.
    expect(detail()).toContain("reaches back furthest to Plato");
    expect(detail()).toContain("None in corpus.");
  });

  it("previews on hover without pinning", () => {
    const { label, detail } = setup();
    fireEvent.mouseEnter(label("Homer"));
    expect(detail()).toContain("Homer · 800 BC");
    expect(screen.queryByRole("button", { name: "Clear ✕" })).toBeNull();
    fireEvent.mouseLeave(label("Homer"));
    expect(detail()).toContain("Top pairs");
  });

  it("toggles focus from the keyboard", () => {
    const { label, detail } = setup();
    fireEvent.keyDown(label("Plato"), { key: "Enter" });
    expect(detail()).toContain("Plato · 380 BC");
    fireEvent.keyDown(label("Plato"), { key: "Tab" });
    expect(detail()).toContain("Plato · 380 BC");
    fireEvent.keyDown(label("Plato"), { key: " " });
    expect(detail()).toContain("Top pairs");
  });

  it("refocuses from a row in the detail strip", () => {
    const { detail, container } = setup();
    const row = [...container.querySelectorAll<HTMLButtonElement>(".net-arc-detail .li")].find(
      (b) => b.textContent.startsWith("Plato → Homer"),
    );
    if (!row) throw new Error("no Plato → Homer row");
    fireEvent.click(row);
    expect(detail()).toContain("Plato · 380 BC");
    const homer = [...container.querySelectorAll<HTMLButtonElement>(".net-arc-detail .li")].find(
      (b) => b.textContent.startsWith("Homer"),
    );
    if (!homer) throw new Error("no Homer row");
    fireEvent.click(homer);
    expect(detail()).toContain("Homer · 800 BC");
  });

  it("shows a tooltip on arc hover and opens the pair on click", () => {
    const { arcs, container, onOpenPair } = setup();
    const heaviest = arcs().at(-1);
    if (!heaviest) throw new Error("no arcs");
    fireEvent.mouseMove(heaviest, { clientX: 600, clientY: 200 });
    const tip = container.querySelector<HTMLElement>(".net-tooltip");
    expect(tip?.textContent).toContain("222 references");
    expect(tip?.textContent).toContain("reaches back 2,260 years · 380 BC");
    expect(Number.parseFloat(tip?.style.left ?? "")).toBeLessThan(600); // flipped left
    expect(heaviest.getAttribute("fill-opacity")).toBe("1");

    fireEvent.click(heaviest);
    expect(onOpenPair).toHaveBeenCalledWith("Nietzsche", "Plato");
    fireEvent.mouseLeave(heaviest);
    expect(container.querySelector(".net-tooltip")).toBeNull();
  });

  it("omits the reach line when an end of the pair is undated", () => {
    const { arcs, container } = setup();
    const lightest = arcs()[0]; // Nietzsche → Pythagoras, n=3
    if (!lightest) throw new Error("no arcs");
    fireEvent.mouseMove(lightest, { clientX: 10, clientY: 200 });
    const tip = container.querySelector<HTMLElement>(".net-tooltip");
    expect(tip?.textContent).toContain("3 references");
    expect(tip?.textContent).not.toContain("reaches back");
    expect(Number.parseFloat(tip?.style.left ?? "")).toBe(24);
  });

  it("says '1 reference', not '1 references' (#728)", () => {
    const one = [pair("Plato", "Homer", 1)];
    const { container } = render(() => (
      <ArcPanel
        authors={authors}
        matrixCells={cells}
        topPairsAll={one}
        topPairsNonScrip={one}
        topPairsPerAuthor={[]}
        onOpenPair={vi.fn()}
      />
    ));
    const arc = container.querySelector<SVGPathElement>("path.net-arc");
    if (!arc) throw new Error("no arc");
    fireEvent.mouseMove(arc, { clientX: 10, clientY: 200 });
    const count = container.querySelector(".net-tooltip .count")?.textContent;
    expect(count).toBe("1 reference");
  });
});
