// Route triage for the #/metrics surface (#600).
//
// The shipped panel answers "what are the percentiles?"; an operator
// opens it asking "is anything wrong?". Everything here is pure and
// DOM-free so the thresholds can be exercised exhaustively without
// mounting anything - which is also what makes the branch coverage
// Sonar wants cheap to pay for.

import type { MetricsSummaryRow } from "~/api/metricsApi";

export type Severity = "bad" | "warn" | "ok";

export interface SeverityThresholds {
  /** Fractional p95 rise against the previous window that reads as a
   *  warning, e.g. 0.10 for +10%. */
  warnP95Delta: number;
  /** ...and as a failure. */
  badP95Delta: number;
  /** Below this many requests a percentile is sampling noise, so a
   *  delta alone never grades a route. Errors still do. */
  minCountForDelta: number;
}

/** These three numbers are the one part of this surface written before
 *  anyone ran it against real traffic - they are back-fitted to the
 *  severities in the source design's fixture data. They live here, in
 *  one place, precisely because they are expected to be tuned. */
export const SEVERITY_THRESHOLDS: SeverityThresholds = {
  warnP95Delta: 0.1,
  badP95Delta: 1.0,
  minCountForDelta: 10,
};

/** Identity of a summary row across windows. `label` alone is not
 *  enough: the unlabeled summary carries a second `kind: "ttfe"` row for
 *  every streaming route at the same `span: ""`, so keying on the label
 *  would collapse the two and pair a route against itself. */
export function rowKey(row: MetricsSummaryRow): string {
  return `${row.label} ${row.method} ${row.kind}`;
}

/** Fractional change in p95 against the previous window, or `undefined`
 *  when there is nothing to compare against. A zero prior is treated as
 *  no baseline rather than as an infinite rise. */
export function p95Delta(
  row: MetricsSummaryRow,
  prior: MetricsSummaryRow | undefined,
): number | undefined {
  if (prior === undefined || prior.p95_ms === 0) return undefined;
  return (row.p95_ms - prior.p95_ms) / prior.p95_ms;
}

export function severityOf(
  row: MetricsSummaryRow,
  prior: MetricsSummaryRow | undefined,
  thresholds: SeverityThresholds = SEVERITY_THRESHOLDS,
): Severity {
  // A 5xx is a failure at any volume - unlike a percentile, a single
  // error is not a sampling artefact - so this precedes the count floor.
  // Note `error_rate` counts ONLY status_class 5: a handler raising 404
  // or 400 is deliberately excluded (`metrics/recorder.py`), so a route
  // rejecting bad input all day stays `ok` here, which is correct.
  if (row.error_rate > 0) return "bad";
  if (row.count < thresholds.minCountForDelta) return "ok";
  const delta = p95Delta(row, prior);
  if (delta === undefined) return "ok";
  if (delta >= thresholds.badP95Delta) return "bad";
  if (delta >= thresholds.warnP95Delta) return "warn";
  return "ok";
}

export interface RouteEntry {
  row: MetricsSummaryRow;
  prior?: MetricsSummaryRow;
  severity: Severity;
  p95Delta?: number;
}

export interface Verdict {
  severity: Severity;
  /** Rendered bold - the conclusion on its own. */
  headline: string;
  /** The rest of the sentence; empty when the headline says it all. */
  detail: string;
}

const plural = (n: number, one: string, many: string): string => (n === 1 ? one : many);

/** How many requests the error rate implies. `error_rate` is a ratio,
 *  and the underlying error count is not in the response - so this is a
 *  reconstruction, and it rounds. */
function errorCount(row: MetricsSummaryRow): number {
  return Math.round(row.error_rate * row.count);
}

function worstClause(entry: RouteEntry): string {
  const { row } = entry;
  if (row.error_rate > 0) {
    return `${row.label} returned errors on ${errorCount(row)} of ${row.count} requests.`;
  }
  // A route can be `bad` on latency alone, with a clean error rate - the
  // errors clause would be a plain falsehood there.
  if (entry.p95Delta === undefined) return `${row.label} is well outside its usual range.`;
  return `${row.label} is ${(1 + entry.p95Delta).toFixed(1)}x its previous-window p95.`;
}

function tailClause(warn: number, ok: number): string {
  const parts: string[] = [];
  if (warn > 0) {
    parts.push(`${warn} ${plural(warn, "route is", "routes are")} slower than the previous window`);
  }
  if (ok > 0) {
    const lead = parts.length > 0 ? "the other " : "";
    const subject = plural(ok, "route is", "routes are");
    parts.push(`${lead}${ok} ${subject} inside ${plural(ok, "its", "their")} usual range`);
  }
  return parts.length > 0 ? `${parts.join("; ")}.` : "";
}

/** One recomputable sentence over the graded rows. Deliberately a
 *  template and not prose: a dashboard that writes sentences it cannot
 *  recompute is worse than one that stays quiet. */
export function verdictOf(entries: RouteEntry[]): Verdict {
  if (entries.length === 0) {
    return { severity: "ok", headline: "No requests recorded in this window.", detail: "" };
  }
  // `find` rather than indexing the filtered array: `bad[0]` is
  // `RouteEntry | undefined` under noUncheckedIndexedAccess, and the
  // assertion needed to narrow it is an eslint error here. Narrowing on
  // `worstEntry` is the same single branch `bad.length > 0` was.
  const worstEntry = entries.find((e) => e.severity === "bad");
  const badCount = entries.filter((e) => e.severity === "bad").length;
  const warn = entries.filter((e) => e.severity === "warn").length;
  const ok = entries.filter((e) => e.severity === "ok").length;

  if (worstEntry !== undefined) {
    const headline = badCount === 1 ? "One route is failing." : `${badCount} routes are failing.`;
    const tail = tailClause(warn, ok);
    const worst = worstClause(worstEntry);
    return { severity: "bad", headline, detail: tail ? `${worst} ${tail}` : worst };
  }
  return {
    severity: warn > 0 ? "warn" : "ok",
    headline: "Nothing is failing.",
    detail: tailClause(warn, ok),
  };
}

/** Grade one window's rows against the previous window's, and say what
 *  the result adds up to. The leaderboard shows whole-request rows only
 *  (`kind === "total"`), so a streaming route appears once rather than
 *  twice with different numbers and no column saying why. */
export function summarise(
  rows: MetricsSummaryRow[],
  priorRows: MetricsSummaryRow[],
  thresholds: SeverityThresholds = SEVERITY_THRESHOLDS,
): { entries: RouteEntry[]; verdict: Verdict } {
  const priorByKey = new Map(priorRows.map((r) => [rowKey(r), r]));
  const entries: RouteEntry[] = rows
    .filter((r) => r.kind === "total")
    .map((row) => {
      const prior = priorByKey.get(rowKey(row));
      return {
        row,
        prior,
        severity: severityOf(row, prior, thresholds),
        p95Delta: p95Delta(row, prior),
      };
    });
  return { entries, verdict: verdictOf(entries) };
}
