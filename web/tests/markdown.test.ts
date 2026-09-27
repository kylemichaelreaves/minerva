// @vitest-environment node
import { describe, it, expect } from "vitest";
import { parseBlock, parseBlocks, parseRichText } from "~/utils/markdown";

describe("parseRichText()", () => {
  it("returns plain text untouched", () => {
    expect(parseRichText("plain words")).toEqual(["plain words"]);
  });

  it("parses **bold**", () => {
    expect(parseRichText("a **bold** b")).toEqual([
      "a ",
      { kind: "bold", children: ["bold"] },
      " b",
    ]);
  });

  it("parses *italic*", () => {
    expect(parseRichText("a *em* b")).toEqual(["a ", { kind: "italic", children: ["em"] }, " b"]);
  });

  it("parses `code`", () => {
    expect(parseRichText("use `foo()` here")).toEqual([
      "use ",
      { kind: "code", text: "foo()" },
      " here",
    ]);
  });

  it("parses [N] citation markers", () => {
    expect(parseRichText("see [1] also")).toEqual(["see ", { kind: "cite", n: 1 }, " also"]);
  });

  it("handles bold containing a citation (nested)", () => {
    expect(parseRichText("**bold [3] text**")).toEqual([
      { kind: "bold", children: ["bold ", { kind: "cite", n: 3 }, " text"] },
    ]);
  });

  it("handles italic containing a citation", () => {
    expect(parseRichText("*it [2] em*")).toEqual([
      { kind: "italic", children: ["it ", { kind: "cite", n: 2 }, " em"] },
    ]);
  });

  it("matches **bold** before *italic* even though both start with *", () => {
    // If italic matched first, we'd get a stray * + invalid italic.
    expect(parseRichText("**bold**")).toEqual([{ kind: "bold", children: ["bold"] }]);
  });

  it("does not treat asterisks adjacent to whitespace as italic delimiters", () => {
    // The italic alternative requires non-whitespace at both ends, so
    // arithmetic-style strings like "2 * 3" don't get parsed as italic.
    expect(parseRichText("multiply 2 * 3 = 6")).toEqual(["multiply 2 * 3 = 6"]);
  });

  it("mixes bold, italic, code, citations, and plain text", () => {
    const out = parseRichText("Plato says **virtue** is *teachable* — see `Meno` [1].");
    expect(out).toEqual([
      "Plato says ",
      { kind: "bold", children: ["virtue"] },
      " is ",
      { kind: "italic", children: ["teachable"] },
      " — see ",
      { kind: "code", text: "Meno" },
      " ",
      { kind: "cite", n: 1 },
      ".",
    ]);
  });

  it("returns [] for empty / non-string", () => {
    expect(parseRichText("")).toEqual([]);
    expect(parseRichText(undefined as unknown as string)).toEqual([]);
    expect(parseRichText(null)).toEqual([]);
    expect(parseRichText(42)).toEqual([]);
  });

  it("caps recursion to avoid pathological input", () => {
    // Wrap "x" in many layers of bold; once depth exceeds the cap we
    // bail out and return the raw inner string instead of recursing
    // deeper. The exact tree shape doesn't matter — only that the call
    // returns instead of stack-overflowing.
    let s = "x";
    for (let i = 0; i < 12; i++) s = `**${s}**`;
    expect(() => parseRichText(s)).not.toThrow();
  });
});

describe("parseBlock()", () => {
  it("detects # heading", () => {
    expect(parseBlock("# Heading 1")).toEqual({ kind: "h1", body: "Heading 1" });
  });
  it("detects ## heading", () => {
    expect(parseBlock("## Sub")).toEqual({ kind: "h2", body: "Sub" });
  });
  it("detects ### heading", () => {
    expect(parseBlock("### Tertiary")).toEqual({ kind: "h3", body: "Tertiary" });
  });
  it("detects - list items", () => {
    expect(parseBlock("- item one")).toEqual({ kind: "list-item", body: "item one" });
  });
  it("detects * list items", () => {
    expect(parseBlock("* item two")).toEqual({ kind: "list-item", body: "item two" });
  });
  it("returns paragraph for everything else", () => {
    expect(parseBlock("Plain prose.")).toEqual({ kind: "paragraph", body: "Plain prose." });
  });
  it("does not mistake **bold** for a heading", () => {
    expect(parseBlock("**bold** at start").kind).toBe("paragraph");
  });
  it("does not mistake ## (no trailing space) for a heading", () => {
    // The heading marker requires a trailing space; `##` alone is plain prose.
    expect(parseBlock("##").kind).toBe("paragraph");
    expect(parseBlock("###hello").kind).toBe("paragraph");
  });

  it("detects --- as a thematic break (horizontal rule)", () => {
    expect(parseBlock("---")).toEqual({ kind: "hr", body: "" });
    expect(parseBlock("-----")).toEqual({ kind: "hr", body: "" });
    expect(parseBlock("  ---  ")).toEqual({ kind: "hr", body: "" });
  });

  it("also detects *** and ___ as thematic breaks", () => {
    expect(parseBlock("***").kind).toBe("hr");
    expect(parseBlock("___").kind).toBe("hr");
  });

  it("does not mistake -- (only two dashes) for a thematic break", () => {
    expect(parseBlock("--").kind).toBe("paragraph");
  });

  it('does not mistake "--- text" for a thematic break', () => {
    // CommonMark: a thematic break is the entire line being dashes; trailing
    // text disqualifies it.
    expect(parseBlock("--- text").kind).toBe("paragraph");
  });
});

describe("parseBlocks()", () => {
  it("returns a single paragraph block for plain prose", () => {
    expect(parseBlocks("Plato says the city is just.")).toEqual([
      { kind: "paragraph", body: "Plato says the city is just." },
    ]);
  });

  it("keeps multi-line plain prose as one paragraph", () => {
    // Without any block markers, internal newlines stay inside the
    // paragraph. (The renderer collapses them via normal whitespace.)
    expect(parseBlocks("line one\nline two")).toEqual([
      { kind: "paragraph", body: "line one\nline two" },
    ]);
  });

  it('splits a "**Sources**\\n- a\\n- b" paragraph into header + two items', () => {
    expect(parseBlocks("**Sources**\n- a\n- b")).toEqual([
      { kind: "paragraph", body: "**Sources**" },
      { kind: "list-item", body: "a" },
      { kind: "list-item", body: "b" },
    ]);
  });

  it("handles bullet-only paragraphs", () => {
    expect(parseBlocks("- one\n- two\n- three")).toEqual([
      { kind: "list-item", body: "one" },
      { kind: "list-item", body: "two" },
      { kind: "list-item", body: "three" },
    ]);
  });

  it("handles a heading line followed by bullets", () => {
    expect(parseBlocks("## Sources\n- a\n- b")).toEqual([
      { kind: "h2", body: "Sources" },
      { kind: "list-item", body: "a" },
      { kind: "list-item", body: "b" },
    ]);
  });

  it("drops blank lines between blocks", () => {
    expect(parseBlocks("## H\n\n- a\n\n- b")).toEqual([
      { kind: "h2", body: "H" },
      { kind: "list-item", body: "a" },
      { kind: "list-item", body: "b" },
    ]);
  });

  it("does not split a paragraph that has no block markers", () => {
    // A multi-sentence prose paragraph stays intact.
    const p = "Sentence one. Sentence two\nwith a wrapped line.";
    expect(parseBlocks(p)).toEqual([{ kind: "paragraph", body: p }]);
  });
});
