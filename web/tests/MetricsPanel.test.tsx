import { render, waitFor, fireEvent } from "@solidjs/testing-library";
import { createSignal } from "solid-js";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MetricsPanel, errorMessage } from "~/Metrics/MetricsPanel";
import type { MetricWindow } from "~/api/metricsApi";

const row = (label: string, p95: number) => ({
  label,
  method: "GET",
  kind: "total" as const,
  span: "",
  count: 10,
  mean_ms: p95 / 2,
  min_ms: 1,
  max_ms: p95,
  p50_ms: p95 / 2,
  p95_ms: p95,
  p99_ms: p95,
  error_rate: 0,
});

// `json` is `() => Promise.resolve(...)` rather than `async () => (...)`:
// an `async` arrow with no `await` inside trips
// `@typescript-eslint/require-await`, and the two are otherwise identical —
// same shape `apiGet`'s real `r.json()` call expects. Same convention as
// `tests/helpers/testRouting.ts`'s `okResponse`.
function mockSummary(rows: unknown[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ window: "24h", since: 0, until: 1, rows }),
    }),
  );
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

  it("surfaces a string rejection's message once Solid's castError wraps it into an Error", async () => {
    // NOT a demonstration of `errorMessage`'s non-Error fallback (a
    // previous version of this test claimed that, and it was wrong —
    // caught in review). Solid's `createResource` runs every rejection
    // through its own `castError` before `.error` is ever readable, and
    // `castError` turns a string rejection into `new Error(str)` — so
    // `err instanceof Error` is true here too, same as the plain-`Error`
    // case above; the text comes from `.message`, not `String(err)`. The
    // `String()` branch itself is unreachable through any resource for
    // exactly that reason, and is covered directly below instead, calling
    // `errorMessage` as a plain function with something `castError` never
    // produces.
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue("offline"));
    const view = render(() => <MetricsPanel />);
    expect(await view.findByText(/couldn't load metrics: offline/i)).toBeTruthy();
  });

  describe("errorMessage", () => {
    it("reads .message off an Error", () => {
      expect(errorMessage(new Error("boom"))).toBe("boom");
    });

    it("falls back to String() for a value that is genuinely not an Error", () => {
      // The one shape `castError` never produces, so the only way to
      // reach this branch is to call the function directly rather than
      // through a resource.
      expect(errorMessage({ toString: () => "offline-reason" })).toBe("offline-reason");
    });
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

  // The UNLABELED summary's second row shape for a streaming route: same
  // label, `kind: "ttfe"`, still `span: ""` (`store.py`'s unlabeled
  // branch filters on `span = ''` with no `kind` filter, so a streaming
  // route's `total` and `ttfe` rows are both in this response — never in
  // the labeled drill-down, which excludes `span = ''` entirely).
  const ttfeRow = (label: string, p95: number) => ({
    label,
    method: "GET",
    kind: "ttfe" as const,
    span: "",
    count: 4,
    mean_ms: p95 / 2,
    min_ms: 1,
    max_ms: p95,
    p50_ms: p95 / 2,
    p95_ms: p95,
    p99_ms: p95,
    error_rate: 0,
  });

  // Labeled (drill-down) rows: ALWAYS `kind: "total"` and ALWAYS a
  // non-empty `span` — the recorder never tags a sub-span `ttfe`, and
  // `store.py`'s labeled branch is `label = ? AND span != ''`. A row
  // shaped any other way (an empty `span`, or `kind: "ttfe"`) is not a
  // shape this endpoint can produce; the previous version of this fixture
  // let both through, which is exactly how the toggle tests below used to
  // pass against an API shape that doesn't exist (caught in review).
  const subSpanRow = (span: string, p95: number) => ({
    label: "slow",
    method: "GET",
    kind: "total" as const,
    span,
    count: 4,
    mean_ms: p95 / 2,
    min_ms: 1,
    max_ms: p95,
    p50_ms: Math.round(p95 / 2),
    p95_ms: p95,
    p99_ms: p95 + 1,
    error_rate: 0,
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
        // Distinct p95 per `kind` so a test can tell, from the fetched
        // points alone, which one a click actually asked for.
        const isTtfe = url.includes("kind=ttfe");
        const p95 = isTtfe ? 111 : 999;
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              label: "slow",
              kind: isTtfe ? "ttfe" : "total",
              span: "",
              bucket_seconds: 300,
              points: [
                {
                  t: 0,
                  count: 1,
                  mean_ms: p95 / 2,
                  max_ms: p95,
                  p50_ms: p95 / 2,
                  p95_ms: p95,
                  p99_ms: p95,
                },
              ],
            }),
        });
      }
      if (url.includes("/api/metrics/summary") && url.includes("label=")) {
        if (opts.detailFails) return Promise.reject(new Error("breakdown down"));
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ window: "24h", since: 0, until: 1, rows: opts.detailRows }),
        });
      }
      return Promise.resolve({
        ok: true,
        status: 200,
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
    expect(
      fetchMock.mock.calls.some(([input]) => urlOf(input).includes("/api/metrics/series")),
    ).toBe(false);
  });

  it("drills into a selected route's sub-span breakdown and trend chart, marking llm_call as per-attempt", async () => {
    mockDrilldown({
      leaderboard: [row("slow", 900)],
      detailRows: [subSpanRow("stanza_parse", 300), subSpanRow("llm_call", 500)],
    });
    const view = render(() => <Host />);
    const cells = await view.findAllByTestId("metrics-route-label");
    fireEvent.click(cells[0] as Element);

    await view.findByText("stanza_parse");
    expect(await view.findByText(/per attempt, not per request/i)).toBeTruthy();
    // The trend chart mounted with the fetched series.
    expect(view.container.querySelector(".mchart")).not.toBeNull();
  });

  it("lists a streaming route exactly once, not twice for its total and ttfe rows", async () => {
    // The unlabeled summary carries BOTH rows for a streaming route —
    // same label, `kind: "total"` and `kind: "ttfe"`, both `span: ""`
    // (`store.py`'s unlabeled branch has no `kind` filter). Rendering
    // every row verbatim used to list "chat" twice with different
    // numbers and no column saying why (caught in review) — the
    // leaderboard must keep only the `total` half.
    mockSummary([row("chat", 900), ttfeRow("chat", 700), row("fast", 5)]);
    const view = render(() => <MetricsPanel />);
    const cells = await view.findAllByTestId("metrics-route-label");
    expect(cells.map((c) => c.textContent)).toEqual(["chat", "fast"]);
  });

  it("shows the total/TTFE toggle only when the selected route's UNLABELED rows include a ttfe measurement, and re-fetches the chart by kind on click", async () => {
    mockDrilldown({
      // The ttfe row lives in the leaderboard (unlabeled) response, not
      // the drill-down — that's the whole point of the fix.
      leaderboard: [row("slow", 900), ttfeRow("slow", 700)],
      detailRows: [subSpanRow("stanza_parse", 300)],
    });
    const view = render(() => <Host />);
    const cells = await view.findAllByTestId("metrics-route-label");
    fireEvent.click(cells[0] as Element);

    await view.findByText("Total");
    expect(view.getByText("TTFE")).toBeTruthy();
    // Default view: the chart fetched the "total" series (p95 999, per
    // `mockDrilldown`'s kind-keyed response).
    await waitFor(() => expect(view.getByText("999", { exact: false })).toBeTruthy());

    fireEvent.click(view.getByText("TTFE"));
    // Clicking the toggle re-fetches the chart's series with kind=ttfe —
    // not just a client-side re-filter of already-fetched data — and the
    // chart now shows the ttfe series (p95 111).
    await waitFor(() => expect(view.getByText("111", { exact: false })).toBeTruthy());
  });

  it("does not show the toggle for a route with no ttfe row", async () => {
    mockDrilldown({
      leaderboard: [row("slow", 880)],
      detailRows: [subSpanRow("stanza_parse", 300)],
    });
    const view = render(() => <Host />);
    const cells = await view.findAllByTestId("metrics-route-label");
    fireEvent.click(cells[0] as Element);
    await view.findByText("stanza_parse");
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

  it("surfaces a trend-chart fetch failure separately from the breakdown, without also showing the chart's own empty state", async () => {
    mockDrilldown({
      leaderboard: [row("slow", 900)],
      detailRows: [subSpanRow("stanza_parse", 300)],
      seriesFails: true,
    });
    const view = render(() => <Host />);
    const cells = await view.findAllByTestId("metrics-route-label");
    fireEvent.click(cells[0] as Element);
    expect(await view.findByText(/couldn't load the trend chart/i)).toBeTruthy();
    // Not both explanations for the same blank chart at once.
    expect(view.queryByText(/no data/i)).toBeNull();
  });

  it("shows a loading state for the trend chart instead of flashing its empty state while the series fetch is in flight", async () => {
    let resolveSeries!: (v: unknown) => void;
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = urlOf(input);
      if (url.includes("/api/metrics/series")) {
        return new Promise((resolve) => {
          resolveSeries = resolve;
        });
      }
      if (url.includes("/api/metrics/summary") && url.includes("label=")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              window: "24h",
              since: 0,
              until: 1,
              rows: [subSpanRow("stanza_parse", 300)],
            }),
        });
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve({ window: "24h", since: 0, until: 1, rows: [row("slow", 900)] }),
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const view = render(() => <Host />);
    const cells = await view.findAllByTestId("metrics-route-label");
    fireEvent.click(cells[0] as Element);

    expect(await view.findByText(/loading trend/i)).toBeTruthy();
    expect(view.queryByText(/no data/i)).toBeNull();

    resolveSeries({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          label: "slow",
          kind: "total",
          span: "",
          bucket_seconds: 300,
          points: [{ t: 0, count: 1, mean_ms: 10, max_ms: 20, p50_ms: 10, p95_ms: 20, p99_ms: 20 }],
        }),
    });
    await waitFor(() => expect(view.queryByText(/loading trend/i)).toBeNull());
    expect(view.container.querySelector(".mchart")).not.toBeNull();
  });

  it("clears the selection and returns to the leaderboard view via the back button", async () => {
    mockDrilldown({
      leaderboard: [row("slow", 900)],
      detailRows: [subSpanRow("stanza_parse", 300)],
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

  it("puts the chart above the table, and lets only the table scroll", async () => {
    // The window buttons drive the chart, so the chart sits directly under
    // them and the table scrolls beneath both. Before this the table came
    // first and was taller than the viewport on its own — 15 rows measured
    // at 621px against a 560px viewport — leaving the chart 472px below the
    // fold. jsdom does no layout, so assert the structure that produces it.
    mockSummary([row("chat", 900)]);
    const view = render(() => <MetricsPanel />);
    await view.findAllByTestId("metrics-route-label");

    const panel = view.container.querySelector(".metrics-panel");
    const order = [...panel!.children].map((c) => c.className);
    expect(order.indexOf("metrics-head")).toBeLessThan(order.indexOf("metrics-table-wrap"));

    const wrap = view.container.querySelector(".metrics-table-wrap");
    expect(wrap).not.toBeNull();
    expect(wrap!.querySelector("table.metrics-table")).not.toBeNull();
  });

  it("renders no sub-span table when the route has no sub-spans", async () => {
    // Only three code paths are instrumented, so most routes have none —
    // `health` measured live with 0 sub-span rows. Rendering the table
    // anyway left a bare "Span Count p50 p95 p99" header under the chart,
    // labelling nothing, directly above the route table's near-identical
    // header. A header with no table is not a table.
    mockDrilldown({ leaderboard: [row("health", 5)], detailRows: [] });
    const view = render(() => <Host />);
    const cells = await view.findAllByTestId("metrics-route-label");
    fireEvent.click(cells[0] as Element);

    // Wait for the drill-down to settle: the chart mounts once the series
    // resolves, which is also when the sub-span table would appear.
    await view.findByText("← All routes");
    await waitFor(() => {
      expect(view.container.querySelector(".mchart")).not.toBeNull();
    });
    expect(view.container.querySelector(".metrics-subspan-table")).toBeNull();
    expect(view.queryByText("Span")).toBeNull();
  });
});
