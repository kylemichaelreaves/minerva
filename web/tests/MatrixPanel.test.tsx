import { fireEvent, render, screen } from "@solidjs/testing-library";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MatrixPanel } from "~/Network/components/MatrixPanel";
import type { MatrixCell, NetworkAuthor } from "~/api/networkApi";

const authors: NetworkAuthor[] = [
  { name: "Plato", short: "Plato", ord: 400, corpus: "class" },
  { name: "Vulgate", short: "Vulgate", ord: 520, corpus: "scrip" },
  { name: "Augustine", short: "Augustine", ord: 600, corpus: "med" },
  { name: "Aquinas", short: "Aquinas", ord: 700, corpus: "med" },
  { name: "Boulainvilliers", short: "Boulainvill…", ord: 845, corpus: "em" },
];
const cells: MatrixCell[] = [
  { r: 3, c: 2, n: 600 },
  { r: 3, c: 1, n: 300 },
  { r: 3, c: 0, n: 100 },
  { r: 2, c: 1, n: 100 },
];

function setup() {
  const onOpenPair = vi.fn();
  const view = render(() => (
    <MatrixPanel authors={authors} cells={cells} onOpenPair={onOpenPair} />
  ));
  // Cells render in `cells` order.
  const cell = (i: number): SVGRectElement => {
    const r = view.container.querySelectorAll<SVGRectElement>("rect.net-cell")[i];
    if (!r) throw new Error(`no cell ${i}`);
    return r;
  };
  return { ...view, onOpenPair, cell };
}

describe("<MatrixPanel />", () => {
  // happy-dom has no layout; give the SVG wrap the size of a real panel.
  beforeEach(() => {
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(720);
    vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(460);
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("omits authors who neither cite nor are cited", () => {
    const { container } = setup();
    expect(container.textContent).not.toContain("Boulainvill");
    expect(screen.getAllByText("Augustine").length).toBe(2); // row + column
    expect(screen.getAllByText("Aquinas").length).toBe(1); // cites, never cited
    expect(screen.getAllByText("Plato").length).toBe(1); // cited, never cites
  });

  it("divides each axis between corpus bands", () => {
    const { container } = setup();
    // Rows: med only → no divider. Cols: class | scrip | med → two.
    expect(container.querySelectorAll(".net-matrix-bands line").length).toBe(2);
    expect(container.textContent).toContain("SCRIPTURE");
    expect(container.textContent).toContain("MEDIEVAL");
  });

  it("switches the legend and cell colours with the mode", () => {
    const { container, cell } = setup();
    const aquinasVulgate = () => cell(1);
    expect(aquinasVulgate().getAttribute("fill")).toBe("var(--net-step-3)");
    expect(container.textContent).toContain("5k+");

    fireEvent.click(screen.getByRole("button", { name: "% of col" }));
    expect(screen.getByRole("button", { name: "% of col" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
    // 300 of the Vulgate's 400 incoming citations: 75% → top step.
    expect(aquinasVulgate().getAttribute("fill")).toBe("var(--net-step-5)");
    expect(container.textContent).toContain("who draws on this source?");

    fireEvent.click(screen.getByRole("button", { name: "% of row" }));
    // 300 of Aquinas's 1,000: 30% → step 4.
    expect(aquinasVulgate().getAttribute("fill")).toBe("var(--net-step-4)");
  });

  it("shows shares on hover and highlights the pair's labels", () => {
    const { container, cell } = setup();
    fireEvent.mouseEnter(cell(1));
    const tip = container.querySelector(".net-tooltip");
    expect(tip?.textContent).toContain("300 xrefs");
    expect(tip?.textContent).toContain("30.0% of Aquinas’s citations");
    expect(tip?.textContent).toContain("75.0% of citations to Vulgate");
    expect(container.querySelector(".net-matrix-crosshair")).toBeTruthy();
    const bold = [...container.querySelectorAll("text[font-weight='600']")].map(
      (t) => t.textContent,
    );
    expect(bold.sort()).toEqual(["Aquinas", "Vulgate"]);

    fireEvent.mouseLeave(cell(1));
    expect(container.querySelector(".net-tooltip")).toBeNull();
  });

  it("puts the tooltip right of a cell, flipping left near the right edge", () => {
    const { container, cell } = setup();
    const tipLeft = () =>
      Number.parseFloat(container.querySelector<HTMLElement>(".net-tooltip")?.style.left ?? "");
    const rectX = (r: SVGRectElement) => Number(r.getAttribute("x"));

    const toLastCol = cell(0); // Aquinas → Augustine
    const toFirstCol = cell(2); // Aquinas → Plato
    fireEvent.mouseEnter(toFirstCol);
    expect(tipLeft()).toBeGreaterThan(rectX(toFirstCol));
    fireEvent.mouseLeave(toFirstCol);

    fireEvent.mouseEnter(toLastCol);
    expect(tipLeft() + 240).toBeLessThan(rectX(toLastCol));
  });

  it("opens the pair on click", () => {
    const { onOpenPair, cell } = setup();
    fireEvent.click(cell(1));
    expect(onOpenPair).toHaveBeenCalledWith("Aquinas", "Vulgate");
  });
});
