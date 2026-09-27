import { describe, expect, it } from "vitest";

// happy-dom's own fetch resolves `/api/...` against http://localhost:3000 and
// opens a socket. tests/setup.ts replaces it so an unmocked fetch fails at
// once, the way it did under jsdom, instead of reaching the network (#687).
describe("unmocked fetch in the default test environment", () => {
  it("rejects immediately, without a network attempt", async () => {
    await expect(fetch("/api/landing/stats")).rejects.toThrow(/unmocked fetch in a unit test/);
  });

  it("rejects on window.fetch too", async () => {
    await expect(window.fetch("/api/works")).rejects.toThrow(/unmocked fetch/);
  });
});
