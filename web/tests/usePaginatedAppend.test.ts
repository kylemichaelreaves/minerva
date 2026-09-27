// @vitest-environment node
import { describe, it, expect, vi } from "vitest";
import { createRoot, createSignal } from "solid-js";
import { usePaginatedAppend } from "~/hooks/usePaginatedAppend";

const flush = (): Promise<void> => Promise.resolve();

// The hook is created inside a synchronous root (its effect needs an owner);
// the test body then drives it from outside, the way event handlers do.
function setup(items: number[]) {
  return createRoot((dispose) => {
    const [data, setData] = createSignal<{ items: number[] } | null>({ items });
    const api = usePaginatedAppend(() => data());
    const first = () => data()?.items ?? [];
    return { api, first, setData, dispose };
  });
}

describe("usePaginatedAppend", () => {
  it("concatenates first page with appended items", async () => {
    const { api, first, dispose } = setup([1, 2]);
    expect(api.rows(first())).toEqual([1, 2]);
    expect(api.hasMore(first(), 5)).toBe(true);

    const fetchPage = vi.fn(() => Promise.resolve({ items: [3, 4] }));
    await api.loadMore(first(), fetchPage);
    await flush();

    expect(fetchPage).toHaveBeenCalledWith(2, expect.any(AbortSignal));
    expect(api.rows(first())).toEqual([1, 2, 3, 4]);
    dispose();
  });

  it("resets extra rows when first page data changes", async () => {
    const { api, first, setData, dispose } = setup([1]);
    await api.loadMore(first(), () => Promise.resolve({ items: [2] }));
    await flush();
    expect(api.rows(first())).toEqual([1, 2]);

    setData({ items: [10] });
    await flush();
    await flush();

    expect(api.rows(first())).toEqual([10]);
    dispose();
  });

  it("clears appending when filter changes mid-flight", async () => {
    const { api, first, setData, dispose } = setup([1]);
    let resolvePage: ((value: { items: number[] }) => void) | undefined;
    const fetchPage = vi.fn(
      () =>
        new Promise<{ items: number[] }>((resolve) => {
          resolvePage = resolve;
        }),
    );
    void api.loadMore(first(), fetchPage);
    await flush();
    expect(api.appending()).toBe(true);

    setData({ items: [10] });
    await flush();
    expect(api.appending()).toBe(false);

    resolvePage?.({ items: [99] });
    await flush();
    expect(api.rows(first())).toEqual([10]);
    dispose();
  });
});
