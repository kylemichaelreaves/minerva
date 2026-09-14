// The selected route's drill-down, extracted from `MetricsPanel` (#600):
// the TTFE toggle, the trend chart, and the sub-span breakdown.
//
// Takes resource STATE as plain props (`seriesLoading`, `seriesErrorText`,
// …) rather than the `Resource` objects themselves. Solid's `Resource<T>`
// types `.error` as `any` in its errored-state variant, so reading it
// straight into a JSX prop is exactly the "assigning `any` into a typed
// slot" case `no-unsafe-assignment` exists to catch. Narrowing once, in
// the owner, keeps that cast in one place and leaves this component
// mountable from a test with no resources at all.

import { For, Show } from "solid-js";
import type { MetricsSummaryRow, MetricsSeriesPoint } from "~/api/metricsApi";
import { TimeSeriesChart } from "~/Metrics/TimeSeriesChart";

export type SpanKind = "total" | "ttfe";

export interface RouteDetailProps {
  label: string;
  spanKind: SpanKind;
  onSpanKind: (kind: SpanKind) => void;
  /** Whether the selected route recorded a `kind: "ttfe"` row — i.e. it
   *  streams. Most routes do not, and the toggle only appears when it
   *  has something to toggle to. */
  hasTtfe: boolean;
  onBack: () => void;

  seriesPoints: MetricsSeriesPoint[];
  seriesBucketSeconds: number;
  seriesLoading: boolean;
  seriesErrorText?: string;

  detailRows: MetricsSummaryRow[];
  detailLoading: boolean;
  detailErrorText?: string;
}

export function RouteDetail(props: RouteDetailProps) {
  return (
    <section class="metrics-detail">
      <div class="metrics-detail-head">
        <h2>{props.label}</h2>
        <button type="button" class="metrics-back" onClick={() => props.onBack()}>
          ← All routes
        </button>
        <Show when={props.hasTtfe}>
          <div class="metrics-kind-toggle" role="group" aria-label="Metric">
            <button
              type="button"
              classList={{ active: props.spanKind === "total" }}
              onClick={() => props.onSpanKind("total")}
            >
              Total
            </button>
            <button
              type="button"
              classList={{ active: props.spanKind === "ttfe" }}
              onClick={() => props.onSpanKind("ttfe")}
            >
              TTFE
            </button>
          </div>
          {/* The toggle only affects the trend chart below — the
              sub-span breakdown has no ttfe variant to switch to. */}
          <span class="metrics-note">trend chart only</span>
        </Show>
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
          the leaderboard has one: without it, every selection (and every
          toggle flip) flashes "No data" while the fetch is in flight
          rather than looking like it's doing something. */}
      <Show when={props.seriesErrorText === undefined}>
        <Show
          when={!props.seriesLoading}
          fallback={<div class="metrics-loading">Loading trend…</div>}
        >
          <TimeSeriesChart points={props.seriesPoints} bucketSeconds={props.seriesBucketSeconds} />
        </Show>
      </Show>

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
          {/* Only three code paths are instrumented, so most routes have
              no sub-spans at all. Rendering the table regardless left a
              bare "Span Count p50 p95 p99" header under the chart
              labelling nothing, directly above the route table's
              near-identical header. A header with no rows beneath it is
              not a table. */}
          <Show when={props.detailRows.length > 0}>
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
                <For each={props.detailRows}>
                  {(row) => (
                    <tr>
                      <td>
                        {row.span}
                        {/* Two things about llm_call that are correct but easy to
                            misread, called out where they would mislead. Its count
                            and percentiles are PER ATTEMPT — the LLM client retries,
                            and every attempt records its own row. And the span closes
                            when the LLM's response HEADERS arrive (`llm.py`), so body
                            and stream consumption fall outside it: on the chat route
                            the breakdown will not add up to `total` (#586). */}
                        <Show when={row.span === "llm_call"}>
                          <span class="metrics-note">
                            {" "}
                            (per attempt, not per request; measured to response headers, so streamed
                            body time is excluded)
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
  );
}
