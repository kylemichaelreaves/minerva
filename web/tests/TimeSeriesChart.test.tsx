import { render, screen } from "@solidjs/testing-library";
import { describe, expect, it } from "vitest";
import { TimeSeriesChart } from "~/Metrics/TimeSeriesChart";
import type { MetricsSeriesPoint } from "~/api/metricsApi";

const point = (t: number, p50: number, p95: number): MetricsSeriesPoint => ({
  t, count: 10, mean_ms: p50, max_ms: p95, p50_ms: p50, p95_ms: p95, p99_ms: p95,
});

describe("TimeSeriesChart", () => {
  it("renders an empty state rather than an axis-less chart", () => {
    render(() => <TimeSeriesChart points={[]} />);
    expect(screen.getByText(/no data/i)).toBeTruthy();
  });

  it("draws one polyline per series", () => {
    const points = [point(0, 10, 40), point(300, 12, 50), point(600, 11, 45)];
    const { container } = render(() => <TimeSeriesChart points={points} />);
    expect(container.querySelectorAll("polyline").length).toBe(2);
  });

  it("survives a single point without dividing by a zero span", () => {
    const { container } = render(() => <TimeSeriesChart points={[point(0, 10, 40)]} />);
    const d = container.querySelector("polyline")?.getAttribute("points") ?? "";
    expect(d).not.toContain("NaN");
  });

  it("survives a flat series without dividing by a zero range", () => {
    const points = [point(0, 10, 10), point(300, 10, 10)];
    const { container } = render(() => <TimeSeriesChart points={points} />);
    const d = container.querySelector("polyline")?.getAttribute("points") ?? "";
    expect(d).not.toContain("NaN");
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

  it("direct-labels each series and shows a legend, without coloring the text", () => {
    const points = [point(0, 10, 40), point(300, 12, 50)];
    const { container } = render(() => <TimeSeriesChart points={points} />);
    expect(screen.getAllByText("p50").length).toBeGreaterThan(0);
    expect(screen.getAllByText("p95").length).toBeGreaterThan(0);
    for (const el of Array.from(container.querySelectorAll("text"))) {
      expect(el.getAttribute("class") ?? "").not.toMatch(/mchart-line/);
    }
  });
});
