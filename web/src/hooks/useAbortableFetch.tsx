// Shared hook for the fetch-with-AbortController pattern used by
// every list/window-style surface (Refs corpus browser, Refs review
// queue, etc.).
//
// Before this hook, each surface had ~25 lines of nearly-identical
// boilerplate: an `inflight` controller, a createEffect that read
// filter props + reset loading/error + aborted the prior controller +
// kicked an async function that guarded `controller.signal.aborted`
// at every assignment + an onCleanup. The audit flagged the
// duplication as the next-biggest frontend refactor target.
//
// Usage:
//
//     const { data, loading, error } = useAbortableFetch(
//       // Args accessor — Solid tracks reactive reads inside it so the
//       // hook re-fetches whenever any read prop changes.
//       () => ({
//         sourceAuthor: props.sourceAuthor,
//         limit: 500,
//       }),
//       // Fetcher — receives the args + a fresh AbortSignal.
//       fetchReferencesByAuthor,
//     );
//
// The hook intentionally does NOT show toasts — `error` is exposed
// for the caller to render inline (matches the existing Refs
// `.refs-error` block). Surfaces that want a user-visible toast on
// failure should call `apiError(...)` from a `createEffect` watching
// `error`.

import { createEffect, createSignal, onCleanup } from "solid-js";
import { errorMessage, isAbortError } from "~/utils/util";

export interface AbortableFetchApi<T> {
  data: () => T | null;
  loading: () => boolean;
  error: () => string | null;
}

export function useAbortableFetch<Args, T>(
  argsAccessor: () => Args,
  fetcher: (args: Args, signal: AbortSignal) => Promise<T>,
): AbortableFetchApi<T> {
  const [data, setData] = createSignal<T | null>(null);
  const [loading, setLoading] = createSignal(false);
  const [error, setError] = createSignal<string | null>(null);

  let inflight: AbortController | undefined;

  createEffect(() => {
    // Reading args inside the effect tracks every reactive prop
    // touched by the accessor. The effect re-runs on any change.
    const args = argsAccessor();
    inflight?.abort();
    const controller = new AbortController();
    inflight = controller;
    setLoading(true);
    setError(null);
    void (async () => {
      try {
        const res = await fetcher(args, controller.signal);
        if (!controller.signal.aborted) {
          setData(() => res);
        }
      } catch (err) {
        if (isAbortError(err)) return;
        if (!controller.signal.aborted) {
          setError(errorMessage(err));
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    })();
  });

  onCleanup(() => {
    inflight?.abort();
  });

  return { data, loading, error };
}
