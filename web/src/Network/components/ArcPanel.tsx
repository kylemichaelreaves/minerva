import { For, Show, createMemo, createSignal } from "solid-js";
import type { AuthorPair, MatrixCell, NetworkAuthor } from "~/api/networkApi";
import { ATLAS_AUTHORS } from "~/data/atlasData";
import { useElementSize } from "~/hooks/useElementSize";
import { ArcDetail } from "~/Network/components/ArcDetail";
import {
  axisBreaks,
  eraLabel,
  eraSpans,
  formatYearEra,
  logWeight,
  pairsFromCells,
  placeAuthors,
  taperPath,
  timeScale,
  type ArcAuthor,
} from "~/Network/components/arcLayout";

export interface SelectArcPairsOpts {
  validNames?: Set<string>;
  hideIntraScrip?: boolean;
  cap?: number;
}

/** Union volumetric top pairs with per-author top pairs, dedupe by src/tgt. */
export function selectArcPairs(
  primary: AuthorPair[],
  supplemental: AuthorPair[],
  opts: SelectArcPairsOpts = {},
): AuthorPair[] {
  const seen = new Set<string>();
  const out: AuthorPair[] = [];
  for (const p of [...primary, ...supplemental]) {
    const key = `${p.src}\x00${p.tgt}`;
    if (seen.has(key)) continue;
    if (opts.validNames) {
      if (!opts.validNames.has(p.src) || !opts.validNames.has(p.tgt)) continue;
    }
    if (opts.hideIntraScrip && p.intra_scrip) continue;
    seen.add(key);
    out.push(p);
    if (opts.cap !== undefined && out.length >= opts.cap) break;
  }
  return out;
}

// Map author name → year (negative = BCE). The NetworkAuthor shape
// carries only `ord`, a sort ordinal from `author_ordering.py` that is
// not a date. Years come from ATLAS_AUTHORS (the table the landing
// chronology strip uses); authors missing from it are interpolated by
// `placeAuthors`.
const YEAR_BY_NAME: ReadonlyMap<string, number> = new Map(
  ATLAS_AUTHORS.map((a) => [a.name, a.year]),
);

const PAD_X = 20;
/** Baseline y. The rotated author labels and era brackets sit above it. */
const BASE_Y = 112;
const MONO = "ui-monospace, SFMono-Regular, Menlo, monospace";

const involves = (p: AuthorPair, name: string) => p.src === name || p.tgt === name;
/** The resting arc set: volume-ranked top pairs plus, with scripture
 *  hidden, each author's top 3. */
function restingPairs(
  src: {
    topPairsAll: AuthorPair[];
    topPairsNonScrip: AuthorPair[];
    topPairsPerAuthor: AuthorPair[];
  },
  hideIntra: boolean,
  validNames: Set<string>,
): AuthorPair[] {
  if (!hideIntra) return selectArcPairs(src.topPairsAll, [], { validNames });
  return selectArcPairs(src.topPairsNonScrip, src.topPairsPerAuthor, { validNames });
}

/** Arcs to draw, lightest first so the heaviest paint on top: every pair
 *  of the focused author, or the resting set. */
function drawnPairs(focus: string | null, all: AuthorPair[], rest: AuthorPair[]): AuthorPair[] {
  const pairs = focus ? all.filter((p) => involves(p, focus)) : rest;
  return [...pairs].sort((a, b) => a.n - b.n);
}

/** Focused: navy for what the author cites, ochre for who cites them.
 *  Resting: navy, or terra for an intra-scripture pair. */
function arcFill(p: AuthorPair, focus: string | null): string {
  if (focus) return p.src === focus ? "var(--net-arc-out)" : "var(--net-arc-in)";
  return p.intra_scrip ? "var(--net-terra)" : "var(--net-arc-out)";
}

/** Opacity follows volume; focused arcs start from a higher floor, and
 *  the hovered arc is solid. */
function arcOpacity(
  p: AuthorPair,
  focus: string | null,
  hovered: AuthorPair | undefined,
  weight: number,
): number {
  if (hovered === p) return 1;
  return (focus ? 0.35 : 0.12) + 0.6 * weight;
}

const pairSpan = (xOf: ReadonlyMap<string, number>, p: AuthorPair) =>
  Math.abs((xOf.get(p.src) ?? 0) - (xOf.get(p.tgt) ?? 0));

export function ArcPanel(props: {
  authors: NetworkAuthor[];
  /** Full matrix sparse cells: every in-corpus author pair. A focused
   *  author shows all of theirs, not just those in the top-N set. */
  matrixCells: MatrixCell[];
  topPairsAll: AuthorPair[];
  topPairsNonScrip: AuthorPair[];
  /** Backend's per-author top 3 outgoing non-intra-scrip pairs. We
   *  union with topPairsNonScrip so canonical-lineage edges (Hegel→
   *  Heraclitus, Nietzsche→Heraclitus, etc.) survive the volume-rank
   *  truncation. */
  topPairsPerAuthor: AuthorPair[];
  onOpenPair: (source: string, target: string) => void;
}) {
  const [hideIntra, setHideIntra] = createSignal(true);
  // `focus` is set by clicking an author and stays until cleared;
  // `preview` follows the pointer over the labels and wins while set.
  const [focus, setFocus] = createSignal<string | null>(null);
  const [preview, setPreview] = createSignal<string | null>(null);
  const active = () => preview() ?? focus();
  const [hovered, setHovered] = createSignal<{ pair: AuthorPair; x: number; y: number } | null>(
    null,
  );
  let stageEl: HTMLDivElement | undefined;
  const size = useElementSize(() => stageEl, { w: 700, h: 320 });

  const placed = createMemo(() => placeAuthors(props.authors, YEAR_BY_NAME));
  const byName = createMemo(() => new Map(placed().map((a) => [a.name, a])));

  const allPairs = createMemo(() => pairsFromCells(props.authors, props.matrixCells, hideIntra()));
  // The resting set: volume-ranked top pairs plus each author's top 3.
  const restPairs = createMemo(() => restingPairs(props, hideIntra(), new Set(byName().keys())));
  const drawn = createMemo(() => drawnPairs(active(), allPairs(), restPairs()));
  const context = createMemo(() => {
    const f = active();
    return f ? restPairs().filter((p) => !involves(p, f)) : [];
  });
  const linked = createMemo(() => new Set(drawn().flatMap((p) => [p.src, p.tgt])));

  const geo = createMemo(() => {
    const { w, h } = size();
    const years = placed().map((a) => a.year);
    const xs = timeScale(years, PAD_X, Math.max(0, w - 2 * PAD_X));
    const xOf = new Map(placed().map((a, i) => [a.name, xs[i] ?? 0]));
    const everyPair = [...allPairs(), ...restPairs()];
    return {
      w,
      h,
      xs,
      xOf,
      breaks: axisBreaks(years, xs),
      eras: eraSpans(placed(), xs),
      maxN: Math.max(1, ...everyPair.map((p) => p.n)),
      maxSpan: Math.max(1, ...everyPair.map((p) => pairSpan(xOf, p))),
      maxDip: Math.max(0, h - BASE_Y - 14),
    };
  });

  const weight = (p: AuthorPair) => logWeight(p.n, geo().maxN);
  function arcD(p: AuthorPair) {
    const g = geo();
    const dip = g.maxDip * Math.pow(pairSpan(g.xOf, p) / g.maxSpan, 0.75);
    return taperPath(g.xOf.get(p.src) ?? 0, g.xOf.get(p.tgt) ?? 0, BASE_Y, dip, 1 + weight(p) * 6);
  }
  function toggleFocus(name: string) {
    setFocus((f) => (f === name ? null : name));
  }

  return (
    <section class="net-panel" data-panel="arc">
      <div class="net-panel-head">
        <div>
          <div class="net-panel-title">Chronological arc diagram</div>
          <div class="net-panel-q">Which authors reach back furthest, and to whom?</div>
        </div>
        <button
          class={"net-toggle" + (hideIntra() ? " on" : "")}
          aria-pressed={hideIntra()}
          onClick={() => setHideIntra((v) => !v)}
        >
          <span class="sw" /> Hide intra-scripture
        </button>
      </div>
      <div class="net-panel-body">
        <div class="net-arc-wrap">
          <ArcLegend active={active()} />
          <div class="net-arc-stage" ref={stageEl}>
            <svg
              width={geo().w}
              height={geo().h}
              viewBox={`0 0 ${geo().w} ${geo().h}`}
              style={{ display: "block" }}
            >
              <EraBrackets eras={geo().eras} />
              <line
                x1={PAD_X - 6}
                x2={geo().w - PAD_X + 6}
                y1={BASE_Y}
                y2={BASE_Y}
                stroke="var(--ink)"
                stroke-width={0.8}
              />
              <For each={geo().breaks}>{(x) => <AxisBreak x={x} />}</For>
              <g class="net-arc-context">
                <For each={context()}>{(p) => <path d={arcD(p)} />}</For>
              </g>
              <For each={drawn()}>
                {(p) => (
                  <path
                    class="net-arc"
                    d={arcD(p)}
                    fill={arcFill(p, active())}
                    fill-opacity={arcOpacity(p, active(), hovered()?.pair, weight(p))}
                    onClick={() => props.onOpenPair(p.src, p.tgt)}
                    onMouseMove={(e) => {
                      if (!stageEl) return;
                      const rect = stageEl.getBoundingClientRect();
                      setHovered({ pair: p, x: e.clientX - rect.left, y: e.clientY - rect.top });
                    }}
                    onMouseLeave={() => setHovered(null)}
                  />
                )}
              </For>
              <For each={placed()}>
                {(a, i) => (
                  <AuthorLabel
                    author={a}
                    x={geo().xs[i()] ?? 0}
                    active={active()}
                    pinned={focus() === a.name}
                    linked={linked().has(a.name)}
                    onPreview={setPreview}
                    onToggle={toggleFocus}
                  />
                )}
              </For>
            </svg>
            <Show when={hovered()}>
              {(h) => <ArcTooltip hover={h()} byName={byName()} width={geo().w} />}
            </Show>
          </div>
          <ArcDetail
            active={active()}
            pinned={focus() !== null && preview() === null}
            topPairs={restPairs()}
            allPairs={allPairs()}
            hideIntra={hideIntra()}
            byName={byName()}
            onFocus={(name) => {
              setPreview(null);
              setFocus(name);
            }}
          />
        </div>
      </div>
    </section>
  );
}

function ArcLegend(props: { active: string | null }) {
  return (
    <div class="net-arc-legend">
      <Show
        when={props.active}
        fallback={
          <>
            <span>thin end = citing · thick end = cited</span>
            <span>opacity = volume</span>
            <span>click an author to focus</span>
          </>
        }
      >
        {(f) => (
          <>
            <span>
              <i class="sw" style={{ background: "var(--net-arc-out)" }} />
              {f()} cites
            </span>
            <span>
              <i class="sw" style={{ background: "var(--net-arc-in)" }} />
              cites {f()}
            </span>
            <span>thin end = citing · thick end = cited</span>
          </>
        )}
      </Show>
    </div>
  );
}

function EraBrackets(props: { eras: { name: string; x0: number; x1: number }[] }) {
  return (
    <g class="net-arc-eras">
      <For each={props.eras}>
        {(e) => (
          <>
            <line x1={e.x0} x2={e.x1} y1={16} y2={16} />
            <line x1={e.x0} x2={e.x0} y1={13} y2={19} />
            <line x1={e.x1} x2={e.x1} y1={13} y2={19} />
            <text
              x={(e.x0 + e.x1) / 2}
              y={10}
              text-anchor="middle"
              font-size="8.5"
              letter-spacing=".1em"
              font-family={MONO}
              fill="var(--ink-mute)"
            >
              {eraLabel(e.name, e.x1 - e.x0)}
            </text>
          </>
        )}
      </For>
    </g>
  );
}

/** A `//` break over a stretch of the axis that has been compressed. */
function AxisBreak(props: { x: number }) {
  return (
    <g class="net-arc-break">
      <rect x={props.x - 3} y={BASE_Y - 4} width={6} height={8} />
      <line x1={props.x - 4} x2={props.x - 1} y1={BASE_Y + 4} y2={BASE_Y - 4} />
      <line x1={props.x + 1} x2={props.x + 4} y1={BASE_Y + 4} y2={BASE_Y - 4} />
    </g>
  );
}

function AuthorLabel(props: {
  author: ArcAuthor;
  x: number;
  active: string | null;
  pinned: boolean;
  linked: boolean;
  onPreview: (name: string | null) => void;
  onToggle: (name: string) => void;
}) {
  const y = BASE_Y - 8;
  const name = () => props.author.name;
  const emphasis = () => {
    if (!props.active) return {};
    if (props.active === name()) return { "font-weight": 600 };
    return props.linked ? {} : { opacity: 0.35 };
  };
  return (
    <g
      class="net-arc-label"
      role="button"
      tabindex="0"
      aria-pressed={props.pinned}
      aria-label={`${name()}: show citations`}
      onMouseEnter={() => props.onPreview(name())}
      onMouseLeave={() => props.onPreview(null)}
      onClick={() => props.onToggle(name())}
      onKeyDown={(e) => {
        if (e.key !== "Enter" && e.key !== " ") return;
        e.preventDefault();
        props.onToggle(name());
      }}
    >
      <line x1={props.x} x2={props.x} y1={BASE_Y - 4} y2={BASE_Y} />
      <rect x={props.x - 5.5} y={26} width={11} height={BASE_Y - 22} />
      <text
        x={props.x + 3.5}
        y={y}
        transform={`rotate(-90 ${props.x + 3.5} ${y})`}
        font-size="10.5"
        font-family="var(--sans)"
        fill={props.author.scrip ? "var(--net-terra)" : "var(--ink)"}
        {...emphasis()}
      >
        {props.author.short}
      </text>
    </g>
  );
}

const TIP_W = 240;
const TIP_OFFSET = 14;

function ArcTooltip(props: {
  hover: { pair: AuthorPair; x: number; y: number };
  byName: ReadonlyMap<string, ArcAuthor>;
  width: number;
}) {
  const p = () => props.hover.pair;
  // Right of the cursor, flipping left near the right edge.
  const left = () =>
    props.hover.x + TIP_OFFSET + TIP_W > props.width
      ? Math.max(0, props.hover.x - TIP_OFFSET - TIP_W)
      : props.hover.x + TIP_OFFSET;
  const reach = () => {
    const s = props.byName.get(p().src);
    const t = props.byName.get(p().tgt);
    if (!s?.dated || !t?.dated) return null;
    return `reaches back ${(s.year - t.year).toLocaleString()} years · ${formatYearEra(t.year)}`;
  };
  return (
    <div
      class="net-tooltip"
      style={{ left: `${left()}px`, top: `${props.hover.y + TIP_OFFSET}px` }}
    >
      <div class="pair">
        {p().src}
        <span class="arr">→</span>
        {p().tgt}
      </div>
      <div class="count">
        {p().n.toLocaleString()} reference{p().n === 1 ? "" : "s"}
      </div>
      <Show when={reach()}>{(r) => <div class="sub">{r()}</div>}</Show>
      <div class="hint">click arc to open</div>
    </div>
  );
}
