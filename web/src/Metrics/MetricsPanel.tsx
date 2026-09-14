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
// Exported so a unit test can hit the `String(err)` branch directly —
// going through a resource never can, since `castError` normalizes every
// rejection into an `Error` before `.error` is ever read.
export function errorMessage(err: unknown): string {
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

  // The unlabeled summary is genuinely dual-purpose, and the two halves
  // must not be confused (found in review): it carries ONE row per
  // route for a plain request (`kind: "total"`, `span: ""`) but TWO for
  // a streaming route — a second `kind: "ttfe"` row at the same
  // `span: ""` (`store.py`'s `summary()`, unlabeled branch, filters on
  // `span = ''` only, with no `kind` filter). Rendering every row
  // un-filtered would list a streaming route twice with different
  // numbers and no column saying why. `summaryRows` is the raw fetch;
  // `rows` (the leaderboard) keeps only the `total` half so each route
  // appears exactly once.
  const summaryRows = createMemo<MetricsSummaryRow[]>(
    () => valueUnlessErrored(summary)?.rows ?? [],
  );

  const rows = createMemo<MetricsSummaryRow[]>(() =>
    // Sort here rather than trust the endpoint's own ordering — the
    // panel's contract with its caller is "slowest first" regardless of
    // what the backend happens to send.
    [...summaryRows().filter((r) => r.kind === "total")].sort((a, b) => b.p95_ms - a.p95_ms),
  );

  // `selectedLabel` doubles as the `createResource` source for both the
  // sub-span breakdown and (below) the trend chart. Solid skips the
  // fetcher entirely when a source accessor returns a falsy value, so
  // while nothing is selected these never run — which is the guard the
  // brief calls for, though not for the reason an earlier version of
  // this comment gave. `qs()` drops an empty value, so an empty `label`
  // never reaches the query string at all, and `_handle_metrics_series`
  // answers a label-less request with 400 (`handlers/metrics.py`). The
  // cost of firing anyway is therefore a guaranteed-failing fetch and a
  // spurious error banner on first render, before the reader has picked
  // a route — not the silent whole-table query this used to claim.
  const detailSource = (): { label: string; w: MetricWindow } | undefined => {
    const label = selectedLabel();
    return label ? { label, w: win() } : undefined;
  };

  const [detail] = createResource(detailSource, (src) => fetchMetricsSummary(src.w, src.label));

  // The trend chart's source ALSO depends on `spanKind`: unlike the
  // sub-span breakdown (labeled query, always `kind: "total"` — a
  // sub-span has no ttfe variant), the chart is the whole-request
  // series, and the backend defaults `kind` to `"total"` when it's
  // omitted (`handlers/metrics.py`). Without threading the toggle
  // through here, switching to "TTFE" would relabel the same total-
  // latency chart rather than actually change what it shows.
  const seriesSource = ():
    { label: string; w: MetricWindow; kind: "total" | "ttfe" } | undefined => {
    const label = selectedLabel();
    return label ? { label, w: win(), kind: spanKind() } : undefined;
  };
  const [series] = createResource(seriesSource, (src) =>
    fetchMetricsSeries(src.label, { window: src.w, kind: src.kind }),
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

  // Sub-span rows (the labeled query, `span != ''`) are ALWAYS
  // `kind: "total"` — the recorder never tags a sub-span `ttfe`
  // (`recorder.py`) — so this table is never filtered by `spanKind`;
  // there is nothing for the toggle to filter here.
  const detailRows = createMemo<MetricsSummaryRow[]>(() => valueUnlessErrored(detail)?.rows ?? []);
  // The toggle only makes sense — and only appears — when the selected
  // route's UNLABELED rows include a `ttfe` measurement (a streaming
  // route); most routes never do. Read from `summaryRows`, not
  // `detailRows` — the labeled query can't produce a `ttfe` row at all,
  // so deriving this from the drill-down could never be true.
  const hasTtfe = createMemo(() =>
    summaryRows().some((r) => r.label === selectedLabel() && r.kind === "ttfe"),
  );
  const seriesPoints = createMemo(() => valueUnlessErrored(series)?.points ?? []);
  // The chart labels its x-axis from this: the server buckets daily for
  // `7d`/`30d`/`all`, where an HH:MM tick is always `00:00`. 0 while the
  // fetch is in flight or errored, which reads as "sub-daily" — the same
  // thing an empty chart shows anyway.
  const seriesBucketSeconds = createMemo(() => valueUnlessErrored(series)?.bucket_seconds ?? 0);

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
                {/* The toggle only affects the trend chart below — the
                    sub-span breakdown has no ttfe variant to switch to. */}
                <span class="metrics-note">trend chart only</span>
              </Show>
            </div>

            <Show when={seriesFailed()}>
              <div class="metrics-error" role="alert">
                Couldn't load the trend chart: {errorMessage(series.error)}
              </div>
            </Show>
            {/* Chart XOR banner: `seriesPoints()` is `[]` on error too (the
                same `valueUnlessErrored` guard), and `TimeSeriesChart`
                renders its own "No data" for an empty array — showing both
                read as two contradictory explanations for the same blank
                chart. A loading state sits alongside for the same reason
                the leaderboard has one: without it, every selection (and
                every toggle flip) flashes "No data" while the fetch is
                in flight rather than looking like it's doing something. */}
            <Show when={!seriesFailed()}>
              <Show
                when={!series.loading}
                fallback={<div class="metrics-loading">Loading trend…</div>}
              >
                <TimeSeriesChart points={seriesPoints()} bucketSeconds={seriesBucketSeconds()} />
              </Show>
            </Show>

            <Show when={detailFailed()}>
              <div class="metrics-error" role="alert">
                Couldn't load the breakdown: {errorMessage(detail.error)}
              </div>
            </Show>

            <Show when={!detailFailed()}>
              <Show
                when={!detail.loading}
                fallback={<div class="metrics-loading">Loading breakdown…</div>}
              >
                {/* Only three code paths are instrumented, so most routes
                    have no sub-spans at all. Rendering the table regardless
                    left a bare "Span Count p50 p95 p99" header under the
                    chart labelling nothing, directly above the route
                    table's near-identical header. A header with no rows
                    beneath it is not a table. */}
                <Show when={detailRows().length > 0}>
                  <table class="metrics-subspan-table" aria-label="Sub-span breakdown">
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
                      <For each={detailRows()}>
                        {(row) => (
                          <tr>
                            <td>
                              {row.span}
                              {/* Two things about llm_call that are correct but easy
                                to misread, called out where they would mislead.
                                Its count and percentiles are PER ATTEMPT — the LLM
                                client retries, and every attempt records its own
                                row. And the span closes when the LLM's response
                                HEADERS arrive (`llm.py`), so body and stream
                                consumption fall outside it: on the chat route the
                                breakdown will not add up to `total`. */}
                              <Show when={row.span === "llm_call"}>
                                <span class="metrics-note">
                                  {" "}
                                  (per attempt, not per request; measured to response headers, so
                                  streamed body time is excluded)
                                </span>
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
                </Show>
              </Show>
            </Show>
          </section>
        )}
      </Show>

      <Show when={summaryFailed()}>
        <div class="metrics-error" role="alert">
          Couldn't load metrics: {errorMessage(summary.error)}
        </div>
      </Show>

      <Show when={!summaryFailed()}>
        <Show when={!summary.loading} fallback={<div class="metrics-loading">Loading…</div>}>
          <Show
            when={rows().length > 0}
            fallback={
              <div class="metrics-empty" role="status">
                No requests recorded in this window.
              </div>
            }
          >
            <div class="metrics-table-wrap">
              <table class="metrics-table" aria-label="Requests by route">
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
            </div>
          </Show>
        </Show>
      </Show>
    </div>
  );
}
