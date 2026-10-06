// @vitest-environment node
import { describe, expect, it } from "vitest";
import { Linter } from "eslint";
import tsParser from "@typescript-eslint/parser";
import { MOUSE_ONLY_MESSAGE, minervaPlugin } from "../eslint.mouseOnly.js";

// The gate behind #773: an intrinsic element that is not natively interactive
// and carries `onClick` with no `role`, `tabindex` or `href` is reachable by
// mouse only. These pin the selector's edges, since a selector that is merely
// wrong reports nothing at all.
const linter = new Linter({ configType: "flat" });
const lint = (code: string) =>
  linter
    .verify(
      code,
      [
        {
          files: ["**/*.tsx"],
          languageOptions: {
            parser: tsParser,
            parserOptions: { ecmaFeatures: { jsx: true } },
          },
          plugins: { minerva: minervaPlugin },
          rules: { "minerva/no-mouse-only-click": "error" },
        },
      ],
      "probe.tsx",
    )
    .map((m) => m.message);

describe("mouse-only control selector", () => {
  it.each([
    ["a span", `<span onClick={f}>x</span>`],
    ["a div", `<div class="row" onClick={f} />`],
    ["an svg group", `<g onClick={f}><path /></g>`],
    ["a table row", `<tr onClick={f}><td /></tr>`],
    ["an anchor with no href", `<a onClick={f}>x</a>`],
  ])("flags %s with onClick and nothing else", (_, jsx) => {
    expect(lint(`const v = ${jsx};`)).toEqual([MOUSE_ONLY_MESSAGE]);
  });

  it.each([
    ["a button", `<button type="button" onClick={f}>x</button>`],
    ["an input", `<input onClick={f} />`],
    ["a summary", `<summary onClick={f}>x</summary>`],
    ["an anchor with href", `<a href="#/x" onClick={f}>x</a>`],
    ["an element with a role", `<g role="button" tabindex="0" onClick={f} />`],
    ["an element with tabindex only", `<div tabindex="-1" onClick={f} />`],
    ["an element with camelCase tabIndex", `<div tabIndex={0} onClick={f} />`],
    ["a component", `<KwicRow onClick={f} />`],
    ["a span with no handler", `<span onMouseEnter={f}>x</span>`],
  ])("passes %s", (_, jsx) => {
    expect(lint(`const v = ${jsx};`)).toEqual([]);
  });

  it("reports the onClick, so a disable comment sits beside the handler", () => {
    const out = linter.verify(
      `const v = (\n  <span\n    class="x"\n    onClick={f}\n  />\n);`,
      [
        {
          files: ["**/*.tsx"],
          languageOptions: { parser: tsParser, parserOptions: { ecmaFeatures: { jsx: true } } },
          plugins: { minerva: minervaPlugin },
          rules: { "minerva/no-mouse-only-click": "error" },
        },
      ],
      "probe.tsx",
    );
    expect(out.map((m) => m.line)).toEqual([4]);
  });
});
