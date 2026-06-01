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

  createEffect(() => {
    void firstPageData();
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
    setAppending(true);
    setAppendError(null);
    try {
      const offset = rows(firstPage).length;
      const res = await fetchPage(offset);
      setExtraRows((cur) => [...cur, ...res.items]);
    } catch (err) {
      setAppendError(errorMessage(err));
    } finally {
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
