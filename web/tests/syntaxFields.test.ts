import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { parseConllu } from "~/Syntax/conllu/parse";
import type { Sentence, Token } from "~/Syntax/conllu/types";
import { FIELD_NAMES, fieldRuns, topologicalFields } from "~/Syntax/layout/fields";

// The topological-field heuristic, checked against expectations derived by
// hand from the corrected rule in docs/syntax-annotation-plan.md — *not* from
// this implementation's output, and not from the source brief, whose version
// of the Rechte Klammer is inverted for UD.
//
// The brief defines RK as "tokens depending on LK". UD makes the participle
// the head and the finite auxiliary its `aux` dependent, so on fixture 1
// nothing depends on `hat`, RK computes empty, and the Mittelfeld swallows the
// clause. The rule here climbs to the head instead.

const fixture = (name: string): Sentence => {
  const raw = readFileSync(resolve(process.cwd(), "public/data", `${name}.conllu`), "utf8");
  const sent = parseConllu(raw).sentences[0];
  if (!sent) throw new Error(`${name} parsed to no sentences`);
  return sent;
};

/** `VF=Der Geist · LK=hat` — a whole assignment as one readable string. */
const shape = (sent: Sentence): string => {
  const forms = new Map(sent.tokens.map((t) => [t.id, t.form]));
  return topologicalFields(sent.tokens)
    .map((f) => `${f.name}=${f.tokens.map((id) => forms.get(id) ?? "?").join(" ")}`)
    .join(" · ");
};

/** A minimal token; only the columns the heuristic reads are interesting. */
const tok = (id: number, form: string, over: Partial<Token> = {}): Token => ({
  id,
  form,
  lemma: form.toLowerCase(),
  upos: "NOUN",
  xpos: "NN",
  feats: "_",
  head: 0,
  deprel: "dep",
  deps: "_",
  misc: "_",
  ...over,
});

const FIN = "Mood=Ind|Number=Sing|Person=3|Tense=Pres|VerbForm=Fin";

describe("topologicalFields", () => {
  it("puts the participle in the right bracket, not the finite auxiliary", () => {
    // Der Geist | hat | sich in der Geschichte | entwickelt | —
    // The whole point of the correction: `hat` is the LK and `entwickelt`,
    // its head, is the RK. Under the brief's rule RK would be empty.
    expect(shape(fixture("fixture_projective"))).toBe(
      "VF=Der Geist · LK=hat · MF=sich in der Geschichte · RK=entwickelt",
    );
  });

  it("leaves the Nachfeld empty rather than filling it with the full stop", () => {
    // Punctuation is excluded from assignment. Without that, fixture 1's
    // Nachfeld is `.` and the sentence reads as extraposed when it is not.
    const fields = topologicalFields(fixture("fixture_projective").tokens);

    expect(fields.map((f) => f.name)).toEqual(["VF", "LK", "MF", "RK"]);
  });

  it("puts an extraposed relative clause in the Nachfeld", () => {
    // Den Mann | habe | ich | gesehen | der dort steht
    // The non-projective fixture's crossing arc *is* the extraposition, so the
    // two derivations agree: what renders below the row is what lands right of
    // the right bracket.
    expect(shape(fixture("fixture_nonprojective"))).toBe(
      "VF=Den Mann · LK=habe · MF=ich · RK=gesehen · NF=der dort steht",
    );
  });

  it("takes a finite root as the left bracket itself", () => {
    // Der Geist entwickelt sich. — no auxiliary, so the right bracket is
    // empty and everything after the finite verb is Mittelfeld.
    const tokens = [
      tok(1, "Der", { upos: "DET", head: 2, deprel: "det" }),
      tok(2, "Geist", { head: 3, deprel: "nsubj" }),
      tok(3, "entwickelt", { upos: "VERB", feats: FIN, head: 0, deprel: "root" }),
      tok(4, "sich", { upos: "PRON", head: 3, deprel: "expl:pv" }),
      tok(5, ".", { upos: "PUNCT", head: 3, deprel: "punct" }),
    ];

    const fields = topologicalFields(tokens);

    expect(fields.map((f) => `${f.name}:${f.tokens.join(",")}`)).toEqual([
      "VF:1,2",
      "LK:3",
      "MF:4",
    ]);
  });

  it("carries a separable prefix into the right bracket", () => {
    // Er fängt heute an. — the particle is the right bracket of a finite
    // verb that is itself the left one.
    const tokens = [
      tok(1, "Er", { upos: "PRON", head: 2, deprel: "nsubj" }),
      tok(2, "fängt", { upos: "VERB", feats: FIN, head: 0, deprel: "root" }),
      tok(3, "heute", { upos: "ADV", head: 2, deprel: "advmod" }),
      tok(4, "an", { upos: "ADP", head: 2, deprel: "compound:prt" }),
      tok(5, ".", { upos: "PUNCT", head: 2, deprel: "punct" }),
    ];

    expect(topologicalFields(tokens).map((f) => `${f.name}:${f.tokens.join(",")}`)).toEqual([
      "VF:1",
      "LK:2",
      "MF:3",
      "RK:4",
    ]);
  });

  it("gathers a whole verbal complex into the right bracket", () => {
    // Er wird das Buch gelesen haben. — RK is the head plus its own later
    // auxiliaries, so `gelesen haben` brackets as one unit.
    const tokens = [
      tok(1, "Er", { upos: "PRON", head: 5, deprel: "nsubj" }),
      tok(2, "wird", { upos: "AUX", feats: FIN, head: 5, deprel: "aux" }),
      tok(3, "das", { upos: "DET", head: 4, deprel: "det" }),
      tok(4, "Buch", { head: 5, deprel: "obj" }),
      tok(5, "gelesen", { upos: "VERB", feats: "VerbForm=Part", head: 0, deprel: "root" }),
      tok(6, "haben", { upos: "AUX", feats: "VerbForm=Inf", head: 5, deprel: "aux" }),
      tok(7, ".", { upos: "PUNCT", head: 5, deprel: "punct" }),
    ];

    expect(topologicalFields(tokens).map((f) => `${f.name}:${f.tokens.join(",")}`)).toEqual([
      "VF:1",
      "LK:2",
      "MF:3,4",
      "RK:5,6",
    ]);
  });

  it("declines to guess when the sentence has no finite verb", () => {
    // A heading, a fragment, an infinitival — no left bracket, so no fields
    // rather than an invented one.
    const tokens = [
      tok(1, "Vom", { upos: "ADP", head: 2, deprel: "case" }),
      tok(2, "Nutzen", { head: 0, deprel: "root" }),
      tok(3, "der", { upos: "DET", head: 4, deprel: "det" }),
      tok(4, "Historie", { head: 2, deprel: "nmod" }),
    ];

    expect(topologicalFields(tokens)).toEqual([]);
  });

  it("declines to guess when the right bracket would sit left of the left one", () => {
    // Verb-final subordination promoted to root: the finite `aux` follows its
    // participial head, so the brackets invert. An inverted field model is
    // worse than none — the heuristic reports no right bracket instead.
    const tokens = [
      tok(1, "dass", { upos: "SCONJ", head: 3, deprel: "mark" }),
      tok(2, "gelesen", { upos: "VERB", feats: "VerbForm=Part", head: 0, deprel: "root" }),
      tok(3, "hat", { upos: "AUX", feats: FIN, head: 2, deprel: "aux" }),
    ];

    const fields = topologicalFields(tokens);

    expect(fields.map((f) => f.name)).not.toContain("RK");
    expect(fields.map((f) => `${f.name}:${f.tokens.join(",")}`)).toEqual(["VF:1,2", "LK:3"]);
  });

  it("assigns every non-punctuation token to exactly one field", () => {
    // The bands are drawn from each field's extent, so a token claimed twice
    // would render under two overlapping brackets.
    for (const name of ["fixture_projective", "fixture_nonprojective"]) {
      const sent = fixture(name);
      const claimed = topologicalFields(sent.tokens).flatMap((f) => f.tokens);
      const words = sent.tokens.filter((t) => t.upos !== "PUNCT").map((t) => t.id);

      expect(new Set(claimed).size, name).toBe(claimed.length);
      expect(
        claimed.slice().sort((a, b) => a - b),
        name,
      ).toEqual(words);
    }
  });

  it("names every field it can emit", () => {
    // The renderer keys its labels off this list; a field with no entry would
    // draw an unlabelled band.
    expect(Object.keys(FIELD_NAMES)).toEqual(["VF", "LK", "MF", "RK", "NF"]);
  });
});

describe("fieldRuns", () => {
  const never = () => false;

  it("draws one band for a field whose tokens are adjacent", () => {
    expect(fieldRuns([2, 3, 4], [1, 2, 3, 4, 5], never)).toEqual([[2, 3, 4]]);
  });

  it("splits a field interrupted by a token it does not claim", () => {
    // `hat versucht … das zu tun` — the right bracket holds both verbs and
    // nothing between them, so one band would bracket words it never claimed.
    expect(fieldRuns([2, 6], [1, 2, 3, 4, 5, 6], never)).toEqual([[2], [6]]);
  });

  it("bridges punctuation rather than breaking on it", () => {
    // The comma is unassigned by rule, not because the heuristic failed on
    // it; sawing the Mittelfeld in half at every comma would be noise.
    const isPunct = (id: number) => id === 3;

    expect(fieldRuns([2, 4], [1, 2, 3, 4, 5], isPunct)).toEqual([[2, 3, 4]]);
  });

  it("does not trail a band past its last token onto punctuation", () => {
    const isPunct = (id: number) => id === 3;

    expect(fieldRuns([1, 2], [1, 2, 3, 4], isPunct)).toEqual([[1, 2]]);
  });

  it("ignores ids that are not on this row", () => {
    // A field spanning a wrap draws one band per row, from that row's members.
    expect(fieldRuns([1, 2, 7, 8], [6, 7, 8, 9], never)).toEqual([[7, 8]]);
  });

  it("has nothing to draw for a field entirely on another row", () => {
    expect(fieldRuns([1, 2], [6, 7, 8], never)).toEqual([]);
  });
});
