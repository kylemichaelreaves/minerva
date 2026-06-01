import { For } from "solid-js";
import type { AuthorPair } from "~/api/networkApi";

export function ArcPanelTopStrip(props: {
  width: number;
  padL: number;
  padR: number;
  hideIntra: boolean;
  pairs: AuthorPair[];
  onOpenPair: (source: string, target: string) => void;
}) {
  const STRIP_H = 96;
  return (
    <svg
      class="net-arc-strip"
      width={props.width}
      height={STRIP_H}
      viewBox={`0 0 ${props.width} ${STRIP_H}`}
      style={{ display: "block" }}
    >
      <line
        x1={props.padL}
        x2={props.width - props.padR}
        y1={0}
        y2={0}
        stroke="var(--rule)"
        stroke-width={0.6}
        stroke-dasharray="2 2"
      />
      <text
        x={props.padL}
        y={10}
        font-size="9.5"
        fill="var(--ink-mute)"
        font-family="ui-monospace, SFMono-Regular, Menlo, monospace"
        letter-spacing="0.14em"
      >
        {props.hideIntra ? "TOP PAIRS — INTRA-SCRIPTURE HIDDEN" : "TOP PAIRS — ALL"}
      </text>
      <For each={props.pairs}>
        {(p, i) => {
          const yRow = 22 + i() * 12;
          const col = p.intra_scrip ? "var(--net-terra)" : "var(--net-navy)";
          const rowsX = props.padL;
          const rowsW = props.width - props.padL - props.padR;
          const barColX = rowsX + rowsW * 0.55;
          const countGutter = 56;
          const barMaxW = rowsW - rowsW * 0.55 - countGutter;
          const bw =
            (Math.log10(p.n + 1) / Math.log10((props.pairs[0]?.n ?? p.n) + 1)) * barMaxW;
          return (
            <>
              <text
                x={rowsX}
                y={yRow}
                font-size="9"
                fill="var(--ink-faint)"
                font-family="ui-monospace, SFMono-Regular, Menlo, monospace"
              >
                {String(i() + 1).padStart(2, "0")}
              </text>
              <text
                x={rowsX + 18}
                y={yRow}
                font-size="10.5"
                fill="var(--ink)"
                font-family="var(--sans)"
                style={{ cursor: "pointer" }}
                onClick={() => props.onOpenPair(p.src, p.tgt)}
              >
                {p.src} → {p.tgt}
              </text>
              <rect
                x={barColX}
                y={yRow - 7}
                width={bw}
                height={7}
                fill={col}
                fill-opacity={0.7}
              />
              <text
                x={props.width - props.padR}
                y={yRow}
                font-size="10"
                fill={col}
                font-family="ui-monospace, SFMono-Regular, Menlo, monospace"
                text-anchor="end"
                font-weight="500"
              >
                {p.n.toLocaleString()}
              </text>
            </>
          );
        }}
      </For>
    </svg>
  );
}
