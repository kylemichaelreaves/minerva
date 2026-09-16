import { render } from "@solidjs/testing-library";
import { describe, expect, it } from "vitest";
import type { MetricsSummaryRow } from "~/api/metricsApi";
import { StatTiles, formatDelta } from "~/Metrics/StatTiles";

const row = (over: Partial<MetricsSummaryRow> = {}): MetricsSummaryRow => ({
  label: "work range",
  method: "GET",
  kind: "total",
  span: "",
  count: 47,
  mean_ms: 500,
  min_ms: 1,
  max_ms: 10_000,
  p50_ms: 210,
  p95_ms: 9800,
  p99_ms: 10_000,
  error_rate: 0,
  ...over,
});

describe("formatDelta", () => {
  it("is an em dash when there is no baseline", () => {
    expect(formatDelta(undefined, "6h").text).toBe("—");
  });

  it("names the window it compared against", () => {
    expect(formatDelta(0.38, "6h").text).toBe("+38% vs previous 6h");
  });

  it("signs a fall", () => {
    expect(formatDelta(-0.04, "24h").text).toBe("-4% vs previous 24h");
  });

  it("reports no change without a sign", () => {
    expect(formatDelta(0, "1h").text).toBe("0% vs previous 1h");
  });

  it("marks a rise as the bad direction and a fall as the good one", () => {
    // Latency going up is the regression, so "up" is the bad class -
    // the inverse of the usual "up is good" reading.
    expect(formatDelta(0.38, "6h").direction).toBe("up");
    expect(formatDelta(-0.04, "6h").direction).toBe("down");
    expect(formatDelta(0, "6h").direction).toBe("");
    expect(formatDelta(undefined, "6h").direction).toBe("");
  });

  it("rounds to whole percent", () => {
    expect(formatDelta(3.104, "6h").text).toBe("+310% vs previous 6h");
  });
});

describe("StatTiles", () => {
  it("renders p50, p95, p99 and errors", () => {
    const view = render(() => <StatTiles row={row()} windowLabel="6h" />);
    for (const label of ["p50", "p95", "p99", "errors"]) {
      expect(view.getByText(label)).toBeTruthy();
    }
    expect(view.getByText("9800")).toBeTruthy();
  });

  it("shows a clean route as zero errors with no count", () => {
    const view = render(() => <StatTiles row={row({ error_rate: 0 })} windowLabel="6h" />);
    expect(view.getByText("none")).toBeTruthy();
  });

  it("reconstructs the error count from the rate", () => {
    // The response carries the ratio, not the count, so this is derived.
    const view = render(() => (
      <StatTiles row={row({ count: 47, error_rate: 9 / 47 })} windowLabel="6h" />
    ));
    expect(view.getByText("9 of 47")).toBeTruthy();
  });

  it("rounds the reconstruction rather than truncating it", () => {
    // 15/22 * 22 is 14.999999999999998 in float, so `Math.floor` would
    // silently report one error fewer than actually occurred. Chosen by
    // searching count <= 200 for the first rate where the two disagree -
    // the realistic 9-of-47 case above does NOT distinguish them.
    const view = render(() => (
      <StatTiles row={row({ count: 22, error_rate: 15 / 22 })} windowLabel="6h" />
    ));
    expect(view.getByText("15 of 22")).toBeTruthy();
  });

  it("shows each percentile's delta against the prior row", () => {
    const view = render(() => (
      <StatTiles row={row({ p95_ms: 138 })} prior={row({ p95_ms: 100 })} windowLabel="6h" />
    ));
    expect(view.getByText("+38% vs previous 6h")).toBeTruthy();
  });

  it("shows an em dash for a percentile whose prior value was zero", () => {
    // Dividing by it yields Infinity, which would render "+Infinity%"
    // rather than admitting there is nothing to compare against.
    const view = render(() => (
      <StatTiles row={row({ p50_ms: 40 })} prior={row({ p50_ms: 0 })} windowLabel="6h" />
    ));
    expect(view.getAllByText("—")).toHaveLength(1);
  });

  it("shows an em dash for every percentile when there is no prior row", () => {
    const view = render(() => <StatTiles row={row()} windowLabel="all" />);
    expect(view.getAllByText("—")).toHaveLength(3);
  });
});
