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

  onMount(() => {
    const node = el();
    if (!node) return;
    const ro = new ResizeObserver(() => {
      const n = el();
      if (!n) return;
      setSize({ w: n.clientWidth, h: n.clientHeight });
    });
    ro.observe(node);
    onCleanup(() => {
      ro.disconnect();
    });
    setSize({ w: node.clientWidth, h: node.clientHeight });
  });

  return size;
}
