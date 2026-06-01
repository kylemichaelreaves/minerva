// Shared atlas-style chronology geometry. Used by both the Landing
// atlas (horizontal strip across X) and the Network arc drilldown
// (vertical strip down Y) — same canonical year tick set, same
// signed-year formatting, same greedy collision-avoidance pass for
// labels that would otherwise overlap their neighbours.
//
// Each consumer picks an axis-mapping function (year → position in
// viewBox units) and the rest is reusable.

/** Tick marks the atlas strip renders along its year axis. Chosen to
 *  hit every half-millennium plus a bookend at Nietzsche. */
export const YEAR_TICKS = [-1000, -500, 0, 500, 1000, 1500, 1880];

/** Render-time signed-year formatter:
 *    -1000 → "−1000"   (proper minus, not ASCII hyphen)
 *        0 → "0"
 *      500 → "+500"
 *  Used in tick labels and tooltips wherever a year is shown. */
export function formatYear(year: number): string {
  if (year < 0) return `−${Math.abs(year)}`;
  if (year === 0) return "0";
  return `+${year}`;
}

/** Greedy collision avoidance for a 1-D label strip.
 *
 *  Given items sorted by their natural axis position, walks the list
 *  and bumps each item to the next row only when its label box would
 *  overlap a previously-placed item on the same row. Returns the
 *  input items in their ORIGINAL order, each annotated with a `row`
 *  index ≥ 0 (`0` means "natural row, no nudge needed").
 *
 *  Generic over `T extends { name }` so callers can keep their full
 *  author/work shape; collision math operates on positions and label
 *  widths only.
 *
 *  Arguments:
 *    items         — the labels to place
 *    positionOf    — maps an item to its axis coordinate (viewBox units)
 *    labelHalfWidth— half the rendered label's extent along the axis.
 *                    Caller computes from `item.name.length * fontSize *
 *                    advance / 2`. Generic so the helper can work for
 *                    both 1-D-X (Landing atlas) and 1-D-Y (NetworkArc)
 *                    layouts — the function never assumes which axis.
 *    padding       — extra clearance between adjacent labels on the
 *                    same row. Tunes how tightly labels pack before
 *                    bumping to a new row. Defaults to 6 viewBox units.
 */
export interface LayoutItem<T> {
  item: T;
  row: number;
}

export function layoutLabelsGreedy<T extends { name: string }>(
  items: T[],
  positionOf: (item: T) => number,
  labelHalfWidth: (item: T) => number,
  padding = 6,
): LayoutItem<T>[] {
  const sorted = [...items].sort((a, b) => positionOf(a) - positionOf(b));
  const placed: { pos: number; row: number; halfWidth: number }[] = [];
  const out = new Map<T, number>();
  for (const item of sorted) {
    const pos = positionOf(item);
    const hw = labelHalfWidth(item);
    let row = 0;
    while (
      placed.some(
        (p) => p.row === row && Math.abs(p.pos - pos) < p.halfWidth + hw + padding,
      )
    ) {
      row += 1;
    }
    placed.push({ pos, row, halfWidth: hw });
    out.set(item, row);
  }
  // Preserve the caller's input ordering so JSX renders are stable —
  // sorted-by-position is only used internally for placement.
  return items.map((item) => ({ item, row: out.get(item) ?? 0 }));
}
