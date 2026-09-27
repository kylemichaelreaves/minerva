// @vitest-environment node
import { describe, it, expect } from "vitest";
import { romanize, containsHebrew } from "~/utils/hebrew";

describe("romanize (Hebrew)", () => {
  it("transliterates common pointed words", () => {
    // Bereshit = בְּרֵאשִׁית (Gen 1:1 opening).
    expect(romanize("בְּרֵאשִׁית")).toBe("breshit");
    // Bara = בָּרָא ("created").
    expect(romanize("בָּרָא")).toBe("bara");
    // Elohim = אֱלֹהִים — aleph silent, niqqud → e/o/i, mem at end.
    expect(romanize("אֱלֹהִים")).toBe("elohim");
  });

  it("strips cantillation marks", () => {
    // Same word with cantillation (te'amim) should romanize the
    // same as without — the marks are recitation guides, not
    // phonemic.
    expect(romanize("בְּרֵאשִׁ֖ית")).toBe("breshit");
    expect(romanize("בָּרָ֣א")).toBe("bara");
  });

  it("handles vav vowel modes (cholam / shuruq / consonantal)", () => {
    // Vav with cholam (וֹ) → "o".
    expect(romanize("אוֹר")).toBe("or");
    // Vav with shuruq (וּ) → "u".
    expect(romanize("רוּחַ")).toBe("rukha");
    // Bare vav between consonants → "v".
    expect(romanize("דָּוִד")).toBe("david");
  });

  it("distinguishes shin (ש with ׁ) from sin (ש with ׂ)", () => {
    // Shin (with shin-dot ׁ) → "sh".
    expect(romanize("שָׁלוֹם")).toBe("shalom");
    // Sin (with sin-dot ׂ) → "s".
    expect(romanize("יִשְׂרָאֵל")).toBe("yisrael");
  });

  it("collapses final-form letters to non-final equivalents", () => {
    // אָדָם uses final mem (ם).
    expect(romanize("אָדָם")).toBe("adam");
    // אֱלֹהִים — final mem.
    expect(romanize("אֱלֹהִים")).toBe("elohim");
    // מֶלֶךְ — final kaf (ך) without dagesh → "kh".
    expect(romanize("מֶלֶךְ")).toBe("melekh");
  });

  it("renders dageshed bet vs bare bet correctly", () => {
    // בָּ with dagesh → "b"; ב bare → "v".
    expect(romanize("בָּית")).toBe("bayt");
    // The Genesis word ברא starts with bet+dagesh+qamatz → "ba".
    expect(romanize("בָּרָא")).toBe("bara");
  });

  it("handles aleph and ayin as silent", () => {
    // אֲנִי — aleph silent, "ani".
    expect(romanize("אֲנִי")).toBe("ani");
    // עַם — ayin silent, "am".
    expect(romanize("עַם")).toBe("am");
  });

  it("passes empty / non-Hebrew input through unchanged", () => {
    expect(romanize("")).toBe("");
    expect(romanize("123")).toBe("123");
    expect(romanize("Genesis")).toBe("Genesis");
  });
});

describe("containsHebrew", () => {
  it("detects Hebrew script", () => {
    expect(containsHebrew("בראשית")).toBe(true);
    expect(containsHebrew("Gen 1:1 בראשית")).toBe(true);
  });
  it("rejects non-Hebrew text", () => {
    expect(containsHebrew("hello world")).toBe(false);
    expect(containsHebrew("ἀρχή")).toBe(false);
  });
});

describe("containsHebrew is a script test, not a combining-mark test (#367)", () => {
  it("rejects decomposed Latin", () => {
    expect(containsHebrew("Schröder".normalize("NFD"))).toBe(false);
  });

  it("rejects decomposed Greek", () => {
    // NFC Greek was already rejected — its accents are precomposed. NFD
    // Greek decomposes to base + Inherited mark, which tripped `\p{M}`.
    expect(containsHebrew("ἀρχή".normalize("NFD"))).toBe(false);
  });

  it("rejects vocalized Arabic", () => {
    expect(containsHebrew("مُحَمَّد")).toBe(false);
  });

  it("accepts pointed Hebrew in either normalization form", () => {
    // Hebrew points are themselves Script=Hebrew, unlike Greek accents
    // and Arabic harakat, so a mark-free regex still sees them.
    expect(containsHebrew("שָׁלוֹם".normalize("NFC"))).toBe(true);
    expect(containsHebrew("שָׁלוֹם".normalize("NFD"))).toBe(true);
  });
});
