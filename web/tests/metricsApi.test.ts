import { describe, expect, it, vi, afterEach } from "vitest";
import {
  METRIC_WINDOWS,
  fetchMetricsSeries,
  fetchMetricsSummary,
} from "~/api/metricsApi";

function mockFetch(body: unknown) {
  const spy = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: () => Promise.resolve(body),
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

afterEach(() => vi.unstubAllGlobals());

describe("metricsApi", () => {
  it("exposes the windows the backend accepts", () => {
    expect(METRIC_WINDOWS).toEqual(["1h", "6h", "24h", "7d", "30d", "all"]);
  });

  it("requests the summary for a window", async () => {
    const spy = mockFetch({ window: "24h", since: 0, until: 1, rows: [] });
    await fetchMetricsSummary("24h");
    expect(spy.mock.calls[0]?.[0]).toContain("/api/metrics/summary");
    expect(spy.mock.calls[0]?.[0]).toContain("window=24h");
  });

  it("passes a label through to the sub-span drill-down", async () => {
    const spy = mockFetch({ window: "24h", since: 0, until: 1, rows: [] });
    await fetchMetricsSummary("24h", "chunk syntax");
    expect(spy.mock.calls[0]?.[0]).toContain("label=chunk+syntax");
  });

  it("requests a series with kind and span", async () => {
    const spy = mockFetch({
      label: "chat", kind: "ttfe", span: "", bucket_seconds: 300, points: [],
    });
    const got = await fetchMetricsSeries("chat", { window: "7d", kind: "ttfe" });
    expect(spy.mock.calls[0]?.[0]).toContain("kind=ttfe");
    expect(got.bucket_seconds).toBe(300);
  });
});
