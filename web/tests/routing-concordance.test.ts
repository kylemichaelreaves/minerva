import { afterEach, describe, expect, it } from "vitest";
import { readRoute, routeHash } from "~/routing";
import { mergeRoutePatchAllowClear } from "~/routes/routeUtils";

describe("concordance routing", () => {
  afterEach(() => {
    window.location.hash = "#/";
  });

  it("parses concordance hash", () => {
    window.location.hash = "#/concordance?lang=deu&scope=corpus&sort=freq";
    const r = readRoute();
    expect(r.kind).toBe("concordance");
    if (r.kind !== "concordance") return;
    expect(r.lang).toBe("deu");
    expect(r.scope).toBe("corpus");
    expect(r.sort).toBe("freq");
  });

  it("mergeRoutePatchAllowClear clears letter", () => {
    const base = {
      kind: "concordance" as const,
      lang: "deu",
      letter: "A",
    };
    const out = mergeRoutePatchAllowClear(base, {
      letter: undefined,
    }) as Record<string, unknown>;
    expect("letter" in out && out.letter === undefined).toBe(true);
  });

  it("round-trips concordance route hash", () => {
    const r = {
      kind: "concordance" as const,
      lang: "deu",
      scope: "corpus" as const,
      sort: "freq" as const,
    };
    const hash = routeHash(r);
    window.location.hash = hash;
    const parsed = readRoute();
    expect(parsed.kind).toBe("concordance");
  });

  it("round-trips multiple works in scopeWorks (comma-safe)", () => {
    // A work title containing a comma must survive the CSV encode/decode
    // round-trip rather than splitting into two phantom works.
    const r = {
      kind: "concordance" as const,
      lang: "deu",
      scope: "work" as const,
      scopeWorks: ["Kritik der reinen Vernunft", "Sein, Zeit"],
    };
    const hash = routeHash(r);
    window.location.hash = hash;
    const parsed = readRoute();
    expect(parsed.kind).toBe("concordance");
    if (parsed.kind !== "concordance") return;
    expect(parsed.scope).toBe("work");
    expect(parsed.scopeWorks).toEqual(["Kritik der reinen Vernunft", "Sein, Zeit"]);
  });

  it("round-trips multiple works on the lemma route", () => {
    const r = {
      kind: "concordance-lemma" as const,
      lemma: "Geist",
      lang: "deu",
      scope: "work" as const,
      scopeWorks: ["Kritik der reinen Vernunft", "Phänomenologie des Geistes"],
    };
    const hash = routeHash(r);
    window.location.hash = hash;
    const parsed = readRoute();
    expect(parsed.kind).toBe("concordance-lemma");
    if (parsed.kind !== "concordance-lemma") return;
    expect(parsed.scopeWorks).toEqual([
      "Kritik der reinen Vernunft",
      "Phänomenologie des Geistes",
    ]);
  });

  it("round-trips multiple authors in scopeAuthors (comma-safe)", () => {
    // An author name containing a comma must survive the CSV
    // encode/decode round-trip rather than splitting into two phantoms.
    const r = {
      kind: "concordance" as const,
      lang: "deu",
      scope: "author" as const,
      scopeAuthors: ["Kant", "Hegel, G.W.F."],
    };
    const hash = routeHash(r);
    window.location.hash = hash;
    const parsed = readRoute();
    expect(parsed.kind).toBe("concordance");
    if (parsed.kind !== "concordance") return;
    expect(parsed.scope).toBe("author");
    expect(parsed.scopeAuthors).toEqual(["Kant", "Hegel, G.W.F."]);
  });

  it("round-trips multiple authors on the lemma route", () => {
    const r = {
      kind: "concordance-lemma" as const,
      lemma: "Geist",
      lang: "deu",
      scope: "author" as const,
      scopeAuthors: ["Kant", "Hegel"],
    };
    const hash = routeHash(r);
    window.location.hash = hash;
    const parsed = readRoute();
    expect(parsed.kind).toBe("concordance-lemma");
    if (parsed.kind !== "concordance-lemma") return;
    expect(parsed.scopeAuthors).toEqual(["Kant", "Hegel"]);
  });
});
