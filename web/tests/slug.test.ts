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

// Regression guard for the trim's shape, not just its result. The trim used
// to be `/^-+|-+$/g`, which SonarQube failed the build on as super-linear:
// `-+$` backtracks through every length at every start position, so a title
// that folds to a long run of hyphens is quadratic. The replacement walks the
// string once from each end, mirroring Python's `str.strip("-")`.
describe("trimming is linear and total", () => {
  test("a title with no slug characters at all collapses to the empty string", () => {
    expect(slugify("——— ... ———")).toBe("");
  });

  test("a long run of separators does not blow up", () => {
    const start = Date.now();
    expect(slugify(`${"-".repeat(50_000)}a${"-".repeat(50_000)}`)).toBe("a");
    expect(Date.now() - start).toBeLessThan(1_000);
  });

  test("interior hyphens survive", () => {
    expect(slugify("--a-b--")).toBe("a-b");
  });
});
