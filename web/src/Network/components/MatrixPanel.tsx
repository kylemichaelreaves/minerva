import { For, Show, createMemo, createSignal, onMount } from "solid-js";
import type { MatrixCell, NetworkAuthor } from "~/api/networkApi";
import { CORPUS_YEAR_SPAN_LABEL } from "~/Landing/corpusFacts";

export function MatrixPanel(props: {
  authors: NetworkAuthor[];
  cells: MatrixCell[];
  onOpenPair: (source: string, target: string) => void;
}) {
  const [size, setSize] = createSignal({ w: 720, h: 460 });
  let wrapEl: HTMLDivElement | undefined;
  const [hover, setHover] = createSignal<MatrixCell | null>(null);

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
    const N = props.authors.length || 1;
    const padL = 78,
      padT = 72,
      padR = 8,
      padB = 12;
    const cellW = (w - padL - padR) / N;
    const cellH = (h - padT - padB) / N;
    const cell = Math.max(2, Math.min(cellW, cellH));
    return { w, h, N, padL, padT, padR, padB, cell };
  });

  const maxN = createMemo(() => Math.max(1, ...props.cells.map((c) => c.n)));

  function rampColor(n: number) {
    if (!n) return "transparent";
    const t = Math.log10(n + 1) / Math.log10(maxN() + 1);
    const a = Math.max(0.08, Math.min(1, t));
    return `color-mix(in oklab, var(--net-navy) ${(a * 100).toFixed(0)}%, var(--paper))`;
  }

  return (
    <section class="net-panel" data-panel="matrix">
      <div class="net-panel-head">
        <div>
          <div class="net-panel-title">Author × Author citation matrix</div>
          <div class="net-panel-q">
            Who, across {CORPUS_YEAR_SPAN_LABEL} years, cited whom — and how heavily?
          </div>
        </div>
        <div class="net-segment">
          <button class="on">Counts</button>
        </div>
      </div>
      <div class="net-panel-body">
        <div class="net-matrix-wrap">
          <div class="net-matrix-legend">
            <div class="ramp">
              <span>log&nbsp;n</span>
              <span class="net-ramp-bar">
                <For each={[0, 1, 10, 100, 1000, 10000]}>
                  {(v) => <span style={{ background: rampColor(v) }} />}
                </For>
              </span>
              <span>1 → 10⁴</span>
            </div>
            <div>rows = citing &nbsp;·&nbsp; cols = cited &nbsp;·&nbsp; sort = chronological</div>
          </div>
          <div class="net-matrix-svg-wrap" ref={wrapEl}>
            <svg
              width={layout().w}
              height={layout().h}
              viewBox={`0 0 ${layout().w} ${layout().h}`}
              style={{ display: "block" }}
            >
              {/* background grid (paper-edge alternating per row for readability) */}
              <For each={props.authors}>
                {(_, r) => (
                  <rect
                    x={layout().padL}
                    y={layout().padT + r() * layout().cell}
                    width={layout().N * layout().cell}
                    height={layout().cell - 0.4}
                    fill={r() % 2 === 0 ? "var(--paper)" : "var(--paper-soft)"}
                  />
                )}
              </For>
              {/* diagonal hairline */}
              <line
                x1={layout().padL}
                y1={layout().padT}
                x2={layout().padL + layout().N * layout().cell}
                y2={layout().padT + layout().N * layout().cell}
                stroke="var(--rule)"
                stroke-width={0.5}
                stroke-dasharray="2 2"
              />
              {/* nonzero cells */}
              <For each={props.cells}>
                {(c) => (
                  <rect
                    class="net-cell"
                    x={layout().padL + c.c * layout().cell}
                    y={layout().padT + c.r * layout().cell}
                    width={layout().cell - 0.4}
                    height={layout().cell - 0.4}
                    fill={rampColor(c.n)}
                    onMouseEnter={() => setHover(c)}
                    onMouseLeave={() => setHover(null)}
                    onClick={() =>
                      props.onOpenPair(props.authors[c.r].name, props.authors[c.c].name)
                    }
                  >
                    <title>
                      {props.authors[c.r].name} → {props.authors[c.c].name}: {c.n.toLocaleString()}
                    </title>
                  </rect>
                )}
              </For>
              {/* row labels — citing (left) */}
              <For each={props.authors}>
                {(a, r) => (
                  <text
                    x={layout().padL - 6}
                    y={layout().padT + r() * layout().cell + layout().cell / 2 + 3}
                    text-anchor="end"
                    font-size={String(Math.min(10.5, layout().cell + 2))}
                    font-family="var(--sans)"
                    fill={a.corpus === "scrip" ? "var(--net-terra)" : "var(--ink)"}
                  >
                    {a.short}
                  </text>
                )}
              </For>
              {/* col labels — cited (top, rotated 45°) */}
              <For each={props.authors}>
                {(a, c) => {
                  const x = layout().padL + c() * layout().cell + layout().cell / 2;
                  return (
                    <text
                      x={x}
                      y={layout().padT - 6}
                      font-size={String(Math.min(10.5, layout().cell + 2))}
                      font-family="var(--sans)"
                      fill={a.corpus === "scrip" ? "var(--net-terra)" : "var(--ink)"}
                      transform={`rotate(-45 ${x} ${layout().padT - 6})`}
                      text-anchor="start"
                    >
                      {a.short}
                    </text>
                  );
                }}
              </For>
              {/* axis captions */}
              <text
                x={8}
                y={layout().padT - 18}
                font-size="9.5"
                fill="var(--ink-mute)"
                font-family="ui-monospace, SFMono-Regular, Menlo, monospace"
              >
                citing ↓
              </text>
              <text
                x={layout().padL - 4}
                y={layout().padT - 56}
                font-size="9.5"
                fill="var(--ink-mute)"
                font-family="ui-monospace, SFMono-Regular, Menlo, monospace"
              >
                cited →
              </text>
            </svg>
            <Show when={hover()}>
              <MatrixTooltip authors={props.authors} cell={hover()!} layout={layout()} />
            </Show>
          </div>
          <div class="net-matrix-strip">
            <span class="label">drill-down</span>
            <span>
              Click any cell to open <em>/refs</em> filtered to that source → target pair.
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}

function MatrixTooltip(props: {
  authors: NetworkAuthor[];
  cell: MatrixCell;
  layout: { padL: number; padT: number; cell: number; w: number; h: number };
}) {
  const left = () => {
    const raw = props.layout.padL + (props.cell.c + 1) * props.layout.cell + 8;
    return Math.min(raw, props.layout.w - 260);
  };
  const top = () => {
    const raw = props.layout.padT + props.cell.r * props.layout.cell - 4;
    return Math.min(raw, props.layout.h - 90);
  };
  return (
    <div class="net-tooltip" style={{ left: `${left()}px`, top: `${top()}px` }}>
      <div class="pair">
        {props.authors[props.cell.r].name} <span class="arr">→</span>{" "}
        {props.authors[props.cell.c].name}
      </div>
      <div class="count">{props.cell.n.toLocaleString()} xrefs</div>
      <div class="hint">click to filter /refs ↘</div>
    </div>
  );
}

/* ============================================================
   Arc diagram + top-pairs strip
   ============================================================ */
