import { fireEvent, render } from "@solidjs/testing-library";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { MatrixCell, NetworkAuthor } from "~/api/networkApi";
import { MatrixPanel } from "~/Network/components/MatrixPanel";
import { must } from "./helpers/must";

const authors: NetworkAuthor[] = [
  { name: "Hebrew Bible", short: "HB", ord: 50, corpus: "scrip" },
  { name: "Plato", short: "Pl", ord: 100, corpus: "class" },
  { name: "Aristotle", short: "Ar", ord: 200, corpus: "class" },
];
const cells: MatrixCell[] = [{ r: 2, c: 1, n: 1234 }];

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
}

/** Mirrors MatrixPanel's layout memo: padL 78, padT 72, padR 8, padB 12. */
function expectedCell(w: number, h: number, n: number) {
  return Math.max(2, Math.min((w - 86) / n, (h - 84) / n));
}

function colLabels(container: HTMLElement) {
  // Column labels are the only <text> nodes carrying a rotate transform.
  return [...container.querySelectorAll("svg text[transform]")];
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
    let cell = expectedCell(720, 460, 3);
    let labels = colLabels(container);
    expect(labels.map((t) => t.textContent)).toEqual(["HB", "Pl", "Ar"]);
    labels.forEach((t, c) => {
      const x = 78 + c * cell + cell / 2;
      expect(Number(t.getAttribute("x"))).toBeCloseTo(x, 6);
      expect(t.getAttribute("transform")).toBe(`rotate(-45 ${x} 66)`);
    });

    resize(wrap, 400, 300);
    cell = expectedCell(400, 300, 3);
    labels = colLabels(container);
    labels.forEach((t, c) => {
      const x = 78 + c * cell + cell / 2;
      expect(Number(t.getAttribute("x"))).toBeCloseTo(x, 6);
      expect(t.getAttribute("transform")).toBe(`rotate(-45 ${x} 66)`);
    });
    // Sanity: the change is real, not a coincidence of equal cells.
    expect(expectedCell(400, 300, 3)).not.toBeCloseTo(expectedCell(720, 460, 3), 1);
  });

  it("colours scripture column labels terra and others ink", () => {
    const { container } = mount();
    const fills = colLabels(container).map((t) => t.getAttribute("fill"));
    expect(fills).toEqual(["var(--net-terra)", "var(--ink)", "var(--ink)"]);
  });

  it("shows a tooltip for the hovered cell, hides it on leave, and opens the pair on click", () => {
    const { container, onOpenPair } = mount();
    const rect = must(container.querySelector(".net-cell"), ".net-cell");

    expect(container.querySelector(".net-tooltip")).toBeNull();
    fireEvent.mouseEnter(rect);
    const tip = must(container.querySelector(".net-tooltip"), ".net-tooltip");
    expect(tip.querySelector(".pair")?.textContent).toBe("Aristotle → Plato");
    expect(tip.querySelector(".count")?.textContent).toBe(`${(1234).toLocaleString()} xrefs`);

    fireEvent.mouseLeave(rect);
    expect(container.querySelector(".net-tooltip")).toBeNull();

    fireEvent.click(rect);
    expect(onOpenPair).toHaveBeenCalledWith("Aristotle", "Plato");
  });
});
