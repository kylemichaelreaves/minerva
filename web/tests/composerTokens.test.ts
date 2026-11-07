import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { contrastRatio } from "./helpers/contrast";
import { must } from "./helpers/must";

const css = readFileSync("src/styles/styles.css", "utf8");

/** Declarations of the first top-level block opened by `selector`. */
function themeVars(selector: string): Map<string, string> {
  const start = css.indexOf(`${selector} {`);
  const body = css.slice(start, css.indexOf("\n}", start));
  const vars = new Map<string, string>();
  for (const m of body.matchAll(/(--[\w-]+):\s*([^;]+);/g)) {
    vars.set(must(m[1]), must(m[2]).trim());
  }
  return vars;
}

function resolve(vars: Map<string, string>, name: string): string {
  const raw = must(vars.get(name), name);
  const ref = /^var\((--[\w-]+)\)$/.exec(raw);
  return ref ? resolve(vars, must(ref[1])) : raw;
}

describe.each([
  ["light", ":root"],
  ["dark", '[data-theme="dark"]'],
])("composer tokens (%s)", (_theme, selector) => {
  const vars = themeVars(selector);
  const pair = (fg: string, bg: string) => contrastRatio(resolve(vars, fg), resolve(vars, bg));

  it("defines the shadow token", () => {
    expect(vars.get("--composer-shadow")).toBeTruthy();
  });
  it("--on-accent is legible on --accent", () => {
    expect(pair("--on-accent", "--accent")).toBeGreaterThanOrEqual(4.5);
  });
  it("--ink is legible on --paper-raised", () => {
    expect(pair("--ink", "--paper-raised")).toBeGreaterThanOrEqual(4.5);
  });
  it("--ink-mute (key hint) is legible on --paper-raised", () => {
    expect(pair("--ink-mute", "--paper-raised")).toBeGreaterThanOrEqual(4.5);
  });
});
