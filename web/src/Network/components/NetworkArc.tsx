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

import { For, Show, createSignal } from "solid-js";
import type { AuthorPair, NetworkSummary } from "~/api/networkApi";
import { YEAR_TICKS, formatYear } from "~/utils/atlasGeometry";
import { ATLAS_AUTHORS } from "~/Landing/atlasData";
import { NetworkDrilldownShell } from "~/Network/components/NetworkDrilldownShell";
import { selectArcPairs } from "~/Network/components/ArcPanel";

interface Props {
  minConfidence?: number;
  sourceAuthors?: string[];
  corpora?: string[];
  sourceMethods?: string[];
  onBack: () => void;
  onOpenAuthor: (name: string) => void;
}

// SVG canvas — matches design 5b: 390 × 1320 viewBox. Renders
// near-native size on mobile (no aspect-ratio compression).
const BASE_X = 110;
const Y_TOP = 40;
const Y_BOT = 1280;
const Y_MIN = -1000;
const Y_MAX = 1880;
const VB_WIDTH = 390;
const VB_HEIGHT = 1320;
// Minimum vertical gap (viewBox units) between two stacked labels.
const LABEL_MIN_GAP = 14;
// Max top-N pairs we render as arcs. More than this and the canvas
// turns into a tangle — readability beats completeness here.
const MAX_ARCS = 30;

function yOf(year: number): number {
  return Y_TOP + ((year - Y_MIN) * (Y_BOT - Y_TOP)) / (Y_MAX - Y_MIN);
}

function yearOf(name: string): number | null {
  const a = ATLAS_AUTHORS.find((x) => x.name === name);
  return a ? a.year : null;
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
function layoutLabels(authors: { name: string; year: number }[]) {
  const sorted = [...authors].sort((a, b) => a.year - b.year);
  let prevLblY = -Infinity;
  return sorted.map((a) => {
    const yNat = yOf(a.year);
    const yLbl = Math.max(yNat, prevLblY + LABEL_MIN_GAP);
    prevLblY = yLbl;
    return { ...a, yNat, yLbl };
  });
}

function ArcSvg(props: {
  summary: NetworkSummary;
  onOpenAuthor: (name: string) => void;
}) {
  // Tap-to-show tooltip pinned to the right side of the panel. On
  // mobile, a cursor-following tooltip is unusable (the finger
  // covers it), so we pin it to the right gutter and align its
  // vertical position with the tapped arc. Tap an arc to set;
  // tap the SVG background to dismiss.
  const [hovered, setHovered] = createSignal<
    { pair: AuthorPair; yViewBox: number } | null
  >(null);
  let svgEl: SVGSVGElement | undefined;

  const laidOut = () =>
    layoutLabels(ATLAS_AUTHORS.map((a) => ({ name: a.name, year: a.year })));

  // Filter the API's top pairs to only those with both endpoints in
  // our year table. Union the volumetric ``all`` slice with the
  // backend's ``per_author_top`` (each source author's top 3
  // outgoing non-intra-scrip pairs) so canonical-lineage edges like
  // Hegel→Heraclitus / Nietzsche→Heraclitus survive even when their
  // volume sits below the volumetric MAX_ARCS cutoff.
  const validNames = () =>
    new Set(
      ATLAS_AUTHORS.map((a) => a.name).filter((n) => yearOf(n) !== null),
    );

  const arcs = () =>
    selectArcPairs(
      props.summary.top_pairs.all,
      props.summary.top_pairs.per_author_top,
      { validNames: validNames(), cap: MAX_ARCS },
    );

  return (
    <div class="net-arc-svg-wrap">
      <svg
        ref={svgEl}
        class="net-arc-svg"
        viewBox={`0 0 ${VB_WIDTH} ${VB_HEIGHT}`}
        preserveAspectRatio="xMidYMin meet"
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
                <text x={14} y={y + 3.5} class="net-arc-yearlbl">
                  {formatYear(yr)}
                </text>
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
                onClick={() => props.onOpenAuthor(a.name)}
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
                <text
                  x={100}
                  y={a.yLbl + 3.5}
                  text-anchor="end"
                  class="net-arc-name"
                >
                  {a.name}
                </text>
              </g>
            );
          }}
        </For>
        <For each={arcs()}>
          {(p) => {
            const ys = yOf(yearOf(p.src)!);
            const yt = yOf(yearOf(p.tgt)!);
            const yA = Math.min(ys, yt);
            const yB = Math.max(ys, yt);
            const ry = (yB - yA) / 2;
            const rx = Math.max(18, Math.min((yB - yA) * 0.48, 250));
            const backward = yearOf(p.src)! > yearOf(p.tgt)!;
            const stroke = backward
              ? "var(--accent)"
              : "var(--ink-mute, #6b6357)";
            const sw = 0.6 + Math.log10(p.n + 1) * 0.5;
            const isHovered = () => hovered()?.pair === p;
            return (
              <path
                d={`M ${BASE_X} ${yA} A ${rx} ${ry} 0 0 1 ${BASE_X} ${yB}`}
                fill="none"
                stroke={stroke}
                stroke-width={isHovered() ? sw + 0.8 : sw}
                opacity={isHovered() ? 0.85 : 0.5}
                stroke-linecap="round"
                style={{ cursor: "pointer" }}
                onClick={(e) => {
                  e.stopPropagation();
                  // Anchor the tooltip's vertical position to the arc's
                  // midpoint so it visually associates with the tapped
                  // arc rather than the touch point (which on mobile
                  // is wherever the user's finger happened to land).
                  setHovered({ pair: p, yViewBox: (yA + yB) / 2 });
                }}
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
          // so ``displayedY = svgClientHeight * (vbY / VB_HEIGHT)``.
          // Falls back to a fixed top if the svg ref isn't ready.
          const tipTop = () => {
            if (!svgEl) return 60;
            const svgH = svgEl.getBoundingClientRect().height;
            return Math.max(8, svgH * (h().yViewBox / VB_HEIGHT) - 38);
          };
          return (
            <div
              class="net-tooltip net-tooltip-mobile"
              style={{ top: `${tipTop()}px` }}
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
      sourceAuthors={props.sourceAuthors}
      corpora={props.corpora}
      sourceMethods={props.sourceMethods}
    >
      {(summary) => (
        <>
          <div class="net-arc-meta">
            <span class="num">{summary.totals.xrefs.toLocaleString()}</span>{" "}
            citations · oxblood = citations <em>backward</em> in time
          </div>
          <ArcSvg summary={summary} onOpenAuthor={props.onOpenAuthor} />
        </>
      )}
    </NetworkDrilldownShell>
  );
}
