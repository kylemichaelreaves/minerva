import { For, createMemo } from "solid-js";
import type { TopWorkRow } from "~/api/networkApi";

export function LeaderboardPanel(props: {
  rows: TopWorkRow[];
  onOpen: (author: string, work: string) => void;
}) {
  return (
    <div class="net-panel">
      <div class="net-panel-head">
        <div>
          <div class="net-panel-title">Top-cited works</div>
          <div class="net-panel-q">What does everyone keep coming back to?</div>
        </div>
      </div>
      <div class="net-panel-body">
        <div class="net-leader-wrap">
          <div class="net-leader-rows">
            <For each={props.rows}>
              {(row, i) => (
                <button
                  class="net-leader-row"
                  onClick={() => props.onOpen(row.author, row.work)}
                >
                  <div class="rk">{String(i() + 1).padStart(2, "0")}</div>
                  <div class="work">
                    {row.work}
                    <span class="auth">{row.author}</span>
                  </div>
                  <div class="spark">
                    <LeaderboardSparkline n={row.n} max={props.rows[0]?.n ?? row.n} />
                  </div>
                  <div class="cnt">{row.n.toLocaleString()}</div>
                </button>
              )}
            </For>
          </div>
        </div>
      </div>
    </div>
  );
}

/* Simple bar — the design's century sparkline needs century-bucket
   data the index doesn't track yet. A log-scaled fill bar communicates
   the same "this is much bigger than #10" relationship faithfully. */
function LeaderboardSparkline(props: { n: number; max: number }) {
  const sw = 80;
  const sh = 12;
  const w = createMemo(() =>
    Math.max(
      2,
      (Math.log10(props.n + 1) / Math.log10(Math.max(2, props.max) + 1)) * sw,
    ),
  );
  return (
    <svg width={sw} height={sh} viewBox={`0 0 ${sw} ${sh}`} style={{ display: "block" }}>
      <rect x={0} y={0} width={sw} height={sh - 2} fill="var(--paper-edge)" />
      <rect
        x={0}
        y={0}
        width={w()}
        height={sh - 2}
        fill="var(--net-navy)"
        fill-opacity={0.7}
      />
      <line
        x1={0}
        x2={sw}
        y1={sh - 1}
        y2={sh - 1}
        stroke="var(--rule)"
        stroke-width={0.5}
      />
    </svg>
  );
}
