import { describe, expect, it } from "vitest";
import { readRoute, routeHash } from "~/routing";

// `readRoute()` takes no argument — it reads `window.location.hash`. jsdom
// carries a directly-assigned hash between tests, so switch via
// history.replaceState, exactly as web/tests/routing.test.ts does.
function withHash<T>(hash: string, fn: () => T): T {
  const prev = window.location.hash;
  window.history.replaceState(null, "", hash || "#");
  try {
    return fn();
  } finally {
    window.history.replaceState(null, "", prev || "#");
  }
}

describe("#/metrics routing", () => {
  it("parses the bare surface", () => {
    expect(withHash("#/metrics", readRoute)).toMatchObject({ kind: "metrics" });
  });

  it("carries the window and selected label", () => {
    expect(withHash("#/metrics?window=7d&label=chunk+syntax", readRoute)).toMatchObject({
      kind: "metrics",
      window: "7d",
      label: "chunk syntax",
    });
  });

  it("ignores an unknown window rather than rendering a broken page", () => {
    expect(withHash("#/metrics?window=bananas", readRoute)).toMatchObject({
      kind: "metrics",
      window: undefined,
    });
  });

  // Supplemental coverage below — the brief's three cases above are exact.

  it("carries no window or label on the bare surface", () => {
    expect(withHash("#/metrics", readRoute)).toEqual({
      kind: "metrics",
      window: undefined,
      label: undefined,
    });
  });

  it("accepts every recognized window value", () => {
    for (const w of ["1h", "6h", "24h", "7d", "30d", "all"] as const) {
      expect(withHash(`#/metrics?window=${w}`, readRoute)).toMatchObject({
        kind: "metrics",
        window: w,
      });
    }
  });

  it("round-trips window + label through routeHash", () => {
    const hash = routeHash({ kind: "metrics", window: "1h", label: "chunk syntax" });
    expect(withHash(hash, readRoute)).toEqual({
      kind: "metrics",
      window: "1h",
      label: "chunk syntax",
    });
  });

  it("serializes the bare route without a query string", () => {
    expect(routeHash({ kind: "metrics" })).toBe("#/metrics");
  });

  it("serializes only the window when no label is selected", () => {
    expect(routeHash({ kind: "metrics", window: "6h" })).toBe("#/metrics?window=6h");
  });

  it("serializes only the label when no window override is set", () => {
    expect(routeHash({ kind: "metrics", label: "chunk syntax" })).toBe(
      "#/metrics?label=chunk+syntax",
    );
  });
});
