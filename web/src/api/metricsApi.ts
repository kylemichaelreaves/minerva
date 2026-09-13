import { apiGet } from "~/api/client";

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

export interface MetricsSummaryResponse {
  window: string;
  since: number;
  until: number;
  rows: MetricsSummaryRow[];
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

export async function fetchMetricsSummary(
  window: MetricWindow,
  label?: string,
  signal?: AbortSignal,
): Promise<MetricsSummaryResponse> {
  const qs = new URLSearchParams({ window });
  if (label) qs.set("label", label);
  return apiGet<MetricsSummaryResponse>(`/api/metrics/summary?${qs}`, signal);
}

export async function fetchMetricsSeries(
  label: string,
  opts: { window: MetricWindow; kind?: string; span?: string },
  signal?: AbortSignal,
): Promise<MetricsSeriesResponse> {
  const qs = new URLSearchParams({ label, window: opts.window });
  if (opts.kind) qs.set("kind", opts.kind);
  if (opts.span) qs.set("span", opts.span);
  return apiGet<MetricsSeriesResponse>(`/api/metrics/series?${qs}`, signal);
}
