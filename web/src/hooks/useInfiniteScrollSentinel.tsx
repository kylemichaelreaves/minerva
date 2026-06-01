import { createEffect, createSignal, onCleanup } from "solid-js";

/**
 * Wires an IntersectionObserver to a sentinel element ref callback.
 * Re-runs when `enabled` toggles or the sentinel mounts/unmounts.
 */
export function useInfiniteScrollSentinel(
  enabled: () => boolean,
  onIntersect: () => void,
): (el: HTMLDivElement) => void {
  const [sentinelEl, setSentinelEl] = createSignal<HTMLDivElement | null>(null);

  createEffect(() => {
    const el = sentinelEl();
    if (!el || !enabled()) return;
    const obs = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            onIntersect();
          }
        }
      },
      { rootMargin: "400px 0px" },
    );
    obs.observe(el);
    onCleanup(() => obs.disconnect());
  });

  return setSentinelEl;
}
