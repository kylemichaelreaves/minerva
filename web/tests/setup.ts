import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@solidjs/testing-library";

// jsdom doesn't implement window.matchMedia. The `useMobile` hook
// reads it at module load time (to seed its initial signal), so any
// component that imports a module touching useMobile crashes without
// this shim. Default to "desktop" (matches === false) — components
// can re-mock per test if they need to assert mobile behavior.
// In jsdom, `window.matchMedia` is missing; in node without jsdom,
// `window` itself is. Guard for both — TS's lib.dom types claim both
// always exist, so the rule fires here but the check is real.
// eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
if (typeof window !== "undefined" && !window.matchMedia) {
  window.matchMedia = (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => undefined, // legacy API some libs still use
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  });
}

// jsdom lacks ResizeObserver; Network ArcPanel observes wrap size.
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

// Solid testing library doesn't auto-cleanup like RTL does in some setups;
// belt-and-braces.
afterEach(() => {
  cleanup();
});

// Solid's createResource emits fetcher rejections to the global
// unhandledRejection channel even when the consumer reads `.error`
// properly. In components like ConcordanceTabPanel where the network
// call is fire-and-forget (the UI just shows an empty/error state),
// the rejection escapes the test runner and vitest flags it. Swallow
// rejections that look like our own apiGet errors. Real assertion
// failures still surface — they don't go through this channel.
if (typeof process !== "undefined") {
  process.on("unhandledRejection", (reason) => {
    const msg = reason instanceof Error ? reason.message : String(reason);
    if (
      msg.startsWith("fetch returned no response for ") ||
      /^\d{3}\b/.test(msg)
    ) {
      // Expected: a test didn't mock a parallel-mount API call.
      // The component already shows the error state; consume here.
      return;
    }
    throw reason instanceof Error ? reason : new Error(msg);
  });
}
