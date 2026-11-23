// @vitest-environment node
import { describe, expect, it, vi } from "vitest";
import { createRoot, createSignal, flush } from "solid-js";
import { createAsyncState } from "~/hooks/createAsyncState";

const settle = () => new Promise((r) => setTimeout(r, 0));

describe("createAsyncState", () => {
  // The source is memoised, as `createResource`'s was: an upstream write that
  // leaves the source's value unchanged must not re-ask. Unmemoised, a click
  // on a Metrics route row (URL changes, window doesn't) refetched the summary
  // and rebuilt the route list under the pointer.
  it("does not refetch when an upstream write leaves the source value unchanged", async () => {
    const fetcher = vi.fn((w: string) => Promise.resolve(w.toUpperCase()));
    const [route, setRoute] = createSignal({ window: "24h", selected: "a" });
    const state = createRoot(() => createAsyncState(() => route().window, fetcher));
    flush();
    await settle();
    flush();
    expect(state.value()).toBe("24H");
    expect(fetcher).toHaveBeenCalledTimes(1);

    setRoute({ window: "24h", selected: "b" });
    flush();
    await settle();
    flush();
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(state.refreshing()).toBe(false);

    setRoute({ window: "7d", selected: "b" });
    flush();
    await settle();
    flush();
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(state.value()).toBe("7D");
  });
});
