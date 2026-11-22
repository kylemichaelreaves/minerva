/**
 * HeatmapPanel must let Solid reconcile its grid (#200, item 2).
 *
 * Two imperative IIFEs pushed SVG nodes into an array, so every
 * `ResizeObserver` tick tore the whole grid down and rebuilt it —
 * ~(books × authors) `<rect>` elements plus labels, on every resize
 * frame — while `:134` and `:154` in the same file already used `<For>`.
 *
 * The load-bearing test is `keeps the same DOM nodes across a resize`:
 * it is the one that fails on the IIFE version and passes on `<For>`.
 * The rest pin the geometry so the refactor cannot quietly move a cell.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, cleanup } from "@solidjs/testing-library";
import { flush } from "solid-js";
import { HeatmapPanel } from "~/Network/components/HeatmapPanel";
import type { HeatmapCell, HeatmapSection } from "~/api/networkApi";

// jsdom reports clientWidth/clientHeight as 0, and the panel's layout
// math divides by them. Back them with a mutable box so a "resize" is a
// real change in the numbers the component reads.
let box = { w: 800, h: 300 };
const observerCallbacks: (() => void)[] = [];

beforeEach(() => {
  box = { w: 800, h: 300 };
  observerCallbacks.length = 0;
  for (const prop of ["clientWidth", "clientHeight"] as const) {
    Object.defineProperty(HTMLElement.prototype, prop, {
      configurable: true,
      get() {
        return prop === "clientWidth" ? box.w : box.h;
      },
    });
  }
  vi.stubGlobal(
    "ResizeObserver",
    class {
      constructor(cb: () => void) {
        observerCallbacks.push(cb);
      }
      observe() {
        /* no-op: the test fires callbacks directly via resizeTo() */
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
  cleanup();
  vi.unstubAllGlobals();
});

function resizeTo(w: number, h: number) {
  box = { w, h };
  for (const cb of observerCallbacks) cb();
}

const SECTIONS: HeatmapSection[] = [
  { name: "Torah", books: ["Gen", "Exod"] },
  { name: "Gospels", books: ["Matt", "Mark", "Luke"] },
];
const AUTHORS = ["Aquinas", "Augustine"];
const CELLS: HeatmapCell[] = [
  { author: "Aquinas", book: "Gen", n: 120 },
  { author: "Aquinas", book: "Matt", n: 40 },
  { author: "Augustine", book: "Gen", n: 7 },
];

function renderPanel() {
  return render(() => (
    <HeatmapPanel authors={AUTHORS} sections={SECTIONS} cells={CELLS} />
  ));
}

describe("HeatmapPanel grid", () => {
  it("renders one cell per author × book", () => {
    const { container } = renderPanel();
    // 5 books × 2 authors
    expect(container.querySelectorAll("rect").length).toBeGreaterThanOrEqual(10);
  });

  it("labels every cell with its author, book and count", () => {
    const { container } = renderPanel();
    const titles = [...container.querySelectorAll("rect title")].map((t) =>
      t.textContent.replace(/\s+/g, " ").trim(),
    );
    expect(titles).toContain("Aquinas → Gen: 120");
    expect(titles).toContain("Augustine → Gen: 7");
    // A pair with no cell row still gets a cell, showing zero.
    expect(titles).toContain("Augustine → Luke: 0");
  });

  it("renders a column label per book and a band label per section", () => {
    const { container } = renderPanel();
    const texts = [...container.querySelectorAll("text")].map((t) => t.textContent);
    for (const book of ["Gen", "Exod", "Matt", "Mark", "Luke"]) {
      expect(texts).toContain(book);
    }
    expect(texts).toContain("TORAH");
    expect(texts).toContain("GOSPELS");
  });

  it("renders a row label per author", () => {
    const { container } = renderPanel();
    const texts = [...container.querySelectorAll("text")].map((t) => t.textContent);
    expect(texts).toContain("Aquinas");
    expect(texts).toContain("Augustine");
  });

  it("keeps the same DOM nodes across a resize, updating their geometry", () => {
    const { container } = renderPanel();
    const before = [...container.querySelectorAll("rect")];
    // Cell WIDTH, not x: column 0 sits at `padL` whatever the panel
    // measures, so its x is size-independent and would make the
    // "attributes moved" check below pass vacuously.
    expect(before.length).toBeGreaterThan(0);
    const firstWidth = before[0]?.getAttribute("width");

    resizeTo(1200, 500);
    flush();

    const after = [...container.querySelectorAll("rect")];
    expect(after.length).toBe(before.length);
    // Node IDENTITY preserved — the grid was reconciled, not rebuilt.
    // This is what the imperative IIFE could not do. Compared with `===`
    // rather than `toEqual`, which would pass on two structurally equal
    // but freshly-created node sets.
    expect(before.every((node, i) => after[i] === node)).toBe(true);
    // …and the geometry did update, so the test isn't passing vacuously.
    expect(container.querySelector("svg")?.getAttribute("width")).toBe("1200");
    expect(after[0]?.getAttribute("width")).not.toBe(firstWidth);
  });

  it("positions columns left-to-right in section order", () => {
    const { container } = renderPanel();
    const xOf = (book: string) => {
      const label = [...container.querySelectorAll("text")].find(
        (t) => t.textContent === book,
      );
      return Number(label?.getAttribute("x"));
    };
    const xs = ["Gen", "Exod", "Matt", "Mark", "Luke"].map(xOf);
    for (let i = 1; i < xs.length; i++) {
      expect(xs[i] ?? 0).toBeGreaterThan(xs[i - 1] ?? 0);
    }
  });

  it("survives an empty corpus without dividing by zero", () => {
    const { container } = render(() => (
      <HeatmapPanel authors={[]} sections={[]} cells={[]} />
    ));
    const svg = container.querySelector("svg");
    expect(svg).toBeTruthy();
    expect(Number(svg?.getAttribute("width"))).toBeGreaterThan(0);
  });
});
