// Request-timing observability surface (#581, redesigned in #600).
//
// The first version answered "what are the percentiles?"; an operator
// opens this page asking "is anything wrong?". So the list is ordered by
// severity, the conclusion is stated in one recomputable sentence, and
// the detail pane sits beside the list rather than above it.
//
// This file owns resources, selection and composition only. Everything
// it renders lives in `RouteList`, `RouteDetail`, `StatTiles`,
// `SpanWaterfall` and the pure `severity` module — split up because
// Sonar's maintainability gate grades new code on cognitive complexity
// per function, and #559 showed that adding to an already-dense function
// fails it at an A rating while `check-diff-coverage` stays green and
// nothing local warns.

import { For, Show, createMemo, createResource, createSignal, type Resource } from "solid-js";

import { MetricsHealthBanner } from "./MetricsHealthBanner";
import { RequestLedger } from "./RequestLedger";
import {
  METRIC_WINDOWS,
  fetchMetricsSeries,
  fetchMetricsSummary,
  type MetricWindow,
  type MetricsSummaryRow,
} from "~/api/metricsApi";
import { RouteDetail, type SpanKind } from "~/Metrics/RouteDetail";
import { RouteList } from "~/Metrics/RouteList";
import { summarise } from "~/Metrics/severity";
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
   *  a bare `<MetricsPanel />` has no host to report to. */
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

const WINDOW_PROSE: Record<MetricWindow, string> = {
  "1h": "last hour",
  "6h": "last 6 hours",
  "24h": "last 24 hours",
  "7d": "last 7 days",
  "30d": "last 30 days",
  all: "all time",
};

/** A resource's `.error`/`.loading` accessors are always safe to read;
 *  the accessor itself (calling `res()`) rethrows once the resource has
 *  errored (so an `ErrorBoundary` above can catch it). This panel wants
 *  its OWN inline message instead of handing the error up to the surface
 *  boundary and blanking the whole page, so every read of a resource's
 *  value goes through this guard rather than calling the accessor. */
function valueUnlessErrored<T>(res: Resource<T>): T | undefined {
  if (res.error !== undefined) return undefined;
  return res();
}

/** The rendered message for a failed resource, or `undefined` while it
 *  has not failed. Solid types `.error` as `any` in its errored-state
 *  variant, so narrowing it to `string | undefined` here keeps that `any`
 *  from reaching a typed JSX prop. */
function errorTextOf(res: Resource<unknown>): string | undefined {
  if (res.error === undefined) return undefined;
  return errorMessage(res.error);
}

export function MetricsPanel(props: MetricsPanelProps) {
  const win = (): MetricWindow => props.window ?? "24h";
  // Which `kind` of the selected route to display. Local UI state, not
  // controlled: it has no URL representation and resets on every new
  // selection so a stale TTFE view from a previous route doesn't linger
  // under a route that has none.
  const [spanKind, setSpanKind] = createSignal<SpanKind>("total");
  // "The reader closed the detail pane", as distinct from "the reader has
  // not chosen yet". Without it `selectedLabel`'s fallback to
  // `defaultLabel` re-selects the worst route the instant the back button
  // clears it, and the button does nothing at all.
  const [dismissed, setDismissed] = createSignal(false);

  const selectWindow = (w: MetricWindow) => {
    props.onNavigate?.({ window: w, label: props.label });
  };

  const selectLabel = (label: string | undefined) => {
    setSpanKind("total");
    setDismissed(label === undefined);
    props.onNavigate?.({ window: win(), label });
  };

  const [view, setView] = createSignal<"routes" | "requests">("routes");
  const [summary] = createResource(win, (w) => fetchMetricsSummary(w));
  // The baseline. `offset: 1` is the window immediately before this one,
  // which is why it needed a backend parameter at all: before it, the
  // only available comparison was a WIDER window — this one plus more,
  // where a spike inside the current window also moves the number being
  // compared against.
  //
  // `all` is skipped rather than requested: it starts at the epoch and
  // has no previous window, and the endpoint answers a non-zero offset
  // there with a 400. Returning undefined stops Solid running the
  // fetcher at all, so the tiles show an em dash instead.
  const priorSource = (): MetricWindow | undefined => (win() === "all" ? undefined : win());
  const [prior] = createResource(priorSource, (w) => fetchMetricsSummary(w, { offset: 1 }));

  // The unlabeled summary is dual-purpose, and the two halves must not be
  // confused: it carries ONE row per route for a plain request
  // (`kind: "total"`, `span: ""`) but TWO for a streaming route — a
  // second `kind: "ttfe"` row at the same `span: ""` (`store.py`'s
  // `summary()`, unlabeled branch, filters on `span = ''` only, with no
  // `kind` filter).
  const summaryRows = createMemo<MetricsSummaryRow[]>(
    () => valueUnlessErrored(summary)?.rows ?? [],
  );
  const priorRows = createMemo<MetricsSummaryRow[]>(() => valueUnlessErrored(prior)?.rows ?? []);

  // `summarise` keeps only the `kind === "total"` half, so a streaming
  // route appears once in the list rather than twice with different
  // numbers and no column saying why.
  const graded = createMemo(() => summarise(summaryRows(), priorRows()));
  const entries = createMemo(() => graded().entries);
  const totalRequests = createMemo(() => entries().reduce((sum, e) => sum + e.row.count, 0));

  // The selected route defaults to the worst one, DERIVED rather than
  // written to the URL: a bare `#/metrics` lands on the thing that needs
  // attention without rewriting the reader's address bar behind their
  // back. `onNavigate` still fires only on an explicit click.
  const bySlowest = createMemo(() => [...entries()].sort((a, b) => b.row.p95_ms - a.row.p95_ms));
  const defaultLabel = createMemo(
    () => bySlowest().find((e) => e.severity === "bad")?.row.label ?? bySlowest()[0]?.row.label,
  );
  const selectedLabel = (): string | undefined => {
    if (props.label !== undefined) return props.label;
    return dismissed() ? undefined : defaultLabel();
  };

  const selectedEntry = createMemo(() => entries().find((e) => e.row.label === selectedLabel()));
  // The ttfe half of the same route, for the "Time to first event" tab.
  // Only a streaming route has one, which is also what makes the tabs
  // appear at all.
  const rowFor = (rows: MetricsSummaryRow[], kind: SpanKind) =>
    rows.find((r) => r.label === selectedLabel() && r.kind === kind);
  const ttfeRow = createMemo(() => rowFor(summaryRows(), "ttfe"));

  // The tab drives the tiles AND the chart. The first version relabelled
  // only the chart and carried a "trend chart only" note admitting it;
  // the ttfe row has its own count, error rate and percentiles, so there
  // was never a reason for the tiles not to follow.
  const activeRow = createMemo(() => (spanKind() === "ttfe" ? ttfeRow() : selectedEntry()?.row));
  const activePrior = createMemo(() => rowFor(priorRows(), spanKind()));

  // Solid skips a fetcher entirely when its source accessor returns a
  // falsy value, so these never run while nothing is selected. `qs()`
  // drops an empty value, and `_handle_metrics_series` answers a
  // label-less request with 400 (`handlers/metrics.py`), so firing anyway
  // would mean a guaranteed-failing fetch and a spurious error banner.
  const detailSource = (): { label: string; w: MetricWindow } | undefined => {
    const label = selectedLabel();
    return label ? { label, w: win() } : undefined;
  };
  const [detail] = createResource(detailSource, (src) =>
    fetchMetricsSummary(src.w, { label: src.label }),
  );

  const seriesSource = (): { label: string; w: MetricWindow; kind: SpanKind } | undefined => {
    const label = selectedLabel();
    return label ? { label, w: win(), kind: spanKind() } : undefined;
  };
  const [series] = createResource(seriesSource, (src) =>
    fetchMetricsSeries(src.label, { window: src.w, kind: src.kind }),
  );

  // Sub-span rows (the labeled query, `span != ''`) are ALWAYS
  // Passed through UNFILTERED, and that is now load-bearing: since CPU
  // entered the aggregate the drill-down returns a `kind: "cpu"` row
  // alongside each wall row, and `SpanWaterfall` needs both — it splits
  // them itself (`wallRows` / `cpuByName`) so one span is drawn once with
  // its CPU share beside it.
  //
  // This comment used to say the list "is never filtered by `spanKind`"
  // because the recorder only ever emitted one kind per span. That stopped
  // being true when `kind: "cpu"` was added; filtering still does not happen
  // HERE, but it does happen, and the reason changed.
  const detailRows = createMemo<MetricsSummaryRow[]>(() => valueUnlessErrored(detail)?.rows ?? []);
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
        <span class="metrics-sub">
          {WINDOW_PROSE[win()]} · {totalRequests().toLocaleString()} requests
        </span>
        <div class="metrics-windows" role="group" aria-label="Time window">
          <For each={METRIC_WINDOWS}>
            {(w) => (
              <button
                type="button"
                classList={{ "metrics-window-btn": true, active: win() === w }}
                aria-pressed={win() === w}
                onClick={() => selectWindow(w)}
              >
                {WINDOW_LABELS[w]}
              </button>
            )}
          </For>
        </div>
      </header>

      {/* One recomputable sentence, never prose. Hidden while the fetch
          is in flight or failed: a verdict over zero rows would read "No
          requests recorded in this window", which is a claim about the
          data rather than about the fetch. */}
      {/* Above the verdict, not instead of it: the verdict describes the
          routes, this describes whether the numbers under it can be trusted
          at all. Renders nothing when healthy, so its presence is the
          signal (#618). */}
      {/* `summary.error &&` first, deliberately: reading an errored Solid
          resource RE-THROWS, so `summary()?.health` alone takes down the
          whole error path — which is the one path where the page most needs
          to still render. */}
      <MetricsHealthBanner health={summary.error ? undefined : summary()?.health} />

      <Show when={!summary.loading && errorTextOf(summary) === undefined}>
        <p class="metrics-verdict">
          <span class={`metrics-dot ${graded().verdict.severity}`} aria-hidden="true" />
          <span>
            <b>{graded().verdict.headline}</b> {graded().verdict.detail}
          </span>
        </p>
      </Show>

      {/* A view toggle rather than a second hash route: `readRoute` is already
          over the Sonar complexity limit (#589) and grows a branch per
          surface, so adding one here would make that worse for no gain. */}
      <div class="metrics-views" role="group" aria-label="Metrics view">
        <button type="button" aria-pressed={view() === "routes"} onClick={() => setView("routes")}>
          Routes
        </button>
        <button
          type="button"
          aria-pressed={view() === "requests"}
          onClick={() => setView("requests")}
        >
          Requests
        </button>
      </div>

      <Show when={view() === "requests"}>
        <RequestLedger window={win()} />
      </Show>

      <Show when={view() === "routes"}>
        <main classList={{ "metrics-split": true, "detail-open": selectedEntry() !== undefined }}>
          <RouteList
            entries={entries()}
            loading={summary.loading}
            errorText={errorTextOf(summary)}
            selectedLabel={selectedLabel()}
            onSelect={selectLabel}
          />

          <Show when={selectedEntry()}>
            {(entry) => (
              <RouteDetail
                label={entry().row.label}
                method={entry().row.method}
                row={activeRow()}
                prior={activePrior()}
                windowLabel={WINDOW_LABELS[win()]}
                spanKind={spanKind()}
                onSpanKind={setSpanKind}
                hasTtfe={ttfeRow() !== undefined}
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
        </main>
      </Show>
    </div>
  );
}
