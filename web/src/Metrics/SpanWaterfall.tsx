// "Where the time goes" for the selected route (#600): each recorded
// sub-span as a share of the whole request's p95.
//
// Replaces the sub-span table this surface shipped with. The table put
// five numeric columns under a header nearly identical to the route
// table's directly above it; the question a reader actually has here is
// proportional ("what dominates?"), which is a bar, not a column.

import { For, Show } from "solid-js";
import type { MetricsSummaryRow } from "~/api/metricsApi";
import type { SpanKind } from "~/Metrics/RouteDetail";
import { cpuVerdict } from "~/Metrics/cpu";

/** A span's p95 as a fraction of the route's. Verified against the
 *  source design's own fixture data, which carries both the millisecond
 *  values and the percentages it derived from them.
 *
 *  Deliberately NOT clamped: a sub-span is recorded per attempt while
 *  the total is per request, so a retried span can genuinely exceed the
 *  request it sits inside. That is information; only the bar width is
 *  clamped, so the figure can still print it. */
export function spanShare(spanP95: number, totalP95: number): number {
  if (totalP95 === 0) return 0;
  return spanP95 / totalP95;
}

export interface SpanWaterfallProps {
  /** Sub-span rows from the labeled summary, already p95-sorted by the
   *  server (`store.py`'s `summary()`). Do not re-sort. */
  rows: MetricsSummaryRow[];
  /** The whole request's p95, which every share is measured against. */
  totalP95: number;
  /** Which tab the detail pane is on. Sub-spans exist only for whole
   *  requests, so this changes the caption, never the rows. */
  spanKind?: SpanKind;
}

/** Wall rows only.
 *
 *  `summary(label=...)` filters on `span != ''` and NOT on kind, so since CPU
 *  joined `request_timings` the drill-down returns a wall row and a cpu row
 *  for each span. Rendering the list unfiltered draws every span twice.
 */
export function wallRows(rows: MetricsSummaryRow[]): MetricsSummaryRow[] {
  return rows.filter((r) => r.kind !== "cpu");
}

/** CPU p95 by span name. A span with no entry was not measured — which is a
 *  different answer from zero, and must not render as one. */
export function cpuByName(rows: MetricsSummaryRow[]): Record<string, number> {
  const out: Record<string, number> = {};
  for (const r of rows) {
    if (r.kind === "cpu" && r.span) out[r.span] = r.p95_ms;
  }
  return out;
}

export function SpanWaterfall(props: SpanWaterfallProps) {
  const pct = (row: MetricsSummaryRow): number =>
    Math.round(spanShare(row.p95_ms, props.totalP95) * 100);
  const walls = () => wallRows(props.rows);
  const cpu = () => cpuByName(props.rows);

  return (
    // Named for the same reason #595 named the sub-span table this
    // replaced: an accessible name is what makes the breakdown
    // addressable by role instead of by its copy.
    <section class="metrics-card" aria-label="Where the time goes">
      <div class="metrics-card-head">
        <span class="metrics-card-label">Where the time goes · p95 request</span>
        <span class="metrics-note">{Math.round(props.totalP95)} ms total</span>
      </div>

      <Show
        when={walls().length > 0}
        fallback={<p class="metrics-empty-inline">No sub-spans recorded for this route.</p>}
      >
        <div class="metrics-wf">
          <For each={walls()}>
            {(row) => (
              <>
                <span class="metrics-wf-name">
                  {row.span}
                  {/* Database time is measured at the connection layer
                      rather than by a span at a call site, so it is tagged
                      differently — it is a sum over many statements, not one
                      instrumented interval. */}
                  <Show when={row.span === "sqlite"}>
                    <span class="metrics-wf-tag">connection layer</span>
                  </Show>
                  <Show when={cpuVerdict(row.p95_ms, cpu()[row.span])}>
                    {(v) => <span class="metrics-wf-cpu">{v()}</span>}
                  </Show>
                </span>
                <span class="metrics-wf-bar">
                  <i style={{ width: `${Math.min(100, pct(row))}%` }} />
                </span>
                <span class="metrics-wf-value">
                  {Math.round(row.p95_ms)} · {pct(row)}%
                </span>
              </>
            )}
          </For>
        </div>
      </Show>

      {/* Two things about llm_call that are correct but easy to misread,
          called out where they would mislead. Its count and percentiles
          are PER ATTEMPT — the LLM client retries, and every attempt
          records its own row. And the span closes when the LLM's response
          HEADERS arrive (`llm.py`), so body and stream consumption fall
          outside it: on the chat route the spans will not add up to the
          total. Tracked as #586. */}
      <Show when={props.rows.some((r) => r.span === "llm_call")}>
        <p class="metrics-note">
          llm_call is measured per attempt, not per request, and closes when response headers arrive
          — streamed body time falls outside it, so the spans do not sum to the total on this route.
        </p>
      </Show>

      {/* The recorder never tags a sub-span `ttfe` (`recorder.py`), so
          this card cannot follow the tab. Saying so beats looking stale. */}
      <Show when={props.spanKind === "ttfe"}>
        <p class="metrics-note">
          Sub-spans are measured on the whole request, not on time to first event.
        </p>
      </Show>
    </section>
  );
}
