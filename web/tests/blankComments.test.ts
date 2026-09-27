// @vitest-environment node
import { describe, expect, it } from "vitest";

import { blankComments } from "./helpers/blankComments";

// #349. `routeConstruction.test.ts` decides whether a route is reachable by
// regex over source text. With no notion of what is live code, a
// commented-out constructor satisfies it — which is precisely the state #232
// was filed on, one comment marker away.
//
// The contract is narrower than "strip comments": it must blank them **in
// place**. `constructorsOf` derives its reported `file:line` from a character
// offset (`text.slice(0, m.index).split("\n").length`), so any transform that
// changes length or newline count silently corrupts every location the guard
// prints.

describe("blankComments", () => {
  it("preserves length and line count exactly", () => {
    const src = ['const a = 1; // trailing', "/* block */ const b = 2;", "const c = 3;"].join(
      "\n",
    );
    const out = blankComments(src);
    expect(out).toHaveLength(src.length);
    expect(out.split("\n")).toHaveLength(src.split("\n").length);
  });

  it("preserves newlines inside a multi-line block comment", () => {
    const src = "a\n/* one\ntwo\nthree */\nb";
    const out = blankComments(src);
    expect(out.split("\n")).toHaveLength(5);
    expect(out).toHaveLength(src.length);
    // The line the code is on must not move.
    expect(out.split("\n")[4]).toBe("b");
  });

  it("blanks a line comment but keeps code before it", () => {
    const out = blankComments('navigate({ kind: "reader" }); // and a note');
    expect(out).toContain('navigate({ kind: "reader" });');
    expect(out).not.toContain("and a note");
  });

  it("blanks a commented-out constructor entirely", () => {
    // The mutation from #349's measurement.
    const out = blankComments("        // syntaxChunkId: chunkId,");
    expect(out.trim()).toBe("");
    expect(out).not.toContain("syntaxChunkId");
  });

  it("does not treat // inside a string literal as a comment", () => {
    // Otherwise a URL in a string blanks the rest of the line, which can
    // hide a real constructor sitting after it.
    const src = 'const u = "https://example.com"; navigate({ kind: "reader" });';
    const out = blankComments(src);
    expect(out).toContain('navigate({ kind: "reader" });');
    expect(out).toContain("https://example.com");
  });

  it("handles escaped quotes inside strings without losing track", () => {
    const src = 'const s = "a \\" // not a comment"; navigate({ kind: "refs" });';
    const out = blankComments(src);
    expect(out).toContain('navigate({ kind: "refs" });');
  });

  it("does not treat // inside a template literal as a comment", () => {
    const src = "const u = `https://x.dev`; navigate({ kind: \"network\" });";
    const out = blankComments(src);
    expect(out).toContain('navigate({ kind: "network" });');
  });

  it("blanks a block comment wrapping a constructor on one line", () => {
    const out = blankComments('/* navigate({ kind: "syntax" }); */');
    expect(out.trim()).toBe("");
  });

  it("leaves ordinary division alone", () => {
    const src = "const half = total / 2; const q = a / b;";
    expect(blankComments(src)).toBe(src);
  });

  it("blanks a JSX comment block", () => {
    // `{/* … */}` — the braces are code, the inner block is not.
    const out = blankComments('{/* <Foo kind="reader" /> */}');
    expect(out).not.toContain("reader");
    expect(out.startsWith("{")).toBe(true);
    expect(out.endsWith("}")).toBe(true);
  });
});
