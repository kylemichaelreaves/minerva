import { For, Show, createMemo, createSignal } from "solid-js";
import type { LandingStats } from "~/api/landingApi";
import { useIsMobile } from "~/components/shell/MobileShellContext";
import { CORPUS_YEAR_SPAN_LABEL } from "~/features/Landing/corpusFacts";
import {
  ATLAS_AUTHORS,
  BANDS,
  BASE_Y,
  ROW_GAP,
  TRADITION_LABEL,
  VB_HEIGHT,
  VB_WIDTH,
  YEAR_TICKS,
  assignAtlasRows,
  fmtYear,
  xOf,
  type AtlasAuthor,
  type Tradition,
} from "~/data/atlasData";
import { onActivateKey } from "~/utils/activateKey";
import "~/Network/components/atlas.css";

/** Format one corpus-fact number, tolerating a missing field.
 *
 *  Mirrors `fmtNum` in `Landing/index.tsx`, which renders the same three
 *  numbers in the landing's stats line and has always guarded them. Kept as a
 *  local function rather than shared because the two differ in the em dash:
 *  the stats line's `—` sits in its own `.num` span, here it is inline. */
const fmtStat = (n: number | undefined): string =>
  typeof n === "number" ? n.toLocaleString() : "—";

export function Atlas(props: {
  onPickAuthor: (name: string) => void;
  stats: LandingStats | null;
  isMobile?: () => boolean;
}) {
  const [hover, setHover] = createSignal<(AtlasAuthor & { computedRow: number }) | null>(null);
  const shellMobile = useIsMobile();
  const isMobile = () => props.isMobile?.() ?? shellMobile();

  const labelFontSize = () => (isMobile() ? 20 : 10.5);
  const layout = createMemo(() => assignAtlasRows(ATLAS_AUTHORS, labelFontSize()));
  const rowGap = () => (isMobile() ? 26 : ROW_GAP);

  function tickColor(t: Tradition) {
    return `var(--atlas-${t})`;
  }

  return (
    <div class="net-atlas">
      <div class="net-atlas-scroll">
        <svg
          class="net-atlas-svg"
          viewBox={`0 0 ${VB_WIDTH} ${VB_HEIGHT}`}
          preserveAspectRatio="xMidYMid meet"
        >
          <For each={BANDS}>
            {(b) => (
              <rect
                x={xOf(b.yStart)}
                y={BASE_Y - 1}
                width={xOf(b.yEnd) - xOf(b.yStart)}
                height={3}
                fill={tickColor(b.key)}
              />
            )}
          </For>

          <For each={BANDS.slice(0, -1)}>
            {(b) => (
              <line
                x1={xOf(b.yEnd)}
                y1={BASE_Y - 10}
                x2={xOf(b.yEnd)}
                y2={BASE_Y + 12}
                stroke="var(--rule-hair, var(--rule))"
                stroke-width="1"
              />
            )}
          </For>

          <For each={BANDS}>
            {(b) => (
              <text
                x={(xOf(b.yStart) + xOf(b.yEnd)) / 2}
                y={BASE_Y + 44}
                text-anchor="middle"
                class="atlas-bandlbl"
              >
                {TRADITION_LABEL[b.key]}
              </text>
            )}
          </For>

          <For each={YEAR_TICKS}>
            {(y) => (
              <>
                <line
                  x1={xOf(y)}
                  y1={BASE_Y + 4}
                  x2={xOf(y)}
                  y2={BASE_Y + 10}
                  stroke="var(--ink-faint)"
                  stroke-width="1"
                />
                <text x={xOf(y)} y={BASE_Y + 24} text-anchor="middle" class="atlas-year">
                  {fmtYear(y)}
                </text>
              </>
            )}
          </For>

          <For each={layout()}>
            {(a) => {
              const x = xOf(a.year);
              const labelY = BASE_Y - 14 - a.computedRow * rowGap();
              const labelX = x + a.xShift;
              const needsConnector = a.computedRow > 0 || Math.abs(a.xShift) > 4;
              return (
                <g
                  class="atlas-author"
                  role="button"
                  tabindex="0"
                  aria-label={`${a.name}: open references`}
                  onMouseEnter={() => setHover(a)}
                  onMouseLeave={() => setHover((h) => (h === a ? null : h))}
                  onFocus={() => setHover(a)}
                  onBlur={() => setHover((h) => (h === a ? null : h))}
                  onClick={() => props.onPickAuthor(a.name)}
                  onKeyDown={onActivateKey(() => props.onPickAuthor(a.name))}
                  style={{ cursor: "pointer" }}
                >
                  <Show when={needsConnector}>
                    <path
                      d={`M ${labelX} ${labelY + 3} L ${labelX} ${BASE_Y - 13} L ${x} ${BASE_Y - 9}`}
                      fill="none"
                      stroke="var(--ink-faint)"
                      stroke-width="0.6"
                    />
                  </Show>
                  <line
                    x1={x}
                    y1={BASE_Y - 7}
                    x2={x}
                    y2={BASE_Y + 1}
                    stroke="var(--ink)"
                    stroke-width="1"
                  />
                  <text x={labelX} y={labelY} text-anchor="middle" class="atlas-name">
                    {a.name}
                  </text>
                  <rect
                    x={x - 14}
                    y={labelY - 12}
                    width={28}
                    height={BASE_Y - labelY + 24}
                    fill="transparent"
                  />
                </g>
              );
            }}
          </For>
        </svg>

        <Show when={hover()}>
          {(h) => (
            <div
              classList={{
                "atlas-tooltip": true,
                // Past the midpoint the popover opens leftward instead, so the
                // authors near the right edge don't push it off the page.
                "atlas-tooltip-flip": xOf(h().year) > VB_WIDTH / 2,
              }}
              style={{
                left: `${(xOf(h().year) / VB_WIDTH) * 100}%`,
                top: `${((BASE_Y - 14 - h().computedRow * rowGap() - 10) / VB_HEIGHT) * 100}%`,
              }}
            >
              <div class="nm">{h().name}</div>
              <div class="tr">{TRADITION_LABEL[h().tradition]}</div>
              <div class="wk">{h().work}</div>
            </div>
          )}
        </Show>
      </div>

      {/* `<Show when={props.stats}>` proves the object is there, NOT that its
          fields are — a 200 carrying a partial payload made
          `undefined.toLocaleString()` throw, which took the whole landing (its home
          then) down with it. `Landing/index.tsx` renders these same three numbers through
          its own `fmtNum` and has always been defensive; this copy was not, so
          the two disagreed about the same data. Formatted per-field for that
          reason, not out of superstition. */}
      <div class="net-atlas-caption">
        <Show when={props.stats}>
          {(s) => (
            <>
              {CORPUS_YEAR_SPAN_LABEL} YEARS<span class="sep">·</span>
              {fmtStat(s().authors)} AUTHORS<span class="sep">·</span>
              {fmtStat(s().works)} WORKS<span class="sep">·</span>
              {fmtStat(s().xrefs)} VERIFIED CROSS-REFERENCES
            </>
          )}
        </Show>
      </div>
    </div>
  );
}
