import { For, Show, createMemo, createSignal, onMount } from "solid-js";
import type { AuthorPair, MatrixCell, NetworkAuthor } from "~/api/networkApi";
import { ATLAS_AUTHORS } from "~/Landing/atlasData";
import { ArcPanelTopStrip } from "~/Network/components/ArcPanelTopStrip";

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

// Map author name → actual year (negative = BCE). The NetworkAuthor
// shape we get from the backend carries `ord` — a sort ordinal from
// `author_ordering.py` (50 for Hebrew Bible, 100 for Homer, 200 for
// Thales, …). Earlier this component displayed `${a.ord} BC` on the
// arc's baseline label, which made Hebrew Bible read "50 BC" instead
// of ~1000 BC and Homer "100 BC" instead of 800 BC — off by an order
// of magnitude. Years come from ATLAS_AUTHORS instead (the same
// table the landing chronological strip already uses).
const YEAR_BY_NAME: ReadonlyMap<string, number> = new Map(
  ATLAS_AUTHORS.map((a) => [a.name, a.year]),
);

function formatYear(year: number): string {
  return year < 0 ? `${Math.abs(year)} BC` : `${year} CE`;
}

export function ArcPanel(props: {
  authors: NetworkAuthor[];
  /** Full matrix sparse cells: every author-pair the index has,
   *  not just top-N. We use these to progressively reveal lower-
   *  volume pairs as the user zooms in — wider horizontal space
   *  earns more arcs to fill it. */
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
  const [size, setSize] = createSignal({ w: 700, h: 460 });
  const [hideIntra, setHideIntra] = createSignal(true);
  // Horizontal zoom multiplier (1× = fit, 5× = compressed periods
  // pulled apart). Pan offset is managed by the scroll container —
  // no separate panX signal needed. ``stripH`` (96 px) is reserved
  // for the non-zooming top-pairs strip that sits below the arcs.
  const [zoom, setZoom] = createSignal(1);
  const STRIP_H = 96;
  // Cursor-following tooltip for arc hover. ``x`` / ``y`` are in
  // ``.net-arc-wrap``-relative pixels; we offset the rendered tooltip
  // 14 px below the cursor so it doesn't overlap the arc itself.
  const [hovered, setHovered] = createSignal<
    { pair: AuthorPair; x: number; y: number } | null
  >(null);
  let wrapEl: HTMLDivElement | undefined;
  let stageEl: HTMLDivElement | undefined;

  onMount(() => {
    if (!wrapEl) return;
    const ro = new ResizeObserver(() => {
      // wrapEl can be undefined at observer-fire time if the component
      // unmounted between observe() and the next layout — TS can't see
      // that path because the outer guard narrowed in scope.
      // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
      if (!wrapEl) return;
      setSize({ w: wrapEl.clientWidth, h: wrapEl.clientHeight });
    });
    ro.observe(wrapEl);
    setSize({ w: wrapEl.clientWidth, h: wrapEl.clientHeight });
  });

  const idxOf = createMemo(() => {
    const m = new Map<string, number>();
    props.authors.forEach((a, i) => m.set(a.name, i));
    return m;
  });

  // Compute how many additional pairs (beyond the curated top-N
  // baseline) to surface at the current zoom level. At 1× we stick
  // with the baseline; each additional zoom step earns more arcs
  // until 5× shows roughly an order of magnitude more pairs.
  const zoomPairBudget = createMemo(() => {
    const z = zoom();
    if (z <= 1.001) return 0;
    // Quadratic-ish growth: 2× → +60, 3× → +180, 4× → +330, 5× → +500
    return Math.round((z - 1) * (z - 1) * 30 + (z - 1) * 30);
  });

  const visiblePairs = createMemo(() => {
    // Baseline strategy (zoom-independent):
    //  • volume rank (topPairsNonScrip / topPairsAll)
    //  • per-author top 3 (topPairsPerAuthor) — guarantees every
    //    major thinker shows their top engagements even if their
    //    volume sits below the volumetric cutoff (e.g. Hegel→
    //    Heraclitus at 49 is rank ~36 in non_scrip but is Hegel's
    //    #6 outgoing edge and pedagogically central).
    const baseline = hideIntra() ? props.topPairsNonScrip : props.topPairsAll;
    const supplemental = hideIntra() ? props.topPairsPerAuthor : [];
    const seen = new Set<string>();
    const out = selectArcPairs(baseline, supplemental, {
      validNames: new Set(idxOf().keys()),
    });
    for (const p of out) {
      seen.add(`${p.src}\x00${p.tgt}`);
    }

    // Zoom-progressive layer: at >1× pull in additional pairs from
    // the full matrix.cells sorted by count desc. The new horizontal
    // space earns finer-grained detail. We reconstruct AuthorPair
    // shape from (r, c, n) by name lookup; intra_scrip is recomputed
    // from the author's corpus bucket so the strip's intra-scripture
    // classification stays consistent.
    const budget = zoomPairBudget();
    if (budget > 0 && props.matrixCells.length > 0) {
      const cells = [...props.matrixCells].sort((a, b) => b.n - a.n);
      let added = 0;
      for (const cell of cells) {
        if (added >= budget) break;
        const src = props.authors[cell.r]?.name;
        const tgt = props.authors[cell.c]?.name;
        if (!src || !tgt) continue;
        const key = `${src}\x00${tgt}`;
        if (seen.has(key)) continue;
        const srcBucket = props.authors[cell.r]?.corpus;
        const tgtBucket = props.authors[cell.c]?.corpus;
        const isc = srcBucket === "scrip" && tgtBucket === "scrip";
        if (hideIntra() && isc) continue;
        seen.add(key);
        out.push({ src, tgt, n: cell.n, intra_scrip: isc });
        added++;
      }
    }
    return out;
  });

  const layout = createMemo(() => {
    const { w, h } = size();
    const padL = 24,
      padR = 24,
      padT = 32;
    const stripH = STRIP_H;
    // The arcs render in their own SVG above the strip; this leaves
    // ``arcH`` pixels for the arcs and STRIP_H below for the (fixed)
    // top-pairs data strip.
    const arcH = Math.max(120, h - stripH);
    const stripY = arcH; // strip sits in a separate SVG; this only
    // affects the arc-area baseY math.
    const N = Math.max(1, props.authors.length);
    // ``w`` is the wrap width; the *arc* SVG width is ``w * zoom``
    // so the arcs spread out when zoomed. The strip stays at ``w``.
    const arcW = w * zoom();
    const innerW = arcW - padL - padR;
    const xs = props.authors.map(
      (_, i) => padL + (innerW * i) / Math.max(1, N - 1),
    );
    const baseY = padT;
    const maxDip = arcH - baseY - 12;
    const arcMaxR = Math.max(
      1,
      ...visiblePairs().map(
        (p) => Math.abs(xs[idxOf().get(p.tgt)!] - xs[idxOf().get(p.src)!]) / 2,
      ),
    );
    return {
      w, h, arcW, arcH, padL, padR, padT, stripH, stripY,
      xs, baseY, maxDip, arcMaxR,
    };
  });

  // Strip layout uses the un-zoomed wrap width so it stays fixed
  // while the arc area scrolls horizontally.
  const stripLayout = createMemo(() => {
    const { w } = size();
    const padL = 24, padR = 24;
    return { w, padL, padR };
  });

  // Zoom controls. Re-center the scroll viewport on the previous
  // midpoint so zooming feels anchored.
  function setZoomCentered(next: number) {
    const clamped = Math.max(1, Math.min(5, next));
    if (!stageEl) {
      setZoom(clamped);
      return;
    }
    const prevW = size().w * zoom();
    const nextW = size().w * clamped;
    const viewW = stageEl.clientWidth;
    const prevMid = stageEl.scrollLeft + viewW / 2;
    const ratio = prevW > 0 ? prevMid / prevW : 0.5;
    setZoom(clamped);
    queueMicrotask(() => {
      // stageEl can be undefined at microtask-fire time if the
      // component unmounted between the setZoom and the next tick.
      // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
      if (!stageEl) return;
      stageEl.scrollLeft = ratio * nextW - viewW / 2;
    });
  }
  function zoomIn() { setZoomCentered(zoom() * 1.5); }
  function zoomOut() { setZoomCentered(zoom() / 1.5); }
  function zoomReset() { setZoomCentered(1); }

  function onWheel(e: WheelEvent) {
    // Cmd/Ctrl + wheel = zoom. Plain wheel just scrolls horizontally
    // (default browser behavior in the scroll container).
    if (e.metaKey || e.ctrlKey) {
      e.preventDefault();
      const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
      setZoomCentered(zoom() * factor);
    }
  }

  const maxN = createMemo(() =>
    Math.max(1, ...visiblePairs().map((p) => p.n)),
  );

  function arcStroke(p: AuthorPair) {
    return p.intra_scrip
      ? "var(--net-terra)"
      : "var(--net-navy)";
  }
  function strokeW(n: number) {
    // Base + log-scaled, with a mild zoom-dependent bump so thin
    // arcs don't dissolve into the wider stage at higher zoom. The
    // floor lifts from 0.6 → ~1.2 at 5×, and the dynamic range
    // grows proportionally so heavy arcs stay distinguishably thick.
    const z = zoom();
    const base = 0.6 + (z - 1) * 0.15;
    const range = 3.4 + (z - 1) * 0.3;
    return base + (Math.log10(n + 1) / Math.log10(maxN() + 1)) * range;
  }
  function dipFor(r: number) {
    return Math.sqrt(r / layout().arcMaxR) * layout().maxDip * 0.96;
  }
  function arcPath(p: AuthorPair) {
    const x1 = layout().xs[idxOf().get(p.src)!];
    const x2 = layout().xs[idxOf().get(p.tgt)!];
    const ctrlY = layout().baseY + dipFor(Math.abs(x2 - x1) / 2);
    return `M ${x1} ${layout().baseY} Q ${(x1 + x2) / 2} ${ctrlY} ${x2} ${layout().baseY}`;
  }

  const topStrip = createMemo(() => visiblePairs().slice(0, 5));

  return (
    <section class="net-panel" data-panel="arc">
      <div class="net-panel-head">
        <div>
          <div class="net-panel-title">Chronological arc diagram</div>
          <div class="net-panel-q">
            Which authors reach back furthest, and to whom?
          </div>
        </div>
        <div class="net-arc-zoom" role="group" aria-label="Zoom">
          <button
            class="net-arc-zoom-btn"
            onClick={zoomOut}
            disabled={zoom() <= 1.001}
            aria-label="Zoom out"
            title="Zoom out (⌘− or ⌘-wheel)"
          >−</button>
          <span
            class="net-arc-zoom-level"
            onClick={zoomReset}
            title="Reset zoom"
            role="button"
          >{zoom().toFixed(1)}×</span>
          <button
            class="net-arc-zoom-btn"
            onClick={zoomIn}
            disabled={zoom() >= 4.99}
            aria-label="Zoom in"
            title="Zoom in (⌘+ or ⌘-wheel)"
          >+</button>
        </div>
        <button
          class={"net-toggle" + (hideIntra() ? " on" : "")}
          onClick={() => setHideIntra((v) => !v)}
        >
          <span class="sw" /> Hide intra-scripture
        </button>
      </div>
      <div class="net-panel-body">
        <div class="net-arc-wrap" ref={wrapEl}>
          {/* Scrollable arc stage. Width = wrap * zoom so the
              arcs spread out when zoomed; the wrap clips and the
              inner div scrolls horizontally. */}
          <div
            class="net-arc-stage"
            ref={stageEl}
            onWheel={onWheel}
            style={{ height: `${layout().arcH}px` }}
          >
          <svg
            width={layout().arcW}
            height={layout().arcH}
            viewBox={`0 0 ${layout().arcW} ${layout().arcH}`}
            style={{ display: "block" }}
          >
            <line
              x1={layout().padL - 4}
              x2={layout().arcW - layout().padR + 4}
              y1={layout().baseY}
              y2={layout().baseY}
              stroke="var(--ink)"
              stroke-width={0.6}
            />
            {/* tick marks + labels. At 1× zoom we show a hand-picked
                sparse set (so rotated names don't collide). At higher
                zoom the wider stage earns more labels — at 2× ~half
                the authors, at 3× all of them. Labels for un-named
                authors collapse to dots until the zoom allows. */}
            <For each={props.authors}>
              {(a, i) => {
                const SPARSE_LABELS = new Set([
                  "Hebrew Bible", "Homer", "Plato", "Cicero", "Septuagint",
                  "Vulgate", "Augustine", "Aquinas", "Descartes", "Kant",
                  "Nietzsche",
                ]);
                const MID_LABELS = new Set([
                  ...SPARSE_LABELS,
                  "Heraclitus", "Parmenides", "Aristotle", "New Testament",
                  "Epictetus", "Marcus Aurelius", "Quran",
                  "Luther Bibel 1912", "King James Bible", "Sacy",
                  "Hobbes", "Hume", "Hegel", "Marx",
                ]);
                // Reactive accessor — must call ``zoom()`` inside an
                // accessor so the ``<Show>`` below re-evaluates when
                // the zoom signal changes. A captured const would
                // freeze at first render.
                const showLabel = () =>
                  zoom() >= 2.6 ? true
                  : zoom() >= 1.5 ? MID_LABELS.has(a.name)
                  : SPARSE_LABELS.has(a.name);
                return (
                  <>
                    <line
                      x1={layout().xs[i()]}
                      x2={layout().xs[i()]}
                      y1={layout().baseY - 3}
                      y2={layout().baseY}
                      stroke="var(--ink-mute)"
                      stroke-width={0.6}
                    />
                    <Show when={showLabel()}>
                      <text
                        x={layout().xs[i()]}
                        y={layout().baseY - 14}
                        font-size="9.5"
                        font-family="var(--sans)"
                        fill={
                          a.corpus === "scrip"
                            ? "var(--net-terra)"
                            : "var(--ink)"
                        }
                        text-anchor="middle"
                      >
                        {a.short}
                      </text>
                      <Show when={YEAR_BY_NAME.has(a.name)}>
                        <text
                          x={layout().xs[i()]}
                          y={layout().baseY - 5}
                          font-size="8.5"
                          font-family="ui-monospace, SFMono-Regular, Menlo, monospace"
                          fill="var(--ink-faint)"
                          text-anchor="middle"
                        >
                          {formatYear(YEAR_BY_NAME.get(a.name)!)}
                        </text>
                      </Show>
                    </Show>
                    <Show when={!showLabel}>
                      <circle
                        cx={layout().xs[i()]}
                        cy={layout().baseY}
                        r={1.1}
                        fill="var(--ink-mute)"
                      />
                    </Show>
                  </>
                );
              }}
            </For>
            {/* arcs */}
            <For each={visiblePairs()}>
              {(p) => (
                <path
                  d={arcPath(p)}
                  fill="none"
                  stroke={arcStroke(p)}
                  stroke-width={strokeW(p.n)}
                  stroke-opacity={hovered()?.pair === p ? 0.85 : 0.55}
                  stroke-linecap="round"
                  style={{ cursor: "pointer" }}
                  onClick={() => props.onOpenPair(p.src, p.tgt)}
                  onMouseMove={(e) => {
                    if (!wrapEl) return;
                    const rect = wrapEl.getBoundingClientRect();
                    setHovered({
                      pair: p,
                      x: e.clientX - rect.left,
                      y: e.clientY - rect.top,
                    });
                  }}
                  onMouseLeave={() => setHovered(null)}
                />
              )}
            </For>
          </svg>
          </div>
          <ArcPanelTopStrip
            width={stripLayout().w}
            padL={stripLayout().padL}
            padR={stripLayout().padR}
            hideIntra={hideIntra()}
            pairs={topStrip()}
            onOpenPair={props.onOpenPair}
          />
          <Show when={hovered()}>
            {(h) => {
              // Tooltip width is ~240 px (per `.net-tooltip` CSS).
              // Right-edge clamp keeps it inside `.net-arc-wrap`;
              // when the cursor is near the right edge we flip it to
              // the left of the cursor instead of the default right.
              const tipW = 240;
              const offset = 14;
              const tipX = () =>
                h().x + offset + tipW > size().w
                  ? Math.max(0, h().x - offset - tipW)
                  : h().x + offset;
              const tipY = () => h().y + offset;
              return (
                <div
                  class="net-tooltip"
                  style={{
                    left: `${tipX()}px`,
                    top: `${tipY()}px`,
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
                  <div class="hint">CLICK ARC TO OPEN</div>
                </div>
              );
            }}
          </Show>
        </div>
      </div>
    </section>
  );
}

/* ============================================================
   Scripture heatmap
   ============================================================ */
