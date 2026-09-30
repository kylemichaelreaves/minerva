// Element-size tracking signal backed by a single ResizeObserver.
//
// The Network panels (arc / heatmap / matrix) all need their wrap
// element's client box to drive SVG layout math. Each used to spin up
// its own ResizeObserver in onMount and never disconnect it — the
// observer (and its closure) outlived the component on every
// mount/unmount cycle. This hook owns the observer lifecycle:
// observe on mount, `onCleanup(() => ro.disconnect())` on disposal.
//
// `el` is an accessor (not a raw element) because Solid `ref`
// variables are assigned during render — by the time onMount runs the
// accessor returns the real node.
//
// A 0×0 client box is not a size. It is what every pre-layout paint,
// every `display:none` ancestor and every headless render reports, and
// accepting it collapsed each consumer to a zero-width SVG, discarding
// the very fallback it exists for (#585). So a box with either
// dimension at zero is "no measurement": the signal keeps the last good
// size, or `initial` if there has not been one.

import { createSignal, onCleanup, onMount } from "solid-js";

export interface ElementSize {
  w: number;
  h: number;
}

export function useElementSize(
  el: () => HTMLElement | undefined,
  initial: ElementSize,
): () => ElementSize {
  const [size, setSize] = createSignal<ElementSize>(initial);
  const measure = (n: HTMLElement | undefined) => {
    if (n && n.clientWidth > 0 && n.clientHeight > 0) {
      setSize({ w: n.clientWidth, h: n.clientHeight });
    }
  };

  onMount(() => {
    const node = el();
    if (!node) return;
    const ro = new ResizeObserver(() => {
      measure(el());
    });
    ro.observe(node);
    onCleanup(() => {
      ro.disconnect();
    });
    measure(node);
  });

  return size;
}
