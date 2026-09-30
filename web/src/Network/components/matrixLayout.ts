import type { CorpusBucket, MatrixCell, NetworkAuthor } from "~/api/networkApi";

/** What a cell's colour encodes: raw xref count, or its share of the
 *  citing author's row / the cited author's column. */
export type MatrixMode = "n" | "row" | "col";

/** Band order down the rows and across the columns. Scripture sits
 *  between antiquity and the medieval authors, where the Vulgate falls
 *  chronologically. Within a band, the server's chronological order is
 *  kept. */
const BAND_ORDER: CorpusBucket[] = ["class", "scrip", "med", "em", "mod", "ext"];

export const BAND_LABEL: Record<CorpusBucket, string> = {
  class: "Classical",
  scrip: "Scripture",
  med: "Medieval",
  em: "Early Modern",
  mod: "Modern",
  ext: "Other",
};

/** Lower bound of each of the six colour steps, per mode. A value takes
 *  the highest step whose bound it reaches. */
export const MODE_BINS: Record<MatrixMode, { t: number[]; labels: string[] }> = {
  n: { t: [1, 10, 50, 200, 1000, 5000], labels: ["1", "10", "50", "200", "1k", "5k+"] },
  row: {
    t: [0, 0.01, 0.03, 0.08, 0.2, 0.4],
    labels: ["<1%", "1%", "3%", "8%", "20%", "40%+"],
  },
  col: {
    t: [0, 0.01, 0.03, 0.08, 0.2, 0.4],
    labels: ["<1%", "1%", "3%", "8%", "20%", "40%+"],
  },
};

export const MODE_HINT: Record<MatrixMode, string> = {
  n: "rows = citing · cols = cited · raw counts",
  row: "each row sums to 100% · what does this author draw on?",
  col: "each column sums to 100% · who draws on this source?",
};

export interface Band {
  corpus: CorpusBucket;
  /** Position range [start, end) along the axis. */
  start: number;
  end: number;
}

export interface MatrixAxes {
  /** Author indices (into `authors`) that cite someone, in display order. */
  rows: number[];
  /** Author indices that are cited by someone, in display order. */
  cols: number[];
  rowPos: Map<number, number>;
  colPos: Map<number, number>;
  rowBands: Band[];
  colBands: Band[];
  rowTotal: Map<number, number>;
  colTotal: Map<number, number>;
}

function bandRank(a: NetworkAuthor | undefined): number {
  const k = BAND_ORDER.indexOf(a?.corpus ?? "ext");
  return k === -1 ? BAND_ORDER.length : k;
}

function orderAxis(authors: NetworkAuthor[], totals: Map<number, number>): number[] {
  return [...totals.keys()].sort((a, b) => bandRank(authors[a]) - bandRank(authors[b]) || a - b);
}

function groupBands(authors: NetworkAuthor[], order: number[]): Band[] {
  const bands: Band[] = [];
  order.forEach((i, pos) => {
    const corpus = authors[i]?.corpus ?? "ext";
    const last = bands.at(-1);
    if (last?.corpus === corpus) last.end = pos + 1;
    else bands.push({ corpus, start: pos, end: pos + 1 });
  });
  return bands;
}

function addTo(m: Map<number, number>, k: number, n: number) {
  m.set(k, (m.get(k) ?? 0) + n);
}

/** Axes for the matrix: authors who never cite drop out of the rows and
 *  authors who are never cited drop out of the columns, and each axis is
 *  grouped into corpus bands. */
export function buildAxes(authors: NetworkAuthor[], cells: MatrixCell[]): MatrixAxes {
  const rowTotal = new Map<number, number>();
  const colTotal = new Map<number, number>();
  for (const c of cells) {
    addTo(rowTotal, c.r, c.n);
    addTo(colTotal, c.c, c.n);
  }
  const rows = orderAxis(authors, rowTotal);
  const cols = orderAxis(authors, colTotal);
  return {
    rows,
    cols,
    rowPos: new Map(rows.map((i, k) => [i, k])),
    colPos: new Map(cols.map((i, k) => [i, k])),
    rowBands: groupBands(authors, rows),
    colBands: groupBands(authors, cols),
    rowTotal,
    colTotal,
  };
}

/** The value a cell is coloured by in `mode`. */
export function cellValue(cell: MatrixCell, mode: MatrixMode, axes: MatrixAxes): number {
  if (mode === "row") return cell.n / (axes.rowTotal.get(cell.r) ?? cell.n);
  if (mode === "col") return cell.n / (axes.colTotal.get(cell.c) ?? cell.n);
  return cell.n;
}

/** Colour step (0–5) for a value under `mode`. */
export function stepFor(value: number, mode: MatrixMode): number {
  const t = MODE_BINS[mode].t;
  let step = 0;
  t.forEach((bound, k) => {
    if (value >= bound) step = k;
  });
  return step;
}

/** Approximate advance of one band-caption character: 8.5px monospace
 *  (0.6em) plus ~0.12em letter-spacing. */
const BAND_CHAR_PX = 6.1;

/** Band caption shortened to fit `length` px along its axis: the full
 *  label, else its first word, else that word clipped with a period.
 *  Empty when not even three characters fit. */
export function bandLabel(corpus: CorpusBucket, length: number): string {
  const room = Math.floor((length - 4) / BAND_CHAR_PX);
  const full = BAND_LABEL[corpus].toUpperCase();
  if (full.length <= room) return full;
  const first = full.split(" ")[0] ?? full;
  if (first.length <= room) return first;
  return room >= 3 ? `${first.slice(0, room - 1)}.` : "";
}

/** `n` as a percentage of `total`, one decimal. */
export function pct(n: number, total: number | undefined): string {
  return `${((n / (total ?? n)) * 100).toFixed(1)}%`;
}

/** A cell with its display position on each axis, and the two authors it
 *  names. The matrix is a keyboard grid (#696): this is what its roving
 *  tabindex walks. */
export interface GridCell {
  cell: MatrixCell;
  src: NetworkAuthor;
  tgt: NetworkAuthor;
  /** Row position, 0 = top. */
  row: number;
  /** Column position, 0 = left. */
  col: number;
}

/** Each cell placed on `axes`, in display order: rows top to bottom, then
 *  columns left to right. A cell that cannot be placed on the axes or
 *  named from `authors` is left out, not drawn at position 0. */
export function placeCells(
  cells: MatrixCell[],
  axes: MatrixAxes,
  authors: NetworkAuthor[],
): GridCell[] {
  return cells
    .flatMap((cell) => {
      const src = authors[cell.r];
      const tgt = authors[cell.c];
      const row = axes.rowPos.get(cell.r);
      const col = axes.colPos.get(cell.c);
      if (!src || !tgt || row === undefined || col === undefined) return [];
      return [{ cell, src, tgt, row, col }];
    })
    .sort((a, b) => a.row - b.row || a.col - b.col);
}

/** Placed cells (in `placeCells` order) grouped into display rows. */
export function gridRows(placed: GridCell[]): { pos: number; cells: GridCell[] }[] {
  const rows: { pos: number; cells: GridCell[] }[] = [];
  let current: GridCell[] = [];
  let pos = -1;
  for (const g of placed) {
    if (g.row !== pos) {
      pos = g.row;
      current = [];
      rows.push({ pos, cells: current });
    }
    current.push(g);
  }
  return rows;
}

export type GridMove = "left" | "right" | "up" | "down" | "home" | "end";

type Rank = readonly [number, number, number];

/** How each move ranks a candidate against the focused cell: `null` for a
 *  cell the move cannot reach, otherwise lower is nearer. The grid is
 *  sparse, so the cell straight below is often missing: a vertical move
 *  goes to the nearest row that has any cell, then its nearest column,
 *  then the leftmost of two equally near. */
const MOVES: Record<GridMove, (c: GridCell, from: GridCell) => Rank | null> = {
  right: (c, f) => (c.row === f.row && c.col > f.col ? [c.col, 0, 0] : null),
  left: (c, f) => (c.row === f.row && c.col < f.col ? [-c.col, 0, 0] : null),
  home: (c, f) => (c.row === f.row ? [c.col, 0, 0] : null),
  end: (c, f) => (c.row === f.row ? [-c.col, 0, 0] : null),
  down: (c, f) => (c.row > f.row ? [c.row, Math.abs(c.col - f.col), c.col] : null),
  up: (c, f) => (c.row < f.row ? [-c.row, Math.abs(c.col - f.col), c.col] : null),
};

const nearer = (a: Rank, b: Rank) => (a[0] - b[0] || a[1] - b[1] || a[2] - b[2]) < 0;

/** The cell `move` lands on from `from`, or `from` itself at an edge. */
export function moveInGrid(cells: readonly GridCell[], from: GridCell, move: GridMove): GridCell {
  let best = from;
  let bestRank: Rank | null = null;
  for (const c of cells) {
    const rank = MOVES[move](c, from);
    if (rank && (bestRank === null || nearer(rank, bestRank))) {
      best = c;
      bestRank = rank;
    }
  }
  return best;
}
