// The route list: severity first, then everything else (#600).
//
// Deliberately NOT built on `LeaderboardPanel` (Network's top-cited-works
// list, `~/Network/components/LeaderboardPanel.tsx`): that component
// renders a fixed author/work/sparkline row shape with no sort, no
// selection state, and no drill-down. The overlap is "a list of rows",
// not enough to share code without inventing an abstraction neither
// surface needs — and copying it wholesale would fail Sonar's <=3%
// duplication gate at any coverage level regardless (#254).

import { For, Show, createMemo, createSignal } from "solid-js";
import type { RouteEntry, Severity } from "~/Metrics/severity";

export const SORT_MODES = ["severity", "p95", "count", "name"] as const;
export type SortMode = (typeof SORT_MODES)[number];

const SORT_LABELS: Record<SortMode, string> = {
  severity: "sorted by severity",
  p95: "sorted by p95",
  count: "sorted by count",
  name: "sorted by name",
};

const SEVERITY_RANK: Record<Severity, number> = { bad: 0, warn: 1, ok: 2 };

/** Returns a new array; the caller's is left alone. Severity ties break
 *  on p95 so the worst thing in each group is still at its top. */
export function sortEntries(entries: RouteEntry[], mode: SortMode): RouteEntry[] {
  const copy = [...entries];
  if (mode === "name") return copy.sort((a, b) => a.row.label.localeCompare(b.row.label));
  if (mode === "count") return copy.sort((a, b) => b.row.count - a.row.count);
  if (mode === "p95") return copy.sort((a, b) => b.row.p95_ms - a.row.p95_ms);
  return copy.sort(
    (a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity] || b.row.p95_ms - a.row.p95_ms,
  );
}

export interface RouteListProps {
  entries: RouteEntry[];
  /** FIRST load only — nothing to render yet. Deliberately NOT a
   *  resource's `.loading`, which is also true during a refresh and would
   *  unmount rows that are still perfectly good. `MetricsPanel.firstLoad`
   *  is the only thing that should feed this. */
  loading: boolean;
  /** These rows belong to the previous request and the next one is in
   *  flight. Dims them; never hides them. */
  stale?: boolean;
  /** Inline message when the summary fetch failed; rendered INSTEAD of
   *  the list, since an empty list would otherwise read as "no traffic". */
  errorText?: string;
  selectedLabel?: string;
  onSelect: (label: string) => void;
}

function Row(props: {
  entry: RouteEntry;
  maxP95: number;
  selected: boolean;
  onSelect: (label: string) => void;
}) {
  const row = () => props.entry.row;
  // A floor of 2%, not 0: 1 ms against a 9800 ms worst case rounds to
  // nothing, and a row with no bar at all reads as missing data rather
  // than as a very fast route.
  const width = () => Math.max(2, Math.round((row().p95_ms / props.maxP95) * 100));

  return (
    <button
      type="button"
      class="metrics-row"
      aria-pressed={props.selected}
      onClick={() => props.onSelect(row().label)}
    >
      <span class="metrics-row-name">
        <span class={`metrics-dot ${props.entry.severity}`} aria-hidden="true" />
        <span class="metrics-row-text" data-testid="metrics-route-label">
          {row().label}
        </span>
        <span class="metrics-method">{row().method}</span>
      </span>
      <span classList={{ "metrics-row-err": true, bad: row().error_rate > 0 }}>
        <Show when={row().error_rate > 0} fallback="—">
          {(row().error_rate * 100).toFixed(1)}%
        </Show>
      </span>
      <span class="metrics-row-count">{row().count.toLocaleString()}</span>
      <span>
        <span classList={{ "metrics-row-p95": true, bad: props.entry.severity === "bad" }}>
          {Math.round(row().p95_ms)}
          <small>ms</small>
        </span>
        <span class="metrics-row-bar">
          <i classList={{ bad: props.entry.severity === "bad" }} style={{ width: `${width()}%` }} />
        </span>
      </span>
    </button>
  );
}

export function RouteList(props: RouteListProps) {
  // Local, not in the URL. `readRoute`'s cognitive complexity is already
  // over the Sonar limit and grows with every new surface (#589), so a
  // `sort=` parameter would worsen a gate that is already red. Same
  // precedent as the detail pane's Total/TTFE tab.
  const [sort, setSort] = createSignal<SortMode>("severity");

  const sorted = createMemo(() => sortEntries(props.entries, sort()));
  const maxP95 = createMemo(() => Math.max(1, ...props.entries.map((e) => e.row.p95_ms)));
  // Grouping is a property of the severity ordering. Showing "Needs a
  // look" above a list ordered by name would offer two organising
  // principles at once and honour neither.
  const grouped = createMemo(() => sort() === "severity");
  const needsLook = createMemo(() => sorted().filter((e) => e.severity !== "ok"));
  const fine = createMemo(() => sorted().filter((e) => e.severity === "ok"));

  const rowFor = (entry: RouteEntry) => (
    <Row
      entry={entry}
      maxP95={maxP95()}
      selected={props.selectedLabel === entry.row.label}
      onSelect={props.onSelect}
    />
  );

  return (
    <div classList={{ "metrics-routes": true, "metrics-stale": props.stale }}>
      <div class="metrics-routes-head">
        <span class="metrics-label">
          {props.entries.length} {props.entries.length === 1 ? "route" : "routes"}
        </span>
        <select
          aria-label="Sort routes"
          value={sort()}
          onChange={(e) => setSort(e.currentTarget.value as SortMode)}
        >
          <For each={SORT_MODES}>{(mode) => <option value={mode}>{SORT_LABELS[mode]}</option>}</For>
        </select>
      </div>

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
            when={props.entries.length > 0}
            fallback={
              <div class="metrics-empty" role="status">
                No requests recorded in this window.
              </div>
            }
          >
            {/* Named, and a group rather than a bare div: the rows are
                toggle buttons (`aria-pressed`), so a set of related
                controls is exactly what `group` describes — same
                precedent as the "Time window" group in MetricsPanel. It
                is also what lets the browser suite address the list by
                role + name (#593's tier 1) now that the route TABLE it
                named is gone. */}
            <div class="metrics-routes-scroll" role="group" aria-label="Routes">
              <Show when={grouped()} fallback={<For each={sorted()}>{rowFor}</For>}>
                <Show when={needsLook().length > 0}>
                  <div class="metrics-group">
                    <span class="metrics-label bad">Needs a look</span>
                    <hr />
                  </div>
                  <For each={needsLook()}>{rowFor}</For>
                </Show>
                <Show when={fine().length > 0}>
                  <div class="metrics-group">
                    <span class="metrics-label">Inside usual range</span>
                    <hr />
                  </div>
                  <For each={fine()}>{rowFor}</For>
                </Show>
              </Show>
            </div>
          </Show>
        </Show>
      </Show>
    </div>
  );
}
