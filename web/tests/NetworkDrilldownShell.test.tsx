import { fireEvent, render, screen, waitFor } from "@solidjs/testing-library";
import { createSignal } from "solid-js";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchNetworkSummary } from "~/api/networkApi";
import { NetworkDrilldownShell } from "~/Network/components/NetworkDrilldownShell";
import { makeNetworkSummary } from "./helpers/networkSummary";

vi.mock("~/api/networkApi", async (importOriginal) => ({
  ...(await importOriginal<typeof import("~/api/networkApi")>()),
  fetchNetworkSummary: vi.fn(),
}));
const fetchMock = vi.mocked(fetchNetworkSummary);

beforeEach(() => {
  fetchMock.mockReset();
});

describe("<NetworkDrilldownShell />", () => {
  it("renders the body with the loaded summary, and again with the refetched one", async () => {
    fetchMock.mockResolvedValueOnce(makeNetworkSummary({ xrefs: 111 }));
    const [conf, setConf] = createSignal(0.5);
    render(() => (
      <NetworkDrilldownShell title="Chronological arc" onBack={vi.fn()} minConfidence={conf()}>
        {(summary) => <p data-testid="body">xrefs={summary.totals.xrefs}</p>}
      </NetworkDrilldownShell>
    ));
    expect(screen.getByText("Chronological arc")).toBeTruthy();
    expect(await screen.findByTestId("body")).toHaveTextContent("xrefs=111");
    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ minConfidence: 0.5 }),
      expect.any(AbortSignal),
    );

    fetchMock.mockResolvedValueOnce(makeNetworkSummary({ xrefs: 222 }));
    setConf(0.9);
    await waitFor(() => {
      expect(screen.getByTestId("body")).toHaveTextContent("xrefs=222");
    });
    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ minConfidence: 0.9 }),
      expect.any(AbortSignal),
    );
  });

  it("shows Loading… until the fetch settles, then hides the body on error", async () => {
    let reject: (e: Error) => void = () => undefined;
    fetchMock.mockReturnValueOnce(
      new Promise((_, rej) => {
        reject = rej;
      }),
    );
    const children = vi.fn(() => <p data-testid="body">body</p>);
    const { container } = render(() => (
      <NetworkDrilldownShell title="Verification coverage" onBack={vi.fn()}>
        {children}
      </NetworkDrilldownShell>
    ));
    expect(container.querySelector(".net-loading")).toHaveTextContent("Loading…");

    reject(new Error("summary exploded"));
    await waitFor(() => {
      expect(container.querySelector(".net-error")).toHaveTextContent("summary exploded");
    });
    expect(screen.queryByTestId("body")).toBeNull();
    expect(children).not.toHaveBeenCalled();
  });

  it("the back button calls onBack", () => {
    fetchMock.mockReturnValueOnce(new Promise(() => undefined));
    const onBack = vi.fn();
    render(() => (
      <NetworkDrilldownShell title="t" onBack={onBack}>
        {() => <p>body</p>}
      </NetworkDrilldownShell>
    ));
    fireEvent.click(screen.getByRole("button", { name: "Back to Network" }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });
});
