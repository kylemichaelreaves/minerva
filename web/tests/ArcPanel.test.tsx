import { render, screen } from "@solidjs/testing-library";
import { describe, expect, it, vi } from "vitest";
import { ArcPanel } from "~/Network/components/ArcPanel";
import type { NetworkAuthor } from "~/api/networkApi";

const authors: NetworkAuthor[] = [
  { name: "Plato", short: "Pl", ord: 100, corpus: "class" },
  { name: "Aristotle", short: "Ar", ord: 200, corpus: "class" },
];

describe("<ArcPanel />", () => {
  it("renders panel title", () => {
    render(() => (
      <ArcPanel
        authors={authors}
        matrixCells={[]}
        topPairsAll={[]}
        topPairsNonScrip={[]}
        topPairsPerAuthor={[]}
        onOpenPair={vi.fn()}
      />
    ));
    expect(screen.getByText("Chronological arc diagram")).toBeTruthy();
  });
});
