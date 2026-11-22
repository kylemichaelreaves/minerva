import { fireEvent, render, screen } from "@solidjs/testing-library";
import { flush } from "solid-js";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { MatrixCell, NetworkAuthor } from "~/api/networkApi";
import { MatrixPanel } from "~/Network/components/MatrixPanel";
import { must } from "./helpers/must";

const authors: NetworkAuthor[] = [
  { name: "Hebrew Bible", short: "HB", ord: 50, corpus: "scrip" },
  { name: "Plato", short: "Pl", ord: 100, corpus: "class" },
  { name: "Aristotle", short: "Ar", ord: 200, corpus: "class" },
];
// Aristotle → Plato, Aristotle → HB, Plato → HB. Nobody cites Aristotle, so
// the columns are Plato then HB: the classical band comes before scripture.
const cells: MatrixCell[] = [
  { r: 2, c: 1, n: 1234 },
  { r: 2, c: 0, n: 10 },
  { r: 1, c: 0, n: 5 },
];

// happy-dom has no layout, so drive useElementSize by hand: capture the
// observer callback and fire it after giving the wrap a client box.
let observerCallbacks: (() => void)[] = [];
beforeEach(() => {
  observerCallbacks = [];
  vi.stubGlobal(
    "ResizeObserver",
    class {
      constructor(cb: () => void) {
        observerCallbacks.push(cb);
      }
      observe() {
        /* driven manually via observerCallbacks */
      }
      unobserve() {
        /* no-op */
      }
      disconnect() {
        /* no-op */
      }
    },
  );
});
afterEach(() => {
  vi.unstubAllGlobals();
});

function resize(el: HTMLElement, w: number, h: number) {
  Object.defineProperty(el, "clientWidth", { value: w, configurable: true });
  Object.defineProperty(el, "clientHeight", { value: h, configurable: true });
  for (const cb of observerCallbacks) cb();
  flush();
}

/** Mirrors MatrixPanel's geometry: PAD l 112, r 6. Cells are sized to the
 *  width independently of the height, so a column is (w - 118) / cols. */
function expectedColW(w: number, cols: number) {
  return (w - 118) / cols;
}

/** Column label x, and its -90° rotation about (x, PAD.t - 6 = 98). */
function expectedX(w: number, cols: number, k: number) {
  const cw = expectedColW(w, cols);
  return 112 + k * cw + cw / 2 + 3.5;
}

function colLabels(container: HTMLElement) {
  // Column labels are the rotated <text> directly under the SVG; the
  // rotated row-band captions sit inside a <g>.
  return [...container.querySelectorAll("svg > text[transform]")];
}

function mount(onOpenPair = vi.fn()) {
  const { container } = render(() => (
    <MatrixPanel authors={authors} cells={cells} onOpenPair={onOpenPair} />
  ));
  const wrap = must(
    container.querySelector<HTMLElement>(".net-matrix-svg-wrap"),
    ".net-matrix-svg-wrap",
  );
  return { container, wrap, onOpenPair };
}

describe("<MatrixPanel />", () => {
  // Regression: the column-label x was a plain const inside <For>'s
  // untracked mapper, so it was computed at the first layout and never
  // followed a resize — the labels drifted away from their columns.
  it("column-label x and rotate transform follow a layout change", () => {
    const { container, wrap } = mount();

    resize(wrap, 720, 460);
    let labels = colLabels(container);
    expect(labels.map((t) => t.textContent)).toEqual(["Pl", "HB"]);
    labels.forEach((t, k) => {
      const x = expectedX(720, 2, k);
      expect(Number(t.getAttribute("x"))).toBeCloseTo(x, 6);
      expect(t.getAttribute("transform")).toBe(`rotate(-90 ${x} 98)`);
    });

    resize(wrap, 400, 300);
    labels = colLabels(container);
    labels.forEach((t, k) => {
      const x = expectedX(400, 2, k);
      expect(Number(t.getAttribute("x"))).toBeCloseTo(x, 6);
      expect(t.getAttribute("transform")).toBe(`rotate(-90 ${x} 98)`);
    });
    // Sanity: the change is real, not a coincidence of equal columns.
    expect(expectedColW(400, 2)).not.toBeCloseTo(expectedColW(720, 2), 1);
  });

  it("colours scripture column labels terra and others ink", () => {
    const { container } = mount();
    const fills = colLabels(container).map((t) => t.getAttribute("fill"));
    expect(fills).toEqual(["var(--ink)", "var(--net-terra)"]);
  });

  it("shows a tooltip for the hovered cell, hides it on leave, and opens the pair on click", () => {
    const { container, onOpenPair } = mount();
    const rect = screen.getByRole("gridcell", { name: /^Aristotle → Plato:/ });

    expect(container.querySelector(".net-tooltip")).toBeNull();
    fireEvent.mouseEnter(rect);
    flush();
    const tip = must(container.querySelector(".net-tooltip"), ".net-tooltip");
    expect(tip.querySelector(".pair")?.textContent).toBe("Aristotle → Plato");
    expect(tip.querySelector(".count")?.textContent).toBe(`${(1234).toLocaleString()} xrefs`);

    fireEvent.mouseLeave(rect);
    flush();
    expect(container.querySelector(".net-tooltip")).toBeNull();

    fireEvent.click(rect);
    flush();
    expect(onOpenPair).toHaveBeenCalledWith("Aristotle", "Plato");
  });
});
