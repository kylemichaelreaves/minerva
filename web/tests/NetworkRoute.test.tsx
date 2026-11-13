// `NetworkRoute` wiring between the dashboard and its two drilldowns (#891).
//
// The dashboard's "include rejected" toggle used to stop at the dashboard:
// opening a drilldown rebuilt the route from four filter fields, so the
// drilldown fetched without rejected rows, and Back rebuilt `#/network` from
// the same four fields, so the toggle was off on return.

import { fireEvent, render, screen } from "@solidjs/testing-library";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchNetworkSummary } from "~/api/networkApi";
import { MobileShellProvider } from "~/components/shell/MobileShellContext";
import type { Route } from "~/routing";
import { NetworkRoute } from "~/routes/NetworkRoute";
import { networkFiltersFromRoute } from "~/routes/routeUtils";
import type { RouteContextProps } from "~/routes/types";
import { makeNetworkSummary } from "./helpers/networkSummary";
import { createTestRouting, type TestRouting } from "./helpers/testRouting";

vi.mock("~/api/networkApi", async (importOriginal) => ({
  ...(await importOriginal<typeof import("~/api/networkApi")>()),
  fetchNetworkSummary: vi.fn(),
}));
const fetchMock = vi.mocked(fetchNetworkSummary);

function makeCtx(routing: TestRouting): RouteContextProps {
  // Only `routing` is read by NetworkRoute.
  return { routing } as unknown as RouteContextProps;
}

const FILTERS = {
  minConfidence: 0.5,
  includeRejected: true,
  sourceAuthors: ["Hegel"],
  corpora: ["de"],
  sourceMethods: ["rules"],
};

beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockResolvedValue(makeNetworkSummary());
});

describe("NetworkRoute — filters survive a drilldown round trip (#891)", () => {
  it.each(["network-arc", "network-coverage"] as const)(
    "%s fetches with the toggle and Back restores it",
    async (kind) => {
      const routing = createTestRouting({ kind, ...FILTERS });
      render(() => (
        <MobileShellProvider>
          <NetworkRoute {...makeCtx(routing)} />
        </MobileShellProvider>
      ));

      fireEvent.click(await screen.findByRole("button", { name: "Back to Network" }));

      expect(fetchMock).toHaveBeenCalledWith(
        expect.objectContaining({ includeRejected: true }),
        expect.any(AbortSignal),
      );
      expect(routing.navigateSpy).toHaveBeenLastCalledWith({ kind: "network", ...FILTERS });
    },
  );

  it("carries every dashboard filter into a drilldown route", () => {
    const dashboard: Route = { kind: "network", ...FILTERS };
    expect(networkFiltersFromRoute(dashboard)).toEqual(FILTERS);
  });
});
