import { describe, it, expect } from "vitest";
import { romanize, containsArabic } from "~/utils/arabic";

describe("romanize (Arabic)", () => {
  it("transliterates Al-Fatihah 1:1 opening (Bismillah)", () => {
    // The Basmala: بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ
    // bi sm i (a)l lah i (a)l rahman i (a)l rahim i  ≈  "bismi llahi alrrahmani alrrahimi"
    // We accept the pragmatic shape: starts with "bismi", contains "llah",
    // and shadda doubles the lam / ra.
    const out = romanize("بِسْمِ");
    expect(out).toMatch(/^bismi$/);
  });

  it("doubles consonants when shadda is present", () => {
    // الرحيم with shadda on ra (ٱلرَّحِيمِ) → "llrrahimi" or similar.
    // Just verify the ra is doubled: contains "rr".
    expect(romanize("ٱلرَّحِيمِ")).toContain("rr");
    // ٱلرَّحْمَٰنِ also has shadda-ra'd.
    expect(romanize("ٱلرَّحْمَٰنِ")).toContain("rr");
  });

  it("renders alef wasla (ٱ) silently", () => {
    // ٱللَّهِ — the leading ٱ is the connecting alef; pronounced
    // 'llahi' in connected speech. We render it without the
    // initial vowel.
    expect(romanize("ٱللَّهِ").startsWith("l")).toBe(true);
  });

  it("transliterates Quran 36:1 opening (Ya-Sin)", () => {
    // يس — bare letters "ya sin" → "ys"; consonants only, no
    // tashkeel in this fragment. Pragmatic outcome: "ys".
    expect(romanize("يس")).toBe("ys");
  });

  it("handles tanwin (an / in / un)", () => {
    // كِتَابٌ — kitabun (an indefinite "book"). The tanwin damm (ـٌ)
    // on the final letter should render as "un".
    expect(romanize("كِتَابٌ")).toBe("kitabun");
    // عَلِيمٍ — alimin.
    expect(romanize("عَلِيمٍ")).toBe("alimin");
    // مَرْحَبًا — marhaban.
    expect(romanize("مَرْحَبًا")).toBe("marhaban");
  });

  it("folds emphatic letters into their plain equivalents", () => {
    // صَدْر — ṣadr → "sadr" (ṣad folded to s).
    expect(romanize("صَدْر")).toBe("sadr");
    // طَيِّب — ṭayyib → "tayyib" (ṭa folded to t).
    expect(romanize("طَيِّب")).toBe("tayyib");
  });

  it("renders ta marbuta (ة) as 'h' in pause form", () => {
    // مَكَّة — Makkah. Ta marbuta is the final letter.
    expect(romanize("مَكَّة")).toBe("makkah");
  });

  it("passes empty / non-Arabic input through unchanged", () => {
    expect(romanize("")).toBe("");
    expect(romanize("123")).toBe("123");
    expect(romanize("Quran")).toBe("Quran");
  });
});

describe("containsArabic", () => {
  it("detects Arabic script", () => {
    expect(containsArabic("بسم الله")).toBe(true);
    expect(containsArabic("Q 2:255 بسم")).toBe(true);
  });
  it("rejects non-Arabic text", () => {
    expect(containsArabic("hello world")).toBe(false);
    expect(containsArabic("בראשית")).toBe(false);
  });
});
