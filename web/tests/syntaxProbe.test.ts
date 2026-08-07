import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { TOKEN_GAP, TOKEN_PAD_X, probeWidths } from "~/Syntax/layout/measure";

// The one place the arc diagram touches the DOM, and the constants it assumes
// the stylesheet agrees with.
//
// Token positions are computed analytically rather than read back from the
// laid-out row — measuring the DOM would be circular, because widths decide
// the row breaks and the row breaks decide the DOM. That arithmetic is only
// right while it performs the *same* sum the flex row does, which makes both
// halves of this file a check on one thing: does the computed geometry still
// match what the browser draws (#142)?

/** A hidden probe row whose cells report *widths*, sub-pixel and all. */
function probeWith(widths: readonly number[]): HTMLElement {
  const probe = document.createElement("div");
  widths.forEach((w, i) => {
    const cell = document.createElement("span");
    cell.dataset.probe = String(i + 1);
    // jsdom lays nothing out, so both readings are stubbed explicitly — which
    // is the point: the test can tell which one the code took.
    cell.getBoundingClientRect = () => ({ width: w }) as DOMRect;
    Object.defineProperty(cell, "offsetWidth", { value: Math.round(w) });
    probe.appendChild(cell);
  });
  return probe;
}

describe("probeWidths", () => {
  it("keeps the fractional width the flex row actually lays out", () => {
    // `offsetWidth` rounds to a whole pixel. The row it is standing in for
    // does not, so the error accumulates token by token: ~0.8px each, ~8px by
    // the end of a ten-token row, and the arrowhead lands beside its glyph.
    const widths = probeWidths(probeWith([41.6, 58.4]));

    expect(widths.get(1)).toBeCloseTo(41.6, 5);
    expect(widths.get(2)).toBeCloseTo(58.4, 5);
  });

  it("keys the widths by token id, not by position", () => {
    const probe = probeWith([10, 20]);
    probe.children[0]?.setAttribute("data-probe", "7");

    expect(probeWidths(probe).get(7)).toBe(10);
  });

  it("ignores anything in the probe that is not a cell", () => {
    const probe = probeWith([10]);
    probe.appendChild(document.createElement("span"));

    expect(probeWidths(probe).size).toBe(1);
  });
});

describe("the constants the analytic path assumes", () => {
  // Read out of the stylesheet, because the flex row is what actually happens
  // and these numbers only exist to predict it. A gap changed in CSS and not
  // here would slide every arc a little further off along the row, with
  // nothing failing.
  const css = readFileSync(resolve(process.cwd(), "src/Syntax/syntax.css"), "utf8");

  const ruleBody = (selector: string): string => {
    const at = css.indexOf(`${selector} {`);
    if (at === -1) throw new Error(`no rule for ${selector}`);
    return css.slice(at, css.indexOf("}", at));
  };

  const declaration = (selector: string, prop: string): string => {
    const m = new RegExp(`\\b${prop}\\s*:\\s*([^;]+);`).exec(ruleBody(selector));
    if (!m?.[1]) throw new Error(`no ${prop} on ${selector}`);
    return m[1].trim();
  };

  it("matches TOKEN_GAP to the gap on the token row", () => {
    expect(declaration(".syn-toks", "gap")).toBe(`${String(TOKEN_GAP)}px`);
  });

  it("matches TOKEN_PAD_X to the horizontal padding on a token", () => {
    // The probe is a bare `.syn-form`, so it carries none of `.syn-tok`'s
    // padding; the analytic path adds it back. Shorthand is `top x bottom`,
    // and the middle value is the one on both sides.
    const parts = declaration(".syn-tok", "padding").split(/\s+/);
    const x = Number((parts[1] ?? "").replace("px", ""));

    expect(x * 2).toBe(TOKEN_PAD_X);
  });
});
