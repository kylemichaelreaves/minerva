import type { Arc } from "./arcs";
import { TOKEN_GAP } from "./measure";

// Wrapping the token row, and cutting arcs at the wrap.
//
// This exists because a sentence does not fit. Measured on the real corpus at
// 20px type: the median German sentence is 1328px wide, 44% exceed a 1440px
// viewport, and the worst case is 7824px — 5.4 screens for one sentence of
// Hegel. The alternatives both fail on what a reader actually needs, which is
// to see both endpoints of a relation and its label at once: zoom-to-fit puts
// the median sentence at 22px type and the tail far below legibility, and
// horizontal scroll means a 47-token arc is never visible as a single shape.
//
// So rows wrap. An arc crossing a boundary is cut at the measure edge and
// resumes on the next row, each half carrying the index of the token it is
// reaching for. An arc spanning a row it does not touch leaves a pass-through
// bar at its level, so a long-range dependency stays visible as a continuous
// thing rather than vanishing in the middle.

/** How far back from the hard limit we will look for a nicer break. */
const BREAK_ZONE = 0.2;

/** A row edge, when a segment runs off the side rather than to a token. */
export type Edge = "L" | "R";

export interface TokenLike {
  id: number;
  form: string;
  upos?: string | null;
}

export interface ArcSegment {
  /** Index into the row array this segment is drawn on. */
  row: number;
  /** Token id, or a row edge when the arc was cut. */
  from: number | Edge;
  to: number | Edge;
  /** True when this end was severed by a wrap rather than being a real endpoint. */
  cutFrom: boolean;
  cutTo: boolean;
  /** The arrowhead lands on the dependent, and only on the segment that holds it. */
  arrow: boolean;
  /** Crosses this row without either endpoint on it. */
  through: boolean;
  /** The token at the far end, for the `→ 27` marker on a cut. */
  partner: number;
  level: number;
  deprel: string;
  below: boolean;
  /** Identity of the parent arc — segments of one arc highlight together. */
  key: string;
}

/**
 * Break tokens into rows that fit *measure* pixels.
 *
 * Where a row could break anywhere in the last fifth of the measure, prefer a
 * point just after punctuation: cuts then land at clause edges, where fewest
 * arcs are severed. Falling back to the hard limit is deliberate — chasing a
 * comma near the start of the row would waste most of the measure and cost
 * more rows than it saves cuts.
 */
export function breakRows(
  tokens: readonly TokenLike[],
  widths: readonly number[],
  measure: number,
): number[][] {
  const rows: number[][] = [];
  let start = 0;

  while (start < tokens.length) {
    let used = 0;
    let end = start; // exclusive

    while (end < tokens.length) {
      const w = widths[end] ?? 0;
      const next = used === 0 ? w : used + TOKEN_GAP + w;
      if (next > measure && end > start) break;
      used = next;
      end += 1;
    }

    // A single token wider than the measure still has to go somewhere, or the
    // loop never advances.
    if (end === start) end = start + 1;

    if (end < tokens.length) {
      const zoneStart = start + Math.floor((end - start) * (1 - BREAK_ZONE));
      for (let k = end - 1; k >= zoneStart && k > start; k -= 1) {
        if (tokens[k]?.upos === "PUNCT") {
          end = k + 1; // break *after* the punctuation
          break;
        }
      }
    }

    rows.push(tokens.slice(start, end).map((t) => t.id));
    start = end;
  }

  return rows;
}

/** token id → index of the row it sits on. */
function rowIndex(rows: readonly number[][]): Map<number, number> {
  const out = new Map<number, number>();
  rows.forEach((row, i) => row.forEach((id) => out.set(id, i)));
  return out;
}

/**
 * Split *arcs* into per-row drawable segments.
 *
 * An arc entirely on one row yields one whole segment. An arc crossing a
 * boundary yields one segment per row it touches: the ends at a real token are
 * drawn normally, the ends at a wrap are cut flat against the measure edge.
 * Rows in between get a pass-through bar.
 */
export function segmentArcs(
  arcs: readonly (Arc & { level?: number })[],
  rows: readonly number[][],
  below: boolean,
): ArcSegment[] {
  const at = rowIndex(rows);
  const out: ArcSegment[] = [];

  for (const a of arcs) {
    const headRow = at.get(a.head);
    const depRow = at.get(a.dep);
    if (headRow === undefined || depRow === undefined) continue;

    const base = {
      level: a.level ?? 1,
      deprel: a.deprel,
      below,
      key: `${a.dep}>${a.head}`,
    };

    if (headRow === depRow) {
      out.push({
        ...base,
        row: headRow,
        from: a.head,
        to: a.dep,
        cutFrom: false,
        cutTo: false,
        arrow: true,
        through: false,
        partner: a.dep,
      });
      continue;
    }

    // Which way the arc travels decides which edge each half runs off.
    const depIsLater = depRow > headRow;
    const first = Math.min(headRow, depRow);
    const last = Math.max(headRow, depRow);

    // The head's row: from the head token out to the edge the dependent lies
    // beyond. No arrowhead — that belongs to the dependent's half.
    out.push({
      ...base,
      row: headRow,
      from: a.head,
      to: depIsLater ? "R" : "L",
      cutFrom: false,
      cutTo: true,
      arrow: false,
      through: false,
      partner: a.dep,
    });

    // The dependent's row: resumes at the opposite edge and lands the arrow.
    out.push({
      ...base,
      row: depRow,
      from: depIsLater ? "L" : "R",
      to: a.dep,
      cutFrom: true,
      cutTo: false,
      arrow: true,
      through: false,
      partner: a.head,
    });

    for (let r = first + 1; r < last; r += 1) {
      out.push({
        ...base,
        row: r,
        from: "L",
        to: "R",
        cutFrom: true,
        cutTo: true,
        arrow: false,
        through: true,
        partner: a.head,
      });
    }
  }

  // Emitted head-first per arc; a renderer draws row by row, and a caller
  // reading these in sequence expects the same order. Stable, so the segments
  // of one arc keep their head → dependent → pass-through relationship.
  return out.sort((a, b) => a.row - b.row);
}
