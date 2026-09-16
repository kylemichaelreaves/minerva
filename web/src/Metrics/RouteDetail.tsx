// The selected route's detail pane (#600): headline tiles, trend chart,
// and the sub-span waterfall.
//
// Takes resource STATE as plain props (`seriesLoading`, `seriesErrorText`,
// ...) rather than the `Resource` objects themselves. Solid's `Resource<T>`
// types `.error` as `any` in its errored-state variant, so reading it
// straight into a JSX prop is exactly the "assigning `any` into a typed
// slot" case `no-unsafe-assignment` exists to catch. Narrowing once, in
// the owner, keeps that cast in one place and leaves this component
// mountable from a test with no resources at all.

import { Show } from "solid-js";
import type { MetricsSeriesPoint, MetricsSummaryRow } from "~/api/metricsApi";
import { SpanWaterfall } from "~/Metrics/SpanWaterfall";
import { StatTiles } from "~/Metrics/StatTiles";
import { TimeSeriesChart } from "~/Metrics/TimeSeriesChart";

export type SpanKind = "total" | "ttfe";

const TAB_LABELS: Record<SpanKind, string> = {
  total: "Total",
  ttfe: "Time to first event",
};

export interface RouteDetailProps {
  label: string;
  method: string;
  /** The summary row for the ACTIVE tab. Absent when the selected route
   *  recorded nothing in this window — a deep link into a route that has
   *  since gone quiet, or a window narrow enough to exclude it. */
  row?: MetricsSummaryRow;
  /** The same row one window earlier, when the backend could supply it. */
  prior?: MetricsSummaryRow;
  /** Rendered into the tiles' delta captions, e.g. "6h". */
  windowLabel: string;

  spanKind: SpanKind;
  onSpanKind: (kind: SpanKind) => void;
  /** Whether the route recorded a `kind: "ttfe"` row — i.e. it streams.
   *  Most routes do not, and the tabs only appear when there is a second
   *  thing to show. */
  hasTtfe: boolean;
  /** Returns to the list. Desktop shows both panes at once and hides
   *  this; the mobile layout stacks them and needs it. */
  onBack: () => void;

  seriesPoints: MetricsSeriesPoint[];
  seriesBucketSeconds: number;
  seriesLoading: boolean;
  seriesErrorText?: string;

  detailRows: MetricsSummaryRow[];
  detailLoading: boolean;
  detailErrorText?: string;
}

function Tab(props: { kind: SpanKind; active: SpanKind; onPick: (k: SpanKind) => void }) {
  return (
    <button
      type="button"
      classList={{ active: props.active === props.kind }}
      aria-pressed={props.active === props.kind}
      onClick={() => props.onPick(props.kind)}
    >
      {TAB_LABELS[props.kind]}
    </button>
  );
}

export function RouteDetail(props: RouteDetailProps) {
  // "streaming" is derived, not recorded: a route that produced a ttfe
  // row is one that streamed. The design's companion "cached" badge has
  // no equivalent — nothing records cache hits — so it is not here.
  const meta = (): string => {
    const parts = props.hasTtfe ? ["streaming"] : [];
    const count = props.row?.count;
    if (count !== undefined) parts.push(`${count.toLocaleString()} requests`);
    return parts.join(" · ");
  };

  return (
    <section class="metrics-detail">
      <div class="metrics-detail-head">
        <button type="button" class="metrics-back" onClick={() => props.onBack()}>
          ← All routes
        </button>
        <h2>{props.label}</h2>
        <span class="metrics-method">{props.method}</span>
        <span class="metrics-note">{meta()}</span>
        <Show when={props.hasTtfe}>
          <div class="metrics-tabs" role="group" aria-label="Metric">
            <Tab kind="total" active={props.spanKind} onPick={props.onSpanKind} />
            <Tab kind="ttfe" active={props.spanKind} onPick={props.onSpanKind} />
          </div>
        </Show>
      </div>

      <Show
        when={props.row}
        fallback={
          <p class="metrics-empty-inline" role="status">
            This route recorded nothing in the selected window.
          </p>
        }
      >
        {(row) => <StatTiles row={row()} prior={props.prior} windowLabel={props.windowLabel} />}
      </Show>

      <section class="metrics-card metrics-card-chart">
        {/* No legend here: `TimeSeriesChart` renders its own, keyed to
            the same `--metric-p50`/`--metric-p95` tokens. A second copy
            in this head would be two elements to keep in step and a
            duplication-gate hit for nothing (#254). */}
        <div class="metrics-card-head">
          <span class="metrics-card-label">Latency over time</span>
        </div>

        <Show when={props.seriesErrorText}>
          {(text) => (
            <div class="metrics-error" role="alert">
              Couldn't load the trend chart: {text()}
            </div>
          )}
        </Show>
        {/* Chart XOR banner: `seriesPoints` is `[]` on error too, and
            `TimeSeriesChart` renders its own "No data" for an empty array —
            showing both reads as two contradictory explanations for the same
            blank chart. A loading state sits alongside for the same reason
            the list has one: without it, every selection (and every tab
            flip) flashes "No data" while the fetch is in flight rather than
            looking like it is doing something. */}
        <Show when={props.seriesErrorText === undefined}>
          <Show
            when={!props.seriesLoading}
            fallback={<div class="metrics-loading">Loading trend…</div>}
          >
            <TimeSeriesChart
              points={props.seriesPoints}
              bucketSeconds={props.seriesBucketSeconds}
            />
          </Show>
        </Show>
      </section>

      <Show when={props.detailErrorText}>
        {(text) => (
          <div class="metrics-error" role="alert">
            Couldn't load the breakdown: {text()}
          </div>
        )}
      </Show>

      <Show when={props.detailErrorText === undefined}>
        <Show
          when={!props.detailLoading}
          fallback={<div class="metrics-loading">Loading breakdown…</div>}
        >
          <SpanWaterfall
            rows={props.detailRows}
            totalP95={props.row?.p95_ms ?? 0}
            spanKind={props.spanKind}
          />
        </Show>
      </Show>
    </section>
  );
}
