import { apiGet, qs } from "~/api/client";

export const METRIC_WINDOWS = ["1h", "6h", "24h", "7d", "30d", "all"] as const;
export type MetricWindow = (typeof METRIC_WINDOWS)[number];

/** Whole-request timing, or a named step inside one when `span` is set. */
export interface MetricsSummaryRow {
  label: string;
  method: string;
  /** `"cpu"` joined the two originals when CPU time entered the aggregate.
   *  The labeled drill-down filters on `span != ''` and NOT on kind, so a
   *  consumer that does not filter will draw every span twice. */
  kind: "total" | "ttfe" | "cpu";
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
  /** Wall time. Exact. */
  ms: number;
  /** CPU time on the request's thread. **Absent means not measured**, which is
   *  a different answer from a measured zero — `time.thread_time` is not on
   *  every platform, and rows written before Phase 2 have no value at all.
   *
   *  On a streaming `llm_call` this is an upper bound: the span wraps a
   *  generator that yields across the SSE loop, so the consumer's work on the
   *  same thread lands inside it. Thread-scoped CPU cannot separate them. */
  cpu_ms?: number;
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
  /** CPU for the whole request. `null` means not measured — distinguish it
   *  from 0, which means measured and idle. Present on every request, unlike
   *  phase CPU: only 0.22% of requests carry a phase at all. */
  cpu_ms: number | null;
  /** Database time, summed over every statement the request issued, measured
   *  at the connection layer rather than by a span at a call site.
   *
   *  This is usually most of the request: `works list` measured 240.5 ms of
   *  SQLite inside a 241.3 ms request — 99.7%, in a single statement. `null`
   *  means not measured (a row written before Phase 3), which is a different
   *  answer from 0. */
  sqlite_ms: number | null;
  sqlite_queries: number | null;
}

/** Keyset cursor. Both halves are required: `at` is a float from
 *  `time.time()` and two requests can share one, so resuming from `at` alone
 *  would skip whichever sat on the boundary. */
export interface MetricsRequestsCursor {
  at: number;
  id: string;
}

export interface MetricsRequestsResponse {
  window: string;
  since: number;
  until: number;
  rows: MetricsRequestRow[];
  /** The limit actually applied after clamping, not the one requested. */
  limit: number;
  has_more: boolean;
  /** Handed back rather than rebuilt by the client from the last row —
   *  reconstructing it would couple every caller to the ordering, which is
   *  what keyset pagination exists to hide. */
  next_before: MetricsRequestsCursor | null;
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
  before?: MetricsRequestsCursor;
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
      before_at: opts.before?.at,
      before_id: opts.before?.id,
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
