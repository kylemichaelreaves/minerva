import { describe, expect, it } from "vitest";
import type { MatrixCell, NetworkAuthor } from "~/api/networkApi";
import {
  GAP_CAP,
  axisBreaks,
  eraLabel,
  eraSpans,
  formatYearEra,
  furthestBack,
  logWeight,
  pairsFromCells,
  placeAuthors,
  placeOnAxis,
  resolvePairs,
  taperPath,
  timeScale,
  type ArcAuthor,
} from "~/Network/components/arcLayout";

const au = (
  name: string,
  ord: number,
  corpus: NetworkAuthor["corpus"] = "class",
): NetworkAuthor => ({
  name,
  short: name,
  ord,
  corpus,
});

describe("formatYearEra", () => {
  it("labels BC and CE", () => {
    expect(formatYearEra(-800)).toBe("800 BC");
    expect(formatYearEra(1880)).toBe("1880 CE");
  });
});

describe("placeAuthors", () => {
  const years = new Map([
    ["Aesop", -580],
    ["Theognis", -540],
    ["Heraclitus", -500],
    ["Luther Bibel 1912", 1912],
    ["Nietzsche", 1880],
  ]);

  it("sorts by year, not by ordinal", () => {
    const out = placeAuthors(
      [
        au("Theognis", 150),
        au("Aesop", 170),
        au("Luther Bibel 1912", 730, "scrip"),
        au("Nietzsche", 935),
      ],
      years,
    );
    expect(out.map((a) => a.name)).toEqual(["Aesop", "Theognis", "Nietzsche", "Luther Bibel 1912"]);
    expect(out[3]).toMatchObject({ scrip: true, dated: true, year: 1912 });
  });

  it("interpolates an undated author on ordinal between dated neighbours", () => {
    // Pythagoras (ord 230) between Aesop (170, −580) and Heraclitus (250, −500).
    const out = placeAuthors(
      [au("Aesop", 170), au("Pythagoras", 230), au("Heraclitus", 250)],
      years,
    );
    expect(out[1]).toMatchObject({ name: "Pythagoras", year: -520, dated: false });
  });

  it("copies the nearest dated author at either end", () => {
    const out = placeAuthors([au("Early", 10), au("Aesop", 170), au("Late", 999)], years);
    expect(out.map((a) => [a.name, a.year, a.dated])).toEqual([
      ["Early", -580, false],
      ["Aesop", -580, true],
      ["Late", -580, false],
    ]);
  });

  it("takes the last dated author at its ordinal when neighbours tie", () => {
    const same = new Map([
      ["A", -100],
      ["B", 100],
    ]);
    const out = placeAuthors([au("A", 50), au("X", 50), au("B", 50)], same);
    expect(out.find((a) => a.name === "X")?.year).toBe(100);
  });

  it("places everyone at year 0 when nobody is dated", () => {
    expect(placeAuthors([au("A", 1)], new Map())[0]).toMatchObject({ year: 0, dated: false });
  });
});

describe("timeScale", () => {
  it("fills the inner width exactly", () => {
    const xs = timeScale([-800, -500, -380, 1260, 1880], 20, 600);
    expect(xs[0]).toBe(20);
    expect(xs.at(-1)).toBeCloseTo(620, 3);
  });

  it("caps long gaps so they get no more room than GAP_CAP years", () => {
    // 1000-year and GAP_CAP-year gaps should come out the same width.
    const xs = timeScale([0, 1000, 1000 + GAP_CAP], 0, 400);
    expect((xs[1] ?? 0) - (xs[0] ?? 0)).toBeCloseTo((xs[2] ?? 0) - (xs[1] ?? 0), 3);
  });

  it("keeps simultaneous authors at least the minimum spacing apart", () => {
    const xs = timeScale([0, 0, 0, 500], 0, 600);
    expect((xs[1] ?? 0) - (xs[0] ?? 0)).toBeGreaterThanOrEqual(11);
  });

  it("still fits when the width cannot give every author 11 px", () => {
    const years = Array.from({ length: 41 }, (_, i) => i * 50);
    const xs = timeScale(years, 20, 400);
    expect(xs.at(-1)).toBeCloseTo(420, 3);
  });

  it("centres a lone author", () => {
    expect(timeScale([100], 20, 600)).toEqual([320]);
  });

  it("places nobody when there is nobody", () => {
    expect(timeScale([], 20, 600)).toEqual([]);
  });
});

describe("placeOnAxis", () => {
  // #692: the x rides on the item it belongs to, so a caller never zips a
  // parallel `xs` array back onto its authors by index — the `xs[i] ?? 0`
  // that zip needed could not fire, and nobody had seen it work.
  it("carries each item through with its timeScale x attached", () => {
    const items = [
      { name: "Homer", year: -800 },
      { name: "Plato", year: -380 },
      { name: "Kant", year: 1780 },
    ];
    const placed = placeOnAxis(items, 20, 600);
    expect(placed.map((p) => p.name)).toEqual(["Homer", "Plato", "Kant"]);
    expect(placed.map((p) => p.x)).toEqual(
      timeScale(
        items.map((i) => i.year),
        20,
        600,
      ),
    );
    expect(placed[0]?.x).toBe(20);
    expect(placed.at(-1)?.x).toBeCloseTo(620, 3);
  });
});

describe("resolvePairs", () => {
  const ends = new Map([
    ["A", 1],
    ["B", 2],
  ]);
  const p = (src: string, tgt: string) => ({ src, tgt, n: 1, intra_scrip: false });

  it("keeps a pair with both ends known, and resolves them", () => {
    expect(resolvePairs([p("A", "B")], ends)).toEqual([{ pair: p("A", "B"), src: 1, tgt: 2 }]);
  });

  it("drops a pair when either end is unknown", () => {
    expect(resolvePairs([p("Z", "B"), p("A", "Z")], ends)).toEqual([]);
  });
});

describe("axisBreaks", () => {
  it("marks the midpoint of each gap longer than GAP_CAP", () => {
    expect(axisBreaks([0, 50, 50 + GAP_CAP + 1], [0, 10, 30])).toEqual([20]);
  });
});

describe("eraSpans", () => {
  const a = (name: string, year: number): ArcAuthor => ({
    name,
    short: name,
    scrip: false,
    year,
    dated: true,
  });

  it("brackets the authors in each era and skips empty eras", () => {
    const spans = eraSpans(
      [a("Homer", -800), a("Plato", -380), a("Nietzsche", 1880)],
      [10, 50, 90],
    );
    expect(spans).toEqual([
      { name: "Archaic", x0: 5, x1: 15 },
      { name: "Classical", x0: 45, x1: 55 },
      { name: "Modern", x0: 85, x1: 95 },
    ]);
  });
});

describe("eraLabel", () => {
  it("shortens to fit", () => {
    expect(eraLabel("Late Antiquity", 100)).toBe("LATE ANTIQUITY");
    expect(eraLabel("Late Antiquity", 50)).toBe("LATE");
    expect(eraLabel("Classical", 50)).toBe("CLASS");
    expect(eraLabel("Medieval", 10)).toBe("");
  });
});

describe("pairsFromCells", () => {
  const authors = [
    au("Aquinas", 700, "med"),
    au("Vulgate", 520, "scrip"),
    au("Sacy", 750, "scrip"),
  ];
  const cells: MatrixCell[] = [
    { r: 0, c: 1, n: 5 },
    { r: 2, c: 1, n: 50 },
    { r: 9, c: 1, n: 1 }, // unknown author index
  ];

  it("names each cell, flags intra-scripture pairs, and sorts heaviest first", () => {
    expect(pairsFromCells(authors, cells, false)).toEqual([
      { src: "Sacy", tgt: "Vulgate", n: 50, intra_scrip: true },
      { src: "Aquinas", tgt: "Vulgate", n: 5, intra_scrip: false },
    ]);
  });

  it("drops intra-scripture pairs when asked", () => {
    expect(pairsFromCells(authors, cells, true).map((p) => p.src)).toEqual(["Aquinas"]);
  });
});

describe("logWeight", () => {
  it("is 1 at the maximum and 0 at zero", () => {
    expect(logWeight(1000, 1000)).toBeCloseTo(1);
    expect(logWeight(0, 1000)).toBe(0);
  });
});

describe("taperPath", () => {
  it("is a closed outline starting at the citing end", () => {
    const d = taperPath(10, 110, 50, 30, 4);
    const [x, y] = (/^M([\d.]+),([\d.]+)/.exec(d) ?? []).slice(1).map(Number);
    expect(Math.abs((x ?? 0) - 10)).toBeLessThan(0.5);
    expect(Math.abs((y ?? 0) - 50)).toBeLessThan(0.5);
    expect(d.endsWith("Z")).toBe(true);
  });

  it("is wider at the cited end than the citing end", () => {
    const pts = taperPath(0, 100, 0, 0, 6)
      .replace(/[MZ]/g, "")
      .split("L")
      .map((s) => s.split(",").map(Number));
    // Flat arc: the outline's first/last points straddle x1, the middle
    // two straddle x2. Their vertical separation is the local width.
    const width = (a: number[] | undefined, b: number[] | undefined) =>
      Math.abs((a?.[1] ?? 0) - (b?.[1] ?? 0));
    const n = pts.length;
    expect(width(pts[n / 2 - 1], pts[n / 2])).toBeGreaterThan(width(pts[0], pts[n - 1]));
  });
});

describe("furthestBack", () => {
  const a = (name: string, year: number, dated = true): ArcAuthor => ({
    name,
    short: name,
    scrip: false,
    year,
    dated,
  });
  const byName = new Map(
    [a("Nietzsche", 1880), a("Plato", -380), a("Homer", -800), a("Pythagoras", -520, false)].map(
      (x) => [x.name, x],
    ),
  );
  const pair = (tgt: string) => ({ src: "Nietzsche", tgt, n: 1, intra_scrip: false });

  it("picks the earliest dated target", () => {
    expect(furthestBack("Nietzsche", [pair("Plato"), pair("Homer")], byName)).toEqual({
      name: "Homer",
      years: 2680,
    });
  });

  it("ignores undated targets and undated sources", () => {
    expect(furthestBack("Nietzsche", [pair("Pythagoras")], byName)).toBeNull();
    expect(furthestBack("Pythagoras", [pair("Homer")], byName)).toBeNull();
  });
});
