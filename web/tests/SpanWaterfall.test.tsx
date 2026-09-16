import { render } from "@solidjs/testing-library";
import { describe, expect, it } from "vitest";
import type { MetricsSummaryRow } from "~/api/metricsApi";
import { SpanWaterfall, spanShare } from "~/Metrics/SpanWaterfall";

const span = (name: string, p95: number): MetricsSummaryRow => ({
  label: "work range",
  method: "GET",
  kind: "total",
  span: name,
  count: 47,
  mean_ms: p95 / 2,
  min_ms: 1,
  max_ms: p95,
  p50_ms: p95 / 2,
  p95_ms: p95,
  p99_ms: p95,
  error_rate: 0,
});

describe("spanShare", () => {
  it("is the span's p95 as a fraction of the route's", () => {
    // Verified against the source design's own fixture: range_scan
    // 8900/9800 carries pct 91, hydrate 620/9800 carries 6.
    expect(Math.round(spanShare(8900, 9800) * 100)).toBe(91);
    expect(Math.round(spanShare(620, 9800) * 100)).toBe(6);
  });

  it("is zero when the route's p95 is zero", () => {
    expect(spanShare(50, 0)).toBe(0);
  });

  it("can exceed one", () => {
    // Sub-spans are recorded per attempt while the total is per request,
    // so a retried span genuinely can outlast its own request. Clamping
    // the NUMBER would hide that; only the bar width is clamped.
    expect(spanShare(200, 100)).toBe(2);
  });
});

describe("SpanWaterfall", () => {
  it("renders one row per span with its value and share", () => {
    const view = render(() => (
      <SpanWaterfall rows={[span("range_scan", 8900), span("hydrate", 620)]} totalP95={9800} />
    ));
    expect(view.getByText("range_scan")).toBeTruthy();
    expect(view.getByText("hydrate")).toBeTruthy();
    expect(view.getByText(/8900.*91%/)).toBeTruthy();
  });

  it("reports the total it measured shares against", () => {
    const view = render(() => <SpanWaterfall rows={[span("q", 10)]} totalP95={9800} />);
    expect(view.getByText(/9800 ms total/)).toBeTruthy();
  });

  it("says so when a route recorded no sub-spans", () => {
    // Only three code paths are instrumented, so this is the common
    // case rather than the edge one.
    const view = render(() => <SpanWaterfall rows={[]} totalP95={220} />);
    expect(view.getByText(/no sub-spans recorded/i)).toBeTruthy();
  });

  it("carries the llm_call caveat only on that span", () => {
    const view = render(() => (
      <SpanWaterfall rows={[span("llm_call", 3420), span("retrieve", 640)]} totalP95={4320} />
    ));
    expect(view.getByText(/per attempt/i)).toBeTruthy();
    expect(view.queryAllByText(/per attempt/i)).toHaveLength(1);
  });

  it("clamps only the bar width when a span outlasts the request", () => {
    const view = render(() => <SpanWaterfall rows={[span("llm_call", 200)]} totalP95={100} />);
    // The printed figure keeps the truth...
    expect(view.getByText(/200 · 200%/)).toBeTruthy();
    // ...while the bar stops at the track's edge.
    const bar = view.container.querySelector<HTMLElement>(".metrics-wf-bar i");
    expect(bar?.style.width).toBe("100%");
  });

  it("notes that sub-spans are whole-request when the ttfe tab is active", () => {
    // The recorder never tags a sub-span `ttfe`, so this table cannot
    // follow the tab and must say so rather than look stale.
    const view = render(() => (
      <SpanWaterfall rows={[span("q", 10)]} totalP95={100} spanKind="ttfe" />
    ));
    expect(view.getByText(/measured on the whole request/i)).toBeTruthy();
  });

  it("omits that note on the total tab", () => {
    const view = render(() => (
      <SpanWaterfall rows={[span("q", 10)]} totalP95={100} spanKind="total" />
    ));
    expect(view.queryByText(/measured on the whole request/i)).toBeNull();
  });

  // Carries forward #595's naming of the sub-span table this card
  // replaced: an accessible name is what makes the breakdown addressable
  // by role rather than by its copy.
  it("names the breakdown so it is addressable by role (#593)", () => {
    const view = render(() => <SpanWaterfall rows={[span("range_scan", 8900)]} totalP95={9800} />);
    expect(view.getByRole("region", { name: "Where the time goes" })).toBeTruthy();
  });
});
