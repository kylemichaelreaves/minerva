import { createEffect, createSignal, onCleanup, onMount, type Accessor } from "solid-js";
import {
  computePopoverPosition,
  POPOVER_CARD_HEIGHT_ESTIMATE,
  type PopoverPosition,
} from "~/utils/popoverPosition";

export function usePopoverPosition(
  anchor: Accessor<DOMRect>,
  opts?: Accessor<{ heightEstimate?: number; direction?: "ltr" | "rtl" }>,
): { pos: () => PopoverPosition; flipUp: () => boolean } {
  const resolveOpts = () => opts?.() ?? {};
  const [pos, setPos] = createSignal(
    computePopoverPosition(anchor(), resolveOpts()),
  );

  // Track the anchor reactively: the Reader swaps card content inside
  // a non-keyed <Show> when a second marked word is clicked, so the
  // hook instance survives with a NEW anchor rect — without this
  // effect the card stayed pinned at the previous word's position
  // until the next scroll/resize.
  createEffect(() => {
    const o = resolveOpts();
    setPos(
      computePopoverPosition(anchor(), {
        heightEstimate: o.heightEstimate ?? POPOVER_CARD_HEIGHT_ESTIMATE,
        direction: o.direction ?? "ltr",
      }),
    );
  });

  onMount(() => {
    const onScrollResize = () => {
      const o = resolveOpts();
      setPos(
        computePopoverPosition(anchor(), {
          heightEstimate: o.heightEstimate ?? POPOVER_CARD_HEIGHT_ESTIMATE,
          direction: o.direction ?? "ltr",
        }),
      );
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
