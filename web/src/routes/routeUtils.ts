import type { NetworkFilterParams } from "~/api/networkApi";
import type { Route } from "~/routing";

export type RouteRefs = Extract<Route, { kind: "refs" }>;
export type RouteRefsReview = Extract<Route, { kind: "refs-review" }>;
export type RouteNetwork = Extract<Route, { kind: "network" }>;
export type RouteNetworkArc = Extract<Route, { kind: "network-arc" }>;
export type RouteNetworkCoverage = Extract<Route, { kind: "network-coverage" }>;
export type RouteConcordance = Extract<Route, { kind: "concordance" }>;
export type RouteLemma = Extract<Route, { kind: "concordance-lemma" }>;
export type RouteMetrics = Extract<Route, { kind: "metrics" }>;

export function isRefsRoute(r: Route): r is RouteRefs {
  return r.kind === "refs";
}

export function isRefsReviewRoute(r: Route): r is RouteRefsReview {
  return r.kind === "refs-review";
}

export function isNetworkRoute(r: Route): r is RouteNetwork {
  return r.kind === "network";
}

export function isNetworkArcRoute(r: Route): r is RouteNetworkArc {
  return r.kind === "network-arc";
}

export function isNetworkCoverageRoute(r: Route): r is RouteNetworkCoverage {
  return r.kind === "network-coverage";
}

export function isConcordanceRoute(r: Route): r is RouteConcordance {
  return r.kind === "concordance";
}

export function isLemmaRoute(r: Route): r is RouteLemma {
  return r.kind === "concordance-lemma";
}

export function isMetricsRoute(r: Route): r is RouteMetrics {
  return r.kind === "metrics";
}

/** Routes you step OUT to from the Reader and step back from, as opposed to
 *  destinations you arrive at (#348).
 *
 *  A step-out keeps the Reader mounted underneath it — `useWorkRange`'s
 *  signals, the scroll position, the open term card, the pinned highlights,
 *  the translate rail and the selection toolbar all survive the round trip,
 *  none of which the `readCache` from #343 can restore. A destination
 *  releases it, because there is no passage to come back to and a retained
 *  Reader would keep a window, its effects and its `IntersectionObserver`
 *  alive behind a full-page view for the rest of the session.
 *
 *  Both concordance kinds qualify: `Reader/index.tsx` links to the lemma
 *  detail from the rail's lemma card and to the index from the
 *  work-concordance link. Nothing in the Reader links to the network
 *  dashboard or the refs browser — both are top-nav entry points — so they
 *  are destinations, which is why they are absent here rather than
 *  overlooked. #342 fixed the fourth case, the syntax overlay, by a
 *  different mechanism: it is a modifier on the reader route itself, so the
 *  route never stops being a reader route and this predicate never sees it. */
export function keepsReaderAlive(r: Route): boolean {
  return r.kind === "concordance" || r.kind === "concordance-lemma";
}

export type NetworkFilterFields = NetworkFilterParams;

/** Shared network filter fields from any network-related route. */
export function networkFiltersFromRoute(
  r: Extract<
    Route,
    { kind: "network" | "network-arc" | "network-coverage" }
  >,
): NetworkFilterFields {
  return {
    minConfidence: r.minConfidence,
    includeRejected: r.includeRejected,
    sourceAuthors: r.sourceAuthors,
    corpora: r.corpora,
    sourceMethods: r.sourceMethods,
  };
}

export function networkRouteFromFilters(
  kind: "network" | "network-arc" | "network-coverage",
  filters: NetworkFilterFields,
): Route {
  return { kind, ...filters };
}

/** Merge patch into base; `undefined` in patch means preserve base value. */
export function mergeRoutePatch<T extends object>(
  base: T,
  patch: Partial<T>,
): T {
  const out = { ...base };
  for (const key of Object.keys(patch) as (keyof T)[]) {
    if (patch[key] !== undefined) {
      out[key] = patch[key];
    }
  }
  return out;
}

/** Merge patch allowing explicit `undefined` clears (uses `in` check). */
export function mergeRoutePatchAllowClear<T extends object>(
  base: T,
  patch: Partial<T>,
): T {
  const out = { ...base };
  for (const key of Object.keys(patch) as (keyof T)[]) {
    if (key in patch) {
      out[key] = patch[key] as T[keyof T];
    }
  }
  return out;
}
