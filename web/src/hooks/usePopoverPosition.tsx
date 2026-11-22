import { createSignal, onSettled, type Accessor } from "solid-js";
import {
  computePopoverPosition,
  POPOVER_CARD_HEIGHT_ESTIMATE,
  type PopoverPosition,
} from "~/utils/popoverPosition";

export function usePopoverPosition(
  anchor: Accessor<DOMRect>,
  opts?: Accessor<{ heightEstimate?: number; direction?: "ltr" | "rtl" }>,
): { pos: () => PopoverPosition } {
  const measure = (): PopoverPosition => {
    const o = opts?.() ?? {};
    return computePopoverPosition(anchor(), {
      heightEstimate: o.heightEstimate ?? POPOVER_CARD_HEIGHT_ESTIMATE,
      direction: o.direction ?? "ltr",
    });
  };

  // A writable derived signal, so it tracks the anchor reactively: the
  // Reader swaps card content inside a non-keyed <Show> when a second
  // marked word is clicked, so the hook instance survives with a NEW
  // anchor rect — without recomputing on it the card stayed pinned at
  // the previous word's position until the next scroll/resize. Scroll and
  // resize write a fresh measurement over it; the next anchor change
  // recomputes it again.
  const [pos, setPos] = createSignal(measure);

  onSettled(() => {
    const onScrollResize = () => {
      setPos(measure());
    };
    window.addEventListener("scroll", onScrollResize, true);
    window.addEventListener("resize", onScrollResize);
    return () => {
      window.removeEventListener("scroll", onScrollResize, true);
      window.removeEventListener("resize", onScrollResize);
    };
  });

  return {
    pos,
  };
}
