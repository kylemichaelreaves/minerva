import { render, waitFor, fireEvent } from "@solidjs/testing-library";
import { createSignal } from "solid-js";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MetricsPanel } from "~/Metrics/MetricsPanel";
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
    // Stated twice by design: the verdict line says it as a conclusion,
    // the list says it where the rows would be.
    expect((await view.findAllByText(/no requests recorded/i)).length).toBeGreaterThan(0);
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
    // exactly that reason, and is covered in `tests/util.test.ts` instead,
    // calling `errorMessage` as a plain function with something
    // `castError` never produces.
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue("offline"));
    const view = render(() => <MetricsPanel />);
    expect(await view.findByText(/couldn't load metrics: offline/i)).toBeTruthy();
  });

  // `errorMessage` itself is NOT re-tested here. It lives in
  // `~/utils/util.ts` and is covered by `tests/util.test.ts` — this
  // file's copy of it (and of those assertions) was a duplicate of
  // both, removed under #600.

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

  it("opens on the worst route without rewriting the URL", async () => {
    // A bare `#/metrics` should land on the thing that needs attention.
    // The default is DERIVED, not navigated to: reporting it through
    // `onNavigate` would rewrite the reader's address bar on first paint.
    const onNavigate = vi.fn();
    mockDrilldown({
      leaderboard: [row("fine", 900), { ...row("boom", 5), error_rate: 0.5 }],
      detailRows: [],
    });
    const view = render(() => <MetricsPanel onNavigate={onNavigate} />);
    await waitFor(() => expect(view.getByRole("heading", { level: 2 }).textContent).toBe("boom"));
    expect(onNavigate).not.toHaveBeenCalled();
  });

  it("falls back to the slowest route when nothing is failing", async () => {
    mockDrilldown({ leaderboard: [row("fast", 5), row("slow", 900)], detailRows: [] });
    const view = render(() => <MetricsPanel />);
    await waitFor(() => expect(view.getByRole("heading", { level: 2 }).textContent).toBe("slow"));
  });

  it("fetches a previous-window baseline alongside the current window", async () => {
    const fetchMock = mockDrilldown({ leaderboard: [row("slow", 900)], detailRows: [] });
    render(() => <MetricsPanel />);
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([input]) => urlOf(input).includes("offset=1"))).toBe(true),
    );
  });

  it("asks for no baseline on the all-time window, which has no previous one", async () => {
    // The endpoint answers a non-zero offset there with a 400, so the
    // request must not be made rather than made and swallowed.
    const fetchMock = mockDrilldown({ leaderboard: [row("slow", 900)], detailRows: [] });
    const view = render(() => <MetricsPanel window="all" />);
    await view.findAllByTestId("metrics-route-label");
    await Promise.resolve();
    expect(fetchMock.mock.calls.some(([input]) => urlOf(input).includes("offset=1"))).toBe(false);
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
    expect(view.getByText("Time to first event")).toBeTruthy();
    // Default view: the chart fetched the "total" series (p95 999, per
    // `mockDrilldown`'s kind-keyed response).
    await waitFor(() => expect(view.getByText("999", { exact: false })).toBeTruthy());

    fireEvent.click(view.getByText("Time to first event"));
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
    expect(view.queryByText("Time to first event")).toBeNull();
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

  it("puts the list and the detail side by side, with the verdict above both", async () => {
    // The reader's first question is "is anything wrong?", so the verdict
    // comes before either pane. The detail no longer sits ABOVE the list
    // pushing it off screen; the two are columns of one row. jsdom does
    // no layout, so assert the structure that produces it.
    mockDrilldown({ leaderboard: [row("chat", 900)], detailRows: [] });
    const view = render(() => <MetricsPanel />);
    await view.findAllByTestId("metrics-route-label");

    const panel = view.container.querySelector(".metrics-panel");
    const order = [...panel!.children].map((c) => c.className);
    expect(order.findIndex((c) => c.includes("metrics-head"))).toBeLessThan(
      order.findIndex((c) => c.includes("metrics-verdict")),
    );
    expect(order.findIndex((c) => c.includes("metrics-verdict"))).toBeLessThan(
      order.findIndex((c) => c.includes("metrics-split")),
    );

    const split = view.container.querySelector(".metrics-split");
    expect(split!.querySelector(".metrics-routes")).not.toBeNull();
    await waitFor(() => expect(split!.querySelector(".metrics-detail")).not.toBeNull());
  });

  it("marks the split as open only while a route is selected", async () => {
    // The mobile layout stacks the panes and swaps between them, and it
    // keys off this class rather than re-deriving the selection.
    mockDrilldown({ leaderboard: [row("slow", 900)], detailRows: [] });
    const view = render(() => <Host />);
    await view.findAllByTestId("metrics-route-label");
    await waitFor(() =>
      expect(view.container.querySelector(".metrics-split")!.classList).toContain("detail-open"),
    );
    fireEvent.click(await view.findByText(/all routes/i));
    await waitFor(() =>
      expect(view.container.querySelector(".metrics-split")!.classList).not.toContain(
        "detail-open",
      ),
    );
  });

  it("says a route has no sub-spans rather than showing an empty table", async () => {
    // Only three code paths are instrumented, so most routes have none -
    // `health` measured live with 0 sub-span rows. The old table rendered
    // a bare "Span Count p50 p95 p99" header labelling nothing, directly
    // above the route table's near-identical header.
    mockDrilldown({ leaderboard: [row("health", 5)], detailRows: [] });
    const view = render(() => <Host />);
    await view.findByText("← All routes");
    expect(await view.findByText(/no sub-spans recorded/i)).toBeTruthy();
    expect(view.container.querySelector(".metrics-subspan-table")).toBeNull();
  });

  it("states the window and total request count in the header", async () => {
    mockDrilldown({ leaderboard: [row("a", 10), row("b", 20)], detailRows: [] });
    const view = render(() => <MetricsPanel window="6h" />);
    // `row()` is 10 requests apiece.
    expect(await view.findByText(/last 6 hours · 20 requests/i)).toBeTruthy();
  });

  it("leads with a verdict naming the failing route", async () => {
    mockDrilldown({
      leaderboard: [{ ...row("work range", 9800), count: 47, error_rate: 9 / 47 }],
      detailRows: [],
    });
    const view = render(() => <MetricsPanel />);
    const verdict = await waitFor(() => {
      const el = view.container.querySelector(".metrics-verdict");
      expect(el).not.toBeNull();
      return el!;
    });
    expect(verdict.textContent).toContain("One route is failing.");
    expect(verdict.textContent).toContain("work range");
    expect(verdict.textContent).toContain("9 of 47");
  });

  it("switches the tiles as well as the chart on the time-to-first-event tab", async () => {
    // The first version relabelled only the chart and carried a "trend
    // chart only" note admitting it. The ttfe row has its own
    // percentiles, so the tiles follow now.
    mockDrilldown({
      leaderboard: [row("slow", 900), ttfeRow("slow", 700)],
      detailRows: [],
    });
    const view = render(() => <Host />);
    await view.findByText("Total");
    // Scoped to the tiles: 900 also appears in the route row's p95 cell,
    // which is the same number for a different reason.
    const tileText = () =>
      [...view.container.querySelectorAll(".metrics-tile-value")].map((e) => e.textContent);
    await waitFor(() => expect(tileText()).toContain("900ms"));
    fireEvent.click(view.getByText("Time to first event"));
    await waitFor(() => expect(tileText()).toContain("700ms"));
    expect(tileText()).not.toContain("900ms");
  });
});
