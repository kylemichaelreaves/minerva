/** Wall-vs-CPU verdict, in one place because two surfaces render it.
 *
 *  Thresholds are the source design's (`obs-render.js`), not invented here:
 *  a bar that is nearly all CPU is compute, a nearly hollow one is waiting.
 *
 *  Returns undefined when CPU was not measured — `time.thread_time` is not on
 *  every platform, and rows written before Phase 2 carry no value. Rendering
 *  that as "0ms, waiting" would assert a measurement nobody took.
 */
export function cpuVerdict(
  wall: number,
  cpu: number | null | undefined,
): "cpu-bound" | "waiting" | "mixed" | undefined {
  if (cpu === null || cpu === undefined) return undefined;
  if (wall <= 0) return undefined;
  const ratio = cpu / wall;
  if (ratio > 0.6) return "cpu-bound";
  if (ratio < 0.1) return "waiting";
  return "mixed";
}
