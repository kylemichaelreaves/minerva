// Mobile chronological arc — design 5b.
//
// Transposes the desktop's horizontal arc 90° clockwise: chronology
// runs top→bottom, the baseline is a vertical line on the left, and
// arcs bulge to the right. Author labels stay horizontal (no
// rotation, no compression). Phones scroll vertically natively, so
// forcing a horizontal pan for a chronological list was the wrong
// call.
//
// Oxblood = backward-in-time citations (src.year > tgt.year);
// ink-mute = forward-in-time (rarer in our corpus).
//
// Fetch + topbar + loading shell live in `NetworkDrilldownShell`;
// this file owns the meta strip + SVG composition.

import { For, Show, createMemo, createSignal } from "solid-js";
import type { AuthorPair, NetworkFilterParams, NetworkSummary } from "~/api/networkApi";
import { YEAR_TICKS, formatYear } from "~/utils/atlasGeometry";
import { ATLAS_AUTHORS } from "~/data/atlasData";
import { NetworkDrilldownShell } from "~/Network/components/NetworkDrilldownShell";
import { YEAR_BY_NAME, selectArcPairs } from "~/Network/components/ArcPanel";
import { onActivateKey } from "~/utils/activateKey";

interface Props extends NetworkFilterParams {
  onBack: () => void;
  onOpenAuthor: (name: string) => void;
}

// SVG canvas — design 5b's 390-wide column. Renders near-native size
// on mobile (no aspect-ratio compression).
//
// The height is NOT a constant. It was (1320, with the chronology
// domain hardcoded to -1000..1880), and both went stale as the corpus
// grew: authors past 1880 fell off the end of the scale, and the
// greedy label stack ran past the bottom of the viewBox, silently
// clipping the last seven names. Both bounds are now derived from
// ATLAS_AUTHORS by `buildArcLayout`, so adding an author can move the
// canvas but can never fall off it. See #128.
const BASE_X = 110;
const Y_TOP = 40;
const Y_BOT = 1280;
const VB_WIDTH = 390;
// Breathing room below the last label, mirroring Y_TOP above the first.
const VB_BOTTOM_PAD = 40;
// Minimum vertical gap (viewBox units) between two stacked labels.
const LABEL_MIN_GAP = 14;
// Baseline offset applied when drawing a label's <text> at a layout y,
// so the glyphs sit centred on the tick rather than hanging above it.
// Exported because the canvas-height invariant has to account for it —
// a label whose *baseline* clears the viewBox still gets sliced (#128).
export const LABEL_TEXT_DY = 3.5;
// Max top-N pairs we render as arcs. More than this and the canvas
// turns into a tangle — readability beats completeness here.
const MAX_ARCS = 30;

/** Build the year→y scale for a chronology domain. Both bounds come
 *  from the data, so the newest author always lands exactly on Y_BOT
 *  rather than past it. */
function makeYOf(yMin: number, yMax: number): (year: number) => number {
  const span = yMax - yMin || 1;
  return (year) => Y_TOP + ((year - yMin) * (Y_BOT - Y_TOP)) / span;
}

/** Greedy label de-overlap going downward. If a label's natural y is
 *  too close to the previous label's y, nudge it down and draw a
 *  connector back to the true tick.
 *
 *  This is the vertical analogue of `assignAtlasRows` — same idea,
 *  different axis. Kept inline (rather than threaded through the
 *  shared `layoutLabelsGreedy`) because here we want a smooth nudged
 *  y-offset rather than discrete row indices: arcs land at the
 *  natural y, labels at the nudged y, and a connector closes the
 *  gap. Discrete rows aren't a clean fit for that. */
function layoutLabels(authors: { name: string; year: number }[], yOf: (y: number) => number) {
  const sorted = [...authors].sort((a, b) => a.year - b.year);
  let prevLblY = -Infinity;
  return sorted.map((a) => {
    const yNat = yOf(a.year);
    const yLbl = Math.max(yNat, prevLblY + LABEL_MIN_GAP);
    prevLblY = yLbl;
    return { ...a, yNat, yLbl };
  });
}

export interface ArcLayout {
  labels: { name: string; year: number; yNat: number; yLbl: number }[];
  /** Year → viewBox-y for this author set's chronology domain. */
  yOf: (year: number) => number;
  /** y of the chronology baseline's lower end, in viewBox units. */
  yBottom: number;
  /** Height the `viewBox` must declare to contain every label. */
  vbHeight: number;
}

/** Lay out the chronology column for *authors* and size the canvas to
 *  fit it. The greedy de-overlap in `layoutLabels` can push the tail
 *  well past the baseline when a period is dense (ten authors share
 *  1740–1912), so the canvas has to be measured after the fact, not
 *  asserted up front. */
export function buildArcLayout(authors: { name: string; year: number }[]): ArcLayout {
  const years = authors.map((a) => a.year);
  const yOf = makeYOf(years.length ? Math.min(...years) : 0, years.length ? Math.max(...years) : 1);
  const labels = layoutLabels(authors, yOf);
  // Labels are year-sorted and the nudge only ever moves downward, so
  // the last entry is the lowest.
  const last = labels.at(-1);
  const lastBaseline = last ? last.yLbl + LABEL_TEXT_DY : Y_BOT;
  return {
    labels,
    yOf,
    yBottom: Y_BOT,
    vbHeight: Math.ceil(Math.max(Y_BOT, lastBaseline) + VB_BOTTOM_PAD),
  };
}

// Approximate advance widths in viewBox units, measured off the
// rendered SVG: `.net-arc-name` runs ~4.8 units/char, the monospace
// `.net-arc-yearlbl` ~6.0. Only used to decide whether two labels
// would physically overlap, so being a character out just makes
// suppression marginally eager or lazy — never wrong enough to matter.
const AUTHOR_CHAR_W = 4.8;
const TICK_CHAR_W = 6.0;
const AUTHOR_LABEL_RIGHT = 100;
const TICK_LABEL_LEFT = 14;
// Baselines within this many units are on the same visual line.
const SAME_LINE_DY = 7;

/** Which year-tick *labels* to draw. The tick marks themselves always
 *  render; only the text is suppressed, and only where an author label
 *  would physically sit on top of it.
 *
 *  The first author's year equals the chronology domain's minimum, so
 *  "−1000" and "Hebrew Bible" collide by construction rather than by
 *  crowding. Sharing a line isn't sufficient though: author labels are
 *  right-anchored at x=100 and ticks start at x=14, so a short name
 *  like "Hume" clears the tick column even at Δy 2.6. Both axes have
 *  to overlap before we drop anything (#128). */
export function tickLabelsToDraw(
  ticks: readonly number[],
  labels: { name: string; yLbl: number }[],
  yOf: (year: number) => number,
): number[] {
  return ticks.filter((tick) => {
    const y = yOf(tick);
    const tickRight = TICK_LABEL_LEFT + formatYear(tick).length * TICK_CHAR_W;
    return !labels.some(
      (l) =>
        Math.abs(l.yLbl - y) < SAME_LINE_DY &&
        AUTHOR_LABEL_RIGHT - l.name.length * AUTHOR_CHAR_W < tickRight,
    );
  });
}

function ArcSvg(props: { summary: NetworkSummary; onOpenAuthor: (name: string) => void }) {
  // Tap-to-show tooltip pinned to the right side of the panel. On
  // mobile, a cursor-following tooltip is unusable (the finger
  // covers it), so we pin it to the right gutter and align its
  // vertical position with the tapped arc. Tap an arc to set;
  // tap the SVG background to dismiss.
  const [hovered, setHovered] = createSignal<{ pair: AuthorPair; yViewBox: number } | null>(null);
  let svgEl: SVGSVGElement | undefined;

  const layout = createMemo(() =>
    buildArcLayout(ATLAS_AUTHORS.map((a) => ({ name: a.name, year: a.year }))),
  );
  const laidOut = () => layout().labels;
  const yOf = (year: number) => layout().yOf(year);
  const tickLabels = createMemo(() => tickLabelsToDraw(YEAR_TICKS, layout().labels, layout().yOf));

  // Keep only the API's top pairs with both endpoints in the year
  // table, each resolved to those two years — the selector's filter and
  // lookup are one step, so there is no second lookup to guard (#692).
  // Union the volumetric ``all`` slice with the backend's
  // ``per_author_top`` (each source author's top 3 outgoing
  // non-intra-scrip pairs) so canonical-lineage edges like
  // Hegel→Heraclitus / Nietzsche→Heraclitus survive even when their
  // volume sits below the volumetric MAX_ARCS cutoff.
  const arcs = () =>
    selectArcPairs(
      props.summary.top_pairs.all,
      props.summary.top_pairs.per_author_top,
      YEAR_BY_NAME,
      { cap: MAX_ARCS },
    );

  return (
    <div class="net-arc-svg-wrap">
      <svg
        ref={svgEl}
        class="net-arc-svg"
        viewBox={`0 0 ${VB_WIDTH} ${layout().vbHeight}`}
        preserveAspectRatio="xMidYMin meet"
        // eslint-disable-next-line minerva/no-mouse-only-click -- click-outside dismiss of the tooltip; nothing to reach
        onClick={() => setHovered(null)}
      >
        <line
          x1={BASE_X}
          y1={Y_TOP}
          x2={BASE_X}
          y2={Y_BOT}
          stroke="var(--ink)"
          stroke-width="0.8"
        />
        <For each={YEAR_TICKS}>
          {(yr) => {
            const y = yOf(yr);
            return (
              <>
                <line
                  x1={BASE_X - 5}
                  y1={y}
                  x2={BASE_X + 5}
                  y2={y}
                  stroke="var(--ink-faint, #8a8170)"
                  stroke-width="0.8"
                />
                <Show when={tickLabels().includes(yr)}>
                  <text x={14} y={y + LABEL_TEXT_DY} class="net-arc-yearlbl">
                    {formatYear(yr)}
                  </text>
                </Show>
              </>
            );
          }}
        </For>
        <For each={laidOut()}>
          {(a) => {
            const nudged = a.yLbl - a.yNat > 1.5;
            return (
              <g
                class="net-arc-author"
                role="button"
                tabindex="0"
                aria-label={`${a.name}: open author`}
                onClick={() => props.onOpenAuthor(a.name)}
                onKeyDown={onActivateKey(() => props.onOpenAuthor(a.name))}
              >
                <line
                  x1={BASE_X - 5}
                  y1={a.yNat}
                  x2={BASE_X + 5}
                  y2={a.yNat}
                  stroke="var(--ink)"
                  stroke-width="1"
                />
                <Show when={nudged}>
                  <path
                    d={`M ${BASE_X - 6} ${a.yNat} L ${BASE_X - 14} ${a.yNat} L ${BASE_X - 14} ${a.yLbl} L ${BASE_X - 6} ${a.yLbl}`}
                    fill="none"
                    stroke="var(--ink-faint, #8a8170)"
                    stroke-width="0.5"
                  />
                </Show>
                <text x={100} y={a.yLbl + LABEL_TEXT_DY} text-anchor="end" class="net-arc-name">
                  {a.name}
                </text>
              </g>
            );
          }}
        </For>
        <For each={arcs()}>
          {({ pair: p, src: srcYear, tgt: tgtYear }) => {
            const ys = yOf(srcYear);
            const yt = yOf(tgtYear);
            const yA = Math.min(ys, yt);
            const yB = Math.max(ys, yt);
            const ry = (yB - yA) / 2;
            const rx = Math.max(18, Math.min((yB - yA) * 0.48, 250));
            const backward = srcYear > tgtYear;
            const stroke = backward ? "var(--accent)" : "var(--ink-mute, #6b6357)";
            const sw = 0.6 + Math.log10(p.n + 1) * 0.5;
            const isHovered = () => hovered()?.pair === p;
            // Anchor the tooltip's vertical position to the arc's midpoint so
            // it visually associates with the tapped arc rather than the touch
            // point (which on mobile is wherever the user's finger happened to
            // land).
            const show = () => setHovered({ pair: p, yViewBox: (yA + yB) / 2 });
            return (
              <path
                d={`M ${BASE_X} ${yA} A ${rx} ${ry} 0 0 1 ${BASE_X} ${yB}`}
                fill="none"
                stroke={stroke}
                stroke-width={isHovered() ? sw + 0.8 : sw}
                opacity={isHovered() ? 0.85 : 0.5}
                stroke-linecap="round"
                style={{ cursor: "pointer" }}
                role="button"
                tabindex="0"
                aria-label={`${p.src} → ${p.tgt}: ${p.n.toLocaleString()} reference${p.n === 1 ? "" : "s"}`}
                onClick={(e) => {
                  e.stopPropagation();
                  show();
                }}
                onKeyDown={onActivateKey(show)}
              />
            );
          }}
        </For>
      </svg>
      <Show when={hovered()}>
        {(h) => {
          // Tooltip pinned to the right gutter at ~190px width; its
          // top is computed by mapping the arc's midpoint viewBox-y
          // to the rendered svg's pixel-y via the displayed-height
          // ratio. ``preserveAspectRatio="xMidYMin meet"`` on the
          // svg keeps the y-axis scale equal to the x-axis scale,
          // so ``displayedY = svgClientHeight * (vbY / vbHeight)``.
          // Falls back to a fixed top if the svg ref isn't ready.
          const tipTop = () => {
            if (!svgEl) return 60;
            const svgH = svgEl.getBoundingClientRect().height;
            return Math.max(8, svgH * (h().yViewBox / layout().vbHeight) - 38);
          };
          return (
            <div
              class="net-tooltip net-tooltip-mobile"
              style={{ top: `${tipTop()}px` }}
              // eslint-disable-next-line minerva/no-mouse-only-click -- tap-to-dismiss; focusing another arc or author replaces it
              onClick={(e) => {
                e.stopPropagation();
                setHovered(null);
              }}
            >
              <div class="pair">
                {h().pair.src}
                <span class="arr">→</span>
                {h().pair.tgt}
              </div>
              <div class="count">
                {h().pair.n.toLocaleString()} reference
                {h().pair.n === 1 ? "" : "s"}
              </div>
              <div class="hint">TAP TO DISMISS</div>
            </div>
          );
        }}
      </Show>
    </div>
  );
}

export function NetworkArc(props: Props) {
  return (
    <NetworkDrilldownShell
      title="Chronological arc"
      onBack={props.onBack}
      minConfidence={props.minConfidence}
      includeRejected={props.includeRejected}
      sourceAuthors={props.sourceAuthors}
      corpora={props.corpora}
      sourceMethods={props.sourceMethods}
    >
      {(summary) => (
        <>
          <div class="net-arc-meta">
            <span class="num">{summary.totals.xrefs.toLocaleString()}</span> citations · oxblood =
            citations <em>backward</em> in time
          </div>
          <ArcSvg summary={summary} onOpenAuthor={props.onOpenAuthor} />
        </>
      )}
    </NetworkDrilldownShell>
  );
}
