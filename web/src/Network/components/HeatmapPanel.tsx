import { For, createMemo } from "solid-js";
import type { HeatmapCell, HeatmapSection } from "~/api/networkApi";
import { useElementSize } from "~/hooks/useElementSize";

/** Ten ramp swatches. Module-level so `<For>` sees one stable array. */
const legendSwatches = Array.from({ length: 10 }, (_, i) => i);

export function HeatmapPanel(props: {
  authors: string[];
  sections: HeatmapSection[];
  cells: HeatmapCell[];
}) {
  let wrapEl: HTMLDivElement | undefined;
  const size = useElementSize(() => wrapEl, { w: 700, h: 280 });

  // Column order, flattened across sections. Deliberately independent of
  // `size()`: `<For>` keys on item identity, so a memo that recomputed on
  // every ResizeObserver tick would hand it a fresh array and it would
  // rebuild the grid — the defect this replaced (#200). Depending only on
  // `props.sections` means a resize changes attributes, not structure.
  const books = createMemo(() => props.sections.flatMap((s) => s.books));

  // Section bands, carrying the column span each one covers so the
  // divider and label can be placed from `layout()` at render time.
  // Same reasoning as `books`: no `size()` dependency.
  const bands = createMemo(() => {
    let start = 0;
    return props.sections.map((s) => {
      const band = { name: s.name.toUpperCase(), start, count: s.books.length };
      start += s.books.length;
      return band;
    });
  });

  const layout = createMemo(() => {
    const { w, h } = size();
    const padL = 84,
      padT = 38,
      padR = 8,
      padB = 22;
    const cols = Math.max(1, books().length);
    const rows = Math.max(1, props.authors.length);
    const cellW = (w - padL - padR) / cols;
    const cellH = (h - padT - padB) / rows;
    return { w, h, padL, padT, padR, padB, cols, rows, cellW, cellH };
  });

  const colX = (index: number) => layout().padL + index * layout().cellW;

  const legendX = () => layout().padL;
  const legendY = () => size().h - layout().padB + 6;

  const counts = createMemo(() => {
    const m = new Map<string, number>();
    for (const c of props.cells) m.set(`${c.author}|${c.book}`, c.n);
    return m;
  });

  const maxN = createMemo(() =>
    Math.max(1, ...props.cells.map((c) => c.n)),
  );

  function ramp(n: number) {
    if (!n) return "var(--paper-soft)";
    const t = Math.log10(n + 1) / Math.log10(maxN() + 1);
    const a = Math.max(0.08, Math.min(1, t));
    return `color-mix(in oklab, var(--net-terra) ${(a * 100).toFixed(0)}%, var(--paper))`;
  }

  return (
    <section class="net-panel" data-panel="heatmap">
      <div class="net-panel-head">
        <div>
          <div class="net-panel-title">Scripture citation heatmap</div>
          <div class="net-panel-q">
            Which biblical books do post-classical authors lean on?
          </div>
        </div>
      </div>
      <div class="net-panel-body">
        <div class="net-heatmap-wrap">
          <div class="net-heatmap-svg-wrap" ref={wrapEl}>
            <svg
              width={size().w}
              height={size().h}
              viewBox={`0 0 ${size().w} ${size().h}`}
              style={{ display: "block" }}
            >
              {/* cells + rotated book labels, one column per book */}
              <For each={books()}>
                {(book, col) => (
                  <>
                    <For each={props.authors}>
                      {(author, row) => {
                        const n = () => counts().get(`${author}|${book}`) ?? 0;
                        return (
                          <rect
                            x={colX(col())}
                            y={layout().padT + row() * layout().cellH}
                            width={layout().cellW - 0.5}
                            height={layout().cellH - 0.5}
                            fill={ramp(n())}
                          >
                            <title>
                              {author} → {book}: {n().toLocaleString()}
                            </title>
                          </rect>
                        );
                      }}
                    </For>
                    <text
                      x={colX(col()) + layout().cellW / 2}
                      y={layout().padT - 5}
                      font-size="8.5"
                      fill="var(--ink-mute)"
                      font-family="var(--sans)"
                      text-anchor="start"
                      transform={`rotate(-50 ${colX(col()) + layout().cellW / 2} ${layout().padT - 5})`}
                    >
                      {book}
                    </text>
                  </>
                )}
              </For>
              {/* section dividers + band labels. Emitted after the cells
                  so the dashed divider paints on top of them rather than
                  under the next section's first column. */}
              <For each={bands()}>
                {(band) => (
                  <>
                    <line
                      x1={colX(band.start + band.count) - 0.5}
                      x2={colX(band.start + band.count) - 0.5}
                      y1={layout().padT - 14}
                      y2={layout().padT + layout().rows * layout().cellH + 4}
                      stroke="var(--rule)"
                      stroke-width={0.6}
                      stroke-dasharray="2 2"
                    />
                    <text
                      x={colX(band.start) + (band.count * layout().cellW) / 2}
                      y={14}
                      text-anchor="middle"
                      font-size="9.5"
                      fill="var(--ink)"
                      letter-spacing="0.14em"
                      font-weight="600"
                      font-family="var(--sans)"
                    >
                      {band.name}
                    </text>
                  </>
                )}
              </For>
              {/* row labels */}
              <For each={props.authors}>
                {(a, r) => (
                  <text
                    x={layout().padL - 6}
                    y={layout().padT + r() * layout().cellH + layout().cellH / 2 + 3}
                    text-anchor="end"
                    font-size="10"
                    fill="var(--ink)"
                    font-family="var(--sans)"
                  >
                    {a}
                  </text>
                )}
              </For>
              {/* mini ramp legend. `legendSwatches` is a constant list so
                  `<For>` keys on stable items; the IIFE that used to wrap
                  this rebuilt the swatches on every resize purely to hold
                  two local coordinates. */}
              <For each={legendSwatches}>
                {(i) => (
                  <rect
                    x={legendX() + i * 9}
                    y={legendY()}
                    width={8.5}
                    height={6}
                    fill={ramp(Math.pow(10, (i / 9) * Math.log10(maxN())))}
                  />
                )}
              </For>
              <text
                x={legendX() + 100}
                y={legendY() + 5}
                font-size="9"
                fill="var(--ink-mute)"
                font-family="ui-monospace, SFMono-Regular, Menlo, monospace"
              >
                log n · low → high
              </text>
            </svg>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ============================================================
   Verification + leaderboard
   ============================================================ */
