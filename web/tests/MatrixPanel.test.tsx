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
  // Cells render in grid order (rows, then columns), so find one by the
  // pair it names — `i` indexes `cells`, the props order.
  const cell = (i: number): HTMLElement => {
    const c = cells[i];
    const name = `${authors[c?.r ?? -1]?.name} → ${authors[c?.c ?? -1]?.name}`;
    return screen.getByRole("gridcell", { name: new RegExp(`^${name}:`) });
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

  it("lines the crosshair and both axis labels up with the hovered cell (#728)", () => {
    // Pins positions across #728, which moved the crosshair and the labels
    // off `rowPos`/`colPos` lookups (each with an unreachable `?? 0`) and
    // onto the placed cell and the label's own index.
    const { container, cell } = setup();
    const target = cell(1); // Aquinas → Vulgate: row 1, column 1 (neither is 0)
    const n = (el: Element | null | undefined, a: string) => Number(el?.getAttribute(a));
    fireEvent.mouseEnter(target);

    const [rowBar, colBar] = container.querySelectorAll(".net-matrix-crosshair rect");
    expect(n(rowBar, "y")).toBe(n(target, "y") - 0.5);
    expect(n(colBar, "x")).toBe(n(target, "x") - 0.5);

    const label = (name: string, axis: "row" | "col") =>
      [...container.querySelectorAll("text")].find(
        (t) => t.textContent === name && (t.getAttribute("transform") !== null) === (axis === "col"),
      );
    const cellMidY = n(target, "y") - 0.5 + n(rowBar, "height") / 2;
    const cellMidX = n(target, "x") - 0.5 + n(colBar, "width") / 2;
    expect(n(label("Aquinas", "row"), "y")).toBeCloseTo(cellMidY + 3.5);
    expect(n(label("Vulgate", "col"), "x")).toBeCloseTo(cellMidX + 3.5);
  });

  it("puts the tooltip right of a cell, flipping left near the right edge", () => {
    const { container, cell } = setup();
    const tipLeft = () =>
      Number.parseFloat(container.querySelector<HTMLElement>(".net-tooltip")?.style.left ?? "");
    const rectX = (r: Element) => Number(r.getAttribute("x"));

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

  // #696: the cells were mouse-only — plain <rect>s with an onClick and no
  // tabindex, so the drill-down and the share tooltip were unreachable by
  // keyboard, and the `.net-cell:focus` rule could never match.
  describe("keyboard grid", () => {
    // Grid for these fixtures (rows Augustine, Aquinas; cols Plato,
    // Vulgate, Augustine):
    //   Augustine:   .       Vulgate  .
    //   Aquinas:     Plato   Vulgate  Augustine
    const tabbable = (container: HTMLElement) =>
      [...container.querySelectorAll('[role="gridcell"]')].filter(
        (el) => el.getAttribute("tabindex") === "0",
      );

    it("is a labelled grid with exactly one cell in the tab order", () => {
      const { container, cell } = setup();
      const grid = screen.getByRole("grid");
      expect(grid.getAttribute("aria-label")).toMatch(/citation matrix/i);
      expect(grid.getAttribute("aria-rowcount")).toBe("2");
      expect(grid.getAttribute("aria-colcount")).toBe("3");
      expect(screen.getAllByRole("row").map((r) => r.getAttribute("aria-rowindex"))).toEqual([
        "1",
        "2",
      ]);
      expect(screen.getAllByRole("gridcell")).toHaveLength(4);
      // The top-left cell holds the tab stop; every other cell is -1.
      expect(tabbable(container)).toEqual([cell(3)]);
      expect(cell(3).getAttribute("aria-colindex")).toBe("2");
      expect(cell(0).getAttribute("tabindex")).toBe("-1");
    });

    it("moves focus with the arrow keys and carries the tab stop along", () => {
      const { container, cell } = setup();
      cell(3).focus(); // Augustine → Vulgate
      fireEvent.keyDown(cell(3), { key: "ArrowDown" });
      expect(document.activeElement).toBe(cell(1)); // Aquinas → Vulgate
      fireEvent.keyDown(cell(1), { key: "ArrowLeft" });
      expect(document.activeElement).toBe(cell(2)); // Aquinas → Plato
      fireEvent.keyDown(cell(2), { key: "End" });
      expect(document.activeElement).toBe(cell(0)); // Aquinas → Augustine
      expect(tabbable(container)).toEqual([cell(0)]);
    });

    it("keeps focus in place at an edge, and ignores keys it does not handle", () => {
      const { container, cell } = setup();
      cell(3).focus();
      const up = fireEvent.keyDown(cell(3), { key: "ArrowUp" });
      expect(up).toBe(false); // handled: the page must not scroll
      expect(document.activeElement).toBe(cell(3));
      const tab = fireEvent.keyDown(cell(3), { key: "Tab" });
      expect(tab).toBe(true); // not ours: Tab still leaves the grid
      expect(tabbable(container)).toEqual([cell(3)]);
    });

    it("opens the focused pair on Enter or Space", () => {
      const { onOpenPair, cell } = setup();
      fireEvent.keyDown(cell(1), { key: "Enter" });
      expect(onOpenPair).toHaveBeenLastCalledWith("Aquinas", "Vulgate");
      fireEvent.keyDown(cell(2), { key: " " });
      expect(onOpenPair).toHaveBeenLastCalledWith("Aquinas", "Plato");
    });

    it("shows the hover tooltip and crosshair on focus, and hides them on blur", () => {
      const { container, cell } = setup();
      fireEvent.focus(cell(1));
      expect(container.querySelector(".net-tooltip")?.textContent).toContain("300 xrefs");
      expect(container.querySelector(".net-matrix-crosshair")).toBeTruthy();
      fireEvent.blur(cell(1));
      expect(container.querySelector(".net-tooltip")).toBeNull();
      expect(container.querySelector(".net-matrix-crosshair")).toBeNull();
    });
  });
});
