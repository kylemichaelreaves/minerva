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
  scrollTop: 0,
  visibleHeight: 26,
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
    fontFamily: '"EB Garamond", serif',
    fontWeight: "400",
    letterSpacing: "normal",
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
    Object.defineProperty(ta, "clientHeight", { value: 26 });
    stubStyle(
      new Map([
        [
          ta,
          {
            fontSize: "17px",
            lineHeight: "24.65px",
            color: "rgb(26, 23, 20)",
            fontStyle: "italic",
          },
        ],
      ]),
    );

    const o = measureOrigin(ta, box);

    expect(o.textTop).toBe(260);
    expect(o.textLeft).toBe(200);
    expect(o.textWidth).toBe(648);
    expect(o.text).toBe("Why?");
    expect(o.scrollTop).toBe(40);
    expect(o.visibleHeight).toBe(26);
    expect(o.style.fontSize).toBe("17px");
    expect(o.box).toEqual({ top: 288, left: 184, width: 680, height: 88 });
    expect(o.chip).toBeUndefined();
  });

  it("measures the landing's scope chip when there is one", () => {
    const ta = document.createElement("textarea");
    const box = document.createElement("div");
    const chip = document.createElement("div");
    stubRect(chip, { top: 316, left: 763, width: 182, height: 31 });

    expect(measureOrigin(ta, box, chip).chip).toEqual({
      top: 316,
      left: 763,
      width: 182,
      height: 31,
    });
  });

  it("counts the textarea's padding and border into the text origin", () => {
    const ta = document.createElement("textarea");
    ta.value = "Q";
    const box = document.createElement("div");
    stubRect(ta, { top: 100, left: 50, width: 400, height: 30 });
    stubRect(box, { top: 90, left: 40, width: 420, height: 60 });
    Object.defineProperty(ta, "clientWidth", { value: 398 });
    Object.defineProperty(ta, "clientHeight", { value: 40 });
    stubStyle(
      new Map([
        [
          ta,
          {
            paddingTop: "4px",
            paddingBottom: "2px",
            paddingLeft: "6px",
            paddingRight: "8px",
            borderTopWidth: "1px",
            borderLeftWidth: "1px",
          },
        ],
      ]),
    );

    const o = measureOrigin(ta, box);

    expect(o.textTop).toBe(105);
    expect(o.textLeft).toBe(57);
    expect(o.textWidth).toBe(384);
    expect(o.visibleHeight).toBe(34);
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
    expect(t.chip).toBeUndefined();
    const chip = document.createElement("div");
    stubRect(chip, { top: 649, left: 763, width: 182, height: 31 });
    expect(measureTarget(body, composer, chip).chip?.top).toBe(649);
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

    // centre-x 640 → 720; bottom 392 → 784, the wrap being bottom-pinned:
    // at the landing box's 88px height, that puts the top on 304.
    expect(wrap).toEqual([
      { transform: "translate(-80px, -392px)" },
      { transform: "translate(0px, 0px)" },
    ]);
    // …and its height: a 1-line landing box is shorter than the composer,
    // a 20-line one far taller, and the box must not step on frame 0.
    expect(box).toEqual([
      { maxWidth: "680px", height: "88px" },
      { maxWidth: "880px", height: "96px" },
    ]);
  });

  it("has no chip to carry unless both ends have one", () => {
    expect(composerKeyframes(ORIGIN, TARGET).chip).toBeUndefined();
    const chip = { top: 316, left: 763, width: 182, height: 31 };
    expect(composerKeyframes({ ...ORIGIN, chip }, TARGET).chip).toBeUndefined();
    expect(composerKeyframes(ORIGIN, { ...TARGET, chip }).chip).toBeUndefined();
  });

  it("carries the scope chip from the landing's chip, net of the wrap's own move", () => {
    const { chip } = composerKeyframes(
      { ...ORIGIN, chip: { top: 316, left: 763, width: 182, height: 31 } },
      { ...TARGET, chip: { top: 649, left: 763, width: 182, height: 31 } },
    );

    // The chip moves with the box's top, which frame 0 puts on 304 (from
    // 688): so 316 - 649 + 384 = 51 down, and 80 right against the wrap's
    // -80. Opaque throughout, over the CSS fade-in an unscoped landing gets.
    expect(chip).toEqual([
      { transform: "translate(80px, 51px)", opacity: 1 },
      { transform: "translate(0px, 0px)", opacity: 1 },
    ]);
  });
});

describe("ghostKeyframes clip", () => {
  it("shows exactly the textarea's visible window on the first frame, then all of it", () => {
    // A question scrolled 40px inside a 26px-tall textarea: the ghost carries
    // the whole text, but on frame 0 only what the textarea showed is visible.
    const { move } = ghostKeyframes({ ...ORIGIN, scrollTop: 40, visibleHeight: 26 }, TARGET);

    // target insets: 0 top padding + 0 top border, so the window starts at 40.
    expect(move).toMatchObject([
      { clipPath: "inset(40px 0px calc(100% - 66px) 0px)" },
      { clipPath: "inset(0px 0px 0px 0px)" },
    ]);
  });
});
