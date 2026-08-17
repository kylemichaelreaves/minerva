import { describe, it, expect } from "vitest";
import { romanize, tokenizeGreek, tokenizeWords, containsGreek } from "~/utils/greek";

describe("romanize", () => {
  it("handles common words without breathing", () => {
    expect(romanize("λόγος")).toBe("logos");
    expect(romanize("ἀρχή")).toBe("arche");
    expect(romanize("φύσει")).toBe("physei");
  });

  it("aspirates initial vowels with rough breathing", () => {
    expect(romanize("ἡ")).toBe("he");
    expect(romanize("ὁ")).toBe("ho");
    expect(romanize("οὕτως")).toBe("houtos");
  });

  it("leaves smooth-breathing words unaspirated", () => {
    expect(romanize("ἄνθρωπος")).toBe("anthropos");
    expect(romanize("ἀρετή")).toBe("arete");
  });

  it("renders initial ρ with rough breathing as 'rh'", () => {
    expect(romanize("ῥήτωρ")).toBe("rhetor");
    expect(romanize("ῥητορική")).toBe("rhetorike");
  });

  it("applies the γ-nasal rule before γκξχ", () => {
    expect(romanize("ἄγγελος")).toBe("angelos");
    expect(romanize("ἀνάγκη")).toBe("ananke");
  });

  it("renders θφχψξ as digraphs", () => {
    expect(romanize("θεός")).toBe("theos");
    expect(romanize("ψυχή")).toBe("psyche");
    expect(romanize("ἄξιος")).toBe("axios");
  });

  it("preserves initial capital from the source", () => {
    expect(romanize("Ἀριστοτέλης")).toBe("Aristoteles");
    expect(romanize("Ἀθηναῖοι")).toBe("Athenaioi");
  });

  it("passes through empty input", () => {
    expect(romanize("")).toBe("");
  });
});

describe("tokenizeGreek", () => {
  it("splits Greek words from spacing and punctuation", () => {
    const tokens = tokenizeGreek("πᾶσα τέχνη, καὶ μέθοδος.");
    expect(tokens).toEqual([
      { word: true, s: "πᾶσα", offset: 0 },
      { word: false, s: " ", offset: 4 },
      { word: true, s: "τέχνη", offset: 5 },
      { word: false, s: ", ", offset: 10 },
      { word: true, s: "καὶ", offset: 12 },
      { word: false, s: " ", offset: 15 },
      { word: true, s: "μέθοδος", offset: 16 },
      { word: false, s: ".", offset: 23 },
    ]);
  });

  it("treats a mixed Latin/Greek string sensibly", () => {
    const tokens = tokenizeGreek("Book 1: λόγος");
    // "Book 1: " is non-Greek; "λόγος" is the only Greek run; offset
    // is its byte position into the source string.
    expect(tokens.filter((t) => t.word)).toEqual([
      { word: true, s: "λόγος", offset: 8 },
    ]);
  });
});

describe("containsGreek", () => {
  it("detects Greek script", () => {
    expect(containsGreek("λόγος")).toBe(true);
    expect(containsGreek("Republic")).toBe(false);
    expect(containsGreek("1094a")).toBe(false);
  });
});

describe("containsGreek is a script test, not a combining-mark test (#367)", () => {
  it("rejects decomposed Latin", () => {
    // NFD "Schröder": the diaeresis is U+0308, Script=Inherited. The
    // detector's `\p{M}` arm answered true for it, which is how a German
    // label in the Concordance got a Greek romanization tooltip.
    expect(containsGreek("Schröder".normalize("NFD"))).toBe(false);
  });

  it("rejects pointed Hebrew and vocalized Arabic in NFC", () => {
    // Niqqud and tashkeel have no precomposed forms, so these carry
    // combining marks in the form the corpus stores. No NFD involved.
    expect(containsGreek("שָׁלוֹם")).toBe(false);
    expect(containsGreek("مُحَمَّد")).toBe(false);
  });

  it("answers the same for Greek in either normalization form", () => {
    // The base letters carry Script=Greek either way, so the detector
    // needs no normalization pass of its own.
    expect(containsGreek("ἄνθρωπος".normalize("NFC"))).toBe(true);
    expect(containsGreek("ἄνθρωπος".normalize("NFD"))).toBe(true);
  });
});

describe("tokenizeGreek's word flag (#367)", () => {
  it("does not call a bare combining mark a Greek word", () => {
    // TOKEN_RE splits NFD "Schröder" into "Schro" / "̈" / "der";
    // the middle run is a lone Inherited mark and is not a word.
    const tokens = tokenizeGreek("Schröder".normalize("NFD"));
    expect(tokens.filter((t) => t.word)).toEqual([]);
  });

  it("still keeps a Greek word whole across its own accents", () => {
    const nfd = "ἄνθρωπος".normalize("NFD");

    expect(tokenizeGreek(nfd)).toEqual([{ word: true, s: nfd, offset: 0 }]);
  });
});

describe("tokenizeWords", () => {
  // #422. The Reader wraps every `word: true` run in the `.gw` hover
  // affordance, so what counts as a word here is what a reader can hover.
  // A combining mark standing between non-letters is its own run, and
  // typing that run as a word puts a hover target on a recitation sign.
  //
  // Measured over the whole live index when this was filed: 4,367 such
  // runs across 2,643 of 426,514 chunks, every sampled one a Quran waqf
  // mark. The four below are those samples' characters.
  it.each([
    ["ۛ", "ARABIC SMALL HIGH THREE DOTS"],
    ["ۖ", "ARABIC SMALL HIGH LIGATURE SAD WITH LAM WITH ALEF MAKSURA"],
    ["ۗ", "ARABIC SMALL HIGH LIGATURE QAF WITH LAM WITH ALEF MAKSURA"],
    ["ۚ", "ARABIC SMALL HIGH JEEM"],
  ])("does not type the standalone waqf mark %s (%s) as a word", (mark) => {
    const toks = tokenizeWords(`رَيْبَ ${mark} فِيهِ`);
    const markTok = toks.find((t) => t.s === mark);
    expect(markTok).toBeDefined();
    expect(markTok!.word).toBe(false);
  });

  it("types the waqf mark's neighbours as words, from the filed example", () => {
    // The whole line from the issue. Only the pause mark should drop out;
    // the four vocalized words must survive, or the fix has traded a
    // spurious hover target for four missing ones.
    expect(
      tokenizeWords("بُ لَا رَيْبَ ۛ فِيهِ")
        .filter((t) => t.word)
        .map((t) => t.s),
    ).toEqual(["بُ", "لَا", "رَيْبَ", "فِيهِ"]);
  });

  it("keeps marks attached to their host letter rather than splitting them", () => {
    // `ANY_TOKEN_RE` must keep `\p{M}` so a mark continues its host's run.
    // This is the half of the pair that is load-bearing: dropping `\p{M}`
    // there would split `رَيْبَ` into a letter run and a mark run.
    const toks = tokenizeWords("رَيْبَ");
    expect(toks.filter((t) => t.word).map((t) => t.s)).toEqual(["رَيْبَ"]);
  });

  it("types an NFD-decomposed Latin word as one word", () => {
    // `é` as e + U+0301. The host letter makes the run a word; the fix
    // must not depend on the run being mark-free, only on it having a
    // letter somewhere.
    const nfd = "créer".normalize("NFD");
    // Guard the premise: assert this string really is decomposed, or the
    // test silently checks the precomposed path and its name lies.
    expect(nfd).not.toBe("créer".normalize("NFC"));
    expect(nfd.length).toBeGreaterThan("créer".normalize("NFC").length);
    expect(tokenizeWords(nfd).filter((t) => t.word).map((t) => t.s)).toEqual([nfd]);
  });

  it("preserves offsets across a dropped-to-punctuation mark run", () => {
    // The Reader maps hover targets onto term-occurrence spans by these
    // offsets, so reclassifying a run must not shift them.
    const text = "رَيْبَ ۛ فِيهِ";
    for (const t of tokenizeWords(text)) {
      expect(text.slice(t.offset, t.offset + t.s.length)).toBe(t.s);
    }
  });
});
