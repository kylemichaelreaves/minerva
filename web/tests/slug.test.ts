import { describe, expect, test } from "vitest";
import { slugify } from "~/slug";

// The Python half of this algorithm is `src/minerva/reader/slugs.py`. The two
// are pinned together by `data/authors/work_slugs.json`, asserted here and in
// `tests/test_work_slugs.py` — see `workSlugs.test.ts`.
describe("slugify", () => {
  test("lowercases and hyphenates ASCII", () => {
    expect(slugify("Nicomachean Ethics")).toBe("nicomachean-ethics");
  });

  test("strips combining marks after NFKD", () => {
    expect(slugify("Die fröhliche Wissenschaft")).toBe("die-frohliche-wissenschaft");
  });

  test("expands characters NFKD does not decompose", () => {
    expect(slugify("bloßen")).toBe("blossen");
    expect(slugify("Æsop")).toBe("aesop");
    expect(slugify("œuvre")).toBe("oeuvre");
    expect(slugify("Søren")).toBe("soren");
  });

  test("collapses runs of punctuation to one hyphen", () => {
    expect(slugify("Beantwortung der Frage: Was ist Aufklärung?")).toBe(
      "beantwortung-der-frage-was-ist-aufklarung",
    );
  });

  test("trims leading and trailing hyphens", () => {
    expect(slugify("  ...Leviathan!  ")).toBe("leviathan");
  });
});
