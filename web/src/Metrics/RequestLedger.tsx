import { For, Show, batch, createComputed, createResource, createSignal, on } from "solid-js";

import {
  fetchMetricsRequests,
  type MetricsRequestRow,
  type MetricsRequestsCursor,
  type MetricWindow,
} from "../api/metricsApi";
import { cpuVerdict } from "./cpu";
import { firstLoad, refreshing } from "~/Metrics/resourceState";
import { onActivateKey } from "~/utils/activateKey";

/** One row per request, from `request_spans` (#619).
 *
 *  This is the view the aggregate cannot give: `request_timings` folds
 *  requests into 5-minute buckets, so it answers "how is this route
 *  behaving" but never "which request was slow, and where did its time go".
 *
 *  Filtering is SERVER-side on every control here. The table is designed to
 *  hold years — retention defaults to keeping everything, because indexes
 *  rather than deletion are what keep it fast — so narrowing in the browser
 *  would mean shipping years of rows to it first.
 */

function ms(v: number): string {
  if (v < 1) return `${Math.round(v * 10) / 10}ms`;
  if (v < 1000) return `${Math.round(v)}ms`;
  if (v < 10_000) return `${(v / 1000).toFixed(2)}s`;
  return `${(v / 1000).toFixed(1)}s`;
}

/** `MM-DD HH:MM:SS`, in UTC.
 *
 *  The date is not decoration. The window selector reaches `7d`, `30d` and
 *  `all`, so a clock alone makes two requests a week apart look like two a
 *  second apart — and the table is sorted newest-first, which makes that read
 *  as a burst rather than as history.
 *
 *  Shown unconditionally rather than only on windows over a day: a format
 *  that changes shape with the selector is one the reader has to re-learn
 *  each time, and the cost here is five characters.
 *
 *  UTC, like the rest of this surface. A local date beside a UTC clock would
 *  be worse than either alone, and at 23:30Z they disagree about the day.
 */
function stampOf(at: number): string {
  const d = new Date(at * 1000);
  const p = (n: number) => String(n).padStart(2, "0");
  const date = `${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())}`;
  return `${date} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())}`;
}

function toneOf(status: number): string {
  if (status >= 500) return "bad";
  if (status >= 400) return "warn";
  return "ok";
}

export function RequestLedger(props: { window: MetricWindow }) {
  const [errorsOnly, setErrorsOnly] = createSignal(false);
  const [phasedOnly, setPhasedOnly] = createSignal(false);
  const [selected, setSelected] = createSignal<string | undefined>();

  // Pages already loaded, newest first. The resource holds only the page
  // currently in flight; everything before it lives here.
  const [older, setOlder] = createSignal<MetricsRequestRow[]>([]);
  const [cursor, setCursor] = createSignal<MetricsRequestsCursor | undefined>();

  // A filter or window change invalidates every page already appended: they
  // describe the PREVIOUS query, and keeping them would interleave two result
  // sets with nothing on screen to say so.
  const reset = () => {
    setOlder([]);
    setCursor(undefined);
    setSelected(undefined);
  };

  // The checkboxes reset in their own handlers; the window arrives as a prop
  // and the panel does not remount the ledger on a switch, so it needs its
  // own trigger (#881). A computed rather than an effect, and created BEFORE
  // the resource: it then runs ahead of the resource's source in the same
  // update, so the new window is fetched once, from the top. With an effect
  // the resource refetches first, asking the new window for rows older than
  // the OLD window's cursor, and only then resets.
  createComputed(on(() => props.window, reset, { defer: true }));

  const source = () => ({
    window: props.window,
    errors: errorsOnly(),
    phased: phasedOnly(),
    before: cursor(),
  });
  const [rows] = createResource(source, (s) =>
    fetchMetricsRequests(s.window, {
      errors: s.errors,
      phased: s.phased,
      before: s.before,
    }),
  );

  // `rows.error` first: reading an errored Solid resource re-throws, which
  // would take down the error branch below with it.
  const list = (): MetricsRequestRow[] => {
    if (rows.error) return older();
    const body = rows();
    return body ? [...older(), ...body.rows] : older();
  };

  const hasMore = () => (rows.error ? false : (rows()?.has_more ?? false));

  const loadOlder = () => {
    const body = rows.error ? undefined : rows();
    if (!body?.next_before) return;
    setOlder((prev) => [...prev, ...body.rows]);
    setCursor(body.next_before);
  };
  const chosen = () => list().find((r) => r.id === selected());

  return (
    <section class="mledger">
      <div class="mledger-filters">
        <label class="mledger-chk">
          <input
            type="checkbox"
            aria-label="Errors only"
            checked={errorsOnly()}
            onChange={(e) => {
              batch(() => {
                reset();
                setErrorsOnly(e.currentTarget.checked);
              });
            }}
          />{" "}
          Errors only
        </label>
        <label class="mledger-chk">
          <input
            type="checkbox"
            aria-label="Has a phase"
            checked={phasedOnly()}
            onChange={(e) => {
              batch(() => {
                reset();
                setPhasedOnly(e.currentTarget.checked);
              });
            }}
          />{" "}
          Has a phase
        </label>
        {/* `firstLoad`, not `rows.loading`: on a window switch the count was
            unmounted and remounted 17ms later, blinking for no reason. The
            previous count, dimmed, is a better thing to show than nothing. */}
        <Show when={!firstLoad(rows) && !rows.error}>
          <span classList={{ "mledger-count": true, "metrics-stale": refreshing(rows) }}>
            {list().length} requests{hasMore() ? "+" : ""}
          </span>
        </Show>
      </div>

      <Show when={rows.error !== undefined}>
        <p class="mledger-msg">Couldn't load requests.</p>
      </Show>

      <Show when={!rows.error && !rows.loading && list().length === 0}>
        {/* Not a bare empty table: with no traffic in the window this is the
            normal state, and saying so is more useful than blank rows. */}
        <p class="mledger-msg">No requests recorded in this window.</p>
      </Show>

      <Show when={list().length > 0}>
        <div classList={{ "mledger-split": true, "metrics-stale": refreshing(rows) }}>
          {/* Bounded and scrolled. Unbounded, a 200-row page is ~6,600px of
              table and the "Load older" control below it sits that far down
              the document — rendered, reachable by a test that only checks
              for a bounding box, and invisible to a person. */}
          <div class="mledger-tblwrap">
            <table class="mledger-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Route</th>
                  <th>Status</th>
                  <th class="r">Total</th>
                  <th>Unaccounted</th>
                  <th>Phases</th>
                </tr>
              </thead>
              <tbody>
                <For each={list()}>
                  {(r) => (
                    <tr
                      tabindex="0"
                      onClick={() => setSelected(r.id)}
                      onKeyDown={onActivateKey(() => setSelected(r.id))}
                      aria-selected={selected() === r.id}
                      classList={{ sel: selected() === r.id }}
                    >
                      <td class="num dim">{stampOf(r.at)}</td>
                      <td>
                        {r.label} <span class="mledger-meth">{r.method}</span>
                      </td>
                      <td>
                        <span class={`mledger-st ${toneOf(r.status)}`}>{r.status}</span>
                      </td>
                      <td class="num r">{ms(r.total_ms)}</td>
                      <td class="num dim">
                        {/* Usually 100%: only 0.22% of requests carry any
                          phase at all, so a full bar is the measurement
                          rather than a rendering gap. */}
                        {Math.round((r.unaccounted_ms / r.total_ms) * 100)}%
                      </td>
                      <td>
                        <Show
                          when={r.phases.length > 0}
                          fallback={<span class="dim">&mdash;</span>}
                        >
                          <For each={r.phases}>
                            {(p) => <span class="mledger-chip">{p.name}</span>}
                          </For>
                        </Show>
                      </td>
                    </tr>
                  )}
                </For>
              </tbody>
            </table>
          </div>

          <section class="mledger-detail" aria-label="Request detail">
            <Show when={chosen()} fallback={<p class="mledger-msg">Select a request.</p>}>
              {(r) => (
                <>
                  <p class="mledger-id num">
                    {r().id} · {stampOf(r().at)} UTC
                  </p>
                  <h3>{r().label}</h3>
                  <dl class="mledger-tiles">
                    <div>
                      <dt>Total</dt>
                      <dd class="num">{ms(r().total_ms)}</dd>
                    </div>
                    <div>
                      <dt>Accounted</dt>
                      <dd class="num">{ms(r().accounted_ms)}</dd>
                    </div>
                    <div>
                      <dt>Unaccounted</dt>
                      <dd class="num">{ms(r().unaccounted_ms)}</dd>
                    </div>
                    <div>
                      <dt>CPU</dt>
                      <dd class="num">
                        <Show
                          when={r().cpu_ms !== null}
                          fallback={<span class="mledger-unmeasured">not measured</span>}
                        >
                          {ms(r().cpu_ms ?? 0)}{" "}
                          <span class="mledger-verdict">
                            {cpuVerdict(r().total_ms, r().cpu_ms)}
                          </span>
                        </Show>
                      </dd>
                    </div>
                  </dl>
                  {/* Database time sits ABOVE the phases and is labelled
                      differently on purpose: it is a sum over many disjoint
                      statements, not one contiguous interval, so it does not
                      belong in the same ordered waterfall as a span. */}
                  <Show when={r().sqlite_ms !== null}>
                    <div class="mledger-phase mledger-db">
                      <span>
                        sqlite <span class="mledger-tag">connection layer</span>
                      </span>
                      <span class="mledger-bar">
                        <i
                          class="mledger-dbbar"
                          style={{ width: `${((r().sqlite_ms ?? 0) / r().total_ms) * 100}%` }}
                        />
                      </span>
                      <span class="num">{ms(r().sqlite_ms ?? 0)}</span>
                      <span class="num mledger-cpuv">{r().sqlite_queries ?? 0} q</span>
                    </div>
                  </Show>

                  <Show
                    when={r().phases.length > 0}
                    fallback={
                      <p class="mledger-msg">
                        No phase recorded. Only <code>llm_call</code>, <code>embed_search</code> and{" "}
                        <code>stanza_parse</code> are instrumented, on the chat, translate and
                        syntax paths.
                      </p>
                    }
                  >
                    <For each={r().phases}>
                      {(p) => (
                        <div class="mledger-phase">
                          <span>{p.name}</span>
                          <span class="mledger-bar">
                            <i style={{ width: `${(p.ms / r().total_ms) * 100}%` }} />
                            {/* CPU as an inset on the wall bar, per the
                                design: a bar that is nearly all inset is
                                compute, a hollow one is waiting. */}
                            <Show when={p.cpu_ms !== undefined}>
                              <b
                                class="mledger-cpu"
                                style={{ width: `${((p.cpu_ms ?? 0) / r().total_ms) * 100}%` }}
                              />
                            </Show>
                          </span>
                          <span class="num">{ms(p.ms)}</span>
                          <span class="num mledger-cpuv">
                            <Show when={p.cpu_ms !== undefined}>{ms(p.cpu_ms ?? 0)}</Show>
                          </span>
                        </div>
                      )}
                    </For>
                  </Show>
                </>
              )}
            </Show>
          </section>
        </div>
      </Show>

      {/* Append rather than replace: this is a time-ordered feed and "older"
          only ever means further down it. A back-stack of cursors would buy
          page numbers, which is not a thing anyone wants on a log. */}
      <Show when={hasMore()}>
        <button type="button" class="mledger-more" onClick={loadOlder}>
          Load older
        </button>
      </Show>
    </section>
  );
}
