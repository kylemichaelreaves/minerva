// Characterization of the router across every route kind (#589).
//
// `readRoute` and `routeHash` are inverses over the CANONICAL route shape:
// the shape `readRoute` itself produces. Two invariants follow, and both are
// asserted here for every kind:
//
//   1. `readRoute(routeHash(r))` equals `r` for a canonical `r`, fully
//      populated AND bare — so every optional field is exercised on both
//      branches of its guard in `routeHash`.
//   2. For any hash `h` at all — canonical, legacy, malformed —
//      `routeHash(readRoute(h))` is a fixed point: parsing it again yields
//      the same route. That is what `useRouting`'s load-time replaceState
//      relies on to canonicalize a bookmark in one step.
//
// The table of raw hashes pins the parse of every legacy, redirect and
// defensive-fallback shape exactly, so a restructure of either function that
// reorders a match or drops a guard fails here rather than in the browser.
import { describe, expect, it } from "vitest";
import { readRoute, routeHash, type Route } from "~/routing";

function parse(hash: string): Route {
  const prev = window.location.hash;
  window.history.replaceState(null, "", hash || "#");
  try {
    return readRoute();
  } finally {
    window.history.replaceState(null, "", prev || "#");
  }
}

// Canonical routes: each kind fully populated, and each kind bare.
const canonical: [string, Route, string][] = [
  ["landing", { kind: "landing" }, "#/"],
  ["conversation", { kind: "conversation", id: "a b/c" }, "#/c/a%20b%2Fc"],
  [
    "reader, full",
    {
      kind: "reader",
      authorSlug: "plato",
      workSlug: "republic",
      sourceLang: "grc",
      focusChunkId: "rep-509d",
      openTermId: 7,
      syntaxChunkId: "rep-510a",
    },
    "#/r/plato/republic?lang=grc&focus=rep-509d&term=7&syntax=rep-510a",
  ],
  ["reader, bare", { kind: "reader", workSlug: "republic" }, "#/r/republic"],
  [
    "refs, full",
    {
      kind: "refs",
      sourceAuthor: "Aquinas",
      targetAuthor: "Aristotle",
      targetWork: "Nicomachean Ethics",
      referenceType: "quotes",
      includeRejected: true,
    },
    "#/refs?source=Aquinas&target=Aristotle&work=Nicomachean+Ethics&type=quotes&include_rejected=1",
  ],
  ["refs, bare", { kind: "refs", includeRejected: false }, "#/refs"],
  [
    "refs-review, full",
    { kind: "refs-review", sourceAuthor: "Augustine", referenceType: "alludes", referenceId: 12 },
    "#/refs/review?source=Augustine&type=alludes&id=12",
  ],
  ["refs-review, bare", { kind: "refs-review" }, "#/refs/review"],
  [
    "network, full",
    {
      kind: "network",
      minConfidence: 0.5,
      includeRejected: true,
      sourceAuthors: ["Hegel", "Marx, Karl"],
      corpora: ["de"],
      sourceMethods: ["rules"],
    },
    "#/network?min_confidence=0.5&include_rejected=1&source=Hegel%2CMarx%252C%2520Karl&corpus=de&method=rules",
  ],
  ["network, bare", { kind: "network", includeRejected: false }, "#/network"],
  [
    "network-arc, full",
    {
      kind: "network-arc",
      minConfidence: 0.25,
      sourceAuthors: ["Kant"],
      corpora: ["de", "la"],
      sourceMethods: ["llm"],
    },
    "#/network/arc?min_confidence=0.25&source=Kant&corpus=de%2Cla&method=llm",
  ],
  ["network-arc, bare", { kind: "network-arc" }, "#/network/arc"],
  [
    "network-coverage, full",
    {
      kind: "network-coverage",
      minConfidence: 1,
      sourceAuthors: ["Kant"],
      corpora: ["de"],
      sourceMethods: ["llm"],
    },
    "#/network/coverage?min_confidence=1&source=Kant&corpus=de&method=llm",
  ],
  ["network-coverage, bare", { kind: "network-coverage" }, "#/network/coverage"],
  [
    "concordance, full",
    {
      kind: "concordance",
      lang: "grc",
      scope: "work",
      scopeAuthors: ["Plato"],
      scopeWorks: ["Republic", "Laws"],
      letter: "a",
      sort: "alpha",
      pos: "NOUN",
      freqMin: 2,
      freqMax: 90,
      q: "log",
    },
    "#/concordance?lang=grc&scope=work&author=Plato&work=Republic%2CLaws&letter=a&sort=alpha&pos=NOUN&freq_min=2&freq_max=90&q=log",
  ],
  ["concordance, bare", { kind: "concordance" }, "#/concordance"],
  [
    "concordance-lemma, full",
    {
      kind: "concordance-lemma",
      lemma: "λόγος",
      lang: "grc",
      scope: "author",
      scopeAuthors: ["Plato"],
      scopeWorks: ["Republic"],
      caseFilter: "Gen",
      numberFilter: "Sing",
      surface: "λόγου",
    },
    "#/concordance/%CE%BB%CF%8C%CE%B3%CE%BF%CF%82?lang=grc&scope=author&author=Plato&work=Republic&case=Gen&number=Sing&surface=%CE%BB%CF%8C%CE%B3%CE%BF%CF%85",
  ],
  ["concordance-lemma, bare", { kind: "concordance-lemma", lemma: "esse" }, "#/concordance/esse"],
  [
    "metrics, full",
    { kind: "metrics", window: "7d", label: "GET /api/range" },
    "#/metrics?window=7d&label=GET+%2Fapi%2Frange",
  ],
  ["metrics, bare", { kind: "metrics" }, "#/metrics"],
];

describe("canonical routes round-trip in both directions", () => {
  for (const [name, route, hash] of canonical) {
    it(`${name}: routeHash emits the canonical hash`, () => {
      expect(routeHash(route)).toBe(hash);
    });
    it(`${name}: readRoute(routeHash(r)) equals r`, () => {
      expect(parse(routeHash(route))).toEqual(route);
    });
  }
});

// Raw hashes → the exact route they parse to. Legacy, redirect and
// defensive-fallback shapes; each is also checked for invariant 2.
const LANDING: Route = { kind: "landing" };
const raw: [string, Route][] = [
  ["", LANDING],
  ["#/", LANDING],
  ["#/nowhere", LANDING],
  ["#/c/100%", LANDING],
  ["#/c/a/b", LANDING],
  // Reader: author in the path, legacy author in the query, raw titles.
  [
    "#/r/Die%20fr%C3%B6hliche%20Wissenschaft?author=Nietzsche",
    { kind: "reader", authorSlug: "nietzsche", workSlug: "die-frohliche-wissenschaft" },
  ],
  ["#/r/Plato/Republic", { kind: "reader", authorSlug: "plato", workSlug: "republic" }],
  ["#/r/100%", LANDING],
  ["#/r/plato/100%", LANDING],
  ["#/r/republic?term=abc", { kind: "reader", workSlug: "republic" }],
  // Legacy #/syntax/ → reader with the syntax modifier.
  [
    "#/syntax/rep-509d?work=Republic",
    {
      kind: "reader",
      workSlug: "republic",
      focusChunkId: "rep-509d",
      syntaxChunkId: "rep-509d",
    },
  ],
  ["#/syntax/rep-509d", LANDING],
  ["#/syntax/100%?work=Republic", LANDING],
  ["#/syntax/rep-509d?work=100%25", LANDING],
  // Network drilldowns come before the bare network match.
  ["#/network/arc?min_confidence=high", { kind: "network-arc" }],
  ["#/network/coverage?min_confidence=0.9", { kind: "network-coverage", minConfidence: 0.9 }],
  ["#/network/other", LANDING],
  [
    "#/network?min_confidence=x&include_rejected=yes&source=,,A",
    { kind: "network", includeRejected: false, sourceAuthors: ["A"] },
  ],
  ["#/network?source=100%25", { kind: "network", includeRejected: false, sourceAuthors: ["100%"] }],
  // Metrics: an unknown window is dropped, the label kept.
  ["#/metrics?window=forever&label=x", { kind: "metrics", label: "x" }],
  // refs/review comes before refs.
  ["#/refs/review?id=abc&source=A", { kind: "refs-review", sourceAuthor: "A" }],
  ["#/refs?include_rejected=0", { kind: "refs", includeRejected: false }],
  // Concordance lemma before bare concordance; bad enum/number values drop.
  ["#/concordance/100%", LANDING],
  ["#/concordance/esse?scope=galaxy", { kind: "concordance-lemma", lemma: "esse" }],
  ["#/concordance?scope=everything&sort=random&freq_min=-1&freq_max=1.5", { kind: "concordance" }],
  ["#/concordance?scope=corpus&sort=pos", { kind: "concordance", scope: "corpus", sort: "pos" }],
  ["#/concordance?scope=author&sort=freq", { kind: "concordance", scope: "author", sort: "freq" }],
  ["#/concordance/esse?scope=work", { kind: "concordance-lemma", lemma: "esse", scope: "work" }],
  [
    "#/concordance/esse?scope=corpus",
    { kind: "concordance-lemma", lemma: "esse", scope: "corpus" },
  ],
];

describe("raw hashes parse exactly and canonicalize to a fixed point", () => {
  for (const [hash, expected] of raw) {
    it(`parses ${JSON.stringify(hash)}`, () => {
      expect(parse(hash)).toEqual(expected);
    });
    it(`${JSON.stringify(hash)} canonicalizes in one step`, () => {
      const once = parse(hash);
      expect(parse(routeHash(once))).toEqual(once);
    });
  }
});

describe("routeHash omission rules", () => {
  it("drops an empty string, an empty list and a false flag", () => {
    expect(routeHash({ kind: "refs", sourceAuthor: "", includeRejected: false })).toBe("#/refs");
    expect(routeHash({ kind: "network", sourceAuthors: [], includeRejected: false })).toBe(
      "#/network",
    );
  });

  it("keeps a zero-valued number, which a truthiness check would drop", () => {
    expect(routeHash({ kind: "network-arc", minConfidence: 0 })).toBe(
      "#/network/arc?min_confidence=0",
    );
    expect(routeHash({ kind: "reader", workSlug: "republic", openTermId: 0 })).toBe(
      "#/r/republic?term=0",
    );
  });
});
