// Telling a resource's FIRST fetch apart from a refresh.
//
// Solid's `.loading` is true for both, and conflating them is what made a
// time-window switch blank this surface: `load()` never clears a resource's
// `value`, so the previous window's data was still there the whole time and
// every `<Show when={!res.loading}>` unmounted it anyway. Measured on the
// real server, everything below the header jumped 94px up and back inside a
// single ~39ms frame, and the Requests tab's count caption blinked out.
//
// `state` separates the two cases, so anything that swaps content for a
// spinner asks `firstLoad` and anything that wants to say "this is last
// window's number" asks `refreshing`. Neither reads the resource's value, so
// neither re-throws on an errored resource.

import type { Resource } from "solid-js";

/** Nothing to show yet — no previous value to fall back on. The only
 *  condition under which a spinner should replace content. */
export function firstLoad(res: Resource<unknown>): boolean {
  return res.state === "pending";
}

/** The previous request's data is on screen and the next one is in flight.
 *  Dim it (`.metrics-stale`); never hide it. */
export function refreshing(res: Resource<unknown>): boolean {
  return res.state === "refreshing";
}
