// @vitest-environment node
// Tests for `useAbortableFetch` — the lifecycle hook that owns the
// AbortController dance, loading/error signals, and last-write-wins
// guards.

import { describe, it, expect, vi } from "vitest";
import { createRoot, createSignal, type Setter } from "solid-js";
import { useAbortableFetch } from "~/hooks/useAbortableFetch";

/** Build a deferred promise so the test can decide when the fetch
 *  resolves (or rejects, or never settles). */
function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

/** Wait one microtask tick so any pending await chains flush. */
const flush = (): Promise<void> => Promise.resolve();

describe("useAbortableFetch", () => {
  it("calls the fetcher with current args and exposes data on success", async () => {
    await createRoot(async (dispose) => {
      const fetcher = vi.fn((args: { id: number }) =>
        Promise.resolve({ echo: args.id }),
      );
      const { data, loading, error } = useAbortableFetch(() => ({ id: 7 }), fetcher);
      // createEffect runs on the next microtask; flush so the
      // fetcher has been dispatched and resolved.
      await flush();
      await flush();
      expect(fetcher).toHaveBeenCalledWith({ id: 7 }, expect.any(AbortSignal));
      expect(data()).toEqual({ echo: 7 });
      expect(loading()).toBe(false);
      expect(error()).toBeNull();
      dispose();
    });
  });

  it("re-fetches when the args accessor's reactive reads change", async () => {
    interface Args { id: number }
    let setId!: Setter<number>;
    const fetcher = vi.fn((args: Args) => Promise.resolve({ echo: args.id }));
    await createRoot(async (dispose) => {
      const [id, set] = createSignal(1);
      setId = set;
      const { data } = useAbortableFetch(() => ({ id: id() }), fetcher);
      await flush();
      await flush();
      expect(data()).toEqual({ echo: 1 });
      setId(2);
      await flush();
      await flush();
      expect(fetcher).toHaveBeenCalledTimes(2);
      expect(data()).toEqual({ echo: 2 });
      dispose();
    });
  });

  it("aborts the prior fetch when args change before it resolves", async () => {
    interface Args { id: number }
    const d1 = deferred<{ echo: number }>();
    const d2 = deferred<{ echo: number }>();
    const queue = [d1, d2];
    const signals: AbortSignal[] = [];
    const fetcher = vi.fn(async (_args: Args, signal: AbortSignal) => {
      signals.push(signal);
      return queue.shift()!.promise;
    });
    await createRoot(async (dispose) => {
      const [id, setId] = createSignal(1);
      const { data } = useAbortableFetch(() => ({ id: id() }), fetcher);
      // First fetch is in flight; trigger a re-run before it resolves.
      await flush();
      setId(2);
      await flush();
      // The first controller should now be aborted.
      expect(signals[0]!.aborted).toBe(true);
      expect(signals[1]!.aborted).toBe(false);
      // Now resolve the second (current) fetch — that's the one whose
      // data should land.
      d2.resolve({ echo: 2 });
      await flush();
      await flush();
      expect(data()).toEqual({ echo: 2 });
      // Resolving the stale first fetch must not overwrite data().
      d1.resolve({ echo: 999 });
      await flush();
      await flush();
      expect(data()).toEqual({ echo: 2 });
      dispose();
    });
  });

  it("populates error on non-abort failure and keeps loading=false", async () => {
    const fetcher = vi.fn(() => Promise.reject(new Error("network down")));
    await createRoot(async (dispose) => {
      const { data, loading, error } = useAbortableFetch(() => ({}), fetcher);
      await flush();
      await flush();
      expect(error()).toBe("network down");
      expect(loading()).toBe(false);
      expect(data()).toBeNull();
      dispose();
    });
  });

  it("ignores AbortError silently (no error state)", async () => {
    const fetcher = vi.fn(async (_args: unknown, signal: AbortSignal) => {
      return new Promise((_resolve, reject) => {
        signal.addEventListener("abort", () => {
          reject(new DOMException("aborted", "AbortError"));
        });
      });
    });
    await createRoot(async (dispose) => {
      const [id, setId] = createSignal(1);
      const { error } = useAbortableFetch(() => ({ id: id() }), fetcher);
      await flush();
      setId(2); // Triggers abort on the first call.
      await flush();
      await flush();
      // AbortError shouldn't surface as a user error.
      expect(error()).toBeNull();
      dispose();
    });
  });

  it("aborts the inflight controller on cleanup", async () => {
    let capturedSignal: AbortSignal | undefined;
    const d = deferred<unknown>();
    const fetcher = vi.fn(async (_args: unknown, signal: AbortSignal) => {
      capturedSignal = signal;
      return d.promise;
    });
    await createRoot(async (dispose) => {
      useAbortableFetch(() => ({}), fetcher);
      await flush();
      expect(capturedSignal?.aborted).toBe(false);
      dispose();
      expect(capturedSignal?.aborted).toBe(true);
    });
  });

  describe("resetOnChange", () => {
    // Whether the previous args' answer stays readable while the next one
    // is in flight. Keeping it is right for a filter change on a list — the
    // rows flicker otherwise — and wrong when the identity of the thing on
    // screen changed: the Concordance's lemma detail would render the old
    // lemma's occurrences under the new lemma's heading (#65).
    //
    // Default is to keep, because every existing caller was written against
    // that.

    it("keeps the previous data across an args change by default", async () => {
      let setId!: Setter<number>;
      const d2 = deferred<{ echo: number }>();
      const fetcher = vi.fn((args: { id: number }) =>
        args.id === 1 ? Promise.resolve({ echo: 1 }) : d2.promise,
      );
      await createRoot(async (dispose) => {
        const [id, set] = createSignal(1);
        setId = set;
        const { data, loading } = useAbortableFetch(() => ({ id: id() }), fetcher);
        await flush();
        await flush();
        expect(data()).toEqual({ echo: 1 });

        setId(2);
        await flush();

        expect(loading()).toBe(true);
        expect(data()).toEqual({ echo: 1 });
        dispose();
      });
    });

    it("drops the previous data as soon as the args change when asked", async () => {
      let setId!: Setter<number>;
      const d2 = deferred<{ echo: number }>();
      const fetcher = vi.fn((args: { id: number }) =>
        args.id === 1 ? Promise.resolve({ echo: 1 }) : d2.promise,
      );
      await createRoot(async (dispose) => {
        const [id, set] = createSignal(1);
        setId = set;
        const { data, loading } = useAbortableFetch(() => ({ id: id() }), fetcher, {
          resetOnChange: true,
        });
        await flush();
        await flush();
        expect(data()).toEqual({ echo: 1 });

        setId(2);
        await flush();

        // The point: nothing on screen claims to be about id 2 until the
        // answer for id 2 arrives.
        expect(loading()).toBe(true);
        expect(data()).toBeNull();

        d2.resolve({ echo: 2 });
        await flush();
        await flush();
        expect(data()).toEqual({ echo: 2 });
        dispose();
      });
    });

    it("clears a stale error along with the stale data", async () => {
      let setId!: Setter<number>;
      const d2 = deferred<{ echo: number }>();
      const fetcher = vi.fn((args: { id: number }) =>
        args.id === 1 ? Promise.reject(new Error("boom")) : d2.promise,
      );
      await createRoot(async (dispose) => {
        const [id, set] = createSignal(1);
        setId = set;
        const { error } = useAbortableFetch(() => ({ id: id() }), fetcher, {
          resetOnChange: true,
        });
        await flush();
        await flush();
        expect(error()).toBe("boom");

        setId(2);
        await flush();
        expect(error()).toBeNull();
        dispose();
      });
    });
  });
});
