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
    fetchPage: (offset: number) => Promise<{ items: T[] }>,
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
  let seeded = false;

  createEffect(() => {
    void firstPageData();
    if (!seeded) {
      seeded = true;
      return;
    }
    generation += 1;
    setExtraRows([]);
    setAppendError(null);
  });

  const rows = (firstPage: T[]): T[] => [...firstPage, ...extraRows()];

  const hasMore = (firstPage: T[], total: number): boolean =>
    rows(firstPage).length < total;

  async function loadMore(
    firstPage: T[],
    fetchPage: (offset: number) => Promise<{ items: T[] }>,
  ): Promise<void> {
    if (appending()) return;
    const gen = generation;
    setAppending(true);
    setAppendError(null);
    try {
      const offset = rows(firstPage).length;
      const res = await fetchPage(offset);
      if (gen !== generation) return;
      setExtraRows((cur) => [...cur, ...res.items]);
    } catch (err) {
      if (gen !== generation) return;
      setAppendError(errorMessage(err));
    } finally {
      if (gen === generation) {
        setAppending(false);
      }
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
