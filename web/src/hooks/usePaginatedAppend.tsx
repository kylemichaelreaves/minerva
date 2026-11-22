import { createEffect, createSignal, type Accessor } from "solid-js";
import { errorMessage } from "~/utils/util";

export interface PaginatedAppendApi<T> {
  extraRows: () => T[];
  rows: (firstPage: T[]) => T[];
  hasMore: (firstPage: T[], total: number) => boolean;
  appending: () => boolean;
  appendError: () => string | null;
  loadMore: (
    firstPage: T[],
    fetchPage: (offset: number, signal: AbortSignal) => Promise<{ items: T[] }>,
  ) => Promise<void>;
}

/**
 * Appends pages after the first-page result from useAbortableFetch.
 * Resets extra rows whenever `firstPageData` changes (filter change).
 */
export function usePaginatedAppend<T>(
  firstPageData: Accessor<unknown>,
): PaginatedAppendApi<T> {
  const [extraRows, setExtraRows] = createSignal<T[]>([]);
  const [appending, setAppending] = createSignal(false);
  const [appendError, setAppendError] = createSignal<string | null>(null);
  let generation = 0;
  let inFlight: AbortController | null = null;

  // `defer: true` skips the initial run: the first page arriving for the
  // first time is not a filter change, and must not reset anything.
  createEffect(
    () => firstPageData(),
    () => {
      generation += 1;
      // Cancel any page fetch still in flight for the previous filter set
      // so it doesn't waste a round-trip or briefly flash stale rows
      // before the generation guard discards it (issue #62).
      inFlight?.abort();
      inFlight = null;
      setExtraRows([]);
      setAppendError(null);
      setAppending(false);
    },
    { defer: true },
  );

  const rows = (firstPage: T[]): T[] => [...firstPage, ...extraRows()];

  const hasMore = (firstPage: T[], total: number): boolean =>
    rows(firstPage).length < total;

  async function loadMore(
    firstPage: T[],
    fetchPage: (offset: number, signal: AbortSignal) => Promise<{ items: T[] }>,
  ): Promise<void> {
    // The re-entrancy guard reads the plain `inFlight`, not `appending()`: a
    // sentinel can fire several times in one task, and a Solid 2 signal read
    // returns the old value until the write flushes, so `appending()` would
    // still be false for the second call and stack a duplicate page fetch.
    // `inFlight` is non-null exactly while `appending` is true.
    if (inFlight !== null) return;
    const gen = generation;
    const controller = new AbortController();
    inFlight = controller;
    setAppending(true);
    setAppendError(null);
    try {
      const offset = rows(firstPage).length;
      const res = await fetchPage(offset, controller.signal);
      if (gen !== generation) return;
      setExtraRows((cur) => [...cur, ...res.items]);
    } catch (err) {
      // A filter change aborts the request and bumps the generation;
      // the gen check swallows that expected rejection.
      if (gen !== generation) return;
      setAppendError(errorMessage(err));
    } finally {
      if (inFlight === controller) inFlight = null;
      // Unconditional: the generation bump on a filter change doesn't
      // touch `appending`, so a gen-gated reset left it stuck true
      // whenever a filter changed mid-flight — every later loadMore()
      // early-returned and pagination was dead until remount.
      setAppending(false);
    }
  }

  return {
    extraRows,
    rows,
    hasMore,
    appending,
    appendError,
    loadMore,
  };
}
