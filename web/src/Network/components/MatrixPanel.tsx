import { For, Show, createEffect, createMemo, createSignal } from "solid-js";
import type { MatrixCell, NetworkAuthor } from "~/api/networkApi";
import { CORPUS_YEAR_SPAN_LABEL } from "~/features/Landing/corpusFacts";
import { useElementSize } from "~/hooks/useElementSize";
import {
  MODE_BINS,
  MODE_HINT,
  buildAxes,
  cellValue,
  bandLabel,
  gridRows,
  moveInGrid,
  pct,
  placeCells,
  stepFor,
  type GridCell,
  type GridMove,
  type MatrixAxes,
  type MatrixMode,
} from "~/Network/components/matrixLayout";

const MODES: { id: MatrixMode; label: string }[] = [
  { id: "n", label: "Counts" },
  { id: "row", label: "% of row" },
  { id: "col", label: "% of col" },
];

const PAD = { l: 112, t: 104, r: 6, b: 6 };

/** Keys that move focus between cells. */
const KEY_MOVES: Partial<Record<string, GridMove>> = {
  ArrowRight: "right",
  ArrowLeft: "left",
  ArrowUp: "up",
  ArrowDown: "down",
  Home: "home",
  End: "end",
};

const cellKey = (g: GridCell) => `${g.cell.r}:${g.cell.c}`;
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
  const [hover, setHover] = createSignal<GridCell | null>(null);
  const [mode, setMode] = createSignal<MatrixMode>("n");

  const axes = createMemo(() => buildAxes(props.authors, props.cells));
  const placed = createMemo(() => placeCells(props.cells, axes(), props.authors));

  // Roving tabindex (#696): the grid is one tab stop. `current` is the cell
  // that last had focus, so tabbing back returns to it; until one has, the
  // top-left cell holds the stop. `pending` is a cell an arrow key has
  // asked to focus — its rect focuses itself once it sees it.
  const [current, setCurrent] = createSignal<string | null>(null);
  const [pending, setPending] = createSignal<string | null>(null);
  const tabStop = createMemo(() => placed().find((g) => cellKey(g) === current()) ?? placed()[0]);
  const open = (g: GridCell) => props.onOpenPair(g.src.name, g.tgt.name);
  function onCellKey(e: KeyboardEvent, g: GridCell) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      open(g);
      return;
    }
    const move = KEY_MOVES[e.key];
    if (!move) return;
    e.preventDefault();
    const next = moveInGrid(placed(), g, move);
    if (next !== g) setPending(cellKey(next));
  }

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
              <Show when={hover()}>{(g) => <Crosshair g={g()} geo={geo()} />}</Show>
              <Bands axes={axes()} geo={geo()} />
              <For each={axes().rows}>
                {(i, pos) => (
                  <text
                    x={PAD.l - 6}
                    y={PAD.t + pos() * geo().ch + geo().ch / 2 + 3.5}
                    text-anchor="end"
                    font-size="10.5"
                    font-family="var(--sans)"
                    fill={labelFill(i)}
                    {...labelEmphasis(hover()?.cell.r, i)}
                  >
                    {author(i)?.short}
                  </text>
                )}
              </For>
              <For each={axes().cols}>
                {(i, pos) => {
                  const x = () => PAD.l + pos() * geo().cw + geo().cw / 2 + 3.5;
                  const y = PAD.t - 6;
                  return (
                    <text
                      x={x()}
                      y={y}
                      transform={`rotate(-90 ${x()} ${y})`}
                      font-size="10.5"
                      font-family="var(--sans)"
                      fill={labelFill(i)}
                      {...labelEmphasis(hover()?.cell.c, i)}
                    >
                      {author(i)?.short}
                    </text>
                  );
                }}
              </For>
              <g
                role="grid"
                aria-label="Citation matrix: each row cites each column"
                aria-rowcount={axes().rows.length}
                aria-colcount={axes().cols.length}
              >
                <For each={gridRows(placed())}>
                  {(row) => (
                    <g role="row" aria-rowindex={row.pos + 1}>
                      <For each={row.cells}>
                        {(g) => (
                          <MatrixCellRect
                            g={g}
                            geo={geo()}
                            fill={`var(--net-step-${stepFor(cellValue(g.cell, mode(), axes()), mode())})`}
                            tabbable={tabStop() === g}
                            focusNow={pending() === cellKey(g)}
                            onHover={setHover}
                            onFocus={() => {
                              setCurrent(cellKey(g));
                              setPending(null);
                              setHover(g);
                            }}
                            onKeyDown={(e) => onCellKey(e, g)}
                            onOpen={() => open(g)}
                          />
                        )}
                      </For>
                    </g>
                  )}
                </For>
              </g>
            </svg>
            <Show when={hover()}>{(g) => <MatrixTooltip g={g()} axes={axes()} geo={geo()} />}</Show>
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

/** One matrix cell: a gridcell in the roving-tabindex grid. Focus shows
 *  the same tooltip and crosshair as hover (via `onHover`). */
function MatrixCellRect(props: {
  g: GridCell;
  geo: Geometry;
  fill: string;
  tabbable: boolean;
  /** An arrow key moved here: take focus. */
  focusNow: boolean;
  onHover: (g: GridCell | null) => void;
  onFocus: () => void;
  onKeyDown: (e: KeyboardEvent) => void;
  onOpen: () => void;
}) {
  const label = () =>
    `${props.g.src.name} → ${props.g.tgt.name}: ${props.g.cell.n.toLocaleString()} xrefs`;
  return (
    <rect
      ref={(el) => {
        createEffect(() => {
          if (props.focusNow) el.focus();
        });
      }}
      class="net-cell"
      role="gridcell"
      aria-colindex={props.g.col + 1}
      aria-label={label()}
      tabindex={props.tabbable ? 0 : -1}
      x={PAD.l + props.g.col * props.geo.cw + 0.5}
      y={PAD.t + props.g.row * props.geo.ch + 0.5}
      width={Math.max(0, props.geo.cw - 1)}
      height={Math.max(0, props.geo.ch - 1)}
      fill={props.fill}
      onMouseEnter={() => props.onHover(props.g)}
      onMouseLeave={() => props.onHover(null)}
      onFocus={() => props.onFocus()}
      onBlur={() => props.onHover(null)}
      onKeyDown={(e) => props.onKeyDown(e)}
      onClick={() => props.onOpen()}
    >
      <title>
        {props.g.src.name} → {props.g.tgt.name}: {props.g.cell.n.toLocaleString()}
      </title>
    </rect>
  );
}

/** While a cell is hovered, its row and column labels go bold and every
 *  other label fades. */
function labelEmphasis(hovered: number | undefined, i: number) {
  if (hovered === undefined) return {};
  return hovered === i ? { "font-weight": 600 } : { opacity: 0.45 };
}

/** Takes the placed cell, so its position is known rather than looked up
 *  with a fallback that can never fire (#728). */
function Crosshair(props: { g: GridCell; geo: Geometry }) {
  const r = () => props.g.row;
  const c = () => props.g.col;
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

function MatrixTooltip(props: { g: GridCell; axes: MatrixAxes; geo: Geometry }) {
  const cell = () => props.g.cell;
  const src = () => props.g.src;
  const tgt = () => props.g.tgt;
  // Right of the cell, flipping to the left when it would overflow.
  const left = () => {
    const cellX = PAD.l + props.g.col * props.geo.cw;
    const right = cellX + props.geo.cw + 10;
    return right + TIP_W > props.geo.w ? Math.max(0, cellX - TIP_W - 10) : right;
  };
  const top = () => {
    const raw = PAD.t + props.g.row * props.geo.ch - 6;
    return Math.max(0, Math.min(raw, props.geo.h - TIP_H));
  };
  return (
    <div class="net-tooltip" style={{ left: `${left()}px`, top: `${top()}px` }}>
      <div class="pair">
        {src().name} <span class="arr">→</span> {tgt().name}
      </div>
      <div class="count">{cell().n.toLocaleString()} xrefs</div>
      <div class="shares">
        {pct(cell().n, props.axes.rowTotal.get(cell().r))} of {src().short}’s citations
        <br />
        {pct(cell().n, props.axes.colTotal.get(cell().c))} of citations to {tgt().short}
      </div>
      <div class="hint">click to filter /refs ↘</div>
    </div>
  );
}
