/** Resize a textarea to fit its scroll height between min/max (CSS px). */
export function fitTextAreaHeight(
  el: HTMLTextAreaElement | undefined,
  minPx: number,
  maxPx: number,
): void {
  if (!el) return;
  el.style.height = `${minPx}px`;
  el.style.height = `${Math.min(el.scrollHeight, maxPx)}px`;
}
