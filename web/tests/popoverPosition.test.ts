import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { computePopoverPosition } from "~/utils/popoverPosition";

describe("computePopoverPosition", () => {
  const innerHeight = 800;
  const innerWidth = 1200;

  beforeEach(() => {
    Object.defineProperty(window, "innerHeight", {
      value: innerHeight,
      configurable: true,
    });
    Object.defineProperty(window, "innerWidth", {
      value: innerWidth,
      configurable: true,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("places card below anchor when there is room", () => {
    const anchor = new DOMRect(100, 100, 20, 16);
    const pos = computePopoverPosition(anchor);
    expect(pos.flipUp).toBe(false);
    expect(pos.top).toBe(anchor.bottom + 10);
    expect(pos.left).toBe(100);
  });

  it("flips up when bottom would overflow", () => {
    const anchor = new DOMRect(100, 700, 20, 16);
    const pos = computePopoverPosition(anchor);
    expect(pos.flipUp).toBe(true);
    expect(pos.top).toBeLessThan(anchor.top);
  });
});
