import { describe, expect, it } from "vitest";
import { LABEL_TEXT_DY, buildArcLayout, tickLabelsToDraw } from "~/Network/components/NetworkArc";
import { ATLAS_AUTHORS } from "~/data/atlasData";
import { YEAR_TICKS } from "~/utils/atlasGeometry";

// Regression cover for #128: the mobile arc canvas was a hardcoded
// 390×1320 viewBox while the label layout grew with the corpus, so the
// last seven authors — Nietzsche among them — rendered below the
// viewBox and were clipped with no scroll able to reach them.
//
// Both assertions below are invariants the canvas must hold for
// whatever ATLAS_AUTHORS currently contains. Pinning them against the
// real table (not a fixture) is the point: the bug was that the table
// grew and the constants didn't.

describe("buildArcLayout", () => {
  it("keeps every author label inside the canvas", () => {
    const { labels, vbHeight } = buildArcLayout(ATLAS_AUTHORS);

    // The rendered baseline, not the layout y — a label sitting just
    // inside the viewBox still gets sliced once the text offset is
    // applied, which is how "Schiller" was cut mid-glyph.
    const clipped = labels.filter((l) => l.yLbl + LABEL_TEXT_DY > vbHeight).map((l) => l.name);

    expect(clipped).toEqual([]);
  });

  it("maps the latest author onto the baseline, not past its end", () => {
    const { labels, yBottom } = buildArcLayout(ATLAS_AUTHORS);

    const latest = labels.at(-1);

    expect(latest?.yNat).toBeLessThanOrEqual(yBottom);
  });
});

// "Hebrew Bible" is year −1000, the chronology domain's minimum, so
// its label lands exactly on the −1000 tick by construction and the
// two render on top of each other ("−100(Hebrew Bible"). The tick mark
// stays; only its now-redundant text is suppressed.
//
// Suppression has to weigh horizontal extent, not just vertical
// distance: author labels are right-anchored at x=100 and tick labels
// start at x=14, so a short name never reaches the tick column even
// when it shares the line. Measured against the rendered SVG, exactly
// one of the seven ticks actually overlaps.
describe("tickLabelsToDraw", () => {
  it("drops the tick label the first author renders on top of", () => {
    const { labels, yOf } = buildArcLayout(ATLAS_AUTHORS);

    const drawn = tickLabelsToDraw(YEAR_TICKS, labels, yOf);

    expect(drawn).not.toContain(-1000);
  });

  it("keeps ticks whose neighbouring label is too short to reach them", () => {
    const { labels, yOf } = buildArcLayout(ATLAS_AUTHORS);

    const drawn = tickLabelsToDraw(YEAR_TICKS, labels, yOf);

    // −500 shares a line with "Theognis" (Δy 0.6) and 1880 with "Hume"
    // (Δy 2.6), but both names end well right of the tick column.
    expect(drawn).toContain(-500);
    expect(drawn).toContain(1880);
    expect(drawn).toContain(1000);
  });
});
