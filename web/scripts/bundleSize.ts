// Bundle size report: gzipped size of each built asset, compared against the
// last build on `main`. CI's `web · bundle size` job runs it; locally:
//
//   npm run build && npm run bundle-size -- measure dist > bundle-size.json
//   npm run bundle-size -- report bundle-size.json [baseline.json]
//
// `measure` prints {label: gzippedBytes} as JSON. `report` prints a markdown
// table comparing it with a baseline of the same shape — CI posts it as a PR
// comment. Nothing here fails a build: the report is information, not a gate.
//
// Runs directly under Node's type stripping (no build step), so it uses
// erasable TypeScript only — no enums, namespaces or parameter properties.
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

export type Sizes = Record<string, number>;

// Changes smaller than this many bytes are noise and report as unchanged,
// matching `minimum-change-threshold` in preactjs/compressed-size-action.
export const MINIMUM_CHANGE_THRESHOLD = 1_000;
// Growth above this percentage is flagged red rather than yellow.
export const SIGNIFICANT_PERCENT = 15;

export const TOTAL_JS = "total JS";
export const TOTAL_CSS = "total CSS";

// The marker CI uses to find and update its own comment instead of adding
// another on every push.
export const COMMENT_MARKER = "<!-- bundle-size-report -->";

const EMOJI = ["🟢", "🟡", "🔴"] as const;
const ALERT = ["TIP", "WARNING", "CAUTION"] as const;
const HEADLINE = [
  "No bundle grew",
  "Some bundles grew",
  "Some bundles grew significantly",
] as const;

type Level = 0 | 1 | 2;

// Vite names assets `<name>-<8-char hash>.<ext>`. Dropping the hash gives a
// label that stays stable across builds, so a PR compares like with like.
export function labelFor(fileName: string): string {
  return fileName.replace(/-[\w-]{8}(\.(?:js|css))$/, "$1");
}

// Gzipped bytes of every JS and CSS file under `<distDir>/assets`, keyed by
// hash-free label, plus a total per type. Two chunks that share a name sum.
export function measure(distDir: string): Sizes {
  const assetsDir = path.join(distDir, "assets");
  const sizes: Sizes = {};
  let totalJs = 0;
  let totalCss = 0;
  for (const fileName of readdirSync(assetsDir).sort()) {
    const ext = path.extname(fileName);
    if (ext !== ".js" && ext !== ".css") continue;
    const bytes = gzipSync(readFileSync(path.join(assetsDir, fileName))).length;
    const label = labelFor(fileName);
    sizes[label] = (sizes[label] ?? 0) + bytes;
    if (ext === ".js") totalJs += bytes;
    else totalCss += bytes;
  }
  return { ...sizes, [TOTAL_JS]: totalJs, [TOTAL_CSS]: totalCss };
}

export function levelFor(deltaBytes: number, deltaPercent: number): Level {
  if (deltaBytes < MINIMUM_CHANGE_THRESHOLD) return 0;
  return deltaPercent <= SIGNIFICANT_PERCENT ? 1 : 2;
}

export function formatKb(bytes: number): string {
  return `${(bytes / 1_000).toFixed(1)} kB`;
}

function formatDelta(deltaBytes: number, deltaPercent: number): string {
  if (Math.abs(deltaBytes) < MINIMUM_CHANGE_THRESHOLD) return "–";
  const sign = deltaBytes > 0 ? "+" : "−";
  return `${sign}${formatKb(Math.abs(deltaBytes))} (${sign}${Math.abs(deltaPercent).toFixed(1)}%)`;
}

interface Row {
  label: string;
  bytes: number;
  previous: number | undefined;
  deltaBytes: number;
  deltaPercent: number;
  level: Level;
}

function toRow(label: string, bytes: number, baseline: Sizes): Row {
  const previous = baseline[label];
  const deltaBytes = previous === undefined ? 0 : bytes - previous;
  const deltaPercent = previous ? (deltaBytes / previous) * 100 : 0;
  const level = previous === undefined ? 0 : levelFor(deltaBytes, deltaPercent);
  return { label, bytes, previous, deltaBytes, deltaPercent, level };
}

function renderRow(row: Row): string {
  const { label, bytes, previous, level } = row;
  const before = previous === undefined ? "n/a" : formatKb(previous);
  const delta = previous === undefined ? "new" : formatDelta(row.deltaBytes, row.deltaPercent);
  return `| ${EMOJI[level]} | \`${label}\` | ${formatKb(bytes)} | ${before} | ${delta} |`;
}

// A markdown report of `current` against `baseline`. Assets present only in
// the baseline are listed as removed, so a deleted chunk is visible too.
// `baseline` is null when there is nothing to compare against.
export function buildReport(current: Sizes, baseline: Sizes | null): string {
  const rows = Object.entries(current).map(([label, bytes]) => toRow(label, bytes, baseline ?? {}));
  const removed = Object.entries(baseline ?? {}).filter(([l]) => !(l in current));
  const level = Math.max(0, ...rows.map((r) => r.level)) as Level;
  const against =
    baseline === null
      ? "no baseline from `main` yet, so every asset reports as new"
      : "vs the last build on `main`";
  return [
    COMMENT_MARKER,
    "### Bundle size (gzipped)",
    "",
    `> [!${ALERT[level]}]`,
    `> ${EMOJI[level]} ${HEADLINE[level]} — ${against}.`,
    "",
    "| | Asset | Size | Previous | Δ |",
    "| --- | --- | --- | --- | --- |",
    ...rows.map(renderRow),
    ...removed.map(([l, bytes]) => `| 🟢 | \`${l}\` | removed | ${formatKb(bytes)} | – |`),
    "",
    `Changes under ${formatKb(MINIMUM_CHANGE_THRESHOLD)} count as unchanged. ` +
      "Run `npm run analyze:bundle` in `web/` for a treemap of what is inside each asset.",
  ].join("\n");
}

function readSizes(file: string): Sizes {
  return JSON.parse(readFileSync(file, "utf8")) as Sizes;
}

export function main(argv: string[]): string {
  const [command, first, second] = argv;
  if (command === "measure" && first) {
    return JSON.stringify(measure(first), null, 2);
  }
  if (command === "report" && first) {
    return buildReport(readSizes(first), second ? readSizes(second) : null);
  }
  throw new Error("usage: bundleSize.ts measure <distDir> | report <current.json> [baseline.json]");
}

/* v8 ignore next 3 -- CLI entry; main() is what the tests drive. */
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  console.log(main(process.argv.slice(2)));
}
