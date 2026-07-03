import { createEffect, createSignal, onCleanup, onMount, type Accessor } from "solid-js";
import { computePopoverPosition, type PopoverPosition } from "~/utils/popoverPosition";

export function usePopoverPosition(
  anchor: Accessor<DOMRect>,
  opts?: { heightEstimate?: number; direction?: "ltr" | "rtl" },
): { pos: () => PopoverPosition; flipUp: () => boolean } {
  const [pos, setPos] = createSignal(
    computePopoverPosition(anchor(), opts),
  );

  // Track the anchor reactively: the Reader swaps card content inside
  // a non-keyed <Show> when a second marked word is clicked, so the
  // hook instance survives with a NEW anchor rect — without this
  // effect the card stayed pinned at the previous word's position
  // until the next scroll/resize.
  createEffect(() => {
    setPos(computePopoverPosition(anchor(), opts));
  });

  onMount(() => {
    const onScrollResize = () => {
      setPos(computePopoverPosition(anchor(), opts));
    };
    window.addEventListener("scroll", onScrollResize, true);
    window.addEventListener("resize", onScrollResize);
    onCleanup(() => {
      window.removeEventListener("scroll", onScrollResize, true);
      window.removeEventListener("resize", onScrollResize);
    });
  });

  return {
    pos,
    flipUp: () => pos().flipUp,
  };
}
