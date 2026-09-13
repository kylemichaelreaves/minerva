import { For, Show, createMemo } from "solid-js";
import type { MetricsSeriesPoint } from "~/api/metricsApi";
import { useElementSize } from "~/hooks/useElementSize";
import "./metrics.css";

/** Chart interior padding, in SVG (pixel) units. */
const PAD_L = 40;
const PAD_T = 10;
const PAD_R = 30;
const PAD_B = 20;

/** Fixed count of horizontal gridlines the brief calls for. */
const GRID_LINE_COUNT = 4;

const DEFAULT_HEIGHT = 220;
const DEFAULT_WIDTH = 640;

interface Domain {
  min: number;
  max: number;
}

/** Time (x) domain: first/last bucket timestamp. A single point has a
 *  zero-width domain — `scaleLinear` guards the resulting zero span. */
export function timeDomain(points: MetricsSeriesPoint[]): Domain {
  if (points.length === 0) return { min: 0, max: 0 };
  const ts = points.map((p) => p.t);
  return { min: Math.min(...ts), max: Math.max(...ts) };
}

/** Value (y) domain across BOTH series — they share one axis. A flat
 *  series (every value identical) has a zero-height domain — again
 *  guarded in `scaleLinear`, not here. */
export function valueDomain(points: MetricsSeriesPoint[]): Domain {
  if (points.length === 0) return { min: 0, max: 1 };
  const vs = points.flatMap((p) => [p.p50_ms, p.p95_ms]);
  return { min: Math.min(...vs), max: Math.max(...vs) };
}

/** Linear interpolation from a value domain to a pixel range. The
 *  domain span is guarded with `|| 1`: when min === max (a single time
 *  bucket, or a perfectly flat series) this collapses every point to
 *  `rangeMin` instead of dividing by zero and producing NaN. */
export function scaleLinear(
  value: number,
  domainMin: number,
  domainMax: number,
  rangeMin: number,
  rangeMax: number,
): number {
  const span = domainMax - domainMin || 1;
  const t = (value - domainMin) / span;
  return rangeMin + t * (rangeMax - rangeMin);
}

/** `count` evenly spaced values spanning the domain, inclusive of both
 *  ends — used for the gridlines. `count` is a module constant > 1, so
 *  this never divides by zero; a zero-height domain just repeats
 *  `domain.min` at every level, which is correct (a flat series has
 *  one true value). */
export function gridLevels(domain: Domain, count: number): number[] {
  const span = domain.max - domain.min;
  return Array.from({ length: count }, (_, i) => domain.min + (span * i) / (count - 1));
}

/** Render-time HH:MM label for a bucket timestamp, in UTC so the test
 *  suite (and CI, in whatever timezone it runs) sees the same string a
 *  developer's browser would render in theirs — this is a label, not a
 *  clock, so there is no "wrong" timezone to guard against here. */
export function formatTimeLabel(t: number): string {
  const d = new Date(t * 1000);
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}

export function TimeSeriesChart(props: { points: MetricsSeriesPoint[]; height?: number }) {
  let wrapEl: HTMLDivElement | undefined;
  const size = useElementSize(() => wrapEl, { w: DEFAULT_WIDTH, h: DEFAULT_HEIGHT });

  const width = () => size().w;
  const height = () => props.height ?? size().h;

  const plotX0 = PAD_L;
  const plotX1 = () => Math.max(plotX0, width() - PAD_R);
  const plotY0 = PAD_T;
  const plotY1 = () => Math.max(plotY0, height() - PAD_B);

  const tDomain = createMemo(() => timeDomain(props.points));
  const vDomain = createMemo(() => valueDomain(props.points));

  const xAt = (t: number) => scaleLinear(t, tDomain().min, tDomain().max, plotX0, plotX1());
  const yAt = (v: number) => scaleLinear(v, vDomain().min, vDomain().max, plotY1(), plotY0);

  const linePoints = (key: "p50_ms" | "p95_ms") =>
    props.points.map((p) => `${xAt(p.t)},${yAt(p[key])}`).join(" ");

  const levels = createMemo(() => gridLevels(vDomain(), GRID_LINE_COUNT));

  const first = () => props.points[0];
  const last = () => props.points[props.points.length - 1];

  return (
    <div class="mchart" ref={wrapEl}>
      <Show when={props.points.length > 0} fallback={<div class="mchart-empty">No data</div>}>
        <div class="mchart-legend">
          <span class="mchart-legend-item">
            <span class="mchart-swatch" data-series="p50" />
            p50
          </span>
          <span class="mchart-legend-item">
            <span class="mchart-swatch" data-series="p95" />
            p95
          </span>
        </div>
        <div class="mchart-svg-wrap">
          <svg
            width={width()}
            height={height()}
            viewBox={`0 0 ${width()} ${height()}`}
            style={{ display: "block" }}
            role="img"
            aria-label="Latency over time, p50 and p95, in milliseconds"
          >
            <For each={levels()}>
              {(v, i) => (
                <>
                  <line x1={plotX0} x2={plotX1()} y1={yAt(v)} y2={yAt(v)} class="mchart-grid" />
                  <text x={plotX0 - 6} y={yAt(v) + 3} text-anchor="end" class="mchart-tick">
                    {Math.round(v)}
                    {i() === GRID_LINE_COUNT - 1 ? " ms" : ""}
                  </text>
                </>
              )}
            </For>
            <polyline points={linePoints("p50_ms")} class="mchart-line" data-series="p50" />
            <polyline points={linePoints("p95_ms")} class="mchart-line" data-series="p95" />
            <Show when={last()}>
              {(lastPoint) => (
                <>
                  <text
                    x={xAt(lastPoint().t) + 4}
                    y={yAt(lastPoint().p50_ms) + 3}
                    class="mchart-label"
                  >
                    p50
                  </text>
                  <text
                    x={xAt(lastPoint().t) + 4}
                    y={yAt(lastPoint().p95_ms) + 3}
                    class="mchart-label"
                  >
                    p95
                  </text>
                </>
              )}
            </Show>
            <Show when={first()}>
              {(firstPoint) => (
                <text x={plotX0} y={height() - 4} text-anchor="start" class="mchart-tick">
                  {formatTimeLabel(firstPoint().t)}
                </text>
              )}
            </Show>
            <Show when={last()}>
              {(lastPoint) => (
                <text x={plotX1()} y={height() - 4} text-anchor="end" class="mchart-tick">
                  {formatTimeLabel(lastPoint().t)}
                </text>
              )}
            </Show>
          </svg>
        </div>
      </Show>
    </div>
  );
}
