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

/** `#/r/<authorSlug>/<titleSlug>` — and every shape that folds into it.
 *
 *  Extracted from `readRoute` rather than written inline (#602). `readRoute`
 *  is already past the cognitive-complexity limit that gates new code (#589),
 *  and the rating applies to lines that MOVE as well as lines that are added,
 *  so growing its reader branch in place would have handed this change
 *  #589's problem. As its own function the parse scores on its own.
 *
 *  Returns `null` when the hash is not a reader hash at all, so the caller can
 *  fall through the ladder; a reader hash that cannot be decoded returns the
 *  landing route, same defensive posture as the rest of `readRoute`. */
function parseReaderRoute(hash: string): Route | null {
  const m = /^#\/r\/([^/?]+)(?:\/([^/?]+))?(?:\?(.*))?$/.exec(hash);
  if (!m) return null;
  const first = safeDecode(m[1] ?? "");
  const second = m[2] === undefined ? undefined : safeDecode(m[2]);
  if (first === null || second === null) return { kind: "landing" };
  const qs = new URLSearchParams(m[3]);
  const termParam = qs.get("term");
  // Parse `term=<int>` defensively — a bad value (e.g. a stale
  // bookmark) shouldn't break the reader; it just means no card
  // opens on first paint.
  const openTermId = termParam && /^\d+$/.test(termParam) ? Number(termParam) : undefined;
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
    sourceLang: qs.get("lang") ?? undefined,
    focusChunkId: qs.get("focus") ?? undefined,
    openTermId,
    syntaxChunkId: qs.get("syntax") ?? undefined,
  };
}

export function readRoute(): Route {
  const hash = window.location.hash;
  let m = /^#\/c\/([^/?]+)$/.exec(hash);
  if (m) {
    const id = safeDecode(m[1] ?? "");
    return id === null ? { kind: "landing" } : { kind: "conversation", id };
  }
  const readerRoute = parseReaderRoute(hash);
  if (readerRoute) return readerRoute;
  // Legacy syntax hash (#237's shape). Rewritten into the reader route with
  // the syntax modifier — see `syntaxChunkId` above. The chunk goes through as
  // `focus=` as well because this hash carries no lang: `around=<chunk>` makes
  // the server resolve work/lang/edition off the chunk row, where defaulting a
  // lang (as `work_range` does, to "grc") can open a different edition of the
  // same work. Without a `work=` there is no reader location to resolve and so
  // no layer to lay the overlay over, which lands on the landing route.
  m = /^#\/syntax\/([^?]+)(?:\?(.*))?$/.exec(hash);
  if (m) {
    const qs = new URLSearchParams(m[2]);
    const rawWork = qs.get("work");
    const workId = rawWork ? safeDecode(rawWork) : null;
    const chunkId = safeDecode(m[1] ?? "");
    if (workId === null || chunkId === null) return { kind: "landing" };
    return {
      kind: "reader",
      workSlug: slugify(workId),
      focusChunkId: chunkId,
      syntaxChunkId: chunkId,
    };
  }
  m = /^#\/network\/(arc|coverage)(?:\?(.*))?$/.exec(hash);
  if (m) {
    const qs = new URLSearchParams(m[2]);
    const rawConf = qs.get("min_confidence");
    const minConfidence =
      rawConf !== null && /^[0-9.]+$/.test(rawConf) ? Number(rawConf) : undefined;
    const shared = {
      minConfidence,
      sourceAuthors: decodeCsv(qs.get("source")),
      corpora: decodeCsv(qs.get("corpus")),
      sourceMethods: decodeCsv(qs.get("method")),
    };
    return m[1] === "arc"
      ? { kind: "network-arc", ...shared }
      : { kind: "network-coverage", ...shared };
  }
  m = /^#\/network(?:\?(.*))?$/.exec(hash);
  if (m) {
    const qs = new URLSearchParams(m[1]);
    const rawConf = qs.get("min_confidence");
    const minConfidence =
      rawConf !== null && /^[0-9.]+$/.test(rawConf) ? Number(rawConf) : undefined;
    return {
      kind: "network",
      minConfidence,
      includeRejected: qs.get("include_rejected") === "1",
      sourceAuthors: decodeCsv(qs.get("source")),
      corpora: decodeCsv(qs.get("corpus")),
      sourceMethods: decodeCsv(qs.get("method")),
    };
  }
  m = /^#\/metrics(?:\?(.*))?$/.exec(hash);
  if (m) {
    const qs = new URLSearchParams(m[1]);
    const rawWindow = qs.get("window");
    // Reject an unrecognized window rather than carrying it through —
    // a stale bookmark or a hand-edited hash otherwise reaches the
    // panel as a value outside `METRIC_WINDOWS`, which is exactly the
    // "broken page" this guard exists to avoid.
    const isKnownWindow = (v: string): v is MetricWindow =>
      (METRIC_WINDOWS as readonly string[]).includes(v);
    const window = rawWindow !== null && isKnownWindow(rawWindow) ? rawWindow : undefined;
    return {
      kind: "metrics",
      window,
      label: qs.get("label") ?? undefined,
    };
  }
  m = /^#\/refs\/review(?:\?(.*))?$/.exec(hash);
  if (m) {
    const qs = new URLSearchParams(m[1]);
    const idRaw = qs.get("id");
    return {
      kind: "refs-review",
      sourceAuthor: qs.get("source") ?? undefined,
      referenceType: qs.get("type") ?? undefined,
      referenceId: idRaw && /^\d+$/.test(idRaw) ? Number(idRaw) : undefined,
    };
  }
  m = /^#\/concordance\/([^?]+)(?:\?(.*))?$/.exec(hash);
  if (m) {
    const lemma = safeDecode(m[1] ?? "");
    if (lemma === null) return { kind: "landing" };
    const qs = new URLSearchParams(m[2]);
    const scope = qs.get("scope");
    return {
      kind: "concordance-lemma",
      lemma,
      lang: qs.get("lang") ?? undefined,
      scope: scope === "corpus" || scope === "author" || scope === "work" ? scope : undefined,
      scopeAuthors: decodeCsv(qs.get("author")),
      scopeWorks: decodeCsv(qs.get("work")),
      caseFilter: qs.get("case") ?? undefined,
      numberFilter: qs.get("number") ?? undefined,
      surface: qs.get("surface") ?? undefined,
    };
  }
  m = /^#\/concordance(?:\?(.*))?$/.exec(hash);
  if (m) {
    const qs = new URLSearchParams(m[1]);
    const scope = qs.get("scope");
    const sort = qs.get("sort");
    const freqMinRaw = qs.get("freq_min");
    const freqMaxRaw = qs.get("freq_max");
    return {
      kind: "concordance",
      lang: qs.get("lang") ?? undefined,
      scope: scope === "corpus" || scope === "author" || scope === "work" ? scope : undefined,
      scopeAuthors: decodeCsv(qs.get("author")),
      scopeWorks: decodeCsv(qs.get("work")),
      letter: qs.get("letter") ?? undefined,
      sort: sort === "freq" || sort === "alpha" || sort === "pos" ? sort : undefined,
      pos: qs.get("pos") ?? undefined,
      freqMin: freqMinRaw && /^\d+$/.test(freqMinRaw) ? Number(freqMinRaw) : undefined,
      freqMax: freqMaxRaw && /^\d+$/.test(freqMaxRaw) ? Number(freqMaxRaw) : undefined,
      q: qs.get("q") ?? undefined,
    };
  }
  m = /^#\/refs(?:\?(.*))?$/.exec(hash);
  if (m) {
    // URLSearchParams accepts undefined and treats it as an empty
    // query string, so we don't need an explicit `?? ""` fallback.
    const qs = new URLSearchParams(m[1]);
    return {
      kind: "refs",
      sourceAuthor: qs.get("source") ?? undefined,
      targetAuthor: qs.get("target") ?? undefined,
      targetWork: qs.get("work") ?? undefined,
      referenceType: qs.get("type") ?? undefined,
      includeRejected: qs.get("include_rejected") === "1",
    };
  }
  return { kind: "landing" };
}

export function routeHash(route: Route): string {
  if (route.kind === "conversation") return `#/c/${encodeURIComponent(route.id)}`;
  if (route.kind === "reader") {
    const params = new URLSearchParams();
    if (route.sourceLang) params.set("lang", route.sourceLang);

    if (route.focusChunkId) params.set("focus", route.focusChunkId);
    if (route.openTermId !== undefined) params.set("term", String(route.openTermId));
    if (route.syntaxChunkId) params.set("syntax", route.syntaxChunkId);
    const qs = params.toString();
    // Slugs are `[a-z0-9-]` by construction, so `encodeURIComponent` is the
    // identity here; it stays as a guard against a non-slug ever reaching this
    // path, not because anything needs escaping.
    const base = route.authorSlug
      ? `#/r/${encodeURIComponent(route.authorSlug)}/${encodeURIComponent(route.workSlug)}`
      : `#/r/${encodeURIComponent(route.workSlug)}`;
    return qs ? `${base}?${qs}` : base;
  }
  if (route.kind === "refs") {
    const params = new URLSearchParams();
    if (route.sourceAuthor) params.set("source", route.sourceAuthor);
    if (route.targetAuthor) params.set("target", route.targetAuthor);
    if (route.targetWork) params.set("work", route.targetWork);
    if (route.referenceType) params.set("type", route.referenceType);
    if (route.includeRejected) params.set("include_rejected", "1");
    const qs = params.toString();
    return qs ? `#/refs?${qs}` : "#/refs";
  }
  if (route.kind === "refs-review") {
    const params = new URLSearchParams();
    if (route.sourceAuthor) params.set("source", route.sourceAuthor);
    if (route.referenceType) params.set("type", route.referenceType);
    if (route.referenceId !== undefined) params.set("id", String(route.referenceId));
    const qs = params.toString();
    return qs ? `#/refs/review?${qs}` : "#/refs/review";
  }
  if (route.kind === "network") {
    const params = new URLSearchParams();
    if (route.minConfidence !== undefined)
      params.set("min_confidence", String(route.minConfidence));
    if (route.includeRejected) params.set("include_rejected", "1");
    if (route.sourceAuthors?.length) params.set("source", encodeCsv(route.sourceAuthors));
    if (route.corpora?.length) params.set("corpus", encodeCsv(route.corpora));
    if (route.sourceMethods?.length) params.set("method", encodeCsv(route.sourceMethods));
    const qs = params.toString();
    return qs ? `#/network?${qs}` : "#/network";
  }
  if (route.kind === "concordance") {
    const params = new URLSearchParams();
    if (route.lang) params.set("lang", route.lang);
    if (route.scope) params.set("scope", route.scope);
    if (route.scopeAuthors?.length) params.set("author", encodeCsv(route.scopeAuthors));
    if (route.scopeWorks?.length) params.set("work", encodeCsv(route.scopeWorks));
    if (route.letter) params.set("letter", route.letter);
    if (route.sort) params.set("sort", route.sort);
    if (route.pos) params.set("pos", route.pos);
    if (route.freqMin !== undefined) params.set("freq_min", String(route.freqMin));
    if (route.freqMax !== undefined) params.set("freq_max", String(route.freqMax));
    if (route.q) params.set("q", route.q);
    const qs = params.toString();
    return qs ? `#/concordance?${qs}` : "#/concordance";
  }
  if (route.kind === "concordance-lemma") {
    const params = new URLSearchParams();
    if (route.lang) params.set("lang", route.lang);
    if (route.scope) params.set("scope", route.scope);
    if (route.scopeAuthors?.length) params.set("author", encodeCsv(route.scopeAuthors));
    if (route.scopeWorks?.length) params.set("work", encodeCsv(route.scopeWorks));
    if (route.caseFilter) params.set("case", route.caseFilter);
    if (route.numberFilter) params.set("number", route.numberFilter);
    if (route.surface) params.set("surface", route.surface);
    const qs = params.toString();
    const base = `#/concordance/${encodeURIComponent(route.lemma)}`;
    return qs ? `${base}?${qs}` : base;
  }
  if (route.kind === "metrics") {
    const params = new URLSearchParams();
    if (route.window) params.set("window", route.window);
    if (route.label) params.set("label", route.label);
    const qs = params.toString();
    return qs ? `#/metrics?${qs}` : "#/metrics";
  }
  if (route.kind === "network-arc" || route.kind === "network-coverage") {
    const sub = route.kind === "network-arc" ? "arc" : "coverage";
    const params = new URLSearchParams();
    if (route.minConfidence !== undefined)
      params.set("min_confidence", String(route.minConfidence));
    if (route.sourceAuthors?.length) params.set("source", encodeCsv(route.sourceAuthors));
    if (route.corpora?.length) params.set("corpus", encodeCsv(route.corpora));
    if (route.sourceMethods?.length) params.set("method", encodeCsv(route.sourceMethods));
    const qs = params.toString();
    return qs ? `#/network/${sub}?${qs}` : `#/network/${sub}`;
  }
  return "#/";
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
