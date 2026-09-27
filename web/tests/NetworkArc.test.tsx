import { fireEvent, render, screen } from "@solidjs/testing-library";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchNetworkSummary, type AuthorPair } from "~/api/networkApi";
import { selectArcPairs } from "~/Network/components/ArcPanel";
import { NetworkArc } from "~/Network/components/NetworkArc";
import { makeNetworkSummary } from "./helpers/networkSummary";

vi.mock("~/api/networkApi", async (importOriginal) => ({
  ...(await importOriginal<typeof import("~/api/networkApi")>()),
  fetchNetworkSummary: vi.fn(),
}));
// Pass-through spy, so one test can bypass the name filter and reach the
// render-side guard that drops a pair with no known year.
vi.mock("~/Network/components/ArcPanel", async (importOriginal) => {
  const real = await importOriginal<typeof import("~/Network/components/ArcPanel")>();
  return { ...real, selectArcPairs: vi.fn(real.selectArcPairs) };
});
const fetchMock = vi.mocked(fetchNetworkSummary);

const pair = (src: string, tgt: string, n: number): AuthorPair => ({
  src,
  tgt,
  n,
  intra_scrip: false,
});

beforeEach(() => {
  fetchMock.mockReset();
});

/** Arc paths are the only elliptical-arc (`A`) paths in the SVG. */
function arcPaths(container: HTMLElement): SVGPathElement[] {
  return [...container.querySelectorAll<SVGPathElement>("svg path")].filter((p) =>
    (p.getAttribute("d") ?? "").includes(" A "),
  );
}

/** Tap each arc and read which pair the tooltip names, keyed to its stroke. */
function strokeByPair(container: HTMLElement): Record<string, string | null> {
  const out: Record<string, string | null> = {};
  for (const path of arcPaths(container)) {
    fireEvent.click(path);
    const label = container.querySelector(".net-tooltip .pair")?.textContent ?? "";
    out[label] = path.getAttribute("stroke");
  }
  return out;
}

describe("<NetworkArc />", () => {
  it("draws one arc per pair with known years; oxblood when citing backward in time", async () => {
    fetchMock.mockResolvedValueOnce(
      makeNetworkSummary({
        xrefs: 4321,
        pairs: [
          pair("Nietzsche", "Plato", 90),
          pair("Aquinas", "Kant", 3),
          pair("Nobody", "Plato", 50),
        ],
      }),
    );
    const { container } = render(() => <NetworkArc onBack={vi.fn()} onOpenAuthor={vi.fn()} />);
    expect(await screen.findByText((4321).toLocaleString())).toBeTruthy();

    // "Nobody" has no year, so only two arcs render.
    expect(arcPaths(container)).toHaveLength(2);
    expect(strokeByPair(container)).toEqual({
      "Nietzsche→Plato": "var(--accent)",
      "Aquinas→Kant": "var(--ink-mute, #6b6357)",
    });
    expect(container.querySelector(".net-tooltip .count")?.textContent).toBe("3 references");
  });

  it("drops a pair whose endpoint has no year even if the selector lets it through", async () => {
    vi.mocked(selectArcPairs).mockImplementationOnce((primary) => primary);
    fetchMock.mockResolvedValueOnce(
      makeNetworkSummary({
        xrefs: 7,
        pairs: [pair("Nobody", "Plato", 5), pair("Plato", "Nobody", 5), pair("Homer", "Plato", 1)],
      }),
    );
    const { container } = render(() => <NetworkArc onBack={vi.fn()} onOpenAuthor={vi.fn()} />);
    await screen.findByText("7");

    const arcs = arcPaths(container);
    expect(arcs).toHaveLength(1);
    expect(arcs[0]?.getAttribute("d")).not.toContain("NaN");
    // Homer (−800) → Plato (−380) cites forward in time.
    expect(strokeByPair(container)).toEqual({ "Homer→Plato": "var(--ink-mute, #6b6357)" });
    expect(container.querySelector(".net-tooltip .count")?.textContent).toBe("1 reference");
  });
});
