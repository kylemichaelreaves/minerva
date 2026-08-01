// The whole-sentence strip: one tick per token, its height the depth of the
// arc stack over that token, and a frame showing which part of the sentence
// is on screen.
//
// This exists for the tail. Measured across the corpus at 20px type the
// median German sentence is 1328px wide, but the worst is 7824px — 5.4
// screens for one sentence of Hegel — and wrapping, which is what makes that
// readable at all, is also what makes it easy to lose your place in. The
// strip is orientation, not navigation: where you are, where the structure
// gets deep, and where you have already corrected something.
//
// Deliberately not interactive. Keyboard focus already scrolls a token into
// view and the sentence list already moves between sentences, so a click
// target here would be a third way to do something two things already do —
// and an interactive control hidden from assistive technology, which the
// strip must be (it is a picture of a sentence), is worse than none.

/** The minimum a tick needs from a token. */
export interface MinimapToken {
  id: number;
  corrected?: boolean;
}

/** The minimum a tick needs from a levelled arc. */
export interface LevelledEdge {
  head: number;
  dep: number;
  level: number;
}

export interface MinimapTick {
  id: number;
  /** Deepest arc level the token takes part in, at either end. Always ≥ 1 —
   *  a token with no arc still gets a tick, or the strip would have holes in
   *  it where the sentence does not. */
  depth: number;
  /** Carries a hand correction, and is drawn in the corrected colour. */
  corrected: boolean;
}

/**
 * One tick per token, in surface order.
 *
 * Depth counts the token at *both* ends of an arc, not just the dependent:
 * a head governing a level-8 arc is exactly where the sentence's structure
 * is deepest, which is the thing the strip is for.
 */
export function minimapTicks(
  tokens: readonly MinimapToken[],
  arcs: readonly LevelledEdge[],
): MinimapTick[] {
  const depth = new Map<number, number>();
  for (const a of arcs) {
    depth.set(a.dep, Math.max(depth.get(a.dep) ?? 0, a.level));
    depth.set(a.head, Math.max(depth.get(a.head) ?? 0, a.level));
  }
  return tokens.map((t) => ({
    id: t.id,
    depth: Math.max(1, depth.get(t.id) ?? 0),
    corrected: t.corrected === true,
  }));
}

/**
 * The token positions covered by the rows currently on screen, as a
 * half-open interval `[start, end)` of 0-based positions in the token array.
 *
 * Returns `null` when no row is visible — before the first observation, and
 * whenever the sentence has scrolled entirely out of the pane. Drawing a
 * frame over the whole strip in that case would claim the opposite of what
 * is true.
 */
export function visibleSpan(
  rows: readonly (readonly number[])[],
  visible: ReadonlySet<number>,
): readonly [number, number] | null {
  let start = Number.POSITIVE_INFINITY;
  let end = 0;
  let at = 0;
  rows.forEach((row, i) => {
    if (visible.has(i)) {
      start = Math.min(start, at);
      end = Math.max(end, at + row.length);
    }
    at += row.length;
  });
  return start === Number.POSITIVE_INFINITY ? null : [start, end];
}
