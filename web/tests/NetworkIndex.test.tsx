import { fireEvent, render, screen, waitFor } from "@solidjs/testing-library";
import { createSignal, flush } from "solid-js";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fetchNetworkSummary, type NetworkAuthor } from "~/api/networkApi";
import { MobileShellProvider } from "~/components/shell/MobileShellContext";
import Network from "~/Network";
import { fakeMediaQueryList } from "./helpers/matchMedia";
import { makeNetworkSummary } from "./helpers/networkSummary";

vi.mock("~/api/networkApi", async (importOriginal) => ({
  ...(await importOriginal<typeof import("~/api/networkApi")>()),
  fetchNetworkSummary: vi.fn(),
}));
const fetchMock = vi.mocked(fetchNetworkSummary);
vi.mock("~/api/landingApi", () => ({
  fetchLandingStats: vi.fn(() => Promise.resolve({ authors: 48, works: 867, xrefs: 57848 })),
}));

const plato: NetworkAuthor = { name: "Plato", short: "Pl", ord: 100, corpus: "class" };
const kant: NetworkAuthor = { name: "Kant", short: "Ka", ord: 900, corpus: "mod" };
// The matrix drops authors who are never cited, so a lone author needs a
// cell to get a column.
const SELF = { r: 0, c: 0, n: 1 };

beforeEach(() => {
  fetchMock.mockReset();
});
afterEach(() => {
  vi.restoreAllMocks();
});

function forceMobile() {
  vi.spyOn(window, "matchMedia").mockImplementation((query: string) =>
    fakeMediaQueryList(query, true),
  );
}

function mount(initialConf?: number) {
  const [conf, setConf] = createSignal(initialConf);
  const handlers = {
    onOpenPair: vi.fn(),
    onOpenTargetWork: vi.fn(),
    onOpenArc: vi.fn(),
    onOpenCoverage: vi.fn(),
    onOpenAuthor: vi.fn(),
  };
  const result = render(() => (
    <MobileShellProvider>
      <Network minConfidence={conf()} onNavigate={vi.fn()} {...handlers} />
    </MobileShellProvider>
  ));
  return { ...result, setConf, handlers };
}

/** The matrix panel's column labels name the summary's cited authors. They
 *  are the rotated <text> directly under the SVG; the rotated row-band
 *  captions sit inside a <g>. */
function matrixColumns(container: HTMLElement): string[] {
  return [...container.querySelectorAll('[data-panel="matrix"] svg > text[transform]')].map(
    (t) => t.textContent,
  );
}

describe("<Network />", () => {
  it("renders the body from the loaded summary and re-renders it on refetch", async () => {
    fetchMock.mockResolvedValueOnce(
      makeNetworkSummary({ xrefs: 1000, authors: [plato], cells: [SELF] }),
    );
    const { container, setConf } = mount(0.5);

    expect(container.querySelector(".net-loading")).toHaveTextContent("Loading citation network…");
    await waitFor(() => {
      expect(matrixColumns(container)).toEqual(["Pl"]);
    });
    expect(container.querySelector(".net-footer")).toHaveTextContent(
      `${(1000).toLocaleString()} xrefs`,
    );

    fetchMock.mockResolvedValueOnce(
      makeNetworkSummary({ xrefs: 2000, authors: [kant], cells: [SELF] }),
    );
    setConf(0.9);
    await waitFor(() => {
      expect(matrixColumns(container)).toEqual(["Ka"]);
    });
    expect(container.querySelector(".net-footer")).toHaveTextContent(
      `${(2000).toLocaleString()} xrefs`,
    );
  });

  it("renders a summary with no authors instead of overflowing the stack", async () => {
    // A filter that matches nothing returns an empty matrix. The author-seed
    // effect read `allAuthors()` and wrote a fresh `[]` back, which Solid
    // treats as a change, so it re-ran itself until "Maximum call stack size
    // exceeded" — caught by the fetch hook and shown as the network's error.
    // Found when #761 mocked the summary and asserted the page rendered.
    fetchMock.mockResolvedValueOnce(makeNetworkSummary({ xrefs: 0 }));
    const { container } = mount();

    await waitFor(() => {
      expect(container.querySelector(".net-loading")).toBeNull();
    });
    expect(container.querySelector(".net-error")).toBeNull();
    expect(container.querySelector(".net-footer")).toHaveTextContent("0 xrefs");
  });

  it("hides the body and shows the error when the fetch fails", async () => {
    fetchMock.mockRejectedValueOnce(new Error("network summary unavailable"));
    const { container } = mount();
    await waitFor(() => {
      expect(container.querySelector(".net-error")).toHaveTextContent(
        "network summary unavailable",
      );
    });
    expect(container.querySelector(".net-body")).toBeNull();
    expect(screen.queryByText("Author × Author citation matrix")).toBeNull();
  });

  it("carries the Atlas timeline on desktop; picking an author opens their citations", async () => {
    fetchMock.mockResolvedValueOnce(makeNetworkSummary({ authors: [plato], cells: [SELF] }));
    const { container, handlers } = mount();
    const band = await waitFor(() => {
      const el = container.querySelector(".net-atlas-band .net-atlas");
      expect(el).not.toBeNull();
      return el as HTMLElement;
    });
    await waitFor(() => {
      expect(band.querySelector(".net-atlas-caption")).toHaveTextContent(
        `${(57848).toLocaleString()} VERIFIED CROSS-REFERENCES`,
      );
    });
    const first = band.querySelector<SVGGElement>(".atlas-author");
    if (!first) throw new Error("no atlas author");
    fireEvent.click(first);
    expect(handlers.onOpenAuthor).toHaveBeenCalledTimes(1);
    expect(handlers.onOpenAuthor.mock.calls[0]?.[0]).toEqual(expect.any(String));
  });

  it("leaves the Atlas off at phone width", async () => {
    forceMobile();
    fetchMock.mockResolvedValueOnce(makeNetworkSummary({ authors: [plato], cells: [SELF] }));
    const { container } = mount();
    await waitFor(() => expect(container.querySelector(".net-loading")).toBeNull());
    expect(container.querySelector(".net-atlas")).toBeNull();
  });

  it("mobile body routes pair, work, and footer taps to the Network's handlers", async () => {
    forceMobile();
    fetchMock.mockResolvedValueOnce(
      makeNetworkSummary({
        xrefs: 10,
        authors: [plato, kant],
        pairs: [{ src: "Kant", tgt: "Plato", n: 10, intra_scrip: false }],
        works: [{ author: "Plato", work: "Republic", n: 7 }],
      }),
    );
    const { handlers } = mount();

    fireEvent.click(await screen.findByRole("button", { name: /Kant\s*→\s*Plato/ }));
    expect(handlers.onOpenPair).toHaveBeenCalledWith("Kant", "Plato");

    fireEvent.click(screen.getByRole("button", { name: /Republic/ }));
    expect(handlers.onOpenTargetWork).toHaveBeenCalledWith("Plato", "Republic");

    fireEvent.click(screen.getByRole("button", { name: /View as timeline/ }));
    expect(handlers.onOpenArc).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: /Verification coverage/ }));
    expect(handlers.onOpenCoverage).toHaveBeenCalledTimes(1);

    // "More views" has no route of its own: it opens the filters sheet.
    expect(screen.queryByRole("dialog", { name: "Filters" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /More views/ }));
    flush();
    expect(screen.getByRole("dialog", { name: "Filters" })).toBeTruthy();
  });
});
