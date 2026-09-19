import { apiGet, qs } from "~/api/client";

export const METRIC_WINDOWS = ["1h", "6h", "24h", "7d", "30d", "all"] as const;
export type MetricWindow = (typeof METRIC_WINDOWS)[number];

/** Whole-request timing, or a named step inside one when `span` is set. */
export interface MetricsSummaryRow {
  label: string;
  method: string;
  kind: "total" | "ttfe";
  span: string;
  count: number;
  mean_ms: number;
  min_ms: number;
  max_ms: number;
  p50_ms: number;
  p95_ms: number;
  p99_ms: number;
  error_rate: number;
}

/** Why an empty `rows` is not self-explanatory.
 *
 *  Three different situations render as a blank page: no traffic in the
 *  window, metrics persistence switched off (`minerva serve --no-metrics`, or
 *  the metrics DB could not be opened), and every write failing. `persisting`
 *  separates the second; `write_failures` counts the third. */
export interface MetricsHealth {
  write_failures: number;
  persisting: boolean;
}

export interface MetricsSummaryResponse {
  window: string;
  since: number;
  until: number;
  rows: MetricsSummaryRow[];
  health: MetricsHealth;
}

/** One completed request, from `request_spans` (#619).
 *
 *  NOT `request_timings` — that table folds requests into 5-minute buckets, so
 *  it can say how a route behaves but not which request was slow. This is the
 *  only durable place a request's total and its phases are paired. */
export interface MetricsRequestPhase {
  name: string;
  ms: number;
}

export interface MetricsRequestRow {
  id: string;
  at: number;
  label: string;
  method: string;
  status: number;
  total_ms: number;
  accounted_ms: number;
  /** `total_ms - accounted_ms`, computed server-side. Usually the whole
   *  request: only 0.22% of requests carry any phase at all. */
  unaccounted_ms: number;
  phases: MetricsRequestPhase[];
}

export interface MetricsRequestsResponse {
  window: string;
  since: number;
  until: number;
  rows: MetricsRequestRow[];
  /** The limit actually applied after clamping, not the one requested. */
  limit: number;
}

export interface MetricsSeriesPoint {
  t: number;
  count: number;
  mean_ms: number;
  max_ms: number;
  p50_ms: number;
  p95_ms: number;
  p99_ms: number;
}

export interface MetricsSeriesResponse {
  label: string;
  kind: string;
  span: string;
  bucket_seconds: number;
  points: MetricsSeriesPoint[];
}

/** Whole windows to shift the range back, so `1` at `window: "6h"` is
 *  the six hours before the last six. The backend rejects a non-zero
 *  offset for `window: "all"` — an unbounded window has no previous one.
 *
 *  Zero is folded to `undefined` rather than passed through: `qs` drops
 *  `undefined` but keeps a literal `0`, so every ordinary request would
 *  otherwise carry a redundant `offset=0`. Spelled out rather than
 *  `offset || undefined`, which `prefer-nullish-coalescing` rejects and
 *  `??` cannot express - `0 ?? undefined` is `0`. */
const offsetParam = (offset: number | undefined): number | undefined =>
  offset === undefined || offset === 0 ? undefined : offset;

export interface MetricsSummaryOptions {
  /** Drill into one route's sub-spans instead of listing whole requests. */
  label?: string;
  offset?: number;
}

export async function fetchMetricsSummary(
  window: MetricWindow,
  opts: MetricsSummaryOptions = {},
  signal?: AbortSignal,
): Promise<MetricsSummaryResponse> {
  return apiGet<MetricsSummaryResponse>(
    `/api/metrics/summary${qs({
      window,
      label: opts.label,
      offset: offsetParam(opts.offset),
    })}`,
    signal,
  );
}

export interface MetricsRequestsOptions {
  label?: string;
  method?: string;
  errors?: boolean;
  phased?: boolean;
  limit?: number;
}

export async function fetchMetricsRequests(
  window: MetricWindow,
  opts: MetricsRequestsOptions = {},
  signal?: AbortSignal,
): Promise<MetricsRequestsResponse> {
  return apiGet<MetricsRequestsResponse>(
    `/api/metrics/requests${qs({
      window,
      label: opts.label,
      method: opts.method,
      // Filtering is server-side on purpose: the table is designed to hold
      // years, so narrowing in the browser would mean shipping years to it.
      errors: opts.errors ? "1" : undefined,
      phased: opts.phased ? "1" : undefined,
      limit: opts.limit,
    })}`,
    signal,
  );
}

export async function fetchMetricsSeries(
  label: string,
  opts: { window: MetricWindow; kind?: string; span?: string; offset?: number },
  signal?: AbortSignal,
): Promise<MetricsSeriesResponse> {
  return apiGet<MetricsSeriesResponse>(
    `/api/metrics/series${qs({
      label,
      window: opts.window,
      kind: opts.kind,
      span: opts.span,
      offset: offsetParam(opts.offset),
    })}`,
    signal,
  );
}
