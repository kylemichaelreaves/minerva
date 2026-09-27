// @vitest-environment node
import { describe, expect, it } from "vitest";
import type { MetricsSummaryRow } from "~/api/metricsApi";
import {
  SEVERITY_THRESHOLDS,
  p95Delta,
  rowKey,
  severityOf,
  summarise,
  verdictOf,
} from "~/Metrics/severity";

const row = (over: Partial<MetricsSummaryRow> = {}): MetricsSummaryRow => ({
  label: "works list",
  method: "GET",
  kind: "total",
  span: "",
  count: 100,
  mean_ms: 50,
  min_ms: 1,
  max_ms: 200,
  p50_ms: 40,
  p95_ms: 100,
  p99_ms: 150,
  error_rate: 0,
  ...over,
});

describe("rowKey", () => {
  it("distinguishes a streaming route's ttfe row from its total row", () => {
    // Both arrive from the same unlabeled summary with span: "", so
    // label alone would collapse them and pair a route against itself.
    expect(rowKey(row({ kind: "total" }))).not.toBe(rowKey(row({ kind: "ttfe" })));
  });

  it("distinguishes two methods on the same label", () => {
    expect(rowKey(row({ method: "GET" }))).not.toBe(rowKey(row({ method: "POST" })));
  });
});

describe("p95Delta", () => {
  it("is the fractional change against the previous window", () => {
    expect(p95Delta(row({ p95_ms: 150 }), row({ p95_ms: 100 }))).toBeCloseTo(0.5);
  });

  it("is negative when the route got faster", () => {
    expect(p95Delta(row({ p95_ms: 80 }), row({ p95_ms: 100 }))).toBeCloseTo(-0.2);
  });

  it("is undefined with no previous row", () => {
    expect(p95Delta(row(), undefined)).toBeUndefined();
  });

  it("is undefined when the previous p95 is zero", () => {
    // Dividing by it yields Infinity, which would render as an
    // "+Infinity%" delta and classify every such route as failing.
    expect(p95Delta(row({ p95_ms: 5 }), row({ p95_ms: 0 }))).toBeUndefined();
  });
});

describe("severityOf", () => {
  it("is bad when any request returned a server error", () => {
    expect(severityOf(row({ error_rate: 0.01 }), row())).toBe("bad");
  });

  it("is bad on errors even below the count floor", () => {
    // A 5xx is a failure at any volume: unlike a percentile, one error
    // is not a sampling artefact.
    expect(severityOf(row({ count: 1, error_rate: 1 }), undefined)).toBe("bad");
  });

  it("is bad when p95 at least doubled", () => {
    expect(severityOf(row({ p95_ms: 200 }), row({ p95_ms: 100 }))).toBe("bad");
  });

  it("is warn just over the warn threshold", () => {
    expect(severityOf(row({ p95_ms: 111 }), row({ p95_ms: 100 }))).toBe("warn");
  });

  it("is ok just under the warn threshold", () => {
    expect(severityOf(row({ p95_ms: 109 }), row({ p95_ms: 100 }))).toBe("ok");
  });

  it("is warn exactly at the warn threshold", () => {
    expect(severityOf(row({ p95_ms: 110 }), row({ p95_ms: 100 }))).toBe("warn");
  });

  it("is bad exactly at the bad threshold", () => {
    expect(severityOf(row({ p95_ms: 200 }), row({ p95_ms: 100 }))).toBe("bad");
  });

  it("is ok when the route got faster", () => {
    expect(severityOf(row({ p95_ms: 10 }), row({ p95_ms: 100 }))).toBe("ok");
  });

  it("is ok below the count floor however large the delta", () => {
    expect(severityOf(row({ count: 4, p95_ms: 900 }), row({ p95_ms: 100 }))).toBe("ok");
  });

  it("is ok with no previous window to compare against", () => {
    // `window=all` has no previous window, so every non-erroring route
    // lands here and the grouping flattens. That is correct, not a case
    // to special-case.
    expect(severityOf(row({ p95_ms: 900 }), undefined)).toBe("ok");
  });

  it("honours overridden thresholds", () => {
    const strict = { ...SEVERITY_THRESHOLDS, warnP95Delta: 0.01 };
    expect(severityOf(row({ p95_ms: 102 }), row({ p95_ms: 100 }), strict)).toBe("warn");
  });
});

describe("verdictOf", () => {
  it("reports an empty window", () => {
    const v = verdictOf([]);
    expect(v.severity).toBe("ok");
    expect(v.headline).toMatch(/no requests recorded/i);
  });

  it("names the failing route and its error count", () => {
    const v = verdictOf([
      { row: row({ label: "work range", count: 47, error_rate: 9 / 47 }), severity: "bad" },
      { row: row({ label: "works list" }), severity: "ok" },
    ]);
    expect(v.severity).toBe("bad");
    expect(v.headline).toBe("One route is failing.");
    expect(v.detail).toContain("work range");
    expect(v.detail).toContain("9 of 47");
  });

  it("pluralises when more than one route is failing", () => {
    const v = verdictOf([
      { row: row({ label: "a", error_rate: 0.5 }), severity: "bad" },
      { row: row({ label: "b", error_rate: 0.5 }), severity: "bad" },
    ]);
    expect(v.headline).toBe("2 routes are failing.");
  });

  it("describes a bad route that is slow rather than erroring", () => {
    // The "returned errors on X of Y" clause would be a lie here: this
    // route tripped the delta threshold with a clean error rate.
    const v = verdictOf([
      { row: row({ label: "work range", error_rate: 0 }), severity: "bad", p95Delta: 3.1 },
    ]);
    expect(v.detail).not.toContain("errors on");
    expect(v.detail).toContain("work range");
  });

  it("says nothing is failing when only warnings are present", () => {
    const v = verdictOf([
      { row: row({ label: "a" }), severity: "warn" },
      { row: row({ label: "b" }), severity: "ok" },
    ]);
    expect(v.severity).toBe("warn");
    expect(v.headline).toBe("Nothing is failing.");
    expect(v.detail).toContain("1 route is slower");
  });

  it("describes a bad route with no error and no baseline at all", () => {
    // `window=all` reaches here: nothing to compare against, so neither
    // the errors clause nor the multiple is available.
    const v = verdictOf([{ row: row({ label: "work range", error_rate: 0 }), severity: "bad" }]);
    expect(v.detail).toContain("work range is well outside its usual range.");
  });

  it("pluralises the warn and ok tails independently", () => {
    const v = verdictOf([
      { row: row({ label: "a" }), severity: "warn" },
      { row: row({ label: "b" }), severity: "warn" },
      { row: row({ label: "c" }), severity: "ok" },
      { row: row({ label: "d" }), severity: "ok" },
    ]);
    expect(v.detail).toContain("2 routes are slower than the previous window");
    expect(v.detail).toContain("the other 2 routes are inside their usual range");
  });

  it("says everything is inside its usual range when all are ok", () => {
    const v = verdictOf([{ row: row(), severity: "ok" }]);
    expect(v.severity).toBe("ok");
    expect(v.detail).toMatch(/inside (its|their) usual range/i);
  });
});

describe("summarise", () => {
  it("pairs each row with its previous-window counterpart and grades it", () => {
    const now = [row({ label: "slow", p95_ms: 300 }), row({ label: "fine", p95_ms: 100 })];
    const prior = [row({ label: "slow", p95_ms: 100 }), row({ label: "fine", p95_ms: 100 })];
    const { entries } = summarise(now, prior);
    expect(entries.map((e) => [e.row.label, e.severity])).toEqual([
      ["slow", "bad"],
      ["fine", "ok"],
    ]);
  });

  it("drops ttfe rows from the leaderboard so a streaming route appears once", () => {
    const now = [row({ label: "chat", kind: "total" }), row({ label: "chat", kind: "ttfe" })];
    const { entries } = summarise(now, []);
    expect(entries).toHaveLength(1);
    expect(entries[0]?.row.kind).toBe("total");
  });

  it("carries a verdict for the graded rows", () => {
    const { verdict } = summarise([row({ error_rate: 0.5, label: "boom" })], []);
    expect(verdict.severity).toBe("bad");
  });
});
