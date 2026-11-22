// Tests for the apiError toast-stack helper.

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { flush } from "solid-js";
import {
  _resetToastsForTesting,
  apiError,
  dismissToast,
  useToasts,
  type ErrorToast,
} from "~/utils/apiError";
import { must } from "./helpers/must";

// Solid 2 applies signal writes on a microtask; these tests never yield, so
// each read goes through `stack()`, which flushes first.
const stack = (): ErrorToast[] => {
  flush();
  return useToasts()();
};

describe("apiError + useToasts", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    _resetToastsForTesting();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("pushes a toast that useToasts() sees", () => {
    apiError("Couldn't load works.");
    const s = stack();
    expect(s.length).toBe(1);
    expect(must(s[0]).message).toBe("Couldn't load works.");
  });

  it("assigns monotonically increasing ids", () => {
    const id1 = apiError("first");
    const id2 = apiError("second");
    expect(id2).toBeGreaterThan(id1);
  });

  it("auto-dismisses after the TTL", () => {
    apiError("transient failure");
    expect(stack().length).toBe(1);
    // The TTL is 6000ms; advance past it.
    vi.advanceTimersByTime(6000);
    expect(stack().length).toBe(0);
  });

  it("dismissToast removes a specific toast by id", () => {
    const id1 = apiError("first");
    apiError("second");
    expect(stack().length).toBe(2);
    dismissToast(id1);
    const s = stack();
    expect(s.length).toBe(1);
    expect(must(s[0]).message).toBe("second");
  });

  it("stacks multiple toasts in insertion order", () => {
    apiError("a");
    apiError("b");
    apiError("c");
    expect(stack().map((t) => t.message)).toEqual(["a", "b", "c"]);
  });
});
