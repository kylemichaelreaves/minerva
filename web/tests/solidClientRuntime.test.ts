// @vitest-environment node
// Guards #861. vite-plugin-solid 2.11.15 decides whether to give the `ssr`
// environment the `browser` resolve condition from the *global*
// `test.environment` (happy-dom here), not from each file's docblock. Files
// that opt into `@vitest-environment node` run in that `ssr` environment, so
// without `browser` they load solid-js's server build — where `isServer` is
// true and `createEffect` never runs. Every hook test in this directory that
// asserts on an effect then fails with "Number of calls: 0". vite.config.ts
// puts the condition back; this file fails first if that stops working.

import { describe, it, expect } from "vitest";
import { createEffect, createRoot, createSignal } from "solid-js";
import { isServer } from "solid-js/web";

describe("solid-js under a per-file node environment", () => {
  it("resolves the client build, not the server build", () => {
    expect(isServer).toBe(false);
  });

  it("runs effects and re-runs them when a signal changes", async () => {
    const seen: number[] = [];
    const [n, setN] = createSignal(1);
    const dispose = createRoot((d) => {
      createEffect(() => seen.push(n()));
      return d;
    });
    await Promise.resolve();
    setN(2);
    await Promise.resolve();
    dispose();
    expect(seen).toEqual([1, 2]);
  });
});
