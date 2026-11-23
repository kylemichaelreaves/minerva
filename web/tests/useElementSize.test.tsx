/**
 * `useElementSize` at the hook level (#585).
 *
 * A 0×0 client box is what every pre-layout paint, every `display:none`
 * ancestor and every headless render reports. It is not a size, and the
 * hook used to accept it anyway — overwriting its `initial` fallback, so
 * all four consumers (the trend chart and three Network panels) drew a
 * zero-width SVG. Their own suites could not see it: a fully collapsed
 * chart contains no `NaN`. So the contract is pinned here, where it lives.
 */
import { renderHook } from "@solidjs/testing-library";
import { flush } from "solid-js";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useElementSize } from "~/hooks/useElementSize";

/** An element whose client box the test sets, standing in for layout. */
function sizedEl(w: number, h: number) {
  const el = document.createElement("div");
  const box = { w, h };
  Object.defineProperty(el, "clientWidth", { configurable: true, get: () => box.w });
  Object.defineProperty(el, "clientHeight", { configurable: true, get: () => box.h });
  return {
    el,
    resize(nw: number, nh: number) {
      box.w = nw;
      box.h = nh;
    },
  };
}

/** Captures the observer callback so a test can fire a resize tick. */
let observerCallback: () => void = () => undefined;
/** Fire a resize tick, then flush: in Solid 2 the size signal's write is only
 *  visible to a read once the scheduler has applied it. */
const fireResize = (): void => {
  observerCallback();
  flush();
};
let observers = 0;
const disconnect = vi.fn();

beforeEach(() => {
  observers = 0;
  disconnect.mockClear();
  vi.stubGlobal(
    "ResizeObserver",
    class {
      constructor(cb: () => void) {
        observers += 1;
        observerCallback = cb;
      }
      observe() {
        /* the test drives ticks through fireResize */
      }
      disconnect = disconnect;
    },
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const INITIAL = { w: 700, h: 280 };

describe("useElementSize", () => {
  it("keeps the fallback when the element measures 0×0 at mount", () => {
    const { el } = sizedEl(0, 0);
    const { result } = renderHook(() => useElementSize(() => el, INITIAL));
    expect(result()).toEqual(INITIAL);
  });

  it("takes the element's size when it has been laid out", () => {
    const { el } = sizedEl(640, 220);
    const { result } = renderHook(() => useElementSize(() => el, INITIAL));
    expect(result()).toEqual({ w: 640, h: 220 });
  });

  it("treats a box with only one zero dimension as unmeasured too", () => {
    const wide = sizedEl(640, 0);
    const tall = sizedEl(0, 220);
    expect(renderHook(() => useElementSize(() => wide.el, INITIAL)).result()).toEqual(INITIAL);
    expect(renderHook(() => useElementSize(() => tall.el, INITIAL)).result()).toEqual(INITIAL);
  });

  it("follows resize ticks, and keeps the last good size when one reports 0×0", () => {
    const box = sizedEl(640, 220);
    const { result } = renderHook(() => useElementSize(() => box.el, INITIAL));

    box.resize(900, 300);
    fireResize();
    expect(result()).toEqual({ w: 900, h: 300 });

    // Collapsed under a display:none ancestor: not a new size.
    box.resize(0, 0);
    fireResize();
    expect(result()).toEqual({ w: 900, h: 300 });
  });

  it("stays on the fallback until the first real measurement arrives", () => {
    const box = sizedEl(0, 0);
    const { result } = renderHook(() => useElementSize(() => box.el, INITIAL));
    fireResize();
    expect(result()).toEqual(INITIAL);

    box.resize(512, 200);
    fireResize();
    expect(result()).toEqual({ w: 512, h: 200 });
  });

  it("ignores a tick that arrives after the element is gone", () => {
    const box = sizedEl(640, 220);
    let current: HTMLElement | undefined = box.el;
    const { result } = renderHook(() => useElementSize(() => current, INITIAL));
    current = undefined;
    fireResize();
    expect(result()).toEqual({ w: 640, h: 220 });
  });

  it("returns the fallback, and observes nothing, with no element to measure", () => {
    const { result } = renderHook(() => useElementSize(() => undefined, INITIAL));
    expect(result()).toEqual(INITIAL);
    expect(observers).toBe(0);
  });

  it("disconnects its observer when the owner is disposed", () => {
    const { el } = sizedEl(640, 220);
    const { cleanup } = renderHook(() => useElementSize(() => el, INITIAL));
    cleanup();
    expect(disconnect).toHaveBeenCalledTimes(1);
  });
});
