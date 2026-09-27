import { For, Show, createMemo, createSignal } from "solid-js";
import type { MatrixCell, NetworkAuthor } from "~/api/networkApi";
import { CORPUS_YEAR_SPAN_LABEL } from "~/features/Landing/corpusFacts";
import { useElementSize } from "~/hooks/useElementSize";
import {
  MODE_BINS,
  MODE_HINT,
  buildAxes,
  cellValue,
  bandLabel,
  pct,
  stepFor,
  type MatrixAxes,
  type MatrixMode,
} from "~/Network/components/matrixLayout";

const MODES: { id: MatrixMode; label: string }[] = [
  { id: "n", label: "Counts" },
  { id: "row", label: "% of row" },
  { id: "col", label: "% of col" },
];

const PAD = { l: 112, t: 104, r: 6, b: 6 };
const MONO = "ui-monospace, SFMono-Regular, Menlo, monospace";

interface Geometry {
  w: number;
  h: number;
  cw: number;
  ch: number;
  gridW: number;
  gridH: number;
}

export function MatrixPanel(props: {
  authors: NetworkAuthor[];
  cells: MatrixCell[];
  onOpenPair: (source: string, target: string) => void;
}) {
  let wrapEl: HTMLDivElement | undefined;
  const size = useElementSize(() => wrapEl, { w: 720, h: 460 });
  const [hover, setHover] = createSignal<MatrixCell | null>(null);
  const [mode, setMode] = createSignal<MatrixMode>("n");

  const axes = createMemo(() => buildAxes(props.authors, props.cells));

  // Cells are rectangles sized to width and height separately, so the
  // grid fills the panel instead of letterboxing to a square.
  const geo = createMemo<Geometry>(() => {
    const { w, h } = size();
    const gridW = Math.max(0, w - PAD.l - PAD.r);
    const gridH = Math.max(0, h - PAD.t - PAD.b);
    const cw = gridW / Math.max(1, axes().cols.length);
    const ch = gridH / Math.max(1, axes().rows.length);
    return { w, h, cw, ch, gridW, gridH };
  });

  const author = (i: number) => props.authors[i];
  const labelFill = (i: number) =>
    author(i)?.corpus === "scrip" ? "var(--net-terra)" : "var(--ink)";

  return (
    <section class="net-panel" data-panel="matrix">
      <div class="net-panel-head">
        <div>
          <div class="net-panel-title">Author × Author citation matrix</div>
          <div class="net-panel-q">
            Who, across {CORPUS_YEAR_SPAN_LABEL} years, cited whom — and how heavily?
          </div>
        </div>
        <div class="net-segment" role="group" aria-label="Cell values">
          <For each={MODES}>
            {(m) => (
              <button
                type="button"
                classList={{ on: mode() === m.id }}
                aria-pressed={mode() === m.id}
                onClick={() => setMode(m.id)}
              >
                {m.label}
              </button>
            )}
          </For>
        </div>
      </div>
      <div class="net-panel-body">
        <div class="net-matrix-wrap">
          <div class="net-matrix-legend">
            <div class="net-matrix-steps" aria-label="Colour scale">
              <For each={MODE_BINS[mode()].labels}>
                {(label, k) => (
                  <div>
                    <i style={{ background: `var(--net-step-${k()})` }} />
                    <span>{label}</span>
                  </div>
                )}
              </For>
            </div>
            <div>{MODE_HINT[mode()]}</div>
          </div>
          <div class="net-matrix-svg-wrap" ref={wrapEl}>
            <svg
              width={geo().w}
              height={geo().h}
              viewBox={`0 0 ${geo().w} ${geo().h}`}
              style={{ display: "block" }}
            >
              <rect
                x={PAD.l}
                y={PAD.t}
                width={geo().gridW}
                height={geo().gridH}
                fill="var(--net-matrix-field)"
              />
              <Show when={hover()}>
                {(c) => <Crosshair cell={c()} axes={axes()} geo={geo()} />}
              </Show>
              <Bands axes={axes()} geo={geo()} />
              <For each={axes().rows}>
                {(i) => (
                  <text
                    x={PAD.l - 6}
                    y={PAD.t + (axes().rowPos.get(i) ?? 0) * geo().ch + geo().ch / 2 + 3.5}
                    text-anchor="end"
                    font-size="10.5"
                    font-family="var(--sans)"
                    fill={labelFill(i)}
                    {...labelEmphasis(hover()?.r, i)}
                  >
                    {author(i)?.short}
                  </text>
                )}
              </For>
              <For each={axes().cols}>
                {(i) => {
                  const x = () =>
                    PAD.l + (axes().colPos.get(i) ?? 0) * geo().cw + geo().cw / 2 + 3.5;
                  const y = PAD.t - 6;
                  return (
                    <text
                      x={x()}
                      y={y}
                      transform={`rotate(-90 ${x()} ${y})`}
                      font-size="10.5"
                      font-family="var(--sans)"
                      fill={labelFill(i)}
                      {...labelEmphasis(hover()?.c, i)}
                    >
                      {author(i)?.short}
                    </text>
                  );
                }}
              </For>
              <For each={props.cells}>
                {(c) => (
                  <rect
                    class="net-cell"
                    x={PAD.l + (axes().colPos.get(c.c) ?? 0) * geo().cw + 0.5}
                    y={PAD.t + (axes().rowPos.get(c.r) ?? 0) * geo().ch + 0.5}
                    width={Math.max(0, geo().cw - 1)}
                    height={Math.max(0, geo().ch - 1)}
                    fill={`var(--net-step-${stepFor(cellValue(c, mode(), axes()), mode())})`}
                    onMouseEnter={() => setHover(c)}
                    onMouseLeave={() => setHover(null)}
                    onClick={() =>
                      props.onOpenPair(author(c.r)?.name ?? "", author(c.c)?.name ?? "")
                    }
                  >
                    <title>
                      {author(c.r)?.name} → {author(c.c)?.name}: {c.n.toLocaleString()}
                    </title>
                  </rect>
                )}
              </For>
            </svg>
            <Show when={hover()}>
              {(c) => (
                <MatrixTooltip authors={props.authors} cell={c()} axes={axes()} geo={geo()} />
              )}
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

/** While a cell is hovered, its row and column labels go bold and every
 *  other label fades. */
function labelEmphasis(hovered: number | undefined, i: number) {
  if (hovered === undefined) return {};
  return hovered === i ? { "font-weight": 600 } : { opacity: 0.45 };
}

function Crosshair(props: { cell: MatrixCell; axes: MatrixAxes; geo: Geometry }) {
  const r = () => props.axes.rowPos.get(props.cell.r) ?? 0;
  const c = () => props.axes.colPos.get(props.cell.c) ?? 0;
  return (
    <g class="net-matrix-crosshair" pointer-events="none">
      <rect
        x={PAD.l}
        y={PAD.t + r() * props.geo.ch}
        width={props.geo.gridW}
        height={props.geo.ch}
      />
      <rect
        x={PAD.l + c() * props.geo.cw}
        y={PAD.t}
        width={props.geo.cw}
        height={props.geo.gridH}
      />
    </g>
  );
}

/** Band dividers plus band captions: rotated down the left edge for
 *  rows, along the top edge for columns. */
function Bands(props: { axes: MatrixAxes; geo: Geometry }) {
  const bandText = { "font-size": "8.5", "font-family": MONO, fill: "var(--ink-mute)" };
  return (
    <g class="net-matrix-bands">
      <For each={props.axes.rowBands}>
        {(b, k) => {
          const y = () => PAD.t + b.start * props.geo.ch;
          const cy = () => PAD.t + ((b.start + b.end) / 2) * props.geo.ch;
          return (
            <>
              <Show when={k() > 0}>
                <line x1={6} x2={PAD.l + props.geo.gridW} y1={y()} y2={y()} />
              </Show>
              <text
                x={12}
                y={cy()}
                transform={`rotate(-90 12 ${cy()})`}
                text-anchor="middle"
                letter-spacing=".12em"
                {...bandText}
              >
                {bandLabel(b.corpus, (b.end - b.start) * props.geo.ch)}
              </text>
            </>
          );
        }}
      </For>
      <For each={props.axes.colBands}>
        {(b, k) => {
          const x = () => PAD.l + b.start * props.geo.cw;
          const width = () => (b.end - b.start) * props.geo.cw;
          return (
            <>
              <Show when={k() > 0}>
                <line x1={x()} x2={x()} y1={14} y2={PAD.t + props.geo.gridH} />
              </Show>
              <text
                x={x() + width() / 2}
                y={10}
                text-anchor="middle"
                letter-spacing=".12em"
                {...bandText}
              >
                {bandLabel(b.corpus, width())}
              </text>
            </>
          );
        }}
      </For>
    </g>
  );
}

const TIP_W = 240;
const TIP_H = 110;

function MatrixTooltip(props: {
  authors: NetworkAuthor[];
  cell: MatrixCell;
  axes: MatrixAxes;
  geo: Geometry;
}) {
  const src = () => props.authors[props.cell.r];
  const tgt = () => props.authors[props.cell.c];
  // Right of the cell, flipping to the left when it would overflow.
  const left = () => {
    const cellX = PAD.l + (props.axes.colPos.get(props.cell.c) ?? 0) * props.geo.cw;
    const right = cellX + props.geo.cw + 10;
    return right + TIP_W > props.geo.w ? Math.max(0, cellX - TIP_W - 10) : right;
  };
  const top = () => {
    const raw = PAD.t + (props.axes.rowPos.get(props.cell.r) ?? 0) * props.geo.ch - 6;
    return Math.max(0, Math.min(raw, props.geo.h - TIP_H));
  };
  return (
    <div class="net-tooltip" style={{ left: `${left()}px`, top: `${top()}px` }}>
      <div class="pair">
        {src()?.name} <span class="arr">→</span> {tgt()?.name}
      </div>
      <div class="count">{props.cell.n.toLocaleString()} xrefs</div>
      <div class="shares">
        {pct(props.cell.n, props.axes.rowTotal.get(props.cell.r))} of {src()?.short}’s citations
        <br />
        {pct(props.cell.n, props.axes.colTotal.get(props.cell.c))} of citations to {tgt()?.short}
      </div>
      <div class="hint">click to filter /refs ↘</div>
    </div>
  );
}
