// @vitest-environment jsdom
import { render, screen } from "@solidjs/testing-library";
import { describe, expect, it } from "vitest";
import { TimeSeriesChart, formatTimeLabel } from "~/Metrics/TimeSeriesChart";
import type { MetricsSeriesPoint } from "~/api/metricsApi";
import { must } from "./helpers/must";

const point = (t: number, p50: number, p95: number): MetricsSeriesPoint => ({
  t,
  count: 10,
  mean_ms: p50,
  max_ms: p95,
  p50_ms: p50,
  p95_ms: p95,
  p99_ms: p95,
});

/**
 * `useElementSize` (web/src/hooks/useElementSize.tsx) reads
 * `node.clientWidth`/`clientHeight` in `onMount` and overwrites its
 * `initial` fallback even when jsdom reports `0` — tracked separately
 * as #585, not fixed here (it's shared with three Network panels).
 * Geometry assertions need a real measured size, so stub the
 * prototype getters for the duration of one render and restore them
 * in `finally` so a stub can't leak into another test.
 *
 * jsdom defines `clientWidth`/`clientHeight` as accessors on
 * `Element.prototype`, not `HTMLElement.prototype` — stub and restore
 * on the prototype that actually owns them. The `else delete` arms
 * make the restore correct even if a future jsdom version moves the
 * property onto a different prototype in the chain (own-property
 * there, nothing to restore here), rather than being correct only for
 * the one prototype this file happens to name today.
 */
function withMeasuredSize<T>(w: number, h: number, fn: () => T): T {
  const cw = Object.getOwnPropertyDescriptor(Element.prototype, "clientWidth");
  const ch = Object.getOwnPropertyDescriptor(Element.prototype, "clientHeight");
  Object.defineProperty(Element.prototype, "clientWidth", { configurable: true, value: w });
  Object.defineProperty(Element.prototype, "clientHeight", { configurable: true, value: h });
  try {
    return fn();
  } finally {
    if (cw) Object.defineProperty(Element.prototype, "clientWidth", cw);
    else delete (Element.prototype as unknown as Record<string, unknown>).clientWidth;
    if (ch) Object.defineProperty(Element.prototype, "clientHeight", ch);
    else delete (Element.prototype as unknown as Record<string, unknown>).clientHeight;
  }
}

function parsePolylinePoints(pointsAttr: string): [number, number][] {
  return pointsAttr
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((pair) => {
      const parts = pair.split(",");
      return [Number(parts[0]), Number(parts[1])] as [number, number];
    });
}

describe("withMeasuredSize", () => {
  it("restores the real element size after stubbing, even if the callback throws", () => {
    withMeasuredSize(640, 220, () => {
      expect(document.createElement("div").clientWidth).toBe(640);
    });
    expect(document.createElement("div").clientWidth).toBe(0);

    expect(() =>
      withMeasuredSize(640, 220, () => {
        throw new Error("boom");
      }),
    ).toThrow("boom");
    expect(document.createElement("div").clientWidth).toBe(0);
  });
});

describe("TimeSeriesChart", () => {
  it("renders an empty state rather than an axis-less chart", () => {
    render(() => <TimeSeriesChart points={[]} />);
    expect(screen.getByText(/no data/i)).toBeTruthy();
  });

  it("draws one polyline per series, spread across the time scale", () => {
    const points = [point(0, 10, 40), point(300, 12, 50), point(600, 11, 45)];
    const { container } = withMeasuredSize(640, 220, () =>
      render(() => <TimeSeriesChart points={points} />),
    );
    const polylines = container.querySelectorAll("polyline");
    expect(polylines.length).toBe(2);
    const p50Pairs = parsePolylinePoints(polylines[0]?.getAttribute("points") ?? "");
    const distinctXs = new Set(p50Pairs.map(([x]) => x));
    expect(distinctXs.size).toBeGreaterThan(1);
  });

  it("survives a single point without dividing by a zero span, placing it inside the plot", () => {
    const { container } = withMeasuredSize(640, 220, () =>
      render(() => <TimeSeriesChart points={[point(0, 10, 40)]} />),
    );
    const d = container.querySelector("polyline")?.getAttribute("points") ?? "";
    expect(d).not.toContain("NaN");
    const pairs = parsePolylinePoints(d);
    expect(pairs.length).toBe(1);
    const pair = pairs[0];
    expect(pair).toBeDefined();
    const [x, y] = must(pair);
    expect(Number.isFinite(x)).toBe(true);
    expect(Number.isFinite(y)).toBe(true);
    expect(x).toBeGreaterThanOrEqual(0);
    expect(x).toBeLessThanOrEqual(640);
    expect(y).toBeGreaterThanOrEqual(0);
    expect(y).toBeLessThanOrEqual(220);
  });

  it("survives a flat series without dividing by a zero range, spreading x while holding y constant", () => {
    const points = [point(0, 10, 10), point(300, 10, 10)];
    const { container } = withMeasuredSize(640, 220, () =>
      render(() => <TimeSeriesChart points={points} />),
    );
    const d = container.querySelector("polyline")?.getAttribute("points") ?? "";
    expect(d).not.toContain("NaN");
    const pairs = parsePolylinePoints(d);
    expect(pairs.length).toBe(2);
    const [first, second] = pairs;
    expect(first).toBeDefined();
    expect(second).toBeDefined();
    const [x0, y0] = must(first);
    const [x1, y1] = must(second);
    expect(x0).not.toBe(x1);
    expect(y0).toBe(y1);
  });

  it("draws four gridlines that are not all on the same row", () => {
    const points = [point(0, 10, 40), point(300, 12, 50), point(600, 11, 45)];
    const { container } = withMeasuredSize(640, 220, () =>
      render(() => <TimeSeriesChart points={points} />),
    );
    const ys = Array.from(container.querySelectorAll("line.mchart-grid")).map((el) =>
      Number(el.getAttribute("y1")),
    );
    expect(ys.length).toBe(4);
    expect(new Set(ys).size).toBeGreaterThan(1);
  });

  it("labels the y axis in milliseconds", () => {
    render(() => <TimeSeriesChart points={[point(0, 10, 40)]} />);
    expect(screen.getByText(/ms/)).toBeTruthy();
  });

  it("respects an explicit height", () => {
    const points = [point(0, 10, 40), point(300, 12, 50)];
    const { container } = render(() => <TimeSeriesChart points={points} height={180} />);
    const svg = container.querySelector("svg");
    expect(svg?.getAttribute("height")).toBe("180");
  });

  it("labels the x axis with times for sub-daily buckets", () => {
    // 5-minute buckets: the two ticks differ, so HH:MM says something.
    const points = [point(0, 10, 40), point(300, 12, 50)];
    render(() => <TimeSeriesChart points={points} bucketSeconds={300} />);
    expect(screen.getByText("00:00")).toBeTruthy();
    expect(screen.getByText("00:05")).toBeTruthy();
  });

  it("labels the x axis with dates once the server buckets daily", () => {
    // 7d/30d/all bucket daily, and every daily bucket starts at midnight
    // UTC — so both ticks used to read "00:00": two identical, useless
    // labels on the only axis that says which day you are looking at.
    const day = 86400;
    const points = [point(0, 10, 40), point(day, 12, 50)];
    render(() => <TimeSeriesChart points={points} bucketSeconds={day} />);
    expect(screen.getByText("1970-01-01")).toBeTruthy();
    expect(screen.getByText("1970-01-02")).toBeTruthy();
    expect(screen.queryByText("00:00")).toBeNull();
  });

  it("falls back to a time label when no bucket width is given", () => {
    expect(formatTimeLabel(0)).toBe("00:00");
    expect(formatTimeLabel(86400, 3600)).toBe("00:00");
  });

  it("direct-labels each series and shows a legend, without coloring the text", () => {
    const points = [point(0, 10, 40), point(300, 12, 50)];
    const { container } = render(() => <TimeSeriesChart points={points} />);
    expect(screen.getAllByText("p50").length).toBeGreaterThan(0);
    expect(screen.getAllByText("p95").length).toBeGreaterThan(0);
    for (const el of Array.from(container.querySelectorAll("text"))) {
      expect(el.getAttribute("class") ?? "").not.toMatch(/mchart-line/);
    }
  });

  // Regression: the chart used to take its height from `useElementSize` on
  // `.mchart-svg-wrap` — the very element the SVG renders into. That wrap is
  // `width: 100%` with no height, so its height is content-driven, and the
  // only content is the SVG being sized. Each ResizeObserver tick therefore
  // grew the SVG by the layout delta, without bound: measured live in Chrome
  // at 164220px, then 220348 → 220828 → 221308 → 221788, +480px per frame.
  //
  // jsdom cannot reproduce the loop (clientHeight is always 0 here — see
  // #585), and stubbing the size to a constant is exactly the condition
  // under which the bug cannot appear. So assert the invariant instead:
  // height must never be read from the observed element.
  it("does not take its height from the element it renders into", () => {
    const points = [point(0, 10, 40), point(300, 12, 50)];
    const { container } = withMeasuredSize(900, 5000, () =>
      render(() => <TimeSeriesChart points={points} />),
    );
    const svg = container.querySelector("svg");
    expect(svg?.getAttribute("height")).toBe("220");
    expect(svg?.getAttribute("viewBox")).toBe("0 0 900 220");
  });

  it("still takes its width from the element, which is parent-constrained", () => {
    const points = [point(0, 10, 40), point(300, 12, 50)];
    const { container } = withMeasuredSize(900, 5000, () =>
      render(() => <TimeSeriesChart points={points} />),
    );
    expect(container.querySelector("svg")?.getAttribute("width")).toBe("900");
  });
});
