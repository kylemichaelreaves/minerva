import { describe, expect, it } from "vitest";
import type { MatrixCell, NetworkAuthor } from "~/api/networkApi";
import {
  buildAxes,
  cellValue,
  bandLabel,
  gridRows,
  moveInGrid,
  pct,
  placeCells,
  stepFor,
  type GridCell,
  type GridMove,
} from "~/Network/components/matrixLayout";

function nth<T>(xs: T[], i: number): T {
  const x = xs[i];
  if (x === undefined) throw new Error(`no element ${i}`);
  return x;
}

// Server order is chronological: Vulgate (ord 520) sits between the
// classical authors and Augustine.
const authors: NetworkAuthor[] = [
  { name: "Homer", short: "Homer", ord: 100, corpus: "class" },
  { name: "Plato", short: "Plato", ord: 400, corpus: "class" },
  { name: "Vulgate", short: "Vulgate", ord: 520, corpus: "scrip" },
  { name: "Augustine", short: "Augustine", ord: 600, corpus: "med" },
  { name: "Aquinas", short: "Aquinas", ord: 700, corpus: "med" },
  { name: "Boulainvilliers", short: "Boulainvill…", ord: 845, corpus: "em" },
  { name: "Nietzsche", short: "Nietzsche", ord: 935, corpus: "mod" },
];
const cells: MatrixCell[] = [
  { r: 1, c: 0, n: 30 }, // Plato → Homer
  { r: 4, c: 3, n: 600 }, // Aquinas → Augustine
  { r: 4, c: 2, n: 300 }, // Aquinas → Vulgate
  { r: 4, c: 1, n: 100 }, // Aquinas → Plato
  { r: 3, c: 2, n: 100 }, // Augustine → Vulgate
  { r: 6, c: 1, n: 5 }, // Nietzsche → Plato
];

describe("buildAxes", () => {
  const axes = buildAxes(authors, cells);

  it("drops authors who never cite from rows and never-cited ones from cols", () => {
    expect(axes.rows).toEqual([1, 3, 4, 6]);
    expect(axes.cols).toEqual([0, 1, 2, 3]);
    expect(axes.rows).not.toContain(5);
    expect(axes.cols).not.toContain(5);
  });

  it("groups each axis into contiguous corpus bands", () => {
    expect(axes.colBands).toEqual([
      { corpus: "class", start: 0, end: 2 },
      { corpus: "scrip", start: 2, end: 3 },
      { corpus: "med", start: 3, end: 4 },
    ]);
    expect(axes.rowBands.map((b) => b.corpus)).toEqual(["class", "med", "mod"]);
  });

  it("orders scripture after the classical band even when it is listed first", () => {
    const shuffled = [nth(authors, 2), nth(authors, 0)];
    const a = buildAxes(shuffled, [
      { r: 1, c: 0, n: 1 },
      { r: 0, c: 1, n: 1 },
    ]);
    expect(a.rows).toEqual([1, 0]);
  });

  it("sums row and column totals", () => {
    expect(axes.rowTotal.get(4)).toBe(1000);
    expect(axes.colTotal.get(2)).toBe(400);
  });

  it("puts an author with an unknown corpus last", () => {
    const odd = [
      { name: "X", short: "X", ord: 1, corpus: "zzz" as NetworkAuthor["corpus"] },
      nth(authors, 0),
    ];
    const a = buildAxes(odd, [
      { r: 0, c: 1, n: 1 },
      { r: 1, c: 0, n: 1 },
    ]);
    expect(a.rows).toEqual([1, 0]);
  });
});

describe("cellValue", () => {
  const axes = buildAxes(authors, cells);
  const aquinasVulgate = nth(cells, 2);

  it("normalizes by row, by column, or not at all", () => {
    expect(cellValue(aquinasVulgate, "n", axes)).toBe(300);
    expect(cellValue(aquinasVulgate, "row", axes)).toBeCloseTo(0.3);
    expect(cellValue(aquinasVulgate, "col", axes)).toBeCloseTo(0.75);
  });

  it("treats a cell missing from the totals as its own whole", () => {
    const empty = buildAxes(authors, []);
    expect(cellValue(aquinasVulgate, "row", empty)).toBe(1);
    expect(cellValue(aquinasVulgate, "col", empty)).toBe(1);
  });
});

describe("stepFor", () => {
  it("bins counts into six steps", () => {
    expect(stepFor(1, "n")).toBe(0);
    expect(stepFor(9, "n")).toBe(0);
    expect(stepFor(10, "n")).toBe(1);
    expect(stepFor(999, "n")).toBe(3);
    expect(stepFor(22379, "n")).toBe(5);
  });

  it("bins shares", () => {
    expect(stepFor(0.005, "row")).toBe(0);
    expect(stepFor(0.03, "col")).toBe(2);
    expect(stepFor(0.75, "row")).toBe(5);
  });
});

describe("bandLabel", () => {
  it("keeps the full caption when it fits", () => {
    expect(bandLabel("em", 120)).toBe("EARLY MODERN");
  });
  it("falls back to the first word", () => {
    expect(bandLabel("em", 60)).toBe("EARLY");
  });
  it("clips a word that does not fit", () => {
    // Medieval over three 12px rows: room for 5 characters.
    expect(bandLabel("med", 36)).toBe("MEDI.");
  });
  it("drops the caption when nothing legible fits", () => {
    expect(bandLabel("scrip", 12)).toBe("");
  });
});

describe("pct", () => {
  it("formats a share to one decimal", () => {
    expect(pct(300, 1000)).toBe("30.0%");
    expect(pct(5, undefined)).toBe("100.0%");
  });
});

// #696: the matrix is a keyboard grid. These pin the model the panel's
// roving tabindex walks; the panel's own suite drives it with keys.
describe("placeCells", () => {
  const axes = buildAxes(authors, cells);

  it("puts each cell at its display row and column, top-left first", () => {
    const placed = placeCells(cells, axes, authors);
    expect(placed.map((g) => [g.src.name, g.tgt.name, g.row, g.col])).toEqual([
      ["Plato", "Homer", 0, 0],
      ["Augustine", "Vulgate", 1, 2],
      ["Aquinas", "Plato", 2, 1],
      ["Aquinas", "Vulgate", 2, 2],
      ["Aquinas", "Augustine", 2, 3],
      ["Nietzsche", "Plato", 3, 1],
    ]);
    expect(placed[0]?.cell).toBe(cells[0]);
  });

  it("leaves out a cell it cannot place on the axes or name from the authors", () => {
    const offAxes: MatrixCell[] = [
      { r: 5, c: 0, n: 1 }, // Boulainvilliers is on no row
      { r: 1, c: 5, n: 1 }, // …and on no column
    ];
    expect(placeCells(offAxes, axes, authors)).toEqual([]);
    // Axes built from cells that name authors the list does not have.
    const ghosts: MatrixCell[] = [
      { r: 99, c: 0, n: 1 },
      { r: 1, c: 99, n: 1 },
    ];
    expect(placeCells(ghosts, buildAxes(authors, ghosts), authors)).toEqual([]);
  });
});

describe("gridRows", () => {
  it("groups placed cells into their display rows", () => {
    const rows = gridRows(placeCells(cells, buildAxes(authors, cells), authors));
    expect(rows.map((r) => [r.pos, r.cells.map((g) => g.col)])).toEqual([
      [0, [0]],
      [1, [2]],
      [2, [1, 2, 3]],
      [3, [1]],
    ]);
  });

  it("has no rows for no cells", () => {
    expect(gridRows([])).toEqual([]);
  });
});

describe("moveInGrid", () => {
  const who = { name: "X", short: "X", ord: 0, corpus: "class" } as const;
  const at = (row: number, col: number): GridCell => ({
    cell: { r: row, c: col, n: 1 },
    src: who,
    tgt: who,
    row,
    col,
  });
  // A sparse grid, as the real one is:
  //   row 0:  .  A  .  .
  //   row 1:  B  .  .  C
  //   row 2:  .  D  E  F
  const [A, B, C, D, E, F] = [at(0, 1), at(1, 0), at(1, 3), at(2, 1), at(2, 2), at(2, 3)];
  const grid = [A, B, C, D, E, F];
  const move = (from: GridCell, m: GridMove) => moveInGrid(grid, from, m);

  it("steps right and left to the next cell in the row, skipping gaps", () => {
    expect(move(B, "right")).toBe(C);
    expect(move(C, "left")).toBe(B);
    expect(move(D, "right")).toBe(E);
    expect(move(F, "left")).toBe(E);
  });

  it("stays put at the end of a row", () => {
    expect(move(C, "right")).toBe(C);
    expect(move(B, "left")).toBe(B);
    expect(move(A, "right")).toBe(A);
  });

  it("goes to the row's first and last cell on Home and End", () => {
    expect(move(F, "home")).toBe(D);
    expect(move(D, "end")).toBe(F);
    expect(move(A, "home")).toBe(A);
  });

  it("moves vertically to the nearest row that has a cell, then the nearest column", () => {
    expect(move(A, "down")).toBe(B); // row 1: B and C are 1 and 2 columns off
    expect(move(B, "down")).toBe(D); // row 2: D is nearest column 0
    expect(move(C, "down")).toBe(F); // same column
    expect(move(F, "up")).toBe(C);
    expect(move(E, "up")).toBe(C); // B is two columns off, C one
    expect(move(D, "up")).toBe(B); // B and C: B is nearer
  });

  it("breaks a tie between equally near columns towards the left", () => {
    // From column 2, the next row's cells at columns 1 and 3 are equally
    // near; the left one wins, whichever order the cells arrive in.
    const tie = [at(0, 2), at(1, 1), at(1, 3)];
    const [from, left, right] = tie as [GridCell, GridCell, GridCell];
    expect(moveInGrid(tie, from, "down")).toBe(left);
    expect(moveInGrid([from, right, left], from, "down")).toBe(left);
  });

  it("stays put at the top and bottom", () => {
    expect(move(A, "up")).toBe(A);
    expect(move(E, "down")).toBe(E);
  });
});
