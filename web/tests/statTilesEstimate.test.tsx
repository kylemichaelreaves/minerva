/** Percentile tiles say they are estimates (#616).
 *
 *  Quantiles come from 14 log-scale buckets; `min_ms`/`max_ms` are exact.
 *  On live data p99 exceeds max on 8 of 24 routes. Nothing renders max today,
 *  so the contradiction is latent — but per-request rows make a "slowest
 *  request" view easy, and that is where it surfaces. Labelling the estimate
 *  now costs nothing and makes the later panel honest by default.
 */
import { render, screen } from "@solidjs/testing-library";
import { describe, expect, it } from "vitest";

import { StatTiles } from "../src/Metrics/StatTiles";
import type { MetricsSummaryRow } from "../src/api/metricsApi";

const ROW = {
  label: "chunk syntax",
  method: "GET",
  kind: "total",
  span: "",
  count: 8,
  mean_ms: 40,
  min_ms: 5,
  max_ms: 116,
  error_rate: 0,
  p50_ms: 5,
  p95_ms: 220,
  p99_ms: 244,
} as MetricsSummaryRow;

describe("StatTiles", () => {
  it("marks each percentile as an estimate", () => {
    render(() => <StatTiles row={ROW} prior={undefined} windowLabel="6h" />);
    for (const key of ["p50", "p95", "p99"]) {
      const tile = screen.getByText(key).closest("div");
      expect(tile?.getAttribute("title") ?? "").toMatch(/estimate/i);
    }
  });

  it("says what the estimate is derived from", () => {
    render(() => <StatTiles row={ROW} prior={undefined} windowLabel="6h" />);
    const title = screen.getByText("p99").closest("div")?.getAttribute("title") ?? "";
    expect(title).toMatch(/bucket/i);
  });

  it("does not label the errors tile as an estimate", () => {
    // `error_rate` is a ratio of counted requests, not a bucketed quantile.
    render(() => <StatTiles row={ROW} prior={undefined} windowLabel="6h" />);
    const tile = screen.getByText(/errors/i).closest("div");
    expect(tile?.getAttribute("title") ?? "").not.toMatch(/estimate/i);
  });
});
