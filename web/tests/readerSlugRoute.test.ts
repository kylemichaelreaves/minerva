import { describe, expect, it } from "vitest";
import { readRoute, routeHash, type Route } from "~/routing";

/** Readable reader URLs (#602): `#/r/<authorSlug>/<titleSlug>`.
 *
 *  The old shape put the raw TITLE in the path, so three encoders fired on one
 *  string and Kant arrived as
 *  `#/r/Beantwortung%20der%20Frage%3A%20Was%20ist%20Aufkl%C3%A4rung%3F`. */

function withHash<T>(hash: string, fn: () => T): T {
  const prior = window.location.hash;
  window.location.hash = hash;
  try {
    return fn();
  } finally {
    window.location.hash = prior;
  }
}

function reader(hash: string): Extract<Route, { kind: "reader" }> {
  const route = withHash(hash, readRoute);
  if (route.kind !== "reader") throw new Error(`expected a reader route, got ${route.kind}`);
  return route;
}

describe("parsing", () => {
  it("reads an author and a title out of a two-segment path", () => {
    const route = reader("#/r/kant/beantwortung-der-frage-was-ist-aufklarung?lang=deu");
    expect(route.authorSlug).toBe("kant");
    expect(route.workSlug).toBe("beantwortung-der-frage-was-ist-aufklarung");
    expect(route.sourceLang).toBe("deu");
  });

  it("accepts a single segment with no author", () => {
    // What a citation deep-link builds: it holds a title and a chunk, never an
    // author. The server resolves work and edition off `around=<chunk>`.
    const route = reader("#/r/nicomachean-ethics?focus=ne-1097b");
    expect(route.authorSlug).toBeUndefined();
    expect(route.workSlug).toBe("nicomachean-ethics");
    expect(route.focusChunkId).toBe("ne-1097b");
  });

  it("keeps every other reader parameter unchanged", () => {
    const route = reader("#/r/plato/republic?lang=grc&focus=rep-509d&term=42&syntax=rep-510a");
    expect(route.sourceLang).toBe("grc");
    expect(route.focusChunkId).toBe("rep-509d");
    expect(route.openTermId).toBe(42);
    expect(route.syntaxChunkId).toBe("rep-510a");
  });
});

describe("legacy shapes canonicalise on parse", () => {
  it("folds an old title-in-the-path bookmark to slugs", () => {
    // The old URL CONTAINS the title and the author, so this needs no
    // round-trip to resolve — which is why `Route.reader` can carry slugs only.
    const route = reader("#/r/Die%20fr%C3%B6hliche%20Wissenschaft?lang=deu&author=Nietzsche");
    expect(route.authorSlug).toBe("nietzsche");
    expect(route.workSlug).toBe("die-frohliche-wissenschaft");
  });

  it("folds an author-less old bookmark to a single segment", () => {
    const route = reader("#/r/Nicomachean%20Ethics?lang=eng");
    expect(route.authorSlug).toBeUndefined();
    expect(route.workSlug).toBe("nicomachean-ethics");
  });

  it("folds the legacy #/syntax/<chunk>?work=<Title> hash too", () => {
    const route = reader("#/syntax/rep-509d?work=Republic");
    expect(route.workSlug).toBe("republic");
    expect(route.syntaxChunkId).toBe("rep-509d");
    expect(route.focusChunkId).toBe("rep-509d");
  });
});

describe("serialising", () => {
  it("writes the pair as two path segments", () => {
    expect(routeHash({ kind: "reader", authorSlug: "kant", workSlug: "was-ist-aufklarung" })).toBe(
      "#/r/kant/was-ist-aufklarung",
    );
  });

  it("writes one segment when there is no author", () => {
    expect(routeHash({ kind: "reader", workSlug: "nicomachean-ethics" })).toBe(
      "#/r/nicomachean-ethics",
    );
  });

  it("no longer emits author= as a query parameter", () => {
    // The author moved into identity. Leaving it in the query as well would
    // give two sources of truth that a hand-edited URL could disagree on.
    const hash = routeHash({ kind: "reader", authorSlug: "plato", workSlug: "republic" });
    expect(hash).toBe("#/r/plato/republic");
    expect(hash).not.toContain("author=");
  });

  it("produces a URL with nothing percent-encoded in it", () => {
    const hash = routeHash({
      kind: "reader",
      authorSlug: "kant",
      workSlug: "beantwortung-der-frage-was-ist-aufklarung",
      sourceLang: "deu",
    });
    expect(hash).toBe("#/r/kant/beantwortung-der-frage-was-ist-aufklarung?lang=deu");
    expect(hash).not.toContain("%");
  });
});

describe("round trip", () => {
  const cases: Extract<Route, { kind: "reader" }>[] = [
    { kind: "reader", workSlug: "republic" },
    { kind: "reader", authorSlug: "plato", workSlug: "republic" },
    { kind: "reader", authorSlug: "plato", workSlug: "republic", sourceLang: "grc" },
    { kind: "reader", authorSlug: "plato", workSlug: "republic", focusChunkId: "rep-509d" },
    { kind: "reader", authorSlug: "plato", workSlug: "republic", openTermId: 42 },
    { kind: "reader", authorSlug: "plato", workSlug: "republic", syntaxChunkId: "rep-509d" },
    {
      kind: "reader",
      authorSlug: "kant",
      workSlug: "uber-den-gemeinspruch-das-mag-in-der-theorie-richtig-sein",
      sourceLang: "deu",
      focusChunkId: "k-1",
      openTermId: 7,
      syntaxChunkId: "k-2",
    },
  ];

  it.each(cases)("readRoute(routeHash(%o)) is the identity", (route) => {
    expect(withHash(routeHash(route), readRoute)).toEqual({
      openTermId: undefined,
      ...route,
    });
  });
});
