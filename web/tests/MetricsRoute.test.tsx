// `MetricsRoute` is the thin wiring between the `#/metrics` route and
// `MetricsPanel` — same shape as `NetworkRoute`/`RefsRoute`. This file
// covers that wiring specifically (window/label pass-through, `onNavigate`
// turning into `routing.navigate`, and the wrong-route guard); the panel's
// own behavior is `tests/MetricsPanel.test.tsx`'s job.

import { ErrorBoundary } from "solid-js";
import { render, waitFor } from "@solidjs/testing-library";
import { describe, expect, it, vi, afterEach } from "vitest";
import { MetricsRoute } from "~/routes/MetricsRoute";
import type { RouteContextProps } from "~/routes/types";
import { createTestRouting, type TestRouting } from "./helpers/testRouting";

function makeCtx(routing: TestRouting): RouteContextProps {
  // `MetricsRoute` only ever reads `props.routing` — every other field on
  // `RouteContextProps` exists for other route files. Stubbed rather than
  // built for real (which would mean standing up `useConversations`,
  // `useReader`, `useTheme`) since nothing here exercises them.
  return {
    routing,
    conversations: {} as unknown as RouteContextProps["conversations"],
    reader: {} as unknown as RouteContextProps["reader"],
    themeApi: {} as unknown as RouteContextProps["themeApi"],
    scrolled: () => false,
    sidebarCollapsed: () => false,
    setSidebarCollapsed: () => undefined,
    conversationTitle: () => null,
    openSourceInReader: () => undefined,
    onScrollChange: () => undefined,
    marginNotes: true,
  };
}

function mockSummary() {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true, status: 200,
    json: () => Promise.resolve({ window: "24h", since: 0, until: 1, rows: [] }),
  }));
}

afterEach(() => vi.unstubAllGlobals());

describe("MetricsRoute", () => {
  it("forwards the route's window and label into MetricsPanel", async () => {
    mockSummary();
    const routing = createTestRouting({ kind: "metrics", window: "7d", label: "chunk syntax" });
    const view = render(() => <MetricsRoute {...makeCtx(routing)} />);
    await waitFor(() => {
      expect(view.getByText("7d").classList.contains("active")).toBe(true);
    });
  });

  it("turns the panel's onNavigate into routing.navigate", async () => {
    mockSummary();
    const routing = createTestRouting({ kind: "metrics" });
    const view = render(() => <MetricsRoute {...makeCtx(routing)} />);
    const oneHour = await view.findByText("1h");
    oneHour.click();
    expect(routing.navigateSpy).toHaveBeenCalledWith({
      kind: "metrics",
      window: "1h",
      label: undefined,
    });
  });

  it("throws when mounted off a non-metrics route, for an ErrorBoundary above it to catch", async () => {
    mockSummary();
    const routing = createTestRouting({ kind: "landing" });
    const view = render(() => (
      <ErrorBoundary fallback={(err) => <div>broke: {(err as Error).message}</div>}>
        <MetricsRoute {...makeCtx(routing)} />
      </ErrorBoundary>
    ));
    await waitFor(() => {
      expect(view.getByText(/expected metrics route/i)).toBeTruthy();
    });
  });
});
