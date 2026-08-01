import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  TOKEN_GAP,
  clearMeasureCache,
  fontKey,
  layoutRow,
  measureTokens,
} from "~/Syntax/layout/measure";

// Arc endpoints are token centres, so every x-position depends on a measured
// glyph advance. Estimating from character counts — which is what the rest of
// this codebase does (`CHAR_ADVANCE = 0.55`) — is not good enough here:
// German diacritics and polytonic Greek measure unpredictably, and an arc that
// lands a few pixels off its token reads as a bug.
//
// The other half of the contract is *when* we measure. Measuring before
// webfonts resolve gives fallback metrics, so arcs land wrong on first paint
// and then visibly snap. That is worse than a beat of delay.

const FONT = { family: "Gentium Plus, serif", size: 20 };

// `getComputedTextLength` lives on SVGTextContentElement in lib.dom, but jsdom
// implements no SVG text metrics at all — tests/setup.ts patches it onto
// SVGElement.prototype, which is what the measuring probe actually reaches
// through the prototype chain. Spy on the object that really carries it.
const textMetrics = SVGElement.prototype as unknown as { getComputedTextLength: () => number };

beforeEach(() => {
  clearMeasureCache();
});

describe("measureTokens", () => {
  it("returns a width for every token", async () => {
    const widths = await measureTokens(["Der", "Geist", "entwickelt"], FONT);

    expect([...widths.keys()]).toEqual(["Der", "Geist", "entwickelt"]);
    for (const w of widths.values()) expect(w).toBeGreaterThan(0);
  });

  it("waits for fonts to resolve before measuring", async () => {
    let resolveFonts = (): void => undefined;
    const gate = new Promise<void>((r) => {
      resolveFonts = r;
    });
    const original = document.fonts;
    Object.defineProperty(document, "fonts", {
      value: { ready: gate },
      writable: true,
      configurable: true,
    });
    const measured = vi.spyOn(textMetrics, "getComputedTextLength");

    try {
      const pending = measureTokens(["Geist"], FONT);
      await Promise.resolve();

      expect(measured).not.toHaveBeenCalled();

      resolveFonts();
      await pending;

      expect(measured).toHaveBeenCalled();
    } finally {
      measured.mockRestore();
      Object.defineProperty(document, "fonts", {
        value: original,
        writable: true,
        configurable: true,
      });
    }
  });

  it("measures each distinct string once", async () => {
    const measured = vi.spyOn(textMetrics, "getComputedTextLength");

    try {
      await measureTokens(["der", "Geist", "der"], FONT);
      const firstPass = measured.mock.calls.length;
      await measureTokens(["der", "Geist"], FONT);

      // "der" appears twice in one call and again in the next; two distinct
      // strings means two measurements, and no more.
      expect(firstPass).toBe(2);
      expect(measured.mock.calls.length).toBe(2);
    } finally {
      measured.mockRestore();
    }
  });

  it("re-measures the same string under a different font", async () => {
    const measured = vi.spyOn(textMetrics, "getComputedTextLength");

    try {
      await measureTokens(["Geist"], FONT);
      await measureTokens(["Geist"], { ...FONT, size: 32 });

      expect(measured.mock.calls.length).toBe(2);
    } finally {
      measured.mockRestore();
    }
  });

  it("leaves no measuring element in the document", async () => {
    await measureTokens(["Geist"], FONT);

    expect(document.querySelectorAll("svg").length).toBe(0);
  });
});

describe("fontKey", () => {
  it("distinguishes size, family and weight", () => {
    expect(fontKey(FONT)).not.toBe(fontKey({ ...FONT, size: 21 }));
    expect(fontKey(FONT)).not.toBe(fontKey({ ...FONT, family: "serif" }));
    expect(fontKey(FONT)).not.toBe(fontKey({ ...FONT, weight: 600 }));
  });

  it("is stable for the same spec", () => {
    expect(fontKey({ family: "a", size: 1 })).toBe(fontKey({ family: "a", size: 1 }));
  });
});

describe("layoutRow", () => {
  it("puts a fixed gap between boxes and centres each one", () => {
    const boxes = layoutRow([30, 50, 20], 0);

    expect(boxes[0]).toEqual({ left: 0, width: 30, centre: 15 });
    expect(boxes[1]).toEqual({ left: 30 + TOKEN_GAP, width: 50, centre: 30 + TOKEN_GAP + 25 });
    expect(boxes[2]?.left).toBe(30 + TOKEN_GAP + 50 + TOKEN_GAP);
  });

  it("honours a starting offset", () => {
    const boxes = layoutRow([10], 40);

    expect(boxes[0]).toEqual({ left: 40, width: 10, centre: 45 });
  });

  it("ends at the last box, with no trailing gap", () => {
    const boxes = layoutRow([10, 10], 0);
    const last = boxes[boxes.length - 1];

    expect(last && last.left + last.width).toBe(20 + TOKEN_GAP);
  });
});
