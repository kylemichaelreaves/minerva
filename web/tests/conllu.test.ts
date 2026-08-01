import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { parseConllu } from "~/Syntax/conllu/parse";
import { writeConllu } from "~/Syntax/conllu/serialise";
import type { Sentence, Token } from "~/Syntax/conllu/types";

// CoNLL-U is the interchange format for the syntax overlay: it is what we
// export, and what we would import a real treebank through. The parser is
// hand-written rather than installed — the format is ten tab-separated
// columns, sentences separated by a blank line, `#` comment lines carrying
// metadata.
//
// The load-bearing property is byte-identical round-tripping. A serialiser
// that quietly normalises whitespace, drops a comment, or renumbers a column
// turns "export your corrections" into silent corruption, and the corrections
// are hand labour. So `writeConllu(parseConllu(x)) === x` is asserted against
// the real fixture bytes, not a normalised form.

// Vite rewrites `import.meta.url` to a served URL under test, so resolve
// against the package root instead — vitest runs with cwd = web/.
const fixture = (name: string): string =>
  readFileSync(resolve(process.cwd(), "public/data", `${name}.conllu`), "utf8");

/** Build a CoNLL-U line from its ten columns. Written this way rather than
 *  as a template literal so the tabs survive `prettier --write`. */
const row = (...cols: string[]): string => cols.join("\t");

// `noUncheckedIndexedAccess` makes every `sentences[0]` an `X | undefined`.
// These narrow once, with a real failure message, instead of scattering `!`
// through the assertions.
function onlySentence(raw: string): Sentence {
  const { sentences } = parseConllu(raw);
  const sent = sentences[0];
  if (!sent) throw new Error(`expected one sentence, parsed ${sentences.length}`);
  return sent;
}

function tokenAt(sent: Sentence, index: number): Token {
  const tok = sent.tokens[index];
  if (!tok) throw new Error(`no token at index ${index} (have ${sent.tokens.length})`);
  return tok;
}

describe("parseConllu", () => {
  it("reads the ten columns of a token line", () => {
    const sent = onlySentence(fixture("fixture_projective"));

    expect(sent.sentId).toBe("proj-1");
    expect(sent.tokens).toHaveLength(9);

    expect(tokenAt(sent, 3)).toEqual({
      id: 4,
      form: "sich",
      lemma: "sich",
      upos: "PRON",
      xpos: "PRF",
      feats: "Case=Acc|Number=Sing|Person=3|Reflex=Yes",
      head: 8,
      deprel: "expl:pv",
      deps: "_",
      misc: "_",
    });
  });

  it("records head 0 for the root", () => {
    const sent = onlySentence(fixture("fixture_projective"));

    const root = sent.tokens.find((t) => t.head === 0);

    expect(root?.form).toBe("entwickelt");
    expect(root?.deprel).toBe("root");
  });

  it("keeps comment lines verbatim and lifts the metadata it knows", () => {
    const sent = onlySentence(fixture("fixture_nonprojective"));

    expect(sent.comments).toEqual([
      "# sent_id = nonproj-1",
      "# text = Den Mann habe ich gesehen, der dort steht.",
    ]);
    expect(sent.sentId).toBe("nonproj-1");
    expect(sent.text).toBe("Den Mann habe ich gesehen, der dort steht.");
  });
});

describe("writeConllu", () => {
  it.each(["fixture_projective", "fixture_nonprojective"])(
    "round-trips %s byte-identically",
    (name) => {
      const raw = fixture(name);

      expect(writeConllu(parseConllu(raw))).toBe(raw);
    },
  );

  it("round-trips a multi-sentence document", () => {
    const raw = fixture("fixture_projective") + fixture("fixture_nonprojective");

    const doc = parseConllu(raw);

    expect(doc.sentences).toHaveLength(2);
    expect(writeConllu(doc)).toBe(raw);
  });
});

// Multiword token ranges (`3-4 zum`) and empty nodes (`5.1`) are part of the
// format but have no place in an arc diagram — a range is one surface string
// spanning two syntactic words, and an empty node has no surface at all.
// Neither carries a usable (id, head) pair, so both are excluded from
// `tokens`. They still have to survive the round-trip, so they are retained
// verbatim with the position they occupied among the sentence's non-comment
// lines, and re-emitted there.
describe("multiword ranges and empty nodes", () => {
  const raw =
    [
      "# sent_id = mwt-1",
      "# text = Er geht zum Markt.",
      row("1", "Er", "er", "PRON", "PPER", "_", "2", "nsubj", "_", "_"),
      row("2", "geht", "gehen", "VERB", "VVFIN", "_", "0", "root", "_", "_"),
      row("3-4", "zum", "_", "_", "_", "_", "_", "_", "_", "_"),
      row("3", "zu", "zu", "ADP", "APPR", "_", "5", "case", "_", "_"),
      row("4", "dem", "der", "DET", "ART", "_", "5", "det", "_", "_"),
      row("5", "Markt", "Markt", "NOUN", "NN", "_", "2", "obl", "_", "SpaceAfter=No"),
      row("5.1", "_", "_", "_", "_", "_", "_", "_", "_", "_"),
      row("6", ".", ".", "PUNCT", "$.", "_", "2", "punct", "_", "_"),
    ].join("\n") + "\n\n";

  it("excludes them from tokens", () => {
    const sent = onlySentence(raw);

    expect(sent.tokens.map((t) => t.id)).toEqual([1, 2, 3, 4, 5, 6]);
  });

  it("records that they were skipped, and why", () => {
    const sent = onlySentence(raw);

    expect(sent.skipped.map(({ kind, id, lineIndex }) => ({ kind, id, lineIndex }))).toEqual([
      { kind: "multiword", id: "3-4", lineIndex: 2 },
      { kind: "empty", id: "5.1", lineIndex: 6 },
    ]);
    expect(sent.skipped.map((s) => s.raw).join("\n")).toContain("zum");
    expect(sent.skipped.map((s) => s.raw).join("\n")).toContain("5.1");
  });

  it("re-emits them in their original positions", () => {
    expect(writeConllu(parseConllu(raw))).toBe(raw);
  });
});

// HEAD may be `_` for a token that was never parsed. Reading that as 0 would
// invent a second root and trip the single-root check the editor enforces, so
// it is carried as null and written back as `_`.
describe("unparsed heads", () => {
  const raw =
    [
      "# sent_id = unparsed-1",
      row("1", "Der", "der", "DET", "ART", "_", "_", "_", "_", "_"),
      row("2", "Geist", "Geist", "NOUN", "NN", "_", "0", "root", "_", "_"),
    ].join("\n") + "\n\n";

  it("distinguishes `_` from attachment to root", () => {
    const sent = onlySentence(raw);

    expect(tokenAt(sent, 0).head).toBeNull();
    expect(tokenAt(sent, 1).head).toBe(0);
  });

  it("writes `_` back rather than 0", () => {
    expect(writeConllu(parseConllu(raw))).toBe(raw);
  });
});

// Real treebanks are not always canonically formatted. Parsing must tolerate
// what serialising never produces: extra blank lines between sentences, and a
// file that ends without the terminating blank line. Round-tripping those is
// explicitly NOT promised — `writeConllu` emits the canonical form.
describe("tolerating non-canonical input", () => {
  it("ignores runs of blank lines between sentences", () => {
    const raw = fixture("fixture_projective") + "\n\n\n" + fixture("fixture_nonprojective");

    expect(parseConllu(raw).sentences).toHaveLength(2);
  });

  it("accepts a final sentence with no terminating blank line", () => {
    const raw = fixture("fixture_projective").trimEnd();

    expect(onlySentence(raw).tokens).toHaveLength(9);
  });
});
