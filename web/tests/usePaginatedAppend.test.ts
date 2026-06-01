import { describe, it, expect, vi } from "vitest";
import { createRoot, createSignal } from "solid-js";
import { usePaginatedAppend } from "~/hooks/usePaginatedAppend";

const flush = (): Promise<void> => Promise.resolve();

describe("usePaginatedAppend", () => {
  it("concatenates first page with appended items", async () => {
    await createRoot(async (dispose) => {
      const [data] = createSignal<{ items: number[] } | null>({
        items: [1, 2],
      });
      const api = usePaginatedAppend(() => data());

      const first = () => data()?.items ?? [];
      expect(api.rows(first())).toEqual([1, 2]);
      expect(api.hasMore(first(), 5)).toBe(true);

      const fetchPage = vi.fn(() => Promise.resolve({ items: [3, 4] }));
      await api.loadMore(first(), fetchPage);
      await flush();

      expect(fetchPage).toHaveBeenCalledWith(2);
      expect(api.rows(first())).toEqual([1, 2, 3, 4]);
      dispose();
    });
  });

  it("resets extra rows when first page data changes", async () => {
    await createRoot(async (dispose) => {
      const [data, setData] = createSignal<{ items: number[] } | null>({
        items: [1],
      });
      const api = usePaginatedAppend(() => data());

      const first = () => data()?.items ?? [];
      await api.loadMore(first(), () => Promise.resolve({ items: [2] }));
      await flush();
      expect(api.rows(first())).toEqual([1, 2]);

      setData({ items: [10] });
      await flush();
      await flush();

      expect(api.rows(first())).toEqual([10]);
      dispose();
    });
  });
});
