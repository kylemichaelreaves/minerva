export interface PopoverPosition {
  top: number;
  left: number;
  flipUp: boolean;
}

export const POPOVER_CARD_WIDTH = 360;
export const POPOVER_CARD_GAP = 10;
export const POPOVER_CARD_HEIGHT_ESTIMATE = 280;

/** Read the effective writing direction of an element, walking up the
 *  ancestor chain if needed. Used by popover callers to opt into RTL
 *  placement when the anchor lives inside an RTL-flowing passage
 *  (Hebrew MT, Quran, Arabic philosophy). Returns `'ltr'` by default. */
export function detectAnchorDirection(el: Element | null): "ltr" | "rtl" {
  if (!el || typeof window === "undefined") return "ltr";
  const dir = window.getComputedStyle(el).direction;
  return dir === "rtl" ? "rtl" : "ltr";
}

export function computePopoverPosition(
  anchor: DOMRect,
  opts?: { heightEstimate?: number; direction?: "ltr" | "rtl" },
): PopoverPosition {
  const heightEstimate = opts?.heightEstimate ?? POPOVER_CARD_HEIGHT_ESTIMATE;
  const direction = opts?.direction ?? "ltr";
  const vh = window.innerHeight;
  const vw = window.innerWidth;
  const flipUp =
    anchor.bottom + heightEstimate + POPOVER_CARD_GAP > vh &&
    anchor.top - heightEstimate - POPOVER_CARD_GAP > 0;
  const top = flipUp
    ? Math.max(8, anchor.top - POPOVER_CARD_GAP - heightEstimate)
    : Math.min(vh - 8, anchor.bottom + POPOVER_CARD_GAP);
  // Anchor the card's logical-start edge to the word's logical-start
  // edge — left in LTR, right in RTL. Without this the card opens
  // visually-after the word in RTL, which reads as if it's anchored
  // to the *next* word rather than the clicked one.
  let left =
    direction === "rtl" ? anchor.right - POPOVER_CARD_WIDTH : anchor.left;
  if (left + POPOVER_CARD_WIDTH > vw - 8) {
    left = vw - POPOVER_CARD_WIDTH - 8;
  }
  if (left < 8) left = 8;
  return { top, left, flipUp };
}
