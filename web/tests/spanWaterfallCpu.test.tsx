/** The aggregate waterfall after CPU and SQLite joined `request_timings`.
 *
 *  The labeled drill-down filters on `span != ''` only, so it now returns
 *  BOTH the wall row and the cpu row for each span. Rendering the list
 *  unfiltered would draw every span twice — and the comment in MetricsPanel
 *  saying the list "is never filtered by spanKind" was true only while the
 *  recorder emitted a single kind.
 */
import { render, screen } from "@solidjs/testing-library";
import { describe, expect, it } from "vitest";

import { SpanWaterfall, wallRows, cpuByName } from "../src/Metrics/SpanWaterfall";
import type { MetricsSummaryRow } from "../src/api/metricsApi";

function row(over: Partial<MetricsSummaryRow>): MetricsSummaryRow {
  return {
    label: "chat",
    method: "POST",
    kind: "total",
    span: "",
    count: 10,
    mean_ms: 1,
    min_ms: 1,
    max_ms: 1,
    error_rate: 0,
    p50_ms: 1,
    p95_ms: 1,
    p99_ms: 1,
    ...over,
  };
}

const ROWS = [
  row({ kind: "total", span: "llm_call", p95_ms: 4750 }),
  row({ kind: "cpu", span: "llm_call", p95_ms: 19 }),
  row({ kind: "total", span: "sqlite", p95_ms: 240 }),
];

describe("wallRows", () => {
  it("drops cpu rows so each span is drawn once", () => {
    expect(wallRows(ROWS).map((r) => r.span)).toEqual(["llm_call", "sqlite"]);
  });

  it("indexes cpu by span name", () => {
    expect(cpuByName(ROWS)).toEqual({ llm_call: 19 });
  });

  it("has no entry for a span whose cpu was never measured", () => {
    // `thread_time` missing, or a row written before Phase 2. Absent, not 0.
    expect(cpuByName([row({ kind: "total", span: "sqlite", p95_ms: 240 })])).toEqual({});
  });
});

describe("SpanWaterfall", () => {
  it("draws each span once even when cpu rows are present", () => {
    render(() => <SpanWaterfall rows={ROWS} totalP95={5000} />);
    expect(screen.getAllByText("llm_call")).toHaveLength(1);
  });

  it("shows database time as its own row", () => {
    render(() => <SpanWaterfall rows={ROWS} totalP95={5000} />);
    expect(screen.getByText("sqlite")).toBeTruthy();
  });

  it("labels a span by what its cpu share says about it", () => {
    // llm_call: 19ms cpu against 4750ms wall — waiting, not computing.
    render(() => <SpanWaterfall rows={ROWS} totalP95={5000} />);
    expect(screen.getByLabelText("Where the time goes").textContent).toMatch(/waiting/i);
  });

  it("says nothing about cpu for a span that has none", () => {
    const only = [row({ kind: "total", span: "sqlite", p95_ms: 240 })];
    render(() => <SpanWaterfall rows={only} totalP95={5000} />);
    const wf = screen.getByLabelText("Where the time goes");
    expect(wf.textContent).not.toMatch(/waiting|cpu-bound|mixed/i);
  });
});
