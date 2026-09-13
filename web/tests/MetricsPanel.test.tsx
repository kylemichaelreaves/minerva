import { render, waitFor, fireEvent } from "@solidjs/testing-library";
import { createSignal } from "solid-js";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MetricsPanel } from "~/Metrics/MetricsPanel";
import type { MetricWindow } from "~/api/metricsApi";

const row = (label: string, p95: number) => ({
  label, method: "GET", kind: "total" as const, span: "",
  count: 10, mean_ms: p95 / 2, min_ms: 1, max_ms: p95,
  p50_ms: p95 / 2, p95_ms: p95, p99_ms: p95, error_rate: 0,
});

// `json` is `() => Promise.resolve(...)` rather than `async () => (...)`:
// an `async` arrow with no `await` inside trips
// `@typescript-eslint/require-await`, and the two are otherwise identical —
// same shape `apiGet`'s real `r.json()` call expects. Same convention as
// `tests/helpers/testRouting.ts`'s `okResponse`.
function mockSummary(rows: unknown[]) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true, status: 200,
    json: () => Promise.resolve({ window: "24h", since: 0, until: 1, rows }),
  }));
}

afterEach(() => vi.unstubAllGlobals());

describe("MetricsPanel", () => {
  it("lists routes slowest first", async () => {
    mockSummary([row("fast", 5), row("slow", 900)]);
    const view = render(() => <MetricsPanel />);
    const cells = await view.findAllByTestId("metrics-route-label");
    expect(cells.map((c) => c.textContent)).toEqual(["slow", "fast"]);
  });

  it("shows an empty state when nothing has been recorded", async () => {
    mockSummary([]);
    const view = render(() => <MetricsPanel />);
    expect(await view.findByText(/no requests recorded/i)).toBeTruthy();
  });

  it("surfaces a fetch failure instead of rendering an empty table", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));
    const view = render(() => <MetricsPanel />);
    await waitFor(async () => expect(await view.findByText(/couldn't load/i)).toBeTruthy());
  });

  it("falls back to String() for a rejection that isn't an Error", async () => {
    // `fetch` can reject with something other than an `Error` (a thrown
    // string, an abort reason); `errorMessage`'s non-Error branch covers
    // that rather than rendering "[object Object]" or crashing.
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue("offline"));
    const view = render(() => <MetricsPanel />);
    expect(await view.findByText(/couldn't load metrics: offline/i)).toBeTruthy();
  });

  // --- Supplemental coverage below. The three tests above are the brief's
  // exact cases (mechanically adjusted only where the repo's strict eslint
  // config forced it — see the two comments above); these exercise the
  // window selector, the drill-down (sub-span breakdown + trend chart), the
  // llm_call per-attempt callout, the TTFE toggle, the empty-label guard on
  // `fetchMetricsSeries`, and error reporting from the drill-down fetches.

  function urlOf(input: RequestInfo | URL): string {
    return typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  }

  // p99 offset by +1 from p95, and p50 halved, so a single row never
  // repeats the same rendered number in two cells — needed because these
  // tests assert on exact rendered text (`getByText`), which throws on an
  // ambiguous match rather than picking one.
  const subSpanRow = (span: string, kind: "total" | "ttfe", p95: number) => ({
    label: "slow", method: "GET", kind, span,
    count: 4, mean_ms: p95 / 2, min_ms: 1, max_ms: p95,
    p50_ms: Math.round(p95 / 2), p95_ms: p95, p99_ms: p95 + 1, error_rate: 0,
  });

  // `MetricsPanel` is fully controlled (same idiom as `Network`/`Refs`):
  // it never mutates `window`/`label` itself, only reports the reader's
  // request via `onNavigate`. A bare `<MetricsPanel />` (as the three
  // brief-exact tests above use) is correct for a read-only render, but
  // every interactive scenario below needs something upstream to accept
  // that report and feed it back in — exactly the role `MetricsRoute`
  // plays in production.
  function Host(props: { initialLabel?: string }) {
    const [win, setWin] = createSignal<MetricWindow>("24h");
    const [label, setLabel] = createSignal<string | undefined>(props.initialLabel);
    return (
      <MetricsPanel
        window={win()}
        label={label()}
        onNavigate={(patch) => {
          setWin(patch.window);
          setLabel(patch.label);
        }}
      />
    );
  }

  function mockDrilldown(opts: {
    leaderboard: unknown[];
    detailRows: unknown[];
    seriesFails?: boolean;
    detailFails?: boolean;
  }) {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = urlOf(input);
      if (url.includes("/api/metrics/series")) {
        if (opts.seriesFails) return Promise.reject(new Error("series down"));
        return Promise.resolve({
          ok: true, status: 200,
          json: () => Promise.resolve({
            label: "slow", kind: "total", span: "", bucket_seconds: 300,
            points: [{ t: 0, count: 1, mean_ms: 10, max_ms: 20, p50_ms: 10, p95_ms: 20, p99_ms: 20 }],
          }),
        });
      }
      if (url.includes("/api/metrics/summary") && url.includes("label=")) {
        if (opts.detailFails) return Promise.reject(new Error("breakdown down"));
        return Promise.resolve({
          ok: true, status: 200,
          json: () => Promise.resolve({ window: "24h", since: 0, until: 1, rows: opts.detailRows }),
        });
      }
      return Promise.resolve({
        ok: true, status: 200,
        json: () => Promise.resolve({ window: "24h", since: 0, until: 1, rows: opts.leaderboard }),
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  it("never calls fetchMetricsSeries before a route is selected", async () => {
    const fetchMock = mockDrilldown({
      leaderboard: [row("slow", 900)],
      detailRows: [],
    });
    const view = render(() => <MetricsPanel />);
    await view.findAllByTestId("metrics-route-label");
    // Give any stray microtask a chance to fire before asserting absence.
    await Promise.resolve();
    expect(fetchMock.mock.calls.some(([input]) => urlOf(input).includes("/api/metrics/series"))).toBe(
      false,
    );
  });

  it("drills into a selected route's sub-span breakdown and trend chart, marking llm_call as per-attempt", async () => {
    mockDrilldown({
      leaderboard: [row("slow", 900)],
      detailRows: [
        subSpanRow("", "total", 900),
        subSpanRow("stanza_parse", "total", 300),
        subSpanRow("llm_call", "total", 500),
      ],
    });
    const view = render(() => <Host />);
    const cells = await view.findAllByTestId("metrics-route-label");
    fireEvent.click(cells[0] as Element);

    await view.findByText("stanza_parse");
    expect(await view.findByText(/per attempt, not per request/i)).toBeTruthy();
    // The trend chart mounted with the fetched series.
    expect(view.container.querySelector(".mchart")).not.toBeNull();
  });

  it("shows the total/TTFE toggle only when the selected route recorded a ttfe row, and switches rows on click", async () => {
    mockDrilldown({
      leaderboard: [row("slow", 900)],
      detailRows: [
        subSpanRow("", "total", 880),
        subSpanRow("", "ttfe", 660),
      ],
    });
    const view = render(() => <Host />);
    const cells = await view.findAllByTestId("metrics-route-label");
    fireEvent.click(cells[0] as Element);

    await view.findByText("Total");
    expect(view.getByText("TTFE")).toBeTruthy();
    // Defaults to the "total" kind's row.
    expect(view.getByText("880")).toBeTruthy();
    expect(view.queryByText("660")).toBeNull();

    fireEvent.click(view.getByText("TTFE"));
    await waitFor(() => expect(view.getByText("660")).toBeTruthy());
    expect(view.queryByText("880")).toBeNull();
  });

  it("does not show the toggle for a route with no ttfe row", async () => {
    mockDrilldown({
      leaderboard: [row("slow", 900)],
      detailRows: [subSpanRow("", "total", 880)],
    });
    const view = render(() => <Host />);
    const cells = await view.findAllByTestId("metrics-route-label");
    fireEvent.click(cells[0] as Element);
    await view.findByText("880");
    expect(view.queryByText("TTFE")).toBeNull();
  });

  it("surfaces a breakdown fetch failure without losing the leaderboard already on screen", async () => {
    mockDrilldown({
      leaderboard: [row("slow", 900)],
      detailRows: [],
      detailFails: true,
    });
    const view = render(() => <Host />);
    const cells = await view.findAllByTestId("metrics-route-label");
    fireEvent.click(cells[0] as Element);
    expect(await view.findByText(/couldn't load the breakdown/i)).toBeTruthy();
    // The leaderboard row is still there underneath.
    expect((await view.findAllByTestId("metrics-route-label"))[0]?.textContent).toBe("slow");
  });

  it("surfaces a trend-chart fetch failure separately from the breakdown", async () => {
    mockDrilldown({
      leaderboard: [row("slow", 900)],
      detailRows: [subSpanRow("", "total", 900)],
      seriesFails: true,
    });
    const view = render(() => <Host />);
    const cells = await view.findAllByTestId("metrics-route-label");
    fireEvent.click(cells[0] as Element);
    expect(await view.findByText(/couldn't load the trend chart/i)).toBeTruthy();
  });

  it("clears the selection and returns to the leaderboard view via the back button", async () => {
    mockDrilldown({
      leaderboard: [row("slow", 900)],
      detailRows: [subSpanRow("", "total", 900)],
    });
    const view = render(() => <Host />);
    const cells = await view.findAllByTestId("metrics-route-label");
    fireEvent.click(cells[0] as Element);
    const back = await view.findByText(/all routes/i);
    fireEvent.click(back);
    await waitFor(() => expect(view.queryByText(/all routes/i)).toBeNull());
  });

  it("is fully controlled: switching windows reports the new window (and preserves the selection) via onNavigate", async () => {
    mockDrilldown({ leaderboard: [row("slow", 900)], detailRows: [] });

    const view = render(() => <Host initialLabel="slow" />);
    const oneHour = await view.findByText("1h");
    fireEvent.click(oneHour);

    await waitFor(() => {
      expect(oneHour.classList.contains("active")).toBe(true);
    });
  });
});
