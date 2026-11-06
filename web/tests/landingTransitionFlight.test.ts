import { describe, it, expect, vi, afterEach } from "vitest";
import {
  composerKeyframes,
  ghostKeyframes,
  measureOrigin,
  measureTarget,
  type FlightOrigin,
  type FlightTarget,
} from "~/features/LandingTransition/flight";

// jsdom has no layout: every rect and computed value below is stubbed, so
// these tests pin the arithmetic, not the browser.

function stubRect(el: Element, r: { top: number; left: number; width: number; height: number }) {
  vi.spyOn(el, "getBoundingClientRect").mockReturnValue({
    ...r,
    x: r.left,
    y: r.top,
    right: r.left + r.width,
    bottom: r.top + r.height,
    toJSON: () => r,
  });
}

function stubStyle(map: Map<Element, Record<string, string>>) {
  const real = window.getComputedStyle.bind(window);
  vi.spyOn(window, "getComputedStyle").mockImplementation((el: Element) => {
    const own = map.get(el);
    if (!own) return real(el);
    return new Proxy({} as CSSStyleDeclaration, {
      get: (_t, prop: string) => own[prop] ?? "0px",
    });
  });
}

const ORIGIN: FlightOrigin = {
  text: "Why?",
  textTop: 260,
  textLeft: 200,
  textWidth: 648,
  style: {
    fontSize: "17px",
    lineHeight: "24.65px",
    color: "rgb(26, 23, 20)",
    fontStyle: "italic",
  },
  box: { top: 304, left: 300, width: 680, height: 88 },
};

const TARGET: FlightTarget = {
  body: { top: 118, left: 280, width: 880, height: 28 },
  composer: { top: 688, left: 280, width: 880, height: 96 },
  style: {
    fontSize: "18px",
    lineHeight: "27.9px",
    color: "rgb(59, 53, 48)",
    fontStyle: "italic",
    backgroundColor: "rgba(0, 0, 0, 0)",
    borderTopColor: "rgb(59, 53, 48)",
    borderRightColor: "rgb(59, 53, 48)",
    borderBottomColor: "rgb(59, 53, 48)",
    borderLeftColor: "rgb(26, 23, 20)",
    fontFamily: "\"EB Garamond\", serif",
    fontWeight: "400",
    letterSpacing: "normal",
    whiteSpace: "normal",
    overflowWrap: "normal",
    wordBreak: "normal",
    paddingTop: "0px",
    paddingRight: "0px",
    paddingBottom: "0px",
    paddingLeft: "18px",
    borderTopWidth: "0px",
    borderRightWidth: "0px",
    borderBottomWidth: "0px",
    borderLeftWidth: "2px",
    borderTopStyle: "none",
    borderRightStyle: "none",
    borderBottomStyle: "none",
    borderLeftStyle: "solid",
  },
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("measureOrigin", () => {
  it("offsets the text origin by the textarea's scroll, so a long question flies whole", () => {
    const ta = document.createElement("textarea");
    ta.value = "  Why?  ";
    const box = document.createElement("div");
    stubRect(ta, { top: 300, left: 200, width: 648, height: 26 });
    stubRect(box, { top: 288, left: 184, width: 680, height: 88 });
    Object.defineProperty(ta, "scrollTop", { value: 40 });
    Object.defineProperty(ta, "clientWidth", { value: 648 });
    stubStyle(
      new Map([
        [ta, { fontSize: "17px", lineHeight: "24.65px", color: "rgb(26, 23, 20)", fontStyle: "italic" }],
      ]),
    );

    const o = measureOrigin(ta, box);

    expect(o.textTop).toBe(260);
    expect(o.textLeft).toBe(200);
    expect(o.textWidth).toBe(648);
    expect(o.text).toBe("Why?");
    expect(o.style.fontSize).toBe("17px");
    expect(o.box).toEqual({ top: 288, left: 184, width: 680, height: 88 });
  });

  it("counts the textarea's padding and border into the text origin", () => {
    const ta = document.createElement("textarea");
    ta.value = "Q";
    const box = document.createElement("div");
    stubRect(ta, { top: 100, left: 50, width: 400, height: 30 });
    stubRect(box, { top: 90, left: 40, width: 420, height: 60 });
    Object.defineProperty(ta, "clientWidth", { value: 398 });
    stubStyle(
      new Map([
        [ta, { paddingTop: "4px", paddingLeft: "6px", paddingRight: "8px", borderTopWidth: "1px", borderLeftWidth: "1px" }],
      ]),
    );

    const o = measureOrigin(ta, box);

    expect(o.textTop).toBe(105);
    expect(o.textLeft).toBe(57);
    expect(o.textWidth).toBe(384);
  });
});

describe("measureTarget", () => {
  it("reads the landed body's box and its full frame + chrome style", () => {
    const body = document.createElement("div");
    const composer = document.createElement("div");
    stubRect(body, TARGET.body);
    stubRect(composer, TARGET.composer);
    stubStyle(new Map([[body, TARGET.style]]));

    const t = measureTarget(body, composer);

    expect(t.body).toEqual(TARGET.body);
    expect(t.composer).toEqual(TARGET.composer);
    expect(t.style.borderLeftWidth).toBe("2px");
    expect(t.style.paddingLeft).toBe("18px");
    expect(t.style.fontSize).toBe("18px");
  });
});

describe("ghostKeyframes", () => {
  it("starts with the text exactly on the textarea's text and ends on the body", () => {
    const { move } = ghostKeyframes(ORIGIN, TARGET);

    // Outer box pushed out by the target's 18px padding + 2px rule.
    expect(move).toMatchObject([
      { left: "180px", top: "260px", width: "668px", fontSize: "17px", color: "rgb(26, 23, 20)" },
      { left: "280px", top: "118px", width: "880px", fontSize: "18px", color: "rgb(59, 53, 48)" },
    ]);
  });

  it("draws the user-turn chrome in from transparent", () => {
    const { chrome } = ghostKeyframes(ORIGIN, TARGET);

    expect(chrome).toMatchObject([
      { borderLeftColor: "transparent", backgroundColor: "transparent" },
      { borderLeftColor: "rgb(26, 23, 20)" },
    ]);
  });
});

describe("composerKeyframes", () => {
  it("translates the real composer back onto the landing box and widens it", () => {
    const { wrap, box } = composerKeyframes(ORIGIN, TARGET);

    // centre-x 640 → 720, top 304 → 688
    expect(wrap).toEqual([
      { transform: "translate(-80px, -384px)" },
      { transform: "translate(0px, 0px)" },
    ]);
    expect(box).toEqual([{ maxWidth: "680px" }, { maxWidth: "880px" }]);
  });
});
