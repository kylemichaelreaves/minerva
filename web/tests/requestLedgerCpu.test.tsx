/** Wall vs CPU in the ledger detail.
 *
 *  The ratio labels are the design's, from `obs-render.js`:
 *      cpu/wall > 0.6  -> cpu-bound
 *      cpu/wall < 0.1  -> waiting
 *      otherwise       -> mixed
 *
 *  The case that matters most is the one that looks like nothing: `cpu_ms`
 *  absent means NOT MEASURED, and must not render as "0ms, waiting" — that
 *  would state a measurement nobody took.
 */
import { render, screen, fireEvent } from "@solidjs/testing-library";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RequestLedger } from "../src/Metrics/RequestLedger";

const base = {
  id: "a1b2c3d4e5f60718",
  at: 1_700_000_000,
  label: "chat",
  method: "POST",
  status: 200,
  total_ms: 1000,
  accounted_ms: 0,
  unaccounted_ms: 1000,
  phases: [] as { name: string; ms: number; cpu_ms?: number }[],
  cpu_ms: null as number | null,
  sqlite_ms: null as number | null,
  sqlite_queries: null as number | null,
};

function stub(row: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ window: "24h", since: 0, until: 1, rows: [row], limit: 200 }),
    }),
  );
}

async function openDetail(row: Record<string, unknown>) {
  stub(row);
  render(() => <RequestLedger window="24h" />);
  fireEvent.click(await screen.findByText("chat"));
  return screen.findByRole("region", { name: "Request detail" });
}

afterEach(() => vi.unstubAllGlobals());

describe("RequestLedger CPU", () => {
  it("calls a request that spent its time waiting 'waiting'", async () => {
    const d = await openDetail({ ...base, cpu_ms: 20 }); // 20/1000 = 2%
    expect(d.textContent).toMatch(/waiting/i);
  });

  it("calls a request that spent its time computing 'cpu-bound'", async () => {
    const d = await openDetail({ ...base, cpu_ms: 940 });
    expect(d.textContent).toMatch(/cpu-bound/i);
  });

  it("calls the middle 'mixed'", async () => {
    const d = await openDetail({ ...base, cpu_ms: 300 });
    expect(d.textContent).toMatch(/mixed/i);
  });

  it("says NOT MEASURED rather than showing a zero when cpu is null", async () => {
    const d = await openDetail({ ...base, cpu_ms: null });
    expect(d.textContent).toMatch(/not measured/i);
    expect(d.textContent).not.toMatch(/waiting/i);
  });

  it("distinguishes a measured idle request from an unmeasured one", async () => {
    const idle = await openDetail({ ...base, cpu_ms: 0 });
    expect(idle.textContent).toMatch(/waiting/i);
    expect(idle.textContent).not.toMatch(/not measured/i);
  });

  it("shows cpu beside wall for a phase that has it", async () => {
    const d = await openDetail({
      ...base,
      accounted_ms: 800,
      unaccounted_ms: 200,
      phases: [{ name: "stanza_parse", ms: 800, cpu_ms: 780 }],
    });
    expect(d.textContent).toContain("stanza_parse");
    expect(d.textContent).toMatch(/780/);
  });

  it("omits the cpu column for a phase written before it was measured", async () => {
    const d = await openDetail({
      ...base,
      accounted_ms: 800,
      unaccounted_ms: 200,
      phases: [{ name: "llm_call", ms: 800 }],
    });
    expect(d.textContent).toContain("llm_call");
    expect(d.textContent).not.toMatch(/cpu-bound|waiting/i);
  });
});

describe("RequestLedger database time", () => {
  it("shows sqlite time and the statement count", async () => {
    const d = await openDetail({
      ...base,
      total_ms: 241.3,
      sqlite_ms: 240.5,
      sqlite_queries: 2,
    });
    expect(d.textContent).toContain("sqlite");
    expect(d.textContent).toMatch(/2 q/);
  });

  it("says not measured for a row written before phase 3", async () => {
    // `null`, not 0. A route that touches no database and a row from before
    // the measurement existed must not look identical.
    const d = await openDetail({ ...base, sqlite_ms: null, sqlite_queries: null });
    expect(d.textContent).not.toMatch(/\bsqlite\b/);
  });

  it("renders a genuinely zero-query request as measured, not absent", async () => {
    const d = await openDetail({ ...base, sqlite_ms: 0, sqlite_queries: 0 });
    expect(d.textContent).toContain("sqlite");
    expect(d.textContent).toMatch(/0 q/);
  });
});
