// Tests for the apiError toast-stack helper.

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import {
  _resetToastsForTesting,
  apiError,
  dismissToast,
  useToasts,
} from "~/utils/apiError";

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
    const stack = useToasts()();
    expect(stack.length).toBe(1);
    expect(stack[0].message).toBe("Couldn't load works.");
  });

  it("assigns monotonically increasing ids", () => {
    const id1 = apiError("first");
    const id2 = apiError("second");
    expect(id2).toBeGreaterThan(id1);
  });

  it("auto-dismisses after the TTL", () => {
    apiError("transient failure");
    expect(useToasts()().length).toBe(1);
    // The TTL is 6000ms; advance past it.
    vi.advanceTimersByTime(6000);
    expect(useToasts()().length).toBe(0);
  });

  it("dismissToast removes a specific toast by id", () => {
    const id1 = apiError("first");
    apiError("second");
    expect(useToasts()().length).toBe(2);
    dismissToast(id1);
    const stack = useToasts()();
    expect(stack.length).toBe(1);
    expect(stack[0].message).toBe("second");
  });

  it("stacks multiple toasts in insertion order", () => {
    apiError("a");
    apiError("b");
    apiError("c");
    expect(useToasts()().map((t) => t.message)).toEqual(["a", "b", "c"]);
  });
});
