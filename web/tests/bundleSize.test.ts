// @vitest-environment node
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { gzipSync } from "node:zlib";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  buildReport,
  COMMENT_MARKER,
  labelFor,
  levelFor,
  main,
  measure,
  TOTAL_CSS,
  TOTAL_JS,
} from "../scripts/bundleSize";

describe("labelFor", () => {
  it("drops Vite's 8-character content hash", () => {
    expect(labelFor("index-sQb5QmNr.js")).toBe("index.js");
    // Hashes may contain `_` and `-`.
    expect(labelFor("index-DIlG_nZ_.css")).toBe("index.css");
    expect(labelFor("Reader-a-b_c-de.js")).toBe("Reader.js");
  });

  it("leaves names without a hash alone", () => {
    expect(labelFor("vendor.js")).toBe("vendor.js");
  });
});

describe("levelFor", () => {
  it("treats shrinkage and sub-threshold growth as unchanged", () => {
    expect(levelFor(-50_000, -40)).toBe(0);
    expect(levelFor(999, 50)).toBe(0);
  });

  it("is yellow up to 15% growth and red beyond", () => {
    expect(levelFor(1_000, 15)).toBe(1);
    expect(levelFor(1_000, 15.1)).toBe(2);
  });
});

describe("measure", () => {
  let dist: string;
  beforeEach(() => {
    dist = mkdtempSync(path.join(tmpdir(), "bundle-size-"));
    mkdirSync(path.join(dist, "assets"));
  });
  afterEach(() => {
    rmSync(dist, { recursive: true, force: true });
  });

  const write = (name: string, body: string) => {
    writeFileSync(path.join(dist, "assets", name), body);
    return gzipSync(Buffer.from(body)).length;
  };

  it("reports gzipped size per asset plus per-type totals", () => {
    const js = write("index-sQb5QmNr.js", "console.log(1);".repeat(50));
    const lazy = write("Reader-AAAAAAAA.js", "export const x = 1;");
    const css = write("index-DIlG_nZ_.css", "body{color:red}");
    write("owl-AAAAAAAA.png", "not measured");

    expect(measure(dist)).toEqual({
      "Reader.js": lazy,
      "index.css": css,
      "index.js": js,
      [TOTAL_JS]: js + lazy,
      [TOTAL_CSS]: css,
    });
  });

  it("sums chunks that share a name", () => {
    const a = write("chunk-AAAAAAAA.js", "a".repeat(10));
    const b = write("chunk-BBBBBBBB.js", "b".repeat(20));
    expect(measure(dist)["chunk.js"]).toBe(a + b);
  });

  it("is reachable through main()", () => {
    write("index-sQb5QmNr.js", "1");
    expect(JSON.parse(main(["measure", dist]))).toHaveProperty("index.js");
  });
});

describe("buildReport", () => {
  it("says so when there is no baseline", () => {
    const report = buildReport({ "index.js": 50_000 }, null);
    expect(report.startsWith(COMMENT_MARKER)).toBe(true);
    expect(report).toContain("no baseline from `main` yet");
    expect(report).toContain("| 🟢 | `index.js` | 50.0 kB | n/a | new |");
  });

  it("rates each row and headlines the worst", () => {
    const report = buildReport(
      { "index.js": 110_000, "index.css": 40_000, "lazy.js": 10_500 },
      { "index.js": 100_000, "index.css": 30_000, "lazy.js": 10_000 },
    );
    expect(report).toContain("| 🟡 | `index.js` | 110.0 kB | 100.0 kB | +10.0 kB (+10.0%) |");
    expect(report).toContain("| 🔴 | `index.css` | 40.0 kB | 30.0 kB | +10.0 kB (+33.3%) |");
    expect(report).toContain("| 🟢 | `lazy.js` | 10.5 kB | 10.0 kB | – |");
    expect(report).toContain("> [!CAUTION]");
  });

  it("shows shrinkage and removed assets as green", () => {
    const report = buildReport({ "index.js": 80_000 }, { "index.js": 100_000, "old.js": 5_000 });
    expect(report).toContain("| 🟢 | `index.js` | 80.0 kB | 100.0 kB | −20.0 kB (−20.0%) |");
    expect(report).toContain("| 🟢 | `old.js` | removed | 5.0 kB | – |");
    expect(report).toContain("> [!TIP]");
  });

  it("does not divide by a zero-byte baseline", () => {
    expect(buildReport({ "a.js": 2_000 }, { "a.js": 0 })).toContain(
      "| 🟡 | `a.js` | 2.0 kB | 0.0 kB | +2.0 kB (+0.0%) |",
    );
  });
});

describe("main", () => {
  it("reads the report's inputs from JSON files", () => {
    const dir = mkdtempSync(path.join(tmpdir(), "bundle-size-"));
    try {
      const current = path.join(dir, "current.json");
      const baseline = path.join(dir, "baseline.json");
      writeFileSync(current, JSON.stringify({ "index.js": 2_000 }));
      writeFileSync(baseline, JSON.stringify({ "index.js": 1_000 }));
      expect(main(["report", current, baseline])).toContain("+1.0 kB (+100.0%)");
      expect(main(["report", current])).toContain("| new |");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("explains its usage on bad arguments", () => {
    expect(() => main([])).toThrow(/usage/);
    expect(() => main(["measure"])).toThrow(/usage/);
  });
});
