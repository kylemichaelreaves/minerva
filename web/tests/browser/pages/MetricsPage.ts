import type { Locator, Page } from "@playwright/test";

export class MetricsPage {
  constructor(private readonly page: Page) {}

  async goto(): Promise<void> {
    await this.page.goto("/#/metrics");
    await this.table.waitFor();
  }

  get table(): Locator {
    return this.page.getByRole("table", { name: "Requests by route" });
  }

  /** The chart's own name, from TimeSeriesChart.tsx:148-149. */
  get chart(): Locator {
    return this.page.getByRole("img", { name: /Latency over time/ });
  }

  /** A row identified by the route it reports, via the one pre-existing
   *  data-testid in the codebase (MetricsPanel.tsx:357). Tier 1 cannot
   *  distinguish rows: a row's accessible name concatenates every cell,
   *  including counts that change between runs. */
  routeRow(label: string): Locator {
    return this.table.getByRole("row").filter({
      has: this.page
        .getByTestId("metrics-route-label")
        .and(this.page.getByText(label, { exact: true })),
    });
  }

  async selectRoute(label: string): Promise<void> {
    await this.routeRow(label).click();
  }

  /** The first route label the server actually reported. Derived, because
   *  which routes appear depends on what the suite happened to request. */
  async firstRouteLabel(): Promise<string> {
    const cell = this.page.getByTestId("metrics-route-label").first();
    const text = (await cell.textContent())?.trim();
    if (!text) {
      throw new Error(
        "no route rows rendered — the server recorded no requests. Not " +
          "skipping: the suite has already driven the API by this point.",
      );
    }
    return text;
  }
}
