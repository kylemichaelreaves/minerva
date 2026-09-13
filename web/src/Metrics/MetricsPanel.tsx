// Request-timing observability surface (#581). Composes the two read
// endpoints (Task 7) behind `metricsApi` (Task 8) and the trend chart
// (Task 8) into one page: a whole-request leaderboard, slowest first,
// that drills into a per-route sub-span breakdown + trend chart.
//
// Deliberately NOT built on `LeaderboardPanel` (Network's top-cited-works
// list, `~/Network/components/LeaderboardPanel.tsx`): that component
// renders a fixed author/work/sparkline row shape with no sort, no
// selection state, and no drill-down. This panel's rows are a real
// `<table>` (sortable by measured p95, clickable to select) over a
// different data shape entirely — the overlap is "a list of rows", not
// enough to share code without inventing an abstraction neither surface
// needs. Copying it wholesale would fail Sonar's ≤3% duplication gate at
// any coverage level regardless (#254).

import { For, Show, createMemo, createResource, createSignal, type Resource } from "solid-js";
import {
  METRIC_WINDOWS,
  fetchMetricsSeries,
  fetchMetricsSummary,
  type MetricWindow,
  type MetricsSummaryRow,
} from "~/api/metricsApi";
import { TimeSeriesChart } from "~/Metrics/TimeSeriesChart";
import "./metrics.css";

export interface MetricsPanelProps {
  /** Current window; defaults to 24h when absent. Fully controlled —
   *  same idiom as `Network`/`Refs`: the panel never owns this as local
   *  state, it reads the prop and reports the window the reader picked
   *  via `onNavigate` for a host route to feed back in. */
  window?: MetricWindow;
  /** Currently selected route label, if any (a `#/metrics?...&label=`
   *  deep link resolves here). Also fully controlled. */
  label?: string;
  /** Called with the panel's requested {window, label} whenever either
   *  changes, so a host route can mirror it into the URL. Optional —
   *  the brief's tests mount `<MetricsPanel />` bare, with no host to
   *  report to. */
  onNavigate?: (patch: { window: MetricWindow; label?: string }) => void;
}

const WINDOW_LABELS: Record<MetricWindow, string> = {
  "1h": "1h",
  "6h": "6h",
  "24h": "24h",
  "7d": "7d",
  "30d": "30d",
  all: "All time",
};

/** A resource's `.error`/`.loading` accessors are always safe to read;
 *  the accessor itself (calling `res()`) rethrows once the resource has
 *  errored (so an `ErrorBoundary` above can catch it). This panel wants
 *  its OWN inline message instead of handing the error up to the
 *  surface boundary and blanking the whole page, so every read of a
 *  resource's value goes through this guard rather than calling the
 *  accessor directly. */
function valueUnlessErrored<T>(res: Resource<T>): T | undefined {
  if (res.error !== undefined) return undefined;
  return res();
}

// The `String(err)` branch is defensive rather than reachable in
// practice: Solid's `createResource` runs every rejection through its
// own `castError` before it ever reaches `.error` — `new Error(typeof
// err === "string" ? err : "Unknown error", { cause: err })` — so
// `summary.error`/`detail.error`/`series.error` are always `Error`
// instances by the time they get here (a non-`Error` rejection, e.g.
// `Promise.reject("offline")`, still surfaces via `.message`, not this
// line). Kept anyway: `err`'s declared type is `unknown`, and a helper
// with that signature should not assume its caller's guarantee holds
// forever. Same defensive shape as `SurfaceErrorBoundary`'s `messageOf`.
function errorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  return String(err);
}

export function MetricsPanel(props: MetricsPanelProps) {
  const win = (): MetricWindow => props.window ?? "24h";
  const selectedLabel = (): string | undefined => props.label;
  // Which `kind` of the selected route's sub-span rows to display. This
  // one IS local UI state, not controlled — it has no URL representation
  // and resets on every new selection so a stale TTFE view from a
  // previous route doesn't linger under a route that has none.
  const [spanKind, setSpanKind] = createSignal<"total" | "ttfe">("total");

  const selectWindow = (w: MetricWindow) => {
    props.onNavigate?.({ window: w, label: selectedLabel() });
  };

  const selectLabel = (label: string | undefined) => {
    setSpanKind("total");
    props.onNavigate?.({ window: win(), label });
  };

  const [summary] = createResource(win, (w) => fetchMetricsSummary(w));

  const rows = createMemo<MetricsSummaryRow[]>(() => {
    const data = valueUnlessErrored(summary);
    // Sort here rather than trust the endpoint's own ordering — the
    // panel's contract with its caller is "slowest first" regardless of
    // what the backend happens to send.
    return [...(data?.rows ?? [])].sort((a, b) => b.p95_ms - a.p95_ms);
  });

  // `selectedLabel` doubles as both resources' `createResource` source.
  // Solid skips the fetcher entirely when a source accessor returns a
  // falsy value, so while nothing is selected these never run — which is
  // the guard the brief calls for: an empty `label` is silently dropped
  // from the query string by `qs()`, so calling `fetchMetricsSeries`
  // with one would issue a whole-table query that looks like a normal
  // request rather than an obvious bug.
  const detailSource = (): { label: string; w: MetricWindow } | undefined => {
    const label = selectedLabel();
    return label ? { label, w: win() } : undefined;
  };

  const [detail] = createResource(detailSource, (src) => fetchMetricsSummary(src.w, src.label));
  const [series] = createResource(detailSource, (src) =>
    fetchMetricsSeries(src.label, { window: src.w }),
  );

  // Solid's `Resource<T>` types `.error` as `any` in its errored-state
  // variant (it's a discriminated union across load states, and that
  // branch's `error` field is untyped). Reading it straight into a JSX
  // `when=` prop is exactly the "assigning `any` into a typed slot" case
  // `no-unsafe-assignment` exists to catch, so every check goes through
  // one of these boolean-typed wrappers instead.
  const summaryFailed = (): boolean => summary.error !== undefined;
  const detailFailed = (): boolean => detail.error !== undefined;
  const seriesFailed = (): boolean => series.error !== undefined;

  const detailRows = createMemo<MetricsSummaryRow[]>(() => valueUnlessErrored(detail)?.rows ?? []);
  // The toggle only makes sense — and only appears — when the selected
  // route actually recorded a `ttfe` measurement (a streaming route);
  // most routes never do.
  const hasTtfe = createMemo(() => detailRows().some((r) => r.kind === "ttfe"));
  const visibleDetailRows = createMemo(() => detailRows().filter((r) => r.kind === spanKind()));
  const seriesPoints = createMemo(() => valueUnlessErrored(series)?.points ?? []);

  return (
    <div class="metrics-panel">
      <header class="metrics-head">
        <h1>Request timing</h1>
        <div class="metrics-windows" role="group" aria-label="Time window">
          <For each={METRIC_WINDOWS}>
            {(w) => (
              <button
                type="button"
                classList={{ "metrics-window-btn": true, active: win() === w }}
                onClick={() => selectWindow(w)}
              >
                {WINDOW_LABELS[w]}
              </button>
            )}
          </For>
        </div>
      </header>

      <Show when={summaryFailed()}>
        <div class="metrics-error" role="alert">
          Couldn't load metrics: {errorMessage(summary.error)}
        </div>
      </Show>

      <Show when={!summaryFailed()}>
        <Show when={!summary.loading} fallback={<div class="metrics-loading">Loading…</div>}>
          <Show
            when={rows().length > 0}
            fallback={<div class="metrics-empty">No requests recorded in this window.</div>}
          >
            <table class="metrics-table">
              <thead>
                <tr>
                  <th>Route</th>
                  <th>Method</th>
                  <th>Count</th>
                  <th>p50</th>
                  <th>p95</th>
                  <th>p99</th>
                  <th>Errors</th>
                </tr>
              </thead>
              <tbody>
                <For each={rows()}>
                  {(row) => (
                    <tr
                      class="metrics-table-row"
                      classList={{ selected: selectedLabel() === row.label }}
                      onClick={() => selectLabel(row.label)}
                    >
                      <td data-testid="metrics-route-label">{row.label}</td>
                      <td>{row.method}</td>
                      <td>{row.count.toLocaleString()}</td>
                      <td>{Math.round(row.p50_ms)}</td>
                      <td>{Math.round(row.p95_ms)}</td>
                      <td>{Math.round(row.p99_ms)}</td>
                      <td>{(row.error_rate * 100).toFixed(1)}%</td>
                    </tr>
                  )}
                </For>
              </tbody>
            </table>
          </Show>
        </Show>
      </Show>

      <Show when={selectedLabel()}>
        {(label) => (
          <section class="metrics-detail">
            <div class="metrics-detail-head">
              <h2>{label()}</h2>
              <button type="button" class="metrics-back" onClick={() => selectLabel(undefined)}>
                ← All routes
              </button>
              <Show when={hasTtfe()}>
                <div class="metrics-kind-toggle" role="group" aria-label="Metric">
                  <button
                    type="button"
                    classList={{ active: spanKind() === "total" }}
                    onClick={() => setSpanKind("total")}
                  >
                    Total
                  </button>
                  <button
                    type="button"
                    classList={{ active: spanKind() === "ttfe" }}
                    onClick={() => setSpanKind("ttfe")}
                  >
                    TTFE
                  </button>
                </div>
              </Show>
            </div>

            <Show when={detailFailed()}>
              <div class="metrics-error" role="alert">
                Couldn't load the breakdown: {errorMessage(detail.error)}
              </div>
            </Show>

            <Show when={seriesFailed()}>
              <div class="metrics-error" role="alert">
                Couldn't load the trend chart: {errorMessage(series.error)}
              </div>
            </Show>

            <TimeSeriesChart points={seriesPoints()} />

            <table class="metrics-subspan-table">
              <thead>
                <tr>
                  <th>Span</th>
                  <th>Count</th>
                  <th>p50</th>
                  <th>p95</th>
                  <th>p99</th>
                </tr>
              </thead>
              <tbody>
                <For each={visibleDetailRows()}>
                  {(row) => (
                    <tr>
                      <td>
                        {row.span || "(whole request)"}
                        {/* llm_call's count and percentiles are PER ATTEMPT — the
                            LLM client retries, and every attempt records its own
                            row. Correct, but easy to misread as per-request, so
                            it's called out at the point it would mislead. */}
                        <Show when={row.span === "llm_call"}>
                          <span class="metrics-note"> (per attempt, not per request)</span>
                        </Show>
                      </td>
                      <td>{row.count.toLocaleString()}</td>
                      <td>{Math.round(row.p50_ms)}</td>
                      <td>{Math.round(row.p95_ms)}</td>
                      <td>{Math.round(row.p99_ms)}</td>
                    </tr>
                  )}
                </For>
              </tbody>
            </table>
          </section>
        )}
      </Show>
    </div>
  );
}
