import type { Sentence } from "../conllu/types";

// Arc geometry for the dependency diagram: which arcs exist, which of them
// cross, how they stack, and the path each one draws.
//
// Kept pure and free of any DOM or Solid dependency — this is the part that is
// easy to get subtly wrong and expensive to debug through a rendered SVG, so
// it is unit-tested against golden fixtures in isolation.

/** Corner radius on the flat-topped bracket. */
const R = 8;
/** Distance from the token row to the first level's apex. */
const BASE = 18;
/** Distance between successive levels. */
const GAP = 30;

/** `+1` renders above the token row, `-1` below it. */
export type Side = 1 | -1;

export interface Arc {
  /** Token id of the head. */
  head: number;
  /** Token id of the dependent. The arrowhead lands here. */
  dep: number;
  deprel: string;
  /** Closed interval `[min(head, dep), max(head, dep)]`. */
  span: readonly [number, number];
}

export interface LevelledArc {
  arc: Arc;
  /** 1-based; level 1 sits closest to the token row. */
  level: number;
}

/**
 * The arcs of a sentence, one per token that has a head.
 *
 * The root gets none: `head = 0` is an attachment to the sentence itself, not
 * to a token, so there is nothing to draw between. Unparsed tokens (`head`
 * `null`, the format's `_`) likewise get none — there is no claim to render.
 */
export function arcsOf(sent: Sentence): Arc[] {
  const arcs: Arc[] = [];
  for (const tok of sent.tokens) {
    if (tok.head === null || tok.head === 0) continue;
    arcs.push({
      head: tok.head,
      dep: tok.id,
      deprel: tok.deprel,
      span: [Math.min(tok.head, tok.id), Math.max(tok.head, tok.id)],
    });
  }
  return arcs;
}

/**
 * Whether *arc* crosses another — i.e. some token strictly inside its span
 * attaches to a token outside it.
 *
 * `head(k) === 0` counts as outside, and that is correct rather than an
 * accident of the comparison: a root-attached token sitting inside a span
 * genuinely breaks it, because the root's own edge escapes the interval.
 *
 * An unparsed interior token (`head` `null`) is *not* treated as crossing.
 * It makes no claim about where it attaches, so reporting a discontinuity on
 * its behalf would be inventing one.
 */
export function isNonProjective(arc: Arc, sent: Sentence): boolean {
  const [i, j] = arc.span;
  for (const tok of sent.tokens) {
    if (tok.id <= i || tok.id >= j) continue;
    if (tok.head === null) continue;
    if (tok.head < i || tok.head > j) return true;
  }
  return false;
}

/** Two arcs may share a level iff their spans are disjoint or meet at exactly
 *  one endpoint. Any other overlap — nested or properly crossing — collides. */
function compatible(a: Arc, b: Arc): boolean {
  const [aStart, aEnd] = a.span;
  const [bStart, bEnd] = b.span;
  const overlapStart = Math.max(aStart, bStart);
  const overlapEnd = Math.min(aEnd, bEnd);
  // No overlap at all, or an overlap that is a single shared point.
  return overlapStart >= overlapEnd;
}

/**
 * Stack arcs into levels so that no two on the same level overlap.
 *
 * Sorting by span width ascending is what makes nesting come out right: a
 * narrow arc is placed before any arc that contains it, so the container is
 * pushed outward and the nested arc sits closer to the token row — which is
 * how a reader expects constituency to read off the diagram.
 *
 * Run this separately over the projective and non-projective sets; they occupy
 * mirrored stacks on opposite sides of the row and must not share levels.
 */
export function assignLevels(arcs: readonly Arc[]): LevelledArc[] {
  const ordered = [...arcs].sort((a, b) => {
    const widthA = a.span[1] - a.span[0];
    const widthB = b.span[1] - b.span[0];
    return widthA - widthB || a.span[0] - b.span[0];
  });

  const levels: Arc[][] = [];
  const out: LevelledArc[] = [];

  for (const arc of ordered) {
    let placed = false;
    for (let i = 0; i < levels.length; i += 1) {
      const level = levels[i];
      if (!level?.every((other) => compatible(arc, other))) continue;
      level.push(arc);
      out.push({ arc, level: i + 1 });
      placed = true;
      break;
    }
    if (!placed) {
      levels.push([arc]);
      out.push({ arc, level: levels.length });
    }
  }

  return out;
}

/**
 * The apex y for *level* on *side*.
 *
 * Levels above the row step upward from `rowTop`; levels below step downward
 * from `rowBottom`, mirrored.
 */
export function apexY(level: number, side: Side, rowTop: number, rowBottom: number): number {
  const offset = BASE + (level - 1) * GAP;
  return side > 0 ? rowTop - offset : rowBottom + offset;
}

/**
 * A flat-topped bracket with rounded corners, from head to dependent.
 *
 * Flat-topped rather than a Bézier so the apex sits *exactly* on the level
 * line: label clearance is then a constant, not a function of span width.
 *
 * The path runs head → dependent, so `marker-end` puts the arrowhead on the
 * dependent, which is the direction the relation is read in.
 *
 * @param xHead  x of the head token's centre
 * @param xDep   x of the dependent token's centre
 * @param apex   y of the flat segment (from `apexY`)
 * @param yStart y of the token row edge the arc springs from
 * @param side   `+1` above the row, `-1` below
 */
export function arcPath(
  xHead: number,
  xDep: number,
  apex: number,
  yStart: number,
  side: Side,
): string {
  const dirX = xDep > xHead ? 1 : -1;
  return [
    `M ${xHead} ${yStart}`,
    `L ${xHead} ${apex + side * R}`,
    `Q ${xHead} ${apex} ${xHead + dirX * R} ${apex}`,
    `L ${xDep - dirX * R} ${apex}`,
    `Q ${xDep} ${apex} ${xDep} ${apex + side * R}`,
    `L ${xDep} ${yStart}`,
  ].join(" ");
}
