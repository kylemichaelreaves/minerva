import { Show } from "solid-js";

import type { MetricsHealth } from "../api/metricsApi";

/** Why this exists at all.
 *
 *  Three different situations used to render as the same slightly-empty page:
 *  no traffic in the window, metrics persistence switched off, and every write
 *  failing. The third is the dangerous one — `_note_write_failure` logs once
 *  per Recorder and is silent afterwards by design, so a server that has been
 *  dropping samples for a week says nothing anywhere.
 *
 *  The distinction the banner draws, and the reason the two degraded states
 *  read differently rather than sharing one "something is wrong":
 *
 *    not recording  -> the count is RIGHT and FROZEN
 *    writes failing -> the count is WRONG and still MOVING
 *
 *  Only the second makes every derived number an undercount of unknown size,
 *  which is worse to read silently than a stale page that admits it is stale.
 *
 *  It sits in the verdict's slot rather than above the header, so the page
 *  keeps its shape and the reader keeps their place. Data stays visible in
 *  both states: labelled stale numbers beat no numbers.
 */
export function MetricsHealthBanner(props: { health: MetricsHealth | undefined }) {
  // An older server has no `health` key. Render nothing rather than claiming
  // a fault — absence of the field is not evidence of a problem.
  const state = () => {
    const h = props.health;
    if (!h) return undefined;
    if (!h.persisting) return "notWriting" as const;
    // `persisting` only says a connection exists; it says nothing about
    // whether writes through it are landing.
    if (h.write_failures > 0) return "failing" as const;
    return undefined;
  };

  return (
    <Show when={state()}>
      {(kind) => (
        <p
          class={[
            "metrics-health",
            kind() === "failing" ? "metrics-health-warn" : "metrics-health-bad",
          ]}
          role="status"
          aria-label="Metrics health"
        >
          <span class={["metrics-dot", kind() === "failing" ? "warn" : "bad"]} aria-hidden="true" />
          <span>
            <Show
              when={kind() === "failing"}
              fallback={
                <>
                  <b>Nothing is being recorded.</b> The server is running without a metrics database
                  — started with <code>--no-metrics</code>, or <code>data/metrics.sqlite</code>{" "}
                  could not be opened. Everything below is the last data that reached disk and is{" "}
                  <b>frozen</b>; it will not change while this is showing.
                </>
              }
            >
              <>
                <b>{props.health?.write_failures} writes have failed.</b> Recording is being
                attempted and the database is rejecting or losing writes, so every count, quantile
                and error rate below is an <b>undercount</b> of unknown size. Unlike a stopped
                recorder, this number is still moving.
              </>
            </Show>
          </span>
        </p>
      )}
    </Show>
  );
}
