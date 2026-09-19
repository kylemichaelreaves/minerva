import { For, Show, createResource, createSignal } from "solid-js";

import { fetchMetricsRequests, type MetricsRequestRow, type MetricWindow } from "../api/metricsApi";

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

function clockOf(at: number): string {
  const d = new Date(at * 1000);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())}`;
}

/** The design's thresholds (obs-render.js), not invented here.
 *
 *  Returns undefined when CPU was not measured — `time.thread_time` is not on
 *  every platform and pre-Phase-2 rows carry no value. Rendering that as
 *  "0ms, waiting" would assert a measurement nobody took, which is the same
 *  mistake the health block exists to prevent one level up.
 */
function cpuVerdict(wall: number, cpu: number | null | undefined): string | undefined {
  if (cpu === null || cpu === undefined) return undefined;
  if (wall <= 0) return undefined;
  const ratio = cpu / wall;
  if (ratio > 0.6) return "cpu-bound";
  if (ratio < 0.1) return "waiting";
  return "mixed";
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

  const source = () => ({
    window: props.window,
    errors: errorsOnly(),
    phased: phasedOnly(),
  });
  const [rows] = createResource(source, (s) =>
    fetchMetricsRequests(s.window, { errors: s.errors, phased: s.phased }),
  );

  // `rows.error` first: reading an errored Solid resource re-throws, which
  // would take down the error branch below with it.
  const list = (): MetricsRequestRow[] => {
    if (rows.error) return [];
    const body = rows();
    return body ? body.rows : [];
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
            onChange={(e) => setErrorsOnly(e.currentTarget.checked)}
          />
          Errors only
        </label>
        <label class="mledger-chk">
          <input
            type="checkbox"
            aria-label="Has a phase"
            checked={phasedOnly()}
            onChange={(e) => setPhasedOnly(e.currentTarget.checked)}
          />
          Has a phase
        </label>
        <Show when={!rows.loading && !rows.error}>
          <span class="mledger-count">{list().length} requests</span>
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
        <div class="mledger-split">
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
                    onClick={() => setSelected(r.id)}
                    aria-selected={selected() === r.id}
                    classList={{ sel: selected() === r.id }}
                  >
                    <td class="num dim">{clockOf(r.at)}</td>
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
                      <Show when={r.phases.length > 0} fallback={<span class="dim">&mdash;</span>}>
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

          <aside class="mledger-detail" role="region" aria-label="Request detail">
            <Show when={chosen()} fallback={<p class="mledger-msg">Select a request.</p>}>
              {(r) => (
                <>
                  <p class="mledger-id num">{r().id}</p>
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
                        sqlite
                        <span class="mledger-tag">connection layer</span>
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
          </aside>
        </div>
      </Show>
    </section>
  );
}
