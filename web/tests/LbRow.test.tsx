// Leaderboard row rendering, and specifically when the sparkline earns its
// column (#370).
//
// The bar heights are normalized against the ROW's own maximum
// (`Sparkline.tsx`), so the tallest bar in a row is always 100% at every scope.
// Narrow the concordance to a single work and `per_work` collapses to one entry
// whose `n` equals the row's `count` — measured on the live index, every row
// comes back `distinct_works=1, per_work=[{work, n}]` — so every row drew the
// same solid block. Correct, and informationless.
//
// These are the first tests to mount `Sparkline` at all. The one pre-existing
// fixture that touches it (`ConcordanceIndexScope.test.tsx`) uses
// `per_work: []`, a shape the backend never produces for `scope=work`, and so
// only ever exercised the empty fallback.

import { render } from "@solidjs/testing-library";
import { describe, expect, it, vi } from "vitest";
import type { LemmaIndexRow } from "~/api/concordanceApi";
import { LbRow } from "~/Concordance/components/LbRow";

function makeRow(overrides: Partial<LemmaIndexRow> = {}): LemmaIndexRow {
  return {
    rank: 1,
    lemma: "Geist",
    pos: "NOUN",
    count: 682,
    distinct_works: 4,
    per_work: [
      { work: "Phänomenologie des Geistes", n: 400 },
      { work: "Wissenschaft der Logik", n: 200 },
      { work: "Enzyklopädie", n: 82 },
    ],
    ...overrides,
  };
}

function renderRow(row: LemmaIndexRow) {
  return render(() => <LbRow row={row} onOpen={vi.fn()} />);
}

describe("<LbRow /> sparkline", () => {
  it("draws one bar per work, scaled to the row's own maximum", () => {
    const { container } = renderRow(makeRow());
    const bars = container.querySelectorAll(".spark .bar");

    expect(bars.length).toBe(3);
    // 400 is the row max → 100%; 200 → 50%; 82 → 20.5%.
    expect((bars[0] as HTMLElement).style.height).toBe("100%");
    expect((bars[1] as HTMLElement).style.height).toBe("50%");
  });

  it("draws no bar when the lemma sits in a single work", () => {
    // The state the reader hit: one work in scope. The cell itself stays, so
    // the row grid's track keeps its width and rows do not reflow when the
    // scope widens again.
    const { container } = renderRow(
      makeRow({
        distinct_works: 1,
        count: 1438,
        per_work: [{ work: "Phänomenologie des Geistes", n: 1438 }],
      }),
    );

    expect(container.querySelector(".spark")).not.toBeNull();
    expect(container.querySelectorAll(".spark .bar").length).toBe(0);
  });

  it("draws no bar when there is no per-work breakdown at all", () => {
    const { container } = renderRow(makeRow({ distinct_works: 0, per_work: [] }));

    expect(container.querySelector(".spark")).not.toBeNull();
    expect(container.querySelectorAll(".spark .bar").length).toBe(0);
  });

  it("keeps the count whether or not the sparkline is drawn", () => {
    // What the reader asked to keep. The count is the row's own cell and has
    // nothing to do with the distribution.
    const many = renderRow(makeRow());
    expect(many.container.querySelector(".ct")?.textContent).toBe("682");

    const one = renderRow(
      makeRow({ distinct_works: 1, count: 1438, per_work: [{ work: "W", n: 1438 }] }),
    );
    expect(one.container.querySelector(".ct")?.textContent).toBe("1,438");
  });

  it("names the work in each bar's tooltip, not just the number", () => {
    const { container } = renderRow(makeRow());
    const bars = container.querySelectorAll(".spark .bar");
    expect(bars[0]!.getAttribute("title")).toBe("Phänomenologie des Geistes: 400");
  });

  it("names what the bars mean, so they are not read as broken", () => {
    // There is no column header on the leaderboard and no legend; before this
    // the only affordance was a `title` on each bar showing the bare integer,
    // which at single-work scope duplicated the count two cells to the left.
    const { container } = renderRow(makeRow());
    expect(container.querySelector(".spark")?.getAttribute("title")).toContain(
      "top works",
    );
  });
});
