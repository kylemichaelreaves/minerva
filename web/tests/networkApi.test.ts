// @vitest-environment node
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { fetchNetworkSummary } from "~/api/networkApi";

describe("networkApi", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              totals: { xrefs: 0, authors: 0, works: 0 },
              matrix: { authors: [], cells: [] },
              top_pairs: { all: [], non_scrip: [], per_author: [] },
              heatmap: { sections: [] },
              verification: [],
              top_works: [],
            }),
        }),
      ),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("builds query string for filters", async () => {
    await fetchNetworkSummary({
      minConfidence: 0.5,
      sourceAuthors: ["Plato", "Aristotle"],
      corpora: ["class"],
    });
    const url = (fetch as ReturnType<typeof vi.fn>).mock.calls[0]?.[0] as string;
    expect(url).toContain("min_confidence=0.5");
    expect(url).toContain("source_author=Plato");
    expect(url).toContain("corpus=class");
  });
});
