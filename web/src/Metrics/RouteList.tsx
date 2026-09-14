// The whole-request leaderboard, extracted from `MetricsPanel` (#600).
//
// Deliberately NOT built on `LeaderboardPanel` (Network's top-cited-works
// list, `~/Network/components/LeaderboardPanel.tsx`): that component
// renders a fixed author/work/sparkline row shape with no sort, no
// selection state, and no drill-down. These rows are a real `<table>`
// over a different data shape entirely — the overlap is "a list of rows",
// not enough to share code without inventing an abstraction neither
// surface needs. Copying it wholesale would fail Sonar's <=3%
// duplication gate at any coverage level regardless (#254).

import { For, Show } from "solid-js";
import type { MetricsSummaryRow } from "~/api/metricsApi";

export interface RouteListProps {
  /** Whole-request rows, already filtered to `kind === "total"` and
   *  ordered by the caller. This component does not sort. */
  rows: MetricsSummaryRow[];
  loading: boolean;
  /** Inline message when the summary fetch failed; absent when it did
   *  not. Rendered INSTEAD of the table — see `MetricsPanel`. */
  errorText?: string;
  selectedLabel?: string;
  onSelect: (label: string) => void;
}

export function RouteList(props: RouteListProps) {
  return (
    <>
      <Show when={props.errorText}>
        {(text) => (
          <div class="metrics-error" role="alert">
            Couldn't load metrics: {text()}
          </div>
        )}
      </Show>

      <Show when={props.errorText === undefined}>
        <Show when={!props.loading} fallback={<div class="metrics-loading">Loading…</div>}>
          <Show
            when={props.rows.length > 0}
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
                  <For each={props.rows}>
                    {(row) => (
                      <tr
                        class="metrics-table-row"
                        classList={{ selected: props.selectedLabel === row.label }}
                        onClick={() => props.onSelect(row.label)}
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
    </>
  );
}
