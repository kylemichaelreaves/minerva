import { fireEvent, render } from "@solidjs/testing-library";
import { describe, expect, it, vi } from "vitest";
import type { MetricsSummaryRow } from "~/api/metricsApi";
import { RouteDetail } from "~/Metrics/RouteDetail";

const row = (over: Partial<MetricsSummaryRow> = {}): MetricsSummaryRow => ({
  label: "chat message",
  method: "POST",
  kind: "total",
  span: "",
  count: 128,
  mean_ms: 1200,
  min_ms: 10,
  max_ms: 6100,
  p50_ms: 1150,
  p95_ms: 4320,
  p99_ms: 6100,
  error_rate: 0,
  ...over,
});

const base = {
  label: "chat message",
  method: "POST",
  windowLabel: "6h",
  spanKind: "total" as const,
  onSpanKind: vi.fn(),
  hasTtfe: false,
  onBack: vi.fn(),
  seriesPoints: [],
  seriesBucketSeconds: 300,
  seriesLoading: false,
  detailRows: [],
  detailLoading: false,
};

describe("RouteDetail", () => {
  it("says the route recorded nothing rather than rendering empty tiles", () => {
    // Reachable two ways: a `?label=` deep link into a route that has
    // since gone quiet, and switching to a window narrow enough to
    // exclude it. Tiles of "0ms / —" would read as a measurement.
    const view = render(() => <RouteDetail {...base} />);
    expect(view.getByRole("status").textContent).toMatch(/recorded nothing/i);
    expect(view.container.querySelector(".metrics-tiles")).toBeNull();
  });

  it("measures span shares against zero when there is no row to measure against", () => {
    // The waterfall still renders (the spans themselves came back), but
    // every share is 0 rather than NaN%.
    const view = render(() => (
      <RouteDetail {...base} detailRows={[row({ span: "llm_call", p95_ms: 300 })]} />
    ));
    expect(view.getByText(/300 · 0%/)).toBeTruthy();
  });

  it("counts the requests in its meta line", () => {
    const view = render(() => <RouteDetail {...base} row={row()} />);
    expect(view.getByText("128 requests")).toBeTruthy();
  });

  it("calls a streaming route streaming", () => {
    // Derived from the presence of a ttfe row, not recorded anywhere.
    const view = render(() => <RouteDetail {...base} row={row()} hasTtfe={true} />);
    expect(view.getByText(/^streaming · 128 requests$/)).toBeTruthy();
  });

  it("offers no tabs for a route that does not stream", () => {
    const view = render(() => <RouteDetail {...base} row={row()} />);
    expect(view.queryByText("Time to first event")).toBeNull();
  });

  it("reports the tab the reader picked", () => {
    const onSpanKind = vi.fn();
    const view = render(() => (
      <RouteDetail {...base} row={row()} hasTtfe={true} onSpanKind={onSpanKind} />
    ));
    fireEvent.click(view.getByText("Time to first event"));
    expect(onSpanKind).toHaveBeenCalledWith("ttfe");
  });

  it("marks the active tab for assistive technology", () => {
    const view = render(() => <RouteDetail {...base} row={row()} hasTtfe={true} spanKind="ttfe" />);
    const pressed = view.container.querySelectorAll('.metrics-tabs [aria-pressed="true"]');
    expect(pressed).toHaveLength(1);
    expect(pressed[0]?.textContent).toBe("Time to first event");
  });

  it("offers a way back to the list", () => {
    // Hidden by CSS on desktop, where both panes are on screen at once;
    // the mobile layout stacks them and this is the only way back.
    const onBack = vi.fn();
    const view = render(() => <RouteDetail {...base} row={row()} onBack={onBack} />);
    fireEvent.click(view.getByText(/all routes/i));
    expect(onBack).toHaveBeenCalled();
  });
});
