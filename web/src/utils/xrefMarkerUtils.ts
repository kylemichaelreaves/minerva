/** Render small counts as Unicode superscript characters so the chip
 *  reads as `▸²`, `▸³`, etc. Falls back to the raw number for counts
 *  > 9 (rare; the page-density limit is far below that). */
export function xrefSuperscript(n: number): string {
  if (n < 0 || !Number.isInteger(n)) return String(n);
  const SUP = ["⁰", "¹", "²", "³", "⁴", "⁵", "⁶", "⁷", "⁸", "⁹"];
  if (n <= 9) return SUP[n] ?? String(n);
  return String(n)
    .split("")
    .map((d) => SUP[Number(d)] ?? d)
    .join("");
}
