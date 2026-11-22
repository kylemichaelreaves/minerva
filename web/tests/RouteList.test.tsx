import { fireEvent, render } from "@solidjs/testing-library";
import { flush } from "solid-js";
import { describe, expect, it, vi } from "vitest";
import type { MetricsSummaryRow } from "~/api/metricsApi";
import type { RouteEntry } from "~/Metrics/severity";
import { RouteList, sortEntries } from "~/Metrics/RouteList";

const row = (over: Partial<MetricsSummaryRow> = {}): MetricsSummaryRow => ({
  label: "works list",
  method: "GET",
  kind: "total",
  span: "",
  count: 65,
  mean_ms: 30,
  min_ms: 1,
  max_ms: 300,
  p50_ms: 12,
  p95_ms: 142,
  p99_ms: 310,
  error_rate: 0,
  ...over,
});

const entry = (over: Partial<MetricsSummaryRow>, severity: RouteEntry["severity"]): RouteEntry => ({
  row: row(over),
  severity,
});

const labels = (es: RouteEntry[]): string[] => es.map((e) => e.row.label);

describe("sortEntries", () => {
  const es = [
    entry({ label: "c", p95_ms: 100, count: 9 }, "ok"),
    entry({ label: "a", p95_ms: 900, count: 1 }, "bad"),
    entry({ label: "b", p95_ms: 500, count: 50 }, "warn"),
  ];

  it("orders bad before warn before ok", () => {
    expect(labels(sortEntries(es, "severity"))).toEqual(["a", "b", "c"]);
  });

  it("breaks a severity tie on p95, slowest first", () => {
    const tied = [
      entry({ label: "slow", p95_ms: 900 }, "ok"),
      entry({ label: "slower", p95_ms: 950 }, "ok"),
    ];
    expect(labels(sortEntries(tied, "severity"))).toEqual(["slower", "slow"]);
  });

  it("orders by p95 regardless of severity", () => {
    expect(labels(sortEntries(es, "p95"))).toEqual(["a", "b", "c"]);
  });

  it("orders by count, busiest first", () => {
    expect(labels(sortEntries(es, "count"))).toEqual(["b", "c", "a"]);
  });

  it("orders by name", () => {
    expect(labels(sortEntries(es, "name"))).toEqual(["a", "b", "c"]);
  });

  it("does not mutate the input", () => {
    const original = [...es];
    sortEntries(es, "name");
    expect(es).toEqual(original);
  });
});

describe("RouteList", () => {
  const mixed = [
    entry({ label: "work range", p95_ms: 9800, error_rate: 9 / 47, count: 47 }, "bad"),
    entry({ label: "chat message", p95_ms: 4320, method: "POST" }, "warn"),
    entry({ label: "works list", p95_ms: 142 }, "ok"),
  ];

  it("groups by severity under the severity sort", () => {
    const view = render(() => <RouteList entries={mixed} loading={false} onSelect={vi.fn()} />);
    expect(view.getByText(/needs a look/i)).toBeTruthy();
    expect(view.getByText(/inside usual range/i)).toBeTruthy();
  });

  it("drops the group headings under any other sort", () => {
    // Grouping by severity while ordering by name would show a reader
    // two different organising principles at once.
    const view = render(() => <RouteList entries={mixed} loading={false} onSelect={vi.fn()} />);
    fireEvent.change(view.getByLabelText(/sort routes/i), { target: { value: "name" } });
    flush();
    expect(view.queryByText(/needs a look/i)).toBeNull();
  });

  it("shows the method and error rate on a row", () => {
    const view = render(() => <RouteList entries={mixed} loading={false} onSelect={vi.fn()} />);
    expect(view.getByText("POST")).toBeTruthy();
    expect(view.getByText("19.1%")).toBeTruthy();
  });

  it("shows an em dash rather than 0.0% for a clean route", () => {
    const view = render(() => (
      <RouteList
        entries={[entry({ label: "works list" }, "ok")]}
        loading={false}
        onSelect={vi.fn()}
      />
    ));
    expect(view.getByText("—")).toBeTruthy();
  });

  it("scales each bar against the slowest route in the list", () => {
    const view = render(() => <RouteList entries={mixed} loading={false} onSelect={vi.fn()} />);
    const bars = view.container.querySelectorAll<HTMLElement>(".metrics-row-bar i");
    expect(bars[0]?.style.width).toBe("100%");
  });

  it("gives a barely-measurable route a visible sliver", () => {
    // 1/9800 rounds to 0%, which renders as no bar at all and reads as
    // missing data rather than as a fast route.
    const view = render(() => (
      <RouteList
        entries={[
          entry({ label: "a", p95_ms: 9800 }, "bad"),
          entry({ label: "b", p95_ms: 1 }, "ok"),
        ]}
        loading={false}
        onSelect={vi.fn()}
      />
    ));
    const bars = view.container.querySelectorAll<HTMLElement>(".metrics-row-bar i");
    expect(bars[1]?.style.width).toBe("2%");
  });

  it("reports the selected route to its caller", () => {
    const onSelect = vi.fn();
    const view = render(() => <RouteList entries={mixed} loading={false} onSelect={onSelect} />);
    fireEvent.click(view.getByText("works list"));
    flush();
    expect(onSelect).toHaveBeenCalledWith("works list");
  });

  it("marks the selected row for assistive technology", () => {
    const view = render(() => (
      <RouteList entries={mixed} loading={false} selectedLabel="chat message" onSelect={vi.fn()} />
    ));
    const pressed = view.container.querySelectorAll('[aria-pressed="true"]');
    expect(pressed).toHaveLength(1);
    expect(pressed[0]?.textContent).toContain("chat message");
  });

  it("counts the routes it is showing", () => {
    const view = render(() => <RouteList entries={mixed} loading={false} onSelect={vi.fn()} />);
    expect(view.getByText("3 routes")).toBeTruthy();
  });

  it("says one route in the singular", () => {
    const view = render(() => (
      <RouteList entries={[entry({}, "ok")]} loading={false} onSelect={vi.fn()} />
    ));
    expect(view.getByText("1 route")).toBeTruthy();
  });

  it("reports a failed fetch instead of an empty list", () => {
    const view = render(() => (
      <RouteList entries={[]} loading={false} errorText="network down" onSelect={vi.fn()} />
    ));
    expect(view.getByRole("alert").textContent).toContain("network down");
  });

  it("says the window is empty when it is", () => {
    const view = render(() => <RouteList entries={[]} loading={false} onSelect={vi.fn()} />);
    expect(view.getByRole("status").textContent).toMatch(/no requests recorded/i);
  });

  // Carries forward #595's "names the route table so it is addressable by
  // role (#593)". #600 replaced that table with this list, so the
  // assertion moves here rather than disappearing with the markup it
  // named — the browser suite's tier-1 locator
  // (`MetricsPage.routeList`) resolves through exactly this name.
  it("names the route list so it is addressable by role (#593)", () => {
    const view = render(() => (
      <RouteList entries={[entry({ label: "fast" }, "ok")]} loading={false} onSelect={vi.fn()} />
    ));
    expect(view.getByRole("group", { name: "Routes" })).toBeTruthy();
  });

  it("shows a loading state rather than an empty window mid-fetch", () => {
    const view = render(() => <RouteList entries={[]} loading={true} onSelect={vi.fn()} />);
    expect(view.queryByRole("status")).toBeNull();
    expect(view.getByText(/loading/i)).toBeTruthy();
  });
});
