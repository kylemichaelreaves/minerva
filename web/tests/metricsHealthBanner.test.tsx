/** The degraded banner: three states that used to render identically.
 *
 *  `persisting: false` and `write_failures > 0` both produced an ordinary,
 *  slightly empty page. The distinction the design draws: when not recording,
 *  the count is RIGHT and FROZEN; when writes are failing, the count is WRONG
 *  and still MOVING. Silently reading an undercount is worse than reading a
 *  stale number that says it is stale.
 */
import { render, screen } from "@solidjs/testing-library";
import { describe, expect, it, vi } from "vitest";
import { MetricsHealthBanner } from "../src/Metrics/MetricsHealthBanner";

describe("MetricsHealthBanner", () => {
  it("renders nothing when metrics are healthy", () => {
    const { container } = render(() => (
      <MetricsHealthBanner health={{ write_failures: 0, persisting: true }} />
    ));
    expect(container.textContent).toBe("");
  });

  it("says nothing is being recorded when persistence is off", () => {
    render(() => <MetricsHealthBanner health={{ write_failures: 0, persisting: false }} />);
    const banner = screen.getByRole("status", { name: "Metrics health" });
    expect(banner.textContent).toContain("Nothing is being recorded");
    // The actionable part: the numbers below are not going to move.
    expect(banner.textContent).toMatch(/frozen/i);
  });

  it("says counts are an undercount when writes are failing", () => {
    render(() => <MetricsHealthBanner health={{ write_failures: 147, persisting: true }} />);
    const banner = screen.getByRole("status", { name: "Metrics health" });
    expect(banner.textContent).toContain("147");
    expect(banner.textContent).toMatch(/undercount/i);
  });

  it("distinguishes the two degraded states from each other", () => {
    const { container: off } = render(() => (
      <MetricsHealthBanner health={{ write_failures: 0, persisting: false }} />
    ));
    const { container: failing } = render(() => (
      <MetricsHealthBanner health={{ write_failures: 147, persisting: true }} />
    ));
    expect(off.textContent).not.toBe(failing.textContent);
  });

  it("treats a failing write as degraded even while persisting is true", () => {
    // The trap: `persisting` only says a connection exists. It says nothing
    // about whether writes through it are landing.
    render(() => <MetricsHealthBanner health={{ write_failures: 3, persisting: true }} />);
    expect(screen.getByRole("status", { name: "Metrics health" })).toBeTruthy();
  });

  it("tolerates a missing health block from an older server", () => {
    const { container } = render(() => <MetricsHealthBanner health={undefined} />);
    expect(container.textContent).toBe("");
  });
});

describe("MetricsHealthBanner inside MetricsPanel", () => {
  it("does not take down the error path when the summary fetch rejects", async () => {
    // Reading an errored Solid resource re-throws. Rendering the banner from
    // `summary()?.health` without guarding on `summary.error` therefore breaks
    // the one path where the page most needs to still render something.
    const { MetricsPanel } = await import("../src/Metrics/MetricsPanel");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));
    const view = render(() => <MetricsPanel />);
    expect(await view.findByText(/couldn't load/i, {}, { timeout: 3000 })).toBeTruthy();
    vi.unstubAllGlobals();
  });
});
