// Request-timing observability surface (#581). Composes the two read
// endpoints behind `metricsApi` and the trend chart into one page: a
// whole-request leaderboard, slowest first, that drills into a per-route
// sub-span breakdown + trend chart.
//
// This file owns resources, selection and composition only. The two
// halves it renders live in `RouteList.tsx` and `RouteDetail.tsx` —
// split out under #600 because Sonar's maintainability gate grades new
// code on cognitive complexity per function, and #559 showed that adding
// to an already-dense function fails it at an A rating while
// `check-diff-coverage` stays green and nothing local warns.

import { For, Show, createMemo, createResource, createSignal, type Resource } from "solid-js";
import {
  METRIC_WINDOWS,
  fetchMetricsSeries,
  fetchMetricsSummary,
  type MetricWindow,
  type MetricsSummaryRow,
} from "~/api/metricsApi";
import { RouteDetail, type SpanKind } from "~/Metrics/RouteDetail";
import { RouteList } from "~/Metrics/RouteList";
import { errorMessage } from "~/utils/util";
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

/** The rendered message for a failed resource, or `undefined` while it
 *  has not failed. Solid types `.error` as `any` in its errored-state
 *  variant (a discriminated union whose errored branch is untyped), so
 *  narrowing it to `string | undefined` here keeps that `any` from
 *  reaching a typed JSX prop — the case `no-unsafe-assignment` exists
 *  to catch. */
function errorTextOf(res: Resource<unknown>): string | undefined {
  if (res.error === undefined) return undefined;
  return errorMessage(res.error);
}

export function MetricsPanel(props: MetricsPanelProps) {
  const win = (): MetricWindow => props.window ?? "24h";
  const selectedLabel = (): string | undefined => props.label;
  // Which `kind` of the selected route's rows to display. This one IS
  // local UI state, not controlled — it has no URL representation and
  // resets on every new selection so a stale TTFE view from a previous
  // route doesn't linger under a route that has none.
  const [spanKind, setSpanKind] = createSignal<SpanKind>("total");

  const selectWindow = (w: MetricWindow) => {
    props.onNavigate?.({ window: w, label: selectedLabel() });
  };

  const selectLabel = (label: string | undefined) => {
    setSpanKind("total");
    props.onNavigate?.({ window: win(), label });
  };

  const [summary] = createResource(win, (w) => fetchMetricsSummary(w));

  // The unlabeled summary is genuinely dual-purpose, and the two halves
  // must not be confused: it carries ONE row per route for a plain
  // request (`kind: "total"`, `span: ""`) but TWO for a streaming route
  // — a second `kind: "ttfe"` row at the same `span: ""` (`store.py`'s
  // `summary()`, unlabeled branch, filters on `span = ''` only, with no
  // `kind` filter). Rendering every row un-filtered would list a
  // streaming route twice with different numbers and no column saying
  // why. `summaryRows` is the raw fetch; `rows` (the leaderboard) keeps
  // only the `total` half so each route appears exactly once.
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
  // brief calls for. `qs()` drops an empty value, so an empty `label`
  // never reaches the query string at all, and `_handle_metrics_series`
  // answers a label-less request with 400 (`handlers/metrics.py`). The
  // cost of firing anyway would therefore be a guaranteed-failing fetch
  // and a spurious error banner on first render, before the reader has
  // picked a route.
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
  const seriesSource = (): { label: string; w: MetricWindow; kind: SpanKind } | undefined => {
    const label = selectedLabel();
    return label ? { label, w: win(), kind: spanKind() } : undefined;
  };
  const [series] = createResource(seriesSource, (src) =>
    fetchMetricsSeries(src.label, { window: src.w, kind: src.kind }),
  );

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
          <RouteDetail
            label={label()}
            spanKind={spanKind()}
            onSpanKind={setSpanKind}
            hasTtfe={hasTtfe()}
            onBack={() => selectLabel(undefined)}
            seriesPoints={seriesPoints()}
            seriesBucketSeconds={seriesBucketSeconds()}
            seriesLoading={series.loading}
            seriesErrorText={errorTextOf(series)}
            detailRows={detailRows()}
            detailLoading={detail.loading}
            detailErrorText={errorTextOf(detail)}
          />
        )}
      </Show>

      <RouteList
        rows={rows()}
        loading={summary.loading}
        errorText={errorTextOf(summary)}
        selectedLabel={selectedLabel()}
        onSelect={selectLabel}
      />
    </div>
  );
}
