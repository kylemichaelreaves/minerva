import { For, createMemo, createSignal, onMount, type JSX } from "solid-js";
import type { HeatmapCell, HeatmapSection } from "~/api/networkApi";

export function HeatmapPanel(props: {
  authors: string[];
  sections: HeatmapSection[];
  cells: HeatmapCell[];
}) {
  const [size, setSize] = createSignal({ w: 700, h: 280 });
  let wrapEl: HTMLDivElement | undefined;

  onMount(() => {
    if (!wrapEl) return;
    const ro = new ResizeObserver(() => {
      // wrapEl can become undefined async; outer narrowing isn't visible here.
      // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
      if (!wrapEl) return;
      setSize({ w: wrapEl.clientWidth, h: wrapEl.clientHeight });
    });
    ro.observe(wrapEl);
    setSize({ w: wrapEl.clientWidth, h: wrapEl.clientHeight });
  });

  const layout = createMemo(() => {
    const { w, h } = size();
    const padL = 84,
      padT = 38,
      padR = 8,
      padB = 22;
    const allBooks = props.sections.flatMap((s) => s.books);
    const cols = Math.max(1, allBooks.length);
    const rows = Math.max(1, props.authors.length);
    const cellW = (w - padL - padR) / cols;
    const cellH = (h - padT - padB) / rows;
    return { w, h, padL, padT, padR, padB, cols, rows, cellW, cellH, allBooks };
  });

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
              {/* section headers + dividers */}
              {(() => {
                const elements: JSX.Element[] = [];
                let cx = layout().padL;
                for (const section of props.sections) {
                  const sectionStart = cx;
                  for (const book of section.books) {
                    // cells per author
                    for (let r = 0; r < layout().rows; r++) {
                      const author = props.authors[r];
                      const n = counts().get(`${author}|${book}`) ?? 0;
                      elements.push(
                        <rect
                          x={cx}
                          y={layout().padT + r * layout().cellH}
                          width={layout().cellW - 0.5}
                          height={layout().cellH - 0.5}
                          fill={ramp(n)}
                        >
                          <title>
                            {author} → {book}: {n.toLocaleString()}
                          </title>
                        </rect>,
                      );
                    }
                    // book label
                    elements.push(
                      <text
                        x={cx + layout().cellW / 2}
                        y={layout().padT - 5}
                        font-size="8.5"
                        fill="var(--ink-mute)"
                        font-family="var(--sans)"
                        text-anchor="start"
                        transform={`rotate(-50 ${cx + layout().cellW / 2} ${layout().padT - 5})`}
                      >
                        {book}
                      </text>,
                    );
                    cx += layout().cellW;
                  }
                  // section divider + label
                  elements.push(
                    <line
                      x1={cx - 0.5}
                      x2={cx - 0.5}
                      y1={layout().padT - 14}
                      y2={layout().padT + layout().rows * layout().cellH + 4}
                      stroke="var(--rule)"
                      stroke-width={0.6}
                      stroke-dasharray="2 2"
                    />,
                  );
                  elements.push(
                    <text
                      x={sectionStart + (section.books.length * layout().cellW) / 2}
                      y={14}
                      text-anchor="middle"
                      font-size="9.5"
                      fill="var(--ink)"
                      letter-spacing="0.14em"
                      font-weight="600"
                      font-family="var(--sans)"
                    >
                      {section.name.toUpperCase()}
                    </text>,
                  );
                }
                return elements;
              })()}
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
              {/* mini ramp legend */}
              {(() => {
                const lgX = layout().padL,
                  lgY = size().h - layout().padB + 6;
                return (
                  <>
                    <For each={Array.from({ length: 10 }, (_, i) => i)}>
                      {(i) => (
                        <rect
                          x={lgX + i * 9}
                          y={lgY}
                          width={8.5}
                          height={6}
                          fill={ramp(Math.pow(10, (i / 9) * Math.log10(maxN())))}
                        />
                      )}
                    </For>
                    <text
                      x={lgX + 100}
                      y={lgY + 5}
                      font-size="9"
                      fill="var(--ink-mute)"
                      font-family="ui-monospace, SFMono-Regular, Menlo, monospace"
                    >
                      log n · low → high
                    </text>
                  </>
                );
              })()}
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
