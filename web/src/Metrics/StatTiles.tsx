// The four headline numbers for the selected route (#600): p50, p95,
// p99 and errors, each against the previous window where one exists.

import { For, Show } from "solid-js";
import type { MetricsSummaryRow } from "~/api/metricsApi";

/** `""` when there is no direction to show - no baseline, or no change. */
export type DeltaDirection = "up" | "down" | "";

export interface FormattedDelta {
  text: string;
  direction: DeltaDirection;
}

/** A percentile delta as the tile renders it. "up" is the BAD direction
 *  here: these are latencies, so a rise is the regression - the inverse
 *  of the usual reading, and why the class is named for the direction
 *  rather than for the judgement. */
export function formatDelta(delta: number | undefined, windowLabel: string): FormattedDelta {
  if (delta === undefined) return { text: "—", direction: "" };
  const pct = Math.round(delta * 100);
  const sign = pct > 0 ? "+" : "";
  const direction: DeltaDirection = pct > 0 ? "up" : pct < 0 ? "down" : "";
  return { text: `${sign}${pct}% vs previous ${windowLabel}`, direction };
}

/** `classList` is deliberately avoided here: an empty `direction` would
 *  put an empty string in the object's key position, and
 *  `classList.toggle("")` throws SyntaxError in the DOM. Solid happens to
 *  filter it today; spelling the class out does not depend on that. */
function deltaClass(delta: FormattedDelta): string {
  return delta.direction === "" ? "metrics-tile-delta" : `metrics-tile-delta ${delta.direction}`;
}

export interface StatTilesProps {
  row: MetricsSummaryRow;
  /** The same route in the immediately preceding window, when the
   *  backend could supply one. Absent for `window=all`, and for a route
   *  that did not exist in the previous window. */
  prior?: MetricsSummaryRow;
  /** Rendered into the delta caption, e.g. "6h" -> "vs previous 6h". */
  windowLabel: string;
}

interface Percentile {
  key: string;
  of: (r: MetricsSummaryRow) => number;
}

/** Why every percentile tile carries this.
 *
 *  Quantiles are interpolated from 14 log-scale buckets while `min_ms` and
 *  `max_ms` are exact, so a quantile can report a duration that never
 *  occurred — on live data p99 exceeds max on 8 of 24 routes (#616). Nothing
 *  renders max today, which is the only reason the contradiction is invisible.
 *  Saying "estimate" here costs nothing and makes a later "slowest request"
 *  panel honest by default rather than by someone remembering.
 *
 *  Not applied to the errors tile: `error_rate` is a ratio of counted
 *  requests, not a bucketed quantile.
 */
const PERCENTILE_TITLE =
  "Estimated from 14 log-scale buckets, not exact — it can exceed the slowest " +
  "request actually recorded. min/max are measured.";

const PERCENTILES: Percentile[] = [
  { key: "p50", of: (r) => r.p50_ms },
  { key: "p95", of: (r) => r.p95_ms },
  { key: "p99", of: (r) => r.p99_ms },
];

/** Requests that returned a 5xx, reconstructed from the ratio - the
 *  response carries `error_rate`, not a count, so this rounds. */
function errorCount(row: MetricsSummaryRow): number {
  return Math.round(row.error_rate * row.count);
}

export function StatTiles(props: StatTilesProps) {
  const deltaFor = (p: Percentile): FormattedDelta => {
    const prior = props.prior;
    if (prior === undefined || p.of(prior) === 0) return formatDelta(undefined, props.windowLabel);
    return formatDelta((p.of(props.row) - p.of(prior)) / p.of(prior), props.windowLabel);
  };

  return (
    <div class="metrics-tiles">
      <For each={PERCENTILES}>
        {(p) => (
          <div class="metrics-tile" title={PERCENTILE_TITLE}>
            <span class="metrics-tile-label">{p.key}</span>
            <span class="metrics-tile-value">
              {Math.round(p.of(props.row))}
              <small>ms</small>
            </span>
            <span class={deltaClass(deltaFor(p))}>{deltaFor(p).text}</span>
          </div>
        )}
      </For>
      <div class="metrics-tile">
        <span class="metrics-tile-label">errors</span>
        <span class="metrics-tile-value">
          {(props.row.error_rate * 100).toFixed(1)}
          <small>%</small>
        </span>
        <span class="metrics-tile-delta">
          <Show when={props.row.error_rate > 0} fallback="none">
            {errorCount(props.row)} of {props.row.count}
          </Show>
        </span>
      </div>
    </div>
  );
}
