import { createEffect, createSignal } from "solid-js";

/**
 * Wires an IntersectionObserver to a sentinel element ref callback.
 * Re-runs when `enabled` toggles or the sentinel mounts/unmounts.
 *
 * The signal-based ref callback is the load-bearing part: a plain
 * `let` ref read inside an effect tracks nothing, so an effect that
 * early-returns while the sentinel is unmounted (e.g. it sits inside
 * a `<Show>` that hasn't rendered yet) never re-runs and the observer
 * is never attached. Use this hook instead of hand-rolling.
 *
 * `opts.root` is read non-reactively (in the effect's untracked apply
 * phase) when the observer is (re)built —
 * by the time the sentinel element mounts, its scroll container
 * exists, so a plain ref accessor is fine.
 */
export function useInfiniteScrollSentinel(
  enabled: () => boolean,
  onIntersect: () => void,
  opts?: { root?: () => Element | null | undefined; rootMargin?: string },
): (el: HTMLDivElement) => void {
  const [sentinelEl, setSentinelEl] = createSignal<HTMLDivElement | null>(null);

  createEffect(
    () => (enabled() ? sentinelEl() : null),
    (el) => {
      if (!el) return;
      const obs = new IntersectionObserver(
        (entries) => {
          for (const e of entries) {
            if (e.isIntersecting) {
              onIntersect();
            }
          }
        },
        {
          root: opts?.root?.() ?? null,
          rootMargin: opts?.rootMargin ?? "400px 0px",
        },
      );
      obs.observe(el);
      return () => {
        obs.disconnect();
      };
    },
  );

  return (el) => {
    setSentinelEl(el);
  };
}
