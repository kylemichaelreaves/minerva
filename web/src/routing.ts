// Hash-based router. `#/` is the landing; `#/c/<id>` is an open
// conversation; `#/r/<work>?lang=gr` is the primary-source reader
// for one work.
//
// Pathname-based routing is intentionally avoided so the app keeps
// working when served from a subpath (e.g. `minerva serve` behind a
// reverse proxy).

import { createSignal, onCleanup, onMount } from "solid-js";
import { METRIC_WINDOWS, type MetricWindow } from "~/api/metricsApi";
import { slugify } from "~/slug";

export type Route =
  | { kind: "landing" }
  | { kind: "conversation"; id: string }
  | {
      kind: "reader";
      /** URL slug of the work's title (#602). NOT the title: the route
       *  carries `die-frohliche-wissenschaft`, and the canonical
       *  `Die fröhliche Wissenschaft` arrives with the range response.
       *
       *  The title used to be the path segment, which meant three encoders
       *  fired on one string and the URL was unreadable and untypeable. */
      workSlug: string;
      sourceLang?: string;
      /** URL slug of the author, when known. Part of identity rather than a
       *  `?author=` hint, because that is what disambiguates same-titled
       *  works (Luther 1912 vs 1545 share every book title AND lang).
       *
       *  Optional because a citation deep-link carries a title and a chunk
       *  but no author; the server resolves that off `around=<chunk>`, and
       *  the Reader canonicalises the URL once the response names the
       *  author. */
      authorSlug?: string;
      focusChunkId?: string;
      /** Term-card open state. When set, the Reader resumes the
       *  popover for this term on next paint — used so a click on a
       *  marked Greek word is routable and survives a page reload. */
      openTermId?: number;
      /** Dependency-syntax layer open over this chunk (`?syntax=<id>`).
       *
       *  A MODIFIER on the reader route, not a route of its own (#342).
       *  The overlay used to be a peer `<Match>` in the same `<Switch>`
       *  as the Reader, which meant opening it unmounted the Reader:
       *  `useWorkRange`'s signals were destroyed, the window refetched,
       *  and the return trip blanked the page and lost the scroll
       *  position. As a modifier the reader location stays resolved, so
       *  the Reader stays mounted and the overlay is what it always
       *  looked like — a layer (`.syn` is `position: fixed; inset: 0`).
       *
       *  The legacy `#/syntax/<chunk>?work=<work>` hash parses into this
       *  shape, so existing bookmarks keep working and get canonicalized
       *  on load by `useRouting`'s replaceState. */
      syntaxChunkId?: string;
    }
  | {
      /** Corpus-wide cross-references browser. Mirrors the
       *  `/api/references` filter shape — every query parameter is
       *  optional, and absence means "no filter on this axis." The
       *  route is linkable + bookmarkable.
       *
       *  `targetWork` is only set via deep-link URLs today; there's
       *  no work picker in the FiltersBar yet (would require a
       *  dependent author→work dropdown). Bookmarks like
       *  `#/refs?target=Aristotle&work=Nicomachean+Ethics` work fine. */
      kind: "refs";
      sourceAuthor?: string;
      targetAuthor?: string;
      targetWork?: string;
      referenceType?: string;
      includeRejected?: boolean;
    }
  | {
      /** Curator review queue. Iterates `curator_status='auto'`
       *  rows lowest-confidence first so the reviewer triages the
       *  borderline cases first. Optional filters narrow the queue
       *  to a single source author or reference type. */
      kind: "refs-review";
      sourceAuthor?: string;
      referenceType?: string;
      /** Reference id under review. Encoded as `?id=<n>` so the queue
       *  is bookmarkable / shareable / refresh-stable; without this
       *  the local `cursor` signal alone reset to 0 on every reload.
       *  The Review component resolves this back to a queue cursor on
       *  load, falls back to cursor 0 when missing, and updates the
       *  URL via `replace` (not `push`) on advance so the back button
       *  doesn't cycle through every reviewed reference. */
      referenceId?: number;
    }
  | {
      /** Citation-network dashboard. One-screen visualization of
       *  the corpus's cross-reference graph: author×author matrix,
       *  chronological arc diagram, scripture heatmap, verification
       *  coverage, top-cited works. All five panels cross-filter
       *  off the same set of header chips, encoded as URL params
       *  so the slice is bookmarkable. Multi-select chips serialize
       *  as comma-separated lists. */
      kind: "network";
      minConfidence?: number;
      includeRejected?: boolean;
      sourceAuthors?: string[];
      corpora?: string[];
      sourceMethods?: string[];
    }
  | {
      /** Full-screen chronological-arc drilldown — design 5b.
       *  Reached from the network footer link on mobile. Shares the
       *  network's filter shape so the same filter chip strip can be
       *  rendered. */
      kind: "network-arc";
      minConfidence?: number;
      includeRejected?: boolean;
      sourceAuthors?: string[];
      corpora?: string[];
      sourceMethods?: string[];
    }
  | {
      /** Full-screen verification-coverage drilldown — design 6.
       *  Per-author stacked bars (verified / unverified / disputed).
       *  Same filter shape as `network`. */
      kind: "network-coverage";
      minConfidence?: number;
      includeRejected?: boolean;
      sourceAuthors?: string[];
      corpora?: string[];
      sourceMethods?: string[];
    }
  | {
      /** Concordance index — lemma frequency leaderboard. Top-nav
       *  entry point. Scope-picker drives whether the data is corpus,
       *  author, or work-scoped. Sort + letter-filter are bookmarkable.
       *
       *  `pos`, `freqMin`, `freqMax`, and `q` were added with the
       *  filter-bar redesign — POS dropdown narrows by UD tag, the
       *  freq-range slider clamps the leaderboard to a window, and
       *  the search field substring-matches the lemma. */
      kind: "concordance";
      lang?: string;
      scope?: "corpus" | "author" | "work";
      scopeAuthors?: string[];
      scopeWorks?: string[];
      letter?: string;
      sort?: "freq" | "alpha" | "pos";
      pos?: string;
      freqMin?: number;
      freqMax?: number;
      q?: string;
    }
  | {
      /** Concordance lemma detail — KWIC grid for one lemma in scope.
       *  ``lemma`` is the URL-encoded lemma string from the lemma cache. */
      kind: "concordance-lemma";
      lemma: string;
      lang?: string;
      scope?: "corpus" | "author" | "work";
      scopeAuthors?: string[];
      scopeWorks?: string[];
      caseFilter?: string;
      numberFilter?: string;
      surface?: string;
    }
  | {
      /** Request-timing observability dashboard (#581). Bare `#/metrics`
       *  shows the whole-request leaderboard, slowest first; `label`
       *  drills into one route's sub-span breakdown + trend chart.
       *  `window` is one of `METRIC_WINDOWS` — an unrecognized value
       *  (a stale bookmark, a hand-edited hash) is dropped rather than
       *  passed through, so the panel falls back to its own default
       *  instead of rendering a broken selector. */
      kind: "metrics";
      window?: MetricWindow;
      label?: string;
    };

/** Decode one percent-encoded path segment defensively. Malformed
 *  encoding (e.g. a truncated `#/c/100%`) makes decodeURIComponent
 *  throw URIError, which would blank-screen the whole app from the
 *  router. Returns null on failure so callers can fall back to the
 *  landing route — same defensive posture as the `term=` parse below. */
const safeDecode = (s: string): string | null => {
  try {
    return decodeURIComponent(s);
  } catch {
    return null;
  }
};

/** Multi-select params (network filter chips) serialize as CSV.
 *  Each component is percent-encoded before joining so a comma INSIDE
 *  a value (corpus labels, author names) round-trips instead of
 *  splitting the value in two on the next parse. */
const encodeCsv = (vals: string[]): string => vals.map(encodeURIComponent).join(",");
const decodeCsv = (raw: string | null): string[] | undefined =>
  raw === null
    ? undefined
    : raw
        .split(",")
        .filter(Boolean)
        .map((s) => safeDecode(s) ?? s);

// ─── Parsing ──────────────────────────────────────────────────────────────
//
// `readRoute` is a table, not a ladder (#589). The ladder it replaced scored
// 44 on Sonar's cognitive-complexity metric against a limit of 15, and grew
// by a branch with every surface. Each surface is now one `RouteRule`: a
// regex, and a `build` that turns the match into a route.
//
// The first rule whose regex matches wins. Today no hash can match two rules:
// every general shape demands `?` or end-of-hash straight after its literal,
// so `#/network/arc` cannot fall into `#/network`, nor `#/refs/review` into
// `#/refs`, nor `#/concordance/<lemma>` into `#/concordance`. The table keeps
// the specific shape first anyway, so that loosening one of those regexes
// cannot silently re-route the drilldown. A query string, where a shape has
// one, is captured by the named group `q` and handed to `build` parsed.

interface RouteRule {
  re: RegExp;
  build: (m: RegExpExecArray, qs: URLSearchParams) => Route;
}

const LANDING: Route = { kind: "landing" };

/** A query parameter, with absence as `undefined` rather than `null`. */
const opt = (qs: URLSearchParams, key: string): string | undefined => qs.get(key) ?? undefined;

/** A non-negative integer parameter (`term=`, `id=`, `freq_min=`). Anything
 *  else — a stale bookmark, a hand-edited hash — is dropped rather than
 *  carried through as NaN. */
const optDigits = (qs: URLSearchParams, key: string): number | undefined => {
  const raw = qs.get(key);
  return raw !== null && /^\d+$/.test(raw) ? Number(raw) : undefined;
};

/** `min_confidence=`, shared by the network dashboard and its drilldowns. */
const optConfidence = (qs: URLSearchParams): number | undefined => {
  const raw = qs.get("min_confidence");
  return raw !== null && /^[0-9.]+$/.test(raw) ? Number(raw) : undefined;
};

/** A parameter restricted to a fixed set of values; anything else drops. */
const optOneOf = <T extends string>(
  qs: URLSearchParams,
  key: string,
  allowed: readonly T[],
): T | undefined => {
  const raw = qs.get(key);
  return (allowed as readonly (string | null)[]).includes(raw) ? (raw as T) : undefined;
};

const SCOPES = ["corpus", "author", "work"] as const;
const SORTS = ["freq", "alpha", "pos"] as const;

/** The filter chips the network dashboard and both drilldowns share. */
const networkFilters = (qs: URLSearchParams) => ({
  minConfidence: optConfidence(qs),
  includeRejected: qs.get("include_rejected") === "1",
  sourceAuthors: decodeCsv(qs.get("source")),
  corpora: decodeCsv(qs.get("corpus")),
  sourceMethods: decodeCsv(qs.get("method")),
});

/** `#/r/<authorSlug>/<titleSlug>` — and every shape that folds into it.
 *
 *  Kept as its own named function rather than inlined into the table (#602):
 *  it is the densest parse, and scores on its own. A reader hash that cannot
 *  be decoded returns the landing route, same defensive posture as the rest
 *  of `readRoute`. */
function buildReaderRoute(m: RegExpExecArray, qs: URLSearchParams): Route {
  const first = safeDecode(m[1] ?? "");
  const second = m[2] === undefined ? undefined : safeDecode(m[2]);
  if (first === null || second === null) return LANDING;
  // One segment is the title, two are author-then-title, and an OLD bookmark
  // holds the raw title in that same position with the author in `?author=`.
  // `slugify` is idempotent on a slug, so all three fold through one pair of
  // calls and the Reader never sees a second route shape — the address bar is
  // then rewritten to the canonical form by `useRouting`'s first-load
  // `replaceState`, exactly as the legacy `#/syntax/` hash already is.
  const rawAuthor = second === undefined ? qs.get("author") : first;
  return {
    kind: "reader",
    authorSlug: rawAuthor ? slugify(rawAuthor) : undefined,
    workSlug: slugify(second ?? first),
    sourceLang: opt(qs, "lang"),
    focusChunkId: opt(qs, "focus"),
    // Parsed defensively — a bad value (e.g. a stale bookmark) shouldn't
    // break the reader; it just means no card opens on first paint.
    openTermId: optDigits(qs, "term"),
    syntaxChunkId: opt(qs, "syntax"),
  };
}

/** Legacy syntax hash (#237's shape). Rewritten into the reader route with
 *  the syntax modifier — see `syntaxChunkId` above. The chunk goes through as
 *  `focus=` as well because this hash carries no lang: `around=<chunk>` makes
 *  the server resolve work/lang/edition off the chunk row, where defaulting a
 *  lang (as `work_range` does, to "grc") can open a different edition of the
 *  same work. Without a `work=` there is no reader location to resolve and so
 *  no layer to lay the overlay over, which lands on the landing route. */
function buildLegacySyntaxRoute(m: RegExpExecArray, qs: URLSearchParams): Route {
  const rawWork = qs.get("work");
  const workId = rawWork ? safeDecode(rawWork) : null;
  const chunkId = safeDecode(m[1] ?? "");
  if (workId === null || chunkId === null) return LANDING;
  return {
    kind: "reader",
    workSlug: slugify(workId),
    focusChunkId: chunkId,
    syntaxChunkId: chunkId,
  };
}

const isKnownWindow = (v: string | null): v is MetricWindow =>
  (METRIC_WINDOWS as readonly (string | null)[]).includes(v);

const ROUTE_RULES: readonly RouteRule[] = [
  {
    re: /^#\/c\/([^/?]+)$/,
    build: (m) => {
      const id = safeDecode(m[1] ?? "");
      return id === null ? LANDING : { kind: "conversation", id };
    },
  },
  { re: /^#\/r\/([^/?]+)(?:\/([^/?]+))?(?:\?(?<q>.*))?$/, build: buildReaderRoute },
  { re: /^#\/syntax\/([^?]+)(?:\?(?<q>.*))?$/, build: buildLegacySyntaxRoute },
  // Drilldowns BEFORE the bare network route.
  {
    re: /^#\/network\/(arc|coverage)(?:\?(?<q>.*))?$/,
    build: (m, qs) =>
      m[1] === "arc"
        ? { kind: "network-arc", ...networkFilters(qs) }
        : { kind: "network-coverage", ...networkFilters(qs) },
  },
  {
    re: /^#\/network(?:\?(?<q>.*))?$/,
    build: (_m, qs) => ({
      kind: "network",
      ...networkFilters(qs),
    }),
  },
  {
    re: /^#\/metrics(?:\?(?<q>.*))?$/,
    build: (_m, qs) => {
      // Reject an unrecognized window rather than carrying it through —
      // a stale bookmark or a hand-edited hash otherwise reaches the
      // panel as a value outside `METRIC_WINDOWS`, which is exactly the
      // "broken page" this guard exists to avoid.
      const rawWindow = qs.get("window");
      return {
        kind: "metrics",
        window: isKnownWindow(rawWindow) ? rawWindow : undefined,
        label: opt(qs, "label"),
      };
    },
  },
  // Review queue BEFORE the refs browser.
  {
    re: /^#\/refs\/review(?:\?(?<q>.*))?$/,
    build: (_m, qs) => ({
      kind: "refs-review",
      sourceAuthor: opt(qs, "source"),
      referenceType: opt(qs, "type"),
      referenceId: optDigits(qs, "id"),
    }),
  },
  // Lemma detail BEFORE the leaderboard.
  {
    re: /^#\/concordance\/([^?]+)(?:\?(?<q>.*))?$/,
    build: (m, qs) => {
      const lemma = safeDecode(m[1] ?? "");
      if (lemma === null) return LANDING;
      return {
        kind: "concordance-lemma",
        lemma,
        lang: opt(qs, "lang"),
        scope: optOneOf(qs, "scope", SCOPES),
        scopeAuthors: decodeCsv(qs.get("author")),
        scopeWorks: decodeCsv(qs.get("work")),
        caseFilter: opt(qs, "case"),
        numberFilter: opt(qs, "number"),
        surface: opt(qs, "surface"),
      };
    },
  },
  {
    re: /^#\/concordance(?:\?(?<q>.*))?$/,
    build: (_m, qs) => ({
      kind: "concordance",
      lang: opt(qs, "lang"),
      scope: optOneOf(qs, "scope", SCOPES),
      scopeAuthors: decodeCsv(qs.get("author")),
      scopeWorks: decodeCsv(qs.get("work")),
      letter: opt(qs, "letter"),
      sort: optOneOf(qs, "sort", SORTS),
      pos: opt(qs, "pos"),
      freqMin: optDigits(qs, "freq_min"),
      freqMax: optDigits(qs, "freq_max"),
      q: opt(qs, "q"),
    }),
  },
  {
    re: /^#\/refs(?:\?(?<q>.*))?$/,
    build: (_m, qs) => ({
      kind: "refs",
      sourceAuthor: opt(qs, "source"),
      targetAuthor: opt(qs, "target"),
      targetWork: opt(qs, "work"),
      referenceType: opt(qs, "type"),
      includeRejected: qs.get("include_rejected") === "1",
    }),
  },
];

export function readRoute(): Route {
  const hash = window.location.hash;
  for (const rule of ROUTE_RULES) {
    const m = rule.re.exec(hash);
    // URLSearchParams accepts undefined and treats it as an empty query
    // string, so a hash with no `?` needs no explicit fallback.
    if (m) return rule.build(m, new URLSearchParams(m.groups?.q));
  }
  return LANDING;
}

// ─── Serializing ──────────────────────────────────────────────────────────
//
// The inverse, as a map from kind to serializer (#589) — the if-chain it
// replaced scored 109. Every serializer lists its parameters as
// `[key, value]` pairs in a fixed order, and `withQuery` drops the ones whose
// value is `undefined`; the `q*` helpers encode each guard the old chain
// spelled out per field (a string is omitted when empty, a number only when
// absent so `0` survives, a list when empty, a flag when false).

type QueryPair = readonly [string, string | undefined];

const qText = (v: string | undefined): string | undefined => (v === "" ? undefined : v);
const qNum = (v: number | undefined): string | undefined =>
  v === undefined ? undefined : String(v);
const qCsv = (v: string[] | undefined): string | undefined =>
  v?.length ? encodeCsv(v) : undefined;
const qFlag = (v: boolean | undefined): string | undefined => (v ? "1" : undefined);

function withQuery(base: string, pairs: readonly QueryPair[]): string {
  const params = new URLSearchParams();
  for (const [key, value] of pairs) {
    if (value !== undefined) params.set(key, value);
  }
  const qs = params.toString();
  return qs ? `${base}?${qs}` : base;
}

type RouteOf<K extends Route["kind"]> = Extract<Route, { kind: K }>;
type NetworkFilters = Pick<
  RouteOf<"network-arc">,
  "minConfidence" | "includeRejected" | "sourceAuthors" | "corpora" | "sourceMethods"
>;

/** The shared network filters as query pairs, for the dashboard and both
 *  drilldowns alike. The drilldowns used to drop `include_rejected`, so a
 *  drilldown counted a different slice from the dashboard that opened it,
 *  and Back lost the toggle (#891). It sits between `min_confidence` and the
 *  chips because that is the parameter order the dashboard has always
 *  emitted. */
const networkPairs = (r: NetworkFilters): QueryPair[] => [
  ["min_confidence", qNum(r.minConfidence)],
  ["include_rejected", qFlag(r.includeRejected)],
  ["source", qCsv(r.sourceAuthors)],
  ["corpus", qCsv(r.corpora)],
  ["method", qCsv(r.sourceMethods)],
];

const SERIALIZERS: { [K in Route["kind"]]: (r: RouteOf<K>) => string } = {
  landing: () => "#/",
  conversation: (r) => `#/c/${encodeURIComponent(r.id)}`,
  reader: (r) =>
    // Slugs are `[a-z0-9-]` by construction, so `encodeURIComponent` is the
    // identity here; it stays as a guard against a non-slug ever reaching
    // this path, not because anything needs escaping.
    withQuery(
      r.authorSlug
        ? `#/r/${encodeURIComponent(r.authorSlug)}/${encodeURIComponent(r.workSlug)}`
        : `#/r/${encodeURIComponent(r.workSlug)}`,
      [
        ["lang", qText(r.sourceLang)],
        ["focus", qText(r.focusChunkId)],
        ["term", qNum(r.openTermId)],
        ["syntax", qText(r.syntaxChunkId)],
      ],
    ),
  refs: (r) =>
    withQuery("#/refs", [
      ["source", qText(r.sourceAuthor)],
      ["target", qText(r.targetAuthor)],
      ["work", qText(r.targetWork)],
      ["type", qText(r.referenceType)],
      ["include_rejected", qFlag(r.includeRejected)],
    ]),
  "refs-review": (r) =>
    withQuery("#/refs/review", [
      ["source", qText(r.sourceAuthor)],
      ["type", qText(r.referenceType)],
      ["id", qNum(r.referenceId)],
    ]),
  network: (r) => withQuery("#/network", networkPairs(r)),
  "network-arc": (r) => withQuery("#/network/arc", networkPairs(r)),
  "network-coverage": (r) => withQuery("#/network/coverage", networkPairs(r)),
  concordance: (r) =>
    withQuery("#/concordance", [
      ["lang", qText(r.lang)],
      ["scope", qText(r.scope)],
      ["author", qCsv(r.scopeAuthors)],
      ["work", qCsv(r.scopeWorks)],
      ["letter", qText(r.letter)],
      ["sort", qText(r.sort)],
      ["pos", qText(r.pos)],
      ["freq_min", qNum(r.freqMin)],
      ["freq_max", qNum(r.freqMax)],
      ["q", qText(r.q)],
    ]),
  "concordance-lemma": (r) =>
    withQuery(`#/concordance/${encodeURIComponent(r.lemma)}`, [
      ["lang", qText(r.lang)],
      ["scope", qText(r.scope)],
      ["author", qCsv(r.scopeAuthors)],
      ["work", qCsv(r.scopeWorks)],
      ["case", qText(r.caseFilter)],
      ["number", qText(r.numberFilter)],
      ["surface", qText(r.surface)],
    ]),
  metrics: (r) =>
    withQuery("#/metrics", [
      ["window", qText(r.window)],
      ["label", qText(r.label)],
    ]),
};

export function routeHash(route: Route): string {
  // The map is total over `Route["kind"]`, so the lookup always succeeds;
  // the cast only tells TS that `route` matches the serializer it selects,
  // which it cannot correlate through an indexed access on its own.
  const serialize = SERIALIZERS[route.kind] as (r: Route) => string;
  return serialize(route);
}

export interface RoutingApi {
  route: () => Route;
  navigate: (r: Route) => void;
  /** Update the route in place — uses history.replaceState instead
   *  of pushState, so the back button doesn't accumulate intermediate
   *  states. Used for fine-grained per-item URL tracking (e.g. the
   *  curator review queue advancing to the next reference) where
   *  every cursor change shouldn't become a separate history entry. */
  replace: (r: Route) => void;
}

export function useRouting(): RoutingApi {
  const initial = readRoute();
  const [route, setRoute] = createSignal<Route>(initial);

  // Canonicalize the URL on first load. A non-canonical hash (extra
  // params, malformed encoding, Firefox's decoded `location.hash`)
  // parses fine, but the address bar should show the serialized form.
  // replaceState — never push — so the back button still leaves the
  // app instead of bouncing through a synthetic entry.
  const initialHash = routeHash(initial);
  if (window.location.hash !== initialHash) {
    window.history.replaceState(null, "", initialHash);
  }

  // History writes happen ONLY here (and in `replace` below) — never
  // from an effect watching the signal. A write-from-effect turned
  // every externally-triggered signal change (including popstate
  // itself) into a fresh pushState, trapping the back button.
  //
  // The no-op guard compares parsed routes re-serialized through
  // routeHash rather than raw hash strings: Firefox returns
  // `location.hash` percent-DECODED, so a raw comparison would push a
  // duplicate entry for any route with encoded characters.
  const navigate = (r: Route): void => {
    const target = routeHash(r);
    if (routeHash(readRoute()) !== target) {
      window.history.pushState(null, "", target);
    }
    setRoute(r);
  };

  const replace = (r: Route): void => {
    const target = routeHash(r);
    if (routeHash(readRoute()) !== target) {
      window.history.replaceState(null, "", target);
    }
    setRoute(r);
  };

  // Re-derive route state from the URL whenever something outside our
  // `navigate()` path changed it. These handlers only READ the URL
  // into the signal — no history writes — so back/forward walk the
  // stack cleanly. Two events to cover both shapes:
  //   * `popstate` — back/forward navigation.
  //   * `hashchange` — in-page anchor clicks (<a href="#/c/...">), the
  //     user manually editing the hash, browser extensions, and any
  //     other path that mutates `location.hash` without going through
  //     `history.pushState`. Without this, those fragment-only
  //     navigations would leave the route signal out of sync with the
  //     URL and the UI stuck on the wrong screen.
  onMount(() => {
    const handler = () => setRoute(readRoute());
    window.addEventListener("popstate", handler);
    window.addEventListener("hashchange", handler);
    onCleanup(() => {
      window.removeEventListener("popstate", handler);
      window.removeEventListener("hashchange", handler);
    });
  });

  return { route, navigate, replace };
}
