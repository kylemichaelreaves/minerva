import type { AuthorPair, MatrixCell, NetworkAuthor } from "~/api/networkApi";

/** An author placed on the arc's time axis. */
export interface ArcAuthor {
  name: string;
  short: string;
  scrip: boolean;
  /** Year used for placement. Interpolated when the author has no
   *  recorded year — see `placeAuthors`. */
  year: number;
  /** False when `year` is interpolated; such a year is never displayed. */
  dated: boolean;
}

/** Era-style year label: "800 BC" / "1880 CE". */
export function formatYearEra(year: number): string {
  return year < 0 ? `${Math.abs(year)} BC` : `${year} CE`;
}

/** An author with the year it was looked up under — carried together so
 *  nothing re-looks it up behind a fallback that cannot fire (#728). */
interface Dated {
  a: NetworkAuthor;
  year: number;
}

function interpolate(ord: number, lo: Dated, hi: Dated) {
  if (hi.a.ord === lo.a.ord) return lo.year;
  return Math.round(lo.year + ((hi.year - lo.year) * (ord - lo.a.ord)) / (hi.a.ord - lo.a.ord));
}

/** Sort authors by year for the time axis.
 *
 *  Only authors on the landing atlas carry a year, so an undated author
 *  is placed by interpolating on `ord` between its nearest dated
 *  neighbours (or copying the nearest one at either end). Authors
 *  arrive in `ord` order from the server. */
export function placeAuthors(
  authors: NetworkAuthor[],
  years: ReadonlyMap<string, number>,
): ArcAuthor[] {
  const byOrd = [...authors].sort((a, b) => a.ord - b.ord);
  const dated: Dated[] = byOrd.flatMap((a) => {
    const year = years.get(a.name);
    return year === undefined ? [] : [{ a, year }];
  });
  const placed = byOrd.map((a) => {
    const y = years.get(a.name);
    if (y !== undefined) return { a, year: y, dated: true };
    const lo = dated.findLast((d) => d.a.ord <= a.ord);
    const hi = dated.find((d) => d.a.ord >= a.ord);
    let year = 0;
    if (lo && hi) year = interpolate(a.ord, lo, hi);
    else year = (lo ?? hi)?.year ?? 0;
    return { a, year, dated: false };
  });
  return placed
    .toSorted((p, q) => p.year - q.year || p.a.ord - q.a.ord)
    .map(({ a, year, dated: isDated }) => ({
      name: a.name,
      short: a.short,
      scrip: a.corpus === "scrip",
      year,
      dated: isDated,
    }));
}

/** Longest gap, in years, that still widens the axis. Longer gaps are
 *  compressed to this and marked with a break. */
export const GAP_CAP = 90;

/** Differences between consecutive years. */
function yearGaps(years: readonly number[]): number[] {
  const gaps: number[] = [];
  let prev: number | null = null;
  for (const y of years) {
    if (prev !== null) gaps.push(y - prev);
    prev = y;
  }
  return gaps;
}

/** Each item (in `placeAuthors` order) with its pixel x on a piecewise
 *  year scale: every gap is `min(gap, GAP_CAP) * k` px but never under a
 *  minimum spacing, with `k` solved so the whole axis fills `innerW`.
 *  The minimum spacing shrinks on narrow panels so some width is left
 *  for the years themselves.
 *
 *  The x rides on the item rather than in a parallel array, so a caller
 *  never zips positions back onto authors by index (#692). */
export function placeOnAxis<T extends { year: number }>(
  items: readonly T[],
  padL: number,
  innerW: number,
): (T & { x: number })[] {
  const gaps = yearGaps(items.map((a) => a.year));
  if (gaps.length === 0) return items.map((a) => ({ ...a, x: padL + innerW / 2 }));
  const even = innerW / gaps.length;
  // 11 px keeps rotated labels apart; below that even spacing wins, so
  // the axis still fits (labels crowd rather than overflow).
  const minSp = Math.min(15, Math.max(Math.min(11, even), even * 0.75));
  const step = (g: number, k: number) => Math.max(minSp, Math.min(g, GAP_CAP) * k);
  const total = (k: number) => gaps.reduce((s, g) => s + step(g, k), 0);
  let lo = 0;
  let hi = innerW;
  for (let i = 0; i < 40; i++) {
    const mid = (lo + hi) / 2;
    if (total(mid) > innerW) hi = mid;
    else lo = mid;
  }
  let x = padL;
  let prev: number | null = null;
  return items.map((a) => {
    if (prev !== null) x += step(a.year - prev, lo);
    prev = a.year;
    return { ...a, x };
  });
}

/** Pixel x for each year, as `placeOnAxis` would place it. */
export function timeScale(years: number[], padL: number, innerW: number): number[] {
  return placeOnAxis(
    years.map((year) => ({ year })),
    padL,
    innerW,
  ).map((p) => p.x);
}

/** A point on the axis, as `placeOnAxis` returns it. */
interface AxisPoint {
  year: number;
  x: number;
}

/** Midpoints of the gaps long enough to be compressed. Takes
 *  `placeOnAxis`'s output, so a year and its x cannot come apart (#728). */
export function axisBreaks(axis: readonly AxisPoint[]): number[] {
  const out: number[] = [];
  let prev: AxisPoint | undefined;
  for (const p of axis) {
    if (prev && p.year - prev.year > GAP_CAP) out.push((p.x + prev.x) / 2);
    prev = p;
  }
  return out;
}

const ERAS: [string, number, number][] = [
  ["Archaic", -Infinity, -460],
  ["Classical", -460, -300],
  ["Roman", -300, 300],
  ["Late Antiquity", 300, 800],
  ["Medieval", 800, 1500],
  ["Early Modern", 1500, 1780],
  ["Modern", 1780, Infinity],
];

export interface EraSpan {
  name: string;
  x0: number;
  x1: number;
}

/** Bracket over the authors in each era, 5 px past the outermost ticks.
 *  Eras with no authors are omitted. */
export function eraSpans(axis: readonly AxisPoint[]): EraSpan[] {
  const out: EraSpan[] = [];
  for (const [name, from, to] of ERAS) {
    const inEra = axis.filter((p) => p.year >= from && p.year < to);
    const first = inEra[0];
    const last = inEra.at(-1);
    if (first === undefined || last === undefined) continue;
    out.push({ name, x0: first.x - 5, x1: last.x + 5 });
  }
  return out;
}

/** Era caption shortened to fit a bracket `width` px wide. */
export function eraLabel(name: string, width: number): string {
  if (width > 80) return name.toUpperCase();
  if (width > 34) return name.replace(/ .*/, "").slice(0, 5).toUpperCase();
  return "";
}

/** A pair with both of its ends looked up — in a year table, or on the
 *  axis. */
export interface ArcEnds<T> {
  pair: AuthorPair;
  src: T;
  tgt: T;
}

/** The pairs whose two ends `ends` knows, each with those ends resolved.
 *  Filtering and lookup are one step, so a caller never holds a pair it
 *  then fails to place, and needs no fallback for a miss (#692). */
export function resolvePairs<T>(
  pairs: readonly AuthorPair[],
  ends: ReadonlyMap<string, T>,
): ArcEnds<T>[] {
  return pairs.flatMap((pair) => {
    const src = ends.get(pair.src);
    const tgt = ends.get(pair.tgt);
    return src === undefined || tgt === undefined ? [] : [{ pair, src, tgt }];
  });
}

/** Every in-matrix author pair, heaviest first. */
export function pairsFromCells(
  authors: NetworkAuthor[],
  cells: MatrixCell[],
  hideIntraScrip: boolean,
): AuthorPair[] {
  const out: AuthorPair[] = [];
  for (const c of cells) {
    const src = authors[c.r];
    const tgt = authors[c.c];
    if (!src || !tgt) continue;
    const intra = src.corpus === "scrip" && tgt.corpus === "scrip";
    if (hideIntraScrip && intra) continue;
    out.push({ src: src.name, tgt: tgt.name, n: c.n, intra_scrip: intra });
  }
  return out.sort((a, b) => b.n - a.n);
}

/** 0–1 weight of a count on a log scale topping out at `maxN`. */
export function logWeight(n: number, maxN: number): number {
  return Math.log10(n + 1) / Math.log10(Math.max(1, maxN) + 1);
}

/** Closed outline of a quadratic arc hanging below `baseY` from `x1`
 *  (citing end, `w0` wide) to `x2` (cited end, `w1` wide). The apex
 *  sits `dip` px below the baseline. */
export function taperPath(
  x1: number,
  x2: number,
  baseY: number,
  dip: number,
  w1: number,
  w0 = 0.5,
): string {
  const cx = (x1 + x2) / 2;
  const cy = baseY + 2 * dip;
  const left: string[] = [];
  const right: string[] = [];
  const SEG = 24;
  for (let i = 0; i <= SEG; i++) {
    const u = i / SEG;
    const v = 1 - u;
    const bx = v * v * x1 + 2 * v * u * cx + u * u * x2;
    const by = v * v * baseY + 2 * v * u * cy + u * u * baseY;
    const dx = 2 * v * (cx - x1) + 2 * u * (x2 - cx);
    const dy = 2 * v * (cy - baseY) + 2 * u * (baseY - cy);
    const len = Math.hypot(dx, dy) || 1;
    const half = (w0 + (w1 - w0) * u) / 2;
    const nx = (-dy / len) * half;
    const ny = (dx / len) * half;
    left.push(`${(bx + nx).toFixed(1)},${(by + ny).toFixed(1)}`);
    right.unshift(`${(bx - nx).toFixed(1)},${(by - ny).toFixed(1)}`);
  }
  return `M${left.join("L")}L${right.join("L")}Z`;
}

/** The earliest-dated author `name` cites, if any cited author is dated. */
export function furthestBack(
  name: string,
  outgoing: AuthorPair[],
  byName: ReadonlyMap<string, ArcAuthor>,
): { name: string; years: number } | null {
  const self = byName.get(name);
  if (!self?.dated) return null;
  let best: ArcAuthor | undefined;
  for (const p of outgoing) {
    const t = byName.get(p.tgt);
    if (t?.dated && (!best || t.year < best.year)) best = t;
  }
  return best ? { name: best.name, years: self.year - best.year } : null;
}
