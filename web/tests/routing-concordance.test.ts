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
});
