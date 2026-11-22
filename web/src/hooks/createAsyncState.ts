// An async read that keeps its previous answer on screen while the next one
// is in flight, and that reports failure as a value rather than throwing.
// Solid 2's replacement for the app's `createResource` reads: Metrics, the
// Syntax overlay, the Reader's Concordance tab and TermCard all use it.
//
// Two properties of the Metrics surface, where it started, drive the shape:
//
// 1. A FIRST fetch must be told apart from a refresh. Conflating them is what
//    once made a time-window switch blank this surface: the previous window's
//    data was still available the whole time, and every "hide while loading"
//    guard unmounted it anyway. Measured on the real server, everything below
//    the header jumped 94px up and back inside a single ~39ms frame, and the
//    Requests tab's count caption blinked out. So anything that swaps content
//    for a spinner asks `firstLoad`, and anything that wants to say "this is
//    last window's number" asks `refreshing`.
//
// 2. A failed fetch is shown INLINE, beside the rest of the panel, rather than
//    handed up to the surface's `<Errored>` boundary to blank the whole page.
//    The fetch's promise is therefore settled into a `Settled` value before
//    the memo sees it, so the memo never rejects and `error` is ordinary data.
//
// The node is a `createDeferred` with a `loadingValue`: it never suspends (no
// `<Loading>` boundary is needed, and nothing outside this panel is held by
// its fetches), and after its first answer a refetch keeps that answer
// readable while `isPending` reports the refetch.

import { createDeferred, isPending } from "solid-js";

export type Settled<T> =
  /** The source returned `undefined`: nothing has been asked for. */
  | { status: "idle" }
  /** Commit #0 — asked, but no answer has ever landed. */
  | { status: "loading" }
  | { status: "ok"; value: T }
  | { status: "error"; error: unknown };

export interface AsyncState<T> {
  /** The last answer's value; `undefined` while idle, loading or errored. */
  value: () => T | undefined;
  /** The last answer's error; `undefined` unless the last answer failed. */
  error: () => unknown;
  /** Nothing to show yet — no previous answer to fall back on. The only
   *  condition under which a spinner should replace content. */
  firstLoad: () => boolean;
  /** A previous answer is on screen and the next one is in flight. Dim it
   *  (`.metrics-stale`); never hide it. */
  refreshing: () => boolean;
}

const IDLE: Settled<never> = { status: "idle" };
const LOADING: Settled<never> = { status: "loading" };

function settle<S, T>(fetcher: (s: S) => Promise<T>, s: S): Promise<Settled<T>> {
  // `new Promise(r => r(...))` so a fetcher that throws synchronously lands
  // as an `error` answer too, instead of escaping into the memo.
  return new Promise<T>((resolve) => resolve(fetcher(s))).then(
    (value): Settled<T> => ({ status: "ok", value }),
    (error: unknown): Settled<T> => ({ status: "error", error }),
  );
}

/** Fetch `fetcher(source())` whenever `source` changes. A `source` that
 *  returns `undefined` asks nothing — the fetcher does not run — and the
 *  state reads as idle (neither loading nor refreshing). */
export function createAsyncState<S, T>(
  source: () => S | undefined,
  fetcher: (s: S) => Promise<T>,
): AsyncState<T> {
  const node = createDeferred<Settled<T>>(
    () => {
      const s = source();
      return s === undefined ? IDLE : settle(fetcher, s);
    },
    { loadingValue: LOADING },
  );
  const pending = () => isPending(() => node());

  return {
    value: () => {
      const n = node();
      return n.status === "ok" ? n.value : undefined;
    },
    error: () => {
      const n = node();
      return n.status === "error" ? n.error : undefined;
    },
    // Idle-then-asked counts as a first load too: the idle answer is a real
    // commit, so the node reads as pending rather than as `loading`, but
    // there is still nothing on screen to keep.
    firstLoad: () => {
      const status = node().status;
      return status === "loading" || (status === "idle" && pending());
    },
    refreshing: () => {
      const status = node().status;
      return (status === "ok" || status === "error") && pending();
    },
  };
}
